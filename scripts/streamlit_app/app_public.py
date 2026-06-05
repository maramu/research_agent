# -*- coding: utf-8 -*-
"""
app_public.py — Portada de la instancia pública de research_agent (puerto 8502).

Solo expone RAG y Revisión bibliográfica. No muestra ingesta, configuración
ni datos internos del corpus. Síntesis limitada a Ollama (local).

Lanzar desde scripts/streamlit_app/:
    PUBLIC_APP=true streamlit run app_public.py \
        --server.address 0.0.0.0 --server.port 8502
"""

from __future__ import annotations

import streamlit as st

from app_utils import (
    OLLAMA_HOST, GROBID_URL,
    check_nas, check_ollama,
    check_password, human_status_icon, is_public_app,
)

st.set_page_config(
    page_title="research_agent · acceso público",
    page_icon="🔬",
    layout="wide",
)

# ── Autenticación ─────────────────────────────────────────────────────────────
if not check_password("PUBLIC_APP_PASSWORD"):
    st.stop()

# ── Cabecera ──────────────────────────────────────────────────────────────────
st.title("🔬 research_agent")
st.caption(
    "Interfaz de consulta bibliográfica sobre literatura científica procesada. "
    "Usa la barra lateral para navegar a **RAG** o **Revisión bibliográfica**."
)

# ── Estado de servicios (solo lo relevante para el usuario) ───────────────────
st.subheader("Estado de servicios")
col1, col2 = st.columns(2)

with col1:
    nas_ok, nas_msg = check_nas()
    icon = human_status_icon(nas_ok)
    st.metric("Corpus", f"{icon} {'Disponible' if nas_ok else 'No disponible'}")
    if not nas_ok:
        st.caption("El corpus no está accesible en este momento.")

with col2:
    ollama_ok, ollama_msg = check_ollama()
    icon = human_status_icon(ollama_ok)
    st.metric("Modelo de lenguaje", f"{icon} {'OK' if ollama_ok else 'KO'}")
    st.caption(ollama_msg)

if st.button("🔄 Re-comprobar estado"):
    st.rerun()

st.divider()

# ── Instrucciones ─────────────────────────────────────────────────────────────
st.subheader("¿Cómo usar?")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("""
### 🔍 RAG — Consultas directas

Busca fragmentos relevantes en el corpus y obtén una respuesta sintetizada.

1. Selecciona la **categoría** y el **índice** en la barra lateral
2. Escribe tu pregunta
3. Pulsa **Buscar**

Ideal para preguntas concretas: mecanismos, resultados, comparativas.
""")

with col_b:
    st.markdown("""
### 📚 Revisión bibliográfica

Genera síntesis orientadas a escritura científica con prompts especializados:

- Estado del arte
- Tabla de artículos clave
- Lagunas de conocimiento
- Comparativa de mecanismos
- Introducción preliminar

Ideal para preparar la sección de introducción o discusión de un artículo.
""")

st.divider()
st.caption(
    "Instancia de solo lectura. Modelos disponibles: Ollama (local). "
    "Para acceso completo contacta con el administrador."
)
