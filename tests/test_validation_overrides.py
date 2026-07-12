# -*- coding: utf-8 -*-
"""Tests de scripts/utils/validation_overrides.py — "mantener campo, no
volver a sugerir" para la validación de metadata (Crossref).

Todos los tests redirigen validation_overrides.OVERRIDES_PATH a un CSV
temporal (tmp_path) vía monkeypatch: nunca tocan el NAS real.
"""
import pytest

from utils import validation_overrides as vo


@pytest.fixture(autouse=True)
def _tmp_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(vo, "OVERRIDES_PATH", tmp_path / "validation_overrides.csv")
    yield


class TestDismissUndismiss:
    def test_dismiss_adds_to_dismissed_set(self):
        affected = vo.dismiss("cat1", "p1", "year", note="rechazada")
        assert affected == 1
        assert ("p1", "year") in vo.dismissed_set("cat1")

    def test_dismiss_invalid_field_rejected(self):
        affected = vo.dismiss("cat1", "p1", "not_a_real_field")
        assert affected == 0
        assert vo.dismissed_set("cat1") == set()

    def test_dismiss_doi_accepted(self):
        # "doi" cubre el aviso crossref_miss (DOI correcto no resuelto en
        # Crossref) — mantenerlo silencia el aviso sin tocar el valor del DOI.
        affected = vo.dismiss("cat1", "p1", "doi", note="miss confirmado ok")
        assert affected == 1
        assert ("p1", "doi") in vo.dismissed_set("cat1")

    def test_dismiss_is_idempotent_upsert(self):
        vo.dismiss("cat1", "p1", "year", note="primero")
        vo.dismiss("cat1", "p1", "year", note="segundo")
        df = vo.load()
        rows = df[(df["category"] == "cat1") & (df["paper_id"] == "p1")
                  & (df["field"] == "year")]
        assert len(rows) == 1
        assert rows.iloc[0]["note"] == "segundo"

    def test_undismiss_removes_from_set(self):
        vo.dismiss("cat1", "p1", "authors")
        assert ("p1", "authors") in vo.dismissed_set("cat1")
        affected = vo.undismiss("cat1", "p1", "authors")
        assert affected == 1
        assert ("p1", "authors") not in vo.dismissed_set("cat1")

    def test_undismiss_missing_row_returns_zero(self):
        assert vo.undismiss("cat1", "ghost", "year") == 0

    def test_categories_are_isolated(self):
        vo.dismiss("cat1", "p1", "title")
        assert ("p1", "title") in vo.dismissed_set("cat1")
        assert ("p1", "title") not in vo.dismissed_set("cat2")


class TestListDismissed:
    def test_list_dismissed_scoped_to_category(self):
        vo.dismiss("cat1", "p1", "title", note="a")
        vo.dismiss("cat2", "p2", "year", note="b")
        df = vo.list_dismissed("cat1")
        assert list(df["paper_id"]) == ["p1"]
        assert df.iloc[0]["note"] == "a"

    def test_list_dismissed_empty(self):
        df = vo.list_dismissed("cat1")
        assert df.empty
