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


class TestReconcileWithCorpus:
    """DOIs 'pending' que ya están en algún papers_metadata.jsonl del corpus
    (ingesta fuera de 3a_download_pdfs.py, p.ej. subida manual) deben pasar
    a 'downloaded' sin intervención manual."""

    def _write_corpus(self, tmp_path, category, dois):
        import json
        meta_dir = tmp_path / category / "metadata"
        meta_dir.mkdir(parents=True)
        jsonl = meta_dir / "papers_metadata.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            for i, doi in enumerate(dois):
                f.write(json.dumps({"paper_id": f"p{i}", "doi": doi}) + "\n")

    def test_pending_doi_ya_en_corpus_se_marca_downloaded(self, tmp_path, monkeypatch):
        from utils.constants import CANONICAL_CATEGORIES
        cat = CANONICAL_CATEGORIES[0]
        self._write_corpus(tmp_path, cat, ["10.1016/j.wasman.2026.115484"])

        df = pd.DataFrame([_row(doi="10.1016/j.wasman.2026.115484")])
        dr.save(df)

        affected = dr.reconcile_with_corpus(categorias_dir=tmp_path)
        assert affected == 1

        reloaded = dr.load()
        row = reloaded[reloaded["doi"] == "10.1016/j.wasman.2026.115484"].iloc[0]
        assert row["status"] == "downloaded"

    def test_pending_doi_ausente_del_corpus_no_cambia(self, tmp_path, monkeypatch):
        from utils.constants import CANONICAL_CATEGORIES
        cat = CANONICAL_CATEGORIES[0]
        self._write_corpus(tmp_path, cat, ["10.1016/otro.doi"])

        df = pd.DataFrame([_row(doi="10.1016/j.wasman.2026.115484")])
        dr.save(df)

        affected = dr.reconcile_with_corpus(categorias_dir=tmp_path)
        assert affected == 0

        reloaded = dr.load()
        row = reloaded[reloaded["doi"] == "10.1016/j.wasman.2026.115484"].iloc[0]
        assert row["status"] == "pending"

    def test_reconcile_es_case_insensitive(self, tmp_path):
        from utils.constants import CANONICAL_CATEGORIES
        cat = CANONICAL_CATEGORIES[0]
        self._write_corpus(tmp_path, cat, ["10.1016/J.WASMAN.2026.115484"])

        df = pd.DataFrame([_row(doi="10.1016/j.wasman.2026.115484")])
        dr.save(df)

        affected = dr.reconcile_with_corpus(categorias_dir=tmp_path)
        assert affected == 1

    def test_reconcile_no_toca_snooze_ni_downloaded_previos(self, tmp_path):
        from utils.constants import CANONICAL_CATEGORIES
        cat = CANONICAL_CATEGORIES[0]
        self._write_corpus(tmp_path, cat, ["10.1016/ya.descargado"])

        df = pd.DataFrame([
            _row(doi="10.1016/ya.descargado", status="downloaded"),
            _row(doi="10.1016/pospuesto", snooze_until="2099-01-01"),
        ])
        dr.save(df)

        affected = dr.reconcile_with_corpus(categorias_dir=tmp_path)
        assert affected == 0
        reloaded = dr.load()
        pospuesto = reloaded[reloaded["doi"] == "10.1016/pospuesto"].iloc[0]
        assert pospuesto["snooze_until"] == "2099-01-01"
        assert pospuesto["status"] == "pending"


class TestBlockUnblock:
    """Veto persistente: status='blocked'. Un DOI vetado no debe volver a
    intentarse (3a_download_pdfs.py) ni salir en el email semanal."""

    def test_block_actualiza_fila_existente(self):
        dr.save(pd.DataFrame([_row(doi="10.x/test")]))

        assert dr.block(["10.x/test"], reason="fuera de alcance") == 1

        row = dr.load().iloc[0]
        assert row["status"] == "blocked"
        assert row["reason"] == "fuera de alcance"

    def test_block_preserva_el_snooze_previo(self):
        """Vetar y reactivar un DOI pospuesto debe devolverlo a su aplazamiento,
        no al email semanal: 'blocked' ya lo excluye de pending_active() sin
        necesidad de limpiar snooze_until, y unblock() no sabría restaurarlo."""
        future = (date.today() + timedelta(days=730)).isoformat()
        dr.save(pd.DataFrame([_row(doi="10.x/test", snooze_until=future)]))

        dr.block(["10.x/test"], reason="fuera de alcance")
        assert dr.load().iloc[0]["snooze_until"] == future

        dr.unblock(["10.x/test"])

        row = dr.load().iloc[0]
        assert row["status"] == "pending"
        assert row["snooze_until"] == future
        assert dr.pending_active(dr.load()).empty   # sigue pospuesto, no reaparece

    def test_block_inserta_doi_ausente_del_registro(self):
        """Un DOI que se descargó bien nunca pasa por upsert(): al vetarlo hay
        que crear la fila."""
        dr.save(pd.DataFrame(columns=dr._COLS))

        assert dr.block(
            ["10.x/nuevo"], reason="retractado",
            rows=[{"doi": "10.x/nuevo", "title": "T", "year": "2026", "category": "cat"}],
        ) == 1

        row = dr.load().iloc[0]
        assert row["status"] == "blocked"
        assert row["title"] == "T"
        assert row["category"] == "cat"

    def test_block_es_case_insensitive(self):
        dr.save(pd.DataFrame([_row(doi="10.X/Test")]))

        assert dr.block(["10.x/test"]) == 1
        assert len(dr.load()) == 1          # no duplica la fila
        assert dr.load().iloc[0]["status"] == "blocked"

    def test_blocked_no_sale_en_pending_active(self):
        dr.save(pd.DataFrame([_row(doi="10.x/test")]))
        dr.block(["10.x/test"])

        assert dr.pending_active(dr.load()).empty

    def test_upsert_no_pisa_el_veto(self):
        """'blocked' está en _RESOLVED: el upsert semanal no debe machacar
        el motivo del veto con el error de descarga de turno."""
        dr.save(pd.DataFrame([_row(doi="10.x/test")]))
        dr.block(["10.x/test"], reason="fuera de alcance")

        dr.upsert([{"doi": "10.x/test", "reason": "403 Forbidden"}])

        row = dr.load().iloc[0]
        assert row["status"] == "blocked"
        assert row["reason"] == "fuera de alcance"

    def test_blocked_dois_normaliza_a_minusculas(self):
        dr.save(pd.DataFrame([
            _row(doi="10.X/Uno", status="blocked"),
            _row(doi="10.x/dos", status="pending"),
        ]))

        assert dr.blocked_dois() == {"10.x/uno"}

    def test_unblock_devuelve_a_pending(self):
        dr.save(pd.DataFrame([_row(doi="10.x/test", status="blocked")]))

        assert dr.unblock(["10.X/TEST"]) == 1

        row = dr.load().iloc[0]
        assert row["status"] == "pending"
        assert dr.blocked_dois() == set()

    def test_unblock_ignora_filas_no_vetadas(self):
        dr.save(pd.DataFrame([_row(doi="10.x/test", status="downloaded")]))

        assert dr.unblock(["10.x/test"]) == 0
        assert dr.load().iloc[0]["status"] == "downloaded"


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
