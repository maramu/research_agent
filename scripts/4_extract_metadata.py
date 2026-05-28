#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
4_extract_metadata.py

Extrae de GROBID TEI:
- title, doi, journal, year, authors, abstract, highlights
- referencias (listBibl) con campos (doi, title, journal, year, raw)
- phase (detectada desde la ruta del TEI)

Busca recursivamente todos los .tei.xml y .xml bajo:
  /Volumes/research/categorias/<project>/tei/

Salida:
  /Volumes/research/categorias/<project>/metadata/
    papers_metadata.jsonl
    references.jsonl
    per_paper/
      <paper_id>.metadata.json
      <paper_id>.references.json

Uso:
  python3 4_extract_metadata.py --project bioleaching_critical_materials
  python3 4_extract_metadata.py --project microalgae --base /Volumes/research/categorias

Variables de entorno (config/.env):
    OLLAMA_HOST → URL del servidor Ollama (defecto: http://pciq22.uca.es:11434)
    GROBID_URL  → URL del servidor GROBID  (defecto: http://pciq22.uca.es:8070)
"""

import argparse
import hashlib
import json
import os
import re
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
    return find_first_text(root, [
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

    total_refs    = 0
    papers_written = 0

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

            title      = extract_title(root, ns)
            doi        = extract_doi(root, ns)
            journal    = extract_journal(root, ns)
            year       = extract_year(root, ns)
            authors    = extract_authors(root, ns)
            abstract   = extract_abstract(root, ns)
            highlights = extract_highlights(root, ns)
            refs       = extract_references(root, ns)

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
                "journal":         journal,
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
    print(f"📄 Metadata JSONL   : {papers_meta_path}")
    print(f"📚 References JSONL : {refs_path}")
    print(f"📁 Por-paper en     : {per_paper_dir}")


if __name__ == "__main__":
    main()
