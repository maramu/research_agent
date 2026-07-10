#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
books/query.py — Búsqueda de retrieval sobre libros de docencia (SIN LLM).

Wrapper FINO sobre scripts/8_query_rag.py: NO reimplementa el retrieval (denso +
BM25 + RRF + filtros). Solo fija --base /Volumes/research y --project
libros_docencia y delega. 8_query_rag.py imprime, por cada resultado, el score,
paper_id/año/cita, sección, y —para chunks de libro— heading_path + páginas.
Es evaluación de retrieval puro (no hay síntesis con LLM en esa ruta).

Uso:
    python books/query.py "medida de oxigeno disuelto en biorreactores" --k 5
    python books/query.py "downstream processing" --hybrid --k 8

Cualquier flag adicional (--k, --hybrid, --type, --sections, --year-start, …) se
reenvía tal cual a 8_query_rag.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

DEFAULT_BASE = "/Volumes/research"
DEFAULT_COLLECTION = "libros_docencia"

_QUERY_RAG = Path(__file__).resolve().parents[1] / "8_query_rag.py"


def query_books(
    question: str,
    collection: str = DEFAULT_COLLECTION,
    base: str = DEFAULT_BASE,
    extra_args: Optional[List[str]] = None,
) -> subprocess.CompletedProcess:
    """Ejecuta 8_query_rag.py apuntando a la colección de libros y devuelve el
    CompletedProcess (retrieval puro, sin LLM)."""
    cmd = [sys.executable, str(_QUERY_RAG), question,
           "--base", base, "--project", collection] + list(extra_args or [])
    return subprocess.run(cmd, check=False)


def main(argv: Optional[List[str]] = None) -> None:
    """CLI: primer argumento = consulta; el resto se reenvía a 8_query_rag.py."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit('Uso: python books/query.py "tu consulta" [--k N] [--hybrid] …')
    question, extra = argv[0], argv[1:]
    result = query_books(question, extra_args=extra)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
