#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_rag_batch.py — batería de consultas RAG desatendida (headless, sin Streamlit)

Lee un YAML con una lista de preguntas sobre una categoría/proyecto y, para cada
una, reproduce la ruta de recuperación + síntesis de 8_query_rag.py / 2_RAG.py
(sin importar de ninguno de los dos) y escribe un .md con la respuesta
sintetizada (Ollama local) + los chunks recuperados.

Ficheros leídos:
    /Volumes/research/categorias/<category>/embeddings/<phase>/{index.faiss,metadata.jsonl,config.json}
    /Volumes/research/categorias/<category>/metadata/papers_metadata.jsonl
    config/.env

Ejemplo:
    python3 scripts/run_rag_batch.py --config scripts/ejemplos/rag_batch_ejemplo.yml
"""

import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import faiss
import ollama
import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from utils.constants import OLLAMA_MODEL_EMBED
from utils.citations import (load_papers_metadata, build_cite_map,
                             apply_citations, CITE_PROMPT_RULES)
from utils.retrieval import (build_bm25, dense_rank, bm25_rank, rrf_fuse,
                             passes_filters, pool_size)
from utils.export_refs import build_chunks_markdown

# ── Cargar config/.env ────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

DEFAULT_BASE = "/Volumes/research/categorias"
EXPORTS_BASE = "/Volumes/research/exports"


def load_metadata(emb_dir: Path):
    """Copiado VERBATIM de 8_query_rag.py."""
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
    """Copiado VERBATIM de 8_query_rag.py."""
    resp = client.embeddings(model=model, prompt=q)
    return np.array(resp["embedding"], dtype="float32")


def build_context_text(chunks):
    """Copiado VERBATIM de _build_context_text en 2_RAG.py (renombrada)."""
    parts = []
    for i, m in enumerate(chunks, start=1):
        snippet = m.get("text", "").strip()
        section = m.get("section", "?")
        parts.append(f"[{i}] sección: {section}\n{snippet}")
    return "\n\n---\n\n".join(parts)


_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slugify(text: str, n_words: int = 6) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())[:n_words]
    slug = _SLUG_RE.sub("", "_".join(words))
    return slug or "pregunta"


def retrieve(index, meta, bm25, client, embed_model, query, top_k, hybrid,
             allowed_sections, year_start, year_end):
    """Ensamblado IDÉNTICO a 8_query_rag.py líneas 145-171."""
    qv = embed_query(client, query, embed_model).reshape(1, -1)
    has_filter = bool(allowed_sections or year_start or year_end)
    pool = pool_size(top_k, index.ntotal, has_filter)
    d_idx, dist_map = dense_rank(index, qv, pool)
    if hybrid and bm25 is not None:
        ranked = rrf_fuse(d_idx, bm25_rank(bm25, query, pool))
    else:
        ranked = [(i, dist_map[i]) for i in d_idx]

    results = []
    for idx, score in ranked:
        if idx >= len(meta):
            continue
        m = meta[idx]
        if not passes_filters(m, type_=None, paper=None,
                              sections=allowed_sections or None,
                              year_start=year_start, year_end=year_end):
            continue
        results.append((score, idx, m))
        if len(results) >= top_k:
            break
    return results


def synthesize(client, model, results, query, papers_meta):
    context = build_context_text(m for _, _, m in results)
    cite_map = build_cite_map(results, papers_meta)

    # Plantilla EXACTA de synthesize_answer (2_RAG.py 244-255).
    system_content = f"""Eres un asistente científico. Responde a la pregunta basándote ÚNICAMENTE en los fragmentos numerados que se proporcionan a continuación.

Reglas:
- Si los fragmentos no contienen información suficiente para responder, dilo claramente.
- No inventes datos. No uses conocimiento externo a los fragmentos.
- Responde en el mismo idioma que la pregunta.
{CITE_PROMPT_RULES}

Fragmentos:
{context}

Recuerda: cita con [N] junto a cada dato; sin sección de Referencias."""

    prompt = f"{system_content}\n\nPregunta: {query}\n\nRespuesta:"
    raw = client.generate(model=model, prompt=prompt, stream=False)["response"]
    answer_md = apply_citations(raw, cite_map)
    return answer_md


def run_question(idx, q_cfg, cfg, index, meta, bm25, client, embed_model,
                  papers_meta, base, out_dir):
    query = q_cfg["q"]
    sections = set(q_cfg.get("sections", cfg.get("sections", [])) or [])

    results = retrieve(
        index, meta, bm25, client, embed_model, query,
        top_k=cfg.get("top_k", 8),
        hybrid=cfg.get("hybrid", True),
        allowed_sections=sections,
        year_start=cfg.get("year_start"),
        year_end=cfg.get("year_end"),
    )

    answer_md = synthesize(client, cfg["model"], results, query, papers_meta)

    chunks_md = build_chunks_markdown(
        results, cfg["category"], base, papers_meta,
        query=query, score_label=("rrf" if cfg.get("hybrid", True) else "dist"),
    )

    slug = slugify(query)
    filename = f"{idx:02d}_{slug}.md"
    doc = [
        f"# {query}",
        "",
        f"- **Fecha:** {datetime.now().isoformat(timespec='seconds')}",
        f"- **Modelo:** {cfg['model']}",
        f"- **Categoría:** {cfg['category']}",
        f"- **top_k:** {cfg.get('top_k', 8)}",
        f"- **hybrid:** {cfg.get('hybrid', True)}",
        "",
        "## Respuesta",
        "",
        answer_md,
        "",
        "---",
        "",
        chunks_md,
    ]
    (out_dir / filename).write_text("\n".join(doc), encoding="utf-8")
    return filename


def run_batch(cfg: dict, base: str = DEFAULT_BASE, progress_cb=None) -> dict:
    """Ejecuta una batería de consultas RAG.

    ``cfg`` es el mismo dict que hoy sale del YAML (category, phase, top_k,
    hybrid, year_start, year_end, sections, model, questions).

    ``progress_cb(i, n, question, status, out_path)`` es opcional y se llama
    tras cada pregunta con ``status`` "OK"/"ERROR" y la ruta del .md escrito.

    Devuelve ``{"out_dir", "results": [{"q","status","path"}], "n_ok", "n_err"}``.
    """
    cfg = dict(cfg)  # no mutar el dict del caller
    cfg.setdefault("phase", "all")
    cfg.setdefault("top_k", 8)
    cfg.setdefault("hybrid", True)
    cfg.setdefault("sections", [])
    cfg.setdefault("model", "qwen2.5:14b-instruct")
    cfg.setdefault("synth_timeout", 600)

    category = cfg["category"]
    base_path = Path(base)
    emb_dir = base_path / category / "embeddings" / cfg["phase"]

    if not emb_dir.exists():
        raise SystemExit(f"No existe directorio de embeddings: {emb_dir}")

    config_path = emb_dir / "config.json"
    embed_model = OLLAMA_MODEL_EMBED
    if config_path.exists():
        embed_cfg = json.loads(config_path.read_text(encoding="utf-8"))
        embed_model = embed_cfg.get("model", OLLAMA_MODEL_EMBED)

    index_path = emb_dir / "index.faiss"
    if not index_path.exists():
        raise SystemExit(f"No existe index.faiss en: {emb_dir}")

    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11435")
    client = ollama.Client(host=ollama_host, timeout=cfg["synth_timeout"])

    index = faiss.read_index(str(index_path))
    meta = load_metadata(emb_dir)
    papers_meta = load_papers_metadata(category, base_path)

    bm25 = build_bm25([m.get("text", "") for m in meta]) if cfg["hybrid"] else None
    if cfg["hybrid"] and bm25 is None:
        print("⚠️ rank-bm25 no instalado; usando solo denso.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path(EXPORTS_BASE) / f"rag_batch_{category}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    questions = cfg.get("questions", [])
    n = len(questions)
    results_log = []
    n_ok, n_error = 0, 0

    for i, q_cfg in enumerate(questions, start=1):
        query = q_cfg.get("q", f"pregunta_{i}")
        try:
            filename = run_question(i, q_cfg, cfg, index, meta, bm25, client,
                                     embed_model, papers_meta, base_path, out_dir)
            out_path = str(out_dir / filename)
            print(f"[{i}/{n}] OK  → {filename}")
            results_log.append({"q": query, "status": "OK", "path": out_path})
            n_ok += 1
            if progress_cb:
                progress_cb(i, n, query, "OK", out_path)
        except Exception:
            slug = slugify(query)
            err_filename = f"{i:02d}_{slug}.ERROR.md"
            err_text = (
                f"# {query}\n\n"
                f"- **Fecha:** {datetime.now().isoformat(timespec='seconds')}\n\n"
                f"## Error\n\n```\n{traceback.format_exc()}\n```\n"
            )
            (out_dir / err_filename).write_text(err_text, encoding="utf-8")
            err_path = str(out_dir / err_filename)
            print(f"[{i}/{n}] ERROR → {err_filename}")
            results_log.append({"q": query, "status": "ERROR", "path": err_path})
            n_error += 1
            if progress_cb:
                progress_cb(i, n, query, "ERROR", err_path)

    print(f"\n=== RESUMEN: {n_ok} OK / {n_error} ERROR — {out_dir} ===")
    return {"out_dir": str(out_dir), "results": results_log,
            "n_ok": n_ok, "n_err": n_error}


def main():
    ap = argparse.ArgumentParser(description="Batería de consultas RAG desatendida")
    ap.add_argument("--config", required=True, help="Ruta al YAML de configuración")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    run_batch(cfg)


if __name__ == "__main__":
    main()
