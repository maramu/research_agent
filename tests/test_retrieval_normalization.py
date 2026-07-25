# -*- coding: utf-8 -*-
"""Tests de la normalización L2 (item 55a), el invariante de integridad (55b) y
el campo `embed_truncated` (P2 auditoría Kimi). 2026-07-26.

Unitarios: sin Ollama, sin red y sin tocar /Volumes/research/ (los índices FAISS
de prueba se construyen en memoria o en tmp_path).
"""

import json
import re
from pathlib import Path

import faiss
import numpy as np
import pytest

from utils.embeddings import (
    NORM_TOL,
    l2_normalize,
    index_mean_norm,
    assert_index_normalized,
    verify_index_integrity,
    embed_texts,
)
from utils.retrieval import dense_rank
from utils.constants import MAX_EMBED_CHARS

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"

# Norma real de bge-m3 vía Ollama medida el 2026-07-20 (item 55a).
BGE_M3_RAW_NORM = 27.11


def _raw_vectors(n=16, d=8, seed=0):
    """Vectores con norma ~27, como los que devuelve bge-m3 sin normalizar."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=(n, d)).astype("float32")
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return (v * BGE_M3_RAW_NORM).astype("float32")


def _write_index(out_dir: Path, vectors, n_meta=None, normalized=True):
    """Escribe un índice + metadata + config de prueba en out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(np.ascontiguousarray(vectors))
    faiss.write_index(index, str(out_dir / "index.faiss"))

    n_meta = vectors.shape[0] if n_meta is None else n_meta
    with (out_dir / "metadata.jsonl").open("w", encoding="utf-8") as f:
        for i in range(n_meta):
            f.write(json.dumps({"paper_id": f"p{i}", "text": "t"}) + "\n")

    cfg = {"project": "x", "phase": "all", "model": "bge-m3",
           "chunks": index.ntotal, "dimension": int(vectors.shape[1])}
    if normalized:
        cfg["normalized"] = True
    (out_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return index


# ═══════════════════════════════════════════════════════════════════════════
# l2_normalize — el helper único
# ═══════════════════════════════════════════════════════════════════════════

class TestL2Normalize:
    def test_normalized_vector_has_unit_norm(self):
        out = l2_normalize(_raw_vectors())
        norms = np.linalg.norm(out, axis=1)
        assert np.allclose(norms, 1.0, atol=NORM_TOL)

    def test_single_vector_norm_is_one(self):
        v = np.array([3.0, 4.0], dtype="float32")
        out = l2_normalize(v)
        assert out.shape == (1, 2)
        assert float(np.linalg.norm(out)) == pytest.approx(1.0, abs=NORM_TOL)

    def test_does_not_mutate_the_input(self):
        """Obligatorio: faiss.normalize_L2 muta in-place y los callers reutilizan
        su qv (2_RAG lo pasa luego a rank_attachment; 14_Preparar_clase a varios
        índices)."""
        v = np.array([[3.0, 4.0]], dtype="float32")
        before = v.copy()
        l2_normalize(v)
        assert np.array_equal(v, before)

    def test_preserves_direction(self):
        v = np.array([[3.0, 4.0]], dtype="float32")
        assert np.allclose(l2_normalize(v), [[0.6, 0.8]], atol=1e-6)

    def test_zero_vector_stays_zero(self):
        out = l2_normalize(np.zeros((1, 4), dtype="float32"))
        assert np.allclose(out, 0.0)

    def test_output_is_float32_and_contiguous(self):
        out = l2_normalize(np.ones((3, 4), dtype="float64"))
        assert out.dtype == np.float32
        assert out.flags["C_CONTIGUOUS"]


# ═══════════════════════════════════════════════════════════════════════════
# dense_rank — normalización del lado consulta
# ═══════════════════════════════════════════════════════════════════════════

class TestDenseRankNormalizesQuery:
    def _index(self):
        vecs = l2_normalize(_raw_vectors(n=10, d=8, seed=1))
        index = faiss.IndexFlatL2(vecs.shape[1])
        index.add(vecs)
        return index, vecs

    def test_query_is_normalized_before_search(self):
        """Una consulta cruda y la misma normalizada dan distancias idénticas."""
        index, vecs = self._index()
        qv_raw = (vecs[3:4] * BGE_M3_RAW_NORM).astype("float32")
        idx_raw, map_raw = dense_rank(index, qv_raw, 5)
        idx_norm, map_norm = dense_rank(index, l2_normalize(vecs[3:4]), 5)
        assert idx_raw == idx_norm
        for i in idx_raw:
            assert map_raw[i] == pytest.approx(map_norm[i], abs=1e-5)

    def test_distances_are_in_unit_sphere_range(self):
        """Sobre vectores unitarios la L2² cae en [0, 4]; sin normalizar la
        consulta se irían a ~700 y dejarían de ser comparables con el adjunto."""
        index, vecs = self._index()
        qv = (vecs[0:1] * BGE_M3_RAW_NORM).astype("float32")
        _idx, dist_map = dense_rank(index, qv, 5)
        assert all(0.0 <= d <= 4.0 for d in dist_map.values())

    def test_exact_match_is_first_with_zero_distance(self):
        index, vecs = self._index()
        qv = (vecs[7:8] * 13.7).astype("float32")     # misma dirección, otra escala
        idxs, dist_map = dense_rank(index, qv, 3)
        assert idxs[0] == 7
        assert dist_map[7] == pytest.approx(0.0, abs=1e-5)

    def test_does_not_mutate_caller_query(self):
        index, vecs = self._index()
        qv = (vecs[0:1] * BGE_M3_RAW_NORM).astype("float32")
        before = qv.copy()
        dense_rank(index, qv, 3)
        assert np.array_equal(qv, before), "dense_rank mutó el qv del caller"

    def test_empty_index_returns_empty(self):
        index = faiss.IndexFlatL2(8)
        assert dense_rank(index, np.ones((1, 8), dtype="float32"), 5) == ([], {})


# ═══════════════════════════════════════════════════════════════════════════
# Item 55b — invariante de integridad
# ═══════════════════════════════════════════════════════════════════════════

class TestVerifyIndexIntegrity:
    def test_happy_path(self, tmp_path):
        vecs = l2_normalize(_raw_vectors(n=12, d=8))
        index = _write_index(tmp_path, vecs)
        n_meta, mean_norm = verify_index_integrity(tmp_path, index)
        assert n_meta == 12
        assert mean_norm == pytest.approx(1.0, abs=NORM_TOL)

    def test_raises_on_ntotal_metadata_mismatch(self, tmp_path):
        vecs = l2_normalize(_raw_vectors(n=12, d=8))
        index = _write_index(tmp_path, vecs, n_meta=11)
        with pytest.raises(SystemExit, match="ntotal"):
            verify_index_integrity(tmp_path, index)

    def test_raises_on_unnormalized_index(self, tmp_path):
        """El estado exacto en el que están las 8 categorías antes del rollout."""
        index = _write_index(tmp_path, _raw_vectors(n=12, d=8))
        with pytest.raises(SystemExit, match="norma L2 media"):
            verify_index_integrity(tmp_path, index)

    def test_raises_when_config_lacks_normalized_flag(self, tmp_path):
        vecs = l2_normalize(_raw_vectors(n=12, d=8))
        index = _write_index(tmp_path, vecs, normalized=False)
        with pytest.raises(SystemExit, match="normalized"):
            verify_index_integrity(tmp_path, index)

    def test_raises_when_metadata_missing(self, tmp_path):
        vecs = l2_normalize(_raw_vectors(n=4, d=8))
        index = _write_index(tmp_path, vecs)
        (tmp_path / "metadata.jsonl").unlink()
        with pytest.raises(SystemExit, match="no existe"):
            verify_index_integrity(tmp_path, index)


class TestAssertIndexNormalized:
    def test_passes_on_normalized_index(self):
        vecs = l2_normalize(_raw_vectors())
        index = faiss.IndexFlatL2(vecs.shape[1])
        index.add(vecs)
        assert assert_index_normalized(index) == pytest.approx(1.0, abs=NORM_TOL)

    def test_raises_on_legacy_index(self):
        """Modo incremental sobre un índice pre-55a: aborta ANTES de escribir."""
        raw = _raw_vectors()
        index = faiss.IndexFlatL2(raw.shape[1])
        index.add(raw)
        with pytest.raises(SystemExit, match="SIN NORMALIZAR"):
            assert_index_normalized(index, context="test")

    def test_mean_norm_of_raw_index_is_about_27(self):
        raw = _raw_vectors()
        index = faiss.IndexFlatL2(raw.shape[1])
        index.add(raw)
        assert index_mean_norm(index) == pytest.approx(BGE_M3_RAW_NORM, abs=0.1)

    def test_mean_norm_of_empty_index_is_zero(self):
        assert index_mean_norm(faiss.IndexFlatL2(8)) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# P2 — embed_truncated
# ═══════════════════════════════════════════════════════════════════════════

class _FakeClient:
    """Cliente Ollama de mentira. `ctx_limit` simula el tope de contexto real:
    un prompt más largo levanta el mismo error que dispara el truncado reactivo."""

    def __init__(self, dims=4, ctx_limit=None):
        self.dims = dims
        self.ctx_limit = ctx_limit
        self.prompts = []

    def embeddings(self, model=None, prompt=None):
        if self.ctx_limit is not None and len(prompt) > self.ctx_limit:
            raise RuntimeError("input length exceeds context length")
        self.prompts.append(prompt)
        return {"embedding": [0.1] * self.dims}


class TestEmbedTruncatedFlag:
    def test_short_texts_are_not_flagged(self):
        client = _FakeClient()
        flags = []
        embed_texts(client, ["corto", "también corto"], "bge-m3", truncated_out=flags)
        assert flags == [False, False]

    def test_pre_truncation_at_max_embed_chars_is_flagged(self):
        client = _FakeClient()
        flags = []
        embed_texts(client, ["z" * (MAX_EMBED_CHARS + 500)], "bge-m3", truncated_out=flags)
        assert flags == [True]
        assert len(client.prompts[0]) == MAX_EMBED_CHARS

    def test_reactive_truncation_is_flagged(self):
        """El caso de 2023_almenglo #34: cabe en MAX_EMBED_CHARS pero excede el
        contexto en tokens, así que el vector solo cubre parte del texto."""
        client = _FakeClient(ctx_limit=1000)
        flags = []
        embed_texts(client, ["y" * 3000], "bge-m3", truncated_out=flags)
        assert flags == [True]
        assert len(client.prompts[0]) <= 1000

    def test_flags_align_with_texts_in_order(self):
        client = _FakeClient()
        flags = []
        texts = ["a", "b" * (MAX_EMBED_CHARS + 1), "c"]
        vecs = embed_texts(client, texts, "bge-m3", truncated_out=flags)
        assert len(vecs) == len(texts) == len(flags)
        assert flags == [False, True, False]

    def test_out_param_is_optional(self):
        client = _FakeClient()
        assert len(embed_texts(client, ["a", "b"], "bge-m3")) == 2

    def test_vectors_are_returned_raw(self):
        """embed_texts NO normaliza: lo hace el constructor del índice."""
        client = _FakeClient(dims=4)
        vecs = embed_texts(client, ["a"], "bge-m3")
        assert float(np.linalg.norm(vecs[0])) != pytest.approx(1.0, abs=NORM_TOL)


# ═══════════════════════════════════════════════════════════════════════════
# Guard estructural: ninguna ruta puede saltarse la normalización
# ═══════════════════════════════════════════════════════════════════════════

# Receptor .search( cuyo nombre contiene "index" → búsqueda FAISS (descarta los
# re.search de patrones compilados, cuyos receptores no se llaman *index*).
_FAISS_SEARCH_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\.search\s*\(")
_FAISS_BUILD_RE  = re.compile(r"faiss\.IndexFlat\w*\s*\(")


def _py_files():
    return [p for p in _SCRIPTS_DIR.rglob("*.py") if "__pycache__" not in p.parts]


class TestNormalizationCannotBeBypassed:
    def test_only_dense_rank_calls_index_search(self):
        """La normalización de la consulta vive en dense_rank, así que ninguna
        otra ruta puede llamar a index.search() directamente (item 55a). Esta es
        la trampa del item 52, donde se escapó la quinta llamada a Ollama."""
        offenders = []
        for path in _py_files():
            src = path.read_text(encoding="utf-8")
            for m in _FAISS_SEARCH_RE.finditer(src):
                if "index" not in m.group(1).lower():
                    continue
                if path.name == "retrieval.py":
                    continue
                line = src[: m.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(_SCRIPTS_DIR)}:{line} → {m.group(0)}")
        assert not offenders, (
            "búsqueda densa saltándose la normalización de dense_rank:\n  "
            + "\n  ".join(offenders)
        )

    def test_dense_rank_is_the_only_search_site(self):
        src = (_SCRIPTS_DIR / "utils" / "retrieval.py").read_text(encoding="utf-8")
        assert src.count(".search(") == 1
        assert "index.search(l2_normalize(qv)" in src

    def test_index_builders_are_the_two_known_ones(self):
        """Un tercer constructor de índice sin normalizar rompería la fusión
        multi-índice de 14_Preparar_clase.py. Si añades uno, normaliza y añádelo
        aquí a conciencia."""
        builders = {
            str(p.relative_to(_SCRIPTS_DIR))
            for p in _py_files()
            if _FAISS_BUILD_RE.search(p.read_text(encoding="utf-8"))
        }
        assert builders == {"5_build_embeddings.py", "books/embed.py"}, builders

    def test_both_builders_normalize_and_verify(self):
        for rel in ("5_build_embeddings.py", "books/embed.py"):
            src = (_SCRIPTS_DIR / rel).read_text(encoding="utf-8")
            assert "l2_normalize(" in src, f"{rel} no normaliza"
            assert "verify_index_integrity(" in src, f"{rel} no verifica el 55b"
            assert '"normalized": True' in src, f"{rel} no marca config.json"
