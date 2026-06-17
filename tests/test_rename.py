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
