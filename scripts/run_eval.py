#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_eval.py — Evalúa la calidad del retrieval contra un golden Q&A set.

Lee metadatos/eval/golden_<categoria>.jsonl, ejecuta retrieval puro
(igual que 2_RAG.py: embed_query → dense_rank [+ bm25 si --hybrid])
contra el índice FAISS de la categoría, y calcula:

  - Hit@k   : 1 si algún relevant_paper_id aparece en el top-k recuperado
  - MRR     : 1 / posición del primer paper relevante encontrado (0 si ninguno)

Uso:
    python run_eval.py --category anoxic_biogas_biodesulfurization
    python run_eval.py --category anoxic_biogas_biodesulfurization --k 10 --hybrid
    python run_eval.py --category anoxic_biogas_biodesulfurization --phase all

Salida:
    - Tabla por pregunta en stdout (Hit@k, MRR, posición del primer hit)
    - Resumen agregado (Hit@k promedio, MRR promedio)
    - CSV: metadatos/eval/results_<categoria>_<timestamp>.csv
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
import ollama
from dotenv import load_dotenv

_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils.constants import OLLAMA_MODEL_EMBED
from utils.retrieval import dense_rank, bm25_rank, rrf_fuse, pool_size, build_bm25

DEFAULT_BASE = "/Volumes/research/categorias"
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11435")


def load_golden(category: str, eval_dir: Path) -> list[dict]:
    path = eval_dir / f"golden_{category}.jsonl"
    if not path.exists():
        raise SystemExit(f"No existe golden set: {path}")
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_index_and_meta(project: str, phase: str, base: Path):
    emb_dir = base / project / "embeddings" / phase
    index_path = emb_dir / "index.faiss"
    meta_path  = emb_dir / "metadata.jsonl"
    cfg_path   = emb_dir / "config.json"
    if not (index_path.exists() and meta_path.exists()):
        raise SystemExit(f"No existe índice FAISS en: {emb_dir}")
    index = faiss.read_index(str(index_path))
    meta = []
    with meta_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                meta.append(json.loads(line))
    cfg = {}
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return index, meta, cfg


def embed_query(client, query: str, model: str) -> np.ndarray:
    resp = client.embeddings(model=model, prompt=query)
    return np.array(resp["embedding"], dtype="float32")


def retrieve_paper_ids(client, query: str, model: str, index, meta, bm25, k: int, hybrid: bool) -> list[str]:
    """Replica el flujo de retrieval puro de 2_RAG.py: sin filtros, sin adjuntos.
    Devuelve la lista de paper_id en orden de relevancia (sin duplicados),
    igual que `retrieved_papers` en 2_RAG.py."""
    qv = embed_query(client, query, model).reshape(1, -1)
    pool = pool_size(k, index.ntotal, has_filter=False)
    d_idx, dist_map = dense_rank(index, qv, pool)

    if hybrid and bm25 is not None:
        ranked = rrf_fuse(d_idx, bm25_rank(bm25, query, pool))
    else:
        ranked = [(i, dist_map[i]) for i in d_idx]

    paper_ids = []
    seen = set()
    for idx, _score in ranked:
        if idx >= len(meta):
            continue
        pid = meta[idx].get("paper_id", "")
        if pid and pid not in seen:
            seen.add(pid)
            paper_ids.append(pid)
        if len(paper_ids) >= k:
            break
    return paper_ids


def eval_question(retrieved: list[str], relevant: list[str]) -> dict:
    relevant_set = set(relevant)
    hit = 0
    rr = 0.0
    first_hit_pos = None
    for pos, pid in enumerate(retrieved, start=1):
        if pid in relevant_set:
            hit = 1
            rr = 1.0 / pos
            first_hit_pos = pos
            break
    return {"hit": hit, "rr": rr, "first_hit_pos": first_hit_pos}


def main():
    ap = argparse.ArgumentParser(description="Evalúa retrieval contra golden Q&A set")
    ap.add_argument("--category", required=True, help="Nombre de la categoría")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--phase", default="all", help="Fase/índice a evaluar (defecto: all)")
    ap.add_argument("--k", type=int, default=8, help="Top-k a recuperar (defecto: 8, igual que UI)")
    ap.add_argument("--hybrid", action="store_true", help="Usar recuperación híbrida (denso + BM25)")
    ap.add_argument("--eval-dir", default="", help="Directorio de golden sets (defecto: <base>/../metadatos/eval)")
    args = ap.parse_args()

    base = Path(args.base)
    eval_dir = Path(args.eval_dir) if args.eval_dir else base.parent / "metadatos" / "eval"

    golden = load_golden(args.category, eval_dir)
    index, meta, cfg = load_index_and_meta(args.category, args.phase, base)
    embed_model = cfg.get("model", OLLAMA_MODEL_EMBED)

    bm25 = None
    if args.hybrid:
        texts = [m.get("text", "") for m in meta]
        bm25 = build_bm25(texts)
        if bm25 is None:
            print("Advertencia: rank-bm25 no instalado o índice vacío; usando solo denso.")

    client = ollama.Client(host=OLLAMA_HOST, timeout=120)

    print(f"Categoría  : {args.category}")
    print(f"Fase       : {args.phase}")
    print(f"Preguntas  : {len(golden)}")
    print(f"k          : {args.k}")
    print(f"Modo       : {'híbrido' if (args.hybrid and bm25) else 'denso'}")
    print(f"Modelo emb : {embed_model}")
    print("")

    results_rows = []
    for i, item in enumerate(golden, start=1):
        question = item["question"]
        relevant = item.get("relevant_paper_ids", [])

        retrieved = retrieve_paper_ids(
            client, question, embed_model, index, meta, bm25, args.k, args.hybrid
        )
        scores = eval_question(retrieved, relevant)

        print(f"[{i}/{len(golden)}] {question[:70]}...")
        print(f"    Hit@{args.k}: {scores['hit']}  ·  RR: {scores['rr']:.3f}  ·  "
              f"primera coincidencia: pos {scores['first_hit_pos'] or '—'}")

        results_rows.append({
            "question": question,
            "relevant_paper_ids": ";".join(relevant),
            "retrieved_paper_ids": ";".join(retrieved),
            "hit": scores["hit"],
            "rr": round(scores["rr"], 4),
            "first_hit_pos": scores["first_hit_pos"] or "",
        })

    n = len(results_rows)
    hit_rate = sum(r["hit"] for r in results_rows) / n if n else 0.0
    mrr = sum(r["rr"] for r in results_rows) / n if n else 0.0

    print("")
    print("=" * 60)
    print(f"RESUMEN — {args.category}")
    print("=" * 60)
    print(f"Hit@{args.k} promedio : {hit_rate:.3f}  ({sum(r['hit'] for r in results_rows)}/{n})")
    print(f"MRR              : {mrr:.3f}")
    print("=" * 60)

    # CSV de resultados
    eval_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = eval_dir / f"results_{args.category}_{ts}.csv"
    fieldnames = ["question", "relevant_paper_ids", "retrieved_paper_ids", "hit", "rr", "first_hit_pos"]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results_rows)
    print(f"\nResultados CSV: {out_path}")


if __name__ == "__main__":
    main()
