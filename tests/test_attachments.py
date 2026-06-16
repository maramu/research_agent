# -*- coding: utf-8 -*-
"""Tests de lógica pura para scripts/utils/attachments.py.

No requieren red, FAISS, Ollama ni pymupdf (salvo extract_text, que no se testea).
"""

import numpy as np

from utils.attachments import (
    chunk_text,
    rank_attachment,
    fuse_results,
    content_hash,
)
from utils.citations import attachment_citation_key, build_cite_map


class TestChunkText:
    def test_produces_multiple_chunks_with_overlap(self):
        # Varias párrafos de >100 chars para forzar varios chunks.
        paras = [
            "Párrafo número uno con bastante texto para garantizar que ocupe "
            "más de cien caracteres y permita trocear correctamente.",
            "Segundo párrafo también extenso, con suficientes palabras como para "
            "que el algoritmo de agrupación tenga material con qué trabajar.",
            "Tercer párrafo extenso; incluimos más texto de relleno para asegurar "
            "que haya varios chunks y se pueda comprobar el solape entre ellos.",
            "Cuarto párrafo final con bastante longitud adicional para completar "
            "la prueba de troceado y verificar que ningún chunk sea demasiado corto.",
        ]
        text = "\n\n".join(paras)
        chunks = chunk_text(text, target_chars=150, overlap=30)

        assert len(chunks) > 1
        assert all(len(c) >= 30 for c in chunks)
        # El solape debe reflejarse entre chunks consecutivos.
        for a, b in zip(chunks, chunks[1:]):
            assert a[-30:] in b or b[:30] in a or a in b or b in a

    def test_discards_small_chunks(self):
        chunks = chunk_text("hola", target_chars=100, overlap=10)
        assert chunks == []

    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   \n\n  ") == []


class TestAttachmentCitationKey:
    def test_label_priority(self):
        assert attachment_citation_key("2019_shihab_xxx.pdf", "mi nota") == "(mi nota; adjunto)"

    def test_paper_id_pattern(self):
        assert attachment_citation_key("2019_shihab_xxx.pdf", "") == "(Shihab, 2019; adjunto)"

    def test_stem_fallback(self):
        assert attachment_citation_key("apuntes.pdf", "") == "(apuntes; adjunto)"

    def test_no_filename_no_label(self):
        assert attachment_citation_key(None, "") == "(adjunto)"


class TestFuseResults:
    def _meta(self, name, dist=None):
        return {"name": name, "dist": dist}

    def test_guaranteed_attachment_cupo(self):
        corpus = [(10.0, 0, self._meta("corpus"))]
        attach_scored = [(0, 1.0), (1, 2.0), (2, 3.0)]
        attach_metas = [self._meta(f"attach{i}") for i in range(3)]
        out = fuse_results(corpus, attach_scored, attach_metas, k=4, n_min=2, hybrid=False)
        names = [m["name"] for _, _, m in out]
        assert names[:2] == ["attach0", "attach1"]
        assert len(out) <= 4

    def test_non_hybrid_mixes_by_distance(self):
        corpus = [(100.0, 0, self._meta("corpus_far"))]
        attach_scored = [(0, 0.5), (1, 2.0), (2, 50.0)]
        attach_metas = [self._meta(f"attach{i}") for i in range(3)]
        out = fuse_results(corpus, attach_scored, attach_metas, k=3, n_min=1, hybrid=False)
        names = [m["name"] for _, _, m in out]
        # Con n_min=1 se garantiza attach0; de los dos restantes attach1 (dist 2)
        # y attach2 (dist 50) ganan al corpus (dist 100).
        assert "attach0" in names
        assert "corpus_far" not in names
        assert len(out) == 3

    def test_hybrid_does_not_mix_scales(self):
        corpus = [(0.9, 0, self._meta("corpus_a")), (0.7, 1, self._meta("corpus_b"))]
        attach_scored = [(0, 0.1), (1, 0.2)]
        attach_metas = [self._meta(f"attach{i}") for i in range(2)]
        out = fuse_results(corpus, attach_scored, attach_metas, k=3, n_min=1, hybrid=True)
        names = [m["name"] for _, _, m in out]
        # El cupo del adjunto entra, el resto se llena con corpus en orden RRF
        # (mayor score primero), aunque el segundo chunk del adjunto tenga mejor
        # distancia que corpus_b.
        assert names[0] == "attach0"
        assert names[1:] == ["corpus_a", "corpus_b"]
        assert len(out) == 3

    def test_len_final_at_most_k(self):
        corpus = [(1.0, 0, self._meta("c"))]
        attach_scored = [(0, 0.1)]
        attach_metas = [self._meta("a")]
        out = fuse_results(corpus, attach_scored, attach_metas, k=5, n_min=10, hybrid=False)
        assert len(out) <= 5

    def test_rank_attachment_orders_by_distance(self):
        mat = np.array([[0.0, 0.0], [3.0, 4.0], [1.0, 1.0]], dtype="float32")
        qv = np.array([0.0, 0.0], dtype="float32")
        ranked = rank_attachment(qv, mat)
        idxs = [i for i, _ in ranked]
        assert idxs == [0, 2, 1]


class TestContentHash:
    def test_same_input_same_hash(self):
        cfg = {"target_chars": 1000, "overlap": 150, "model_embed": "bge-m3"}
        assert content_hash(b"hola", cfg) == content_hash(b"hola", cfg)

    def test_different_input_different_hash(self):
        cfg = {"target_chars": 1000, "overlap": 150, "model_embed": "bge-m3"}
        assert content_hash(b"hola", cfg) != content_hash(b"adios", cfg)


class TestBuildCiteMapUsesAttachmentKey:
    def test_prefers_underscore_cite(self):
        results = [
            (0.1, 0, {"paper_id": "2020_garcia_x", "_cite": "(mi nota; adjunto)"}),
            (0.2, 1, {"paper_id": "2015_reiter_review"}),
        ]
        cmap = build_cite_map(results, {})
        assert cmap[1] == "(mi nota; adjunto)"
        assert cmap[2] == "(Reiter, 2015)"
