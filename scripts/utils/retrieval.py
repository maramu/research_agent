# -*- coding: utf-8 -*-
"""Funciones puras de recuperación compartidas (denso + BM25 + RRF + filtros).
Sin estado: el índice FAISS, la metadata y el BM25 los pasa el caller.
El orden de docs BM25 DEBE coincidir con el de metadata.jsonl (== vectores FAISS)."""

import re

RRF_K = 60


def tokenize(text: str):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def build_bm25(texts):
    """Construye un BM25Okapi desde una lista de textos (en orden). None si falla."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return None
    tokenized = [tokenize(t) for t in texts]
    if not tokenized:
        return None
    return BM25Okapi(tokenized)


def dense_rank(index, qv, n):
    """Devuelve (idxs_best_first, {idx: dist}). qv ya embebido, shape (1, d)."""
    n = min(int(n), index.ntotal)
    if n <= 0:
        return [], {}
    D, I = index.search(qv, n)
    idxs, dist_map = [], {}
    for d, i in zip(D[0].tolist(), I[0].tolist()):
        if i < 0:
            continue
        idxs.append(int(i))
        dist_map[int(i)] = float(d)
    return idxs, dist_map


def bm25_rank(bm25, query: str, n):
    """Top-n índices por score BM25 (>0), best-first."""
    import numpy as np
    toks = tokenize(query)
    if bm25 is None or not toks:
        return []
    scores = bm25.get_scores(toks)
    n = min(int(n), len(scores))
    if n <= 0:
        return []
    top = np.argpartition(scores, -n)[-n:]
    top = top[np.argsort(scores[top])[::-1]]
    return [int(i) for i in top if scores[i] > 0]


def rrf_fuse(*ranked_lists, k=RRF_K):
    """Reciprocal Rank Fusion. Devuelve [(idx, score)] ordenado desc."""
    scores = {}
    for lst in ranked_lists:
        for rank, idx in enumerate(lst):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def passes_filters(m, type_=None, paper=None, sections=None,
                   year_start=None, year_end=None, doc_type=None):
    """True si el chunk m pasa los filtros. Centraliza la lógica de items 32/34.

    ``paper`` admite dos formas:
      - str  -> match por substring case-insensitive sobre paper_id (uso UI).
      - colección (set/list/tuple) -> match EXACTO contra ese conjunto de
        paper_id (uso de la consulta premium "profundizar en estos papers").
    ``doc_type`` (p.ej. "book"/"article") filtra por el tipo de documento; el
    filtro por book_id ya lo cubre ``paper`` (paper_id == book_id). Ninguno
    afecta a los filtros IMRaD de artículos cuando se deja en None.
    """
    from utils.constants import year_from_paper_id
    if doc_type and m.get("doc_type") != doc_type:
        return False
    if type_ and m.get("type") != type_:
        return False
    if paper:
        pid = m.get("paper_id", "")
        if isinstance(paper, str):
            if paper.lower() not in pid.lower():
                return False
        elif pid not in paper:
            return False
    if sections and m.get("section_canonical") not in sections:
        return False
    if year_start or year_end:
        year = m.get("year") or year_from_paper_id(m.get("paper_id", ""))
        if (year_start and (year is None or year < year_start)) or \
           (year_end and (year is None or year > year_end)):
            return False
    return True


def pool_size(k, ntotal, has_filter):
    """Tamaño del pool de candidatos por brazo."""
    return ntotal if has_filter else min(ntotal, max(k * 10, 200))
