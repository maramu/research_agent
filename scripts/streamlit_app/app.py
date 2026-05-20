# -*- coding: utf-8 -*-
"""
app.py — Portada de la interfaz Streamlit para research_agent.

Muestra:
  - Health checks (NAS, Ollama, GROBID)
  - Estado de las 8 categorías oficiales (PDFs, MDs, embeddings…)
  - Resumen del NAS (inbox, inbox_csv, fallidos)

Lanzar desde scripts/streamlit_app/:
    streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app_utils import (
    CANONICAL_CATEGORIES, CATEGORIAS_DIR, CONFIG_DIR, INBOX_DIR, INBOX_CSV_DIR,
    METADATOS_DIR, NAS_ROOT, OLLAMA_HOST, GROBID_URL,
    PIPELINE_AVAILABLE, PIPELINE_IMPORT_ERROR,
    check_grobid, check_nas, check_ollama,
    get_category_stats, human_status_icon, list_existing_categories,
)

st.set_page_config(
    page_title="research_agent",
    page_icon="🔬",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------

st.title("🔬 research_agent")
st.caption(
    "Panel de control del pipeline de ingesta y análisis de papers científicos. "
    "Usa la barra lateral para navegar entre flujos."
)

# Aviso si pipeline.py no se pudo importar
if not PIPELINE_AVAILABLE:
    st.error(
        f"⚠️ No se puede importar `pipeline.py`.\n\n"
        f"```\n{PIPELINE_IMPORT_ERROR}\n```\n\n"
        f"Verifica que la app está dentro de `scripts/streamlit_app/` "
        f"y que `pipeline.py` está en `scripts/`."
    )

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

st.subheader("Estado de servicios")

col1, col2, col3 = st.columns(3)

with col1:
    ok, msg = check_nas()
    icon = human_status_icon(ok)
    st.metric("NAS", f"{icon} {'OK' if ok else 'KO'}")
    st.caption(msg)

with col2:
    ok, msg = check_ollama()
    icon = human_status_icon(ok)
    st.metric("Ollama", f"{icon} {'OK' if ok else 'KO'}")
    st.caption(f"`{OLLAMA_HOST}` — {msg}")

with col3:
    ok, msg = check_grobid()
    icon = human_status_icon(ok)
    st.metric("GROBID", f"{icon} {'OK' if ok else 'KO'}")
    st.caption(f"`{GROBID_URL}` — {msg}")

# Refresh manual
if st.button("🔄 Re-comprobar estado", use_container_width=False):
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Estado de categorías
# ---------------------------------------------------------------------------

st.subheader("Categorías")

nas_ok, _ = check_nas()
if not nas_ok:
    st.warning(
        "El NAS no está montado. Los conteos por categoría no están disponibles."
    )
else:
    existing = set(list_existing_categories())
    rows = []
    for cat in CANONICAL_CATEGORIES:
        stats = get_category_stats(cat)
        rows.append({
            "Categoría": cat,
            "Existe":    "✓" if stats["exists"] else "—",
            "PDFs":      stats["pdfs"],
            "Pendientes": stats["pending"],
            "MD limpio": stats["md_clean"],
            "Resúmenes": stats["summaries"],
            "Chunks":    stats["chunks"],
            "Metadata":  stats["metadata"],
            "FAISS":     "✓" if stats["embeddings"] else "—",
            "Paquetes":  stats["packages"],
        })

    # Categorías ad-hoc (existen pero no son canónicas)
    adhoc_cats = sorted(existing - set(CANONICAL_CATEGORIES))
    for cat in adhoc_cats:
        stats = get_category_stats(cat)
        rows.append({
            "Categoría": f"{cat} (ad-hoc)",
            "Existe":    "✓",
            "PDFs":      stats["pdfs"],
            "Pendientes": stats["pending"],
            "MD limpio": stats["md_clean"],
            "Resúmenes": stats["summaries"],
            "Chunks":    stats["chunks"],
            "Metadata":  stats["metadata"],
            "FAISS":     "✓" if stats["embeddings"] else "—",
            "Paquetes":  stats["packages"],
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "PDFs":       st.column_config.NumberColumn(width="small"),
            "Pendientes": st.column_config.NumberColumn(
                width="small",
                help="PDFs en pdfs/ sin su correspondiente md_clean/*.clean.md",
            ),
        },
    )

    # Totales
    totals_cols = st.columns(5)
    totals_cols[0].metric("Total PDFs",      int(df["PDFs"].sum()))
    totals_cols[1].metric("Total pendientes", int(df["Pendientes"].sum()))
    totals_cols[2].metric("MD limpio",       int(df["MD limpio"].sum()))
    totals_cols[3].metric("Resúmenes",       int(df["Resúmenes"].sum()))
    totals_cols[4].metric("Con FAISS",       int((df["FAISS"] == "✓").sum()))

    st.divider()

    # ---------------------------------------------------------------------------
    # NAS — carpetas auxiliares
    # ---------------------------------------------------------------------------

    st.subheader("NAS — otras carpetas")

    aux_cols = st.columns(4)

    def _count_pdfs(p):
        return sum(1 for _ in p.rglob("*.pdf")) if p.exists() else 0

    def _count_csv(p):
        return sum(1 for _ in p.glob("*.csv")) if p.exists() else 0

    with aux_cols[0]:
        n = _count_pdfs(INBOX_DIR)
        st.metric("inbox/ (PDFs)", n)
        st.caption(str(INBOX_DIR))

    with aux_cols[1]:
        n = _count_csv(INBOX_CSV_DIR)
        st.metric("inbox_csv/ (CSVs)", n)
        st.caption(str(INBOX_CSV_DIR))

    with aux_cols[2]:
        fall_dir = NAS_ROOT / "fallidos"
        n = _count_pdfs(fall_dir)
        st.metric("fallidos/ (PDFs)", n)
        st.caption(str(fall_dir))

    with aux_cols[3]:
        doi_xlsx = METADATOS_DIR / "doi_manual.xlsx"
        exists = doi_xlsx.exists()
        st.metric("doi_manual.xlsx", "✓" if exists else "—")
        st.caption(str(doi_xlsx))

# ---------------------------------------------------------------------------
# Pie
# ---------------------------------------------------------------------------

st.divider()

with st.expander("ℹ️ Información del entorno"):
    st.write(f"**Scripts**: `{NAS_ROOT.parent / 'Disco' / 'proyectos' / 'research_agent' / 'scripts'}`")
    st.write(f"**Config**: `{CONFIG_DIR}`")
    st.write(f"**NAS root**: `{NAS_ROOT}`")
    st.write(f"**Categorías**: `{CATEGORIAS_DIR}`")
    st.write(f"**Ollama host**: `{OLLAMA_HOST}`")
    st.write(f"**GROBID URL**: `{GROBID_URL}`")
    st.write(f"**pipeline.py importable**: {'✓' if PIPELINE_AVAILABLE else '✗'}")
