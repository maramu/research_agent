# -*- coding: utf-8 -*-
"""
5_📄_DOI_manual.py — Visor de /Volumes/research/metadatos/doi_manual.xlsx.

Solo lectura: filtros por columna y búsqueda libre. La edición se sigue
haciendo en Excel (decisión deliberada para evitar conflictos de bloqueo
con los scripts que escriben en este fichero).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Permitir import de utils.py de la carpeta padre
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import DOI_MANUAL_XLSX, check_nas

st.set_page_config(page_title="DOI manual", page_icon="📄", layout="wide")
st.title("📄 doi_manual.xlsx")

st.caption(f"Fichero: `{DOI_MANUAL_XLSX}`")

# ---------------------------------------------------------------------------
# Pre-checks
# ---------------------------------------------------------------------------

nas_ok, nas_msg = check_nas()
if not nas_ok:
    st.error(f"NAS no montado: {nas_msg}")
    st.stop()

if not DOI_MANUAL_XLSX.exists():
    st.warning(
        f"No existe `{DOI_MANUAL_XLSX}`. Aún no se ha generado "
        "(se crea al ejecutar `1_rename_papers_by_doi.py`)."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Carga (cache para no releer en cada interacción)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Leyendo doi_manual.xlsx…")
def load_doi_manual(path_str: str, mtime: float) -> dict[str, pd.DataFrame]:
    """Lee todas las hojas. mtime se incluye para invalidar caché al cambiar el fichero."""
    return pd.read_excel(path_str, sheet_name=None, engine="openpyxl")


mtime = DOI_MANUAL_XLSX.stat().st_mtime
sheets = load_doi_manual(str(DOI_MANUAL_XLSX), mtime)

# Cabecera con info del fichero
info_cols = st.columns(4)
info_cols[0].metric("Hojas", len(sheets))
info_cols[1].metric("Modificado", pd.Timestamp(mtime, unit="s").strftime("%Y-%m-%d %H:%M"))

# Total filas sumando hojas
total_rows = sum(len(df) for df in sheets.values())
info_cols[2].metric("Filas totales", total_rows)

if st.button("🔄 Recargar", use_container_width=False):
    st.cache_data.clear()
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Selector de hoja
# ---------------------------------------------------------------------------

if len(sheets) == 1:
    sheet_name = next(iter(sheets.keys()))
else:
    sheet_name = st.selectbox("Hoja", options=list(sheets.keys()))

df = sheets[sheet_name].copy()

st.markdown(f"**Hoja `{sheet_name}`** — {len(df)} filas × {len(df.columns)} columnas")

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

with st.expander("🔍 Filtros", expanded=True):
    fcols = st.columns(2)

    with fcols[0]:
        free_text = st.text_input(
            "Búsqueda libre (en todas las columnas de texto)",
            value="",
            placeholder="DOI, título, autor…",
        )

    with fcols[1]:
        # Si hay una columna 'estado' o similar, ofrecemos selector
        status_col = None
        for candidate in ["estado", "status", "categoria", "category", "fuente", "source"]:
            if candidate in df.columns:
                status_col = candidate
                break

        if status_col:
            unique_vals = sorted(df[status_col].dropna().astype(str).unique())
            selected = st.multiselect(
                f"Filtrar por `{status_col}`",
                options=unique_vals,
                default=[],
            )
            if selected:
                df = df[df[status_col].astype(str).isin(selected)]

# Búsqueda libre
if free_text:
    needle = free_text.lower()
    str_cols = df.select_dtypes(include=["object", "string"]).columns
    if len(str_cols) > 0:
        mask = pd.Series(False, index=df.index)
        for col in str_cols:
            mask |= df[col].astype(str).str.lower().str.contains(needle, na=False)
        df = df[mask]

# ---------------------------------------------------------------------------
# Tabla
# ---------------------------------------------------------------------------

st.markdown(f"**Resultado**: {len(df)} filas")

st.dataframe(
    df,
    hide_index=True,
    use_container_width=True,
    height=600,
)

# ---------------------------------------------------------------------------
# Descarga CSV de la vista filtrada
# ---------------------------------------------------------------------------

st.download_button(
    "⬇ Descargar vista filtrada (CSV)",
    data=df.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"doi_manual_{sheet_name}_filtrado.csv",
    mime="text/csv",
    use_container_width=False,
)
