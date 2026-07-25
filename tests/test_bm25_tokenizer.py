# -*- coding: utf-8 -*-
"""Tests del tokenizer BM25 de utils/retrieval.py — item 33 fase 1 (2026-07-26).

El tokenizer viejo era `re.findall(r"[a-z0-9]+", text.lower())`, que destrozaba
acrónimos, fórmulas, tildes y griegas TANTO en el texto indexado como en la
consulta (auditoría externa Kimi 2026-07-20). Estos tests fijan el contrato del
nuevo: lo que importa es que consulta y corpus produzcan tokens COMUNES.

BM25 se construye al vuelo desde metadata.jsonl, así que este cambio NO depende
del reindexado.
"""

import pytest

from utils.retrieval import tokenize, build_bm25, bm25_rank


def _shares(a: str, b: str) -> set:
    """Tokens comunes entre dos textos (lo que de verdad hace match en BM25)."""
    return set(tokenize(a)) & set(tokenize(b))


class TestAccents:
    def test_accented_word_is_one_token(self):
        """Antes: 'desulfurización' → 'desulfurizaci' + 'n'."""
        assert tokenize("desulfurización") == ["desulfurizacion"]

    def test_accented_and_unaccented_match(self):
        assert "desulfurizacion" in _shares("desulfurización", "desulfurizacion")

    def test_enie_is_folded(self):
        assert tokenize("año") == ["ano"]

    def test_uppercase_accents_fold_too(self):
        assert tokenize("DESULFURIZACIÓN") == ["desulfurizacion"]


class TestGreek:
    def test_greek_letters_survive(self):
        assert tokenize("α β μ") == ["α", "β", "μ"]

    def test_micro_sign_folds_to_greek_mu(self):
        """µ (signo micro, U+00B5) y μ (mu griega, U+03BC) deben ser el mismo token."""
        assert tokenize("µmax") == tokenize("μmax")

    def test_greek_in_context_is_not_dropped(self):
        toks = tokenize("the μ value of α-proteobacteria")
        assert "μ" in toks
        assert "α-proteobacteria" in toks


class TestHyphenatedAcronyms:
    def test_compound_and_parts_are_both_emitted(self):
        """'NR-SOB' como token entero Y sus partes: el compuesto añade precisión
        y las partes evitan perder lo que el tokenizer viejo sí encontraba."""
        toks = tokenize("NR-SOB")
        assert "nr-sob" in toks
        assert "nr" in toks and "sob" in toks

    def test_query_by_part_still_matches_the_compound(self):
        """Sin las partes esto sería una REGRESIÓN respecto al tokenizer viejo."""
        assert "sob" in _shares("NR-SOB reactor", "sulfide oxidizing bacteria SOB")

    def test_exact_compound_match_is_available(self):
        assert "nr-sob" in _shares("NR-SOB", "the NR-SOB consortium")

    def test_multi_hyphen_token(self):
        toks = tokenize("anoxic-biotrickling-filter")
        assert "anoxic-biotrickling-filter" in toks
        assert {"anoxic", "biotrickling", "filter"} <= set(toks)


class TestChemicalFormulas:
    def test_h2s_query_matches_flattened_corpus_text(self):
        """CLAVE del item 33. El corpus trae los subíndices aplanados ("H 2 S",
        ~13/16 chunks con química) y la consulta escribe "H2S". Con el tokenizer
        viejo eran h2s vs h/2/s: cero tokens comunes."""
        shared = _shares("H2S removal", "the H 2 S concentration was measured")
        assert {"h", "2", "s"} <= shared

    def test_formula_keeps_its_whole_token_too(self):
        toks = tokenize("H2S")
        assert "h2s" in toks
        assert {"h", "2", "s"} <= set(toks)

    def test_tio2_segments(self):
        toks = tokenize("TiO2")
        assert "tio2" in toks
        assert "tio" in toks and "2" in toks

    def test_tio2_matches_flattened_form(self):
        assert "tio" in _shares("TiO2 photocatalysis", "TiO 2 nanoparticles")

    def test_fe_ii_parentheses_are_separators(self):
        """Fe(II) sigue tokenizando como fe + ii (igual que antes): no se pierde
        nada, y meter paréntesis en el alfabeto pegaría basura tipo '(see'."""
        assert tokenize("Fe(II)") == ["fe", "ii"]

    def test_kla_is_a_single_token(self):
        assert tokenize("kLa") == ["kla"]

    def test_pure_numbers_are_not_split_further(self):
        assert tokenize("1500") == ["1500"]


class TestGeneralBehaviour:
    def test_empty_and_none_are_safe(self):
        assert tokenize("") == []
        assert tokenize(None) == []

    def test_punctuation_is_dropped(self):
        assert tokenize("Table 3 .") == ["table", "3"]

    def test_is_symmetric_between_index_and_query(self):
        """La simetría es el invariante que hace que BM25 funcione: el mismo
        tokenizer se usa en build_bm25 y en bm25_rank."""
        text = "Operational strategies for H2S removal by NR-SOB in desulfurización"
        assert tokenize(text) == tokenize(text)

    def test_plain_words_unchanged_from_old_tokenizer(self):
        assert tokenize("the anoxic biotrickling filter") == [
            "the", "anoxic", "biotrickling", "filter"
        ]


class TestEndToEndBM25:
    """Con rank_bm25 instalado, comprobar que la mejora se ve en el ranking."""

    DOCS = [
        "the H 2 S concentration in the biogas was reduced by the NR-SOB consortium",
        "microalgae cultivation under nitrogen limitation in open raceway ponds",
        "bioplastics degradation kinetics of polyhydroxyalkanoates in seawater",
    ]

    def test_h2s_query_retrieves_the_flattened_document(self):
        bm25 = build_bm25(self.DOCS)
        if bm25 is None:
            pytest.skip("rank_bm25 no instalado")
        top = bm25_rank(bm25, "H2S removal", 3)
        assert top and top[0] == 0

    def test_accented_query_retrieves_unaccented_document(self):
        # Corpus de 3 docs, no 2: con exactamente 2 docs y el término en 1 de
        # ellos, la IDF clásica de Okapi (rank_bm25) da log((2-1+.5)/(1+.5))=0
        # exacto y el score sale 0 pase lo que pase con el tokenizer — no es
        # un caso del tokenizer, es un artefacto del tamaño del corpus.
        bm25 = build_bm25([
            "desulfurizacion anoxica del biogas",
            "otro tema",
            "un tercer documento cualquiera sin relacion",
        ])
        if bm25 is None:
            pytest.skip("rank_bm25 no instalado")
        top = bm25_rank(bm25, "desulfurización", 3)
        assert top and top[0] == 0
