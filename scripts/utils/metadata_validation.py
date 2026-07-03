# -*- coding: utf-8 -*-
"""Validación local de metadata (Nivel 1) — heurísticas sin red.

Detecta registros de papers_metadata.jsonl con metadata de referencia degradada:
título==revista, autores pegados (camelCase) o contaminados con afiliación,
año/DOI implausibles. Pensado para generar un sidecar "a revisar" por categoría
(validation_<cat>.jsonl) que se consume desde 11_Articulos. SOLO LECTURA sobre
papers_metadata.jsonl — este módulo nunca modifica la metadata.

Nivel 2 (contraste con Crossref por DOI) es una iteración posterior; el DOI
ausente NO es issue aquí (ya lo gestiona la columna "Sin DOI" de 11_Articulos).

Forma de `authors` (4_extract_metadata.py): lista de dicts
{"full", "forename", "surname"}; se toleran también strings sueltos, igual que
hace `_fmt_authors` en 11_Articulos.py.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from utils.pdf_utils import normalize_stem

# ---------------------------------------------------------------------------
# TUNABLE: tokens de afiliación/lugar que no deberían aparecer en un nombre de
# autor. Ampliar aquí según los falsos negativos que aparezcan en los pases.
# Se casan como palabra completa (\b...\b), sin distinguir mayúsculas.
# ---------------------------------------------------------------------------
AFFILIATION_TOKENS = [
    "university", "universidad", "universitat", "universite",
    "institute", "instituto", "institut",
    "department", "dept", "faculty", "school",
    "laboratory", "laboratories", "lab",
    "college", "center", "centre",
    "gmbh", "inc", "ltd", "llc", "corp",
    "dtu", "lyngby", "denmark", "spain", "china", "germany", "netherlands",
]

_AFFILIATION_RE = re.compile(
    r"\b(" + "|".join(AFFILIATION_TOKENS) + r")\b", re.IGNORECASE
)

ISSUE_CODES = {
    "title_eq_journal":        "título idéntico al nombre de la revista",
    "title_has_journal_prefix": "título empieza por el nombre de la revista",
    "authors_glued":           "autor con camelCase pegado (sin espacios)",
    "authors_affiliation":     "autor contaminado con afiliación/lugar o dígitos",
    "year_implausible":        "año ausente o fuera de [1900, año_actual+1]",
    "doi_malformed":           "DOI presente pero con formato inválido",
}

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


def _norm(s) -> str:
    """Normaliza para comparación (reutiliza utils.pdf_utils.normalize_stem:
    NFKC, minúsculas, colapsa espacios/puntuación a '_', quita '_' de bordes)."""
    return normalize_stem(str(s or ""))


def _author_names(rec: dict) -> List[str]:
    """Resuelve la lista de autores a nombres legibles (mismo criterio que
    _fmt_authors en 11_Articulos.py: forename+surname, fallback full/str)."""
    authors = rec.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    names = []
    for a in authors:
        if isinstance(a, dict):
            fn = (a.get("forename") or "").strip()
            sn = (a.get("surname") or "").strip()
            nombre = (fn + " " + sn).strip() or (a.get("full") or "").strip()
        else:
            nombre = str(a).strip()
        if nombre:
            names.append(nombre)
    return names


# ---------------------------------------------------------------------------
# Chequeos: cada uno devuelve None o {code, field, severity, msg}
# ---------------------------------------------------------------------------

def check_title_eq_journal(rec: dict) -> Optional[dict]:
    nt, nj = _norm(rec.get("title")), _norm(rec.get("journal"))
    if nt and nj and nt == nj:
        return {"code": "title_eq_journal", "field": "title", "severity": "high",
                "msg": f"título == revista: {rec.get('title')!r}"}
    return None


def check_title_starts_with_journal(rec: dict) -> Optional[dict]:
    nt, nj = _norm(rec.get("title")), _norm(rec.get("journal"))
    # Umbral de trivialidad sobre el texto normalizado; se exige frontera de
    # token ("_") para no casar prefijos parciales de palabra.
    if nj and len(nj) >= 8 and nt != nj and nt.startswith(nj + "_"):
        return {"code": "title_has_journal_prefix", "field": "title",
                "severity": "medium",
                "msg": f"título empieza por la revista {rec.get('journal')!r}"}
    return None


def check_glued_authors(rec: dict) -> Optional[dict]:
    """CamelCase pegado en un autor sin espacios (p. ej. 'ViolaCorbellini').

    Falsos positivos conocidos: apellidos tipo McDonald/DeSantis almacenados
    como token único sin nombre de pila — por eso este chequeo es advisory
    (lista "a revisar"), no correctivo.
    """
    glued = [n for n in _author_names(rec)
             if not re.search(r"\s", n) and re.search(r"[a-z][A-Z]", n)]
    if glued:
        return {"code": "authors_glued", "field": "authors", "severity": "high",
                "msg": "autores pegados: " + "; ".join(glued)}
    return None


def check_authors_affiliation(rec: dict) -> Optional[dict]:
    """Autor con dígitos o tokens de afiliación/lugar (ver AFFILIATION_TOKENS)."""
    bad = [n for n in _author_names(rec)
           if re.search(r"\d", n) or _AFFILIATION_RE.search(n)]
    if bad:
        return {"code": "authors_affiliation", "field": "authors",
                "severity": "high",
                "msg": "autores con afiliación/dígitos: " + "; ".join(bad)}
    return None


def check_year(rec: dict) -> Optional[dict]:
    year = rec.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    max_year = datetime.now().year + 1
    if year is None:
        return {"code": "year_implausible", "field": "year", "severity": "medium",
                "msg": "año ausente"}
    if not (1900 <= year <= max_year):
        return {"code": "year_implausible", "field": "year", "severity": "medium",
                "msg": f"año fuera de rango [1900, {max_year}]: {year}"}
    return None


def check_doi_format(rec: dict) -> Optional[dict]:
    """DOI presente con formato inválido. DOI ausente NO es issue aquí (lo
    gestiona la columna 'Sin DOI' de 11_Articulos)."""
    doi = (rec.get("doi") or "").strip()
    if doi and not _DOI_RE.match(doi):
        return {"code": "doi_malformed", "field": "doi", "severity": "high",
                "msg": f"DOI malformado: {doi!r}"}
    return None


_ALL_CHECKS = [
    check_title_eq_journal,
    check_title_starts_with_journal,
    check_glued_authors,
    check_authors_affiliation,
    check_year,
    check_doi_format,
]


def validate_record(rec: dict) -> List[dict]:
    """Aplica todos los chequeos a un registro; devuelve la lista de issues."""
    return [issue for check in _ALL_CHECKS if (issue := check(rec))]


def load_jsonl(path: Path) -> List[Dict]:
    """Lectura tolerante de un jsonl (líneas corruptas se descartan)."""
    records = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records


def validate_category(category: str, categorias_dir) -> List[dict]:
    """Valida papers_metadata.jsonl de una categoría. Devuelve SOLO los
    registros con >=1 issue (lista "a revisar", no el corpus entero)."""
    jsonl = Path(categorias_dir) / category / "metadata" / "papers_metadata.jsonl"
    flagged = []
    for rec in load_jsonl(jsonl):
        issues = validate_record(rec)
        if issues:
            doi = (rec.get("doi") or "").strip()
            flagged.append({
                "paper_id":  rec.get("paper_id", ""),
                "stable_id": rec.get("stable_id", ""),
                "doi":       doi,
                "has_doi":   bool(doi),
                "title":     rec.get("title") or "",
                "journal":   rec.get("journal") or "",
                "year":      rec.get("year"),
                "authors":   rec.get("authors") or [],
                "issues":    issues,
            })
    return flagged
