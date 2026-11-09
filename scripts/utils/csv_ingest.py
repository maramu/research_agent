# -*- coding: utf-8 -*-
"""Ingesta desde un CSV de Scopus cribado por el investigador.

Funciones puras (sin NAS ni red) para la pestaña «CSV» de Ingestar:

- ``project_name_from_filename``: nombre de proyecto ad-hoc a partir del CSV.
- ``normalize_screened_csv``: lee el CSV (separador/codificación autodetectados)
  y devuelve un DataFrame con las columnas que esperan ``3a_download_pdfs.py`` y
  ``1_rename_papers_by_doi.py`` (``DOI``, ``Title``, ``Year``, ``Authors``,
  ``Source title``), aceptando tanto la exportación original de Scopus (inglés)
  como CSV cribados con cabeceras en español (``titulo``, ``anio``…).
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Union

import pandas as pd

# Nombre canónico → alias aceptados (comparación en minúsculas, sin tildes)
_ALIASES = {
    "DOI": ["doi"],
    "Title": ["title", "article title", "document title", "titulo", "titulo del articulo"],
    "Year": ["year", "publication year", "pubyear", "anio", "ano", "año"],
    "Authors": ["authors", "author names", "author(s)", "autores", "autor"],
    "Source title": ["source title", "revista", "journal", "fuente"],
}

_DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.I)


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.strip().lower()


def project_name_from_filename(filename: str) -> str:
    """'Seleccion_RAG_VOSC_60.csv' → 'seleccion_rag_vosc_60' (válido para run_adhoc)."""
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename.strip().replace("\\", "/").split("/")[-1])
    slug = re.sub(r"[^a-z0-9_-]+", "_", _fold(stem)).strip("_-")
    slug = re.sub(r"_+", "_", slug)
    return slug or "csv_adhoc"


@dataclass
class CsvReport:
    n_rows: int = 0
    n_valid: int = 0               # filas con DOI válido (tras quitar duplicados)
    n_no_doi: int = 0
    n_duplicates: int = 0
    mapped: dict = field(default_factory=dict)   # canónico → columna original
    warnings: List[str] = field(default_factory=list)


def _clean_doi(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).strip()
    s = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", s, flags=re.I)
    m = _DOI_RE.search(s)
    return m.group(0).rstrip(".,;)").lower() if m else ""


def normalize_screened_csv(
    source: Union[bytes, str, "io.IOBase"],
) -> "tuple[pd.DataFrame, CsvReport]":
    """Lee el CSV y lo devuelve normalizado + informe.

    Lanza ``ValueError`` si no hay columna DOI o título reconocible. Las filas sin
    DOI válido se descartan (se cuentan en el informe); los DOIs repetidos se
    dejan una sola vez. Las columnas originales no reconocidas se conservan.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    elif isinstance(source, str):
        source = open(source, "rb")
    raw = source.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    first = raw.decode("utf-8-sig", errors="replace").splitlines()[0] if raw.strip() else ""
    sep = max([",", ";", "\t", "|"], key=first.count)   # el sniffer falla con CSV pequeños
    df = pd.read_csv(io.BytesIO(raw), sep=sep, dtype=str,
                     encoding="utf-8-sig", keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]

    rep = CsvReport(n_rows=len(df))
    folded = {_fold(c): c for c in df.columns}
    for canon, aliases in _ALIASES.items():
        for a in aliases:
            if _fold(a) in folded:
                rep.mapped[canon] = folded[_fold(a)]
                break
    for needed in ("DOI", "Title"):
        if needed not in rep.mapped:
            raise ValueError(
                f"No encuentro la columna {needed} en el CSV (columnas: {list(df.columns)})"
            )

    out = pd.DataFrame()
    for canon, orig in rep.mapped.items():
        out[canon] = df[orig].astype(str).str.strip()
    out["DOI"] = df[rep.mapped["DOI"]].map(_clean_doi)
    for c in df.columns:                      # conservar extras (categoría, por qué, EID…)
        if c not in rep.mapped.values() and c not in out.columns:
            out[c] = df[c]

    rep.n_no_doi = int((out["DOI"] == "").sum())
    out = out[out["DOI"] != ""]
    before = len(out)
    out = out.drop_duplicates(subset="DOI", keep="first").reset_index(drop=True)
    rep.n_duplicates = before - len(out)
    rep.n_valid = len(out)
    if rep.n_no_doi:
        rep.warnings.append(f"{rep.n_no_doi} fila(s) sin DOI válido descartadas")
    if rep.n_duplicates:
        rep.warnings.append(f"{rep.n_duplicates} DOI duplicado(s) eliminados")
    for opt in ("Year", "Authors"):
        if opt not in rep.mapped:
            rep.warnings.append(f"Sin columna {opt}: el nombre del PDF dependerá solo del DOI/título")
    return out, rep
