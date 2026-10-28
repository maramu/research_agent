#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Funciones reutilizables para extracción y manipulación de PDFs científicos.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

DOI_REGEX = re.compile(r"\b(10\.\d{4,9}/[-._;(),<>/:A-Z0-9]+)\b", re.IGNORECASE)

STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of",
    "on", "or", "the", "to", "with", "without", "via", "using", "use",
    "towards", "toward", "over", "under", "through", "during", "between",
    "de", "del", "la", "el", "los", "las", "y", "en", "por", "para", "con",
    "sin", "sobre", "un", "una", "unos", "unas",
}


def strip_accents(text: str) -> str:
    """Elimina tildes y diacríticos de un texto Unicode."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def slugify(text: str) -> str:
    """Convierte texto a slug ASCII en minúsculas con palabras separadas por _."""
    text = strip_accents(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[''`´]", "", text)
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"[\s\-]+", "_", text.strip())
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def normalize_stem(s: str) -> str:
    """NFKC + colapsa espacios/puntos/guiones/comas a '_'; minúsculas; quita '_' extremos."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s\.\-,]+", "_", s).lower()
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


# Longitud mínima de clave para emparejar un PDF con un paper por PREFIJO.
PREFIX_MATCH_MIN_KEY = 60


def stem_key(s: str) -> str:
    """Clave de comparación de nombres: minúsculas, todo lo no [a-z0-9] → '_'.
    A diferencia de normalize_stem, ignora corchetes y paréntesis del "[doi]"."""
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def md_stem_keys(md_dir: Path) -> set[str]:
    """Claves (stem_key) de los paper_id con md_clean en `md_dir`."""
    if not md_dir.is_dir():
        return set()
    return {stem_key(m.name[: -len(".clean.md")]) for m in md_dir.glob("*.clean.md")}


def is_processed_stem(pdf_stem: str, md_keys: set[str]) -> bool:
    """True si el PDF `pdf_stem` ya corresponde a un paper procesado: clave
    exacta, o prefijo de ≥PREFIX_MATCH_MIN_KEY caracteres (el paper_id puede
    estar truncado respecto al nombre largo "Año - Autor - Título [doi]").
    Deliberadamente NO empareja por DOI: dos PDFs con el mismo DOI son justo
    el duplicado que el cribado debe detectar."""
    k = stem_key(pdf_stem)
    return k in md_keys or any(
        len(mk) >= PREFIX_MATCH_MIN_KEY and k.startswith(mk) for mk in md_keys)


_DOI_IN_NAME = re.compile(r"\[(10\.\d{4,9}_[^\]]+)\]|^(10\.\d{4,9}_[^\s]+)$")


def extract_doi_from_filename(name: str) -> Optional[str]:
    """DOI embebido en un nombre de fichero hecho por 3a_download_pdfs.py:
    "Año - Autor - Título [10.1016_j.x.2025.1].pdf" o "10.1515_znb-1986-1208.pdf"
    (el '/' del DOI se guarda como '_'). Mejor esfuerzo: solo se repone el primer
    '/' (tras el registrante); el llamador debe validar el resultado (Crossref)."""
    stem = Path(name).stem if name.lower().endswith(".pdf") else name
    m = _DOI_IN_NAME.search(stem.strip())
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    return normalize_doi(raw.replace("_", "/", 1)) or None


def shorten_title(title: str, max_words: int = 8) -> str:
    """Acorta un título a las primeras max_words palabras significativas (sin stopwords)."""
    clean = strip_accents(title).lower()
    clean = re.sub(r"[^a-z0-9\s]", " ", clean)
    words = [w for w in clean.split() if w and w not in STOPWORDS]
    if not words:
        words = clean.split()
    return "_".join(words[:max_words]) if words else "untitled"


def sanitize_filename(name: str, max_len: int = 180) -> str:
    """Elimina caracteres inválidos en nombres de archivo y trunca si es necesario."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name).strip("._ ")
    if len(name) > max_len:
        stem = Path(name).stem[: max_len - 4]
        name = f"{stem}.pdf"
    return name


def _clean_doi(doi: str) -> str:
    doi = doi.strip()
    doi = doi.rstrip(").,;]}>")
    doi = doi.lstrip("([<{")
    # Wiley/ACS SICI: keep the single-letter suffix (e.g. "2-G"), strip any run
    # of 2+ alpha chars that follows it (e.g. "within" in "2-Gwithin").
    doi = re.sub(r'(-[a-zA-Z])[a-zA-Z]{2,}$', r'\1', doi)
    # General case: strip a word of 3+ alpha chars glued directly after a digit
    # (e.g. "2within" → "2", "129348Abstract" → "129348").
    # NOT applied when alpha follows "/" or "-" — those are legitimate DOI suffixes.
    doi = re.sub(r'(?<=\d)[a-zA-Z]{3,}$', '', doi)
    return doi


def normalize_doi(doi: str) -> str:
    """Strip spaces, URL prefix and trailing slash from a DOI value."""
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.rstrip("/")


def extract_doi_from_text(text: str) -> Optional[str]:
    """Extrae el primer DOI válido encontrado en un bloque de texto."""
    text = text.replace("\x00", " ")
    text = re.sub(r"https?://(dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bdoi\s*:\s*", "", text, flags=re.IGNORECASE)

    matches = DOI_REGEX.findall(text)
    for m in matches:
        doi = _clean_doi(m)
        if doi.lower().startswith("10."):
            return doi
    return None


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 3) -> str:
    """Extrae texto de las primeras max_pages páginas de un PDF."""
    texts = []
    with fitz.open(pdf_path) as doc:
        n = min(len(doc), max_pages)
        for i in range(n):
            texts.append(doc[i].get_text("text", sort=True))
    return "\n".join(texts)


def extract_doi_from_pdf(pdf_path: Path) -> Optional[str]:
    """Extrae DOI de un PDF buscando primero en metadatos y luego en el texto."""
    try:
        with fitz.open(pdf_path) as doc:
            meta = doc.metadata or {}
            meta_text = " ".join(str(v) for v in meta.values() if v)
            doi = extract_doi_from_text(meta_text)
            if doi:
                return doi
    except Exception:
        pass

    try:
        text = extract_text_from_pdf(pdf_path, max_pages=3)
        return extract_doi_from_text(text)
    except Exception:
        return None
