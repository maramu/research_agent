# -*- coding: utf-8 -*-
"""
8_Exportar.py — Exportar bibliografía de una categoría a BibTeX / RIS / CSV.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from app_utils import (
    CATEGORIAS_DIR, check_nas, list_existing_categories,
)
from utils.export_refs import load_papers, to_bibtex, to_ris, to_csv_str

st.set_page_config(page_title="Exportar", page_icon="📤", layout="wide")
st.title("📤 Exportar bibliografía")

nas_ok, nas_msg = check_nas()
if not nas_ok:
    st.error(f"NAS no montado: {nas_msg}")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Selección")
    category = st.selectbox("Categoría", options=list_existing_categories())

    st.subheader("Filtros")
    col_a, col_b = st.columns(2)
    year_min = col_a.number_input("Año desde", 1990, 2030, 2015, 1)
    year_max = col_b.number_input("Año hasta", 1990, 2030, 2030, 1)
    doi_only    = st.checkbox("Solo papers con DOI", value=True)
    min_quality = st.slider("Quality score mínimo", 0.0, 1.0, 0.0, 0.05,
                            help="0 = todos los papers")

# ── Carga y filtrado ──────────────────────────────────────────────────────────
jsonl = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
if not jsonl.exists():
    st.warning(
        f"No hay metadata para `{category}`. "
        "Ejecuta `4_extract_metadata.py` desde Mantenimiento."
    )
    st.stop()

all_papers = load_papers(jsonl)
filtered = []
for m in all_papers:
    if doi_only and not m.get("doi"):
        continue
    y = m.get("year")
    if y and not (year_min <= int(y) <= year_max):
        continue
    qs = m.get("quality_score")
    if min_quality > 0 and (qs is None or float(qs) < min_quality):
        continue
    filtered.append(m)

st.markdown(
    f"**{len(filtered)}** papers seleccionados "
    f"de {len(all_papers)} totales en `{category}`"
)

if not filtered:
    st.warning("Ningún paper cumple los filtros actuales.")
    st.stop()

# ── Vista previa ──────────────────────────────────────────────────────────────
rows = []
for m in filtered:
    aus = m.get("authors") or []
    au_str = "; ".join(a.get("full", "") for a in aus[:3] if a.get("full"))
    if len(aus) > 3:
        au_str += f" +{len(aus)-3}"
    rows.append({
        "Título":  (m.get("title") or "")[:80],
        "Autores": au_str,
        "Año":     m.get("year") or "—",
        "Journal": (m.get("journal") or "")[:50],
        "DOI":     m.get("doi") or "—",
        "Score":   m.get("quality_score", "—"),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ── Descargas ─────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Descargar")
stem = f"{category}_{year_min}-{year_max}"

c1, c2, c3 = st.columns(3)
c1.download_button("📚 BibTeX (.bib)", data=to_bibtex(filtered),
                   file_name=f"{stem}.bib", mime="text/plain")
c2.download_button("📄 RIS (.ris)",    data=to_ris(filtered),
                   file_name=f"{stem}.ris", mime="text/plain")
c3.download_button("📊 CSV (.csv)",    data=to_csv_str(filtered),
                   file_name=f"{stem}.csv", mime="text/csv")
