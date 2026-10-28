# -*- coding: utf-8 -*-
"""Tests de scripts/9_cleanup_duplicates.py — renombrado de papers ya
procesados (item 68): build_new_paper_id() y rename_paper().

A diferencia de 1_rename_papers_by_doi.py (que solo renombra el PDF, antes
de que existan TEI/md_clean/chunks), rename_paper() opera sobre un paper YA
PROCESADO y debe tocar atómicamente todos los sitios donde vive su
paper_id, o un reproceso posterior lo trataría como huérfano (ver item 66).

Todo en tmp_path — nunca toca /Volumes/research/. validation_overrides se
redirige a un CSV temporal vía monkeypatch.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_NAME = "cleanup_duplicates_9_rename_test"
_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "9_cleanup_duplicates.py"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
cleanup = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = cleanup
_spec.loader.exec_module(cleanup)

from utils import validation_overrides as vo  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(vo, "OVERRIDES_PATH", tmp_path / "validation_overrides.csv")
    yield


def _make_processed_paper(base: Path, category: str, paper_id: str, rec: dict,
                          with_embeddings: bool = True) -> Path:
    """Crea en `base/category` todos los artefactos de un paper ya procesado
    (pdf/tei/md_clean/chunks/summaries/per_paper/papers_metadata.jsonl/
    references.jsonl) y, opcionalmente, un índice de embeddings de juguete."""
    proj = base / category
    for d in ("pdfs", "tei", "md_clean", "chunks", "summaries", "metadata/per_paper"):
        (proj / d).mkdir(parents=True, exist_ok=True)

    (proj / "pdfs" / f"{paper_id}.pdf").write_bytes(b"%PDF-1.4 fake")
    (proj / "tei" / f"{paper_id}.tei.xml").write_text("<x/>")
    (proj / "md_clean" / f"{paper_id}.clean.md").write_text("contenido " * 50)
    (proj / "summaries" / f"{paper_id}.summary.md").write_text("resumen")
    chunks = [{"paper_id": paper_id, "section": "intro", "text": "hola"},
              {"paper_id": paper_id, "section": "methods", "text": "mundo"}]
    (proj / "chunks" / f"{paper_id}.chunks.jsonl").write_text(
        "\n".join(json.dumps(c) for c in chunks) + "\n")
    (proj / "metadata" / "per_paper" / f"{paper_id}.metadata.json").write_text(
        json.dumps(rec, indent=2))
    (proj / "metadata" / "per_paper" / f"{paper_id}.references.json").write_text("[]")
    (proj / "metadata" / "papers_metadata.jsonl").write_text(json.dumps(rec) + "\n")
    refs = [{"paper_id": paper_id, "title": "Ref 1"}]
    (proj / "metadata" / "references.jsonl").write_text(
        "\n".join(json.dumps(r) for r in refs) + "\n")

    if with_embeddings:
        emb_dir = proj / "embeddings" / "all__bge-m3"
        emb_dir.mkdir(parents=True, exist_ok=True)
        emb_rows = [{"paper_id": paper_id, "section": "intro", "text": "hola"}]
        (emb_dir / "metadata.jsonl").write_text(
            "\n".join(json.dumps(r) for r in emb_rows) + "\n")
        (emb_dir / "indexed_papers.json").write_text(
            json.dumps({"paper_ids": [paper_id, "otro_paper_sin_tocar"], "model": "bge-m3"}))

    return proj


_REC = {
    "paper_id": "2020_smith_original_messy_name",
    "stable_id": "2020_smith_original_messy_name",
    "title": "A Great Paper About Biogas",
    "doi": None,
    "year": 2020,
    "authors": [{"full": "Jane Smith", "forename": "Jane", "surname": "Smith"}],
    "tei_file": "placeholder",
}


class TestBuildNewPaperId:
    def test_canonical_scheme(self):
        new_id = cleanup.build_new_paper_id(_REC)
        assert new_id == "2020_smith_great_paper_about_biogas"

    def test_falls_back_when_fields_missing(self):
        new_id = cleanup.build_new_paper_id({})
        assert new_id.startswith("0000_unknownauthor_")

    def test_surname_from_full_when_structured_missing(self):
        rec = dict(_REC, authors=[{"full": "Jane Smith"}])
        new_id = cleanup.build_new_paper_id(rec)
        assert new_id.startswith("2020_smith_")

    def test_already_renamed_recognizes_scheme(self):
        """1_rename_papers_by_doi.py debe saltar el resultado en el futuro."""
        import re
        new_id = cleanup.build_new_paper_id(_REC)
        assert re.match(r"^\d{4}_[a-z0-9]+_.+\.pdf$", f"{new_id}.pdf".lower())


class TestRenamePaper:
    def test_noop_when_same_id(self, tmp_path):
        result = cleanup.rename_paper("catA", "same_id", "same_id", tmp_path)
        assert result["skipped"] == "mismo nombre"
        assert result["files_renamed"] == []

    def test_full_rename_updates_every_touch_point(self, tmp_path):
        old_id = _REC["paper_id"]
        rec = dict(_REC, tei_file=str(tmp_path / "catA" / "tei" / f"{old_id}.tei.xml"))
        proj = _make_processed_paper(tmp_path, "catA", old_id, rec)
        vo.dismiss("catA", old_id, "year", note="verificado a mano")

        new_id = cleanup.build_new_paper_id(rec)
        result = cleanup.rename_paper("catA", old_id, new_id, tmp_path)

        assert result["new_id"] == new_id
        # 1) ficheros renombrados, nada del nombre viejo sobrevive
        assert not list(proj.rglob(f"*{old_id}*"))
        assert (proj / "pdfs" / f"{new_id}.pdf").exists()
        assert (proj / "tei" / f"{new_id}.tei.xml").exists()
        assert (proj / "md_clean" / f"{new_id}.clean.md").exists()
        assert (proj / "summaries" / f"{new_id}.summary.md").exists()
        assert (proj / "chunks" / f"{new_id}.chunks.jsonl").exists()
        assert (proj / "metadata" / "per_paper" / f"{new_id}.metadata.json").exists()

        # 2) per_paper metadata.json parcheado (paper_id/stable_id/tei_file)
        per_paper_new = json.loads(
            (proj / "metadata" / "per_paper" / f"{new_id}.metadata.json").read_text())
        assert per_paper_new["paper_id"] == new_id
        assert per_paper_new["stable_id"] == new_id
        assert new_id in per_paper_new["tei_file"]

        # 3) papers_metadata.jsonl: una sola línea, con el id nuevo
        meta_lines = (proj / "metadata" / "papers_metadata.jsonl").read_text().strip().splitlines()
        assert len(meta_lines) == 1
        meta = json.loads(meta_lines[0])
        assert meta["paper_id"] == new_id
        assert meta["stable_id"] == new_id

        # 4) references.jsonl
        refs = [json.loads(l) for l in
                (proj / "metadata" / "references.jsonl").read_text().strip().splitlines()]
        assert all(r["paper_id"] == new_id for r in refs)

        # 5) campo interno "paper_id" de cada chunk (no solo el filename)
        chunks = [json.loads(l) for l in
                  (proj / "chunks" / f"{new_id}.chunks.jsonl").read_text().strip().splitlines()]
        assert all(c["paper_id"] == new_id for c in chunks)

        # 6) embeddings/*/metadata.jsonl + indexed_papers.json — sin tocar
        #    al otro paper que ya estaba indexado
        emb_dir = proj / "embeddings" / "all__bge-m3"
        emb_rows = [json.loads(l) for l in
                    (emb_dir / "metadata.jsonl").read_text().strip().splitlines()]
        assert all(r["paper_id"] == new_id for r in emb_rows)
        idx_data = json.loads((emb_dir / "indexed_papers.json").read_text())
        assert old_id not in idx_data["paper_ids"]
        assert new_id in idx_data["paper_ids"]
        assert "otro_paper_sin_tocar" in idx_data["paper_ids"]

        # 7) validation_overrides.csv
        df = vo.load()
        assert (df[df["category"] == "catA"]["paper_id"] == new_id).all()

        # El índice FAISS (index.faiss) no existe en este fixture — a
        # propósito: rename_paper() no debe tocarlo ni requerirlo.

    def test_aborts_without_touching_anything_on_collision(self, tmp_path):
        old_id, new_id = "paper_old", "paper_new"
        proj = tmp_path / "catA"
        (proj / "pdfs").mkdir(parents=True)
        (proj / "pdfs" / f"{old_id}.pdf").write_bytes(b"old content")
        (proj / "pdfs" / f"{new_id}.pdf").write_bytes(b"COLLISION, do not touch")

        with pytest.raises(FileExistsError):
            cleanup.rename_paper("catA", old_id, new_id, tmp_path)

        assert (proj / "pdfs" / f"{old_id}.pdf").read_bytes() == b"old content"
        assert (proj / "pdfs" / f"{new_id}.pdf").read_bytes() == b"COLLISION, do not touch"

    def test_rename_then_reextract_is_consistent(self, tmp_path):
        """Reproduce el reproceso real tras un renombrado: 4_extract_metadata.py
        no debe generar huérfanos ni duplicar la línea de metadata."""
        import subprocess

        old_id = "2020_smith_original_messy_name"
        tei_xml = (
            '<?xml version="1.0"?>'
            '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>'
            '<titleStmt><title>A Great Paper About Biogas</title>'
            '<author><persName><forename>Jane</forename><surname>Smith</surname>'
            '</persName></author></titleStmt>'
            '<sourceDesc><biblStruct><monogr><title level="j">Bioresource Technology</title>'
            '<imprint><date when="2020"/></imprint></monogr></biblStruct></sourceDesc>'
            '</fileDesc></teiHeader><text><body></body></text></TEI>'
        )
        proj = tmp_path / "catA"
        for d in ("pdfs", "tei", "md_clean", "metadata/per_paper"):
            (proj / d).mkdir(parents=True, exist_ok=True)
        (proj / "tei" / f"{old_id}.tei.xml").write_text(tei_xml)
        (proj / "md_clean" / f"{old_id}.clean.md").write_text("contenido " * 1000)
        (proj / "pdfs" / f"{old_id}.pdf").write_bytes(b"%PDF-1.4 fake")

        rec = {
            "project": "catA", "phase": "p1", "paper_id": old_id, "stable_id": old_id,
            "title": "A Great Paper About Biogas", "doi": None,
            "journal": "Bioresource Technology", "year": 2020,
            "authors": [{"full": "Jane Smith", "forename": "Jane", "surname": "Smith"}],
            "abstract": None, "highlights": [], "n_references": 0,
            "tei_file": str(proj / "tei" / f"{old_id}.tei.xml"), "source_pdf": None,
            "processed_date": "2026-01-01", "source_type": "manual",
            "download_source": "unknown", "download_url": None, "access_type": "unknown",
            "download_date": None, "quality_score": 0.9, "warnings": [],
        }
        (proj / "metadata" / "per_paper" / f"{old_id}.metadata.json").write_text(
            json.dumps(rec, indent=2))
        (proj / "metadata" / "per_paper" / f"{old_id}.references.json").write_text("[]")
        (proj / "metadata" / "papers_metadata.jsonl").write_text(json.dumps(rec) + "\n")

        new_id = cleanup.build_new_paper_id(rec)
        cleanup.rename_paper("catA", old_id, new_id, tmp_path)

        script = Path(__file__).resolve().parents[1] / "scripts" / "4_extract_metadata.py"
        result = subprocess.run(
            [sys.executable, str(script), "--project", "catA", "--base", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

        meta_lines = (proj / "metadata" / "papers_metadata.jsonl").read_text().strip().splitlines()
        assert len(meta_lines) == 1, "huérfano o duplicado tras reprocesar"
        assert json.loads(meta_lines[0])["paper_id"] == new_id
        assert not list(proj.rglob(f"*{old_id}*")), "quedó rastro del nombre viejo"


def test_candidate_paths_encuentra_pdf_con_stem_truncado(tmp_path):
    """Regresión: stem truncado ('..._Thiobacil_10_108') vs PDF con nombre
    largo y DOI entre corchetes. Antes el PDF quedaba huérfano al borrar."""
    proj = tmp_path / "thiosulfate"
    (proj / "pdfs").mkdir(parents=True)
    stem = ("2004_Alcántara_S_Sulfur_formation_by_steady_state_continuous_"
            "cultures_of_a_sulfoxidizing_consortium_and_Thiobacil_10_108")
    pdf = proj / "pdfs" / ("2004 - Alcántara S - Sulfur formation by steady-state "
                           "continuous cultures of a sulfoxidizing consortium and "
                           "Thiobacil [10.1080_09593332508618381].pdf")
    otro = proj / "pdfs" / "2004 - Otro A - Sulfur formation unrelated paper [10.1_x].pdf"
    pdf.write_bytes(b"%PDF"); otro.write_bytes(b"%PDF")
    found = cleanup.candidate_paths(proj, stem)
    assert pdf in found and otro not in found


def test_purge_quarantine_manifest_borra_solo_dentro_de_cuarentena(tmp_path):
    qroot = tmp_path / "quarantine"
    dest = qroot / "deleted" / "20260101_000000" / "cat"
    (dest / "tei").mkdir(parents=True)
    f = dest / "tei" / "p.tei.xml"; f.write_text("x")
    fuera = tmp_path / "categorias" / "cat" / "pdfs" / "p.pdf"
    fuera.parent.mkdir(parents=True); fuera.write_text("x")
    mp = dest / "_manifest_p.json"
    mp.write_text(json.dumps({"category": "cat", "paper_id": "p",
                              "moved": [["/o", str(f)], ["/o2", str(fuera)]],
                              "meta_lines": []}))
    assert cleanup.purge_quarantine_manifest(mp, qroot) == 1
    assert not f.exists() and not mp.exists()
    assert fuera.exists()
    assert not (qroot / "deleted" / "20260101_000000").exists()
    assert qroot.exists()


def test_quarantine_quita_references_y_restore_las_devuelve(tmp_path):
    base = tmp_path / "categorias"; proj = base / "cat"
    (proj / "metadata").mkdir(parents=True); (proj / "pdfs").mkdir()
    meta = {"paper_id": "p_uno", "title": "T", "doi": "10.1/x"}
    (proj / "metadata" / "papers_metadata.jsonl").write_text(json.dumps(meta) + "\n")
    r1 = json.dumps({"ref_key": "a", "paper_id": "p_uno"})
    r2 = json.dumps({"ref_key": "b", "paper_id": "p_otro"})
    refs = proj / "metadata" / "references.jsonl"
    refs.write_text(r1 + "\n" + r2 + "\n")
    dest = tmp_path / "q" / "ts"
    cleanup.quarantine_paper("cat", "p_uno", base, dest)
    assert refs.read_text().splitlines() == [r2]
    man = dest / "cat" / "_manifest_p_uno.json"
    assert json.loads(man.read_text())["refs_lines"] == [r1]
    cleanup.restore_from_quarantine(man, base)
    assert set(refs.read_text().splitlines()) == {r1, r2}


def test_screen_no_aparta_pdf_ya_procesado_con_nombre_largo(tmp_path, monkeypatch):
    """Regresión item 71: el PDF de un paper ya procesado (nombre largo con
    [doi], paper_id truncado) NO debe tomarse por 'nuevo' y salir a cuarentena
    por 'DOI ya en corpus' (su propio DOI)."""
    import pipeline
    cat = "c"
    base = tmp_path / "categorias"
    (base / cat / "pdfs").mkdir(parents=True); (base / cat / "md_clean").mkdir()
    pid = ("2025_Karimi_T_Isolation_and_characterization_of_sulfur_oxidizing_"
           "bacteria_at_the_Ilam_gas_refinery_in_Iran_10_22104_AET_")
    (base / cat / "md_clean" / f"{pid}.clean.md").write_text("x")
    proc = base / cat / "pdfs" / ("2025 - Karimi T - Isolation and characterization of "
                                  "sulfur-oxidizing bacteria at the Ilam gas refinery in "
                                  "Iran [10.22104_AET.2025.7467.2081].pdf")
    nuevo = base / cat / "pdfs" / "nuevo_dup.pdf"
    proc.write_bytes(b"%PDF-a"); nuevo.write_bytes(b"%PDF-b")
    monkeypatch.setattr(pipeline, "CATEGORIAS_DIR", base)
    monkeypatch.setattr(pipeline, "QUARANTINE_DIR", tmp_path / "q")
    monkeypatch.setattr(pipeline, "_load_corpus_doi_index", lambda: {"10.1/x": f"{cat}/{pid}"})
    import utils.pdf_utils as pu
    monkeypatch.setattr(pu, "extract_doi_from_pdf",
                        lambda p: "10.1/x" if Path(p).name == "nuevo_dup.pdf" else "10.1/x")
    res = pipeline.screen_new_pdfs_against_corpus(cat)
    assert proc.exists()                       # el procesado se queda
    assert [q["file"] for q in res["quarantined"]] == ["nuevo_dup.pdf"]
