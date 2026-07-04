# -*- coding: utf-8 -*-
"""Fetcher canónico de Crossref works/<doi> (Nivel 2 de validación de metadata).

Un único punto de acceso al endpoint `works/<doi>` de Crossref, con caché en
memoria por DOI y sleep de cortesía. Devuelve un dict normalizado o None en un
miss legítimo (404 / DOI en DataCite / respuesta no-JSON), sin lanzar excepción.

NO confundir con `crossref_suggest` de 11_Articulos.py, que usa el endpoint de
búsqueda (`/works?query.bibliographic=…`) para sugerir DOIs por título.
"""
import os
import time
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

from utils.pdf_utils import normalize_doi

_MAILTO = os.getenv("UNPAYWALL_EMAIL", "")
_CACHE: Dict[str, Optional[dict]] = {}


def _authors(message: dict) -> List[dict]:
    """Autores de Crossref a [{family, given}]; ignora entradas de organización
    (las que traen `name` en vez de `family`)."""
    out = []
    for a in message.get("author") or []:
        family = (a.get("family") or "").strip()
        if not family:
            continue  # entrada de organización (name) u otra sin apellido
        out.append({"family": family, "given": (a.get("given") or "").strip()})
    return out


def _pick_year(message: dict) -> Optional[int]:
    """Año CANÓNICO con preferencia published-print → published-online →
    issued → published (primer date-parts[0][0] no nulo).

    published-print es el año de publicación citable. `issued` es el MÍNIMO de
    las fechas Crossref (suele ser el online temprano: origen de los mismatches
    +1 local<print), y published-online puede ser una digitalización tardía
    (caso Wise: print=1978, online=2004) — por eso print va primero."""
    for key in ("published-print", "published-online", "issued", "published"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                pass
    return None


def fetch_work(doi: str) -> Optional[dict]:
    """GET api.crossref.org/works/<doi> → dict normalizado o None (miss).

    Devuelve {title, authors:[{family,given}], journal, journal_short, year}.
    404 / DataCite miss / no-JSON → None (miss legítimo, sin excepción).
    Cacheado en memoria por DOI (incluidos los None)."""
    doi = normalize_doi(str(doi or ""))
    if not doi:
        return None
    if doi in _CACHE:
        return _CACHE[doi]

    result: Optional[dict] = None
    try:
        params = {"mailto": _MAILTO} if _MAILTO else {}
        r = requests.get(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            params=params, timeout=15,
        )
        if r.status_code == 200:
            msg = r.json().get("message", {}) or {}
            ct = msg.get("container-title") or []
            sct = msg.get("short-container-title") or []
            title = msg.get("title") or []
            result = {
                "title":         (title[0] or "").strip() if title else "",
                "authors":       _authors(msg),
                "journal":       (ct[0] or "").strip() if ct else "",
                "journal_short": (sct[0] or "").strip() if sct else "",
                "year":          _pick_year(msg),
            }
    except Exception:
        result = None

    _CACHE[doi] = result
    time.sleep(0.1)  # cortesía con Crossref
    return result
