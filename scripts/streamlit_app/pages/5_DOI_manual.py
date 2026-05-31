# -*- coding: utf-8 -*-
"""
5_📄_DOI_manual.py — Editor de /Volumes/research/metadatos/doi_manual.xlsx.

Edición interactiva de DOIs y estados con st.data_editor.
Los cambios se guardan sobreescribiendo el fichero con backup previo (.bak).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

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
# Constantes
# ---------------------------------------------------------------------------

STATUS_OPTIONS = ["", "pending", "done", "not_found", "manual"]
# Columnas siempre deshabilitadas (identificadores de fichero)
DISABLED_COLS  = {"nombre_archivo", "filename"}

# ---------------------------------------------------------------------------
# Carga inicial en session_state
# ---------------------------------------------------------------------------

def _load_sheets() -> dict[str, pd.DataFrame]:
    all_sheets = pd.read_excel(str(DOI_MANUAL_XLSX), sheet_name=None, engine="openpyxl")
    for df in all_sheets.values():
        if "status" not in df.columns:
            df["status"] = ""
        df["status"] = df["status"].fillna("")
    return all_sheets


if "doi_sheets" not in st.session_state:
    st.session_state["doi_sheets"] = _load_sheets()

# Versión del editor: se incrementa al añadir fila para forzar reset del widget
if "doi_editor_version" not in st.session_state:
    st.session_state["doi_editor_version"] = 0

# ---------------------------------------------------------------------------
# Cabecera: métricas + botón recargar
# ---------------------------------------------------------------------------

sheets = st.session_state["doi_sheets"]
mtime  = DOI_MANUAL_XLSX.stat().st_mtime
total_rows = sum(len(df) for df in sheets.values())

hcols = st.columns(4)
hcols[0].metric("Hojas", len(sheets))
hcols[1].metric("Modificado", pd.Timestamp(mtime, unit="s").strftime("%Y-%m-%d %H:%M"))
hcols[2].metric("Filas totales", total_rows)
if hcols[3].button("🔄 Recargar desde disco"):
    for _k in ("doi_sheets", "doi_editor_version"):
        st.session_state.pop(_k, None)
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Selector de hoja
# ---------------------------------------------------------------------------

if len(sheets) == 1:
    sheet_name = next(iter(sheets.keys()))
else:
    sheet_name = st.selectbox("Hoja", options=list(sheets.keys()))

# Referencia directa (no copia) para que .update() propague a session_state
df_full = sheets[sheet_name]

st.markdown(f"**Hoja `{sheet_name}`** — {len(df_full)} filas × {len(df_full.columns)} columnas")

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

with st.expander("🔍 Filtros", expanded=True):
    fcols = st.columns(2)
    with fcols[0]:
        free_text = st.text_input(
            "Búsqueda libre (en todas las columnas de texto)",
            placeholder="DOI, nombre de archivo…",
            key="doi_free_text",
        )
    with fcols[1]:
        unique_statuses = sorted(s for s in df_full["status"].astype(str).unique() if s)
        selected_statuses = st.multiselect(
            "Filtrar por `status`",
            options=unique_statuses,
            default=[],
            key="doi_status_filter",
        )

# Construir máscara de filtro
mask = pd.Series(True, index=df_full.index)

if selected_statuses:
    mask &= df_full["status"].astype(str).isin(selected_statuses)

if free_text:
    needle = free_text.lower()
    text_mask = pd.Series(False, index=df_full.index)
    for col in df_full.select_dtypes(include=["object", "string"]).columns:
        text_mask |= df_full[col].astype(str).str.lower().str.contains(needle, na=False)
    mask &= text_mask

df_view = df_full.loc[mask].copy()
st.markdown(f"**Resultado**: {len(df_view)} filas")

# ---------------------------------------------------------------------------
# column_config
# ---------------------------------------------------------------------------

col_cfg: dict = {}
for col in df_full.columns:
    if col in DISABLED_COLS:
        col_cfg[col] = st.column_config.TextColumn(col, disabled=True)
    elif col == "status":
        col_cfg[col] = st.column_config.SelectboxColumn(
            "status",
            options=STATUS_OPTIONS,
            required=False,
        )
    else:
        col_cfg[col] = st.column_config.TextColumn(col, disabled=False)

# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

# Preservamos los índices originales para poder propagar ediciones a df_full.
# reset_index(drop=True) evita que data_editor muestre el índice numérico de
# pandas (que no coincide con la fila visual cuando se filtra).
original_index = df_view.index.tolist()

edited_view = st.data_editor(
    df_view.reset_index(drop=True),
    column_config=col_cfg,
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
    key=f"doi_editor_{st.session_state['doi_editor_version']}",
)

# Restaurar índices originales y propagar ediciones a df_full en session_state
edited_view.index = original_index
df_full.update(edited_view)

# ---------------------------------------------------------------------------
# Acciones: añadir fila y guardar
# ---------------------------------------------------------------------------

action_cols = st.columns([1, 1, 4])

with action_cols[0]:
    if st.button("➕ Añadir fila", use_container_width=True):
        empty_row = pd.DataFrame([{col: "" for col in df_full.columns}])
        sheets[sheet_name] = pd.concat([df_full, empty_row], ignore_index=True)
        st.session_state["doi_editor_version"] += 1
        st.rerun()

with action_cols[1]:
    if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
        try:
            bak = DOI_MANUAL_XLSX.with_name(DOI_MANUAL_XLSX.name + ".bak")
            bak.write_bytes(DOI_MANUAL_XLSX.read_bytes())

            with pd.ExcelWriter(str(DOI_MANUAL_XLSX), engine="openpyxl") as writer:
                for sname, sdf in sheets.items():
                    sdf.to_excel(writer, sheet_name=sname, index=False)

            n_saved = sum(len(sdf) for sdf in sheets.values())
            st.success(
                f"✓ Guardado — {n_saved} filas escritas. "
                f"Backup en `{bak.name}`."
            )
        except Exception as e:
            st.error(f"Error al guardar: {e}")

st.divider()

# ---------------------------------------------------------------------------
# Descarga CSV de la vista filtrada
# ---------------------------------------------------------------------------

st.download_button(
    "⬇ Descargar vista filtrada (CSV)",
    data=df_view.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"doi_manual_{sheet_name}_filtrado.csv",
    mime="text/csv",
    use_container_width=False,
)
