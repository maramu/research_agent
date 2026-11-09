# -*- coding: utf-8 -*-
import pytest

from utils.csv_ingest import normalize_screened_csv, project_name_from_filename


def test_nombre_proyecto():
    assert project_name_from_filename("Seleccion_RAG_VOSC_60.csv") == "seleccion_rag_vosc_60"
    assert project_name_from_filename("/x/Selección  RAG (v2).CSV") == "seleccion_rag_v2"
    assert project_name_from_filename("***.csv") == "csv_adhoc"


def test_csv_espanol_y_dedup():
    raw = ("n,titulo,autores,anio,revista,DOI\n"
           "1,A,Lin S.,2018,WR,https://doi.org/10.1016/J.X.1\n"
           "2,B,Lee,2019,WR,10.1016/j.x.1\n"      # duplicado del 1
           "3,C,Ko,2020,WR,\n").encode("utf-8-sig")
    df, rep = normalize_screened_csv(raw)
    assert list(df["DOI"]) == ["10.1016/j.x.1"]
    assert rep.n_rows == 3 and rep.n_no_doi == 1 and rep.n_duplicates == 1 and rep.n_valid == 1
    assert {"Title", "Year", "Authors", "Source title"} <= set(df.columns)


def test_csv_scopus_original_semicolon():
    raw = "Authors;Title;Year;DOI\nX;T;2020;10.1016/abc\n".encode()
    df, rep = normalize_screened_csv(raw)
    assert df.loc[0, "Title"] == "T" and rep.n_valid == 1


def test_sin_doi_falla():
    with pytest.raises(ValueError):
        normalize_screened_csv(b"titulo,anio\nA,2020\n")
