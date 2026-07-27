# -*- coding: utf-8 -*-
"""
Registro persistente de DOIs pendientes de descarga.

Ruta fija: /Volumes/research/metadatos/pendientes_descarga.csv

Estados:
  pending | downloaded | manual | blocked | no_pdf_found | duplicate | wrong_document

Usado por 3a_download_pdfs.py para acumular fallos entre lotes,
y por el futuro subagente navegador (item 28) como fuente de trabajo.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

NAS_ROOT = Path("/Volumes/research")
REGISTRY_PATH = NAS_ROOT / "metadatos" / "pendientes_descarga.csv"
CATEGORIAS_DIR = NAS_ROOT / "categorias"

_COLS = [
    "doi", "title", "year", "category",
    "landing_url", "status", "reason", "last_checked", "notes",
    "snooze_until",
]

# Estados que se consideran resueltos (no se sobreescriben al hacer upsert).
# 'blocked' entra aquí: el veto es una decisión manual y el upsert semanal
# no debe pisar su `reason` con el error de descarga de turno.
_RESOLVED = {"downloaded", "manual", "duplicate", "wrong_document", "blocked"}


def _norm(doi) -> str:
    """DOI a clave comparable. El registro guarda el DOI tal cual llegó, así
    que toda comparación pasa por aquí."""
    return str(doi or "").strip().lower()


def load() -> pd.DataFrame:
    """Carga el registro. Devuelve DataFrame vacío si no existe."""
    if REGISTRY_PATH.exists():
        df = pd.read_csv(REGISTRY_PATH, dtype=str).fillna("")
        for col in _COLS:
            if col not in df.columns:
                df[col] = ""
        return df[_COLS]
    return pd.DataFrame(columns=_COLS)


def save(df: pd.DataFrame) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(REGISTRY_PATH, index=False, encoding="utf-8-sig")


def upsert(rows: List[Dict], category: str = "") -> int:
    """Añade o actualiza entradas por DOI.

    - Si el DOI no existe → lo añade con status 'pending'.
    - Si ya existe con estado resuelto (_RESOLVED) → no lo toca.
    - Si ya existe con estado 'pending' → actualiza reason/last_checked.
    - Las notas manuales nunca se sobreescriben.

    Returns:
        Número de entradas nuevas añadidas.
    """
    df = load()
    today = date.today().isoformat()
    added = 0

    for row in rows:
        doi = str(row.get("doi", "")).strip()
        if not doi:
            continue

        landing_url = f"https://doi.org/{doi}" if doi else ""
        entry = {
            "doi":          doi,
            "title":        str(row.get("title", ""))[:300],
            "year":         str(row.get("year", "")),
            "category":     category or str(row.get("category", "")),
            "landing_url":  str(row.get("landing_url", landing_url)),
            "status":       "pending",
            "reason":       str(row.get("reason", row.get("download_error", "")))[:200],
            "last_checked": today,
            "notes":        "",
        }

        mask = df["doi"] == doi
        if mask.any():
            existing_status = df.loc[mask, "status"].iloc[0]
            if existing_status not in _RESOLVED:
                for col in ("title", "year", "category", "landing_url", "reason", "last_checked"):
                    df.loc[mask, col] = entry[col]
        else:
            df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
            added += 1

    save(df)
    return added


def mark_downloaded(dois: List[str]) -> None:
    """Marca DOIs como descargados en el registro (limpia entradas pendientes)."""
    if not dois or not REGISTRY_PATH.exists():
        return
    df = load()
    today = date.today().isoformat()
    for doi in dois:
        mask = df["doi"] == doi
        if mask.any():
            df.loc[mask, "status"] = "downloaded"
            df.loc[mask, "last_checked"] = today
    save(df)


def _corpus_dois(categorias_dir: Optional[Path] = None) -> Set[str]:
    """DOIs (normalizados: strip+lower) presentes en papers_metadata.jsonl de
    todas las CANONICAL_CATEGORIES — para cotejar contra el registro."""
    from utils.constants import CANONICAL_CATEGORIES
    base = Path(categorias_dir) if categorias_dir else CATEGORIAS_DIR
    dois: Set[str] = set()
    for cat in CANONICAL_CATEGORIES:
        jsonl = base / cat / "metadata" / "papers_metadata.jsonl"
        if not jsonl.exists():
            continue
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    rec = json.loads(s)
                except ValueError:
                    continue
                doi = str(rec.get("doi") or "").strip().lower()
                if doi:
                    dois.add(doi)
    return dois


def reconcile_with_corpus(categorias_dir: Optional[Path] = None) -> int:
    """Marca 'downloaded' los DOI 'pending' del registro que YA están en el
    corpus (papers_metadata.jsonl de alguna categoría).

    mark_downloaded() solo la llama 3a_download_pdfs.py; un DOI ingestado por
    otra vía (p.ej. PDF subido a mano, source_type="manual") nunca pasa por
    ahí y se queda "pending" para siempre aunque el paper ya exista. Esto
    cierra ese hueco. No toca papers_metadata.jsonl, solo el registro.
    Devuelve el nº de filas reconciliadas."""
    if not REGISTRY_PATH.exists():
        return 0
    df = load()
    pending_mask = df["status"] == "pending"
    if not pending_mask.any():
        return 0
    corpus = _corpus_dois(categorias_dir)
    if not corpus:
        return 0
    doi_norm = df["doi"].astype(str).str.strip().str.lower()
    match_mask = pending_mask & doi_norm.isin(corpus)
    affected = int(match_mask.sum())
    if affected:
        today = date.today().isoformat()
        df.loc[match_mask, "status"] = "downloaded"
        df.loc[match_mask, "last_checked"] = today
        df.loc[match_mask, "notes"] = ("reconciliado: DOI ya en el corpus "
                                        "(ingesta fuera de 3a_download_pdfs.py)")
        save(df)
    return affected


def pending_active(df: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Filas 'pending' que siguen activas: snooze_until vacío o ya vencido.

    Fuente única de verdad de "qué es un pendiente activo" — la usan tanto
    el email semanal (run_weekly_scopus.py) como la página de gestión, para
    que no diverjan sobre qué DOIs se consideran pendientes.
    """
    if today is None:
        today = date.today()
    today_iso = today.isoformat()
    snooze = df["snooze_until"].astype(str).str.strip()
    is_active_snooze = (snooze == "") | (snooze <= today_iso)
    return df[(df["status"] == "pending") & is_active_snooze]


def snooze(dois: List[str], years: int = 2, note: str = "") -> int:
    """Pospone `dois` fijando snooze_until = hoy + years*365 días.

    No cambia `status` (sigue 'pending'); pending_active() es quien decide
    si una fila pospuesta debe salir en el email. Devuelve el nº de filas
    afectadas.
    """
    if not dois:
        return 0
    df = load()
    mask = df["doi"].isin(dois)
    affected = int(mask.sum())
    if affected:
        until = (date.today() + timedelta(days=365 * years)).isoformat()
        df.loc[mask, "snooze_until"] = until
        if note:
            df.loc[mask, "notes"] = note
        save(df)
    return affected


def unsnooze(dois: List[str]) -> int:
    """Reactiva `dois` pospuestos (snooze_until = ""). Devuelve filas afectadas."""
    if not dois:
        return 0
    df = load()
    mask = df["doi"].isin(dois)
    affected = int(mask.sum())
    if affected:
        df.loc[mask, "snooze_until"] = ""
        save(df)
    return affected


def block(dois: List[str], reason: str = "", rows: Optional[List[Dict]] = None) -> int:
    """Veta `dois`: status='blocked' → 3a_download_pdfs.py no los volverá a
    intentar y pending_active() los deja fuera del email semanal.

    Inserta fila nueva si el DOI no está en el registro: el caso real es un DOI
    que se descargó bien y por tanto nunca pasó por upsert() (que solo registra
    fallos). `rows` (list de dicts con doi/title/year/category) permite rellenar
    los metadatos de esas filas nuevas.

    Devuelve el nº de DOIs vetados (actualizados + insertados).
    """
    if not dois:
        return 0
    df = load()
    today = date.today().isoformat()
    reason = str(reason or "")[:200]
    meta = {_norm(r.get("doi")): r for r in (rows or []) if _norm(r.get("doi"))}

    doi_norm = df["doi"].astype(str).str.strip().str.lower()
    affected = 0
    new_entries: List[Dict] = []

    for doi in dois:
        key = _norm(doi)
        if not key:
            continue
        mask = doi_norm == key
        if mask.any():
            df.loc[mask, "status"] = "blocked"
            df.loc[mask, "snooze_until"] = ""
            df.loc[mask, "reason"] = reason
            df.loc[mask, "last_checked"] = today
        else:
            src = meta.get(key, {})
            raw_doi = str(src.get("doi") or doi).strip()
            new_entries.append({
                "doi":          raw_doi,
                "title":        str(src.get("title", ""))[:300],
                "year":         str(src.get("year", "")),
                "category":     str(src.get("category", "")),
                "landing_url":  str(src.get("landing_url", f"https://doi.org/{raw_doi}")),
                "status":       "blocked",
                "reason":       reason,
                "last_checked": today,
                "notes":        "vetado manualmente (no estaba en el registro)",
                "snooze_until": "",
            })
        affected += 1

    if new_entries:
        df = pd.concat([df, pd.DataFrame(new_entries)], ignore_index=True)
    if affected:
        save(df)
    return affected


def unblock(dois: List[str]) -> int:
    """Levanta el veto: 'blocked' → 'pending'. Devuelve filas afectadas."""
    if not dois:
        return 0
    df = load()
    keys = {_norm(d) for d in dois if _norm(d)}
    if not keys:
        return 0
    doi_norm = df["doi"].astype(str).str.strip().str.lower()
    mask = doi_norm.isin(keys) & (df["status"] == "blocked")
    affected = int(mask.sum())
    if affected:
        df.loc[mask, "status"] = "pending"
        df.loc[mask, "last_checked"] = date.today().isoformat()
        df.loc[mask, "notes"] = "veto levantado: reactivado para descarga"
        save(df)
    return affected


def blocked_dois() -> Set[str]:
    """DOIs vetados, normalizados (strip+lower) para comparar contra el CSV
    de entrada de 3a_download_pdfs.py."""
    if not REGISTRY_PATH.exists():
        return set()
    df = load()
    blocked = df[df["status"] == "blocked"]["doi"].astype(str)
    return {_norm(d) for d in blocked if _norm(d)}