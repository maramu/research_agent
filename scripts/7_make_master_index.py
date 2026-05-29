#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
7_make_master_index.py — Paso 7 del pipeline research_agent

Genera MASTER_INDEX.md con resumen global, tabla de paquetes y detalle por
paper para facilitar la navegación del corpus desde NotebookLM o cualquier
lector Markdown.

Posición en el pipeline:
    notebooklm_packages/pkg_*/PKG_*_manifest.json → 7_make_master_index.py
    → notebooklm_packages/MASTER_INDEX.md

Secciones del MASTER_INDEX.md generado:
    1. Resumen global (total paquetes, total papers, papers por fase)
    2. Packages overview (tabla con pkg_id, fase, nº papers, fecha)
    3. Packages detail (por paquete: rutas de ficheros + lista detallada de papers
       con título, DOI, journal, año y nº referencias)

Ficheros leídos:
    /Volumes/research/categorias/<project>/notebooklm_packages/pkg_*/PKG_*_manifest.json
    /Volumes/research/categorias/<project>/metadata/per_paper/<paper_id>.metadata.json
    config/.env

Ficheros escritos:
    /Volumes/research/categorias/<project>/notebooklm_packages/MASTER_INDEX.md

Parámetros CLI:
    --project PROJECT     Nombre del proyecto/categoría (obligatorio)
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)

Dependencias:
    python-dotenv

Nota:
    Si un paper_id aparece en un manifest pero no tiene fichero .metadata.json,
    se muestra en el índice con el aviso '_(no metadata file found)_' sin
    interrumpir la generación.
"""

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# ── Cargar config/.env ────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

DEFAULT_BASE = "/Volumes/research/categorias"


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def safe(s: Optional[str]) -> str:
    return (s or "").strip()


def find_pkg_folders(pkgs_dir: Path) -> List[Path]:
    pkgs = [d for d in pkgs_dir.glob("pkg_*") if d.is_dir()]
    pkgs.sort(key=lambda p: p.name)
    return pkgs


def get_manifest(pkg_folder: Path) -> Optional[Path]:
    for m in pkg_folder.glob("PKG_*_manifest.json"):
        return m
    return None


def fmt_src(journal: str, year: Optional[int]) -> str:
    j = safe(journal)
    if j and year:
        return f"{j} ({year})"
    if j:
        return j
    if year:
        return str(year)
    return ""


def main():
    ap = argparse.ArgumentParser(description="Genera MASTER_INDEX.md con soporte de fases")
    ap.add_argument("--project", required=True, help="Nombre del proyecto (subcarpeta bajo --base)")
    ap.add_argument("--base",    default=DEFAULT_BASE, help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    args = ap.parse_args()

    base        = Path(args.base)
    project_dir = base / args.project
    pkgs_dir    = project_dir / "notebooklm_packages"
    meta_dir    = project_dir / "metadata" / "per_paper"

    if not pkgs_dir.exists():
        raise SystemExit(f"No existe: {pkgs_dir}")
    if not meta_dir.exists():
        raise SystemExit(f"No existe: {meta_dir}")

    pkg_folders = find_pkg_folders(pkgs_dir)
    if not pkg_folders:
        raise SystemExit(f"No encuentro carpetas pkg_XXX en: {pkgs_dir}")

    lines: List[str] = []
    lines.append(f"# MASTER INDEX — {args.project}")
    lines.append("")
    lines.append("Índice maestro de paquetes NotebookLM organizados por fase.")
    lines.append("")

    # ── Recopilar datos de todos los paquetes ─────────────────
    total_papers  = 0
    total_pkgs    = 0
    phase_counts: Dict[str, int] = defaultdict(int)
    pkg_data = []

    for pkg in pkg_folders:
        manifest_path = get_manifest(pkg)
        if not manifest_path:
            continue
        man     = load_json(manifest_path)
        pkg_id  = man.get("package_id", pkg.name)
        phase   = man.get("phase", "unknown")
        n       = len(man.get("paper_ids", []))
        total_papers += n
        total_pkgs   += 1
        phase_counts[phase] += n
        pkg_data.append((pkg, man, pkg_id, phase, n))

    # ── Resumen global ────────────────────────────────────────
    lines.append("## Resumen")
    lines.append("")
    lines.append(f"- **Total paquetes:** {total_pkgs}")
    lines.append(f"- **Total papers:** {total_papers}")
    lines.append("")
    lines.append("### Papers por fase")
    lines.append("")
    for ph in sorted(phase_counts):
        lines.append(f"- **{ph}:** {phase_counts[ph]} papers")
    lines.append("")

    # ── Tabla de paquetes ─────────────────────────────────────
    lines.append("## Packages overview")
    lines.append("")
    for pkg, man, pkg_id, phase, n in pkg_data:
        created_at = man.get("created_at", "")
        lines.append(f"- **{pkg_id}** [{phase}] — papers: {n} — created_at: {created_at} — folder: `{pkg}`")
    lines.append("")

    # ── Detalle por paquete ───────────────────────────────────
    lines.append("## Packages detail")
    lines.append("")

    for pkg, man, pkg_id, phase, n in pkg_data:
        created_at = man.get("created_at", "")
        paper_ids  = man.get("paper_ids", [])
        files      = man.get("files_generated", {})

        lines.append(f"### {pkg_id}")
        lines.append("")
        lines.append(f"- Phase: **{phase}**")
        if created_at:
            lines.append(f"- Created at: {created_at}")
        lines.append(f"- Papers: {len(paper_ids)}")
        for key, label in [("index", "Index"), ("fulltext", "Fulltext"), ("references", "References")]:
            fname = files.get(key, "")
            if fname:
                lines.append(f"- {label}: `{pkg / fname}`")
        lines.append("")

        lines.append("#### Papers")
        lines.append("")
        for pid in paper_ids:
            meta_path = meta_dir / f"{pid}.metadata.json"
            if meta_path.exists():
                m      = load_json(meta_path)
                title  = safe(m.get("title")) or pid
                doi    = safe(m.get("doi"))
                journal= safe(m.get("journal"))
                year   = m.get("year")
                nrefs  = m.get("n_references")
                ph     = safe(m.get("phase")) or phase
                src    = fmt_src(journal, year)
                bits   = [f"**{pid}** [{ph}] — {title}"]
                if doi:
                    bits.append(f"DOI: {doi}")
                if src:
                    bits.append(f"Source: {src}")
                if nrefs is not None:
                    bits.append(f"Refs: {nrefs}")
                lines.append("- " + " | ".join(bits))
            else:
                lines.append(f"- **{pid}** — _(no metadata file found)_")
        lines.append("")

    out_path = pkgs_dir / "MASTER_INDEX.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ MASTER INDEX creado: {out_path}")
    print(f"   Paquetes : {total_pkgs}")
    print(f"   Papers   : {total_papers}")
    for ph in sorted(phase_counts):
        print(f"   {ph}  : {phase_counts[ph]} papers")


if __name__ == "__main__":
    main()
