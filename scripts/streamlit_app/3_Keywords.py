# -*- coding: utf-8 -*-
"""
3_🔑_Keywords.py — Editor estructurado de config/keywords.yml.

Usa st.data_editor para edición tabular (añadir/borrar filas, edición inline).
Al guardar, hace backup .bak previo del fichero original.
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

from app_utils import CANONICAL_CATEGORIES, CONFIG_DIR, load_yaml, save_yaml

st.set_page_config(page_title="Keywords", page_icon="🔑", layout="wide")
st.title("🔑 Editor de keywords.yml")

st.markdown(
    "Palabras clave para el cribado de PDFs sueltos (flujo **inbox**). "
    "El cribado por keywords es la primera etapa; si hay ambigüedad o ninguna coincidencia, "
    "se pasa a Ollama como fallback."
)

# ---------------------------------------------------------------------------
# Carga del fichero
# ---------------------------------------------------------------------------

YAML_PATH = CONFIG_DIR / "keywords.yml"
st.caption(f"Fichero: `{YAML_PATH}`")

if not YAML_PATH.exists():
    st.error(f"No existe `{YAML_PATH}`.")
    st.stop()

data = load_yaml(YAML_PATH)

# Asegurar que las 8 categorías canónicas estén presentes (aunque vacías)
for cat in CANONICAL_CATEGORIES + ["irrelevante"]:
    if cat not in data:
        data[cat] = []

# Convertir a DataFrame para st.data_editor
rows = []
for cat, kws in data.items():
    if not kws:  # categoría vacía -> fila placeholder visible
        rows.append({"categoria": cat, "keyword": ""})
        continue
    for kw in kws:
        rows.append({"categoria": cat, "keyword": kw})

df = pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

# Categorías disponibles para el dropdown de la columna 'categoria'
categories_available = sorted(set(list(data.keys()) + CANONICAL_CATEGORIES + ["irrelevante"]))

edited = st.data_editor(
    df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "categoria": st.column_config.SelectboxColumn(
            "Categoría",
            options=categories_available,
            required=True,
            width="medium",
        ),
        "keyword": st.column_config.TextColumn(
            "Keyword",
            required=False,
            width="large",
            help="Palabra o expresión (case-insensitive). Las filas vacías se ignoran al guardar.",
        ),
    },
    key="keywords_editor",
)

# ---------------------------------------------------------------------------
# Resumen + guardar
# ---------------------------------------------------------------------------

# Reconstruir dict {categoria: [keywords]}
new_data: dict[str, list[str]] = {}
for cat in categories_available:
    new_data[cat] = []
for _, row in edited.iterrows():
    cat = str(row.get("categoria", "")).strip()
    kw  = str(row.get("keyword", "")).strip()
    if not cat or not kw:
        continue
    new_data.setdefault(cat, [])
    if kw not in new_data[cat]:  # deduplicar
        new_data[cat].append(kw)

# Eliminar categorías sin keywords salvo 'irrelevante' que se conserva siempre
clean_data = {
    cat: kws for cat, kws in new_data.items()
    if kws or cat == "irrelevante"
}

# Resumen
st.divider()
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Resumen")
    summary = pd.DataFrame([
        {"Categoría": cat, "Nº keywords": len(kws)}
        for cat, kws in clean_data.items()
    ])
    st.dataframe(summary, hide_index=True, use_container_width=True)

with col2:
    st.subheader("Acciones")

    # Diff: solo permitimos guardar si hay cambios
    has_changes = clean_data != data

    if has_changes:
        st.info("Hay cambios pendientes de guardar.")
    else:
        st.success("Sin cambios respecto al fichero original.")

    if st.button(
        "💾 Guardar (crea .bak)",
        type="primary",
        disabled=not has_changes,
        use_container_width=True,
    ):
        try:
            save_yaml(YAML_PATH, clean_data)
            st.success(f"Guardado en `{YAML_PATH}` (backup en `{YAML_PATH}.bak`)")
            st.rerun()
        except Exception as e:
            st.error(f"Error guardando: {e}")

    if st.button("↻ Descartar cambios y recargar", use_container_width=True):
        st.rerun()

# ---------------------------------------------------------------------------
# Vista previa del YAML resultante
# ---------------------------------------------------------------------------

with st.expander("👀 Previsualizar YAML que se guardará"):
    import yaml as _yaml
    yaml_str = _yaml.safe_dump(
        clean_data,
        allow_unicode=True, sort_keys=False,
        default_flow_style=False, indent=2,
    )
    st.code(yaml_str, language="yaml")
