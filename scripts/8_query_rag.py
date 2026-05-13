#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
8_query_rag.py

Consulta el índice FAISS de embeddings usando Ollama nomic-embed-text.

Lee embeddings desde:
  /Volumes/research/<project>/embeddings/<phase>/

Uso:
  python3 8_query_rag.py "PLA PBAT anaerobic digestion methane" \
    --project bioplastics_microplastics \
    --phase bioplastics_microplastics \
    --k 10

  python3 8_query_rag.py "bioleaching platinum group metals" \
    --project bioleaching_critical_materials \
    --phase all

Variables de entorno (config/.env):
    OLLAMA_HOST → URL del servidor Ollama (defecto: http://pciq22.uca.es:11434)
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict

import numpy as np
import faiss
import ollama
from dotenv import load_dotenv

# ── Cargar config/.env ────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

DEFAULT_BASE  = "/Volumes/research"
DEFAULT_MODEL = "nomic-embed-text"
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


def embed_query(q: str, model: str) -> np.ndarray:
    resp = ollama.embeddings(model=model, prompt=q)
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
    args = ap.parse_args()

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

    index = faiss.read_index(str(index_path))
    meta  = load_metadata(emb_dir)

    qv       = embed_query(args.query, model).reshape(1, -1)
    D, I     = index.search(qv, args.k * 5)

    results = []
    for dist, idx in zip(D[0].tolist(), I[0].tolist()):
        if idx < 0 or idx >= len(meta):
            continue
        m = meta[idx]
        if args.type  and m.get("type")     != args.type:
            continue
        if args.paper and args.paper not in m.get("paper_id", ""):
            continue
        results.append((dist, idx, m))
        if len(results) >= args.k:
            break

    print(f"\n=== QUERY ===")
    print(args.query)
    print(f"\n=== PROJECT: {args.project}  PHASE: {args.phase}  TOP-{args.k} ===\n")

    for rank, (dist, idx, m) in enumerate(results, start=1):
        phase_tag = f"[{m.get('phase', '?')}] " if args.phase == "all" else ""
        print(
            f"[{rank}] dist={dist:.4f} | {phase_tag}"
            f"paper_id={m.get('paper_id')} | "
            f"section={m.get('section')} | type={m.get('type')}"
        )
        snippet = m.get("text", "")[:700].replace("\n", " ")
        print(f"     {snippet}…")
        print("")


if __name__ == "__main__":
    main()
