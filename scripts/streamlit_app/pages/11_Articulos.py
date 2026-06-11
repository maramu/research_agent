# -*- coding: utf-8 -*-
"""
11_Articulos.py — Catálogo bibliográfico filtrable (privado y público).

Dos secciones:
  A) Tabla resumen por categoría (mismas columnas que la portada / Pendientes).
  B) Listado de artículos de una categoría (o todas) con filtros por texto
     (título/DOI/autor), año, revista y solo-con-DOI; DOI clicable, export CSV
     y métricas de la selección.

No ejecuta nada sobre el corpus: solo lee papers_metadata.jsonl por categoría.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Permitir import de app_utils.py de la carpeta padre (mismo patrón que 2_RAG.py)
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for _d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import (
    CATEGORIAS_DIR, check_password, is_public_app,
    list_existing_categories, get_categories_summary,
)

st.set_page_config(page_title="Artículos", page_icon="📋", layout="wide")

_pwd = "PUBLIC_APP_PASSWORD" if is_public_app() else "PRIVATE_APP_PASSWORD"
if not check_password(_pwd):
    st.stop()

st.title("📋 Catálogo de artículos")

PUBLIC = is_public_app()


# ───────────────────────────────────────────────────────────────────────────
# SECCIÓN A — Tabla resumen por categoría
# ───────────────────────────────────────────────────────────────────────────

st.subheader("Resumen por categoría")


@st.cache_data(show_spinner="Calculando resumen por categoría…")
def _summary_rows(nonce: int) -> list[dict]:
    return get_categories_summary()


summary = _summary_rows(0)
if summary:
    st.dataframe(
        pd.DataFrame(summary),
        hide_index=True,
        use_container_width=True,
        column_config={
            "PDFs": st.column_config.NumberColumn(width="small"),
            "MD limpio": st.column_config.NumberColumn(width="small"),
            "Resúmenes": st.column_config.NumberColumn(width="small"),
            "Chunks": st.column_config.NumberColumn(width="small"),
            "Metadata": st.column_config.NumberColumn(width="small"),
            "Paquetes": st.column_config.NumberColumn(width="small"),
            "Brechas": st.column_config.TextColumn(width="large"),
        },
    )
else:
    st.info("No hay categorías con PDFs en el NAS.")

st.divider()


# ───────────────────────────────────────────────────────────────────────────
# SECCIÓN B — Listado de artículos
# ───────────────────────────────────────────────────────────────────────────

st.subheader("Listado de artículos")


@st.cache_data(show_spinner="Cargando artículos…")
def load_articles(category: str, mtime: float) -> list[dict]:
    meta = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
    rows = []
    if meta.exists():
        with meta.open(encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    d = json.loads(s)
                except Exception:
                    continue
                authors = d.get("authors")
                if isinstance(authors, list):
                    authors = ", ".join(str(a) for a in authors)
                refs = d.get("references")
                n_refs = len(refs) if isinstance(refs, list) else (d.get("n_references") or "")
                rows.append({
                    "category":      category,
                    "title":         d.get("title") or "",
                    "year":          d.get("year"),
                    "journal":       d.get("journal") or d.get("venue") or "",
                    "doi":           d.get("doi") or "",
                    "authors":       authors or "",
                    "n_refs":        n_refs,
                    "quality_score": d.get("quality_score"),
                    "source_type":   d.get("source_type") or "",
                    "access_type":   d.get("access_type") or "",
                    "paper_id":      d.get("paper_id") or d.get("stable_id") or "",
                })
    return rows


def _meta_mtime(category: str) -> float:
    meta = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
    return meta.stat().st_mtime if meta.exists() else 0.0


categories = list_existing_categories()
if not categories:
    st.info("No hay categorías en el NAS.")
    st.stop()

# ── Controles ────────────────────────────────────────────────────────────────
TODAS = "(Todas)"
sel = st.selectbox("Categoría", options=[TODAS] + categories, index=0)

if sel == TODAS:
    rows: list[dict] = []
    for cat in categories:
        rows.extend(load_articles(cat, _meta_mtime(cat)))
else:
    rows = load_articles(sel, _meta_mtime(sel))

if not rows:
    if sel == TODAS:
        st.info("No hay artículos con metadata (papers_metadata.jsonl) en ninguna categoría.")
    else:
        st.info(f"La categoría `{sel}` no tiene papers_metadata.jsonl o está vacío.")
    st.stop()

c1, c2 = st.columns([2, 1])
with c1:
    txt = st.text_input(
        "Búsqueda (título, DOI o autores)",
        value="",
        placeholder="Ej: anaerobic digestion, 10.1016/…, García",
    )
with c2:
    journals = sorted({r["journal"] for r in rows if r["journal"]})
    sel_journals = st.multiselect("Revista (opcional)", options=journals, default=[])

c3, c4 = st.columns([2, 1])
with c3:
    years = [int(r["year"]) for r in rows if isinstance(r["year"], (int, float)) or
             (isinstance(r["year"], str) and r["year"].strip().isdigit())]
    if years:
        y_min, y_max = min(years), max(years)
        usar_year = st.checkbox("Filtrar por año", value=False)
        if usar_year and y_min < y_max:
            ys, ye = st.slider("Rango de años", y_min, y_max, (y_min, y_max))
        elif usar_year:
            ys = ye = y_min
        else:
            ys = ye = None
    else:
        ys = ye = None
with c4:
    solo_doi = st.checkbox("Solo con DOI", value=False)


# ── Aplicar filtros en cascada ───────────────────────────────────────────────
def _year_int(v):
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


filtered = rows
if txt.strip():
    q = txt.strip().lower()
    filtered = [
        r for r in filtered
        if q in str(r["title"]).lower()
        or q in str(r["doi"]).lower()
        or q in str(r["authors"]).lower()
    ]
if sel_journals:
    jset = set(sel_journals)
    filtered = [r for r in filtered if r["journal"] in jset]
if ys is not None and ye is not None:
    filtered = [
        r for r in filtered
        if (_y := _year_int(r["year"])) is not None and ys <= _y <= ye
    ]
if solo_doi:
    filtered = [r for r in filtered if str(r["doi"]).strip()]

st.caption(f"**{len(filtered)}** artículo(s) tras filtrar (de {len(rows)} cargados).")

if not filtered:
    st.warning("Sin resultados con esos filtros. Prueba aflojando los filtros.")
    st.stop()

# ── Tira de métricas ─────────────────────────────────────────────────────────
n_art = len(filtered)
n_doi = sum(1 for r in filtered if str(r["doi"]).strip())
pct_doi = round(100 * n_doi / n_art) if n_art else 0
f_years = [y for r in filtered if (y := _year_int(r["year"])) is not None]
qscores = [float(r["quality_score"]) for r in filtered
           if isinstance(r["quality_score"], (int, float))]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Artículos", n_art)
m2.metric("% con DOI", f"{pct_doi}%")
m3.metric("Años", f"{min(f_years)}–{max(f_years)}" if f_years else "—")
m4.metric("Calidad media", f"{sum(qscores) / len(qscores):.2f}" if qscores else "—")

# ── Tabla ────────────────────────────────────────────────────────────────────
df = pd.DataFrame(filtered)
df["doi_url"] = df["doi"].apply(
    lambda d: f"https://doi.org/{d}" if str(d).strip() else "")

if PUBLIC:
    cols = ["title", "year", "journal", "doi_url"]
else:
    cols = ["title", "year", "journal", "doi_url", "authors", "n_refs",
            "quality_score", "source_type", "access_type", "paper_id"]

col_config = {
    "title":         st.column_config.TextColumn("Título", width="large"),
    "year":          st.column_config.NumberColumn("Año", width="small"),
    "journal":       st.column_config.TextColumn("Revista"),
    "doi_url":       st.column_config.LinkColumn(
        "DOI", display_text=r"https://doi\.org/(.+)"),
    "authors":       st.column_config.TextColumn("Autores"),
    "n_refs":        st.column_config.NumberColumn("Refs", width="small"),
    "quality_score": st.column_config.NumberColumn("Calidad", width="small"),
    "source_type":   st.column_config.TextColumn("Origen"),
    "access_type":   st.column_config.TextColumn("Acceso"),
    "paper_id":      st.column_config.TextColumn("paper_id"),
}

st.dataframe(
    df[cols],
    hide_index=True,
    use_container_width=True,
    column_config=col_config,
)

# ── Export CSV de la vista filtrada ──────────────────────────────────────────
_today = datetime.now().strftime("%Y-%m-%d")
_slug = "todas" if sel == TODAS else sel
csv_bytes = df[cols].to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ Exportar CSV (vista filtrada)",
    data=csv_bytes,
    file_name=f"articulos_{_slug}_{_today}.csv",
    mime="text/csv",
)
