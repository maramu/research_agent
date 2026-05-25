#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
6_make_packages.py

Crea paquetes para NotebookLM en modo append-only:
  PKG_XXX_FULLTEXT.md
  PKG_XXX_REFERENCES.md
  PKG_XXX_INDEX.md
  PKG_XXX_manifest.json

Lee:
  /Volumes/research/categorias/<project>/md_clean/**/*.clean.md
  /Volumes/research/categorias/<project>/metadata/per_paper/<id>.metadata.json
  /Volumes/research/categorias/<project>/metadata/per_paper/<id>.references.json

Salida:
  /Volumes/research/categorias/<project>/notebooklm_packages/pkg_XXX/

Uso:
  python3 6_make_packages.py --project bioleaching_critical_materials --phase bioleaching_critical_materials
  python3 6_make_packages.py --project microalgae --phase all

Variables de entorno (config/.env):
    OLLAMA_HOST → URL del servidor Ollama (defecto: http://pciq22.uca.es:11434)
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml
from dotenv import load_dotenv

# ── Cargar config/.env ────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

DEFAULT_BASE   = "/Volumes/research/categorias"
_KEYWORDS_PATH = Path(__file__).parent.parent / "config" / "keywords.yml"

@dataclass
class Paper:
    paper_id: str
    phase: str
    md_clean_path: Path
    meta_path: Path
    refs_path: Path


def safe(s: Optional[str]) -> str:
    return (s or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def year_from_paper_id(paper_id: str) -> Optional[int]:
    """Extrae el año de un paper_id buscando el primer patrón YYYY (1900-2039)."""
    m = re.search(r'(?<!\d)(19\d{2}|20[0-3]\d)(?!\d)', paper_id)
    return int(m.group(1)) if m else None


def load_keywords_for_category(category: str, max_kw: int = 6) -> List[str]:
    """Devuelve las primeras max_kw keywords de keywords.yml para la categoría dada."""
    try:
        data = yaml.safe_load(_KEYWORDS_PATH.read_text(encoding="utf-8"))
        return ((data or {}).get(category) or [])[:max_kw]
    except Exception:
        return []


def format_corpus_header(project: str, papers: List[Paper], keywords: List[str]) -> str:
    """Cabecera de corpus que se prepende al FULLTEXT package."""
    years: List[int] = []
    for p in papers:
        y: Optional[int] = None
        try:
            meta = load_json(p.meta_path)
            raw_y = meta.get("year")
            if isinstance(raw_y, int) and 1900 < raw_y < 2100:
                y = raw_y
        except Exception:
            pass
        if y is None:
            y = year_from_paper_id(p.paper_id)
        if y is not None:
            years.append(y)

    period  = f"{min(years)}-{max(years)}" if years else "?"
    today   = datetime.now().strftime("%Y-%m-%d")
    kw_str  = ", ".join(keywords) if keywords else "—"

    lines = [
        f"# Corpus: {project}",
        f"## Papers incluidos: {len(papers)}",
        f"## Periodo: {period}",
        f"## Última actualización: {today}",
        f"## Temas principales: {kw_str}",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def paper_id_from_md_clean(md_path: Path) -> str:
    return re.sub(r"\.clean\.md$", "", md_path.name)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def phase_from_path(p: Path, default_phase: str = "unknown") -> str:
    parts = p.parts
    if "md_clean" in parts:
        idx = parts.index("md_clean")
        # idx+1 es la subcarpeta de fase, idx+2 sería el fichero
        if idx + 2 < len(parts):
            return parts[idx + 1]
        # fichero directamente en md_clean/ → usar el nombre del proyecto
        return default_phase

    m = re.match(r"^(phase[^_]+)_", p.name)
    if m:
        return m.group(1)
    return default_phase


def read_existing_packaged_ids(pkgs_dir: Path, phase_filter: str) -> Set[str]:
    packaged: Set[str] = set()
    if not pkgs_dir.exists():
        return packaged
    for manifest in pkgs_dir.rglob("PKG_*_manifest.json"):
        try:
            m = load_json(manifest)
            # Solo contar los manifests del mismo phase (o todos si all)
            if phase_filter != "all":
                if m.get("phase", "all") not in (phase_filter, "all"):
                    continue
            for pid in m.get("paper_ids", []):
                packaged.add(pid)
        except Exception:
            continue
    return packaged


def discover_papers(project_dir: Path, phase_filter: str) -> List[Paper]:
    md_clean_dir = project_dir / "md_clean"
    meta_dir     = project_dir / "metadata" / "per_paper"

    # Busca tanto en md_clean/ directamente como en subdirectorios de fase
    md_files = sorted(
        set(md_clean_dir.glob("*.clean.md")) | set(md_clean_dir.rglob("*.clean.md"))
    )
    if not md_files:
        raise SystemExit(f"No encuentro md_clean en: {md_clean_dir}")

    papers: List[Paper] = []
    for md in md_files:
        phase = phase_from_path(md, default_phase=project_dir.name)

        # Filtrar por fase
        if phase_filter != "all" and phase != phase_filter:
            continue

        pid  = paper_id_from_md_clean(md)
        meta = meta_dir / f"{pid}.metadata.json"
        refs = meta_dir / f"{pid}.references.json"

        if not meta.exists():
            print(f"⚠️  SKIP (no metadata): {pid}")
            continue

        papers.append(Paper(pid, phase, md, meta, refs))

    return papers


def fmt_source_line(journal: str, year: Optional[int]) -> str:
    j = safe(journal)
    if j and year:
        return f"**Source:** {j} ({year})"
    if j:
        return f"**Source:** {j}"
    if year:
        return f"**Year:** {year}"
    return ""


def format_fulltext_md(paper: Paper, project_dir: Path) -> str:
    meta = load_json(paper.meta_path)
    doi  = safe(meta.get("doi"))
    year: Optional[int] = meta.get("year")
    if not isinstance(year, int):
        year = year_from_paper_id(paper.paper_id)

    summary_path = project_dir / "summaries" / f"{paper.paper_id}.summary.md"
    summary = (
        summary_path.read_text(encoding="utf-8", errors="ignore").strip()
        if summary_path.exists()
        else ""
    )
    body = paper.md_clean_path.read_text(encoding="utf-8", errors="ignore").strip()

    lines = [f"# Paper: {paper.paper_id}"]
    if doi:
        lines.append(f"**DOI:** {doi}")
    if year:
        lines.append(f"**Año:** {year}")
    lines.append("")
    if summary:
        lines.append("**Resumen:**")
        lines.append(summary)
        lines.append("")
        lines.append("---")
        lines.append("")
    lines.append("**Texto completo:**")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def format_references_md(paper: Paper) -> str:
    meta  = load_json(paper.meta_path)
    title = safe(meta.get("title")) or paper.paper_id
    doi   = safe(meta.get("doi"))
    refs  = []
    if paper.refs_path.exists():
        try:
            refs = load_json(paper.refs_path)
        except Exception:
            refs = []

    lines = []
    lines.append(f"# References — [{paper.paper_id}] {title}")
    lines.append("")
    if doi:
        lines.append(f"**DOI:** {doi}")
        lines.append("")
    if not refs:
        lines.append("_(No references extracted)_")
        lines.append("")
        return "\n".join(lines)
    for i, r in enumerate(refs, start=1):
        raw  = safe(r.get("raw"))
        rdoi = safe(r.get("doi"))
        if rdoi and rdoi not in raw:
            raw = f"{raw} DOI: {rdoi}"
        lines.append(f"{i}. {raw}")
    lines.append("")
    return "\n".join(lines)


def format_index_md(papers: List[Paper], package_id: str, created_at: str) -> str:
    lines = []
    lines.append(f"# {package_id} — Index")
    lines.append("")
    lines.append(f"- Created at: {created_at}")
    lines.append(f"- Papers: {len(papers)}")
    lines.append("")
    lines.append("## Papers")
    lines.append("")
    for p in papers:
        meta   = load_json(p.meta_path)
        title  = safe(meta.get("title")) or p.paper_id
        doi    = safe(meta.get("doi"))
        journal= safe(meta.get("journal"))
        year   = meta.get("year")
        nrefs  = meta.get("n_references")
        phase  = safe(meta.get("phase")) or p.phase
        src    = safe(journal)
        if year:
            src = (src + f" ({year})").strip() if src else str(year)
        bits = [f"**{p.paper_id}** [{phase}] — {title}"]
        if doi:
            bits.append(f"DOI: {doi}")
        if src:
            bits.append(f"Source: {src}")
        if nrefs is not None:
            bits.append(f"Refs: {nrefs}")
        lines.append("- " + " | ".join(bits))
    lines.append("")
    return "\n".join(lines)


def next_package_number(pkgs_dir: Path) -> int:
    if not pkgs_dir.exists():
        return 1
    nums = []
    for d in pkgs_dir.glob("pkg_*"):
        m = re.match(r"pkg_(\d+)$", d.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def write_package(
    pkgs_dir: Path,
    project: str,
    phase: str,
    package_number: int,
    papers: List[Paper],
    package_size: int,
    source_paths: Dict,
    mode: str,
) -> Path:
    pkg_id     = f"PKG_{package_number:03d}"
    pkg_folder = pkgs_dir / f"pkg_{package_number:03d}"
    pkg_folder.mkdir(parents=True, exist_ok=True)

    created_at     = now_iso()
    fulltext_name  = f"{pkg_id}_FULLTEXT.md"
    refs_name      = f"{pkg_id}_REFERENCES.md"
    index_name     = f"{pkg_id}_INDEX.md"
    manifest_name  = f"{pkg_id}_manifest.json"

    project_dir = pkgs_dir.parent
    keywords    = load_keywords_for_category(project)

    fulltext_parts = [format_corpus_header(project, papers, keywords)]
    for p in papers:
        fulltext_parts.append(format_fulltext_md(p, project_dir))
        fulltext_parts.append("\n\n---\n\n")
    (pkg_folder / fulltext_name).write_text(
        "".join(fulltext_parts).rstrip() + "\n", encoding="utf-8"
    )

    refs_parts = []
    for p in papers:
        refs_parts.append(format_references_md(p))
        refs_parts.append("\n\n---\n\n")
    (pkg_folder / refs_name).write_text(
        "".join(refs_parts).rstrip() + "\n", encoding="utf-8"
    )

    (pkg_folder / index_name).write_text(
        format_index_md(papers, pkg_id, created_at), encoding="utf-8"
    )

    manifest = {
        "package_id":      pkg_id,
        "project":         project,
        "phase":           phase,
        "created_at":      created_at,
        "mode":            mode,
        "package_size":    package_size,
        "paper_ids":       [p.paper_id for p in papers],
        "source_paths":    source_paths,
        "files_generated": {
            "fulltext":   fulltext_name,
            "references": refs_name,
            "index":      index_name,
        },
        "notes": "NotebookLM-friendly bundle: full text + extracted references + index.",
    }
    (pkg_folder / manifest_name).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return pkg_folder


def main():
    ap = argparse.ArgumentParser(description="Crea paquetes NotebookLM por fase")
    ap.add_argument("--project",      required=True, help="Nombre del proyecto (subcarpeta bajo --base)")
    ap.add_argument("--base",         default=DEFAULT_BASE, help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--phase",        default="all",
                    help="Fase a empaquetar (nombre de categoría, o 'all')")
    ap.add_argument("--package-size", type=int, default=45)
    ap.add_argument("--repack-all",   action="store_true",
                    help="Rehace paquetes ignorando manifests previos (no borra nada automáticamente)")
    ap.add_argument("--order",        choices=["paper_id"], default="paper_id")
    args = ap.parse_args()

    base        = Path(args.base)
    project_dir = base / args.project
    pkgs_dir    = project_dir / "notebooklm_packages"
    pkgs_dir.mkdir(parents=True, exist_ok=True)

    papers = discover_papers(project_dir, args.phase)

    if args.order == "paper_id":
        papers.sort(key=lambda p: (p.phase, p.paper_id))

    if args.repack_all:
        mode       = "repack-all"
        to_package = papers
        start_num  = 1
    else:
        mode      = "append-only"
        already   = read_existing_packaged_ids(pkgs_dir, args.phase)
        to_package = [p for p in papers if p.paper_id not in already]
        start_num  = next_package_number(pkgs_dir)

    if not to_package:
        print("✅ No hay papers nuevos para empaquetar. (Todo ya está en manifests)")
        return

    print(f"Phase    : {args.phase}")
    print(f"Papers   : {len(to_package)}")
    print(f"Pkg size : {args.package_size}")
    print(f"Modo     : {mode}")
    print("")

    size   = args.package_size
    batches = [to_package[i:i + size] for i in range(0, len(to_package), size)]

    source_paths = {
        "md_clean": str(project_dir / "md_clean"),
        "metadata": str(project_dir / "metadata" / "per_paper"),
    }

    created  = []
    pkg_num  = start_num
    for batch in batches:
        folder = write_package(
            pkgs_dir=pkgs_dir,
            project=args.project,
            phase=args.phase,
            package_number=pkg_num,
            papers=batch,
            package_size=size,
            source_paths=source_paths,
            mode=mode,
        )
        created.append(folder)
        print(f"✅ Creado paquete: {folder.name}  ({len(batch)} papers)")
        pkg_num += 1

    print("\nArchivos a subir a NotebookLM (por paquete):")
    for f in created:
        for mf in sorted(f.glob("PKG_*_*.md")):
            print(" -", mf)
    print("\n(El manifest queda para control interno.)")


if __name__ == "__main__":
    main()
