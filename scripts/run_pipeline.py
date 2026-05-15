# -*- coding: utf-8 -*-
"""
run_pipeline.py — CLI del orquestador research_agent

Tres subcomandos:

  # Flujo A — Scopus: buscar + descargar + procesar por categoría
  python run_pipeline.py scopus --recent-days 7
  python run_pipeline.py scopus --category microalgae --max 500 --year-start 2020
  python run_pipeline.py scopus --dry-run

  # Flujo B — Inbox: renombrar + cribado + procesar categorías afectadas
  python run_pipeline.py inbox
  python run_pipeline.py inbox --folders /Volumes/research/inbox /tmp/otros_pdfs
  python run_pipeline.py inbox --no-rename

  # Flujo C — Ad-hoc: proyecto temporal desde carpeta de PDFs
  python run_pipeline.py adhoc --name revision_metanol --pdfs /Users/martin/papers
  python run_pipeline.py adhoc --name h2_storage --pdfs ~/Desktop/papers_h2

Para automatización con cron/launchd:
  # Ingesta semanal (solo lo nuevo, todas las categorías)
  python run_pipeline.py scopus --recent-days 7

  # Ingesta semanal (solo microalgae)
  python run_pipeline.py scopus --category microalgae --recent-days 7
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pipeline import run_scopus, run_inbox, run_adhoc, NAS_ROOT


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_scopus(args: argparse.Namespace) -> int:
    result = run_scopus(
        categories=args.categories,
        recent_days=args.recent_days,
        max_results=args.max,
        year_start=args.year_start,
        year_end=args.year_end,
        doctype=args.doctype,
        queries_file=args.queries,
        dry_run=args.dry_run,
    )
    return 0 if result["status"] in ("ok", "partial") else 1


def cmd_inbox(args: argparse.Namespace) -> int:
    result = run_inbox(
        folders=args.folders,
        rename=not args.no_rename,
    )
    return 0 if result["status"] in ("ok", "partial") else 1


def cmd_adhoc(args: argparse.Namespace) -> int:
    result = run_adhoc(
        name=args.name,
        pdf_dir=args.pdfs,
    )
    return 0 if result["status"] == "ok" else 1


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Orquestador del pipeline research_agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── scopus ────────────────────────────────────────────────────────────
    sp = sub.add_parser(
        "scopus",
        help="Búsqueda Scopus → descarga → procesado directo por categoría.",
    )
    sp.add_argument(
        "--category", action="append", dest="categories", metavar="CAT",
        help="Categoría (repetible). Por defecto: todas las del YAML.",
    )
    sp.add_argument("--max", type=int, default=200, metavar="N",
                    help="Max resultados por categoría (defecto: 200).")
    sp.add_argument("--recent-days", type=int, default=None, metavar="N",
                    help="Solo artículos indexados en los últimos N días.")
    sp.add_argument("--year-start", type=int, default=None, metavar="AÑO")
    sp.add_argument("--year-end", type=int, default=None, metavar="AÑO")
    sp.add_argument("--doctype", default=None, metavar="TIPO",
                    help="ar=article, re=review, cp=conference paper.")
    sp.add_argument("--queries", default=None, metavar="YAML",
                    help="Ruta al YAML de queries Scopus.")
    sp.add_argument("--dry-run", action="store_true",
                    help="Solo muestra totales, sin descargar ni procesar.")
    sp.set_defaults(func=cmd_scopus)

    # ── inbox ─────────────────────────────────────────────────────────────
    ip = sub.add_parser(
        "inbox",
        help="PDFs en inbox → renombrar → cribado → categorías → procesado.",
    )
    ip.add_argument(
        "--folders", nargs="+", default=None, metavar="DIR",
        help=f"Carpetas con PDFs (defecto: {NAS_ROOT}/inbox).",
    )
    ip.add_argument("--no-rename", action="store_true",
                    help="Saltar el paso de renombrado por DOI.")
    ip.set_defaults(func=cmd_inbox)

    # ── adhoc ─────────────────────────────────────────────────────────────
    ap = sub.add_parser(
        "adhoc",
        help="Proyecto ad-hoc desde carpeta de PDFs (sin cribado).",
    )
    ap.add_argument("--name", required=True, metavar="NOMBRE",
                    help="Nombre del proyecto (e.g. revision_metanol).")
    ap.add_argument("--pdfs", required=True, metavar="DIR",
                    help="Carpeta con los PDFs de entrada.")
    ap.set_defaults(func=cmd_adhoc)

    args = parser.parse_args()
    rc = args.func(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
