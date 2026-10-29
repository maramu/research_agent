# -*- coding: utf-8 -*-
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "backup_config_t", Path(__file__).resolve().parents[1] / "scripts" / "backup_config.py")
bc = importlib.util.module_from_spec(_spec); sys.modules["backup_config_t"] = bc
_spec.loader.exec_module(bc)


def _mundo(tmp_path):
    repo, research = tmp_path / "repo", tmp_path / "research"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "keywords.yml").write_text("a: 1\n")
    (repo / "config" / ".env").write_text("SECRETO=1\n")             # NO debe copiarse
    (repo / "config" / ".env.example").write_text("X=\n")            # glob *.example no casa con ".env.example"... ver test
    (research / "metadatos").mkdir(parents=True)
    (research / "metadatos" / "doi_manual.xlsx").write_bytes(b"xlsx")
    (research / "categorias" / "c1" / "metadata").mkdir(parents=True)
    (research / "categorias" / "c1" / "metadata" / "papers_metadata.jsonl").write_text("{}\n")
    return repo, research


def test_collect_no_incluye_el_env_real(tmp_path):
    repo, research = _mundo(tmp_path)
    src = bc.collect_sources(repo, research)
    assert "config/keywords.yml" in src and "metadatos/doi_manual.xlsx" in src
    assert "categorias/c1/metadata/papers_metadata.jsonl" in src
    assert not any(k.endswith("/.env") or k == "config/.env" for k in src)


def test_snapshot_solo_si_hay_cambios_y_rota(tmp_path):
    repo, research = _mundo(tmp_path)
    dest = tmp_path / "bk"
    t0 = datetime(2026, 10, 29, 10, 0, 0)
    s1 = bc.snapshot(bc.collect_sources(repo, research), dest, keep=2, now=t0)
    assert s1 and (s1 / "config" / "keywords.yml").read_text() == "a: 1\n"
    assert json.loads((s1 / "MANIFEST.json").read_text())["files"]["config/keywords.yml"]["bytes"] == 5
    assert bc.snapshot(bc.collect_sources(repo, research), dest, keep=2, now=t0 + timedelta(minutes=1)) is None
    (repo / "config" / "keywords.yml").write_text("a: 2\n")
    s2 = bc.snapshot(bc.collect_sources(repo, research), dest, keep=2, now=t0 + timedelta(minutes=2))
    (repo / "config" / "keywords.yml").write_text("a: 3\n")
    s3 = bc.snapshot(bc.collect_sources(repo, research), dest, keep=2, now=t0 + timedelta(minutes=3))
    names = [d.name for d in bc.list_snapshots(dest)]
    assert s2 and s3 and len(names) == 2 and s1.name not in names        # solo las 2 últimas
