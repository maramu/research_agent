# -*- coding: utf-8 -*-
"""
13_RAG_multiple.py — Batería de consultas RAG ("RAG múltiple"). Solo app privada.

Edita los parámetros de una batería, la lanza reutilizando
``run_rag_batch.run_batch`` (sin duplicar lógica) y descarga los .md generados
en un zip. Los .md quedan además en /Volumes/research/exports/.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import streamlit as st

# Permitir import de app_utils.py (carpeta padre) y de run_rag_batch.py (scripts/)
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from app_utils import (
    list_existing_categories, OLLAMA_MODELS_LLM,
    check_password, is_public_app,
)
from utils.constants import CANONICAL_SECTIONS
from run_rag_batch import run_batch, DEFAULT_BASE

st.set_page_config(page_title="RAG múltiple", page_icon="🗂️", layout="wide")

# ── Guard: solo app privada ────────────────────────────────────────────────────
if is_public_app():
    st.warning("Esta página solo está disponible en la app privada.")
    st.stop()

if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()

st.title("🗂️ RAG múltiple — batería de consultas")
st.caption(
    "Lanza una lista de preguntas contra una categoría y descarga un .md por "
    "pregunta (respuesta sintetizada con Ollama local + chunks recuperados). "
    "Reutiliza el mismo motor que `run_rag_batch.py`."
)

cats = list_existing_categories()
if not cats:
    st.error("No hay categorías con índice disponibles.")
    st.stop()

# ── Formulario ─────────────────────────────────────────────────────────────────
with st.form("rag_batch_form"):
    category = st.selectbox("Categoría", cats)

    c1, c2, c3 = st.columns(3)
    with c1:
        phase = st.text_input("Fase (phase)", value="all")
    with c2:
        top_k = st.number_input("top_k", min_value=1, max_value=50, value=8, step=1)
    with c3:
        hybrid = st.checkbox("Híbrido (denso + BM25)", value=True)

    c4, c5 = st.columns(2)
    with c4:
        year_start = st.number_input("Año desde (vacío = sin filtro)",
                                     min_value=1900, max_value=2100,
                                     value=None, step=1)
    with c5:
        year_end = st.number_input("Año hasta (vacío = sin filtro)",
                                   min_value=1900, max_value=2100,
                                   value=None, step=1)

    sections = st.multiselect("Secciones (vacío = todas)", CANONICAL_SECTIONS,
                              default=[])

    _default_model = "qwen2.5:14b-instruct"
    _model_idx = (OLLAMA_MODELS_LLM.index(_default_model)
                  if _default_model in OLLAMA_MODELS_LLM else 0)
    model = st.selectbox("Modelo de síntesis (Ollama)", OLLAMA_MODELS_LLM,
                         index=_model_idx)

    questions_raw = st.text_area(
        "Preguntas (una por línea)", height=200,
        placeholder="¿Pregunta 1?\n¿Pregunta 2?",
    )
    st.caption(
        "El override de secciones por pregunta solo está disponible vía "
        "YAML + CLI (`run_rag_batch.py --config`)."
    )

    submitted = st.form_submit_button("🚀 Lanzar batería")

# ── Ejecución ──────────────────────────────────────────────────────────────────
if submitted:
    questions = [{"q": ln.strip()} for ln in questions_raw.splitlines() if ln.strip()]
    if not questions:
        st.error("Introduce al menos una pregunta.")
        st.stop()

    cfg = {
        "category": category,
        "phase": phase.strip() or "all",
        "top_k": int(top_k),
        "hybrid": bool(hybrid),
        "year_start": int(year_start) if year_start else None,
        "year_end": int(year_end) if year_end else None,
        "sections": list(sections),
        "model": model,
        "questions": questions,
    }

    st.warning(
        "La síntesis local puede tardar varios minutos por pregunta. "
        "No cierres la pestaña hasta que termine."
    )

    barra = st.progress(0.0)
    zona = st.container()

    def _cb(i, n, question, status, out_path):
        barra.progress(i / n)
        if status == "OK":
            try:
                md = Path(out_path).read_text(encoding="utf-8")
            except Exception:
                md = "_(no se pudo leer el .md generado)_"
            with zona.expander(f"✅ {question}"):
                st.markdown(md)
        else:
            zona.error(f"❌ {question}")

    with st.spinner("Ejecutando batería…"):
        summary = run_batch(cfg, base=DEFAULT_BASE, progress_cb=_cb)

    st.session_state["rag_batch_last"] = summary
    st.success(
        f"Batería terminada: {summary['n_ok']} OK / {summary['n_err']} ERROR  \n"
        f"Carpeta: `{summary['out_dir']}`"
    )

# ── Descarga (sobrevive al rerun del botón vía session_state) ───────────────────
summary = st.session_state.get("rag_batch_last")
if summary:
    out_dir = Path(summary["out_dir"])
    if out_dir.exists():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for md in sorted(out_dir.glob("*.md")):
                zf.write(md, md.name)
        st.download_button(
            "⬇️ Descargar .md (zip)",
            data=buf.getvalue(),
            file_name=f"{out_dir.name}.zip",
            mime="application/zip",
        )
        st.caption(
            f"Los .md también están en `{out_dir}` "
            "(dentro de /Volumes/research/exports/)."
        )
