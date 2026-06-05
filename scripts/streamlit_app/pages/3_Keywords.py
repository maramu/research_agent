# -*- coding: utf-8 -*-
"""
3_Keywords.py — Editor de config/keywords.yml.

Un st.text_area por categoría (una keyword por línea).
Al guardar crea backup .bak previo (via save_yaml de app_utils).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import yaml as _yaml

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import CANONICAL_CATEGORIES, CONFIG_DIR, load_yaml, save_yaml

st.set_page_config(page_title="Keywords", page_icon="🔑", layout="wide")
from app_utils import check_password, is_public_app
if is_public_app():
    st.stop()
if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()
st.title("🔑 Editor de keywords.yml")

st.markdown(
    "Palabras clave para el cribado de PDFs (flujo **inbox**). "
    "Primera etapa del clasificador; si hay ambigüedad o ninguna coincidencia, "
    "se pasa a Ollama como fallback. **Una keyword por línea.**"
)

YAML_PATH = CONFIG_DIR / "keywords.yml"
st.caption(f"Fichero: `{YAML_PATH}`")

if not YAML_PATH.exists():
    st.error(f"No existe `{YAML_PATH}`.")
    st.stop()

data = load_yaml(YAML_PATH)

ALL_CATS = CANONICAL_CATEGORIES + ["irrelevante"]
for cat in ALL_CATS:
    if cat not in data:
        data[cat] = []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def parse_area(text: str) -> list[str]:
    """Split lines, strip, deduplicate, filter empties. Preserves order."""
    seen: set[str] = set()
    result: list[str] = []
    for line in text.splitlines():
        kw = line.strip()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


# ---------------------------------------------------------------------------
# Botón SUPERIOR
# ---------------------------------------------------------------------------

save_top = st.button("💾 Guardar todo (crea .bak)", type="primary", key="save_top")
st.divider()

# ---------------------------------------------------------------------------
# Un text_area por categoría
# ---------------------------------------------------------------------------

textarea_values: dict[str, str] = {}

for cat in ALL_CATS:
    kws = data.get(cat, [])
    n = len(kws)
    st.subheader(f"{cat}  ·  {n} keyword{'s' if n != 1 else ''}")
    textarea_values[cat] = st.text_area(
        label=cat,
        value="\n".join(kws),
        height=max(120, min(n * 28 + 48, 340)),
        key=f"ta_{cat}",
        label_visibility="collapsed",
        placeholder="Una keyword por línea…",
    )

# ---------------------------------------------------------------------------
# Botón INFERIOR
# ---------------------------------------------------------------------------

st.divider()
col_save, col_reset = st.columns([1, 1])

with col_save:
    save_bot = st.button(
        "💾 Guardar todo (crea .bak)", type="primary",
        key="save_bot", use_container_width=True,
    )

with col_reset:
    if st.button("↻ Descartar cambios y recargar", key="reset", use_container_width=True):
        st.rerun()

# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------

if save_top or save_bot:
    new_data: dict[str, list[str]] = {
        cat: parse_area(textarea_values[cat]) for cat in ALL_CATS
    }
    try:
        save_yaml(YAML_PATH, new_data)
        total = sum(len(v) for v in new_data.values())
        st.success(
            f"Guardado: {total} keywords en {len(ALL_CATS)} categorías · "
            f"backup en `{YAML_PATH}.bak`"
        )
        st.rerun()
    except Exception as e:
        st.error(f"Error guardando: {e}")

# ---------------------------------------------------------------------------
# Resumen + preview YAML (colapsados por defecto)
# ---------------------------------------------------------------------------

with st.expander("📊 Resumen y previsualización YAML"):
    new_data_preview = {cat: parse_area(textarea_values[cat]) for cat in ALL_CATS}

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("**Keywords en el editor** (pendientes de guardar si hay cambios)")
        for cat in ALL_CATS:
            current_n = len(new_data_preview[cat])
            saved_n   = len(data.get(cat, []))
            delta = current_n - saved_n
            if delta > 0:
                badge = f" `+{delta}`"
            elif delta < 0:
                badge = f" `{delta}`"
            else:
                badge = ""
            st.write(f"- `{cat}`: **{current_n}**{badge}")

    with col2:
        yaml_str = _yaml.safe_dump(
            new_data_preview,
            allow_unicode=True, sort_keys=False,
            default_flow_style=False, indent=2,
        )
        st.code(yaml_str, language="yaml")
