#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pool_candidates.py — Construye el ground truth de los golden sets por pooling
de recuperación, reusando la lógica de retrieval de run_eval.py.

Flujo de trabajo en dos pasos:

  1. pool   — Por cada pregunta, recupera los top `pool-k` candidatos en modo
              denso e híbrido, los une (ordenados por mejor posición entre los
              dos modos) y escribe un review_<category>.md con checkboxes para
              que un experto marque los paper_id realmente relevantes.

  2. build  — Lee el review_<category>.md anotado (líneas `- [x]`), valida los
              paper_id contra el índice FAISS real (guard anti-bug del guion) y
              escribe el golden_<category>.jsonl definitivo.

Uso:
    python pool_candidates.py pool  --category <cat> --questions preguntas.json
    python pool_candidates.py build --category <cat> --questions preguntas.json \\
                                    --review review_<cat>.md
"""

import argparse
import json
import os
import re
import sys
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
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://pciq22.uca.es:11434")


# ───────────────────────────────────────────────────────────────────────────
# Loaders (mismos que run_eval.py)
# ───────────────────────────────────────────────────────────────────────────

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


def load_questions(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"No existe el fichero de preguntas: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("El JSON de preguntas debe ser una lista de {question, answer}.")
    return data


def load_paper_metadata(project: str, base: Path) -> dict:
    """{paper_id: {title, year, journal}}. Clave paper_id con fallback stable_id."""
    path = base / project / "metadata" / "papers_metadata.jsonl"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = rec.get("paper_id") or rec.get("stable_id")
            if key:
                out[key] = {
                    "title":   rec.get("title", ""),
                    "year":    rec.get("year", ""),
                    "journal": rec.get("journal", ""),
                }
    return out


def real_paper_ids(project: str, phase: str, base: Path) -> set[str]:
    """Conjunto de paper_id realmente indexados en embeddings/<phase>/metadata.jsonl."""
    path = base / project / "embeddings" / phase / "metadata.jsonl"
    if not path.exists():
        raise SystemExit(f"No existe metadata del índice: {path}")
    ids: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pid = json.loads(line).get("paper_id", "")
                if pid:
                    ids.add(pid)
    return ids


# ───────────────────────────────────────────────────────────────────────────
# Pooling
# ───────────────────────────────────────────────────────────────────────────

def rank_to_paper_ids(ranked_idxs, meta, cap: int):
    """ranked_idxs: lista de índices de meta (best-first).
    Devuelve (lista paper_id únicos capada a `cap`, {paper_id: pos 1-based})."""
    ordered: list[str] = []
    pos: dict[str, int] = {}
    for idx in ranked_idxs:
        if idx >= len(meta):
            continue
        pid = meta[idx].get("paper_id", "")
        if pid and pid not in pos:
            pos[pid] = len(ordered) + 1
            ordered.append(pid)
            if len(ordered) >= cap:
                break
    return ordered, pos


def cmd_pool(args):
    base = Path(args.base)
    eval_dir = Path(args.eval_dir) if args.eval_dir else base.parent / "metadatos" / "eval"
    out_path = Path(args.out) if args.out else eval_dir / f"review_{args.category}.md"

    questions = load_questions(Path(args.questions))
    index, meta, cfg = load_index_and_meta(args.category, args.phase, base)
    embed_model = cfg.get("model", OLLAMA_MODEL_EMBED)
    papers_meta = load_paper_metadata(args.category, base)

    bm25 = build_bm25([m.get("text", "") for m in meta])
    if bm25 is None:
        print("Advertencia: rank-bm25 no instalado o índice vacío; el ranking híbrido será solo denso.")

    client = ollama.Client(host=OLLAMA_HOST, timeout=120)

    print(f"Categoría : {args.category}")
    print(f"Fase      : {args.phase}")
    print(f"Preguntas : {len(questions)}")
    print(f"pool-k    : {args.pool_k}")
    print(f"Modelo emb: {embed_model}")
    print("")

    blocks: list[str] = []
    for qid, item in enumerate(questions, start=1):
        question = item["question"]
        qv = embed_query(client, question, embed_model).reshape(1, -1)
        pool = pool_size(args.pool_k, index.ntotal, has_filter=False)

        d_idx, _dist_map = dense_rank(index, qv, pool)
        hybrid_ranked = rrf_fuse(d_idx, bm25_rank(bm25, question, pool))
        h_idx = [idx for idx, _score in hybrid_ranked]

        _dense_ids,  dense_pos  = rank_to_paper_ids(d_idx, meta, args.pool_k)
        _hybrid_ids, hybrid_pos = rank_to_paper_ids(h_idx, meta, args.pool_k)

        INF = float("inf")
        candidates = set(dense_pos) | set(hybrid_pos)
        ordered = sorted(
            candidates,
            key=lambda pid: min(dense_pos.get(pid, INF), hybrid_pos.get(pid, INF)),
        )

        print(f"[{qid}/{len(questions)}] {question[:70]}... → {len(ordered)} candidatos")

        lines = [f"<!-- qid: {qid} -->", f"## Q{qid}: {question}", ""]
        for pid in ordered:
            info = papers_meta.get(pid, {})
            year = info.get("year", "") or "—"
            title = info.get("title", "") or ""
            dp = dense_pos.get(pid)
            hp = hybrid_pos.get(pid)
            d_str = f"d{dp}" if dp else "d—"
            h_str = f"h{hp}" if hp else "h—"
            lines.append(f"- [ ] {pid} | ({year}) {title} | {d_str} {h_str}")
        lines.append("")
        blocks.append("\n".join(lines))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Review de candidatos — {args.category}\n\n"
        f"Marca con `[x]` los paper_id relevantes para cada pregunta, luego ejecuta "
        f"`pool_candidates.py build`.\n\n"
    )
    out_path.write_text(header + "\n".join(blocks), encoding="utf-8")
    print(f"\nReview escrito: {out_path}")


# ───────────────────────────────────────────────────────────────────────────
# Build
# ───────────────────────────────────────────────────────────────────────────

_QID_RE     = re.compile(r"^<!--\s*qid:\s*(\d+)\s*-->")
_CHECKED_RE = re.compile(r"^-\s*\[[xX]\]\s*(.+)$")


def parse_review(path: Path) -> dict[int, list[str]]:
    """Devuelve {qid: [paper_id marcados]} leyendo las líneas `- [x]`."""
    if not path.exists():
        raise SystemExit(f"No existe el review: {path}")
    checked: dict[int, list[str]] = {}
    current_qid = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m_qid = _QID_RE.match(line.strip())
            if m_qid:
                current_qid = int(m_qid.group(1))
                checked.setdefault(current_qid, [])
                continue
            m_chk = _CHECKED_RE.match(line.strip())
            if m_chk and current_qid is not None:
                pid = m_chk.group(1).split("|")[0].strip()
                if pid:
                    checked[current_qid].append(pid)
    return checked


def cmd_build(args):
    base = Path(args.base)
    eval_dir = Path(args.eval_dir) if args.eval_dir else base.parent / "metadatos" / "eval"
    review_path = Path(args.review)
    out_path = Path(args.out) if args.out else eval_dir / f"golden_{args.category}.jsonl"

    questions = load_questions(Path(args.questions))
    checked = parse_review(review_path)

    # Guard anti-bug del guion: validar contra el índice real ANTES de escribir.
    valid_ids = real_paper_ids(args.category, args.phase, base)
    invalid = sorted({
        pid for ids in checked.values() for pid in ids if pid not in valid_ids
    })
    if invalid:
        print("ABORTADO: hay paper_id marcados que no existen en el índice FAISS:")
        for pid in invalid:
            print(f"  - {pid}")
        print(f"\nÍndice consultado: {base / args.category / 'embeddings' / args.phase / 'metadata.jsonl'}")
        raise SystemExit(1)

    eval_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for qid, item in enumerate(questions, start=1):
        relevant = checked.get(qid, [])
        rows.append({
            "question": item["question"],
            "answer": item.get("answer", ""),
            "relevant_paper_ids": relevant,
        })
        n = len(relevant)
        flag = "  ⚠️ SIN RELEVANTES" if n == 0 else ""
        print(f"Q{qid}: {n} relevante(s){flag}")

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nGolden escrito: {out_path}")


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Pooling de candidatos para golden sets")
    sub = ap.add_subparsers(dest="command", required=True)

    p_pool = sub.add_parser("pool", help="Genera review_<category>.md con candidatos a marcar")
    p_pool.add_argument("--category", required=True)
    p_pool.add_argument("--questions", required=True, help="JSON con lista de {question, answer}")
    p_pool.add_argument("--base", default=DEFAULT_BASE)
    p_pool.add_argument("--phase", default="all")
    p_pool.add_argument("--pool-k", type=int, default=25, dest="pool_k")
    p_pool.add_argument("--eval-dir", default="")
    p_pool.add_argument("--out", default="")
    p_pool.set_defaults(func=cmd_pool)

    p_build = sub.add_parser("build", help="Construye golden_<category>.jsonl desde el review marcado")
    p_build.add_argument("--category", required=True)
    p_build.add_argument("--questions", required=True, help="JSON con lista de {question, answer}")
    p_build.add_argument("--review", required=True, help="review_<category>.md anotado")
    p_build.add_argument("--base", default=DEFAULT_BASE)
    p_build.add_argument("--phase", default="all")
    p_build.add_argument("--eval-dir", default="")
    p_build.add_argument("--out", default="")
    p_build.set_defaults(func=cmd_build)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
