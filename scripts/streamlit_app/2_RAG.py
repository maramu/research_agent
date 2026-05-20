# -*- coding: utf-8 -*-
"""
2_🔍_RAG.py — Consultas RAG sobre el índice FAISS de un proyecto/categoría.

Dos modos (toggle):
  - Solo retrieval: muestra top-k chunks con metadatos (réplica de 8_query_rag.py)
  - Retrieval + síntesis: pasa los chunks a un LLM Ollama para obtener
    una respuesta sintetizada con citas [N].

Cachea índices FAISS con @st.cache_resource para no recargar en cada consulta.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import faiss
import numpy as np
import ollama
import streamlit as st

# Permitir import de utils.py de la carpeta padre
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import (
    CATEGORIAS_DIR, OLLAMA_HOST, OLLAMA_MODELS_LLM, OLLAMA_MODEL_EMBED,
    check_nas, check_ollama,
    list_embedding_phases, list_existing_categories,
)

st.set_page_config(page_title="RAG", page_icon="🔍", layout="wide")
st.title("🔍 Consultas RAG")

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

nas_ok,    nas_msg    = check_nas()
ollama_ok, ollama_msg = check_ollama()

c1, c2 = st.columns(2)
c1.markdown(f"**NAS**: {'🟢' if nas_ok else '🔴'} {nas_msg}")
c2.markdown(f"**Ollama**: {'🟢' if ollama_ok else '🔴'} {ollama_msg}")

if not nas_ok:
    st.error("El NAS no está montado. No se puede acceder a los índices FAISS.")
    st.stop()
if not ollama_ok:
    st.error("Ollama no está accesible. No se pueden generar embeddings de la consulta.")
    st.stop()

st.divider()


# ---------------------------------------------------------------------------
# Caché de índices FAISS y metadatos
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Cargando índice FAISS…")
def load_index(project: str, phase: str):
    emb_dir = CATEGORIAS_DIR / project / "embeddings" / phase
    if not emb_dir.exists():
        return None, None, None

    index_path = emb_dir / "index.faiss"
    meta_path  = emb_dir / "metadata.jsonl"
    cfg_path   = emb_dir / "config.json"

    if not (index_path.exists() and meta_path.exists()):
        return None, None, None

    index = faiss.read_index(str(index_path))
    meta  = []
    with meta_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                meta.append(json.loads(line))

    cfg = {}
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    return index, meta, cfg


@st.cache_resource(show_spinner=False)
def get_ollama_client():
    return ollama.Client(host=OLLAMA_HOST)


def embed_query(client, query: str, model: str) -> np.ndarray:
    resp = client.embeddings(model=model, prompt=query)
    return np.array(resp["embedding"], dtype="float32")


# ---------------------------------------------------------------------------
# Sidebar — selectores
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Índice")

    projects = list_existing_categories()
    if not projects:
        st.error("No hay proyectos en categorias/")
        st.stop()

    project = st.selectbox("Proyecto", options=projects, key="rag_project")

    phases_with_index = list_embedding_phases(project)
    if not phases_with_index:
        st.error(
            f"No hay índices FAISS para `{project}`.\n\n"
            "Lanza primero `5_build_embeddings.py` desde la página de Ingestar."
        )
        st.stop()

    phase = st.selectbox("Fase", options=phases_with_index, key="rag_phase")

    st.divider()
    st.header("Búsqueda")

    k = st.slider("Top-k", min_value=3, max_value=30, value=8)
    type_filter = st.selectbox(
        "Filtrar por tipo",
        options=["(todos)", "text", "table"],
        index=0,
    )
    paper_filter = st.text_input(
        "Filtrar por paper_id (substring)",
        value="",
        help="Opcional. Filtra resultados cuyo paper_id contenga este texto.",
    )

    st.divider()
    st.header("Respuesta")

    do_synth = st.toggle(
        "Sintetizar respuesta con LLM",
        value=True,
        help="Si está activo, pasa los chunks recuperados a un LLM Ollama para obtener una respuesta con citas.",
    )
    if do_synth:
        synth_model = st.selectbox(
            "Modelo Ollama",
            options=OLLAMA_MODELS_LLM,
            index=1,  # qwen3:8b por defecto (más rápido que 14b)
        )


# ---------------------------------------------------------------------------
# Main — query
# ---------------------------------------------------------------------------

# Cargar índice + meta
index, meta, cfg = load_index(project, phase)
if index is None:
    st.error("No se pudo cargar el índice. ¿Existen index.faiss y metadata.jsonl?")
    st.stop()

embed_model = cfg.get("model", OLLAMA_MODEL_EMBED)

st.markdown(
    f"**Proyecto**: `{project}` · **Fase**: `{phase}` · "
    f"**Chunks indexados**: {len(meta)} · **Modelo embed**: `{embed_model}`"
)

query = st.text_area(
    "Pregunta o consulta",
    value="",
    height=80,
    placeholder="Ej: ¿Qué pretratamientos mejoran el rendimiento de biometanización de PLA?",
)

go = st.button("🔍 Buscar", type="primary", disabled=not query.strip())

if not go:
    st.stop()

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

with st.spinner("Generando embedding y buscando…"):
    client = get_ollama_client()
    qv = embed_query(client, query, embed_model).reshape(1, -1)
    # Pedimos k*5 para luego aplicar filtros
    D, I = index.search(qv, k * 5)

results = []
for dist, idx in zip(D[0].tolist(), I[0].tolist()):
    if idx < 0 or idx >= len(meta):
        continue
    m = meta[idx]
    if type_filter != "(todos)" and m.get("type") != type_filter:
        continue
    if paper_filter and paper_filter.lower() not in m.get("paper_id", "").lower():
        continue
    results.append((dist, idx, m))
    if len(results) >= k:
        break

if not results:
    st.warning("Sin resultados que cumplan los filtros. Prueba aflojando filtros o cambiando la consulta.")
    st.stop()

# ---------------------------------------------------------------------------
# Síntesis con LLM (opcional)
# ---------------------------------------------------------------------------

if do_synth:
    st.subheader("Respuesta")

    # Construir contexto numerado [1], [2], ...
    context_parts = []
    for i, (_, _, m) in enumerate(results, start=1):
        snippet = m.get("text", "").strip()
        paper_id = m.get("paper_id", "?")
        section  = m.get("section", "?")
        context_parts.append(f"[{i}] ({paper_id}, sección: {section})\n{snippet}")
    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""Eres un asistente científico. Responde a la pregunta basándote ÚNICAMENTE en los fragmentos numerados que se proporcionan a continuación.

Reglas:
- Cita las fuentes usando [N] (el número del fragmento) donde apoyes una afirmación.
- Si los fragmentos no contienen información suficiente para responder, dilo claramente.
- No inventes datos. No uses conocimiento externo a los fragmentos.
- Responde en el mismo idioma que la pregunta.

Fragmentos:
{context}

Pregunta: {query}

Respuesta:"""

    def stream_answer():
        for chunk in client.generate(model=synth_model, prompt=prompt, stream=True):
            yield chunk.get("response", "")

    try:
        st.write_stream(stream_answer())
    except Exception as e:
        st.error(f"Error al sintetizar respuesta: {e}")
        st.code(prompt, language="text")

    st.divider()

# ---------------------------------------------------------------------------
# Resultados (chunks)
# ---------------------------------------------------------------------------

st.subheader(f"Chunks recuperados ({len(results)})")

for rank, (dist, idx, m) in enumerate(results, start=1):
    paper_id = m.get("paper_id", "?")
    section  = m.get("section", "?")
    chunk_type = m.get("type", "?")
    phase_tag = m.get("phase", "?")
    snippet  = m.get("text", "")

    with st.expander(
        f"**[{rank}]** dist={dist:.4f} · `{paper_id}` · {section} · {chunk_type}",
        expanded=(rank <= 3),
    ):
        st.caption(f"Fase: `{phase_tag}` · Tipo: `{chunk_type}` · Distancia: {dist:.4f}")
        st.markdown(snippet)
