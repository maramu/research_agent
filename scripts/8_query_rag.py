#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
8_query_rag.py — Paso 8 del pipeline research_agent (CLI de consulta RAG)

Realiza búsqueda por similitud vectorial sobre el índice FAISS de un proyecto
usando Ollama (bge-m3 por defecto) e imprime los chunks más relevantes.

Posición en el pipeline:
    embeddings/<phase>/index.faiss → 8_query_rag.py → resultados en stdout

Flujo de consulta:
    1. Embeddea la query con Ollama (mismo modelo que se usó al indexar)
    2. Busca los k*5 vecinos más cercanos en FAISS (IndexFlatL2)
    3. Filtra por --type y/o --paper si se especifican
    4. Devuelve los top-k resultados con distancia, paper_id, sección y snippet

Ficheros leídos:
    /Volumes/research/categorias/<project>/embeddings/<phase>/index.faiss
    /Volumes/research/categorias/<project>/embeddings/<phase>/metadata.jsonl
    /Volumes/research/categorias/<project>/embeddings/<phase>/config.json
    config/.env

Parámetros CLI:
    query                 Pregunta o consulta en texto libre (obligatorio, posicional)
    --project PROJECT     Nombre del proyecto/categoría (obligatorio)
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)
    --phase PHASE         Subcarpeta del índice a consultar, o 'all' (defecto: all)
    --k N                 Número de resultados a mostrar (defecto: 8)
    --type TYPE           Filtrar chunks por tipo: text | table
    --paper PAPER_ID      Filtrar por paper_id (coincidencia parcial)

Variables de entorno (config/.env):
    OLLAMA_HOST           URL del servidor Ollama (defecto: http://pciq22.uca.es:11434)

Dependencias:
    faiss-cpu, numpy, ollama, python-dotenv

Ejemplo:
    python3 8_query_rag.py "hydrogen sulfide removal biogas" \\
        --project anoxic_biogas_biodesulfurization --k 10

Nota:
    El modelo de embedding se lee de config.json del índice. Si no existe,
    usa OLLAMA_MODEL_EMBED de utils/constants.py (bge-m3). Asegúrate de que
    el modelo con el que se consulta coincide con el usado al indexar.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict

import numpy as np
import faiss
import ollama
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from utils.constants import OLLAMA_MODEL_EMBED, year_from_paper_id

# ── Cargar config/.env ────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

DEFAULT_BASE  = "/Volumes/research/categorias"
DEFAULT_MODEL = OLLAMA_MODEL_EMBED
DEFAULT_K     = 8


def load_metadata(emb_dir: Path) -> List[Dict]:
    meta_path = emb_dir / "metadata.jsonl"
    if not meta_path.exists():
        raise SystemExit(f"No existe metadata.jsonl en: {emb_dir}")
    out = []
    with meta_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def embed_query(client: ollama.Client, q: str, model: str) -> np.ndarray:
    resp = client.embeddings(model=model, prompt=q)
    return np.array(resp["embedding"], dtype="float32")


def main():
    ap = argparse.ArgumentParser(description="Consulta RAG sobre índice FAISS (Ollama nomic-embed-text)")
    ap.add_argument("query",     help="Pregunta o consulta en texto libre")
    ap.add_argument("--project", required=True, help="Nombre del proyecto (subcarpeta bajo --base)")
    ap.add_argument("--base",    default=DEFAULT_BASE, help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--phase",   default="all",
                    help="Etiqueta de fase del índice a consultar (nombre de categoría, o 'all')")
    ap.add_argument("--k",       type=int, default=DEFAULT_K, help="Número de resultados")
    ap.add_argument("--type",    default="", help="Filtrar por type: text|table (opcional)")
    ap.add_argument("--paper",   default="", help="Filtrar por paper_id contiene (opcional)")
    ap.add_argument("--sections", default="",
                    help="Filtrar por section_canonical, separadas por coma "
                         "(p.ej. methods,results,table). Vacío = todas.")
    ap.add_argument("--year-start", type=int, default=None, help="Año desde (incl.)")
    ap.add_argument("--year-end",   type=int, default=None, help="Año hasta (incl.)")
    args = ap.parse_args()

    allowed_sections = {s.strip() for s in args.sections.split(",") if s.strip()}

    base    = Path(args.base)
    emb_dir = base / args.project / "embeddings" / args.phase

    if not emb_dir.exists():
        raise SystemExit(
            f"No existe directorio de embeddings: {emb_dir}\n"
            f"Ejecuta primero: python3 5_build_embeddings.py "
            f"--project {args.project} --phase {args.phase}"
        )

    config_path = emb_dir / "config.json"
    model = DEFAULT_MODEL
    if config_path.exists():
        cfg   = json.loads(config_path.read_text(encoding="utf-8"))
        model = cfg.get("model", DEFAULT_MODEL)

    index_path = emb_dir / "index.faiss"
    if not index_path.exists():
        raise SystemExit(f"No existe index.faiss en: {emb_dir}")

    ollama_host = os.getenv("OLLAMA_HOST", "http://pciq22.uca.es:11434")
    client      = ollama.Client(host=ollama_host, timeout=120)

    index = faiss.read_index(str(index_path))
    meta  = load_metadata(emb_dir)

    qv         = embed_query(client, args.query, model).reshape(1, -1)
    has_filter = bool(args.type or args.paper or allowed_sections
                      or args.year_start or args.year_end)
    n_fetch    = index.ntotal if has_filter else min(index.ntotal, args.k * 5)
    D, I       = index.search(qv, n_fetch)

    results = []
    for dist, idx in zip(D[0].tolist(), I[0].tolist()):
        if idx < 0 or idx >= len(meta):
            continue
        m = meta[idx]
        if args.type  and m.get("type")     != args.type:
            continue
        if args.paper and args.paper not in m.get("paper_id", ""):
            continue
        if allowed_sections and m.get("section_canonical") not in allowed_sections:
            continue
        year = m.get("year") or year_from_paper_id(m.get("paper_id", ""))
        if (args.year_start and (year is None or year < args.year_start)) or \
           (args.year_end   and (year is None or year > args.year_end)):
            continue
        results.append((dist, idx, m))
        if len(results) >= args.k:
            break

    print(f"\n=== QUERY ===")
    print(args.query)
    print(f"\n=== PROJECT: {args.project}  PHASE: {args.phase}  TOP-{args.k} ===\n")

    for rank, (dist, idx, m) in enumerate(results, start=1):
        phase_tag = f"[{m.get('phase', '?')}] " if args.phase == "all" else ""
        year = m.get("year") or year_from_paper_id(m.get("paper_id", ""))
        print(
            f"[{rank}] dist={dist:.4f} | {phase_tag}"
            f"paper_id={m.get('paper_id')} | year={year} | "
            f"section={m.get('section')} ({m.get('section_canonical','?')}) | type={m.get('type')}"
        )
        snippet = m.get("text", "")[:700].replace("\n", " ")
        print(f"     {snippet}…")
        print("")


if __name__ == "__main__":
    main()
