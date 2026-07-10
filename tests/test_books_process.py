# -*- coding: utf-8 -*-
"""Tests de books/process.py: segmentación por TOC, páginas, heading_path,
limpieza (dehyphenation + headers/footers) y esquema de chunk de libro.

El fixture PDF se genera con PyMuPDF (fitz): 4 páginas con una cabecera
recurrente y un número de página en cada una, más un TOC de 3 entradas.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

_MOD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "books" / "process.py"
_spec = importlib.util.spec_from_file_location("books_process", _MOD_PATH)
bp = importlib.util.module_from_spec(_spec)
sys.modules["books_process"] = bp
_spec.loader.exec_module(bp)


# Contenido por página (sin la cabecera/pie; los añade _make_pdf).
_PAGES = [
    # Página 1 — Chapter 1
    "Chapter 1: Introduction\n"
    "This chapter introduces anaerobic diges-\n"
    "tion applied to biogas production in rural settings. "
    "The process converts organic matter into methane.",
    # Página 2 — 1.1 Fundamentals
    "1.1 Fundamentals\n"
    "Anaerobic digestion proceeds through hydrolysis, acidogenesis, "
    "acetogenesis and methanogenesis stages in sequence.",
    # Página 3 — Chapter 2
    "Chapter 2: Methods\n"
    "The experimental setup used a continuous stirred tank reactor "
    "operated at mesophilic temperature.",
    # Página 4 — continuación del Chapter 2
    "Samples were collected daily and analysed for volatile fatty acids "
    "and biogas composition over ninety days of operation.",
]


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    for i, body in enumerate(_PAGES, start=1):
        page = doc.new_page()
        # Cabecera recurrente (debe eliminarse por detección de running lines).
        page.insert_text((72, 40), "HANDBOOK OF BIOGAS TECHNOLOGY", fontsize=9)
        # Cuerpo.
        page.insert_textbox(fitz.Rect(72, 70, 520, 760), body, fontsize=11)
        # Pie con número de página (debe eliminarse como número suelto).
        page.insert_text((300, 780), str(i), fontsize=9)
    doc.set_toc([
        [1, "Chapter 1: Introduction", 1],
        [2, "1.1 Fundamentals", 2],
        [1, "Chapter 2: Methods", 3],
    ])
    doc.save(str(path))
    doc.close()


@pytest.fixture()
def book_pdf(tmp_path):
    p = tmp_path / "handbook.pdf"
    _make_pdf(p)
    return p


def test_toc_extraction_source_pdf(book_pdf):
    with fitz.open(book_pdf) as doc:
        entries, source = bp.get_toc_entries(doc)
    assert source == "pdf"
    assert [e[1] for e in entries] == [
        "Chapter 1: Introduction", "1.1 Fundamentals", "Chapter 2: Methods"]


def test_segment_pages_and_heading_path(book_pdf):
    with fitz.open(book_pdf) as doc:
        raw = bp.extract_pdf_pages(doc)
        entries, _ = bp.get_toc_entries(doc)
    running = bp.detect_running_lines(raw)
    cleaned = [bp.clean_page(p, running) for p in raw]
    secs = bp.segment_chapters(entries, cleaned, "handbook")

    by_title = {s["title"]: s for s in secs}
    # Rango de páginas (1-based inclusivo) derivado del TOC.
    assert (by_title["Chapter 1: Introduction"]["page_start"],
            by_title["Chapter 1: Introduction"]["page_end"]) == (1, 1)
    assert (by_title["1.1 Fundamentals"]["page_start"],
            by_title["1.1 Fundamentals"]["page_end"]) == (2, 2)
    # Chapter 2 abarca hasta la última página del libro.
    assert (by_title["Chapter 2: Methods"]["page_start"],
            by_title["Chapter 2: Methods"]["page_end"]) == (3, 4)

    # heading_path: la subsección cuelga del capítulo padre.
    assert by_title["1.1 Fundamentals"]["heading_path"] == \
        "Chapter 1: Introduction > 1.1 Fundamentals"
    assert by_title["Chapter 2: Methods"]["heading_path"] == "Chapter 2: Methods"


def test_cleaning_dehyphenation_and_running_removed(book_pdf):
    with fitz.open(book_pdf) as doc:
        raw = bp.extract_pdf_pages(doc)
    running = bp.detect_running_lines(raw)
    cleaned = "\n".join(bp.clean_page(p, running) for p in raw)
    # Palabra recompuesta del guion de fin de línea.
    assert "digestion" in cleaned
    assert "diges- tion" not in cleaned and "diges-\ntion" not in cleaned
    # Cabecera recurrente y números de página sueltos eliminados.
    assert "HANDBOOK OF BIOGAS TECHNOLOGY" not in cleaned


def test_chunk_records_schema(book_pdf):
    with fitz.open(book_pdf) as doc:
        raw = bp.extract_pdf_pages(doc)
        entries, _ = bp.get_toc_entries(doc)
    running = bp.detect_running_lines(raw)
    cleaned = [bp.clean_page(p, running) for p in raw]
    secs = bp.segment_chapters(entries, cleaned, "handbook")
    recs = bp.build_book_chunk_records(
        secs, collection="libros_docencia", book_id="handbook",
        book_title="Handbook of Biogas", year=2019,
        source_pdf=book_pdf, source_md_clean=Path("handbook.md"),
        target_words=1000, overlap_words=120,
    )
    assert recs, "debe generar al menos un chunk"
    r = recs[0]
    for key in ("paper_id", "doc_type", "heading_path", "page_start",
                "page_end", "section_canonical", "year", "chunk_hash", "text"):
        assert key in r
    assert r["doc_type"] == "book"
    assert r["section_canonical"] == "chapter"
    assert r["year"] == 2019  # denormalizado, NO year_from_paper_id
    assert all(r["paper_id"] == "handbook" for r in recs)
    # chunk_index consecutivo empezando en 1.
    assert [r["chunk_index"] for r in recs] == list(range(1, len(recs) + 1))


def test_toc_out_of_order_is_sorted_no_duplication():
    """Un bookmark fuera de orden (cap. intercalado al final) NO debe corromper
    los rangos ni duplicar texto: las entradas se ordenan por página."""
    cleaned = [f"texto unico de la pagina {i}" for i in range(1, 11)]  # 10 págs
    # Cap. 2 (pág. 5) llega FUERA DE ORDEN, tras el Índice (pág. 9).
    entries = [
        [1, "Chapter 1", 1],
        [1, "Chapter 3", 7],
        [1, "Index", 9],
        [1, "Chapter 2", 5],  # desordenada
    ]
    secs = bp.segment_chapters(entries, cleaned, "book")
    ranges = {s["title"]: (s["page_start"], s["page_end"]) for s in secs}
    assert ranges["Chapter 1"] == (1, 4)
    assert ranges["Chapter 2"] == (5, 6)
    assert ranges["Chapter 3"] == (7, 8)
    assert ranges["Index"] == (9, 10)
    # Sin ordenar, "Chapter 2" (última) habría acaparado 5..10 y "Chapter 1"
    # habría llegado hasta la 6, solapando. Verificamos que NO hay solape:
    covered = []
    for s in secs:
        covered.extend(range(s["page_start"], s["page_end"] + 1))
    assert len(covered) == len(set(covered)), "los rangos no deben solaparse"


def test_running_chapter_header_removed():
    """Una cabecera de capítulo que solo aparece en su tramo (con nº de página
    variable) debe detectarse y eliminarse."""
    topics = ["hydrolysis", "acidogenesis", "acetogenesis", "methanogenesis",
              "aeration", "agitation", "kinetics", "sterilisation", "membrane",
              "antibiotics", "citric", "scaleup", "protein", "balance"]
    pages = []
    for i, pg in enumerate(range(18, 31)):  # 13 páginas del cap. 1
        t = topics[i % len(topics)]
        pages.append(f"{pg} INDUSTRIAL MICROBIOLOGY\n"
                     f"El proceso de {t} se estudia en detalle sobre el sustrato.\n"
                     f"Los resultados de {t} muestran conversiones distintas cada vez.")
    for i, pg in enumerate(range(31, 39)):  # 8 páginas del cap. 2
        t = topics[(i + 3) % len(topics)]
        pages.append(f"CHAPTER 2 Dissolved Oxygen Measurement {pg}\n"
                     f"La medida de oxigeno disuelto durante {t} varia con el caudal.\n"
                     f"El caso {t} confirma la tendencia observada experimentalmente.")
    running = bp.detect_running_lines(pages)
    cleaned = "\n".join(bp.clean_page(p, running) for p in pages)
    assert "INDUSTRIAL MICROBIOLOGY" not in cleaned
    assert "Dissolved Oxygen Measurement" not in cleaned
    assert "se estudia en detalle sobre el sustrato" in cleaned  # cuerpo intacto


def test_parse_filename_meta():
    year, authors, title = bp.parse_filename_meta(
        "2007-Najafpour_Biochemical_Engineering_and_Biotechnology")
    assert year == 2007
    assert authors == [{"full": "Najafpour", "surname": "Najafpour", "forename": ""}]
    assert title == "Biochemical Engineering and Biotechnology"
    # Sin patrón claro: título legible, sin autores.
    y2, a2, t2 = bp.parse_filename_meta("handbook_of_biogas")
    assert y2 is None and a2 == []


def test_front_back_matter_not_chunked():
    """Secciones Table of Contents / Index / Preface no deben producir chunks;
    el resto sí. Verifica también is_front_back_matter (con/ sin acentos)."""
    assert bp.is_front_back_matter("Table of Contents")
    assert bp.is_front_back_matter("CONTENTS")
    assert bp.is_front_back_matter("Index")
    assert bp.is_front_back_matter("Índice")  # español: "indice" tras quitar acentos
    assert bp.is_front_back_matter("Preface")
    # No debe confundir un capítulo real que contiene la palabra 'index'.
    assert not bp.is_front_back_matter("Refractive Index Measurement")
    assert not bp.is_front_back_matter("5. Growth kinetics")

    sections = [
        {"title": "Table of Contents", "heading_path": "Table of Contents",
         "page_start": 8, "page_end": 17,
         "text": ". . . 5.6.9 Fed batch culture . . . 187 . . . Index . . . 435"},
        {"title": "1. Industrial Microbiology", "heading_path": "1. Industrial Microbiology",
         "page_start": 18, "page_end": 30,
         "text": "Industrial microbiology deals with the use of microorganisms "
                 "in industrial processes such as fermentation and bioconversion."},
        {"title": "Index", "heading_path": "Index",
         "page_start": 435, "page_end": 439,
         "text": "acetic acid 12; aeration 40; biomass 5; enzyme 88; yeast 349"},
    ]
    recs = bp.build_book_chunk_records(
        sections, collection="libros_docencia", book_id="najafpour",
        book_title="Biochemical Engineering", year=2007,
        source_pdf=Path("x.pdf"), source_md_clean=Path("x.md"),
        target_words=1000, overlap_words=120,
    )
    secs_in_chunks = {r["section"] for r in recs}
    assert "Table of Contents" not in secs_in_chunks
    assert "Index" not in secs_in_chunks
    assert "1. Industrial Microbiology" in secs_in_chunks
    assert recs, "el capítulo real debe seguir generando chunks"


def test_non_text_pdf_flagged_ocr(tmp_path):
    """Un PDF vacío (sin texto) no debe considerarse extraíble."""
    p = tmp_path / "scanned.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(str(p))
    doc.close()
    with fitz.open(p) as d:
        pages = bp.extract_pdf_pages(d)
    assert bp.is_text_pdf(pages) is False
