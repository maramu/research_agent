# -*- coding: utf-8 -*-
"""
6_Mantenimiento.py — Tareas de administración del pipeline.

Secciones:
  1. Backfill metadata (stable_id)
  2. Re-indexar FAISS
  3. Limpieza de duplicados
  4. Reconstruir doi_registry
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import (
    CATEGORIAS_DIR,
    PIPELINE_AVAILABLE, PIPELINE_IMPORT_ERROR,
    check_nas, list_existing_categories,
)

st.set_page_config(page_title="Mantenimiento", page_icon="🔧", layout="wide")
st.title("🔧 Mantenimiento")

if not PIPELINE_AVAILABLE:
    st.error(f"No se puede importar `pipeline.py`: {PIPELINE_IMPORT_ERROR}")
    st.stop()

from pipeline import build_doi_registry_from_nas, run_step  # noqa: E402

nas_ok, nas_msg = check_nas()
st.markdown(f"**NAS**: {'🟢' if nas_ok else '🔴'} {nas_msg}")
if not nas_ok:
    st.error("NAS no montado. Operaciones bloqueadas.")
    st.stop()

st.divider()


def execute_script_live(script: str, args: list[str], label: str) -> dict | None:
    """Ejecuta un script del pipeline volcando salida en directo."""
    log_lines: list[str] = []
    status_box = st.status(f"Ejecutando {label}…", expanded=True)
    output_box = status_box.empty()
    MAX_LINES = 200

    def on_output(line: str) -> None:
        log_lines.append(line)
        output_box.code("\n".join(log_lines[-MAX_LINES:]), language="text")

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
# SECCIÓN 1 — Backfill metadata (stable_id)
# ═══════════════════════════════════════════════════════════════════════════

with st.expander("🗂️ Backfill metadata (stable_id)", expanded=False):
    st.markdown(
        "Detecta papers en `categorias/<cat>/metadata/papers_metadata.jsonl` "
        "que no tienen el campo `stable_id` (procesados antes del ítem 14/16). "
        "Re-ejecuta `4_extract_metadata.py` para rellenarlo."
    )

    existing_cats = list_existing_categories()
    backfill_rows: list[dict] = []
    for cat in existing_cats:
        jsonl = CATEGORIAS_DIR / cat / "metadata" / "papers_metadata.jsonl"
        if not jsonl.exists():
            continue
        missing = 0
        with jsonl.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    if "stable_id" not in json.loads(raw):
                        missing += 1
                except json.JSONDecodeError:
                    pass
        if missing:
            backfill_rows.append({"Categoría": cat, "Sin stable_id": missing})

    if not backfill_rows:
        st.success("Todas las categorías tienen `stable_id` en su metadata.")
    else:
        import pandas as pd

        st.dataframe(pd.DataFrame(backfill_rows), hide_index=True, use_container_width=True)

        cats_with_missing = [r["Categoría"] for r in backfill_rows]
        selected_backfill = st.multiselect(
            "Categorías a reprocesar",
            options=cats_with_missing,
            default=cats_with_missing,
            key="backfill_cats",
        )

        if st.button("▶ Re-ejecutar 4_extract_metadata.py", type="primary", key="btn_backfill"):
            if not selected_backfill:
                st.warning("Selecciona al menos una categoría.")
            else:
                for cat in selected_backfill:
                    execute_script_live(
                        "4_extract_metadata.py",
                        ["--project", cat],
                        f"extract_metadata [{cat}]",
                    )


# ═══════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — Re-indexar FAISS
# ═══════════════════════════════════════════════════════════════════════════

with st.expander("🔄 Re-indexar FAISS", expanded=False):
    st.markdown(
        "Re-construye los índices FAISS de las categorías seleccionadas con "
        "`bge-m3` y `--force`. Útil tras limpiar duplicados o hacer backfill de metadata."
    )

    existing_cats_faiss = list_existing_categories()
    if not existing_cats_faiss:
        st.info("No hay categorías en el NAS.")
    else:
        selected_faiss = st.multiselect(
            "Categorías a re-indexar",
            options=existing_cats_faiss,
            default=existing_cats_faiss,
            key="faiss_cats",
        )

        if st.button("▶ Re-indexar seleccionadas", type="primary", key="btn_reindex"):
            if not selected_faiss:
                st.warning("Selecciona al menos una categoría.")
            else:
                for cat in selected_faiss:
                    result = execute_script_live(
                        "5_build_embeddings.py",
                        ["--project", cat, "--model", "bge-m3", "--force"],
                        f"build_embeddings [{cat}]",
                    )
                    if not result or result.get("returncode") != 0:
                        st.error(f"✗ Falló para **{cat}**. Revisar salida.")
                        break
                else:
                    st.success(
                        f"✓ Re-indexado completado para {len(selected_faiss)} categoría(s)."
                    )


# ═══════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — Limpieza de duplicados
# ═══════════════════════════════════════════════════════════════════════════

with st.expander("🗑️ Limpieza de duplicados", expanded=False):
    st.markdown(
        "Detecta artículos duplicados (mismo DOI) ya procesados. "
        "Ejecuta **Preview** primero para revisar qué se eliminaría; "
        "el botón **Aplicar** aparece solo si hay duplicados."
    )

    if st.button("👁️ Preview duplicados", key="btn_cleanup_preview"):
        result = execute_script_live("9_cleanup_duplicates.py", ["--preview"], "Cleanup Preview")
        if result is not None:
            output_text = "\n".join(result.get("output", []))
            counts = re.findall(r"Duplicados[\w\s\-]+:\s*(\d+)", output_text)
            has_dupes = any(int(c) > 0 for c in counts) if counts else False
            st.session_state["cleanup_has_dupes"] = has_dupes
            st.session_state["cleanup_preview_done"] = True
        else:
            st.session_state.pop("cleanup_preview_done", None)

    if st.session_state.get("cleanup_preview_done"):
        if st.session_state.get("cleanup_has_dupes"):
            st.warning(
                "⚠️ Se detectaron duplicados. Usa **Aplicar limpieza** para eliminarlos. "
                "Tras aplicar, re-indexa FAISS de las categorías afectadas."
            )
            if st.button("🗑️ Aplicar limpieza", type="primary", key="btn_cleanup_apply"):
                result = execute_script_live(
                    "9_cleanup_duplicates.py", ["--apply"], "Cleanup Apply"
                )
                if result and result.get("returncode") == 0:
                    st.success(
                        "✓ Limpieza completada. Recuerda **re-indexar FAISS** de las "
                        "categorías afectadas (sección ↑ Re-indexar FAISS)."
                    )
                    st.session_state.pop("cleanup_preview_done", None)
                    st.session_state.pop("cleanup_has_dupes", None)
        else:
            st.success("No se encontraron duplicados.")


# ═══════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — Reconstruir doi_registry
# ═══════════════════════════════════════════════════════════════════════════

with st.expander("📋 Reconstruir doi_registry", expanded=False):
    st.markdown(
        "Escanea `categorias/*/pdfs/` y reconstruye `doi_registry.txt` desde cero. "
        "Útil antes del cribado para detectar duplicados contra artículos ya procesados."
    )

    if st.button("▶ Reconstruir doi_registry", type="primary", key="btn_doi_registry"):
        with st.spinner("Escaneando PDFs en el NAS…"):
            try:
                n_dois = build_doi_registry_from_nas()
                st.success(f"✓ doi_registry reconstruido — **{n_dois}** DOIs registrados.")
            except Exception as e:
                st.error(f"Error al reconstruir doi_registry: {e}")
                st.exception(e)
