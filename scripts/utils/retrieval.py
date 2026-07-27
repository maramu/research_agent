# -*- coding: utf-8 -*-
"""Funciones puras de recuperación compartidas (denso + BM25 + RRF + filtros).
Sin estado: el índice FAISS, la metadata y el BM25 los pasa el caller.
El orden de docs BM25 DEBE coincidir con el de metadata.jsonl (== vectores FAISS).

``dense_rank`` es el ÚNICO punto del repo que llama a ``index.search``: la
normalización L2 de la consulta (item 55a) vive ahí y así ninguna ruta de
búsqueda densa puede saltársela. Guard: tests/test_retrieval_normalization.py.
"""

import re
import unicodedata

from utils.embeddings import l2_normalize

RRF_K = 60

# Alfabeto de token BM25 (item 33): alfanumérico ASCII + griegas minúsculas
# (α/β/μ aparecen en el corpus: μ de tasa de crecimiento, α/β de coeficientes).
_GREEK = "α-ω"
_TOKEN_RE = re.compile(rf"[a-z0-9{_GREEK}]+(?:-[a-z0-9{_GREEK}]+)*")
# Segmentos alfabéticos / numéricos dentro de un token mixto: h2s → h | 2 | s.
_ALNUM_SEG_RE = re.compile(rf"[a-z{_GREEK}]+|[0-9]+")


def _fold(text: str) -> str:
    """Minúsculas + NFKD sin marcas de combinación.

    'Desulfurización' → 'desulfurizacion' (antes el `[a-z0-9]+` la partía en
    'desulfurizaci' + 'n'), 'µ' (signo micro) → 'μ' (mu griega). Las griegas NO
    son marcas de combinación, así que sobreviven al filtro.
    """
    folded = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def tokenize(text: str):
    """Tokeniza para BM25 (item 33). Simétrico entre indexado y consulta.

    Mejoras sobre el `[a-z0-9]+` original, que destrozaba acrónimos, fórmulas,
    tildes y griegas:
      - tildes plegadas vía NFKD (`desulfurización` = `desulfurizacion`);
      - griegas minúsculas conservadas como token;
      - acrónimos con guion como UN token, y ADEMÁS sus partes
        (`NR-SOB` → `nr-sob`, `nr`, `sob`) para no perder las coincidencias que
        el tokenizer viejo sí encontraba;
      - tokens mixtos letra/dígito emitidos también por segmentos
        (`h2s` → `h2s`, `h`, `2`, `s`; `tio2` → `tio2`, `tio`, `2`). Esto es lo
        que hace que la consulta "H2S" case con el texto del corpus, donde los
        subíndices vienen aplanados como "H 2 S" (decisión explícita del item 33:
        NO se reescribe el texto del corpus, se arregla el tokenizer).
    """
    out = []
    for raw in _TOKEN_RE.findall(_fold(text)):
        out.append(raw)
        parts = raw.split("-")
        if len(parts) > 1:
            out.extend(parts)
        for part in parts:
            segs = _ALNUM_SEG_RE.findall(part)
            if len(segs) > 1:
                out.extend(segs)
    return out


_ES_STOPWORDS = {
    "de", "la", "el", "en", "para", "con", "que", "del", "los", "las",
    "una", "un", "es", "por", "se", "cual", "como",
}
_ES_CHARS = set("ñáéíóúü")


def looks_spanish(text: str) -> bool:
    """Heurístico barato: ¿la consulta está en español? True si ≥2 indicios.

    Vive aquí, junto a ``tokenize``, porque es una propiedad del comportamiento
    de BM25, no de la UI: **BM25 es puramente léxico y el corpus está en inglés**.
    Una consulta en español solo casa los cognados —`biogas`, `filter`, `pH`,
    `bioreactor`—, que por ser frecuentes en el corpus tienen IDF baja y aportan
    poca señal, mientras que los términos realmente discriminantes de la pregunta
    (`azufre`, `eliminación`, `anóxico`, `lavador`) no aparecen en ningún
    documento y su brazo se queda sin recall. El resultado no es "BM25 no ayuda":
    es que ``rrf_fuse`` funde ese ranking casi aleatorio **a peso igual** con el
    denso, así que puede empeorar activamente el orden que daba el denso solo.
    El denso (bge-m3) sí es multilingüe y no tiene este problema.

    Aciertos: cada stopword DISTINTA encontrada (sobre los tokens ya plegados de
    ``tokenize``, así que funciona con o sin tildes) suma 1, y la presencia de
    ñ/tildes en el texto crudo suma 1 más. Con ≥2 → True. Se cuentan stopwords
    distintas y no repeticiones para que un "de … de … de" no dispare solo.
    Exigir tildes Y stopwords sería demasiado estricto: mucha gente escribe la
    consulta sin acentos, y ese caso hay que cogerlo igual. Ninguna stopword de
    la lista es palabra inglesa, así que el riesgo en el otro sentido es bajo.

    Es deliberadamente tosco: solo alimenta un aviso en la interfaz, nunca
    bloquea ni cambia el retrieval.
    """
    if not text:
        return False
    hits = len(_ES_STOPWORDS & set(tokenize(text)))
    if any(c in _ES_CHARS for c in text.lower()):
        hits += 1
    return hits >= 2


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
    """Devuelve (idxs_best_first, {idx: dist}). qv ya embebido, shape (1, d).

    ÚNICO punto de entrada a la búsqueda densa del repo (7 ficheros, 8 call
    sites). Normaliza L2 la consulta (item 55a) sobre una COPIA, así que el
    caller puede seguir reutilizando su ``qv`` crudo — lo hacen 2_RAG.py (se lo
    pasa después a ``rank_attachment``) y 14_Preparar_clase.py (mismo qv contra
    varios índices).

    Las distancias devueltas son L2 sobre vectores unitarios (== orden coseno),
    comparables entre índices construidos con el mismo modelo. Siguen siendo
    "menor = mejor", como antes del item 55a.
    """
    n = min(int(n), index.ntotal)
    if n <= 0:
        return [], {}
    D, I = index.search(l2_normalize(qv), n)
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
