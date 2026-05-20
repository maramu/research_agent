# -*- coding: utf-8 -*-
"""
1_📥_Ingestar.py — Ejecutar los tres flujos del pipeline.

Flujos:
  - Scopus: búsqueda Scopus API → descarga → procesado por categoría
  - Inbox:  PDFs en /Volumes/research/inbox → rename → screen → procesado
  - Ad-hoc: carpeta de PDFs → proyecto temporal → procesado + RAG

Cada flujo se ejecuta importando directamente las funciones de pipeline.py
y se enchufa un callback on_output que va volcando líneas a un placeholder
de Streamlit en tiempo real.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Permitir import de utils.py de la carpeta padre
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import (
    CANONICAL_CATEGORIES, CATEGORIAS_DIR, CONFIG_DIR, INBOX_DIR,
    PIPELINE_AVAILABLE, PIPELINE_IMPORT_ERROR,
    check_grobid, check_nas, check_ollama,
    load_yaml,
)

st.set_page_config(page_title="Ingestar", page_icon="📥", layout="wide")
st.title("📥 Ingestar")

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if not PIPELINE_AVAILABLE:
    st.error(f"No se puede importar `pipeline.py`: {PIPELINE_IMPORT_ERROR}")
    st.stop()

from pipeline import run_scopus, run_inbox, run_adhoc  # ya cargado vía utils

nas_ok,    nas_msg    = check_nas()
ollama_ok, ollama_msg = check_ollama()
grobid_ok, grobid_msg = check_grobid()

c1, c2, c3 = st.columns(3)
c1.markdown(f"**NAS**: {'🟢' if nas_ok else '🔴'} {nas_msg}")
c2.markdown(f"**Ollama**: {'🟢' if ollama_ok else '🔴'} {ollama_msg}")
c3.markdown(f"**GROBID**: {'🟢' if grobid_ok else '🔴'} {grobid_msg}")

if not nas_ok:
    st.error("El NAS no está montado. Acción bloqueada.")
    st.stop()

if not (ollama_ok and grobid_ok):
    st.warning(
        "Ollama o GROBID no responden. Puedes lanzar la ingesta igualmente "
        "pero los pasos que los requieran fallarán."
    )

st.divider()


# ---------------------------------------------------------------------------
# Helper: lanzar un flujo capturando salida en directo
# ---------------------------------------------------------------------------

def execute_with_live_output(fn, label: str, **kwargs):
    """Ejecuta fn(**kwargs, on_output=...) y va volcando líneas a un placeholder.

    Devuelve el dict resultado de la función (o None si hubo excepción).
    """
    log_lines: list[str] = []
    status_box  = st.status(f"Ejecutando {label}…", expanded=True)
    output_box  = status_box.empty()
    MAX_LINES = 200

    def on_output(line: str) -> None:
        log_lines.append(line)
        # Mostrar solo las últimas N líneas para no saturar
        visible = log_lines[-MAX_LINES:]
        output_box.code("\n".join(visible), language="text")

    try:
        result = fn(on_output=on_output, **kwargs)
    except Exception as e:
        status_box.update(label=f"✗ {label} — error: {e}", state="error")
        st.exception(e)
        return None

    overall = result.get("status", "?")
    if overall == "ok":
        status_box.update(label=f"✓ {label} completado", state="complete")
    elif overall == "partial":
        status_box.update(label=f"⚠️ {label} completado con errores parciales", state="error")
    else:
        status_box.update(label=f"✗ {label} falló", state="error")

    return result


# ---------------------------------------------------------------------------
# Tabs por flujo
# ---------------------------------------------------------------------------

tab_scopus, tab_inbox, tab_adhoc = st.tabs([
    "🌐 Scopus",
    "📂 Inbox",
    "🧪 Ad-hoc",
])

# ─────────────────────────────────────────────────────────────────────────────
# FLUJO A — Scopus
# ─────────────────────────────────────────────────────────────────────────────

with tab_scopus:
    st.markdown(
        "Consulta Scopus por categoría con las queries definidas en "
        "`config/scopus_queries.yml`. Los PDFs se descargan directamente a "
        "`categorias/<cat>/pdfs/` y se procesa la cadena completa."
    )

    # Cargar queries para mostrar resumen
    queries_file = CONFIG_DIR / "scopus_queries.yml"
    queries_data = load_yaml(queries_file)
    available_cats = list(queries_data.keys()) if queries_data else CANONICAL_CATEGORIES

    with st.form("scopus_form"):
        sel_cats = st.multiselect(
            "Categorías (vacío = todas)",
            options=available_cats,
            default=[],
            help="Si dejas vacío, se procesan todas las categorías con queries definidas",
        )

        col1, col2 = st.columns(2)
        with col1:
            recent_days = st.number_input(
                "Días recientes (PUBYEAR vs hoy)", min_value=0, max_value=3650,
                value=0, step=1,
                help="0 = sin filtro. Para ingesta semanal usa 7.",
            )
            max_results = st.number_input(
                "Máx. resultados por categoría", min_value=1, max_value=5000,
                value=200, step=50,
            )
            doctype = st.selectbox(
                "Tipo de documento", options=["", "ar", "re", "cp"],
                index=0,
                help="ar=article, re=review, cp=conference paper. Vacío=todos",
            )

        with col2:
            year_start = st.number_input(
                "Año inicio (opcional)", min_value=0, max_value=2100,
                value=0, step=1,
            )
            year_end = st.number_input(
                "Año fin (opcional)", min_value=0, max_value=2100,
                value=0, step=1,
            )
            dry_run = st.checkbox(
                "Dry-run (solo simular, no descargar)",
                value=False,
            )

        submit_scopus = st.form_submit_button(
            "▶ Ejecutar flujo Scopus", type="primary", use_container_width=True,
        )

    if submit_scopus:
        kwargs = {
            "categories":  sel_cats if sel_cats else None,
            "recent_days": int(recent_days) if recent_days else None,
            "max_results": int(max_results),
            "year_start":  int(year_start) if year_start else None,
            "year_end":    int(year_end)   if year_end   else None,
            "doctype":     doctype if doctype else None,
            "queries_file": str(queries_file) if queries_file.exists() else None,
            "dry_run":     dry_run,
        }
        result = execute_with_live_output(run_scopus, "Scopus", **kwargs)
        if result:
            with st.expander("📊 Resumen detallado", expanded=True):
                st.json(result)


# ─────────────────────────────────────────────────────────────────────────────
# FLUJO B — Inbox
# ─────────────────────────────────────────────────────────────────────────────

with tab_inbox:
    st.markdown(
        f"Procesa los PDFs sueltos que tengas en `{INBOX_DIR}`. "
        "Renombra por DOI (vía Crossref), criba con keywords + Ollama, "
        "y lanza la cadena de procesado para cada categoría que reciba PDFs nuevos."
    )

    # Contar PDFs actuales en inbox
    n_inbox = sum(1 for _ in INBOX_DIR.rglob("*.pdf")) if INBOX_DIR.exists() else 0
    st.metric("PDFs actualmente en inbox/", n_inbox)

    with st.form("inbox_form"):
        custom_folder = st.text_input(
            "Carpeta de origen (opcional)",
            value="",
            placeholder=str(INBOX_DIR),
            help="Por defecto se usa /Volumes/research/inbox. Solo cambia si tienes los PDFs en otra ruta.",
        )
        do_rename = st.checkbox(
            "Renombrar por DOI antes del cribado (1_rename_papers_by_doi.py)",
            value=True,
        )
        submit_inbox = st.form_submit_button(
            "▶ Ejecutar flujo Inbox", type="primary", use_container_width=True,
            disabled=(n_inbox == 0 and not custom_folder),
        )

    if submit_inbox:
        folders = [custom_folder] if custom_folder else None
        result = execute_with_live_output(
            run_inbox, "Inbox",
            folders=folders,
            rename=do_rename,
        )
        if result:
            with st.expander("📊 Resumen detallado", expanded=True):
                st.json(result)


# ─────────────────────────────────────────────────────────────────────────────
# FLUJO C — Ad-hoc
# ─────────────────────────────────────────────────────────────────────────────

with tab_adhoc:
    st.markdown(
        "Crea un proyecto temporal a partir de una carpeta de PDFs sueltos. "
        "Copia los PDFs a `categorias/<nombre>/pdfs/` y procesa la cadena "
        "completa. No hace cribado ni renombrado: asume que ya están como tú quieres."
    )

    default_name = f"adhoc_{datetime.now().strftime('%Y%m%d_%H%M')}"

    with st.form("adhoc_form"):
        name = st.text_input(
            "Nombre del proyecto",
            value=default_name,
            help="Se creará en categorias/<nombre>/. Usa snake_case sin espacios.",
        )
        pdfs_path = st.text_input(
            "Ruta a la carpeta con los PDFs",
            value="",
            placeholder="/Users/martinramirez/Desktop/papers_revision",
            help="Ruta absoluta. Los PDFs se copian (no se mueven).",
        )

        # Vista previa de PDFs en la ruta
        if pdfs_path:
            p = Path(pdfs_path).expanduser()
            if p.exists() and p.is_dir():
                pdfs_found = list(p.glob("*.pdf"))
                st.caption(f"✓ Carpeta encontrada — {len(pdfs_found)} PDFs detectados")
            else:
                st.caption("⚠️ La carpeta no existe")

        submit_adhoc = st.form_submit_button(
            "▶ Ejecutar flujo Ad-hoc", type="primary", use_container_width=True,
        )

    if submit_adhoc:
        if not name.strip():
            st.error("Falta el nombre del proyecto.")
        elif not pdfs_path.strip():
            st.error("Falta la ruta a la carpeta de PDFs.")
        else:
            result = execute_with_live_output(
                run_adhoc, "Ad-hoc",
                name=name.strip(),
                pdf_dir=str(Path(pdfs_path).expanduser()),
            )
            if result:
                with st.expander("📊 Resumen detallado", expanded=True):
                    st.json(result)
                if result.get("status") == "ok":
                    st.success(
                        f"Proyecto **{result['project']}** listo. "
                        f"Ve a 🔍 RAG para hacer consultas."
                    )
