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
import difflib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from utils.constants import year_from_paper_id
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
    # ── Nivel 1 (heurísticas locales) ──
    "title_eq_journal":        "título idéntico al nombre de la revista",
    "title_has_journal_prefix": "título empieza por el nombre de la revista",
    "authors_glued":           "autor con camelCase pegado (sin espacios) — informativo",
    "authors_affiliation":     "autor contaminado con afiliación/lugar o dígitos",
    "year_implausible":        "año ausente o fuera de [1900, año_actual+1]",
    "doi_malformed":           "DOI presente pero con formato inválido",
    # ── Nivel 2 (contraste con Crossref por DOI) ──
    "crossref_miss":           "DOI no resuelto en Crossref (miss/404)",
    "title_recover":           "título ausente (== revista): Crossref recupera el real",
    "title_mismatch":          "título local difiere del de Crossref",
    "journal_mismatch":        "revista local difiere de la de Crossref",
    "journal_fill":            "revista ausente: Crossref la aporta",
    "year_mismatch":           "año local difiere de Crossref (canónico; paper_id solo fallback)",
    "authors_mismatch":        "autores locales difieren de Crossref (adopción masiva)",
}

# Ratio difflib mínimo para considerar dos títulos "iguales" (por debajo →
# title_mismatch). Sobre texto normalizado.
_TITLE_MATCH_RATIO = 0.85

# Severidades que hacen entrar un paper al sidecar. Los issues "info" (p. ej.
# authors_glued) se SIGUEN calculando y se listan si el paper ya entró por otro
# motivo, pero no lo flaggean por sí solos. Ajustable aquí.
#   Motivo authors_glued="info": forename/surname vienen vacíos en TODO el corpus
#   (solo `full` pegado), así que marcaría ~99% de papers — verdadero pero inútil
#   como triaje por-paper. Su reparación es sistémica vía Crossref (Nivel 2).
SIDECAR_MIN_SEVERITY = {"medium", "high"}

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
        return {"code": "authors_glued", "field": "authors", "severity": "info",
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


# ---------------------------------------------------------------------------
# Nivel 2 — contraste con Crossref por DOI (Crossref SUGIERE, no sobreescribe)
# ---------------------------------------------------------------------------

def _year_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _surnames(authors) -> List[str]:
    """Apellidos normalizados de una lista de autores (dicts o strings)."""
    out = []
    for a in (authors or []):
        if isinstance(a, dict):
            sn = (a.get("surname") or "").strip()
            if not sn:
                full = (a.get("full") or "").strip()
                sn = full.split()[-1] if full else ""
        else:
            toks = str(a).split()
            sn = toks[-1] if toks else ""
        if sn:
            out.append(_norm(sn))
    return out


def _stored_authors_incomplete(authors) -> bool:
    """True si todos los autores tienen forename Y surname vacíos (caso corpus:
    solo `full` pegado). Si no hay autores, también se considera incompleto."""
    dicts = [a for a in (authors or []) if isinstance(a, dict)]
    if not authors:
        return True
    if dicts and all(not (a.get("forename") or "").strip()
                     and not (a.get("surname") or "").strip() for a in dicts):
        return True
    return False


def _fmt_cr_authors(cr_authors) -> str:
    """[{family,given}] → 'Given Family; …' para preview."""
    parts = []
    for a in cr_authors or []:
        nombre = (f"{a.get('given', '')} {a.get('family', '')}").strip()
        if nombre:
            parts.append(nombre)
    return "; ".join(parts)


def year_delta_severity(delta) -> str:
    """Severidad de un year_mismatch según el delta de año (con o sin signo):
    ±1 → "low" (desfase online-temprano vs published-print, apto para adopción
    MASIVA); resto (|delta|>=2 o delta desconocido/None) → "medium" (posible
    corrupción o caso editorial dudoso — passalacqua: local 2023, online 2024,
    print 2025 —, a adoptar uno a uno en el listado por-campo)."""
    return "low" if delta is not None and abs(delta) == 1 else "medium"


def _year_fallback_paper_id(rec: dict) -> List[dict]:
    """Fallback de año SOLO cuando Crossref no aporta año (miss o year vacío):
    sugiere el año embebido en paper_id. Mantiene viva la señal para los años
    corruptos de papers que Crossref no puede confirmar."""
    stored_year = _year_int(rec.get("year"))
    pid_year = year_from_paper_id(rec.get("paper_id") or "")
    if pid_year and pid_year != stored_year:
        return [{"code": "year_mismatch", "field": "year", "severity": "medium",
                 "kind": "mismatch", "stored": stored_year, "suggested": pid_year,
                 "suggested_source": "paper_id",
                 "msg": f"año local {stored_year} ≠ paper_id {pid_year} "
                        f"(sin año de Crossref)"}]
    return []


def compare_with_crossref(rec: dict, fetch=None) -> List[dict]:
    """Contrasta un registro contra Crossref (works/<doi>) y devuelve issues
    con {code, field, severity, kind, stored, suggested, ...}. Crossref SUGIERE;
    la escritura la decide el humano en 11_Articulos.

    `fetch` inyectable (default utils.crossref.fetch_work) para tests offline.
    `kind` ∈ {"mismatch","recover","fill"}. Sin DOI válido → []. Miss →
    crossref_miss (info) + fallback de año por paper_id si aplica."""
    doi = (rec.get("doi") or "").strip()
    if not doi or check_doi_format(rec):   # sin DOI o DOI malformado (Nivel 1)
        return []

    if fetch is None:
        from utils.crossref import fetch_work as fetch
    cr = fetch(doi)
    if not cr:
        return [{"code": "crossref_miss", "field": "doi", "severity": "info",
                 "kind": "miss", "stored": doi, "suggested": None,
                 "msg": "DOI no resuelto en Crossref"}] + _year_fallback_paper_id(rec)

    issues: List[dict] = []

    # ── título ──
    stored_title = (rec.get("title") or "").strip()
    cr_title = (cr.get("title") or "").strip()
    if cr_title:
        is_journal_as_title = bool(
            check_title_eq_journal(rec) or check_title_starts_with_journal(rec))
        if is_journal_as_title:
            issues.append({
                "code": "title_recover", "field": "title", "severity": "high",
                "kind": "recover", "stored": stored_title, "suggested": cr_title,
                "msg": "título local es la revista; Crossref recupera el real"})
        else:
            ratio = difflib.SequenceMatcher(
                None, _norm(stored_title), _norm(cr_title)).ratio()
            if ratio < _TITLE_MATCH_RATIO:
                issues.append({
                    "code": "title_mismatch", "field": "title", "severity": "medium",
                    "kind": "mismatch", "stored": stored_title, "suggested": cr_title,
                    "ratio": round(ratio, 3),
                    "msg": f"título difiere de Crossref (ratio {ratio:.2f})"})

    # ── revista ──
    stored_journal = (rec.get("journal") or "").strip()
    cr_journal = (cr.get("journal") or "").strip()
    cr_journal_short = (cr.get("journal_short") or "").strip()
    if cr_journal or cr_journal_short:
        if not stored_journal:
            issues.append({
                "code": "journal_fill", "field": "journal", "severity": "medium",
                "kind": "fill", "stored": "", "suggested": cr_journal or cr_journal_short,
                "msg": "revista ausente; Crossref la aporta"})
        else:
            nsj = _norm(stored_journal)
            if nsj != _norm(cr_journal) and nsj != _norm(cr_journal_short):
                issues.append({
                    "code": "journal_mismatch", "field": "journal", "severity": "medium",
                    "kind": "mismatch", "stored": stored_journal,
                    "suggested": cr_journal or cr_journal_short,
                    "msg": "revista difiere de Crossref"})

    # ── año ── (Crossref CANÓNICO; paper_id solo fallback si Crossref no trae
    # año). severity discrimina: ±1 = "low" (desfase print/online, adoptable
    # pero de bajo valor), resto = "medium". Sigue entrando al sidecar igual
    # (el flag Crossref va por kind, no por severity).
    stored_year = _year_int(rec.get("year"))
    cr_year = _year_int(cr.get("year"))
    if cr_year:
        if cr_year != stored_year:
            delta = abs(cr_year - stored_year) if stored_year is not None else None
            severity = year_delta_severity(delta)
            issues.append({
                "code": "year_mismatch", "field": "year", "severity": severity,
                "kind": "mismatch", "stored": stored_year, "suggested": cr_year,
                "suggested_source": "crossref",
                "msg": f"año local {stored_year} ≠ Crossref {cr_year}"
                       + (" (±1, print/online)" if severity == "low" else "")})
    else:
        issues.extend(_year_fallback_paper_id(rec))

    # ── autores ── (coarse/advisory; universal en este corpus → adopción masiva)
    cr_authors = cr.get("authors") or []
    if cr_authors:
        stored_sn = set(_surnames(rec.get("authors")))
        cr_sn = set(_surnames(cr_authors))
        overlap = (len(stored_sn & cr_sn) / len(cr_sn)) if cr_sn else 1.0
        if _stored_authors_incomplete(rec.get("authors")) or overlap < 0.5:
            issues.append({
                "code": "authors_mismatch", "field": "authors", "severity": "info",
                "kind": "mismatch", "stored": "; ".join(_author_names(rec)),
                "suggested": _fmt_cr_authors(cr_authors),
                "msg": "autores difieren de Crossref (reparar por adopción masiva)"})

    return issues


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


_CROSSREF_REPAIR_KINDS = {"mismatch", "recover", "fill"}


def _sidecar_row(rec: dict, issues: List[dict], crossref: Optional[dict] = None) -> dict:
    """Construye la fila del sidecar para un paper flagged."""
    doi = (rec.get("doi") or "").strip()
    row = {
        "paper_id":  rec.get("paper_id", ""),
        "stable_id": rec.get("stable_id", ""),
        "doi":       doi,
        "has_doi":   bool(doi),
        "title":     rec.get("title") or "",
        "journal":   rec.get("journal") or "",
        "year":      rec.get("year"),
        "authors":   rec.get("authors") or [],
        "issues":    issues,
    }
    if crossref is not None:
        row["crossref"] = crossref
    return row


def validate_category(category: str, categorias_dir) -> List[dict]:
    """Valida papers_metadata.jsonl de una categoría (Nivel 1 puro). Devuelve
    SOLO los registros con >=1 issue de severidad en SIDECAR_MIN_SEVERITY (lista
    "a revisar", no el corpus entero). Los issues "info" se listan en el
    registro si el paper ya entró por otro motivo, pero no lo flaggean solos."""
    jsonl = Path(categorias_dir) / category / "metadata" / "papers_metadata.jsonl"
    flagged = []
    for rec in load_jsonl(jsonl):
        issues = validate_record(rec)
        if any(i["severity"] in SIDECAR_MIN_SEVERITY for i in issues):
            flagged.append(_sidecar_row(rec, issues))
    return flagged


def validate_category_crossref(category: str, categorias_dir,
                               limit: Optional[int] = None, fetch=None) -> List[dict]:
    """Nivel 1 + Nivel 2: enriquece el sidecar con un bloque
    `crossref:{fetched, issues}` por paper con DOI válido. Un paper entra si
    tiene issues locales medium/high (Nivel 1) O algún issue Crossref con
    kind ∈ {mismatch, recover, fill}.

    `limit` topa el nº de llamadas a Crossref en la categoría (los papers no
    consultados quedan sin bloque crossref). `fetch` inyectable para tests."""
    jsonl = Path(categorias_dir) / category / "metadata" / "papers_metadata.jsonl"
    if fetch is None:
        from utils.crossref import fetch_work as fetch
    flagged, calls = [], 0
    for rec in load_jsonl(jsonl):
        local = validate_record(rec)
        local_flag = any(i["severity"] in SIDECAR_MIN_SEVERITY for i in local)

        cr_block = None
        doi_valid = bool((rec.get("doi") or "").strip()) and not check_doi_format(rec)
        if doi_valid and (limit is None or calls < limit):
            calls += 1
            cr_issues = compare_with_crossref(rec, fetch=fetch)
            fetched = not any(i["code"] == "crossref_miss" for i in cr_issues)
            cr_block = {"fetched": fetched, "issues": cr_issues}

        cr_flag = bool(cr_block) and any(
            i.get("kind") in _CROSSREF_REPAIR_KINDS for i in cr_block["issues"])

        if local_flag or cr_flag:
            flagged.append(_sidecar_row(rec, local, crossref=cr_block))
    return flagged
