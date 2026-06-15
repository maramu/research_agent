# -*- coding: utf-8 -*-
"""Tests de lógica pura para scripts/utils/citations.py (sin red ni FAISS)."""

from utils.citations import (
    citation_key,
    build_cite_map,
    apply_citations,
    strip_reference_section,
)


class TestCitationKey:
    def test_full_record_doi_year_authors(self):
        meta = {
            "2020_garcia_x": {
                "doi": "10.1000/xyz",
                "year": 2020,
                "authors": [{"full": "AnaGarcía", "forename": "", "surname": ""}],
            }
        }
        assert citation_key("2020_garcia_x", meta) == "(García, 2020; 10.1000/xyz)"

    def test_surname_field_priority(self):
        meta = {
            "2019_p": {
                "doi": "10.1/y",
                "year": 2019,
                "authors": [{"full": "X", "forename": "Joon", "surname": "lee"}],
            }
        }
        assert citation_key("2019_p", meta) == "(Lee, 2019; 10.1/y)"

    def test_no_doi(self):
        meta = {"2018_smith_a": {"year": 2018, "authors": []}}
        # sin autores -> fallback al paper_id
        assert citation_key("2018_smith_a", meta) == "(Smith, 2018)"

    def test_year_missing_uses_paper_id(self):
        assert citation_key("2015_reiter_review", {}) == "(Reiter, 2015)"

    def test_no_year_no_match(self):
        assert citation_key("sin-patron", {}) == "(?, s.f.)"


class TestApplyCitations:
    def test_single_and_grouped(self):
        cmap = {
            1: "(García, 2020; 10.x)",
            2: "(Lee, 2019; 10.y)",
            3: "(Smith, 2021; 10.z)",
        }
        out = apply_citations("usa A [1] y B [2][3].", cmap)
        assert out == (
            "usa A (García, 2020; 10.x) y B (Lee, 2019; 10.y; Smith, 2021; 10.z)."
        )

    def test_unknown_label_left_intact(self):
        cmap = {1: "(García, 2020; 10.x)"}
        out = apply_citations("dato [1] y otro [9].", cmap)
        assert "(García, 2020; 10.x)" in out
        assert "[9]" in out

    def test_grouped_with_space(self):
        cmap = {1: "(A, 2020)", 2: "(B, 2021)"}
        out = apply_citations("texto [1] [2] fin.", cmap)
        assert out == "texto (A, 2020; B, 2021) fin."


class TestStripReferenceSection:
    def test_removes_trailing_block(self):
        text = "Cuerpo del texto.\n\nReferencias:\n1. Algo et al. 2020.\n2. Otro 2019."
        assert strip_reference_section(text) == "Cuerpo del texto."

    def test_removes_markdown_heading(self):
        text = "Cuerpo.\n\n## Bibliografía\n- Algo 2020."
        assert strip_reference_section(text) == "Cuerpo."

    def test_no_block_unchanged(self):
        text = "Solo texto sin referencias."
        assert strip_reference_section(text) == text


class TestBuildCiteMap:
    def test_order_matches_context(self):
        results = [
            (0.1, 0, {"paper_id": "2020_garcia_x"}),
            (0.2, 1, {"paper_id": "2015_reiter_review"}),
        ]
        meta = {
            "2020_garcia_x": {"doi": "10.x", "year": 2020, "authors": []},
        }
        cmap = build_cite_map(results, meta)
        assert cmap[1] == "(Garcia, 2020; 10.x)"
        assert cmap[2] == "(Reiter, 2015)"
