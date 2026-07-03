# -*- coding: utf-8 -*-
"""Tests de las heurísticas de validación de metadata (Nivel 1)."""
import json

import pytest

from utils.metadata_validation import (
    check_authors_affiliation,
    check_doi_format,
    check_glued_authors,
    check_title_eq_journal,
    check_title_starts_with_journal,
    check_year,
    validate_category,
    validate_record,
)


# ── title == journal ───────────────────────────────────────────────────────

def test_title_eq_journal_caza():
    rec = {"title": "Bioresource Technology", "journal": "Bioresource Technology"}
    issue = check_title_eq_journal(rec)
    assert issue and issue["code"] == "title_eq_journal"


def test_title_limpio_no_caza():
    rec = {"title": "Anaerobic digestion of manure",
           "journal": "Bioresource Technology"}
    assert check_title_eq_journal(rec) is None


def test_title_prefijo_revista_caza():
    rec = {"title": "Bioresource Technology anaerobic digestion of manure",
           "journal": "Bioresource Technology"}
    issue = check_title_starts_with_journal(rec)
    assert issue and issue["code"] == "title_has_journal_prefix"


# ── autores pegados (camelCase) ─────────────────────────────────────────────

def test_glued_authors_caza():
    rec = {"authors": [{"full": "ViolaCorbellini"}]}
    issue = check_glued_authors(rec)
    assert issue and issue["code"] == "authors_glued"


def test_author_con_espacio_no_caza():
    rec = {"authors": [{"forename": "Viola", "surname": "Corbellini"}]}
    assert check_glued_authors(rec) is None


# ── autores contaminados con afiliación/dígitos ─────────────────────────────

def test_author_afiliacion_caza():
    rec = {"authors": [{"full": "Technical University of Denmark"}]}
    issue = check_authors_affiliation(rec)
    assert issue and issue["code"] == "authors_affiliation"


def test_author_pais_mayusculas_caza():
    rec = {"authors": [{"full": "Kongens Lyngby DENMARK"}]}
    assert check_authors_affiliation(rec) is not None


def test_author_con_digito_caza():
    rec = {"authors": [{"full": "John Smith2"}]}
    assert check_authors_affiliation(rec) is not None


def test_author_normal_no_caza_afiliacion():
    rec = {"authors": [{"forename": "John", "surname": "Smith"}]}
    assert check_authors_affiliation(rec) is None


# ── año ─────────────────────────────────────────────────────────────────────

def test_year_1700_caza():
    assert check_year({"year": 1700}) is not None


def test_year_ausente_caza():
    assert check_year({}) is not None


def test_year_valido_no_caza():
    assert check_year({"year": 2024}) is None


# ── DOI ─────────────────────────────────────────────────────────────────────

def test_doi_valido_no_caza():
    assert check_doi_format({"doi": "10.1016/j.x"}) is None


def test_doi_malformado_caza():
    issue = check_doi_format({"doi": "j.x"})
    assert issue and issue["code"] == "doi_malformed"


def test_doi_ausente_no_genera_issue():
    assert check_doi_format({"doi": ""}) is None
    assert check_doi_format({}) is None


# ── integración ─────────────────────────────────────────────────────────────

def test_validate_record_acumula():
    rec = {"title": "J", "journal": "J", "year": 1700, "doi": "bad"}
    codes = {i["code"] for i in validate_record(rec)}
    assert {"title_eq_journal", "year_implausible", "doi_malformed"} <= codes


def test_registro_limpio_sin_issues():
    rec = {"title": "Anaerobic digestion", "journal": "Bioresource Technology",
           "year": 2024, "doi": "10.1016/j.biortech.2024.001",
           "authors": [{"forename": "Viola", "surname": "Corbellini"}]}
    assert validate_record(rec) == []


def test_validate_category_sidecar(tmp_path):
    cat = "toy_cat"
    meta_dir = tmp_path / cat / "metadata"
    meta_dir.mkdir(parents=True)
    jsonl = meta_dir / "papers_metadata.jsonl"
    rows = [
        {"paper_id": "p1", "title": "Water Research", "journal": "Water Research",
         "year": 2020, "doi": "10.1016/j.watres.2020.1"},
        {"paper_id": "p2", "title": "Clean paper", "journal": "Water Research",
         "year": 2021, "doi": "10.1016/j.watres.2021.2",
         "authors": [{"forename": "Ana", "surname": "Lopez"}]},
    ]
    with jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    flagged = validate_category(cat, tmp_path)
    assert len(flagged) == 1
    assert flagged[0]["paper_id"] == "p1"
    assert flagged[0]["has_doi"] is True
