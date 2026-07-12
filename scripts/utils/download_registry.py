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

from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

import pandas as pd

NAS_ROOT = Path("/Volumes/research")
REGISTRY_PATH = NAS_ROOT / "metadatos" / "pendientes_descarga.csv"

_COLS = [
    "doi", "title", "year", "category",
    "landing_url", "status", "reason", "last_checked", "notes",
    "snooze_until",
]

# Estados que se consideran resueltos (no se sobreescriben al hacer upsert)
_RESOLVED = {"downloaded", "manual", "duplicate", "wrong_document"}


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