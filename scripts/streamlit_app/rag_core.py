# -*- coding: utf-8 -*-
"""
rag_core.py — Núcleo RAG compartido por las páginas Streamlit.

Extraído de pages/2_RAG.py para reutilizarlo sin duplicar lógica desde otras
páginas (p.ej. "Preparar clase"). Contiene: carga cacheada de índices/metadata,
clientes de proveedor, embedding de la query, montaje de contexto, la función
ÚNICA de síntesis con streaming + post-proceso de citas, y los renders de
export (ZIP de papers / Markdown de chunks).

No renderiza página propia: solo define funciones. La política de citas
(build_cite_map → citation_for_chunk) distingue automáticamente libro vs
artículo, así que la síntesis sirve igual para ambos.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import faiss
import numpy as np
import ollama
import streamlit as st

# Bootstrap de path para importar app_utils y utils.* tanto si nos importa una
# página (que ya lo hace) como si nos importan en otro contexto.
_STREAMLIT_APP_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _STREAMLIT_APP_DIR.parent
for _d in (str(_STREAMLIT_APP_DIR), str(_SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import (  # noqa: E402
    OLLAMA_HOST, ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY,
    project_base,
)
from utils.export_refs import build_papers_zip, build_chunks_markdown  # noqa: E402
from utils.citations import (  # noqa: E402
    load_papers_metadata, build_cite_map, apply_citations, CITE_PROMPT_RULES,
)
from utils.retrieval import build_bm25  # noqa: E402


# ---------------------------------------------------------------------------
# Caché de índices / metadata
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Cargando índice FAISS…")
def load_index(project: str, phase: str, index_mtime: float):
    emb_dir = project_base(project) / project / "embeddings" / phase
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


@st.cache_resource(show_spinner="Construyendo índice BM25…")
def load_bm25(project: str, phase: str, index_mtime: float):
    emb_dir = project_base(project) / project / "embeddings" / phase
    meta_path = emb_dir / "metadata.jsonl"
    if not meta_path.exists():
        return None
    texts = []
    with meta_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                texts.append(json.loads(line).get("text", ""))
    return build_bm25(texts)


@st.cache_data(show_spinner=False)
def load_papers_meta(project: str, meta_mtime: float):
    """Índice {paper_id: record} de papers_metadata.jsonl (clave: project+mtime)."""
    return load_papers_metadata(project, project_base(project))


# ---------------------------------------------------------------------------
# Clientes de proveedor
# ---------------------------------------------------------------------------

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


@st.cache_resource(show_spinner=False)
def get_openrouter_client():
    from openai import OpenAI
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com/maramu/research_agent",
            "X-Title": "research_agent RAG",
        },
    )


def get_google_aistudio_client(api_key: str):
    from openai import OpenAI
    return OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=api_key,
    )


def embed_query(client, query: str, model: str) -> np.ndarray:
    resp = client.embeddings(model=model, prompt=query)
    return np.array(resp["embedding"], dtype="float32")


# ---------------------------------------------------------------------------
# Contexto y síntesis
# ---------------------------------------------------------------------------

def _build_context_text(chunks):
    """Construye el bloque de fragmentos numerados a partir de metadata de chunks.

    ``chunks`` es un iterable de dicts con al menos ``text`` y ``section``.
    """
    parts = []
    for i, m in enumerate(chunks, start=1):
        snippet = m.get("text", "").strip()
        section = m.get("section", "?")
        parts.append(f"[{i}] sección: {section}\n{snippet}")
    return "\n\n---\n\n".join(parts)


def _format_chat_prompt(system_content, history, query):
    """Formatea un prompt plano (Ollama) con sistema, historial y pregunta nueva."""
    lines = [system_content, ""]
    for turn in history:
        label = "Usuario" if turn["role"] == "user" else "Asistente"
        lines.append(f"{label}: {turn['content']}")
    lines.append(f"Usuario: {query}")
    lines.append("Asistente:")
    return "\n\n".join(lines)


def synthesize_answer(provider, model, results, query, papers_meta,
                      max_output_tokens, out_box, history=None,
                      system_content=None):
    """Sintetiza una respuesta sobre ``results`` con el provider/modelo dados.

    Función ÚNICA de síntesis: la usan la consulta gratuita (Ollama), la premium
    de pago y la página "Preparar clase". Monta el contexto numerado, hace
    streaming por provider, aplica el post-proceso de citas (apply_citations) y
    devuelve ``(answer_md, usage_capture, prompt)``.

    ``results`` es una lista de tuplas ``(score, idx, m)`` (m = metadata del chunk).

    ``system_content`` (opcional) permite personalizar la instrucción del sistema
    (p.ej. contraste libro↔papers). Si es None se usa la plantilla por defecto.
    Debe incluir los ``Fragmentos`` numerados si se pasa a medida; para eso el
    caller puede usar ``build_default_system(...)`` como base.

    ``history`` (opcional) es una lista de turnos ``{"role", "content"}``. Cuando
    se pasa, el LLM recibe el contexto como mensaje ``system`` seguido del
    historial y la nueva pregunta.
    """
    usage_capture = {
        "input_tokens": 0,
        "output_tokens": 0,
        "is_estimated": False,
        "cost_usd_override": None,
    }

    context = _build_context_text(m for _, _, m in results)

    # Mapa [N] -> clave de cita (artículo o libro, según el chunk).
    cite_map = build_cite_map(results, papers_meta)

    if system_content is None:
        system_content = build_default_system(context)

    if history is None:
        # Comportamiento original: un único mensaje user con todo el contexto.
        prompt = f"{system_content}\n\nPregunta: {query}\n\nRespuesta:"
        ollama_prompt = prompt
        anthropic_system = None
        anthropic_messages = [{"role": "user", "content": prompt}]
        openai_messages = [{"role": "user", "content": prompt}]
    else:
        # Chat con memoria: system + historial + nueva pregunta.
        chat_tail = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in history
        ] + [{"role": "user", "content": query}]
        ollama_prompt = _format_chat_prompt(system_content, history, query)
        prompt = ollama_prompt
        anthropic_system = system_content
        anthropic_messages = chat_tail
        openai_messages = [{"role": "system", "content": system_content}] + chat_tail

    # ─────────────────────────── Streaming por provider ──────────────────────

    def stream_ollama():
        client = get_ollama_client()
        full = ""
        for chunk in client.generate(model=model, prompt=ollama_prompt, stream=True):
            text = chunk.get("response", "")
            full += text
            yield text
        # Ollama no devuelve token counts → estimar
        usage_capture["input_tokens"]  = max(1, len(ollama_prompt) // 4)
        usage_capture["output_tokens"] = max(1, len(full) // 4)
        usage_capture["is_estimated"]  = True

    def stream_anthropic():
        client = get_anthropic_client()
        kwargs = {
            "model": model,
            "max_tokens": max_output_tokens,
            "messages": anthropic_messages,
        }
        if anthropic_system:
            kwargs["system"] = anthropic_system
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
            usage_capture["input_tokens"]  = final.usage.input_tokens
            usage_capture["output_tokens"] = final.usage.output_tokens

    def stream_openai():
        client = get_openai_client()
        oa_stream = client.chat.completions.create(
            model=model,
            messages=openai_messages,
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

    def stream_openrouter():
        client = get_openrouter_client()
        or_stream = client.chat.completions.create(
            model=model,
            messages=openai_messages,
            max_tokens=max_output_tokens,
            stream=True,
            stream_options={"include_usage": True},
            extra_body={"usage": {"include": True}},  # pide a OpenRouter el coste real
        )
        for chunk in or_stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            u = getattr(chunk, "usage", None)
            if u:
                usage_capture["input_tokens"]  = getattr(u, "prompt_tokens", 0) or 0
                usage_capture["output_tokens"] = getattr(u, "completion_tokens", 0) or 0
                _cost = getattr(u, "cost", None)
                if _cost is None:
                    _extra = getattr(u, "model_extra", None) or {}
                    _cost = _extra.get("cost")
                if _cost is not None:
                    usage_capture["cost_usd_override"] = float(_cost)

    def stream_google_aistudio():
        client = get_google_aistudio_client(st.session_state.get("_gai_api_key", ""))
        gai_stream = client.chat.completions.create(
            model=model,
            messages=openai_messages,
            max_tokens=max_output_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in gai_stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            if getattr(chunk, "usage", None):
                usage_capture["input_tokens"]  = chunk.usage.prompt_tokens
                usage_capture["output_tokens"] = chunk.usage.completion_tokens

    # Pintamos manualmente (no st.write_stream) para sustituir [N] por las
    # claves de cita una vez completada la generación.
    _raw_chunks = []

    def _render(gen):
        for piece in gen:
            _raw_chunks.append(piece)
            out_box.markdown("".join(_raw_chunks))

    if provider == "Ollama (local)":
        _render(stream_ollama())
    elif provider == "Anthropic (Claude)":
        _render(stream_anthropic())
    elif provider == "OpenAI (GPT)":
        _render(stream_openai())
    elif provider == "OpenRouter":
        _render(stream_openrouter())
    elif provider == "Google AI Studio":
        _render(stream_google_aistudio())

    raw_md    = "".join(_raw_chunks)
    answer_md = apply_citations(raw_md, cite_map)
    out_box.markdown(answer_md)
    return answer_md, usage_capture, prompt


def build_default_system(context: str) -> str:
    """Plantilla de sistema por defecto (idéntica a la histórica de 2_RAG)."""
    return f"""Eres un asistente científico. Responde a la pregunta basándote ÚNICAMENTE en los fragmentos numerados que se proporcionan a continuación.

Reglas:
- Si los fragmentos no contienen información suficiente para responder, dilo claramente.
- No inventes datos. No uses conocimiento externo a los fragmentos.
- Responde en el mismo idioma que la pregunta.
{CITE_PROMPT_RULES}

Fragmentos:
{context}

Recuerda: cita con [N] junto a cada dato; sin sección de Referencias."""


# ---------------------------------------------------------------------------
# Export (ZIP de papers / Markdown de chunks)
# ---------------------------------------------------------------------------

def _render_papers_export(papers, project, key_prefix=""):
    """Renderiza el expander "Exportar papers recuperados" con ZIP descargable."""
    with st.expander("📦 Exportar papers recuperados", expanded=False):
        _inc_pdf = st.checkbox(
            "Incluir PDFs", value=True,
            key=f"{key_prefix}zip_pdf",
        )
        _inc_md = st.checkbox(
            "Incluir MD limpio", value=True,
            key=f"{key_prefix}zip_md",
        )
        if _inc_pdf or _inc_md:
            _zip = build_papers_zip(
                papers, project, project_base(project),
                include_pdf=_inc_pdf, include_md=_inc_md,
            )
            st.download_button(
                f"⬇️ Descargar ZIP ({len(papers)} papers)",
                data=_zip,
                file_name=f"{project}_papers_RAG.zip",
                mime="application/zip",
                key=f"{key_prefix}dl_papers_zip",
            )
            st.caption(
                "Contiene los PDFs y/o Markdown de los papers con chunks "
                "recuperados en esta búsqueda."
            )


def _render_chunks_export(results, project, score_label="score", key_prefix=""):
    """Botón de descarga de TODOS los chunks recuperados en un único .md con
    referencia completa por chunk. Independiente del ZIP de PDFs/MD.
    """
    _mj = project_base(project) / project / "metadata" / "papers_metadata.jsonl"
    _mtime = _mj.stat().st_mtime if _mj.exists() else 0.0
    papers_meta = load_papers_meta(project, _mtime)

    md = build_chunks_markdown(
        results, project, project_base(project), papers_meta,
        query=st.session_state.get("_last_query"), score_label=score_label,
    )
    st.download_button(
        "⬇️ Descargar chunks (Markdown)",
        data=md.encode("utf-8"),
        file_name=f"{project}_chunks_RAG.md",
        mime="text/markdown",
        key=f"{key_prefix}dl_chunks_md",
    )
    st.caption(
        "Incluye la referencia bibliográfica completa por chunk (título, autores, "
        "año, revista, DOI, sección) para citar desde un LLM externo."
    )
