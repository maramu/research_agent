# -*- coding: utf-8 -*-
"""Tests de scripts/utils/download_registry.py — snooze de DOIs pendientes.

Todos los tests redirigen download_registry.REGISTRY_PATH a un CSV temporal
(tmp_path) vía monkeypatch: nunca tocan el NAS real.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from utils import download_registry as dr


@pytest.fixture(autouse=True)
def _tmp_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "REGISTRY_PATH", tmp_path / "pendientes_descarga.csv")
    yield


def _row(doi="10.x/test", status="pending", snooze_until="", **extra):
    row = {
        "doi": doi, "title": "t", "year": "2024", "category": "cat",
        "landing_url": f"https://doi.org/{doi}", "status": status,
        "reason": "", "last_checked": "2024-01-01", "notes": "",
        "snooze_until": snooze_until,
    }
    row.update(extra)
    return row


class TestPendingActive:
    def test_pending_no_snooze_included(self):
        df = pd.DataFrame([_row(status="pending", snooze_until="")])
        result = dr.pending_active(df, today=date(2026, 1, 1))
        assert len(result) == 1

    def test_pending_future_snooze_excluded(self):
        future = (date(2026, 1, 1) + timedelta(days=400)).isoformat()
        df = pd.DataFrame([_row(status="pending", snooze_until=future)])
        result = dr.pending_active(df, today=date(2026, 1, 1))
        assert result.empty

    def test_pending_expired_snooze_included(self):
        past = (date(2026, 1, 1) - timedelta(days=1)).isoformat()
        df = pd.DataFrame([_row(status="pending", snooze_until=past)])
        result = dr.pending_active(df, today=date(2026, 1, 1))
        assert len(result) == 1

    def test_downloaded_excluded(self):
        df = pd.DataFrame([_row(status="downloaded", snooze_until="")])
        result = dr.pending_active(df, today=date(2026, 1, 1))
        assert result.empty


class TestSnoozeUnsnooze:
    def test_snooze_sets_future_date_keeps_pending_status(self):
        df = pd.DataFrame([_row(doi="10.x/test")])
        dr.save(df)

        affected = dr.snooze(["10.x/test"], years=2)
        assert affected == 1

        reloaded = dr.load()
        row = reloaded[reloaded["doi"] == "10.x/test"].iloc[0]
        assert row["status"] == "pending"
        parsed = date.fromisoformat(row["snooze_until"])
        assert parsed > date.today() + timedelta(days=729)

    def test_unsnooze_clears_snooze_until(self):
        future = (date.today() + timedelta(days=730)).isoformat()
        df = pd.DataFrame([_row(doi="10.x/test", snooze_until=future)])
        dr.save(df)

        affected = dr.unsnooze(["10.x/test"])
        assert affected == 1

        reloaded = dr.load()
        row = reloaded[reloaded["doi"] == "10.x/test"].iloc[0]
        assert row["snooze_until"] == ""


class TestMigration:
    def test_load_backfills_missing_snooze_until_column(self, tmp_path):
        old_cols = [
            "doi", "title", "year", "category",
            "landing_url", "status", "reason", "last_checked", "notes",
        ]
        df_old = pd.DataFrame([{
            "doi": "10.x/old", "title": "t", "year": "2023", "category": "cat",
            "landing_url": "https://doi.org/10.x/old", "status": "pending",
            "reason": "", "last_checked": "2023-01-01", "notes": "",
        }])[old_cols]
        df_old.to_csv(dr.REGISTRY_PATH, index=False, encoding="utf-8-sig")

        reloaded = dr.load()
        assert "snooze_until" in reloaded.columns
        assert reloaded.iloc[0]["snooze_until"] == ""


class TestUpsertSnoozeSafe:
    def test_upsert_does_not_clear_snooze_until(self):
        future = (date.today() + timedelta(days=730)).isoformat()
        df = pd.DataFrame([_row(doi="10.x/test", snooze_until=future)])
        dr.save(df)

        dr.upsert([{"doi": "10.x/test", "reason": "nuevo error"}])

        reloaded = dr.load()
        row = reloaded[reloaded["doi"] == "10.x/test"].iloc[0]
        assert row["snooze_until"] == future
        assert row["status"] == "pending"
        assert row["reason"] == "nuevo error"
