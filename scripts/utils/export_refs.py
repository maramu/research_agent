# -*- coding: utf-8 -*-
"""Genera BibTeX, RIS y CSV desde una lista de dicts de papers_metadata.jsonl."""
import csv
import io
import json
import re
from pathlib import Path
from typing import Dict, List


def load_papers(jsonl_path: Path) -> List[Dict]:
    papers = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    papers.append(json.loads(line))
                except Exception:
                    pass
    return papers


def _bib_key(m: dict, seen: set) -> str:
    authors = m.get("authors") or []
    surname = ""
    if authors:
        a = authors[0]
        raw = a.get("surname") or a.get("full", "").split()[-1]
        surname = re.sub(r"[^a-zA-Z]", "", raw)
    year = str(m.get("year") or "XXXX")
    base = f"{surname}{year}" or m.get("paper_id", "unknown")
    key, i = base, 1
    while key in seen:
        key = f"{base}{chr(96 + i)}"
        i += 1
    seen.add(key)
    return key


def _au_str_bibtex(authors: list) -> str:
    parts = [a.get("full", "") for a in authors if a.get("full")]
    return " and ".join(parts) or "Unknown"


def to_bibtex(papers: List[Dict]) -> str:
    chunks, seen = [], set()
    for m in papers:
        key      = _bib_key(m, seen)
        title    = (m.get("title") or "").replace("{", "").replace("}", "")
        authors  = _au_str_bibtex(m.get("authors") or [])
        journal  = m.get("journal") or ""
        year     = str(m.get("year") or "")
        doi      = m.get("doi") or ""
        abstract = (m.get("abstract") or "")[:500]
        lines    = [f"@article{{{key},",
                    f"  author   = {{{authors}}},",
                    f"  title    = {{{title}}},"]
        if journal:  lines.append(f"  journal  = {{{journal}}},")
        if year:     lines.append(f"  year     = {{{year}}},")
        if doi:      lines.append(f"  doi      = {{{doi}}},")
        if abstract: lines.append(f"  abstract = {{{abstract}}},")
        lines.append("}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def to_ris(papers: List[Dict]) -> str:
    lines = []
    for m in papers:
        lines.append("TY  - JOUR")
        title = m.get("title") or ""
        if title: lines.append(f"TI  - {title}")
        for a in (m.get("authors") or []):
            full = a.get("full", "")
            if full: lines.append(f"AU  - {full}")
        journal = m.get("journal") or ""
        if journal: lines.append(f"JO  - {journal}")
        year = m.get("year")
        if year: lines.append(f"PY  - {year}")
        doi = m.get("doi") or ""
        if doi:
            lines.append(f"DO  - {doi}")
            lines.append(f"UR  - https://doi.org/{doi}")
        abstract = (m.get("abstract") or "")[:500]
        if abstract: lines.append(f"AB  - {abstract}")
        lines.append("ER  -")
        lines.append("")
    return "\n".join(lines)


def build_papers_zip(
    paper_ids: list,
    project: str,
    categorias_dir,
    include_pdf: bool = True,
    include_md: bool = True,
) -> bytes:
    """ZIP en memoria con PDFs y/o md_clean de los paper_ids dados."""
    import io
    import zipfile
    from pathlib import Path
    categorias_dir = Path(categorias_dir)
    pdfs_dir = categorias_dir / project / "pdfs"
    md_dir   = categorias_dir / project / "md_clean"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pid in paper_ids:
            if include_pdf:
                pdf = pdfs_dir / f"{pid}.pdf"
                if pdf.exists():
                    zf.write(pdf, f"pdfs/{pdf.name}")
            if include_md:
                md = md_dir / f"{pid}.clean.md"
                if md.exists():
                    zf.write(md, f"md_clean/{md.name}")
    return buf.getvalue()


def to_csv_str(papers: List[Dict]) -> str:
    buf = io.StringIO()
    fields = ["paper_id", "stable_id", "title", "authors",
              "journal", "year", "doi", "n_references",
              "quality_score", "abstract"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for m in papers:
        row = {k: m.get(k, "") for k in fields}
        aus = m.get("authors") or []
        row["authors"] = "; ".join(
            a.get("full", "") for a in aus if a.get("full")
        )
        writer.writerow(row)
    return buf.getvalue()
