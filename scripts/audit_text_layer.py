#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_text_layer.py — detecta PDFs cuya capa de texto es pobre (posibles escaneados) y, opcionalmente,
genera una copia con OCR (item 35). SOLO LECTURA sobre el corpus: nunca sustituye un PDF.

Indicador: palabras de `md_clean` por página del PDF. Un artículo normal da 300–900; por debajo de
`--threshold` (100) se sospecha escaneo o PDF sin texto; hay que mirarlo a mano (algunos son
documentos de figuras).

Uso:
    python3 scripts/audit_text_layer.py                       # informe de todas las categorías
    python3 scripts/audit_text_layer.py --category thiosulfate
    python3 scripts/audit_text_layer.py --ocr RUTA.pdf --out /ruta/salida.pdf [--lang eng]

OCR: renderiza cada página (PyMuPDF), la pasa por `tesseract` y reensambla un PDF con capa de texto.
Requiere `tesseract` (brew). Para adoptar el resultado: sustituir el PDF a mano y reprocesar la
categoría con `3_process_corpus.py --force` para ese paper.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CATEGORIAS = Path("/Volumes/research/categorias")
DEFAULT_THRESHOLD = 100.0


def words_per_page(words: int, pages: int) -> float:
    return words / max(pages, 1)


def audit_category(cat_dir: Path, threshold: float = DEFAULT_THRESHOLD) -> list:
    """[{category, paper_id, pages, md_words, words_per_page}] de los PDFs bajo el umbral."""
    import fitz
    out = []
    md_dir, pdf_dir = cat_dir / "md_clean", cat_dir / "pdfs"
    if not (md_dir.is_dir() and pdf_dir.is_dir()):
        return out
    for md in sorted(md_dir.glob("*.clean.md")):
        pid = md.name[: -len(".clean.md")]
        pdf = pdf_dir / f"{pid}.pdf"
        if not pdf.exists():
            continue
        try:
            pages = fitz.open(pdf).page_count
        except Exception:
            continue
        words = len(md.read_text(encoding="utf-8", errors="replace").split())
        wpp = words_per_page(words, pages)
        if wpp < threshold:
            out.append({"category": cat_dir.name, "paper_id": pid, "pages": pages,
                        "md_words": words, "words_per_page": round(wpp, 1)})
    return out


def ocr_pdf(src: Path, dst: Path, lang: str = "eng", dpi: int = 300) -> int:
    """Crea `dst` con capa de texto OCR a partir de `src`. Devuelve nº de páginas."""
    import fitz
    if not shutil.which("tesseract"):
        raise SystemExit("tesseract no está instalado (brew install tesseract)")
    doc = fitz.open(src)
    out = fitz.open()
    with tempfile.TemporaryDirectory() as tmp:
        for i, page in enumerate(doc):
            png = Path(tmp) / f"p{i}.png"
            page.get_pixmap(dpi=dpi).save(str(png))
            base = Path(tmp) / f"p{i}"
            r = subprocess.run(["tesseract", str(png), str(base), "-l", lang, "pdf"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"tesseract falló en la página {i + 1}: {r.stderr[-200:]}")
            part = fitz.open(str(base) + ".pdf")
            out.insert_pdf(part)
            part.close()
    out.save(str(dst))
    return len(doc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Auditoría de capa de texto / OCR (item 35)")
    ap.add_argument("--category", help="solo esta categoría")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--csv", help="guarda el informe en este CSV")
    ap.add_argument("--ocr", help="PDF a pasar por OCR")
    ap.add_argument("--out", help="PDF de salida del OCR")
    ap.add_argument("--lang", default="eng")
    args = ap.parse_args()
    if args.ocr:
        if not args.out:
            raise SystemExit("--ocr necesita --out")
        n = ocr_pdf(Path(args.ocr), Path(args.out), args.lang)
        print(f"OCR de {n} página(s) → {args.out}")
        return 0
    cats = [CATEGORIAS / args.category] if args.category else sorted(
        d for d in CATEGORIAS.iterdir() if d.is_dir())
    rows = [r for c in cats for r in audit_category(c, args.threshold)]
    rows.sort(key=lambda r: r["words_per_page"])
    print(f"{len(rows)} PDF(s) con < {args.threshold:g} palabras/página:")
    for r in rows:
        print(f"  {r['words_per_page']:6.1f}  {r['pages']:3d} pág  {r['md_words']:6d} pal  {r['category'][:26]:26s} {r['paper_id'][:70]}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["category", "paper_id", "pages", "md_words", "words_per_page"])
            w.writeheader(); w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
