# -*- coding: utf-8 -*-
"""Tests de regresión para shorten_title y sanitize_filename (fuente única: utils/pdf_utils.py)."""

import pytest

from utils.pdf_utils import sanitize_filename, shorten_title


class TestShortenTitle:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Anaerobic digestion of microalgae", "anaerobic_digestion_microalgae"),
            ("gas-liquid mass transfer", "gas_liquid_mass_transfer"),
            ("Purificación de aguas", "purificacion_aguas"),
            ("The use of a novel reactor", "novel_reactor"),
            ("a an the", "a_an_the"),
        ],
    )
    def test_shorten(self, title, expected):
        assert shorten_title(title, max_words=8) == expected

    def test_max_words(self):
        assert shorten_title("one two three four five six", max_words=3) == "one_two_three"


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("file<name>.pdf", "file_name_.pdf"),
            ("file:name|?*.pdf", "file_name_.pdf"),
            ("my__file.pdf", "my_file.pdf"),
            ("  my_file.pdf  ", "my_file.pdf"),
            ("my_file.txt", "my_file.txt"),
        ],
    )
    def test_sanitize(self, name, expected):
        assert sanitize_filename(name) == expected

    def test_truncate(self):
        result = sanitize_filename("a" * 200 + ".pdf", max_len=50)
        assert len(result) <= 50
        assert result.endswith(".pdf")


def test_rename_no_crea_sufijo_2_si_es_el_mismo_paper(tmp_path):
    """Un PDF cuyo nombre canónico ya existe con contenido idéntico es un duplicado
    intra-categoría: no debe generar `_2`."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "rename_mod", Path(__file__).resolve().parents[1] / "scripts" / "1_rename_papers_by_doi.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    a = tmp_path / "a.pdf"; b = tmp_path / "b.pdf"; c = tmp_path / "c.pdf"
    a.write_bytes(b"%PDF-1"); b.write_bytes(b"%PDF-1"); c.write_bytes(b"%PDF-2")
    assert m.find_same_paper_in_folder(a, b, "10.1/x") == "PDF idéntico ya en la categoría"
    assert m.find_same_paper_in_folder(tmp_path / "no.pdf", b, "10.1/x") is None
