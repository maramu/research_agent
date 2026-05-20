# -*- coding: utf-8 -*-
"""
4_📚_Scopus_queries.py — Editor de config/scopus_queries.yml.

Cada categoría tiene una lista de queries (strings multilínea en sintaxis
Scopus: TITLE-ABS-KEY, AND, OR, W/N…). Por categoría, expander con textareas.
Botones añadir/eliminar/duplicar por query.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Permitir import de utils.py de la carpeta padre
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import CANONICAL_CATEGORIES, CONFIG_DIR, load_yaml, save_yaml

st.set_page_config(page_title="Scopus queries", page_icon="📚", layout="wide")
st.title("📚 Editor de scopus_queries.yml")

st.markdown(
    "Queries de búsqueda en Scopus por categoría. Cada categoría puede tener "
    "múltiples queries. Sintaxis Scopus: `TITLE-ABS-KEY(...)`, `AND`, `OR`, `W/N`, "
    "`PUBYEAR > 2020`, etc. Las queries son independientes de `keywords.yml`."
)

YAML_PATH = CONFIG_DIR / "scopus_queries.yml"
st.caption(f"Fichero: `{YAML_PATH}`")

# ---------------------------------------------------------------------------
# Cargar / inicializar session_state
# ---------------------------------------------------------------------------

# Recargar desde disco solo si no hay nada en sesión o pulsamos "recargar"
if "scopus_queries" not in st.session_state or st.session_state.get("scopus_reload", False):
    data = load_yaml(YAML_PATH) if YAML_PATH.exists() else {}
    # Asegurar categorías canónicas
    for cat in CANONICAL_CATEGORIES:
        if cat not in data:
            data[cat] = []
    # Normalizar: cada categoría es una lista de strings
    for cat, val in list(data.items()):
        if val is None:
            data[cat] = []
        elif isinstance(val, str):
            data[cat] = [val]
        elif not isinstance(val, list):
            data[cat] = []
    st.session_state["scopus_queries"] = data
    st.session_state["scopus_original"] = {k: list(v) for k, v in data.items()}
    st.session_state["scopus_reload"] = False

data: dict[str, list[str]] = st.session_state["scopus_queries"]


# ---------------------------------------------------------------------------
# Acciones globales
# ---------------------------------------------------------------------------

action_cols = st.columns([1, 1, 1, 2])

with action_cols[0]:
    if st.button("↻ Recargar disco", use_container_width=True):
        st.session_state["scopus_reload"] = True
        st.rerun()

with action_cols[1]:
    has_changes = data != st.session_state.get("scopus_original", {})
    if st.button(
        "💾 Guardar (crea .bak)",
        type="primary",
        use_container_width=True,
        disabled=not has_changes,
    ):
        # Limpiar queries vacías al guardar
        clean = {
            cat: [q.strip() for q in qs if q and q.strip()]
            for cat, qs in data.items()
        }
        try:
            save_yaml(YAML_PATH, clean)
            st.session_state["scopus_original"] = {k: list(v) for k, v in clean.items()}
            st.success(f"Guardado en `{YAML_PATH}` (backup en `{YAML_PATH}.bak`)")
        except Exception as e:
            st.error(f"Error guardando: {e}")

with action_cols[2]:
    new_cat_name = st.text_input(
        "Nueva categoría", value="", placeholder="nombre_snake_case",
        label_visibility="collapsed",
    )
    if st.button("➕ Crear categoría", use_container_width=True, disabled=not new_cat_name.strip()):
        cat = new_cat_name.strip()
        if cat in data:
            st.warning(f"`{cat}` ya existe.")
        else:
            data[cat] = []
            st.rerun()

with action_cols[3]:
    if has_changes:
        st.info("⚠️ Cambios sin guardar")
    else:
        st.success("✓ Sin cambios")

st.divider()

# ---------------------------------------------------------------------------
# Editor por categoría (expanders)
# ---------------------------------------------------------------------------

# Categorías ordenadas: canónicas primero, luego adicionales
ordered_cats = (
    [c for c in CANONICAL_CATEGORIES if c in data]
    + sorted(c for c in data.keys() if c not in CANONICAL_CATEGORIES)
)

for cat in ordered_cats:
    queries = data[cat]
    label = f"**{cat}** — {len(queries)} quer{'y' if len(queries)==1 else 'ies'}"

    # Las categorías canónicas con pocas queries (1 o 0) se abren por defecto
    open_by_default = cat in CANONICAL_CATEGORIES and len(queries) <= 1

    with st.expander(label, expanded=open_by_default):
        # Cada query con su textarea + botones
        for i, q in enumerate(queries):
            qcol, bcol = st.columns([10, 1])
            with qcol:
                new_q = st.text_area(
                    f"Query #{i+1}",
                    value=q,
                    key=f"q_{cat}_{i}",
                    height=120,
                    label_visibility="collapsed",
                )
                if new_q != q:
                    data[cat][i] = new_q
            with bcol:
                st.markdown("")  # spacing
                if st.button("🗑", key=f"del_{cat}_{i}", help="Eliminar esta query"):
                    data[cat].pop(i)
                    st.rerun()
                if st.button("📋", key=f"dup_{cat}_{i}", help="Duplicar"):
                    data[cat].insert(i + 1, q)
                    st.rerun()

        # Botones al final del expander
        bottom_cols = st.columns([1, 1, 4])
        with bottom_cols[0]:
            if st.button("➕ Añadir query", key=f"add_{cat}", use_container_width=True):
                data[cat].append("")
                st.rerun()
        with bottom_cols[1]:
            if cat not in CANONICAL_CATEGORIES:
                if st.button(
                    "🗑 Borrar categoría", key=f"delcat_{cat}",
                    use_container_width=True,
                ):
                    del data[cat]
                    st.rerun()

# ---------------------------------------------------------------------------
# Vista previa del YAML resultante
# ---------------------------------------------------------------------------

st.divider()
with st.expander("👀 Previsualizar YAML que se guardará"):
    import yaml as _yaml
    clean = {
        cat: [q.strip() for q in qs if q and q.strip()]
        for cat, qs in data.items()
    }
    yaml_str = _yaml.safe_dump(
        clean, allow_unicode=True, sort_keys=False,
        default_flow_style=False, indent=2, width=120,
    )
    st.code(yaml_str, language="yaml")
