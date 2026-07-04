# -*- coding: utf-8 -*-
"""Tests de las heurísticas de validación de metadata (Nivel 1 y 2)."""
import json

import pytest

from utils.metadata_validation import (
    SIDECAR_MIN_SEVERITY,
    check_authors_affiliation,
    check_doi_format,
    check_glued_authors,
    check_title_eq_journal,
    check_title_starts_with_journal,
    check_year,
    compare_with_crossref,
    validate_category,
    validate_category_crossref,
    validate_record,
)


def _fetch(work):
    """Factoría de fetch inyectable determinista (offline)."""
    return lambda doi: work


def _write_jsonl(tmp_path, cat, rows):
    meta_dir = tmp_path / cat / "metadata"
    meta_dir.mkdir(parents=True)
    jsonl = meta_dir / "papers_metadata.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return tmp_path


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


def test_glued_authors_es_info():
    """authors_glued es informativo (no cuenta para el sidecar)."""
    issue = check_glued_authors({"authors": [{"full": "ViolaCorbellini"}]})
    assert issue["severity"] == "info"
    assert issue["severity"] not in SIDECAR_MIN_SEVERITY


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
    rows = [
        {"paper_id": "p1", "title": "Water Research", "journal": "Water Research",
         "year": 2020, "doi": "10.1016/j.watres.2020.1"},
        {"paper_id": "p2", "title": "Clean paper", "journal": "Water Research",
         "year": 2021, "doi": "10.1016/j.watres.2021.2",
         "authors": [{"forename": "Ana", "surname": "Lopez"}]},
    ]
    base = _write_jsonl(tmp_path, cat, rows)

    flagged = validate_category(cat, base)
    assert len(flagged) == 1
    assert flagged[0]["paper_id"] == "p1"
    assert flagged[0]["has_doi"] is True


def test_solo_glued_no_entra_al_sidecar(tmp_path):
    """Un paper cuyo ÚNICO issue es authors_glued (info) no entra al sidecar."""
    cat = "glued_only"
    rows = [
        {"paper_id": "g1", "title": "Anaerobic digestion of manure",
         "journal": "Bioresource Technology", "year": 2022,
         "doi": "10.1016/j.biortech.2022.1",
         "authors": [{"full": "ViolaCorbellini"}]},
    ]
    base = _write_jsonl(tmp_path, cat, rows)
    assert validate_category(cat, base) == []


def test_high_entra_y_lista_glued_info(tmp_path):
    """Un paper con title_eq_journal (high) entra, y su authors_glued (info)
    aparece listado dentro de sus issues."""
    cat = "high_plus_glued"
    rows = [
        {"paper_id": "h1", "title": "Water Research", "journal": "Water Research",
         "year": 2020, "doi": "10.1016/j.watres.2020.1",
         "authors": [{"full": "ViolaCorbellini"}]},
    ]
    base = _write_jsonl(tmp_path, cat, rows)
    flagged = validate_category(cat, base)
    assert len(flagged) == 1
    codes = {i["code"] for i in flagged[0]["issues"]}
    assert "title_eq_journal" in codes
    assert "authors_glued" in codes


# ── Nivel 2 — compare_with_crossref (fetch mockeado, offline) ────────────────

def _codes(issues):
    return {i["code"] for i in issues}


def test_crossref_title_recover():
    """Título marcado title_eq_journal por Nivel 1 → issue kind='recover'."""
    rec = {"paper_id": "p", "doi": "10.1016/j.watres.2020.1",
           "title": "Water Research", "journal": "Water Research"}
    work = {"title": "Anaerobic digestion of manure", "authors": [],
            "journal": "Water Research", "journal_short": "", "year": 2020}
    issues = compare_with_crossref(rec, fetch=_fetch(work))
    ti = [i for i in issues if i["code"] == "title_recover"]
    assert ti and ti[0]["kind"] == "recover"
    assert ti[0]["suggested"] == "Anaerobic digestion of manure"


def test_crossref_title_mismatch_y_match():
    """Ratio bajo → title_mismatch; ratio alto → sin issue de título."""
    doi = "10.1016/j.watres.2020.1"
    work_diff = {"title": "Completely unrelated subject heading", "authors": [],
                 "journal": "Water Research", "journal_short": "", "year": 2020}
    rec = {"paper_id": "p", "doi": doi, "title": "Anaerobic digestion of manure",
           "journal": "Water Research", "year": 2020}
    assert "title_mismatch" in _codes(compare_with_crossref(rec, fetch=_fetch(work_diff)))

    work_same = dict(work_diff, title="Anaerobic digestion of manure")
    assert "title_mismatch" not in _codes(compare_with_crossref(rec, fetch=_fetch(work_same)))


def test_crossref_journal_short_match_y_fill():
    """journal casa short-container-title → sin issue; stored vacío + cr → fill."""
    doi = "10.1016/j.watres.2020.1"
    work = {"title": "T", "authors": [], "journal": "Water Research",
            "journal_short": "Water Res", "year": 2020}
    rec_match = {"paper_id": "p", "doi": doi, "title": "T",
                 "journal": "Water Res", "year": 2020}
    assert "journal_mismatch" not in _codes(compare_with_crossref(rec_match, fetch=_fetch(work)))
    assert "journal_fill" not in _codes(compare_with_crossref(rec_match, fetch=_fetch(work)))

    rec_empty = {"paper_id": "p", "doi": doi, "title": "T", "journal": "", "year": 2020}
    fill = [i for i in compare_with_crossref(rec_empty, fetch=_fetch(work))
            if i["code"] == "journal_fill"]
    assert fill and fill[0]["kind"] == "fill"


def test_crossref_year_canonico_unica_fuente():
    """Con cr.year presente, la ÚNICA sugerencia de año es crossref (nunca
    paper_id, aunque el paper_id también difiera del local)."""
    rec = {"paper_id": "smith_1995_foo", "doi": "10.1016/j.watres.2046.1",
           "title": "T", "journal": "Water Research", "year": 2046}
    work = {"title": "T", "authors": [], "journal": "Water Research",
            "journal_short": "", "year": 2001}
    issues = [i for i in compare_with_crossref(rec, fetch=_fetch(work))
              if i["code"] == "year_mismatch"]
    assert len(issues) == 1
    assert issues[0]["suggested_source"] == "crossref"
    assert issues[0]["suggested"] == 2001


def test_crossref_year_igual_sin_issue():
    """cr.year == local (los 96 delta-0 del histograma) → sin year_mismatch."""
    rec = {"paper_id": "smith_2020_foo", "doi": "10.1016/j.watres.2020.1",
           "title": "T", "journal": "Water Research", "year": 2020}
    work = {"title": "T", "authors": [], "journal": "Water Research",
            "journal_short": "", "year": 2020}
    assert "year_mismatch" not in _codes(compare_with_crossref(rec, fetch=_fetch(work)))


def test_crossref_year_severidad_por_delta():
    """|delta|==1 (print/online) → severity low; |delta|>=2 → medium."""
    rec = {"paper_id": "p_2020_x", "doi": "10.1016/j.watres.2020.1",
           "title": "T", "journal": "Water Research", "year": 2020}
    work1 = {"title": "T", "authors": [], "journal": "Water Research",
             "journal_short": "", "year": 2021}
    ym1 = [i for i in compare_with_crossref(rec, fetch=_fetch(work1))
           if i["code"] == "year_mismatch"]
    assert ym1 and ym1[0]["severity"] == "low"
    assert ym1[0]["suggested_source"] == "crossref"

    work2 = dict(work1, year=2013)
    ym2 = [i for i in compare_with_crossref(rec, fetch=_fetch(work2))
           if i["code"] == "year_mismatch"]
    assert ym2 and ym2[0]["severity"] == "medium"


def test_crossref_year_fallback_paper_id_sin_cr_year():
    """cr resuelto pero SIN año → fallback: sugerencia desde paper_id."""
    rec = {"paper_id": "smith_1995_foo", "doi": "10.1016/j.watres.2046.1",
           "title": "T", "journal": "Water Research", "year": 2046}
    work = {"title": "T", "authors": [], "journal": "Water Research",
            "journal_short": "", "year": None}
    issues = [i for i in compare_with_crossref(rec, fetch=_fetch(work))
              if i["code"] == "year_mismatch"]
    assert len(issues) == 1
    assert issues[0]["suggested_source"] == "paper_id"
    assert issues[0]["suggested"] == 1995


def test_crossref_miss_no_peta():
    """fetch → None ⇒ crossref_miss (info) sin excepción; sin año en paper_id
    no se añade fallback."""
    rec = {"paper_id": "p", "doi": "10.1016/j.watres.2020.1", "title": "T"}
    issues = compare_with_crossref(rec, fetch=_fetch(None))
    assert len(issues) == 1 and issues[0]["code"] == "crossref_miss"
    assert issues[0]["severity"] == "info"


def test_crossref_miss_con_fallback_paper_id():
    """fetch → None y año local ≠ paper_id → crossref_miss + year_mismatch
    source paper_id (la señal sigue viva para papers que Crossref no resuelve)."""
    rec = {"paper_id": "smith_1995_foo", "doi": "10.1016/j.watres.2046.1",
           "title": "T", "year": 2046}
    issues = compare_with_crossref(rec, fetch=_fetch(None))
    assert _codes(issues) == {"crossref_miss", "year_mismatch"}
    ym = [i for i in issues if i["code"] == "year_mismatch"][0]
    assert ym["suggested_source"] == "paper_id" and ym["suggested"] == 1995


def test_crossref_authors_mismatch_incompleto():
    """Autores con forename/surname vacíos (solo full) → authors_mismatch con
    suggested = lista limpia de Crossref."""
    rec = {"paper_id": "p", "doi": "10.1016/j.watres.2020.1", "title": "T",
           "journal": "Water Research", "year": 2020,
           "authors": [{"full": "ViolaCorbellini", "forename": "", "surname": ""}]}
    work = {"title": "T", "journal": "Water Research", "journal_short": "", "year": 2020,
            "authors": [{"family": "Corbellini", "given": "Viola"}]}
    am = [i for i in compare_with_crossref(rec, fetch=_fetch(work))
          if i["code"] == "authors_mismatch"]
    assert am and am[0]["kind"] == "mismatch"
    assert "Corbellini" in am[0]["suggested"]


def test_crossref_sin_doi_o_malformado_vacio():
    """Sin DOI o DOI malformado → [] (Nivel 1 gestiona el malformado)."""
    assert compare_with_crossref({"paper_id": "p", "doi": ""}, fetch=_fetch({})) == []
    assert compare_with_crossref({"paper_id": "p", "doi": "j.x"}, fetch=_fetch({})) == []


def test_validate_category_crossref_entra_por_mismatch(tmp_path):
    """Un paper limpio en Nivel 1 pero con mismatch Crossref entra al sidecar
    con su bloque crossref."""
    cat = "l2"
    rows = [
        {"paper_id": "p1", "doi": "10.1016/j.watres.2020.1",
         "title": "Anaerobic digestion of manure", "journal": "Water Research",
         "year": 2020, "authors": [{"forename": "Ana", "surname": "Lopez"}]},
    ]
    base = _write_jsonl(tmp_path, cat, rows)
    work = {"title": "A totally different title string", "authors": [],
            "journal": "Water Research", "journal_short": "", "year": 2020}
    flagged = validate_category_crossref(cat, base, fetch=_fetch(work))
    assert len(flagged) == 1
    assert flagged[0]["crossref"]["fetched"] is True
    assert "title_mismatch" in _codes(flagged[0]["crossref"]["issues"])


def test_validate_category_crossref_limit(tmp_path):
    """--limit topa las llamadas: con limit=1 solo el primer paper trae bloque."""
    cat = "l2lim"
    rows = [
        {"paper_id": "p1", "doi": "10.1016/j.watres.2020.1", "title": "T1",
         "journal": "Water Research", "year": 2020},
        {"paper_id": "p2", "doi": "10.1016/j.watres.2021.2", "title": "T2",
         "journal": "Water Research", "year": 2021},
    ]
    base = _write_jsonl(tmp_path, cat, rows)
    work = {"title": "Different heading entirely here", "authors": [],
            "journal": "Water Research", "journal_short": "", "year": 2020}
    calls = {"n": 0}

    def counting_fetch(doi):
        calls["n"] += 1
        return work

    validate_category_crossref(cat, base, limit=1, fetch=counting_fetch)
    assert calls["n"] == 1
