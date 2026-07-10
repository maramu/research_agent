# -*- coding: utf-8 -*-
"""Genera BibTeX, RIS y CSV desde una lista de dicts de papers_metadata.jsonl."""
import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from utils.constants import year_from_paper_id
from utils.citations import citation_for_chunk


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
    import io, json, zipfile
    from pathlib import Path
    categorias_dir = Path(categorias_dir)
    pdfs_dir = categorias_dir / project / "pdfs"
    md_dir   = categorias_dir / project / "md_clean"

    # Mapa paper_id → stable_id desde papers_metadata.jsonl
    _pid_to_stable: dict = {}
    jsonl = categorias_dir / project / "metadata" / "papers_metadata.jsonl"
    if jsonl.exists():
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                    pid = m.get("paper_id", "")
                    sid = m.get("stable_id", "")
                    if pid and sid and pid != sid:
                        _pid_to_stable[pid] = sid
                except Exception:
                    pass

    # Índice de todos los PDFs por stem (para fallback glob)
    _pdf_by_stem: dict = {}
    if pdfs_dir.exists():
        for p in pdfs_dir.glob("*.pdf"):
            _pdf_by_stem[p.stem] = p

    def _find_pdf(pid: str):
        """Devuelve Path del PDF o None. Prueba pid → stable_id → glob prefijo."""
        if pid in _pdf_by_stem:
            return _pdf_by_stem[pid]
        sid = _pid_to_stable.get(pid, "")
        if sid and sid in _pdf_by_stem:
            return _pdf_by_stem[sid]
        # último recurso: primer PDF cuyo stem empiece por pid
        for stem, path in _pdf_by_stem.items():
            if stem.startswith(pid[:20]):
                return path
        return None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pid in paper_ids:
            if include_pdf:
                pdf = _find_pdf(pid)
                if pdf:
                    zf.write(pdf, f"pdfs/{pdf.name}")
            if include_md:
                md = md_dir / f"{pid}.clean.md"
                if md.exists():
                    zf.write(md, f"md_clean/{md.name}")
    return buf.getvalue()


def _fmt_authors_md(authors) -> str:
    """Formatea autores a texto legible (mismo criterio que 11_Articulos.py)."""
    if not authors:
        return ""
    if isinstance(authors, str):
        return authors
    out = []
    for a in authors:
        if isinstance(a, dict):
            fn = (a.get("forename") or "").strip()
            sn = (a.get("surname") or "").strip()
            nombre = (fn + " " + sn).strip() or (a.get("full") or "").strip()
        else:
            nombre = str(a)
        if nombre:
            out.append(nombre)
    return "; ".join(out)


def _text_fence(text: str) -> str:
    """Cerca de tildes segura: más larga que cualquier racha de '~' ya presente en `text`."""
    longest = 0
    current = 0
    for ch in text:
        if ch == "~":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "~" * max(3, longest + 1)


def build_chunks_markdown(results, project, categorias_dir, papers_meta,
                           query=None, score_label="score") -> str:
    """Serializa los chunks recuperados a un único documento Markdown con la
    referencia bibliográfica completa por chunk, pensado para alimentar un LLM
    externo que deba citar. `results` = lista de tuplas (score, idx, m).
    Devuelve str."""
    unique_papers = {
        m.get("paper_id") for _, _, m in results
        if m.get("paper_id") and m.get("paper_id") != "__attachment__"
    }

    lines = [f"# Chunks RAG — {project}", ""]
    if query is not None:
        lines.append(f"- **Consulta:** {query}")
    lines.append(f"- **Fecha:** {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- **Nº chunks:** {len(results)}")
    lines.append(f"- **Nº papers únicos:** {len(unique_papers)}")
    lines.append("")

    for n, (score, _idx, m) in enumerate(results, start=1):
        paper_id = m.get("paper_id", "?")
        section = m.get("section", "?")
        section_c = m.get("section_canonical", "?")
        chunk_type = m.get("type", "?")
        text = (m.get("text") or "").strip()

        lines.append(f"## [{n}] `{paper_id}`")
        lines.append("")

        if paper_id == "__attachment__":
            cite = m.get("_cite") or "Adjunto efímero"
            lines.append(f"- **Referencia:** {cite}")
        elif m.get("doc_type") == "book":
            # Libro: referencia con capítulo + página física (formato de libro).
            lines.append(f"- **Referencia:** {citation_for_chunk(m, papers_meta)}")
            lines.append(f"- **Capítulo:** {m.get('heading_path', '—')}")
            lines.append(f"- **Páginas:** {m.get('page_start', '—')}–{m.get('page_end', '—')}")
            lines.append(f"- **book_id:** `{paper_id}`")
        else:
            rec = papers_meta.get(paper_id, {})
            title = rec.get("title") or "—"
            authors = _fmt_authors_md(rec.get("authors")) or "—"
            year = rec.get("year") or year_from_paper_id(paper_id) or "—"
            journal = rec.get("journal") or "—"
            doi = rec.get("doi")
            doi_str = f"https://doi.org/{doi}" if doi else "—"

            lines.append(f"- **Título:** {title}")
            lines.append(f"- **Autores:** {authors}")
            lines.append(f"- **Año:** {year}")
            lines.append(f"- **Revista:** {journal}")
            lines.append(f"- **DOI:** {doi_str}")
            lines.append(f"- **paper_id:** `{paper_id}`")

        lines.append(f"- **Sección:** {section} (canónica: {section_c})")
        lines.append(f"- **Tipo:** {chunk_type}")
        lines.append(f"- **{score_label}:** {score:.4f}")
        lines.append("")
        lines.append("**Texto:**")
        fence = _text_fence(text)
        lines.append(fence)
        lines.append(text)
        lines.append(fence)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


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
