# -*- coding: utf-8 -*-
"""Tests de regresión para shorten_title y sanitize_filename de 1_rename_papers_by_doi.py."""

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_NAME = "rename_papers_by_doi_1"
_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "1_rename_papers_by_doi.py"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
_rename = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _rename
_spec.loader.exec_module(_rename)

shorten_title = _rename.shorten_title
sanitize_filename = _rename.sanitize_filename


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
