#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3_process_corpus.py — Paso 3 del pipeline research_agent

Pipeline batch: PDF → TEI XML (GROBID) → Markdown limpio → chunks JSONL.

Posición en el pipeline:
    categorias/<phase>/pdfs/ → 3_process_corpus.py → tei/ + md_clean/ + chunks/

Etapas por cada PDF:
    1. GROBID: convierte el PDF a TEI XML (estructura académica completa)
    2. Extracción: parsea el TEI para obtener secciones, tablas y captions
    3. Limpieza: elimina ruido, normaliza espacios, descarta secciones vacías
    4. Chunking: divide el Markdown en fragmentos de ~1500 chars con solapamiento

Skip logic:
    Si el .tei.xml, el .clean.md y el .jsonl correspondientes ya existen y ni
    --force ni --force-md están activos, el PDF se salta. Permite reanudar
    ingestas interrumpidas sin reprocesar lo ya completado.

Chunking — comportamiento (items 62 y 63, 2026-07-26):
    - El H1 (título del paper) y el preámbulo NO se clasifican con
      canonical_section(): un título con "Operational" etiquetaba la portada como
      methods y contagiaba la etiqueta a las subsecciones del cuerpo sin
      clasificación propia (item 62.1).
    - Los bloques de portada sin prosa propia (`**Authors:**` + `**Year|DOI**`,
      < 200 chars de residuo) se FUSIONAN con el chunk siguiente y heredan SU
      section_canonical (item 62.2). chunk_index se renumera tras las fusiones.
    - Cada fila de tabla es un párrafo, así que el splitter corta en frontera de
      fila y nunca fusiona filas de estudios distintos (item 63.1).
    - Cuando una tabla se trocea, TODAS las partes llevan `### Table N` + caption
      (item 63.3).

Ficheros leídos:
    /Volumes/research/categorias/<phase>/pdfs/*.pdf   ← PDFs de entrada
    config/.env                                        ← GROBID_URL, OLLAMA_HOST

Ficheros escritos:
    /Volumes/research/categorias/<phase>/
        tei/<paper_id>.tei.xml          ← TEI bruto de GROBID
        md_clean/<paper_id>.clean.md    ← Markdown limpio
        chunks/<paper_id>.jsonl         ← Chunks para embeddings
        logs/3_process_corpus_report.csv

Parámetros CLI:
    --phase PHASE         Nombre de la categoría/fase a procesar (obligatorio)
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)
    --input-dir-a DIR     Carpeta alternativa de PDFs (sobreescribe la ruta por defecto)
    --grobid URL          URL del servidor GROBID
    --limit N             Procesa solo los primeros N PDFs
    --target-words N      Tamaño objetivo por chunk en palabras (defecto: 850)
    --overlap-words N     Solape entre chunks en palabras (defecto: 120)
    --sleep SEGS          Pausa entre PDFs (defecto: 0)
    --force               Reprocesa todo desde el PDF, RE-INVOCANDO GROBID
    --force-md            Regenera md_clean + chunks desde el TEI existente, SIN
                          llamar a GROBID (falla si no hay TEI). Es el flag para
                          re-trocear tras un cambio del chunker.
    --dry-run             Lista PDFs a procesar sin ejecutar nada

Variables de entorno (config/.env):
    GROBID_URL            URL del servidor GROBID (defecto: http://127.0.0.1:8070)
    OLLAMA_HOST           URL del servidor Ollama  (defecto: http://127.0.0.1:11435)

Dependencias:
    requests, python-dotenv, xml.etree.ElementTree (stdlib)

Notas:
    - GROBID necesita warm-up tras inactividad; la primera llamada puede ser lenta.
    - Errores "[Errno 2] No such file" en PDFs que sí existen indican inestabilidad
      de red/NAS. Solución: copiar los PDFs fallidos a /tmp/<fase>_retry y relanzar
      con --input-dir-a apuntando a esa carpeta y el mismo --phase.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

# ── Cargar config/.env antes de leer variables de entorno ────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

try:
    from utils.constants import MAX_EMBED_CHARS
except Exception:
    MAX_EMBED_CHARS = 8000

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

DEFAULT_BASE   = "/Volumes/research/categorias"
DEFAULT_GROBID = os.getenv("GROBID_URL", "http://127.0.0.1:8070")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11435")

VALID_PHASES = [
    "biological_gas_odor_treatment",
    "anoxic_biogas_biodesulfurization",
    "bioplastics_microplastics",
    "biogas_upgrading_biomethanation",
    "microalgae",
    "single_cell_protein",
    "advanced_oxidation_processes",
    "bioleaching_critical_materials",
]

ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


# ============================================================
# UTILIDADES DE TEXTO
# ============================================================

def norm_space(s: str) -> str:
    s = "" if s is None else s
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def safe_slug(filename_stem: str) -> str:
    s = filename_stem.strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s\.-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s\.-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:120] if len(s) > 120 else s


# ============================================================
# GROBID
# ============================================================

def grobid_process_pdf(pdf_path: Path, grobid_url: str, timeout: int = 600) -> str:
    with pdf_path.open("rb") as f:
        files = {"input": (pdf_path.name, f, "application/pdf")}
        r = requests.post(f"{grobid_url}/api/processFulltextDocument", files=files, timeout=timeout)
    r.raise_for_status()
    return r.text


# ============================================================
# TEI → MARKDOWN
# ============================================================

def tei_get_text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return norm_space("".join(el.itertext()))


def tei_get_text_spaced(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return norm_space(" ".join(t.strip() for t in el.itertext() if t.strip()))


def tei_find_first(root: ET.Element, xpath: str) -> Optional[ET.Element]:
    return root.find(xpath, TEI_NS)


def tei_find_all(root: ET.Element, xpath: str) -> List[ET.Element]:
    return root.findall(xpath, TEI_NS)


def first_existing(*elements: Optional[ET.Element]) -> Optional[ET.Element]:
    for el in elements:
        if el is not None:
            return el
    return None


TEI_URI = "http://www.tei-c.org/ns/1.0"

_REF_HEAD_RE = re.compile(r'^\s*\([\d,;\s–\-]+\)\s*$')
_FIG_HEAD_RE = re.compile(r'(?i)\b(fig(?:ure)?s?\.?\s*[\dIVX]|table\s*[\dIVX]|scheme\s*\d|chart\s*\d)')


def _tei_tag(el: ET.Element) -> str:
    return el.tag.split('}')[-1] if '}' in el.tag else el.tag


def _extract_div_content(el: ET.Element, parts: List[str], depth: int = 2) -> None:
    hashes = "#" * min(depth, 6)
    for child in el:
        t = _tei_tag(child)

        if t == "div":
            head_el  = child.find(f"{{{TEI_URI}}}head")
            head_txt = tei_get_text(head_el).strip() if head_el is not None else ""
            if head_txt:
                parts.append(f"{hashes} {head_txt}\n")
            _extract_div_content(child, parts, depth + 1)

        elif t == "p":
            txt = tei_get_text(child)
            if txt:
                parts.append(txt + "\n")

        elif t == "formula":
            ft = tei_get_text(child)
            if ft:
                parts.append("$$\n" + ft + "\n$$\n")

        elif t == "list":
            for item in child.findall(f"{{{TEI_URI}}}item"):
                txt = tei_get_text(item)
                if txt:
                    parts.append(f"- {txt}\n")

        elif t == "figure":
            fig_type = child.get("type", "")
            head_el  = child.find(f"{{{TEI_URI}}}head")
            desc_el  = child.find(f"{{{TEI_URI}}}figDesc")
            head_txt = tei_get_text(head_el).strip() if head_el is not None else ""
            desc_txt = tei_get_text(desc_el).strip() if desc_el is not None else ""

            if _REF_HEAD_RE.match(head_txt):
                continue

            if fig_type == "table":
                if head_txt:
                    parts.append(f"**{head_txt}**\n")
                if desc_txt:
                    parts.append(desc_txt + "\n")
                for row in child.findall(f".//{{{TEI_URI}}}row"):
                    cells = [norm_space("".join(c.itertext()))
                             for c in row.findall(f"{{{TEI_URI}}}cell")]
                    if any(cells):
                        parts.append("| " + " | ".join(cells) + " |\n")
            else:
                if head_txt and _FIG_HEAD_RE.search(head_txt):
                    parts.append(f"*{head_txt}*\n")
                if desc_txt:
                    parts.append(desc_txt + "\n")

        elif t == "head":
            continue

        else:
            _extract_div_content(child, parts, depth)


def tei_to_md_clean(tei_xml: str) -> Tuple[str, str, int, int]:
    """Convierte TEI XML de GROBID a Markdown limpio.
    Devuelve (paper_title, md, tei_body_words, md_words).
    """
    root = ET.fromstring(tei_xml)

    title_el    = tei_find_first(root, ".//tei:teiHeader//tei:titleStmt/tei:title")
    paper_title = tei_get_text(title_el) or "Untitled"

    authors = []
    for a in root.findall(".//tei:teiHeader//tei:author", TEI_NS):
        pers = a.find(f".//{{{TEI_URI}}}persName")
        if pers is not None:
            txt = tei_get_text_spaced(pers).strip()
            if txt:
                authors.append(txt)

    doi = None
    for idno in root.findall(".//tei:teiHeader//tei:idno", TEI_NS):
        if (idno.get("type") or "").lower() == "doi":
            doi = tei_get_text(idno).strip()
            break

    year     = None
    date_el  = root.find(
        ".//tei:teiHeader//tei:sourceDesc//tei:monogr//tei:imprint//tei:date", TEI_NS
    )
    if date_el is not None:
        m = re.search(r"\b(19|20)\d{2}\b", date_el.get("when", ""))
        if m:
            year = m.group(0)

    abs_el   = first_existing(
        tei_find_first(root, ".//tei:teiHeader//tei:profileDesc//tei:abstract"),
        tei_find_first(root, ".//tei:teiHeader//tei:abstract"),
        tei_find_first(root, ".//tei:text//tei:front//tei:abstract"),
    )
    abstract = tei_get_text(abs_el)

    body           = tei_find_first(root, ".//tei:text//tei:body")
    tei_body_words = len(tei_get_text(body).split()) if body is not None else 0

    parts: List[str] = []
    parts.append(f"# {paper_title}\n")
    if authors:
        parts.append(f"**Authors:** {'; '.join(authors[:12])}\n")
    meta_bits = []
    if year:
        meta_bits.append(f"Year: {year}")
    if doi:
        meta_bits.append(f"DOI: {doi}")
    if meta_bits:
        parts.append("**" + " | ".join(meta_bits) + "**\n")
    if abstract:
        parts.append("## Abstract\n")
        parts.append(abstract + "\n")
    if body is not None:
        _extract_div_content(body, parts, depth=2)

    md       = norm_space("\n".join(parts)) + "\n"
    md_words = len(md.split())
    return paper_title, md, tei_body_words, md_words


# ============================================================
# TABLAS
# ============================================================

def extract_tables_md(tei_xml: str) -> List[Dict]:
    """Extrae las tablas del TEI como Markdown de una fila por párrafo.

    Item 63.1 — CADA FILA ES UN PÁRRAFO (separada por `\\n\\n`), en las dos ramas
    (con y sin columna "Exp."). Antes se unían con un solo `\\n`, así que la tabla
    entera era UN párrafo para `_split_to_max_chars`: una tabla que superara
    MAX_EMBED_CHARS caía a la rama de emergencia por palabras y fusionaba filas de
    estudios distintos (2023_almenglo #34). Con filas como párrafos, el splitter
    corta siempre en frontera de fila por su ruta normal.

    Devuelve dicts con:
        table_id, title
        header_md  ← `### <head>` + caption; se antepone a CADA parte (item 63.3)
        body_md    ← solo las filas, un párrafo cada una
        text       ← header_md + body_md (la tabla completa, como antes)
    """
    root   = ET.fromstring(tei_xml)
    tables = []

    for fig in tei_find_all(root, ".//tei:figure[@type='table']"):
        table_id = fig.get("{http://www.w3.org/XML/1998/namespace}id", "") or ""
        head     = tei_get_text(tei_find_first(fig, "./tei:head")) or "Table"
        desc     = tei_get_text(tei_find_first(fig, "./tei:figDesc"))

        rows = []
        for row in fig.findall(".//tei:table/tei:row", TEI_NS):
            cells = [norm_space("".join(c.itertext())) for c in row.findall("./tei:cell", TEI_NS)]
            rows.append(cells)

        if len(rows) < 2:
            continue

        header, data = rows[0], rows[1:]

        # Ancla semántica de la tabla (heading + caption), separada del cuerpo
        # para poder repetirla en cada parte cuando la tabla se trocee.
        header_md = f"### {head}"
        if desc:
            header_md += f"\n\n*{desc}*"

        blocks: List[str] = []

        exp_col_idx = next(
            (i for i, h in enumerate(header) if h.strip().lower() in {"exp.", "exp", "experiment"}),
            None,
        )

        if exp_col_idx is not None:
            current_key, current_rows = None, []

            def flush_block(k, block_rows):
                if k is None or not block_rows:
                    return
                blocks.append(f"**Experiment {k}**")
                for r in block_rows:
                    r   = r + [""] * (len(header) - len(r))
                    row = dict(zip(header, r))
                    parts = [f"{hk}: {row.get(hk,'').strip()}" for hk in header if row.get(hk,"").strip()]
                    blocks.append("- " + " | ".join(parts))

            for r in data:
                r = r + [""] * (len(header) - len(r))
                k = r[exp_col_idx].strip()
                if k:
                    flush_block(current_key, current_rows)
                    current_key, current_rows = k, [r]
                elif current_key is not None:
                    current_rows.append(r)
            flush_block(current_key, current_rows)
        else:
            for r in data:
                r     = r + [""] * (len(header) - len(r))
                pairs = [f"{header[i]}: {r[i]}" for i in range(len(header)) if r[i].strip()]
                if pairs:
                    blocks.append("- " + " | ".join(pairs))

        body_md = norm_space("\n\n".join(blocks))
        text    = norm_space(f"{header_md}\n\n{body_md}") + "\n"
        tables.append({
            "table_id":  table_id,
            "title":     head,
            "header_md": header_md,
            "body_md":   body_md,
            "text":      text,
        })

    return tables


# ============================================================
# CHUNKING
# ============================================================

# Keyword patterns for mapping a heading title to a canonical section name.
# Order matters: first match wins.
# Conjunto canónico de etiquetas: utils.constants.CANONICAL_SECTIONS (guard: tests/test_canonical_sections.py).
_CANON_PATTERNS: List[Tuple[str, List[str]]] = [
    ("abstract",     ["abstract"]),
    ("introduction", ["introduction", "background", "motivation"]),
    ("methods",      ["method", "material", "experiment", "procedure",
                      "setup", "approach", "protocol", "design", "operational"]),
    ("results",      ["result", "finding", "performance", "measurement",
                      "characterization", "evaluation", "removal", "efficiency"]),
    ("discussion",   ["discussion"]),
    ("conclusion",   ["conclusion", "summary", "outlook", "future", "perspective"]),
]


def canonical_section(title: str) -> str:
    """Maps a heading title to a canonical section label.

    Returns one of: abstract | introduction | methods | results |
    discussion | conclusion | other.
    """
    t = title.lower()
    for canon, keywords in _CANON_PATTERNS:
        for kw in keywords:
            if kw in t:
                return canon
    return "other"


def split_by_headings(md: str) -> List[Tuple[str, str, int]]:
    """Split md_clean into (title, text, level) sections.

    level = number of leading '#' characters (1–6). Preamble (text before
    the first heading) gets level 0. Chunk sizes and overlap are unchanged.
    """
    lines         = md.splitlines()
    sections: List[Tuple[str, List[str], int]] = []
    current_title = "Preamble"
    current_level = 0
    buf: List[str] = []
    heading_re    = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

    for ln in lines:
        m = heading_re.match(ln)
        if m:
            if buf:
                sections.append((current_title, buf, current_level))
            current_title = m.group(2).strip()
            current_level = len(m.group(1))
            buf = []
        else:
            buf.append(ln)

    if buf:
        sections.append((current_title, buf, current_level))

    return [
        (t, norm_space("\n".join(b)), lvl)
        for t, b, lvl in sections
        if norm_space("\n".join(b))
    ]


def chunk_text(text: str, target_words: int, overlap_words: int) -> List[str]:
    paras   = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    cur: List[str] = []
    cur_words = 0

    def wc(s: str) -> int:
        return len(s.split())

    def flush_with_overlap():
        nonlocal cur, cur_words
        if not cur:
            return
        chunk = "\n\n".join(cur).strip()
        if chunk:
            chunks.append(chunk)
        if overlap_words > 0:
            w    = chunk.split()
            tail = w[-overlap_words:] if len(w) > overlap_words else w
            cur, cur_words = [" ".join(tail)], len(tail)
        else:
            cur, cur_words = [], 0

    for p in paras:
        pw = wc(p)
        if pw > target_words * 1.2:
            flush_with_overlap()
            w    = p.split()
            step = max(1, target_words - overlap_words)
            for i in range(0, len(w), step):
                chunks.append(" ".join(w[i:i + target_words]).strip())
            cur, cur_words = [], 0
            continue
        if cur_words + pw <= target_words:
            cur.append(p)
            cur_words += pw
        else:
            flush_with_overlap()
            cur.append(p)
            cur_words += pw

    if cur:
        chunk = "\n\n".join(cur).strip()
        if chunk:
            chunks.append(chunk)

    return chunks


def write_jsonl(path: Path, records: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _split_long_para(para: str, max_chars: int) -> List[str]:
    """Trocea UN párrafo que ya no cabe en max_chars, degradando por niveles.

    Item 63.2 (cinturón y tirantes): antes esta rama hacía `para.split()` +
    `" ".join`, que destruía TODOS los saltos de línea y podía fusionar dos filas
    de tabla en una sola entrada. Ahora respeta primero los `\\n` (unidad natural
    de fila) y solo baja a palabras dentro de una línea que por sí sola no cabe.
    Último recurso: corte duro de un token atómico gigante.
    """
    out: List[str] = []
    cur = ""

    def add_unit(unit: str, sep: str) -> None:
        nonlocal cur
        if cur and len(cur) + len(sep) + len(unit) > max_chars:
            out.append(cur)
            cur = unit
        else:
            cur = f"{cur}{sep}{unit}" if cur else unit

    for line in para.split("\n"):
        if not line.strip():
            continue
        if len(line) <= max_chars:
            add_unit(line, "\n")
            continue
        # La línea sola ya no cabe: degradar a palabras DENTRO de esta línea.
        for w in line.split():
            if len(w) > max_chars:                 # token atómico gigante
                if cur:
                    out.append(cur); cur = ""
                while len(w) > max_chars:
                    out.append(w[:max_chars]); w = w[max_chars:]
                if w:
                    cur = w
            else:
                add_unit(w, " ")

    if cur:
        out.append(cur)
    return out


def _split_to_max_chars(text: str, max_chars: int) -> List[str]:
    """Trocea text en piezas de <= max_chars respetando párrafos/líneas/palabras.
    Devuelve [text] si ya cabe; [] si está vacío."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    out: List[str] = []
    cur = ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            if cur:
                out.append(cur); cur = ""
            pieces = _split_long_para(para, max_chars)
            if pieces:
                out.extend(pieces[:-1])
                cur = pieces[-1]      # el último sigue abierto para el párrafo siguiente
        elif cur and len(cur) + 2 + len(para) > max_chars:
            out.append(cur); cur = para
        else:
            cur = f"{cur}\n\n{para}".strip() if cur else para
    if cur:
        out.append(cur)
    return out


# ── Portadas vacías (item 62.2) ───────────────────────────────────────────────
# Umbral de prosa por debajo del cual un bloque de portada se considera remanente
# sin contenido propio y se fusiona con el chunk siguiente.
COVER_PROSE_MIN_CHARS = 200

# Presupuesto mínimo que debe quedar para el CUERPO de una tabla tras descontar su
# ancla (item 63.3). Si el heading + caption fuera tan largo que no dejara ni esto,
# se emite sin ancla antes que trocear la tabla en migajas.
MIN_TABLE_BODY_BUDGET = 200

_COVER_AUTHORS_RE = re.compile(r"(?im)^[ \t]*\*\*Authors:\*\*.*$")
_COVER_META_RE    = re.compile(r"(?im)^[ \t]*\*\*(?:Year|DOI)\b.*$")


def cover_residue_chars(text: str) -> Optional[int]:
    """Chars de prosa que quedan en un bloque de portada, o None si no es portada.

    Criterio de la verificación P3 (2026-07-26), reproducido tal cual: si el chunk
    contiene una línea `**Authors:**…`, se eliminan esa línea y las
    `**Year…**`/`**DOI…**`, se colapsan los saltos sobrantes y se mide el resto.
    Por debajo de COVER_PROSE_MIN_CHARS el bloque no tiene contenido propio
    (809 de 823 casos medidos en las 8 categorías).

    Devuelve None cuando el bloque no es una portada, para distinguirlo de una
    portada cuyo residuo mide 0.
    """
    if not _COVER_AUTHORS_RE.search(text or ""):
        return None
    rest = _COVER_AUTHORS_RE.sub("", text)
    rest = _COVER_META_RE.sub("", rest)
    rest = re.sub(r"\n{2,}", "\n\n", rest).strip()
    return len(rest)


def merge_empty_cover_blocks(pieces: List[Dict]) -> List[Dict]:
    """Fusiona los bloques de portada sin contenido propio con el chunk SIGUIENTE.

    Item 62.2. La regla es DE CONTENIDO, no posicional: se aplica a cualquier
    pieza que cumpla el criterio de `cover_residue_chars`, no solo a la primera.
    Así los autores siguen siendo recuperables y no quedan vectores muertos
    diluyendo el pool.

    Guardas:
      - sin chunk siguiente (paper que solo tiene portada) → se emite tal cual;
      - si el fusionado superaría MAX_EMBED_CHARS → no se fusiona;
      - el fusionado hereda la metadata de sección del chunk SIGUIENTE
        (section, section_canonical, section_part), nunca la del remanente.
    """
    out: List[Dict] = []
    i = 0
    while i < len(pieces):
        cur     = pieces[i]
        residue = cover_residue_chars(cur["text"])
        if residue is not None and residue < COVER_PROSE_MIN_CHARS:
            if i + 1 >= len(pieces):
                out.append(cur)          # guarda: no hay siguiente
                break
            nxt         = pieces[i + 1]
            merged_text = f"{cur['text']}\n\n{nxt['text']}"
            if len(merged_text) <= MAX_EMBED_CHARS:   # guarda: no pasarse del tope
                merged         = dict(nxt)            # hereda sección del SIGUIENTE
                merged["text"] = merged_text
                out.append(merged)
                i += 2
                continue
        out.append(cur)
        i += 1
    return out


def build_chunk_records(
    md_clean: str,
    tables: List[Dict],
    *,
    phase: str,
    paper_id: str,
    paper_title: str,
    source_pdf: Path,
    source_tei: Path,
    source_md_clean: Path,
    target_words: int,
    overlap_words: int,
) -> List[Dict]:
    sections = split_by_headings(md_clean)  # (title, text, level)

    # Ancestor map: heading level → (title, canonical) for hierarchical
    # section_canonical. When a heading at level L is encountered, all
    # ancestor entries with level > L are dropped (we moved to a sibling
    # or parent section).
    ancestors: Dict[int, Tuple[str, str]] = {}

    # Piezas de texto sin numerar todavía: chunk_index se asigna DESPUÉS de
    # fusionar las portadas vacías (item 62.2), para que quede consecutivo.
    pieces: List[Dict] = []

    for sec_title, sec_text, level in sections:
        # Item 62.1: el nivel 1 es el TÍTULO del paper (tei_to_md_clean lo emite
        # como único H1; el cuerpo empieza en H2 porque _extract_div_content
        # arranca en depth=2), y el nivel 0 es el preámbulo. Ninguno es un
        # heading de sección, así que NO se clasifican: un título con
        # "Operational"/"characterization" etiquetaba el bloque de portada como
        # methods/results y, por el ascenso de ancestros de más abajo, contagiaba
        # esa etiqueta a toda subsección del cuerpo que no clasificara por sí misma.
        canonical = "other" if level <= 1 else canonical_section(sec_title)
        ancestors[level] = (sec_title, canonical)
        for k in list(ancestors.keys()):
            if k > level:
                del ancestors[k]

        if sec_title.lower().startswith("references"):
            continue

        # Effective canonical: nearest ancestor from this level up to 1
        # whose canonical is not "other". Preamble (level 0) always "other".
        sec_canonical = "other"
        for lvl in range(level, 0, -1):
            if lvl in ancestors and ancestors[lvl][1] != "other":
                sec_canonical = ancestors[lvl][1]
                break

        part_i = 0
        for ch in chunk_text(sec_text, target_words, overlap_words):
            for piece in _split_to_max_chars(ch, MAX_EMBED_CHARS):
                part_i += 1
                pieces.append({
                    "section":           sec_title,
                    "section_canonical": sec_canonical,
                    "section_part":      part_i,
                    "text":              piece,
                })

    pieces = merge_empty_cover_blocks(pieces)

    records: List[Dict] = []
    chunk_index = 1

    for p in pieces:
        records.append({
            "phase":             phase,
            "paper_id":          paper_id,
            "paper_title":       paper_title,
            "doc_type":          "article",
            "source_pdf":        str(source_pdf),
            "source_tei":        str(source_tei),
            "source_md_clean":   str(source_md_clean),
            "section":           p["section"],
            "section_canonical": p["section_canonical"],
            "type":              "text",
            "chunk_index":       chunk_index,
            "section_part":      p["section_part"],
            "text":              p["text"],
        })
        chunk_index += 1

    for t_i, tb in enumerate(tables, start=1):
        # Item 63.3: el heading + caption se antepone a CADA parte, no solo a la
        # primera. Se trocea el CUERPO con el presupuesto ya descontado, así que
        # ninguna parte puede pasarse de MAX_EMBED_CHARS al añadirle el ancla.
        header_md = tb.get("header_md", "")
        body_md   = tb.get("body_md", tb.get("text", ""))
        budget    = MAX_EMBED_CHARS - (len(header_md) + 2) if header_md else MAX_EMBED_CHARS
        if budget < MIN_TABLE_BODY_BUDGET:   # ancla patológicamente larga
            header_md, budget = "", MAX_EMBED_CHARS

        # `or [""]` preserva el comportamiento previo para una tabla cuyo cuerpo
        # queda vacío (celdas vacías en el TEI): se emite el ancla sola.
        for part_i, piece in enumerate(_split_to_max_chars(body_md, budget) or [""], start=1):
            text = f"{header_md}\n\n{piece}".strip() if header_md else piece
            records.append({
                "phase":             phase,
                "paper_id":          paper_id,
                "paper_title":       paper_title,
                "doc_type":          "article",
                "source_pdf":        str(source_pdf),
                "source_tei":        str(source_tei),
                "source_md_clean":   str(source_md_clean),
                "section":           tb.get("title", f"Table {t_i}"),
                "section_canonical": "table",
                "type":              "table",
                "chunk_index":       chunk_index,
                "table_id":          tb.get("table_id", ""),
                "section_part":      part_i,
                "text":              text,
            })
            chunk_index += 1

    return records


# ============================================================
# INFORME
# ============================================================

def write_report(report_rows: List[Dict], project_dir: Path) -> None:
    report_dir       = project_dir / "logs"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_csv_path  = report_dir / "3_process_corpus_report.csv"
    report_xlsx_path = report_dir / "3_process_corpus_report.xlsx"

    fieldnames = ["phase", "pdf_file", "pdf_path", "paper_id",
                  "tei_path", "md_clean_path", "chunks_path",
                  "status", "error", "seconds", "n_chunks",
                  "tei_body_words", "md_words", "md_warning"]

    try:
        import pandas as pd
        df = pd.DataFrame(report_rows, columns=fieldnames)
        df.to_csv(report_csv_path, index=False, encoding="utf-8-sig")
        print(f"Report CSV:  {report_csv_path}")
        try:
            df_xl = df.apply(lambda col: col.map(
                lambda v: ILLEGAL_XML.sub("", str(v)) if v is not None else ""
            ))
            df_xl.to_excel(report_xlsx_path, index=False, engine="openpyxl")
            print(f"Report XLSX: {report_xlsx_path}")
        except Exception as e:
            print(f"XLSX no generado: {e}")
    except ImportError:
        import csv as csv_mod
        with report_csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv_mod.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(report_rows)
        print(f"Report CSV:  {report_csv_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    ap = argparse.ArgumentParser(
        description="Pipeline batch: PDF → TEI (GROBID) → MD limpio → chunks JSONL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--phase", required=True,
        metavar="PHASE",
        help="Nombre de la fase/categoría del proyecto (p.ej. 'bioreactores', 'adhoc_xyz')",
    )
    ap.add_argument("--base",          default=DEFAULT_BASE,
                    help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--input-dir-a",   default="",
                    help="Carpeta de PDFs; si no se indica, usa <base>/<phase>/pdfs/")
    ap.add_argument("--grobid",        default=DEFAULT_GROBID,
                    help=f"URL base de GROBID (defecto: {DEFAULT_GROBID})")
    ap.add_argument("--limit",         type=int, default=0,
                    help="Procesar solo N PDFs (0 = todos)")
    ap.add_argument("--target-words",  type=int, default=850,
                    help="Tamaño objetivo por chunk en palabras")
    ap.add_argument("--overlap-words", type=int, default=120,
                    help="Solape entre chunks en palabras")
    ap.add_argument("--sleep",         type=float, default=0.0,
                    help="Pausa entre PDFs (segundos)")
    ap.add_argument("--force",         action="store_true",
                    help="Reprocesar aunque ya existan salidas")
    ap.add_argument("--force-md",      action="store_true",
                    help="Regenerar md_clean y chunks desde TEI existente sin llamar a GROBID")
    ap.add_argument("--dry-run",       action="store_true",
                    help="Solo lista lo que haría, sin llamar a GROBID ni escribir")
    args = ap.parse_args()

    base        = Path(args.base)
    phase       = args.phase
    project_dir = base / phase
    input_dir   = Path(args.input_dir_a) if args.input_dir_a else project_dir / "pdfs"

    # ── Carpetas de salida ────────────────────────────────────
    for subdir in ("tei", "md_clean", "chunks", "logs"):
        (project_dir / subdir).mkdir(parents=True, exist_ok=True)

    # ── Recoger PDFs ─────────────────────────────────────────
    if not input_dir.exists():
        raise SystemExit(f"No existe la carpeta de PDFs: {input_dir}")

    pdf_list: List[Tuple[str, Path]] = [
        (phase, pdf) for pdf in sorted(input_dir.glob("*.pdf"))
    ]

    if not pdf_list:
        raise SystemExit(f"No se encontraron PDFs en: {input_dir}")

    if args.limit and args.limit > 0:
        pdf_list = pdf_list[:args.limit]

    print(f"Phase     : {phase}")
    print(f"Base      : {base}")
    print(f"Input     : {input_dir}")
    print(f"PDFs      : {len(pdf_list)}")
    print(f"GROBID    : {args.grobid}")
    print(f"OLLAMA    : {OLLAMA_HOST}")
    if args.force_md and not args.force:
        print("Modo      : regenerar MD/chunks desde TEI existente")
    if args.dry_run:
        print("Modo      : DRY-RUN")
    print("")

    report_rows: List[Dict] = []

    for idx, (ph, pdf) in enumerate(pdf_list, start=1):
        paper_id    = safe_slug(pdf.stem)
        tei_path    = project_dir / "tei"      / f"{paper_id}.tei.xml"
        md_path     = project_dir / "md_clean" / f"{paper_id}.clean.md"
        chunks_path = project_dir / "chunks"   / f"{paper_id}.jsonl"
        log_path    = project_dir / "logs"     / f"{paper_id}.log"

        row: Dict = {
            "phase":          ph,
            "pdf_file":       pdf.name,
            "pdf_path":       str(pdf),
            "paper_id":       paper_id,
            "tei_path":       str(tei_path),
            "md_clean_path":  str(md_path),
            "chunks_path":    str(chunks_path),
            "status":         "",
            "error":          "",
            "seconds":        0.0,
            "n_chunks":       0,
            "tei_body_words": 0,
            "md_words":       0,
            "md_warning":     "",
        }

        # ── Skip si ya existe ─────────────────────────────────
        if (
            not args.force
            and not args.force_md
            and tei_path.exists()
            and md_path.exists()
            and chunks_path.exists()
        ):
            print(f"[{idx}/{len(pdf_list)}] SKIP (exists) → {pdf.name}")
            row["status"] = "skipped_exists"
            report_rows.append(row)
            continue

        # ── Dry-run ───────────────────────────────────────────
        if args.dry_run:
            print(f"[{idx}/{len(pdf_list)}] DRY-RUN → {pdf.name}  =>  {paper_id}")
            row["status"] = "dry_run"
            report_rows.append(row)
            continue

        # ── Procesar ──────────────────────────────────────────
        t0 = time.time()
        try:
            with log_path.open("w", encoding="utf-8") as lg:
                lg.write(f"PDF: {pdf}\npaper_id: {paper_id}\nphase: {ph}\nstarted: {time.ctime()}\n\n")

                # 1) PDF → TEI (o reutilizar si ya existe)
                reused_tei = False
                if args.force_md:
                    if not tei_path.exists():
                        raise FileNotFoundError(f"--force-md necesita TEI existente: {tei_path}")
                    tei_xml    = tei_path.read_text(encoding="utf-8")
                    reused_tei = True
                    lg.write(f"TEI reused for MD regeneration: {tei_path}\n")
                elif tei_path.exists() and not args.force:
                    tei_xml    = tei_path.read_text(encoding="utf-8")
                    reused_tei = True
                    lg.write(f"TEI reused: {tei_path}\n")
                else:
                    tei_xml = grobid_process_pdf(pdf, args.grobid)
                    tei_path.write_text(tei_xml, encoding="utf-8")
                    lg.write(f"TEI written: {tei_path}\n")

                # 2) TEI → md_clean
                paper_title, md_clean, tei_body_words, md_words = tei_to_md_clean(tei_xml)
                md_warning = ""
                if md_words < 1000:
                    md_warning = "WARNING_short"
                elif tei_body_words > 0 and md_words < tei_body_words * 0.20:
                    md_warning = "WARNING_ratio"
                md_path.write_text(md_clean, encoding="utf-8")
                row["tei_body_words"] = tei_body_words
                row["md_words"]       = md_words
                row["md_warning"]     = md_warning
                lg.write(f"MD clean written: {md_path}\ntitle: {paper_title}\n"
                         f"tei_body_words: {tei_body_words}  md_words: {md_words}  warning: {md_warning}\n")

                # 3) Tablas + 4) Chunking
                tables  = extract_tables_md(tei_xml)
                records = build_chunk_records(
                    md_clean,
                    tables,
                    phase=ph,
                    paper_id=paper_id,
                    paper_title=paper_title,
                    source_pdf=pdf,
                    source_tei=tei_path,
                    source_md_clean=md_path,
                    target_words=args.target_words,
                    overlap_words=args.overlap_words,
                )
                write_jsonl(chunks_path, records)
                lg.write(f"Chunks written: {chunks_path}\nn_chunks: {len(records)}\n")

            dt = time.time() - t0
            row["status"]   = "ok_from_tei" if reused_tei else "ok"
            row["seconds"]  = round(dt, 1)
            row["n_chunks"] = len(records)
            print(f"[{idx}/{len(pdf_list)}] OK  {paper_id}  "
                  f"({'TEI' if reused_tei else 'GROBID'}, {dt:.1f}s)  {len(records)} chunks")

        except Exception as e:
            dt = time.time() - t0
            try:
                with log_path.open("a", encoding="utf-8") as lg:
                    lg.write(f"\nERROR:\n{e}\n")
            except Exception:
                pass
            row["status"]  = "error"
            row["error"]   = str(e)
            row["seconds"] = round(dt, 1)
            print(f"[{idx}/{len(pdf_list)}] ERROR → {pdf.name}  ({e})")

        report_rows.append(row)
        if args.sleep > 0:
            time.sleep(args.sleep)

    # ── Informe ───────────────────────────────────────────────
    write_report(report_rows, project_dir)

    ok       = sum(1 for r in report_rows if r["status"].startswith("ok"))
    skipped  = sum(1 for r in report_rows if r["status"] == "skipped_exists")
    errors   = sum(1 for r in report_rows if r["status"] == "error")
    dry      = sum(1 for r in report_rows if r["status"] == "dry_run")
    chunks   = sum(r["n_chunks"] for r in report_rows)
    warnings = sum(1 for r in report_rows if r.get("md_warning"))

    print(f"\n{'=' * 60}")
    print(f"Phase    : {phase}")
    print(f"PDFs     : {len(pdf_list)}")
    print(f"OK       : {ok}")
    print(f"Skipped  : {skipped}")
    print(f"Errors   : {errors}")
    if dry:
        print(f"Dry-run  : {dry}")
    print(f"Chunks   : {chunks}")
    if warnings:
        print(f"Warnings : {warnings}  (MD corto o ratio bajo — revisar report)")
    print(f"{'=' * 60}")

    ok_rows = sorted(
        [r for r in report_rows if r["status"].startswith("ok") and r.get("md_words", 0) > 0],
        key=lambda r: r["md_words"],
    )
    if ok_rows:
        print("\n--- 5 MDs con menos palabras ---")
        for r in ok_rows[:5]:
            print(f"  {r['md_words']:6} palabras  {r['paper_id'][:70]}")


if __name__ == "__main__":
    main()
