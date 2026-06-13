#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
4_extract_metadata.py — Paso 4 del pipeline research_agent

Extrae metadatos estructurados de los ficheros TEI XML generados por GROBID
y escribe los resultados en formato JSONL por proyecto y por paper.

Posición en el pipeline:
    categorias/<project>/tei/ → 4_extract_metadata.py → metadata/

Campos extraídos del TEI:
    title, doi, journal, year, authors (lista), abstract,
    highlights, n_references, phase

Campos de procedencia añadidos (item 14):
    stable_id        ← slug del DOI si existe, paper_id original si no
    processed_date   ← fecha de procesado (YYYY-MM-DD)
    source_type      ← scopus | inbox | adhoc | manual (auto-detectado o --source-type)
    download_source  ← método de descarga desde descarga_cache.json
    download_url     ← URL del PDF descargado
    access_type      ← open_access | institutional | unknown
    download_date    ← fecha de descarga del PDF

Campos de calidad añadidos (item 17):
    quality_score    ← float 0–1 (7 criterios: título, DOI, abstract, año,
                       autores, ≥5 refs, md_clean no corto)
    warnings         ← lista de strings: missing_doi, no_abstract, etc.

Skip logic:
    Si <paper_id>.metadata.json ya existe y --force no está activo, el paper
    se salta. Permite reanudar sin reprocesar lo ya completado.

Ficheros leídos:
    /Volumes/research/categorias/<project>/tei/**/*.tei.xml
    /Volumes/research/metadatos/descarga_cache.json      ← procedencia de descargas
    config/.env

Ficheros escritos:
    /Volumes/research/categorias/<project>/metadata/
        papers_metadata.jsonl                 ← todos los papers en un JSONL
        references.jsonl                      ← todas las referencias en un JSONL
        per_paper/<paper_id>.metadata.json    ← metadatos por paper
        per_paper/<paper_id>.references.json  ← referencias por paper

Parámetros CLI:
    --project PROJECT     Nombre del proyecto/categoría (obligatorio)
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)
    --force               Reprocesa aunque los metadatos ya existan
    --source-type TYPE    Fuerza el campo source_type (scopus|inbox|adhoc|manual)

Variables de entorno (config/.env):
    OLLAMA_HOST           URL del servidor Ollama (defecto: http://pciq22.uca.es:11434)
    GROBID_URL            URL del servidor GROBID  (defecto: http://pciq22.uca.es:8070)

Dependencias:
    xml.etree.ElementTree (stdlib), python-dotenv

Notas:
    - Papers procesados antes del item 16 carecen de stable_id; rellenar con
      6_Mantenimiento → Backfill metadata.
    - Papers procesados antes del item 17 carecen de quality_score; rellenar
      con 6_Mantenimiento → Backfill metadata.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import time
from urllib.parse import quote

import requests
from utils.pdf_utils import normalize_stem as _norm
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

# ── Cargar config/.env ────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

DEFAULT_BASE = "/Volumes/research/categorias"

_CACHE_PATH = Path("/Volumes/research/metadatos/descarga_cache.json")
_DOI_MANUAL_PATH = Path("/Volumes/research/metadatos/doi_manual.xlsx")
_METHOD_TO_SOURCE: Dict[str, tuple] = {
    "semantic_scholar":  ("semantic_scholar",  "open_access"),
    "unpaywall":         ("unpaywall",          "open_access"),
    "elsevier_api":      ("elsevier_api",       "institutional"),
    "elsevier_specific": ("elsevier_scraping",  "institutional"),
    "wiley_specific":    ("wiley_scraping",     "institutional"),
    "mdpi_specific":     ("mdpi_scraping",      "open_access"),
    "landing_page_pdf":  ("publisher_scraping", "unknown"),
    "doi_accept_pdf":    ("doi_direct",         "open_access"),
}

# Campos que, si ya estaban rellenos en papers_metadata.jsonl previo, no deben
# sobrescribirse con un valor vacío/ausente del TEI. Esto protege correcciones
# manuales hechas desde el editor de Artículos; si se quiere forzar el refresco
# desde el TEI, basta con vaciar el campo antes de re-extraer.
PRESERVE_FIELDS = ("title", "doi", "journal", "year", "authors")


def _is_filled(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True  # números u otros


def sha1_short(s: str, n: int = 10) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:n]


def norm_ws(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s


def find_first_text(el: ET.Element, xpath_list: List[str], ns: Dict) -> Optional[str]:
    for xp in xpath_list:
        node = el.find(xp, ns)
        if node is not None:
            txt = norm_ws("".join(node.itertext()))
            if txt:
                return txt
    return None


def find_all_texts(el: ET.Element, xpath: str, ns: Dict) -> List[str]:
    out = []
    for node in el.findall(xpath, ns):
        txt = norm_ws("".join(node.itertext()))
        if txt:
            out.append(txt)
    return out


def parse_year(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"\b(19|20)\d{2}\b", s)
    if m:
        try:
            return int(m.group(0))
        except Exception:
            return None
    return None


def extract_authors(root: ET.Element, ns: Dict) -> List[Dict]:
    authors = []
    for a in root.findall(".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author", ns):
        pers = a.find(".//tei:persName", ns)
        if pers is not None:
            forename = norm_ws("".join((pers.findtext(".//tei:forename", default="", namespaces=ns) or "").split()))
            surname  = norm_ws("".join((pers.findtext(".//tei:surname",  default="", namespaces=ns) or "").split()))
            full = norm_ws(" ".join([forename, surname]).strip())
        else:
            full = norm_ws("".join(a.itertext()))
            forename, surname = "", ""
        if full:
            authors.append({"full": full, "forename": forename, "surname": surname})
    if not authors:
        for pers in root.findall(".//tei:teiHeader//tei:persName", ns):
            txt = norm_ws("".join(pers.itertext()))
            if txt:
                authors.append({"full": txt, "forename": "", "surname": ""})
    seen, dedup = set(), []
    for a in authors:
        k = a.get("full", "")
        if k and k not in seen:
            seen.add(k)
            dedup.append(a)
    return dedup


def extract_doi(root: ET.Element, ns: Dict) -> Optional[str]:
    for idno in root.findall(".//tei:teiHeader//tei:idno", ns):
        t = (idno.attrib.get("type") or "").lower()
        v = norm_ws("".join(idno.itertext()))
        if not v:
            continue
        if t == "doi":
            return v.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        if re.search(r"\b10\.\d{4,9}/\S+\b", v):
            m = re.search(r"\b10\.\d{4,9}/\S+\b", v)
            if m:
                return m.group(0).rstrip(").,;")
    return None


def extract_title(root: ET.Element, ns: Dict) -> Optional[str]:
    return find_first_text(root, [
        ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title",
        ".//tei:teiHeader//tei:titleStmt/tei:title",
        ".//tei:text//tei:head",
    ], ns)


def extract_journal(root: ET.Element, ns: Dict) -> Optional[str]:
    # Preferir el título de revista del monogr (level="j"); con fallback al
    # primer monogr/title si GROBID no anotó el nivel.
    return find_first_text(root, [
        ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:monogr/tei:title[@level='j']",
        ".//tei:teiHeader//tei:sourceDesc//tei:monogr/tei:title[@level='j']",
        ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:monogr/tei:title",
        ".//tei:teiHeader//tei:sourceDesc//tei:monogr/tei:title",
    ], ns)


def extract_year(root: ET.Element, ns: Dict) -> Optional[int]:
    date_node = root.find(".//tei:teiHeader//tei:sourceDesc//tei:monogr//tei:imprint//tei:date", ns)
    if date_node is not None:
        date_when = date_node.attrib.get("when")
        if date_when:
            y = parse_year(date_when)
            if y:
                return y
        y = parse_year(norm_ws("".join(date_node.itertext())))
        if y:
            return y
    headers = root.findall(".//tei:teiHeader", ns)
    if headers:
        return parse_year(norm_ws("".join(headers[0].itertext())))
    return None


def extract_abstract(root: ET.Element, ns: Dict) -> Optional[str]:
    abs_text = find_first_text(root, [
        ".//tei:teiHeader/tei:profileDesc/tei:abstract",
        ".//tei:teiHeader//tei:abstract",
        ".//tei:text//tei:front//tei:abstract",
    ], ns)
    if abs_text:
        return abs_text
    front = root.find(".//tei:text//tei:front", ns)
    if front is None:
        return None
    for div in front.findall(".//tei:div", ns):
        head = div.find("./tei:head", ns)
        if head is not None and re.search(r"\babstract\b", norm_ws("".join(head.itertext())).lower()):
            ps = find_all_texts(div, ".//tei:p", ns)
            if ps:
                return norm_ws(" ".join(ps))
            items = find_all_texts(div, ".//tei:item", ns)
            if items:
                return norm_ws(" ".join(items))
    return None


def extract_highlights(root: ET.Element, ns: Dict) -> List[str]:
    hl = []
    front = root.find(".//tei:text//tei:front", ns)
    if front is not None:
        for div in front.findall(".//tei:div", ns):
            t = (div.attrib.get("type") or "").lower()
            if t == "highlights":
                items = find_all_texts(div, ".//tei:item", ns)
                if items:
                    hl.extend(items)
                else:
                    hl.extend(find_all_texts(div, ".//tei:p", ns))
        for note in front.findall(".//tei:note", ns):
            t = (note.attrib.get("type") or "").lower()
            if t == "highlights":
                txt = norm_ws("".join(note.itertext()))
                if txt:
                    hl.extend([norm_ws(x) for x in re.split(r"[•\n\r]+", txt) if norm_ws(x)])
        for div in front.findall(".//tei:div", ns):
            head = div.find("./tei:head", ns)
            if head is None:
                continue
            if "highlight" in norm_ws("".join(head.itertext())).lower():
                for c in find_all_texts(div, ".//tei:item", ns) + find_all_texts(div, ".//tei:p", ns):
                    if 10 <= len(c) <= 240:
                        hl.append(c)
    out, seen = [], set()
    for x in hl:
        x = norm_ws(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out[:12]


def extract_references(root: ET.Element, ns: Dict) -> List[Dict]:
    refs = []
    for b in root.findall(".//tei:text//tei:back//tei:listBibl//tei:biblStruct", ns):
        raw = norm_ws("".join(b.itertext()))
        if not raw:
            continue
        doi = None
        for idno in b.findall(".//tei:idno", ns):
            t = (idno.attrib.get("type") or "").lower()
            v = norm_ws("".join(idno.itertext()))
            if not v:
                continue
            if t == "doi":
                doi = v.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
                break
            if re.search(r"\b10\.\d{4,9}/\S+\b", v):
                m = re.search(r"\b10\.\d{4,9}/\S+\b", v)
                if m:
                    doi = m.group(0).rstrip(").,;")
                    break
        ref_title = find_first_text(b, [".//tei:analytic/tei:title", ".//tei:monogr/tei:title"], ns)
        ref_container = None
        if b.find(".//tei:analytic/tei:title", ns) is not None:
            ref_container = find_first_text(b, [".//tei:monogr/tei:title"], ns)
        ref_year = None
        d = b.find(".//tei:imprint/tei:date", ns)
        if d is not None:
            y = parse_year(d.attrib.get("when") or "")
            if not y:
                y = parse_year(norm_ws("".join(d.itertext())))
            ref_year = y
        ref_authors = []
        for au in b.findall(".//tei:analytic//tei:author", ns) or b.findall(".//tei:monogr//tei:author", ns):
            txt = norm_ws("".join(au.itertext()))
            if txt:
                ref_authors.append(txt)
        ref_authors_d, seen = [], set()
        for a in ref_authors:
            if a not in seen:
                seen.add(a)
                ref_authors_d.append(a)
        ref_key = sha1_short(
            f"{(ref_authors_d[0] if ref_authors_d else '')}|{ref_year or ''}|{ref_title or ''}|{doi or ''}|{raw[:80]}", 12
        )
        refs.append({
            "ref_key":   ref_key,
            "doi":       doi,
            "title":     ref_title,
            "container": ref_container,
            "year":      ref_year,
            "authors":   ref_authors_d,
            "raw":       raw,
        })
    return refs


def phase_from_path(p: Path) -> str:
    parts = p.parts
    for i, part in enumerate(parts):
        if part == "tei" and i + 1 < len(parts) - 1:
            return parts[i + 1]
    return "unknown"


def infer_paper_id(p: Path) -> str:
    name = p.name
    name = re.sub(r"\.tei\.xml$", "", name)
    name = re.sub(r"\.xml$", "", name)
    return name


def _tei_stem(name: str) -> str:
    """Stem de un fichero TEI sin sufijos .grobid.tei.xml / .tei.xml / .xml."""
    for suf in (".grobid.tei.xml", ".tei.xml", ".xml"):
        if name.lower().endswith(suf):
            return name[: -len(suf)]
    return name


def _doi_slug(doi: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")


def _load_prov_cache(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _norm_doi(doi: str) -> str:
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        doi = doi.replace(prefix, "")
    return doi.rstrip("/")


def _clean_doi(doi: str) -> str:
    """Limpia un DOI (quita prefijos URL) sin alterar el caso del sufijo."""
    doi = str(doi).strip()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi.strip().rstrip("/")


_CROSSREF_MAILTO = os.getenv("UNPAYWALL_EMAIL", "")
_crossref_journal_cache: Dict[str, str] = {}


def _crossref_journal(doi: str) -> str:
    """Revista (container-title) desde Crossref por DOI. '' si no hay/falla. Cacheado en memoria."""
    doi = (doi or "").strip().rstrip("/")
    if not doi:
        return ""
    if doi in _crossref_journal_cache:
        return _crossref_journal_cache[doi]
    journal = ""
    try:
        params = {"mailto": _CROSSREF_MAILTO} if _CROSSREF_MAILTO else {}
        r = requests.get(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            params=params, timeout=15,
        )
        if r.status_code == 200:
            ct = r.json().get("message", {}).get("container-title") or []
            if ct:
                journal = (ct[0] or "").strip()
    except Exception:
        journal = ""
    _crossref_journal_cache[doi] = journal
    time.sleep(0.1)   # cortesía con Crossref
    return journal


def normalize_title(s: str) -> str:
    """Normaliza un título para comparación laxa (minúsculas, alfanumérico)."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _strip_pdf(name: str) -> str:
    """Clave de doi_manual: stem del PDF en minúsculas, sin extensión .pdf."""
    n = str(name).strip()
    if n.lower().endswith(".pdf"):
        n = n[:-4]
    return n.strip().lower()


def _load_doi_manual(path: Path) -> tuple:
    """Carga doi_manual.xlsx como mapas de fallback de DOI.

    Devuelve (by_name, by_title): {stem_pdf: doi} y {titulo_normalizado: doi}.
    Lee todas las hojas; busca columnas nombre_archivo/filename, doi y
    (opcional) titulo/title. Degrada a mapas vacíos si openpyxl no está o el
    fichero no existe/es ilegible.
    """
    by_name: Dict[str, str] = {}
    by_title: Dict[str, str] = {}
    if not path.exists():
        return by_name, by_title
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return by_name, by_title
    try:
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            header = next(it, None)
            if not header:
                continue
            hl = [str(h).strip().lower() if h is not None else "" for h in header]
            name_idx = next((i for i, h in enumerate(hl)
                             if h in ("nombre_archivo", "filename")), None)
            doi_idx = next((i for i, h in enumerate(hl) if h == "doi"), None)
            title_idx = next((i for i, h in enumerate(hl)
                              if h in ("titulo", "title", "título")), None)
            if name_idx is None or doi_idx is None:
                continue
            for row in it:
                if row is None or len(row) <= doi_idx:
                    continue
                doi_raw = row[doi_idx]
                doi_s = _clean_doi(doi_raw) if doi_raw else ""
                if not doi_s:
                    continue
                if name_idx < len(row) and row[name_idx]:
                    by_name[_strip_pdf(str(row[name_idx]))] = doi_s
                if (title_idx is not None and title_idx < len(row)
                        and row[title_idx]):
                    by_title[normalize_title(str(row[title_idx]))] = doi_s
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return by_name, by_title


def _load_prev_meta(path: Path) -> Dict[str, dict]:
    """Lee papers_metadata.jsonl previo en {paper_id: registro} (si existe)."""
    prev: Dict[str, dict] = {}
    if not path.exists():
        return prev
    try:
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                s = line.strip()
                if not s:
                    continue
                try:
                    d = json.loads(s)
                except Exception:
                    continue
                pid = d.get("paper_id") or d.get("stable_id")
                if pid:
                    prev[pid] = d
    except Exception:
        return {}
    return prev


def _infer_provenance(doi: Optional[str], project: str, cache: dict, source_type: str = "") -> dict:
    base = {
        "source_type":     source_type or "manual",
        "download_source": "unknown",
        "download_url":    None,
        "access_type":     "unknown",
        "download_date":   None,
    }
    if not source_type:
        if project.startswith("adhoc"):
            base["source_type"] = "adhoc"
    if not doi:
        return base
    entry = cache.get(_norm_doi(doi)) or {}
    if not entry:
        return base
    method = entry.get("method", "")
    dl_src, acc = _METHOD_TO_SOURCE.get(method, ("unknown", "unknown"))
    cached_at = entry.get("cached_at", "")
    return {
        "source_type":     source_type or "scopus_or_inbox",
        "download_source": dl_src,
        "download_url":    entry.get("pdf_url") or None,
        "access_type":     acc,
        "download_date":   cached_at[:10] if cached_at else None,
    }


def compute_quality(
    title, doi, year, authors, abstract, refs: list,
    md_clean_path=None,
) -> dict:
    """Calcula quality_score (0–1) y lista de warnings para un paper."""
    warnings = []
    score = 1.0

    if not title:
        warnings.append("missing_title");    score -= 0.25
    if not doi:
        warnings.append("missing_doi");      score -= 0.20
    if not abstract:
        warnings.append("missing_abstract"); score -= 0.15
    if not year:
        warnings.append("missing_year");     score -= 0.10
    if not authors:
        warnings.append("missing_authors");  score -= 0.10
    if len(refs) < 5:
        warnings.append("no_references_extracted"); score -= 0.10
    if md_clean_path is not None:
        try:
            from pathlib import Path as _Path
            p = _Path(md_clean_path)
            if not p.exists() or p.stat().st_size < 3000:
                warnings.append("short_md_clean"); score -= 0.10
        except Exception:
            pass

    return {"quality_score": round(max(0.0, score), 2), "warnings": warnings}


def main():
    ap = argparse.ArgumentParser(description="Extrae metadatos de TEI XML (recursivo por fases)")
    ap.add_argument("--project", required=True, help="Nombre del proyecto (subcarpeta bajo --base)")
    ap.add_argument("--base",    default=DEFAULT_BASE, help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--tei-dir",     default="", help="Ruta TEI; si no, usa <base>/<project>/tei")
    ap.add_argument("--source-type", default="", help="Fuente de los PDFs: scopus, inbox, adhoc, manual (defecto: auto)")
    args = ap.parse_args()

    base        = Path(args.base)
    project     = args.project
    tei_dir     = Path(args.tei_dir) if args.tei_dir else (base / project / "tei")
    source_type = args.source_type or ""
    prov_cache  = _load_prov_cache(_CACHE_PATH)
    doi_manual_by_name, doi_manual_by_title = _load_doi_manual(_DOI_MANUAL_PATH)

    if not tei_dir.exists():
        raise SystemExit(f"No existe TEI dir: {tei_dir}")

    out_dir       = base / project / "metadata"
    per_paper_dir = out_dir / "per_paper"
    out_dir.mkdir(parents=True, exist_ok=True)
    per_paper_dir.mkdir(parents=True, exist_ok=True)

    papers_meta_path = out_dir / "papers_metadata.jsonl"
    refs_path        = out_dir / "references.jsonl"

    ns = {"tei": "http://www.tei-c.org/ns/1.0"}

    # Buscar recursivamente .tei.xml y .xml (evitar duplicados)
    tei_files_set = set(tei_dir.rglob("*.tei.xml")) | set(tei_dir.rglob("*.xml"))
    tei_files = sorted(tei_files_set)

    if not tei_files:
        raise SystemExit(f"No hay TEI .xml en: {tei_dir}")

    print(f"TEI encontrados: {len(tei_files)}")

    # Durabilidad: leer el JSONL previo (para preservar doi/journal no vacíos)
    # y hacer backup .bak antes de reescribirlo.
    prev_meta = _load_prev_meta(papers_meta_path)
    if papers_meta_path.exists():
        bak = papers_meta_path.with_suffix(papers_meta_path.suffix + ".bak")
        shutil.copy(papers_meta_path, bak)

    # Solo emitir metadata para TEI con md_clean correspondiente: evita papers
    # fantasma (TEI huérfanos de dedup/renombrados). Stems normalizados (_norm).
    md_dir = base / project / "md_clean"
    md_stems = set()
    if md_dir.exists():
        for p in md_dir.glob("*.clean.md"):
            md_stems.add(_norm(p.name[: -len(".clean.md")]))

    total_refs    = 0
    papers_written = 0
    orphans: List[str] = []

    with papers_meta_path.open("w", encoding="utf-8") as f_meta, \
         refs_path.open("w", encoding="utf-8") as f_refs:

        for tei_file in tei_files:
            try:
                tree = ET.parse(tei_file)
                root = tree.getroot()
            except Exception as e:
                print(f"⚠️  No puedo parsear {tei_file.name}: {e}")
                continue

            paper_id = infer_paper_id(tei_file)
            phase    = phase_from_path(tei_file)

            # Saltar TEI huérfanos: sin md_clean correspondiente no se emite
            # metadata (restos de dedup/renombrados).
            tei_stem = _tei_stem(tei_file.name)
            if _norm(tei_stem) not in md_stems:
                orphans.append(tei_stem)
                continue

            new_rec = {
                "title":   extract_title(root, ns),
                "doi":     extract_doi(root, ns),
                "journal": extract_journal(root, ns),
                "year":    extract_year(root, ns),
                "authors": extract_authors(root, ns),
            }
            abstract   = extract_abstract(root, ns)
            highlights = extract_highlights(root, ns)
            refs       = extract_references(root, ns)

            # ── Durabilidad de campos editables ──
            # 1) Si el TEI no trae DOI, intenta doi_manual.xlsx (por nombre de
            #    archivo y, en segundo intento, por título normalizado).
            if not new_rec.get("doi"):
                cand = doi_manual_by_name.get(_strip_pdf(paper_id))
                if not cand and new_rec.get("title"):
                    cand = doi_manual_by_title.get(normalize_title(new_rec["title"]))
                if cand:
                    new_rec["doi"] = cand
            # 2) No machacar campos previos no vacíos con un vacío del TEI.
            prev = prev_meta.get(paper_id, {})
            for _f in PRESERVE_FIELDS:
                if _is_filled(prev.get(_f)):
                    new_rec[_f] = prev[_f]

            # 3) Si aún no hay revista pero tenemos DOI, completarla desde Crossref.
            if not _is_filled(new_rec.get("journal")) and new_rec.get("doi"):
                cj = _crossref_journal(new_rec["doi"])
                if cj:
                    new_rec["journal"] = cj

            title   = new_rec["title"]
            doi     = new_rec["doi"]
            journal = new_rec["journal"]
            year    = new_rec["year"]
            authors = new_rec["authors"]

            md_clean_path = base / project / "md_clean" / f"{paper_id}.clean.md"
            quality = compute_quality(title, doi, year, authors, abstract, refs,
                                      md_clean_path=md_clean_path)

            prov = _infer_provenance(doi, project, prov_cache, source_type)
            meta = {
                "project":         project,
                "phase":           phase,
                "paper_id":        paper_id,
                "stable_id":       _doi_slug(doi) if doi else paper_id,
                "title":           title,
                "doi":             doi,
                "journal":         journal or "",
                "year":            year,
                "authors":         authors,
                "abstract":        abstract,
                "highlights":      highlights,
                "n_references":    len(refs),
                "tei_file":        str(tei_file),
                "source_pdf":      None,
                "processed_date":  date.today().isoformat(),
                "source_type":     prov["source_type"],
                "download_source": prov["download_source"],
                "download_url":    prov["download_url"],
                "access_type":     prov["access_type"],
                "download_date":   prov["download_date"],
                "quality_score":   quality["quality_score"],
                "warnings":        quality["warnings"],
            }

            f_meta.write(json.dumps(meta, ensure_ascii=False) + "\n")
            papers_written += 1

            for r in refs:
                r2 = dict(r)
                r2["project"]  = project
                r2["phase"]    = phase
                r2["paper_id"] = paper_id
                f_refs.write(json.dumps(r2, ensure_ascii=False) + "\n")
                total_refs += 1

            (per_paper_dir / f"{paper_id}.metadata.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (per_paper_dir / f"{paper_id}.references.json").write_text(
                json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    print(f"✅ Papers procesados : {papers_written}")
    print(f"✅ Referencias       : {total_refs}")
    print(f"⏭️  TEI huérfanos saltados (sin md_clean): {len(orphans)}")
    for stem in sorted(orphans):
        print(f"     - {stem}")
    print(f"📄 Metadata JSONL   : {papers_meta_path}")
    print(f"📚 References JSONL : {refs_path}")
    print(f"📁 Por-paper en     : {per_paper_dir}")


if __name__ == "__main__":
    main()
