# -*- coding: utf-8 -*-
"""
2_RAG.py — Consultas RAG sobre índice FAISS, con tres providers de síntesis:

  - Ollama (local)     — gratis, requiere VPN UCA
  - Anthropic (Claude) — pago, requiere ANTHROPIC_API_KEY
  - OpenAI  (GPT)      — pago, requiere OPENAI_API_KEY

Características:
  - Estimación de coste antes de la consulta
  - Coste real (input/output tokens) después
  - Contador acumulado del mes (lee /Volumes/research/metadatos/rag_usage/)
  - Streaming en los tres providers
  - Selector de índice (proyecto + fase) que soporta múltiples modelos de embedding
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
import ollama
import streamlit as st

# Permitir import de app_utils.py de la carpeta padre
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import (
    ANTHROPIC_MODELS, OPENAI_MODELS, OLLAMA_MODELS_LLM, OLLAMA_MODEL_EMBED,
    OLLAMA_HOST, ANTHROPIC_API_KEY, OPENAI_API_KEY,
    CATEGORIAS_DIR, LLM_PRICING,
    check_anthropic_api, check_nas, check_ollama, check_openai_api,
    embedding_phase_model, estimate_cost_pre_query, estimate_cost_usd,
    fmt_cost, get_monthly_usage, list_embedding_phases, list_existing_categories,
    record_rag_query,
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
    st.error("Ollama no está accesible. Se necesita para generar embeddings de la consulta.")
    st.stop()

st.divider()


# ---------------------------------------------------------------------------
# Caché de índices FAISS
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
    meta = []
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
    return ollama.Client(host=OLLAMA_HOST, timeout=120)


@st.cache_resource(show_spinner=False)
def get_anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@st.cache_resource(show_spinner=False)
def get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)


def embed_query(client, query: str, model: str) -> np.ndarray:
    resp = client.embeddings(model=model, prompt=query)
    return np.array(resp["embedding"], dtype="float32")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Índice")

    projects = list_existing_categories()
    if not projects:
        st.error("No hay proyectos en categorias/")
        st.stop()

    project = st.selectbox("Proyecto", options=projects, key="rag_project")

    phases = list_embedding_phases(project)
    if not phases:
        st.error(
            f"No hay índices FAISS para `{project}`.\n\n"
            "Lanza primero `5_build_embeddings.py` desde Ingestar."
        )
        st.stop()

    # Mostrar nombre de fase + modelo (entre paréntesis) para que sepas cuál es cuál
    phase_labels = {
        p: f"{p}  ·  ({embedding_phase_model(project, p)})"
        for p in phases
    }
    phase = st.selectbox(
        "Fase / índice",
        options=phases,
        format_func=lambda p: phase_labels[p],
        key="rag_phase",
    )

    st.divider()
    st.header("Recuperación")

    k = st.slider("Top-k chunks", min_value=3, max_value=30, value=8)
    type_filter = st.selectbox(
        "Filtrar por tipo",
        options=["(todos)", "text", "table"],
        index=0,
    )
    paper_filter = st.text_input(
        "Filtrar por paper_id (substring)",
        value="",
    )

    st.divider()
    st.header("Síntesis LLM")

    do_synth = st.toggle("Sintetizar respuesta con LLM", value=True)

    if do_synth:
        provider = st.selectbox(
            "Provider",
            options=["Ollama (local)", "Anthropic (Claude)", "OpenAI (GPT)"],
            index=0,
        )

        if provider == "Ollama (local)":
            synth_model = st.selectbox("Modelo", options=OLLAMA_MODELS_LLM, index=1)
        elif provider == "Anthropic (Claude)":
            ant_ok, ant_msg = check_anthropic_api()
            if not ant_ok:
                st.error(f"Anthropic: {ant_msg}")
                synth_model = None
            else:
                synth_model = st.selectbox("Modelo", options=ANTHROPIC_MODELS, index=1)
        else:  # OpenAI
            oai_ok, oai_msg = check_openai_api()
            if not oai_ok:
                st.error(f"OpenAI: {oai_msg}")
                synth_model = None
            else:
                synth_model = st.selectbox("Modelo", options=OPENAI_MODELS, index=0)

        max_output_tokens = st.slider(
            "Máx tokens respuesta", 256, 4096, 1024, step=256,
            help="Tope superior. La respuesta real suele ser bastante menor.",
        )
    else:
        provider = synth_model = max_output_tokens = None

    # Contador mensual
    st.divider()
    st.header("Uso del mes")
    usage = get_monthly_usage()
    st.metric(
        f"Mes {usage['month']}",
        fmt_cost(usage["total_cost_usd"]),
        f"{usage['n_queries']} consultas",
    )
    if usage["by_provider"]:
        with st.expander("Desglose"):
            for prov, stats in usage["by_provider"].items():
                st.write(
                    f"**{prov}** — {stats['queries']} consultas · "
                    f"{fmt_cost(stats['cost_usd'])}"
                )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

index, meta, cfg = load_index(project, phase)
if index is None:
    st.error("No se pudo cargar el índice. ¿Existen index.faiss y metadata.jsonl?")
    st.stop()

embed_model = cfg.get("model", OLLAMA_MODEL_EMBED)

st.markdown(
    f"**Proyecto**: `{project}` · **Fase**: `{phase}` · "
    f"**Chunks**: {len(meta)} · **Modelo embed**: `{embed_model}` ({index.d} dims)"
)

query = st.text_area(
    "Pregunta o consulta",
    value="",
    height=80,
    placeholder="Ej: ¿Qué pretratamientos mejoran el rendimiento de biometanización de PLA?",
)

# Estimación de coste antes de buscar (basada en k y output esperado)
if do_synth and synth_model:
    avg_chunk_chars = 1200  # estimación heurística
    estimated_prompt_chars = avg_chunk_chars * k + 500  # +500 por prompt fijo
    est_in_tk  = estimated_prompt_chars // 4
    est_out_tk = (max_output_tokens or 500) // 3  # output medio ≈ 1/3 del máximo
    est_cost   = estimate_cost_usd(synth_model, est_in_tk, est_out_tk)

    if est_cost > 0:
        st.info(
            f"💰 **Coste estimado** para esta consulta con {synth_model}: "
            f"~{fmt_cost(est_cost)} "
            f"({est_in_tk:,} input + ~{est_out_tk:,} output tokens, k={k})"
        )
    else:
        st.info(f"💰 **Coste**: gratis (Ollama local)")

go = st.button("🔍 Buscar", type="primary", disabled=not query.strip())

if not go:
    st.stop()

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

with st.spinner("Generando embedding y buscando…"):
    ollama_client = get_ollama_client()
    qv = embed_query(ollama_client, query, embed_model).reshape(1, -1)
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
    st.warning("Sin resultados con esos filtros. Prueba aflojando filtros o cambia la consulta.")
    st.stop()

# ---------------------------------------------------------------------------
# Síntesis
# ---------------------------------------------------------------------------

usage_capture = {
    "input_tokens": 0,
    "output_tokens": 0,
    "is_estimated": False,
}

if do_synth and synth_model:
    st.subheader("Respuesta")

    context_parts = []
    for i, (_, _, m) in enumerate(results, start=1):
        snippet  = m.get("text", "").strip()
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

    # ─────────────────────────── Streaming por provider ──────────────────────

    def stream_ollama():
        full = ""
        for chunk in ollama_client.generate(model=synth_model, prompt=prompt, stream=True):
            text = chunk.get("response", "")
            full += text
            yield text
        # Ollama no devuelve token counts → estimar
        usage_capture["input_tokens"]  = max(1, len(prompt) // 4)
        usage_capture["output_tokens"] = max(1, len(full) // 4)
        usage_capture["is_estimated"]  = True

    def stream_anthropic():
        client = get_anthropic_client()
        with client.messages.stream(
            model=synth_model,
            max_tokens=max_output_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
            usage_capture["input_tokens"]  = final.usage.input_tokens
            usage_capture["output_tokens"] = final.usage.output_tokens

    def stream_openai():
        client = get_openai_client()
        oa_stream = client.chat.completions.create(
            model=synth_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_output_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in oa_stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            if getattr(chunk, "usage", None):
                usage_capture["input_tokens"]  = chunk.usage.prompt_tokens
                usage_capture["output_tokens"] = chunk.usage.completion_tokens

    try:
        if provider == "Ollama (local)":
            st.write_stream(stream_ollama())
        elif provider == "Anthropic (Claude)":
            st.write_stream(stream_anthropic())
        elif provider == "OpenAI (GPT)":
            st.write_stream(stream_openai())
    except Exception as e:
        st.error(f"Error al generar respuesta con {provider}: {e}")
        with st.expander("Prompt enviado (debug)"):
            st.code(prompt, language="text")
        st.stop()

    # Coste real y registro
    in_tk  = usage_capture["input_tokens"]
    out_tk = usage_capture["output_tokens"]
    cost   = estimate_cost_usd(synth_model, in_tk, out_tk)

    cost_label = "Coste estimado" if usage_capture["is_estimated"] else "Coste real"
    st.caption(
        f"📊 {cost_label}: **{fmt_cost(cost)}** · "
        f"{in_tk:,} input + {out_tk:,} output tokens · "
        f"modelo `{synth_model}`"
    )

    record_rag_query(
        provider=provider.split(" ")[0].lower(),
        model=synth_model,
        input_tokens=in_tk,
        output_tokens=out_tk,
        cost_usd=cost,
        query=query,
        project=project,
        is_estimated=usage_capture["is_estimated"],
    )

    st.divider()

# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------

st.subheader(f"Chunks recuperados ({len(results)})")

for rank, (dist, idx, m) in enumerate(results, start=1):
    paper_id   = m.get("paper_id", "?")
    section    = m.get("section", "?")
    chunk_type = m.get("type", "?")
    phase_tag  = m.get("phase", "?")
    snippet    = m.get("text", "")

    with st.expander(
        f"**[{rank}]** dist={dist:.4f} · `{paper_id}` · {section} · {chunk_type}",
        expanded=(rank <= 3),
    ):
        st.caption(f"Fase: `{phase_tag}` · Tipo: `{chunk_type}` · Distancia: {dist:.4f}")
        st.markdown(snippet)
