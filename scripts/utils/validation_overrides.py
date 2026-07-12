# -*- coding: utf-8 -*-
"""
Registro persistente de campos de metadata "verificados" por el usuario.

Cuando una sugerencia de validate_metadata.py (Crossref, Nivel 2) o de las
adopciones masivas de 11_Articulos.py se revisa y se descarta como incorrecta,
se marca aquí (category, paper_id, field) para que NO vuelva a aparecer:
- validate_metadata.py filtra estos pares antes de escribir el sidecar
  (validation_<cat>.jsonl) → no se reprocesan en el origen.
- 11_Articulos.py los filtra también en cliente (oculta al instante, sin
  esperar a re-validar) y evita re-consultar Crossref para ellos en las
  adopciones masivas.

Ruta fija: /Volumes/research/metadatos/validation_overrides.csv
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Set, Tuple

import pandas as pd

NAS_ROOT = Path("/Volumes/research")
OVERRIDES_PATH = NAS_ROOT / "metadatos" / "validation_overrides.csv"

_COLS = ["category", "paper_id", "field", "date", "note"]

# Campos sobre los que tiene sentido "mantener" (llevan sugerencia Crossref
# accionable en el listado por-campo o en una adopción masiva). doi/crossref_miss
# quedan fuera: ahí no hay botón "adoptar/mantener".
FIELDS = {"title", "journal", "year", "authors"}


def load() -> pd.DataFrame:
    """Carga el registro. Devuelve DataFrame vacío si no existe."""
    if OVERRIDES_PATH.exists():
        df = pd.read_csv(OVERRIDES_PATH, dtype=str).fillna("")
        for col in _COLS:
            if col not in df.columns:
                df[col] = ""
        return df[_COLS]
    return pd.DataFrame(columns=_COLS)


def save(df: pd.DataFrame) -> None:
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OVERRIDES_PATH, index=False, encoding="utf-8-sig")


def dismissed_set(category: str) -> Set[Tuple[str, str]]:
    """{(paper_id, field), ...} marcados como verificados en `category`."""
    df = load()
    sub = df[df["category"] == category]
    return set(zip(sub["paper_id"], sub["field"]))


def dismiss(category: str, paper_id: str, field: str, note: str = "") -> int:
    """Marca (category, paper_id, field) como verificado — no se volverá a
    sugerir. Upsert idempotente (re-marcar solo refresca fecha/nota).
    Devuelve 1 si se aplicó, 0 si `field` no es uno de FIELDS."""
    if field not in FIELDS or not paper_id:
        return 0
    df = load()
    mask = ((df["category"] == category) & (df["paper_id"] == paper_id)
             & (df["field"] == field))
    today = date.today().isoformat()
    if mask.any():
        df.loc[mask, "date"] = today
        if note:
            df.loc[mask, "note"] = note
    else:
        row = {"category": category, "paper_id": paper_id, "field": field,
               "date": today, "note": note}
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save(df)
    return 1


def undismiss(category: str, paper_id: str, field: str) -> int:
    """Quita la marca de verificado. Devuelve el nº de filas eliminadas."""
    df = load()
    mask = ((df["category"] == category) & (df["paper_id"] == paper_id)
             & (df["field"] == field))
    affected = int(mask.sum())
    if affected:
        save(df[~mask])
    return affected


def list_dismissed(category: str) -> pd.DataFrame:
    """Filas de `category` (más recientes primero) — para revisar/revertir."""
    df = load()
    sub = df[df["category"] == category]
    return sub.sort_values("date", ascending=False)
