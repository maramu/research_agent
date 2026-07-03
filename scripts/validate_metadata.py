#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI de QA de metadata (Nivel 1, local, sin red) — sin número de pipeline.

Por categoría: valida papers_metadata.jsonl con las heurísticas de
utils/metadata_validation.py y escribe el sidecar
CATEGORIAS_DIR/<cat>/metadata/validation_<cat>.jsonl (una línea por paper
flagged; sobrescribe el anterior). SOLO ESCRIBE el sidecar; NUNCA toca
papers_metadata.jsonl.

Uso:
    python3 scripts/validate_metadata.py --category biogas_upgrading_biomethanation
    python3 scripts/validate_metadata.py --all
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils.constants import CANONICAL_CATEGORIES
from utils.metadata_validation import ISSUE_CODES, load_jsonl, validate_category

# Misma raíz que pipeline.py (no se importa pipeline para no arrastrar deps).
CATEGORIAS_DIR = Path("/Volumes/research/categorias")


def run_category(category: str) -> None:
    meta_dir = CATEGORIAS_DIR / category / "metadata"
    jsonl = meta_dir / "papers_metadata.jsonl"
    if not jsonl.exists():
        print(f"[{category}] papers_metadata.jsonl no encontrado — omitida")
        return

    total = len(load_jsonl(jsonl))
    flagged = validate_category(category, CATEGORIAS_DIR)

    sidecar = meta_dir / f"validation_{category}.jsonl"
    with sidecar.open("w", encoding="utf-8") as f:
        for row in flagged:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_code = Counter(i["code"] for row in flagged for i in row["issues"])
    with_doi = sum(1 for row in flagged if row["has_doi"])

    print(f"[{category}] {total} papers · {len(flagged)} flagged "
          f"({with_doi} con DOI → arreglables con Crossref en Nivel 2)")
    for code, n in by_code.most_common():
        print(f"    {code:26s} {n:4d}  — {ISSUE_CODES.get(code, '')}")
    print(f"    sidecar: {sidecar}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--category", action="append", default=[],
                    help="categoría a validar (repetible)")
    ap.add_argument("--all", action="store_true",
                    help="validar todas las CANONICAL_CATEGORIES")
    args = ap.parse_args()

    if args.all:
        categories = CANONICAL_CATEGORIES
    elif args.category:
        categories = args.category
    else:
        ap.error("indica --category <cat> (repetible) o --all")

    for cat in categories:
        run_category(cat)


if __name__ == "__main__":
    main()
