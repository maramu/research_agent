# -*- coding: utf-8 -*-
"""
15_Pendientes.py — Posponer o VETAR DOIs pendientes, para que dejen de salir
en el email semanal (solo instancia privada).

  · Posponer (snooze_until): sigue 'pending', vuelve a aparecer en N años.
  · Vetar (status='blocked'): permanente. 3a_download_pdfs.py lo salta en la
    ingesta y pending_active() lo deja fuera del email. Reversible con
    "Reactivar" desde la sección Vetados.

Si el DOI vetado YA estaba en el corpus, desde aquí se puede purgar con
pipeline.purge_paper_by_doi() — borrado DURO, sin cuarentena.

download_registry.pending_active() es la única fuente de verdad de "qué es un
pendiente activo", usada tanto aquí como en run_weekly_scopus.py.
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

n_reconciliados = download_registry.reconcile_with_corpus()
if n_reconciliados:
    st.info(f"🔄 {n_reconciliados} DOI(s) reconciliado(s) automáticamente: "
            "ya estaban en el corpus (ingesta manual u otra vía distinta de "
            "la descarga automática) y se han marcado como descargados.")


# ── Purga del corpus (borrado duro) ───────────────────────────────────────────

def _purge_ui(doi: str) -> None:
    """Flujo de eliminación del corpus para un DOI vetado que ya estaba dentro:
    preview → inventario → checkbox de confirmación → borrado duro."""
    from pipeline import purge_paper_by_doi  # import perezoso: toca el NAS

    slug = doi.replace("/", "_").replace(".", "_")
    prev_key = f"purge_prev_{slug}"

    if st.button("🗑️ Eliminar del corpus", key=f"purge_btn_{slug}"):
        st.session_state[prev_key] = purge_paper_by_doi(doi, apply=False)

    prev = st.session_state.get(prev_key)
    if not prev:
        return

    if not prev.get("found"):
        st.info(f"{doi}: no se ha encontrado en papers_metadata.jsonl de ninguna categoría.")
        return

    st.markdown(f"**{prev['category']} / {prev['paper_id'] or '(sin id)'}** — {prev['title']}")
    paths = prev.get("paths", [])
    if paths:
        st.dataframe(
            [{"Fichero": p["path"], "KB": round(p["size"] / 1024)} for p in paths],
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("Sin artefactos en disco: solo el registro de metadata.")
    st.caption("Se eliminará además su línea de papers_metadata.jsonl (con backup .bak) "
               "y su paper_id de indexed_papers.json.")

    ok = st.checkbox("Entiendo que el borrado es irreversible",
                     key=f"purge_ok_{slug}")
    if st.button("💥 Borrar definitivamente", key=f"purge_apply_{slug}",
                 disabled=not ok, type="primary"):
        res = purge_paper_by_doi(doi, category=prev["category"], apply=True)
        st.success(f"✓ {len(res['removed'])} elemento(s) eliminado(s) de "
                   f"{res['category']}.")
        st.warning(
            f"⚠️ Los vectores de este paper **siguen en FAISS** (item 65): "
            f"reindexa la categoría **{res['category']}** con `--force` desde "
            f"6_Mantenimiento para que deje de aparecer en las búsquedas."
        )
        st.session_state.pop(prev_key, None)


def _avisar_si_en_corpus(dois: list) -> None:
    """Tras vetar, avisa de los DOIs que ya estaban en el corpus y ofrece purga."""
    if not dois:
        return
    try:
        corpus = download_registry._corpus_dois()
    except Exception as e:
        st.caption(f"No se pudo comprobar el corpus: {e}")
        return
    en_corpus = [d for d in dois if str(d).strip().lower() in corpus]
    if not en_corpus:
        return
    st.warning(f"⚠️ {len(en_corpus)} DOI(s) vetado(s) YA están en el corpus. "
               "El veto solo impide futuras descargas: el paper sigue indexado.")
    for d in en_corpus:
        with st.expander(f"🗑️ {d}", expanded=len(en_corpus) == 1):
            _purge_ui(d)


mostrar_pospuestos = st.toggle("Mostrar pospuestos", value=False)

df = download_registry.load()
pending_all = df[df["status"] == "pending"]
view = pending_all if mostrar_pospuestos else download_registry.pending_active(df)

if view.empty:
    st.info("No hay DOIs pendientes que mostrar.")

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

sel_dois = edited.loc[edited["Sel"], "doi"].tolist() if not edited.empty else []
st.caption(f"{len(sel_dois)} seleccionado(s).")

motivo = st.text_input(
    "Motivo del veto (opcional)", key="motivo_veto",
    placeholder="p.ej. fuera de alcance / paper retractado / sin acceso institucional",
)

c1, c2, c3 = st.columns(3)
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
with c3:
    if st.button("🚫 Vetar (no volver a descargar)", disabled=not sel_dois,
                 use_container_width=True):
        n = download_registry.block(sel_dois, reason=motivo)
        st.session_state["vetados_recientes"] = list(sel_dois)
        st.success(f"✓ {n} DOI(s) vetados: no se volverán a intentar descargar.")

st.caption("Pospuesto = no aparece en el email semanal hasta la fecha snooze_until. "
           "Vetado = no vuelve a intentarse nunca (reversible desde 'Vetados').")

_avisar_si_en_corpus(st.session_state.get("vetados_recientes", []))


# ── Vetar un DOI que no está en la tabla ──────────────────────────────────────

st.divider()
st.subheader("🚫 Vetar un DOI suelto")
st.caption("Para DOIs que no figuran arriba (p.ej. ya descargados): se crea la "
           "entrada en el registro con status 'blocked'.")

cd1, cd2 = st.columns([2, 3])
with cd1:
    doi_suelto = st.text_input("DOI", key="doi_suelto", placeholder="10.1016/j.xxx.2026.123456")
with cd2:
    motivo_suelto = st.text_input("Motivo (opcional)", key="motivo_suelto")

if st.button("🚫 Vetar este DOI", disabled=not doi_suelto.strip()):
    n = download_registry.block([doi_suelto.strip()], reason=motivo_suelto)
    st.session_state["vetados_recientes"] = [doi_suelto.strip()]
    st.success(f"✓ {n} DOI vetado.")
    _avisar_si_en_corpus([doi_suelto.strip()])


# ── Vetados ───────────────────────────────────────────────────────────────────

st.divider()
st.subheader("🚫 Vetados")

blocked_df = df[df["status"] == "blocked"]
if blocked_df.empty:
    st.caption("Ningún DOI vetado.")
else:
    blocked_view = blocked_df.copy()
    blocked_view.insert(0, "Sel", False)
    edited_blocked = st.data_editor(
        blocked_view,
        column_config={
            "Sel":          st.column_config.CheckboxColumn("Sel", width="small", default=False),
            "landing_url":  st.column_config.LinkColumn("DOI", display_text="🔗 abrir"),
            "title":        st.column_config.TextColumn("Título", width="large", disabled=True),
            "year":         st.column_config.TextColumn("Año", width="small", disabled=True),
            "category":     st.column_config.TextColumn("Categoría", disabled=True),
            "reason":       st.column_config.TextColumn("Motivo del veto", width="large", disabled=True),
            "last_checked": st.column_config.TextColumn("Vetado el", disabled=True),
        },
        column_order=["Sel", "landing_url", "title", "year", "category",
                      "reason", "last_checked"],
        hide_index=True,
        use_container_width=True,
        key="vetados_editor",
    )
    sel_blocked = edited_blocked.loc[edited_blocked["Sel"], "doi"].tolist()

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🔄 Reactivar", disabled=not sel_blocked, use_container_width=True):
            n = download_registry.unblock(sel_blocked)
            st.success(f"✓ {n} DOI(s) reactivados (vuelven a 'pending').")
            st.rerun()
    with b2:
        if st.button("🔎 Comprobar si están en el corpus", disabled=not sel_blocked,
                     use_container_width=True):
            st.session_state["vetados_recientes"] = list(sel_blocked)
            st.rerun()
