# -*- coding: utf-8 -*-
"""
15_Pendientes.py — Posponer DOIs pendientes sin interés/acceso 2 años, para
que dejen de salir en el email semanal (solo instancia privada).

El snooze se guarda en pendientes_descarga.csv (snooze_until) y sobrevive a
la re-ejecución de Scopus: download_registry.pending_active() es la única
fuente de verdad de "qué es un pendiente activo", usada tanto aquí como en
run_weekly_scopus.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for _d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import check_password, is_public_app
from utils import download_registry

st.set_page_config(page_title="Pendientes", page_icon="😴", layout="wide")

if is_public_app():
    st.stop()

if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()

st.title("😴 DOIs pendientes")

mostrar_pospuestos = st.toggle("Mostrar pospuestos", value=False)

df = download_registry.load()
pending_all = df[df["status"] == "pending"]
view = pending_all if mostrar_pospuestos else download_registry.pending_active(df)

if view.empty:
    st.info("No hay DOIs pendientes que mostrar.")
    st.stop()

st.caption(f"{len(view)} DOI(s) pendiente(s)"
           + (" (incluye pospuestos)." if mostrar_pospuestos
              else " activos (no pospuestos)."))

view = view.copy()
view.insert(0, "Sel", False)

col_cfg = {
    "Sel":          st.column_config.CheckboxColumn("Sel", width="small", default=False),
    "landing_url":  st.column_config.LinkColumn("DOI", display_text="🔗 abrir"),
    "title":        st.column_config.TextColumn("Título", width="large", disabled=True),
    "year":         st.column_config.TextColumn("Año", width="small", disabled=True),
    "category":     st.column_config.TextColumn("Categoría", disabled=True),
    "reason":       st.column_config.TextColumn("Motivo", width="large", disabled=True),
    "last_checked": st.column_config.TextColumn("Última revisión", disabled=True),
    "snooze_until": st.column_config.TextColumn("Pospuesto hasta", disabled=True),
}

edited = st.data_editor(
    view,
    column_config=col_cfg,
    column_order=["Sel", "landing_url", "title", "year", "category",
                  "reason", "last_checked", "snooze_until"],
    hide_index=True,
    use_container_width=True,
    key="pendientes_editor",
)

sel_dois = edited.loc[edited["Sel"], "doi"].tolist()
st.caption(f"{len(sel_dois)} seleccionado(s).")

c1, c2 = st.columns(2)
with c1:
    if st.button("😴 Posponer 2 años seleccionados", disabled=not sel_dois,
                 use_container_width=True):
        n = download_registry.snooze(sel_dois, years=2)
        st.success(f"✓ {n} DOI(s) pospuestos 2 años.")
        st.rerun()
with c2:
    if st.button("🔄 Reactivar seleccionados", disabled=not sel_dois,
                 use_container_width=True):
        n = download_registry.unsnooze(sel_dois)
        st.success(f"✓ {n} DOI(s) reactivados.")
        st.rerun()

st.caption("Pospuesto = no aparece en el email semanal hasta la fecha snooze_until.")
