# -*- coding: utf-8 -*-
"""Blinda la coherencia entre _CANON_PATTERNS (3_process_corpus) y
CANONICAL_SECTIONS (utils/constants). El test es el guard real de sincronía;
ver también el comentario junto a _CANON_PATTERNS en 3_process_corpus.py."""

import importlib.util
import sys
from pathlib import Path

import pytest

from utils.constants import CANONICAL_SECTIONS

_MODULE_NAME = "process_corpus_3"
_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "3_process_corpus.py"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
_process_corpus = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _process_corpus
_spec.loader.exec_module(_process_corpus)


class TestCanonicalSectionsCoherence:
    def test_patterns_plus_fallbacks_cover_constant(self):
        """Los 6 patrones + "other" + "table" deben cubrir exactamente CANONICAL_SECTIONS."""
        from_patterns = {canon for canon, _ in _process_corpus._CANON_PATTERNS}
        covered = from_patterns | {"other", "table"}
        assert covered == set(CANONICAL_SECTIONS), (
            f"Desajuste: en _CANON_PATTERNS+fallbacks pero no en CANONICAL_SECTIONS: "
            f"{covered - set(CANONICAL_SECTIONS)}; "
            f"en CANONICAL_SECTIONS pero no cubiertos: "
            f"{set(CANONICAL_SECTIONS) - covered}"
        )

    @pytest.mark.parametrize("title,expected_canon", [
        ("Abstract",                 "abstract"),
        ("Introduction",             "introduction"),
        ("Materials and Methods",    "methods"),
        ("Results",                  "results"),
        ("Conclusions",              "conclusion"),
        ("Acknowledgements",         "other"),
    ])
    def test_canonical_section_output_in_constant(self, title, expected_canon):
        """canonical_section() devuelve siempre un valor de CANONICAL_SECTIONS."""
        result = _process_corpus.canonical_section(title)
        assert result in set(CANONICAL_SECTIONS), (
            f"canonical_section({title!r}) → {result!r} no está en CANONICAL_SECTIONS"
        )
        assert result == expected_canon, (
            f"canonical_section({title!r}) → {result!r}, esperado {expected_canon!r}"
        )
