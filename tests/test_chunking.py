# -*- coding: utf-8 -*-
"""Tests del chunker de 3_process_corpus.py — items 62 y 63 (2026-07-26).

Unitarios y sin datos vivos: construyen TEI/Markdown mínimos en memoria y no
tocan /Volumes/research/ ni GROBID ni Ollama.

Cubre:
  62.1 el título del paper (H1) ya no clasifica secciones;
  62.2 fusión de los bloques de portada sin contenido propio;
  63.1 una fila de tabla = un párrafo;
  63.2 el fallback del splitter respeta los saltos de línea;
  63.3 heading + caption en TODAS las partes de una tabla troceada.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_NAME = "process_corpus_3_chunking"
_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "3_process_corpus.py"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
_pc = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _pc
_spec.loader.exec_module(_pc)

MAX_EMBED_CHARS = _pc.MAX_EMBED_CHARS

_TEI_HEAD = '<TEI xmlns="http://www.tei-c.org/ns/1.0">'


def _tei_table(head: str, desc: str, rows: list) -> str:
    """TEI mínimo con una <figure type="table">. rows[0] es la cabecera."""
    row_xml = []
    for cells in rows:
        cells_xml = "".join(f"<cell>{c}</cell>" for c in cells)
        row_xml.append(f"<row>{cells_xml}</row>")
    return (
        f'{_TEI_HEAD}<text><body><figure type="table" xml:id="tab_0">'
        f"<head>{head}</head><figDesc>{desc}</figDesc>"
        f'<table>{"".join(row_xml)}</table>'
        f"</figure></body></text></TEI>"
    )


def _records(md_clean: str, tables: list) -> list:
    """build_chunk_records con los parámetros de producción y rutas ficticias."""
    return _pc.build_chunk_records(
        md_clean,
        tables,
        phase="test_phase",
        paper_id="2025_test_paper",
        paper_title="T",
        source_pdf=Path("/dev/null/x.pdf"),
        source_tei=Path("/dev/null/x.tei.xml"),
        source_md_clean=Path("/dev/null/x.clean.md"),
        target_words=850,
        overlap_words=120,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Item 63.1 — una fila = un párrafo
# ═══════════════════════════════════════════════════════════════════════════

class TestTableRowsAsParagraphs:
    def test_three_rows_produce_three_paragraphs(self):
        tei = _tei_table(
            "Table 1 .", "Operating conditions",
            [["Study", "pH"], ["Soreanu 2010", "7.0"],
             ["Baspinar 2011", "7.5"], ["Chinalia 2012", "8.0"]],
        )
        tables = _pc.extract_tables_md(tei)
        assert len(tables) == 1

        paras = [p for p in tables[0]["body_md"].split("\n\n") if p.strip()]
        assert len(paras) == 3, f"esperaba 3 párrafos de fila, hay {len(paras)}: {paras}"
        assert all(p.startswith("- ") for p in paras)
        assert "Soreanu 2010" in paras[0] and "Baspinar 2011" in paras[1]

    def test_rows_are_not_joined_by_single_newline(self):
        """La causa raíz del item 63: filas pegadas con un solo \\n."""
        tei = _tei_table("Table 2 .", "", [["A", "B"], ["1", "2"], ["3", "4"]])
        body = _pc.extract_tables_md(tei)[0]["body_md"]
        assert "\n\n" in body
        # Ninguna frontera de fila queda como salto simple.
        assert not any(
            seg.startswith("- ")
            for line in body.split("\n\n")
            for seg in line.split("\n")[1:]
        )

    def test_exp_branch_also_splits_rows(self):
        """La rama CON columna "Exp." también emite una fila por párrafo."""
        tei = _tei_table(
            "Table 3 .", "",
            [["Exp.", "pH", "Load"],
             ["E1", "7.0", "10"], ["", "7.1", "11"],
             ["E2", "8.0", "20"]],
        )
        body = _pc.extract_tables_md(tei)[0]["body_md"]
        paras = [p for p in body.split("\n\n") if p.strip()]
        # 2 cabeceras de experimento + 3 filas de datos.
        assert sum(1 for p in paras if p.startswith("**Experiment")) == 2
        assert sum(1 for p in paras if p.startswith("- ")) == 3
        assert all("\n" not in p for p in paras if p.startswith("- "))


# ═══════════════════════════════════════════════════════════════════════════
# Items 63.1 + 63.3 — troceado de una tabla grande
# ═══════════════════════════════════════════════════════════════════════════

class TestLargeTableSplitting:
    @staticmethod
    def _big_table_records():
        # Filas suficientemente largas para superar MAX_EMBED_CHARS en conjunto.
        rows = [["Study", "Detail"]]
        for i in range(80):
            rows.append([f"Study_{i:03d}_2011", f"pH 7.{i % 10} " + "x" * 200])
        tei = _tei_table("Table 4 .", "Comparison of reported conditions", rows)
        tables = _pc.extract_tables_md(tei)
        assert len(tables[0]["text"]) > MAX_EMBED_CHARS, "la tabla de prueba no supera el tope"
        return tables, _records("# T\n\n## Results\n\nTexto.\n", tables)

    def test_splits_into_several_parts_all_within_budget(self):
        _tables, recs = self._big_table_records()
        parts = [r for r in recs if r["type"] == "table"]
        assert len(parts) > 1, "la tabla debería trocearse en varias partes"
        assert all(len(r["text"]) <= MAX_EMBED_CHARS for r in parts)

    def test_no_row_is_cut_in_half(self):
        """Ninguna fila queda partida ni fusionada con otra (item 63)."""
        _tables, recs = self._big_table_records()
        parts = [r for r in recs if r["type"] == "table"]

        seen = []
        for r in parts:
            for para in r["text"].split("\n\n"):
                if para.startswith("- "):
                    seen.append(para)

        # Cada fila aparece completa y una sola vez, con un único "Study:".
        assert len(seen) == 80, f"esperaba 80 filas intactas, hay {len(seen)}"
        for para in seen:
            assert para.count("Study:") == 1, f"filas fusionadas: {para[:120]}"
            assert para.count("Detail:") == 1
        ids = [p.split("Study:")[1].split("|")[0].strip() for p in seen]
        assert len(set(ids)) == 80

    def test_every_part_starts_with_heading_and_caption(self):
        """Item 63.3: TODAS las partes llevan el ancla, no solo la primera."""
        _tables, recs = self._big_table_records()
        parts = [r for r in recs if r["type"] == "table"]
        for r in parts:
            assert r["text"].startswith("### Table 4 ."), r["text"][:80]
            assert "*Comparison of reported conditions*" in r["text"][:120]

    def test_section_part_starts_at_one(self):
        _tables, recs = self._big_table_records()
        parts = [r for r in recs if r["type"] == "table"]
        assert [r["section_part"] for r in parts] == list(range(1, len(parts) + 1))

    def test_chunk_index_is_consecutive_across_text_and_tables(self):
        _tables, recs = self._big_table_records()
        assert [r["chunk_index"] for r in recs] == list(range(1, len(recs) + 1))


# ═══════════════════════════════════════════════════════════════════════════
# Item 63.2 — el fallback del splitter respeta los saltos de línea
# ═══════════════════════════════════════════════════════════════════════════

class TestSplitToMaxCharsRespectsNewlines:
    def test_emergency_branch_keeps_line_boundaries(self):
        # Un ÚNICO párrafo (sin \n\n) cuyas líneas son filas: es el caso que
        # antes caía a `para.split()` y destruía las fronteras.
        lines = [f"- Study: S{i:02d} | pH: 7.{i % 10}" for i in range(60)]
        para = "\n".join(lines)
        out = _pc._split_to_max_chars(para, 300)

        assert len(out) > 1
        assert all(len(p) <= 300 for p in out)
        recovered = [ln for piece in out for ln in piece.split("\n")]
        assert recovered == lines, "el fallback alteró las fronteras de línea"

    def test_falls_back_to_words_only_inside_an_oversized_line(self):
        long_line = " ".join(f"w{i}" for i in range(200))
        out = _pc._split_to_max_chars(long_line, 100)
        assert all(len(p) <= 100 for p in out)
        assert " ".join(out).split() == long_line.split()

    def test_atomic_token_larger_than_max_is_hard_cut(self):
        out = _pc._split_to_max_chars("x" * 250, 100)
        assert [len(p) for p in out] == [100, 100, 50]
        assert "".join(out) == "x" * 250

    def test_short_text_is_returned_untouched(self):
        assert _pc._split_to_max_chars("corto", 100) == ["corto"]
        assert _pc._split_to_max_chars("   ", 100) == []


# ═══════════════════════════════════════════════════════════════════════════
# Item 62.1 — el título del paper ya no clasifica
# ═══════════════════════════════════════════════════════════════════════════

class TestTitleDoesNotLeakSectionLabel:
    # Título real del corpus (2025_brito): "Operational" casaba con el patrón
    # de methods y etiquetaba la portada como methods.
    TITLE = ("Operational strategies for biogas desulfurization in an "
             "anoxic biotrickling filter")

    def test_preamble_block_is_not_labelled_methods(self):
        md = (
            f"# {self.TITLE}\n\n"
            "**Authors:** J Brito; C Frade-González; F Almenglo\n\n"
            "**Year: 2025 | DOI: 10.1016/j.biortech.2025.132439**\n\n"
            "## Abstract\n\n"
            + "Resumen del trabajo con contenido suficiente. " * 12 + "\n"
        )
        recs = _records(md, [])
        first = recs[0]
        assert first["section_canonical"] != "methods", (
            f"el título sigue clasificando: {first['section_canonical']}"
        )

    def test_level_two_headings_still_classify(self):
        """El fix NO se pasa de largo: los H2 del cuerpo siguen clasificando."""
        md = (
            "# Some Neutral Paper Title\n\n"
            "## Materials and Methods\n\n" + "Detalle experimental. " * 30 + "\n\n"
            "## Results\n\n" + "Resultados medidos. " * 30 + "\n\n"
            "## Conclusions\n\n" + "Cierre del trabajo. " * 30 + "\n"
        )
        recs = _records(md, [])
        by_section = {r["section"]: r["section_canonical"] for r in recs}
        assert by_section["Materials and Methods"] == "methods"
        assert by_section["Results"] == "results"
        assert by_section["Conclusions"] == "conclusion"

    def test_descriptive_subsection_under_operational_title_falls_to_other(self):
        """El alcance real del 62.1: una subsección que no clasifica por sí misma
        ya no hereda la etiqueta del TÍTULO por el ascenso de ancestros."""
        md = (
            f"# {self.TITLE}\n\n"
            "## Site description\n\n" + "Descripción del emplazamiento. " * 30 + "\n"
        )
        recs = _records(md, [])
        target = [r for r in recs if r["section"] == "Site description"]
        assert target, "no se generó el chunk de la subsección"
        assert all(r["section_canonical"] == "other" for r in target), (
            f"heredó del título: {target[0]['section_canonical']}"
        )

    def test_canonical_section_itself_is_unchanged(self):
        """canonical_section() no se toca: el fix está en quién la llama."""
        assert _pc.canonical_section(self.TITLE) == "methods"
        assert _pc.canonical_section("Materials and Methods") == "methods"


# ═══════════════════════════════════════════════════════════════════════════
# Item 62.2 — fusión de las portadas vacías
# ═══════════════════════════════════════════════════════════════════════════

class TestCoverResidue:
    def test_metadata_only_block_has_tiny_residue(self):
        text = ("**Authors:** J Brito; C Frade-González\n\n"
                "**Year: 2025 | DOI: 10.1016/j.biortech.2025.132439**")
        assert _pc.cover_residue_chars(text) == 0

    def test_doi_only_variant_is_also_stripped(self):
        text = "**Authors:** A B\n\n**DOI: 10.1000/xyz**"
        assert _pc.cover_residue_chars(text) == 0

    def test_block_without_authors_line_is_not_a_cover(self):
        assert _pc.cover_residue_chars("Texto normal de una sección.") is None

    def test_mixed_block_keeps_its_prose(self):
        prose = "Contenido real de la portada con prosa propia. " * 6   # >= 200
        residue = _pc.cover_residue_chars(f"**Authors:** A B\n\n{prose}")
        assert residue >= _pc.COVER_PROSE_MIN_CHARS


class TestCoverMerge:
    COVER = ("**Authors:** J Brito; C Frade-González; F Almenglo\n\n"
             "**Year: 2025 | DOI: 10.1016/j.biortech.2025.132439**")

    @staticmethod
    def _piece(text, section="S", canon="other", part=1):
        return {"section": section, "section_canonical": canon,
                "section_part": part, "text": text}

    def test_merges_and_inherits_next_section_canonical(self):
        pieces = [
            self._piece(self.COVER, section="Título", canon="other"),
            self._piece("Cuerpo del abstract.", section="Abstract", canon="abstract"),
        ]
        out = _pc.merge_empty_cover_blocks(pieces)
        assert len(out) == 1
        assert self.COVER in out[0]["text"] and "Cuerpo del abstract." in out[0]["text"]
        assert out[0]["section_canonical"] == "abstract"
        assert out[0]["section"] == "Abstract"

    def test_does_not_merge_when_residue_is_large(self):
        prose = "Prosa propia de la portada, con contenido de verdad. " * 6
        pieces = [
            self._piece(f"**Authors:** A B\n\n{prose}"),
            self._piece("Siguiente.", section="Abstract", canon="abstract"),
        ]
        out = _pc.merge_empty_cover_blocks(pieces)
        assert len(out) == 2
        assert out[0]["section_canonical"] == "other"

    def test_emits_as_is_when_there_is_no_next_chunk(self):
        pieces = [self._piece(self.COVER)]
        out = _pc.merge_empty_cover_blocks(pieces)
        assert len(out) == 1
        assert out[0]["text"] == self.COVER

    def test_does_not_merge_when_result_would_exceed_max(self):
        big = "y" * (MAX_EMBED_CHARS - 10)
        pieces = [self._piece(self.COVER), self._piece(big, canon="abstract")]
        out = _pc.merge_empty_cover_blocks(pieces)
        assert len(out) == 2, "no debe fusionar si se pasa de MAX_EMBED_CHARS"
        assert len(out[1]["text"]) == len(big)

    def test_non_cover_pieces_are_untouched(self):
        pieces = [self._piece("Uno."), self._piece("Dos."), self._piece("Tres.")]
        out = _pc.merge_empty_cover_blocks(pieces)
        assert [p["text"] for p in out] == ["Uno.", "Dos.", "Tres."]


class TestCoverMergeEndToEnd:
    def test_cover_disappears_and_chunk_index_is_renumbered(self):
        md = (
            "# Operational strategies for anoxic biodesulfurization\n\n"
            "**Authors:** J Brito; C Frade-González\n\n"
            "**Year: 2025 | DOI: 10.1016/j.biortech.2025.132439**\n\n"
            "## Abstract\n\n" + "Resumen del trabajo. " * 30 + "\n\n"
            "## Materials and Methods\n\n" + "Montaje experimental. " * 30 + "\n"
        )
        recs = _records(md, [])

        # chunk_index consecutivo desde 1 tras la fusión.
        assert [r["chunk_index"] for r in recs] == list(range(1, len(recs) + 1))

        # No queda ningún chunk que sea solo metadata de portada.
        empties = [r for r in recs
                   if (_pc.cover_residue_chars(r["text"]) or 0) < _pc.COVER_PROSE_MIN_CHARS
                   and _pc.cover_residue_chars(r["text"]) is not None]
        assert not empties, f"quedan portadas vacías: {empties}"

        # Los autores siguen siendo recuperables, dentro del chunk fusionado.
        assert any("**Authors:**" in r["text"] for r in recs)
        merged = next(r for r in recs if "**Authors:**" in r["text"])
        assert merged["section_canonical"] == "abstract"

    def test_paper_with_only_a_cover_still_produces_its_chunk(self):
        md = ("# Some Title\n\n"
              "**Authors:** A B\n\n"
              "**Year: 2020 | DOI: 10.1000/xyz**\n")
        recs = _records(md, [])
        assert len(recs) == 1
        assert "**Authors:**" in recs[0]["text"]
        assert recs[0]["chunk_index"] == 1
        assert recs[0]["section_part"] == 1


class TestSectionPartInvariant:
    def test_section_part_is_never_zero(self):
        tei = _tei_table("Table 1 .", "cap", [["A", "B"], ["1", "2"], ["3", "4"]])
        tables = _pc.extract_tables_md(tei)
        md = (
            "# Title\n\n**Authors:** A B\n\n**Year: 2020 | DOI: 10.1/x**\n\n"
            "## Results\n\n" + "Contenido. " * 40 + "\n"
        )
        recs = _records(md, tables)
        assert recs, "sin registros"
        assert all(r["section_part"] >= 1 for r in recs)
