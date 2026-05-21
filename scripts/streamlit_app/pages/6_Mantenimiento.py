# -*- coding: utf-8 -*-
"""
6_Mantenimiento.py — Tareas de administración del pipeline.

Incluye:
  - Limpiar duplicados (9_cleanup_duplicates.py)
  - Re-indexar embeddings (5_build_embeddings.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import (
    CANONICAL_CATEGORIES, OLLAMA_EMBED_MODELS, OLLAMA_MODEL_EMBED,
    check_nas, list_existing_categories,
    PIPELINE_AVAILABLE, PIPELINE_IMPORT_ERROR,
)

st.set_page_config(page_title="Mantenimiento", page_icon="🔧", layout="wide")
st.title("🔧 Mantenimiento")

if not PIPELINE_AVAILABLE:
    st.error(f"No se puede importar `pipeline.py`: {PIPELINE_IMPORT_ERROR}")
    st.stop()

from pipeline import run_step

nas_ok, nas_msg = check_nas()
st.markdown(f"**NAS**: {'🟢' if nas_ok else '🔴'} {nas_msg}")
if not nas_ok:
    st.error("NAS no montado. Operaciones bloqueadas.")
    st.stop()

st.divider()


def execute_script_live(script: str, args: list[str], label: str):
    """Ejecuta un script capturando salida en directo."""
    log_lines: list[str] = []
    status_box = st.status(f"Ejecutando {label}…", expanded=True)
    output_box = status_box.empty()
    MAX_LINES = 200

    def on_output(line: str) -> None:
        log_lines.append(line)
        visible = log_lines[-MAX_LINES:]
        output_box.code("\n".join(visible), language="text")

    try:
        result = run_step(script, args, on_output=on_output, label=label)
    except Exception as e:
        status_box.update(label=f"✗ {label} — error: {e}", state="error")
        st.exception(e)
        return None

    rc = result.get("returncode", -1)
    if rc == 0:
        status_box.update(label=f"✓ {label} completado", state="complete")
    else:
        status_box.update(label=f"✗ {label} falló (rc={rc})", state="error")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — Limpiar duplicados
# ═══════════════════════════════════════════════════════════════════════════

st.header("🗑️ Limpiar duplicados")
st.markdown(
    "Detecta y elimina artículos duplicados (mismo DOI) ya procesados. "
    "Primero ejecuta **Preview** para revisar qué se eliminará, luego **Apply** "
    "para hacer la limpieza real."
)

col_cleanup1, col_cleanup2 = st.columns(2)
with col_cleanup1:
    if st.button("👁️ Preview — ver duplicados", key="btn_cleanup_preview"):
        execute_script_live("9_cleanup_duplicates.py", ["--preview"], "Cleanup Preview")

with col_cleanup2:
    if st.button(
        "🗑️ Apply — eliminar duplicados",
        type="primary",
        help="⚠️ Esto BORRARÁ archivos. Ejecuta Preview primero.",
        key="btn_cleanup_apply",
    ):
        if not st.session_state.get("cleanup_confirm", False):
            st.warning("Marca la confirmación para continuar.")
        else:
            result = execute_script_live("9_cleanup_duplicates.py", ["--apply"], "Cleanup Apply")
            if result and result.get("returncode") == 0:
                st.success(
                    "✓ Duplicados eliminados. Las categorías afectadas necesitan "
                    "re-indexar (ve a la sección de abajo)."
                )

st.checkbox(
    "✅ Confirmo que revisé el Preview y quiero proceder",
    key="cleanup_confirm",
)

st.divider()


# ═══════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — Re-indexar embeddings
# ═══════════════════════════════════════════════════════════════════════════

st.header("🔄 Re-indexar embeddings")
st.markdown(
    "Re-construye los índices FAISS para las categorías seleccionadas. "
    "Útil tras limpiar duplicados o cambiar de modelo de embeddings."
)

existing_cats = list_existing_categories()
if not existing_cats:
    st.info("No hay categorías en el NAS.")
else:
    model_index = (
        OLLAMA_EMBED_MODELS.index(OLLAMA_MODEL_EMBED)
        if OLLAMA_MODEL_EMBED in OLLAMA_EMBED_MODELS
        else 0
    )

    with st.form("reindex_form"):
        selected_cats = st.multiselect(
            "Categorías a re-indexar",
            options=existing_cats,
            default=[],
            help="Vacío = todas las categorías existentes",
        )

        model = st.selectbox(
            "Modelo de embeddings",
            options=OLLAMA_EMBED_MODELS,
            index=model_index,
            help=f"Default actual: {OLLAMA_MODEL_EMBED}",
        )

        force = st.checkbox(
            "Forzar re-indexado (sobreescribir índices existentes)",
            value=False,
            help="Sin esto, 5_build_embeddings.py salta categorías ya indexadas.",
        )

        submit = st.form_submit_button("▶ Re-indexar", type="primary")

    if submit:
        cats_to_process = selected_cats if selected_cats else existing_cats

        st.info(f"Re-indexando {len(cats_to_process)} categoría(s) con modelo **{model}**…")

        for cat in cats_to_process:
            args = ["--project", cat, "--model", model]
            if force:
                args.append("--force")

            result = execute_script_live(
                "5_build_embeddings.py",
                args,
                f"Embeddings [{cat}]",
            )
            if not result or result.get("returncode") != 0:
                st.error(f"✗ Falló para {cat}. Revisar logs.")
                break
        else:
            st.success(f"✓ Re-indexado completado para {len(cats_to_process)} categoría(s).")
