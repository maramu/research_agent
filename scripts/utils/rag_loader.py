# -*- coding: utf-8 -*-
"""
Carga de índice FAISS + metadata y embedding de consultas — UNA sola implementación
(item 57). Antes `load_metadata`, `load_index_and_meta` y `embed_query` estaban
copiados "VERBATIM" en 8_query_rag.py, run_eval.py, pool_candidates.py,
run_rag_batch.py y rag_core.py, y las copias ya se desalinearon una vez (item 53).

Sin dependencia de streamlit. `faiss`/`numpy` se importan al usarse para que los
módulos que solo necesitan `embed_query` no paguen el import de faiss.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np


def load_metadata(emb_dir: Path) -> List[Dict]:
    """Lee `<emb_dir>/metadata.jsonl` (SystemExit si no existe)."""
    meta_path = Path(emb_dir) / "metadata.jsonl"
    if not meta_path.exists():
        raise SystemExit(f"No existe metadata.jsonl en: {emb_dir}")
    out = []
    with meta_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def check_alignment(index, meta, where: str = "") -> None:
    """Invariante del item 55b al CARGAR: índice y metadata deben ir alineados.
    Antes los consumidores hacían `if idx >= len(meta): continue`, tolerando en
    silencio una desalineación parcial (los resultados apuntarían al chunk equivocado)."""
    if index.ntotal != len(meta):
        raise RuntimeError(
            f"Índice y metadata desalineados{' en ' + where if where else ''}: "
            f"index.ntotal={index.ntotal} != len(metadata)={len(meta)}. "
            "Reconstruye con `5_build_embeddings.py --project <cat> --force`.")


def load_index_and_meta(project: str, phase: str, base: Path):
    """(index, meta, cfg) de `<base>/<project>/embeddings/<phase>/`. SystemExit si
    no existe el índice; RuntimeError si índice y metadata no están alineados."""
    import faiss  # perezoso
    emb_dir = Path(base) / project / "embeddings" / phase
    index_path = emb_dir / "index.faiss"
    meta_path = emb_dir / "metadata.jsonl"
    cfg_path = emb_dir / "config.json"
    if not (index_path.exists() and meta_path.exists()):
        raise SystemExit(f"No existe índice FAISS en: {emb_dir}")
    index = faiss.read_index(str(index_path))
    meta = load_metadata(emb_dir)
    check_alignment(index, meta, str(emb_dir))
    cfg = {}
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return index, meta, cfg


def embed_query(client, query: str, model: str) -> np.ndarray:
    """Vector CRUDO de la consulta (la normalización L2 la hace `dense_rank`, item 55a)."""
    resp = client.embeddings(model=model, prompt=query)
    return np.array(resp["embedding"], dtype="float32")
