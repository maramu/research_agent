#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
books/process.py — Procesado de libros de docencia (paralelo a 3_process_corpus.py).

Pipeline batch SIN GROBID (solo PDF de texto extraíble):
    libros_docencia/pdfs/ → md_clean/ + chunks/ + metadata/libros_metadata.jsonl
                            + metadata/papers_metadata.jsonl (derivado)

Diferencias con 3_process_corpus.py:
    - No hay TEI ni GROBID: el texto se extrae con PyMuPDF (fitz). PDFs
      escaneados (sin texto) NO se procesan: se marcan text_extractable=false y
      quedan como candidatos a OCR (item 35).
    - Segmentación estructural por el TOC del PDF (doc.get_toc()). Si el TOC viene
      vacío, fallback a detección de encabezados por tamaño de fuente y se marca
      toc_source="heuristic" (menor calidad).
    - section_canonical = "chapter" (valor CENTINELA; NO está en
      CANONICAL_SECTIONS a propósito: los libros no se filtran por IMRaD).
    - Cada chunk lleva doc_type="book", heading_path, page_start/page_end,
      chunk_hash y year DENORMALIZADO desde libros_metadata.jsonl (embed.py debe
      PRESERVARLO, no recalcularlo con year_from_paper_id).

Reutiliza de scripts/3_process_corpus.py (import por importlib, sin duplicar):
    chunk_text(), _split_to_max_chars(), norm_space(), safe_slug().

Esquema de chunk de libro (JSONL, una línea por chunk):
    phase, paper_id(=book_id), paper_title, doc_type("book"), type("text"),
    section (hoja del TOC), section_canonical("chapter"), heading_path,
    page_start, page_end, chunk_index, section_part, chunk_hash, year,
    source_pdf, source_md_clean, text

Esquema de libros_metadata.jsonl (nivel libro, una línea por libro):
    book_id, title, authors [{surname, forename, full}], publisher, year, isbn,
    n_pages, n_chapters, source_format, sha256, processed_date, quality_score,
    toc, toc_source, text_extractable, source_pdf

Idempotencia: se salta un libro cuyo sha256 no cambió y cuyos artefactos existen.
--force reprocesa.

Parámetros CLI:
    --collection NAME   Colección/proyecto (defecto: libros_docencia)
    --base DIR          Raíz NAS (defecto: /Volumes/research)
    --input-dir DIR     Carpeta alternativa de PDFs
    --force             Reprocesa aunque existan salidas y no cambie el sha256
    --dry-run           Lista sin procesar
    --limit N           Solo N PDFs
    --target-words N    Tamaño objetivo por chunk (~tokens; defecto 1000)
    --overlap-words N   Solape entre chunks (defecto 120)
    --min-chars-page N  Umbral de texto/página para considerar el PDF extraíble
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from utils.constants import MAX_EMBED_CHARS
except Exception:  # pragma: no cover - fallback defensivo
    MAX_EMBED_CHARS = 8000

DEFAULT_BASE = "/Volumes/research"
DEFAULT_COLLECTION = "libros_docencia"

# section_canonical centinela para chunks de libro (NO en CANONICAL_SECTIONS).
BOOK_SECTION_CANONICAL = "chapter"
BOOK_DOC_TYPE = "book"

DEFAULT_TARGET_WORDS = 1000
DEFAULT_OVERLAP_WORDS = 120
DEFAULT_MIN_CHARS_PAGE = 100

# Títulos de secciones de front/back matter que NO deben trocearse (ruido:
# índices con puntos guía, prefacios, etc.). Comparación sin mayúsculas ni acentos.
_FRONT_BACK_MATTER = (
    # Inglés
    "table of contents", "contents", "index", "indices", "preface", "foreword",
    "front matter", "acknowledgements", "acknowledgments", "acknowledgement",
    "list of figures", "list of tables", "prelims", "preliminaries",
    # Español (variantes evidentes)
    "indice", "indice general", "contenidos", "tabla de contenidos", "prefacio",
    "prologo", "agradecimientos", "preliminares",
)

# Secciones suplementarias que SÍ se conservan como contenido (se trocean) pero
# NO cuentan como capítulos en n_chapters (apéndices, anexos). Mismo criterio de
# comparación que _FRONT_BACK_MATTER (normalizado, por igualdad o prefijo).
_SUPPLEMENTARY_SECTIONS = (
    "appendix", "appendices", "apendice", "apendices", "anexo", "anexos",
)

_ISBN_RE = re.compile(
    r"ISBN(?:-1[03])?\s*:?\s*((?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx])",
    re.IGNORECASE,
)
_COPYRIGHT_YEAR_RE = re.compile(r"(?:©|\(c\)|copyright)\s*(\d{4})", re.IGNORECASE)
_PAGE_NUM_RE = re.compile(r"^\s*[-–—]?\s*(?:\d{1,4}|[ivxlcdmIVXLCDM]{1,7})\s*[-–—]?\s*$")


# ============================================================
# Reutilización de 3_process_corpus.py (nombre con dígito → importlib)
# ============================================================

def _load_process_corpus():
    """Carga scripts/3_process_corpus.py por ruta (su nombre empieza por dígito)."""
    mod_path = _SCRIPTS_DIR / "3_process_corpus.py"
    spec = importlib.util.spec_from_file_location("process_corpus_3", mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["process_corpus_3"] = mod
    spec.loader.exec_module(mod)
    return mod


_PC = _load_process_corpus()
chunk_text = _PC.chunk_text
_split_to_max_chars = _PC._split_to_max_chars
norm_space = _PC.norm_space
safe_slug = _PC.safe_slug


# ============================================================
# UTILIDADES
# ============================================================

def sha256_file(path: Path) -> str:
    """sha256 hex de un fichero (para idempotencia)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def chunk_hash(text: str) -> str:
    """sha1 del texto del chunk (estabilidad/dedup)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _norm_title(title: str) -> str:
    """Normaliza un título: sin acentos, minúsculas, espacios colapsados."""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


def normalize_toc_title(title: str) -> str:
    """Normaliza la etiqueta cruda de una entrada del TOC.

    Algunos libros se ensamblan a partir de PDFs sueltos y el TOC hereda los
    NOMBRES DE FICHERO como etiquetas ('Chapter 1.pdf', 'Prelims.pdf', …). Se
    limpia el espaciado y se retira un único sufijo '.pdf' (case-insensitive)
    para que heading_path/section y el chequeo de front/back matter operen sobre
    el título real, no sobre el nombre del fichero.
    """
    t = (title or "").strip()
    if t.lower().endswith(".pdf"):
        t = t[:-4].strip()
    return t


def _matches_section_group(title: str, group: Tuple[str, ...]) -> bool:
    """True si el título normalizado coincide (igualdad o prefijo de palabra) con
    alguna entrada del grupo. Evita falsos positivos como 'Indexation strategies'
    o 'Refractive index measurement'."""
    n = _norm_title(title)
    return any(n == p or n.startswith(p + " ") for p in group)


def is_front_back_matter(title: str) -> bool:
    """True si el título es front/back matter (índice, prefacio, prelims, etc.).

    No se trocean estas secciones (generan ruido: puntos guía del índice, etc.).
    Coincide por igualdad o por prefijo de palabra (evita falsos positivos como
    'Indexation strategies' o 'Refractive index measurement').
    """
    return _matches_section_group(title, _FRONT_BACK_MATTER)


def is_supplementary_section(title: str) -> bool:
    """True si el título es una sección suplementaria (apéndice/anexo): se
    CONSERVA como contenido pero no cuenta como capítulo en n_chapters."""
    return _matches_section_group(title, _SUPPLEMENTARY_SECTIONS)


def count_chapters(sections: List[Dict]) -> int:
    """Nº de capítulos reales: secciones que no son front/back matter ni
    suplementarias (apéndices). Excluye el 'Front matter' sintético."""
    return sum(
        1 for s in sections
        if not is_front_back_matter(s["title"]) and not is_supplementary_section(s["title"])
    )


def write_jsonl(path: Path, records: List[Dict]) -> None:
    """Escribe una lista de dicts como JSONL (crea el directorio padre)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _parse_authors(raw: str) -> List[Dict]:
    """Convierte el campo author del PDF en [{full, surname, forename}].

    Divide por ';' o '&'; el apellido es la última palabra, el resto el nombre.
    Tolerante: cadena vacía → []. Formato compatible con utils/citations.py.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s*[;&]\s*|\s+and\s+", raw)
    authors: List[Dict] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "," in p:  # "Apellido, Nombre"
            surname, _, forename = p.partition(",")
            surname, forename = surname.strip(), forename.strip()
            full = f"{forename} {surname}".strip()
        else:
            toks = p.split()
            surname = toks[-1]
            forename = " ".join(toks[:-1])
            full = p
        authors.append({"full": full, "surname": surname, "forename": forename})
    return authors


def parse_filename_meta(stem: str) -> Tuple[Optional[int], List[Dict], str]:
    """Deriva (year, authors, title) del nombre de archivo.

    Convención AÑO_Autor_Título (admite '-' o '_' tras el año, p.ej.
    '2007-Najafpour_Biochemical_Engineering_and_Biotechnology'):
      - año: 4 dígitos iniciales.
      - autor: primer token tras el año (apellido).
      - título: resto, con '_'/'-' → espacios.
    Tolerante: si no hay patrón claro, title = stem legible y authors = [].
    """
    s = stem.strip()
    year: Optional[int] = None
    m = re.match(r"^(\d{4})[-_\s]*(.*)$", s)
    if m:
        y = int(m.group(1))
        if 1900 <= y <= 2100:
            year = y
            s = m.group(2)
    authors: List[Dict] = []
    title = s
    # El autor solo es identificable si hubo año delante (patrón AÑO_Autor_Título);
    # sin año, todo el nombre se trata como título.
    if year is not None and "_" in s:
        surname, _, rest = s.partition("_")
        surname = surname.strip()
        if surname and rest.strip():
            authors = [{"full": surname, "surname": surname, "forename": ""}]
            title = rest
    title = re.sub(r"[_-]+", " ", title).strip()
    title = re.sub(r"\s+", " ", title)
    return year, authors, title


def _pdf_year(doc: "fitz.Document", first_pages_text: str) -> Optional[int]:
    """Año: metadatos (creationDate D:YYYY…) o '© YYYY' en las primeras páginas."""
    meta = doc.metadata or {}
    for key in ("creationDate", "modDate"):
        m = re.search(r"D:(\d{4})", meta.get(key, "") or "")
        if m:
            y = int(m.group(1))
            if 1900 <= y <= 2100:
                return y
    m = _COPYRIGHT_YEAR_RE.search(first_pages_text or "")
    if m:
        y = int(m.group(1))
        if 1900 <= y <= 2100:
            return y
    return None


def _pdf_isbn(first_pages_text: str) -> str:
    """ISBN de las primeras páginas (normalizado, solo dígitos/X). '' si no hay."""
    m = _ISBN_RE.search(first_pages_text or "")
    if not m:
        return ""
    raw = re.sub(r"[-\s]", "", m.group(1))
    return raw.upper()


# ============================================================
# EXTRACCIÓN DE TEXTO
# ============================================================

def extract_pdf_pages(doc: "fitz.Document") -> List[str]:
    """Texto por página (una entrada por página) con PyMuPDF."""
    return [page.get_text("text") for page in doc]


def is_text_pdf(pages: List[str], min_chars_per_page: int = DEFAULT_MIN_CHARS_PAGE) -> bool:
    """True si el PDF parece de texto (chars totales / páginas ≥ umbral). NO hace OCR."""
    if not pages:
        return False
    total = sum(len(p.strip()) for p in pages)
    return (total / max(1, len(pages))) >= min_chars_per_page


# ============================================================
# LIMPIEZA (headers/footers, guiones de fin de línea, párrafos)
# ============================================================

def _norm_running(line: str) -> str:
    """Normaliza una línea para detectar cabeceras/pies recurrentes (sin dígitos)."""
    s = re.sub(r"\d+", "", line.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_running_lines(pages: List[str], n_edge: int = 2) -> set:
    """Detecta cabeceras/pies recurrentes mirando las líneas de los BORDES.

    Toma las ``n_edge`` primeras y últimas líneas de cada página (donde viven
    headers/footers), las normaliza (sin dígitos, para unificar el número de
    página variable) y marca como recurrente cualquier línea que aparezca en
    borde en >= umbral páginas. El umbral es absoluto y bajo para capturar
    también cabeceras de CAPÍTULO, que solo salen en su tramo de páginas
    (p.ej. "CHAPTER 2 Dissolved Oxygen…") y nunca alcanzarían un umbral por %.
    """
    counts: Counter = Counter()
    n = len(pages)
    for p in pages:
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        if not lines:
            continue
        edge = lines[:n_edge] + lines[-n_edge:]
        for key in {_norm_running(ln) for ln in edge}:  # una vez por página
            if key:
                counts[key] += 1
    thresh = max(4, n // 100)
    return {k for k, c in counts.items() if c >= thresh and 3 <= len(k) <= 80}


def clean_page(page_text: str, running: set) -> str:
    """Limpia una página: une guiones de fin de línea, quita headers/footers y
    números de página sueltos, y re-fluye las líneas en párrafos."""
    # 1) Unir palabras cortadas por guion al final de línea: "diges-\ntion" → "digestion".
    text = re.sub(
        r"([A-Za-zÁÉÍÓÚÑÜáéíóúñü])-\n([a-záéíóúñü])",
        r"\1\2",
        page_text,
    )
    # 2) Descartar líneas de cabecera/pie recurrentes y números de página sueltos.
    kept: List[str] = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if not stripped:
            kept.append("")
            continue
        if _norm_running(stripped) in running:
            continue
        if _PAGE_NUM_RE.match(stripped):
            continue
        kept.append(stripped)
    # 3) Re-flujo: unir soft-wraps; salto de párrafo si la línea previa termina
    #    en puntuación de cierre o si hay línea en blanco.
    paras: List[str] = []
    cur = ""
    for ln in kept:
        if not ln:
            if cur:
                paras.append(cur)
                cur = ""
            continue
        if cur and not cur.rstrip().endswith((".", "!", "?", ":", ";", "…")):
            cur = f"{cur} {ln}"
        else:
            if cur:
                paras.append(cur)
            cur = ln
    if cur:
        paras.append(cur)
    return norm_space("\n\n".join(paras))


# ============================================================
# TOC / SEGMENTACIÓN EN CAPÍTULOS
# ============================================================

def get_toc_entries(doc: "fitz.Document") -> Tuple[List[List], str]:
    """Devuelve (entries, toc_source).

    entries: [[level, title, page_1based], …] en orden de documento.
    toc_source: "pdf" si viene de doc.get_toc(); "heuristic" si se detectó por
    tamaño de fuente; "none" si no se pudo derivar estructura.
    """
    toc = doc.get_toc(simple=True) or []
    entries = [
        [int(lvl), normalize_toc_title(title), int(pg)]
        for lvl, title, pg in toc
        if title and int(pg) >= 1
    ]
    # Descarta entradas que quedaron sin título tras normalizar (p.ej. ".pdf").
    entries = [e for e in entries if e[1]]
    if entries:
        return entries, "pdf"
    heur = detect_headings_by_font(doc)
    if heur:
        return heur, "heuristic"
    return [], "none"


def detect_headings_by_font(doc: "fitz.Document") -> List[List]:
    """Fallback: detecta encabezados por tamaño de fuente (menor calidad).

    El tamaño de fuente más frecuente (por nº de caracteres) es el cuerpo;
    los tamaños ≥ 1.25× el cuerpo se consideran encabezados y se agrupan en
    hasta 3 niveles. Devuelve [[level, title, page_1based], …].
    """
    sizes: Counter = Counter()
    for page in doc:
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").strip()
                    if txt:
                        sizes[round(span.get("size", 0), 1)] += len(txt)
    if not sizes:
        return []
    body = sizes.most_common(1)[0][0]
    head_sizes = sorted((sz for sz in sizes if sz >= body * 1.25), reverse=True)
    tiers = {sz: i + 1 for i, sz in enumerate(head_sizes[:3])}
    if not tiers:
        return []
    entries: List[List] = []
    for pno, page in enumerate(doc, start=1):
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                txt = " ".join(s.get("text", "") for s in spans).strip()
                if not txt or len(txt) > 120:
                    continue
                sz = round(max(s.get("size", 0) for s in spans), 1)
                if sz in tiers:
                    entries.append([tiers[sz], txt, pno])
    return entries


def segment_chapters(
    entries: List[List],
    cleaned_pages: List[str],
    book_title: str,
) -> List[Dict]:
    """Segmenta el libro en secciones a partir de las entradas del TOC.

    Cada sección: {title, heading_path, page_start, page_end, text} con páginas
    1-based inclusivas. heading_path se construye con la pila de ancestros por
    nivel. Si no hay entradas, el libro entero es una sola sección.

    Las entradas se ORDENAN por página (estable) antes de calcular los rangos:
    algunos PDFs traen bookmarks fuera de orden (p.ej. un capítulo intercalado al
    final de la lista) que, sin ordenar, corromperían los rangos y duplicarían
    texto (una entrada rezagada acapararía hasta el final del libro).

    Nota: dos entradas del TOC en la misma página comparten el texto de esa
    página (no hay offsets intra-página).
    """
    n_pages = len(cleaned_pages)
    # Orden estable por página: preserva el orden original entre páginas iguales
    # (mantiene padre antes que hijo para el heading_path).
    entries = sorted(entries, key=lambda e: e[2])

    def page_text(ps: int, pe: int) -> str:
        ps = max(1, ps)
        pe = min(n_pages, pe)
        return norm_space("\n\n".join(cleaned_pages[ps - 1:pe]))

    if not entries:
        return [{
            "title": book_title,
            "heading_path": book_title,
            "page_start": 1,
            "page_end": n_pages,
            "text": page_text(1, n_pages),
        }]

    sections: List[Dict] = []

    # Front matter: páginas antes de la primera entrada del TOC.
    first_page = entries[0][2]
    if first_page > 1:
        txt = page_text(1, first_page - 1)
        if txt:
            sections.append({
                "title": "Front matter",
                "heading_path": "Front matter",
                "page_start": 1,
                "page_end": first_page - 1,
                "text": txt,
            })

    stack: List[Tuple[int, str]] = []
    for i, (level, title, page) in enumerate(entries):
        while stack and stack[-1][0] >= level:
            stack.pop()
        heading_path = " > ".join([t for _, t in stack] + [title])
        stack.append((level, title))

        page_start = page
        page_end = (entries[i + 1][2] - 1) if i + 1 < len(entries) else n_pages
        if page_end < page_start:
            page_end = page_start

        txt = page_text(page_start, page_end)
        if not txt:
            continue
        sections.append({
            "title": title,
            "heading_path": heading_path,
            "page_start": page_start,
            "page_end": page_end,
            "text": txt,
        })
    return sections


# ============================================================
# CHUNKING
# ============================================================

def build_book_chunk_records(
    sections: List[Dict],
    *,
    collection: str,
    book_id: str,
    book_title: str,
    year: Optional[int],
    source_pdf: Path,
    source_md_clean: Path,
    target_words: int,
    overlap_words: int,
) -> List[Dict]:
    """Trocea las secciones en chunks de libro con el esquema documentado.

    Reutiliza chunk_text()/_split_to_max_chars() de 3_process_corpus. El ``year``
    se denormaliza aquí (viene de libros_metadata.jsonl) y se escribe en cada
    chunk para que embed.py NO lo pierda.

    Las secciones de front/back matter (índice, prefacio, etc.) se SALTAN: no se
    trocean ni se escriben en chunks/.
    """
    records: List[Dict] = []
    chunk_index = 1
    for sec in sections:
        if is_front_back_matter(sec["title"]):
            continue
        for ch in chunk_text(sec["text"], target_words, overlap_words):
            for part_i, piece in enumerate(_split_to_max_chars(ch, MAX_EMBED_CHARS), start=1):
                records.append({
                    "phase":             collection,
                    "paper_id":          book_id,
                    "paper_title":       book_title,
                    "doc_type":          BOOK_DOC_TYPE,
                    "type":              "text",
                    "section":           sec["title"],
                    "section_canonical": BOOK_SECTION_CANONICAL,
                    "heading_path":      sec["heading_path"],
                    "page_start":        sec["page_start"],
                    "page_end":          sec["page_end"],
                    "chunk_index":       chunk_index,
                    "section_part":      part_i,
                    "chunk_hash":        chunk_hash(piece),
                    "year":              year,
                    "source_pdf":        str(source_pdf),
                    "source_md_clean":   str(source_md_clean),
                    "text":              piece,
                })
                chunk_index += 1
    return records


# ============================================================
# METADATA
# ============================================================

def load_books_metadata(collection_dir: Path) -> Dict[str, dict]:
    """Lee metadata/libros_metadata.jsonl → {book_id: record}. {} si no existe."""
    path = collection_dir / "metadata" / "libros_metadata.jsonl"
    if not path.exists():
        return {}
    out: Dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            bid = rec.get("book_id")
            if bid:
                out[bid] = rec
    return out


def save_books_metadata(collection_dir: Path, books_meta: Dict[str, dict]) -> Path:
    """Reescribe metadata/libros_metadata.jsonl con todos los libros (ordenados)."""
    path = collection_dir / "metadata" / "libros_metadata.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for bid in sorted(books_meta):
            f.write(json.dumps(books_meta[bid], ensure_ascii=False) + "\n")
    return path


def derive_papers_metadata(
    books_meta: Dict[str, dict],
    collection_dir: Path,
) -> Path:
    """Deriva metadata/papers_metadata.jsonl desde libros_metadata.jsonl.

    Subset con las claves que esperan 5_build_embeddings.py (year) y
    utils/citations.py (paper_id, authors, year, doi). paper_id = book_id.
    Solo libros con text_extractable=True. Blinda el riesgo 3 (year/citas).
    """
    path = collection_dir / "metadata" / "papers_metadata.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for bid in sorted(books_meta):
            rec = books_meta[bid]
            if not rec.get("text_extractable"):
                continue
            f.write(json.dumps({
                "paper_id": bid,
                "doi":      "",
                "year":     rec.get("year"),
                "authors":  rec.get("authors", []),
                "title":    rec.get("title", ""),
                "isbn":     rec.get("isbn", ""),
            }, ensure_ascii=False) + "\n")
    return path


def build_book_metadata(
    doc: "fitz.Document",
    *,
    book_id: str,
    pdf_path: Path,
    sha256: str,
    n_pages: int,
    n_chapters: int,
    toc: List[List],
    toc_source: str,
    text_extractable: bool,
    first_pages_text: str,
) -> Dict:
    """Construye el registro de libros_metadata.jsonl para un libro.

    Los metadatos internos del PDF suelen ser poco fiables (title vacío,
    producer='Acrobat Distiller', author=''). Cuando faltan, se derivan del
    nombre de archivo (convención AÑO_Autor_Título). El resultado queda
    CURABLE a mano en libros_metadata.jsonl.
    """
    meta = doc.metadata or {}
    fn_year, fn_authors, fn_title = parse_filename_meta(pdf_path.stem)

    pdf_title = (meta.get("title") or "").strip()
    title = pdf_title if len(pdf_title) > 3 else (fn_title or book_id)

    authors = _parse_authors(meta.get("author", "")) or fn_authors
    year = None
    if text_extractable:
        year = _pdf_year(doc, first_pages_text) or fn_year
    isbn = _pdf_isbn(first_pages_text) if text_extractable else ""

    quality = 1.0
    if not text_extractable:
        quality = 0.0
    else:
        if toc_source == "heuristic":
            quality -= 0.3
        elif toc_source == "none":
            quality -= 0.5
        avg_chars = len(first_pages_text) / max(1, min(n_pages, 5))
        if avg_chars < 400:
            quality -= 0.2
    quality = round(max(0.0, min(1.0, quality)), 2)

    return {
        "book_id":          book_id,
        "title":            title,
        "authors":          authors,
        # publisher NO se toma del PDF (producer suele ser el creador, p.ej.
        # 'Acrobat Distiller'). Se deja vacío para curación manual.
        "publisher":        "",
        "year":             year,
        "isbn":             isbn,
        "n_pages":          n_pages,
        "n_chapters":       n_chapters,
        "source_format":    (meta.get("format") or "PDF").strip(),
        "sha256":           sha256,
        "processed_date":   datetime.now().isoformat(timespec="seconds"),
        "quality_score":    quality,
        "toc":              toc,
        "toc_source":       toc_source,
        "text_extractable": text_extractable,
        "source_pdf":       str(pdf_path),
    }


def build_md_clean(book_title: str, sections: List[Dict]) -> str:
    """Reconstruye el Markdown limpio del libro a partir de las secciones."""
    parts: List[str] = [f"# {book_title}\n"]
    for sec in sections:
        depth = sec["heading_path"].count(" > ") + 2  # nivel ≥ 2 bajo el título
        hashes = "#" * min(depth, 6)
        parts.append(f"{hashes} {sec['title']}\n")
        parts.append(sec["text"] + "\n")
    return norm_space("\n".join(parts)) + "\n"


# ============================================================
# PROCESADO DE UN LIBRO
# ============================================================

def process_book(
    pdf_path: Path,
    collection_dir: Path,
    collection: str,
    *,
    target_words: int,
    overlap_words: int,
    min_chars_page: int,
    existing_meta: Dict[str, dict],
    force: bool,
) -> Dict:
    """Procesa un PDF de libro. Devuelve una fila de informe (dict)."""
    book_id = safe_slug(pdf_path.stem)
    md_path = collection_dir / "md_clean" / f"{book_id}.md"
    chunks_path = collection_dir / "chunks" / f"{book_id}.jsonl"
    sha = sha256_file(pdf_path)

    row = {
        "book_id": book_id, "pdf_file": pdf_path.name, "status": "",
        "n_pages": 0, "n_chunks": 0, "skipped_sections": 0, "toc_source": "",
        "text_extractable": "", "quality_score": "", "seconds": 0.0, "error": "",
    }

    # Idempotencia por sha256.
    prev = existing_meta.get(book_id)
    if (not force and prev and prev.get("sha256") == sha
            and prev.get("text_extractable")
            and md_path.exists() and chunks_path.exists()):
        row["status"] = "skipped_unchanged"
        row["n_pages"] = prev.get("n_pages", 0)
        row["toc_source"] = prev.get("toc_source", "")
        row["text_extractable"] = True
        row["quality_score"] = prev.get("quality_score", "")
        return row

    t0 = time.time()
    try:
        with fitz.open(pdf_path) as doc:
            n_pages = doc.page_count
            raw_pages = extract_pdf_pages(doc)
            first_pages_text = "\n".join(raw_pages[:5])

            if not is_text_pdf(raw_pages, min_chars_page):
                # PDF sin texto → candidato a OCR (item 35). No se procesa.
                meta = build_book_metadata(
                    doc, book_id=book_id, pdf_path=pdf_path, sha256=sha,
                    n_pages=n_pages, n_chapters=0, toc=[], toc_source="none",
                    text_extractable=False, first_pages_text=first_pages_text,
                )
                existing_meta[book_id] = meta
                row.update(status="ocr_candidate", n_pages=n_pages,
                           toc_source="none", text_extractable=False,
                           quality_score=0.0, seconds=round(time.time() - t0, 1))
                return row

            running = detect_running_lines(raw_pages)
            cleaned_pages = [clean_page(p, running) for p in raw_pages]

            entries, toc_source = get_toc_entries(doc)
            sections = segment_chapters(entries, cleaned_pages, book_id)

            skipped = [s["title"] for s in sections if is_front_back_matter(s["title"])]
            if skipped:
                print(f"    ↳ {len(skipped)} sección(es) front/back matter saltada(s): "
                      f"{', '.join(skipped[:6])}{' …' if len(skipped) > 6 else ''}")

            meta = build_book_metadata(
                doc, book_id=book_id, pdf_path=pdf_path, sha256=sha,
                n_pages=n_pages, n_chapters=count_chapters(sections), toc=entries,
                toc_source=toc_source, text_extractable=True,
                first_pages_text=first_pages_text,
            )
            book_title = meta["title"]
            year = meta["year"]

            md_clean = build_md_clean(book_title, sections)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md_clean, encoding="utf-8")

            records = build_book_chunk_records(
                sections, collection=collection, book_id=book_id,
                book_title=book_title, year=year, source_pdf=pdf_path,
                source_md_clean=md_path, target_words=target_words,
                overlap_words=overlap_words,
            )
            write_jsonl(chunks_path, records)

        existing_meta[book_id] = meta
        row.update(status="ok", n_pages=n_pages, n_chunks=len(records),
                   skipped_sections=len(skipped),
                   toc_source=toc_source, text_extractable=True,
                   quality_score=meta["quality_score"],
                   seconds=round(time.time() - t0, 1))
    except Exception as e:  # noqa: BLE001
        row.update(status="error", error=str(e), seconds=round(time.time() - t0, 1))
    return row


# ============================================================
# INFORME
# ============================================================

def write_report(rows: List[Dict], collection_dir: Path) -> None:
    """Vuelca el informe de procesado a logs/books_process_report.csv."""
    import csv
    logs_dir = collection_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = ["book_id", "pdf_file", "status", "n_pages", "n_chunks",
                  "skipped_sections", "toc_source", "text_extractable",
                  "quality_score", "seconds", "error"]
    with (logs_dir / "books_process_report.csv").open(
            "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Procesa libros de docencia (PDF de texto) → md_clean + chunks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--collection", default=DEFAULT_COLLECTION,
                    help=f"Colección/proyecto (defecto: {DEFAULT_COLLECTION})")
    ap.add_argument("--base", default=DEFAULT_BASE,
                    help=f"Raíz NAS (defecto: {DEFAULT_BASE})")
    ap.add_argument("--input-dir", default="",
                    help="Carpeta de PDFs; si no se indica, usa <base>/<collection>/pdfs/")
    ap.add_argument("--force", action="store_true",
                    help="Reprocesa aunque el sha256 no cambie y existan salidas")
    ap.add_argument("--dry-run", action="store_true", help="Lista sin procesar")
    ap.add_argument("--limit", type=int, default=0, help="Procesar solo N PDFs")
    ap.add_argument("--target-words", type=int, default=DEFAULT_TARGET_WORDS,
                    help=f"Tamaño objetivo por chunk (~tokens; defecto {DEFAULT_TARGET_WORDS})")
    ap.add_argument("--overlap-words", type=int, default=DEFAULT_OVERLAP_WORDS,
                    help=f"Solape entre chunks (defecto {DEFAULT_OVERLAP_WORDS})")
    ap.add_argument("--min-chars-page", type=int, default=DEFAULT_MIN_CHARS_PAGE,
                    help="Umbral texto/página para considerar el PDF extraíble")
    args = ap.parse_args()

    collection_dir = Path(args.base) / args.collection
    input_dir = Path(args.input_dir) if args.input_dir else collection_dir / "pdfs"
    for sub in ("md_clean", "chunks", "metadata", "logs"):
        (collection_dir / sub).mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        raise SystemExit(f"No existe la carpeta de PDFs: {input_dir}")
    pdfs = sorted(input_dir.glob("*.pdf"))
    if args.limit and args.limit > 0:
        pdfs = pdfs[:args.limit]
    if not pdfs:
        raise SystemExit(f"No se encontraron PDFs en: {input_dir}")

    print(f"Collection : {args.collection}")
    print(f"Base       : {args.base}")
    print(f"Input      : {input_dir}")
    print(f"PDFs       : {len(pdfs)}")
    print(f"Force      : {args.force}")
    print("")

    existing_meta = load_books_metadata(collection_dir)
    rows: List[Dict] = []

    for idx, pdf in enumerate(pdfs, start=1):
        if args.dry_run:
            print(f"[{idx}/{len(pdfs)}] DRY-RUN → {pdf.name}  ⇒  {safe_slug(pdf.stem)}")
            rows.append({"book_id": safe_slug(pdf.stem), "pdf_file": pdf.name,
                         "status": "dry_run"})
            continue
        row = process_book(
            pdf, collection_dir, args.collection,
            target_words=args.target_words, overlap_words=args.overlap_words,
            min_chars_page=args.min_chars_page,
            existing_meta=existing_meta, force=args.force,
        )
        rows.append(row)
        icon = {"ok": "✓", "skipped_unchanged": "•", "ocr_candidate": "⚠",
                "error": "✗"}.get(row["status"], "?")
        detail = row.get("error") or (
            f"{row.get('n_chunks', 0)} chunks, {row.get('n_pages', 0)} pág, "
            f"{row.get('skipped_sections', 0)} secc. saltadas, "
            f"toc={row.get('toc_source')}, q={row.get('quality_score')}"
        )
        print(f"[{idx}/{len(pdfs)}] {icon} {row['status']:18} {row['book_id'][:60]}  {detail}")

    if not args.dry_run:
        save_books_metadata(collection_dir, existing_meta)
        derive_papers_metadata(existing_meta, collection_dir)
        write_report(rows, collection_dir)

    ok = sum(1 for r in rows if r["status"] == "ok")
    skip = sum(1 for r in rows if r["status"] == "skipped_unchanged")
    ocr = sum(1 for r in rows if r["status"] == "ocr_candidate")
    err = sum(1 for r in rows if r["status"] == "error")
    chunks = sum(r.get("n_chunks", 0) for r in rows)
    print(f"\n{'=' * 60}")
    print(f"OK: {ok}  Skipped: {skip}  OCR-candidatos: {ocr}  Errores: {err}  Chunks: {chunks}")
    if ocr:
        print("Candidatos a OCR (item 35):")
        for r in rows:
            if r["status"] == "ocr_candidate":
                print(f"  ⚠ {r['pdf_file']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
