# -*- coding: utf-8 -*-
"""Tests de regresión para scripts/utils/pdf_utils.py."""

import pytest

from utils.pdf_utils import (
    DOI_REGEX,
    _clean_doi,
    extract_doi_from_text,
    normalize_stem,
    slugify,
    strip_accents,
)


class TestDOIRegex:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("10.1000/xyz", "10.1000/xyz"),
            ("DOI: 10.1016/j.biortech.2023.129348", "10.1016/j.biortech.2023.129348"),
            ("see 10.1021/es011412n for details", "10.1021/es011412n"),
            ("<10.1021/es011412n>", "10.1021/es011412n"),
            ("(10.1021/es011412n)", "10.1021/es011412n"),
            ("https://doi.org/10.1000/abc", "10.1000/abc"),
            ("10.1002/aic.690470228", "10.1002/aic.690470228"),
        ],
    )
    def test_regex_matches(self, text, expected):
        assert expected in DOI_REGEX.findall(text)

    def test_regex_longest_match(self):
        assert "10.1016/j.biortech.2023.129348" in DOI_REGEX.findall(
            "10.1016/j.biortech.2023.129348."
        )

    def test_regex_no_false_positive(self):
        assert DOI_REGEX.findall("...solo números 10.1234 y una barra /x.") == []


class TestCleanDoi:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("10.1016/j.biortech.2023.129348", "10.1016/j.biortech.2023.129348"),
            ("  10.1016/j.biortech.2023.129348  ", "10.1016/j.biortech.2023.129348"),
            ("10.1016/j.biortech.2023.129348.", "10.1016/j.biortech.2023.129348"),
            ("10.1016/j.biortech.2023.129348,", "10.1016/j.biortech.2023.129348"),
            ("10.1016/j.biortech.2023.129348;", "10.1016/j.biortech.2023.129348"),
            ("10.1016/j.biortech.2023.129348)", "10.1016/j.biortech.2023.129348"),
            ("10.1016/j.biortech.2023.129348]", "10.1016/j.biortech.2023.129348"),
            ("(10.1016/j.biortech.2023.129348)", "10.1016/j.biortech.2023.129348"),
            ("<10.1016/j.biortech.2023.129348>", "10.1016/j.biortech.2023.129348"),
            # basura pegada (comportamiento INTENCIONADO):
            ("10.1016/j.biortech.2023.129348Abstract", "10.1016/j.biortech.2023.129348"),
            ("10.1000/example2within", "10.1000/example2"),
            ("10.1000/example-AB", "10.1000/example-AB"),
            ("10.1000/example-ABC", "10.1000/example-A"),
            ("10.1021/es011412-Gwithin", "10.1021/es011412-G"),
            # BUG conocido: _clean_doi recorta sufijos legítimos de 3+ letras (item 44)
            pytest.param(
                "10.1000/xyz",
                "10.1000/xyz",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason="_clean_doi recorta sufijos legítimos de 3+ letras (item 44)",
                ),
            ),
        ],
    )
    def test_clean(self, raw, expected):
        assert _clean_doi(raw) == expected


class TestExtractDoiFromText:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("DOI: 10.1016/j.biortech.2023.129348", "10.1016/j.biortech.2023.129348"),
            (
                "https://doi.org/10.1016/j.biortech.2023.129348",
                "10.1016/j.biortech.2023.129348",
            ),
            ("<10.1016/j.biortech.2023.129348>.", "10.1016/j.biortech.2023.129348"),
            (
                "The article 10.1021/es011412-Gwithin is cited.",
                "10.1021/es011412-G",
            ),
        ],
    )
    def test_extract(self, text, expected):
        assert extract_doi_from_text(text) == expected

    def test_extract_none(self):
        assert extract_doi_from_text("no hay doi aquí") is None


class TestSlugify:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Anaerobic Digestion", "anaerobic_digestion"),
            ("M&W Systems", "m_and_w_systems"),
            ("señor     josé", "senor_jose"),
        ],
    )
    def test_slugify(self, text, expected):
        assert slugify(text) == expected


class TestStripAccents:
    def test_strip(self):
        assert strip_accents("señor josé") == "senor jose"
        assert strip_accents("ﬁle") == "file"


class TestNormalizeStem:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("file name", "file_name"),
            ("file-name", "file_name"),
            ("file.name", "file_name"),
            ("file,name", "file_name"),
            ("File Name", "file_name"),
            ("__file__name__", "file_name"),
            ("ﬁle_name", "file_name"),
            ("10. 2012-06 A...", "10_2012_06_a"),
            ("Purification, Upgrading", "purification_upgrading"),
            ("fe_ii_-persulfate", "fe_ii_persulfate"),
        ],
    )
    def test_normalize_stem(self, raw, expected):
        assert normalize_stem(raw) == expected

    def test_empty(self):
        assert normalize_stem("") == ""

    def test_only_separators(self):
        assert normalize_stem("   ---...,,,   ") == ""
