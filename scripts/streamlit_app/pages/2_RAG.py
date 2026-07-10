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
import re
import sys
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
import ollama
import streamlit as st

# Permitir import de app_utils.py de la carpeta padre
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from app_utils import (
    ANTHROPIC_MODELS, OPENAI_MODELS, OLLAMA_MODELS_LLM, OLLAMA_MODEL_EMBED,
    OPENROUTER_MODELS, OPENROUTER_API_KEY,
    GOOGLE_AISTUDIO_MODELS, check_google_aistudio_api,
    OLLAMA_HOST, ANTHROPIC_API_KEY, OPENAI_API_KEY,
    CATEGORIAS_DIR, NAS_ROOT, LLM_PRICING, LLM_CONTEXT_WINDOWS, project_base,
    check_anthropic_api, check_nas, check_ollama, check_openai_api,
    check_openrouter_api,
    embedding_phase_model, estimate_cost_pre_query, estimate_cost_usd,
    fmt_cost, get_monthly_usage, list_embedding_phases, list_existing_categories,
    record_rag_query, record_rag_query_full, check_password, is_public_app,
)
from utils.export_refs import build_papers_zip, build_chunks_markdown
from utils.constants import CANONICAL_SECTIONS, year_from_paper_id
from utils.citations import (
    load_papers_metadata, build_cite_map, apply_citations, CITE_PROMPT_RULES,
    attachment_citation_key,
)
from utils.retrieval import (dense_rank, bm25_rank, rrf_fuse,
                             passes_filters, pool_size)
from utils.attachments import (
    extract_text, chunk_text, embed_texts, rank_attachment,
    fuse_results, content_hash, make_attachment_metas,
)

st.set_page_config(page_title="RAG", page_icon="🔍", layout="wide")

_pwd_env = "PUBLIC_APP_PASSWORD" if is_public_app() else "PRIVATE_APP_PASSWORD"
if not check_password(_pwd_env):
    st.stop()

st.title("🔍 Consultas RAG")

if "attach_cache" not in st.session_state:
    st.session_state["attach_cache"] = {}

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
# Núcleo RAG compartido (índices, proveedores, síntesis, export) — rag_core.py
# ---------------------------------------------------------------------------
from rag_core import (
    load_index, load_bm25, load_papers_meta,
    get_ollama_client, get_anthropic_client, get_openai_client,
    get_openrouter_client, get_google_aistudio_client,
    embed_query, _build_context_text, _format_chat_prompt,
    synthesize_answer, _render_papers_export, _render_chunks_export,
)


# ---------------------------------------------------------------------------
# Profundizar (modelo de pago) — consulta premium sobre artículos ya rescatados
# Solo app privada (guard is_public_app en el caller). Reutiliza synthesize_answer
# y el filtro paper_id de passes_filters (no reimplementa el retrieval).
# ---------------------------------------------------------------------------

def _retrieve_paper_deepen_results(query, paper_ids, project, phase, embed_model, top_k):
    """Re-consulta FAISS restringida a un conjunto de paper_id con top_k ampliado.

    Devuelve una lista de tuplas ``(score, idx, m)`` con los chunks recuperados,
    o ``None`` si no se pudo cargar el índice o no hay paper_ids.
    """
    _ip = project_base(project) / project / "embeddings" / phase / "index.faiss"
    _im = _ip.stat().st_mtime if _ip.exists() else 0.0
    p_index, p_meta, _p_cfg = load_index(project, phase, _im)
    if p_index is None:
        st.error("No se pudo recargar el índice para profundizar.")
        return None
    paper_set = set(paper_ids)
    if not paper_set:
        st.warning("No hay paper_id rescatados sobre los que profundizar.")
        return None
    with st.spinner("Recuperando más fragmentos de esos papers…"):
        client = get_ollama_client()
        qv = embed_query(client, query, embed_model).reshape(1, -1)
        pool = pool_size(int(top_k), p_index.ntotal, True)
        d_idx, dist_map = dense_rank(p_index, qv, pool)
        results = []
        for idx in d_idx:
            if idx >= len(p_meta):
                continue
            m = p_meta[idx]
            if not passes_filters(m, paper=paper_set):
                continue
            results.append((dist_map[idx], idx, m))
            if len(results) >= int(top_k):
                break
    return results


def _run_premium_query():
    """Ejecuta la consulta de pago sobre los artículos ya rescatados.

    Lee los parámetros elegidos de session_state (fijados por el botón
    "Profundizar"), streamea la respuesta con synthesize_answer, registra el
    coste con mode="premium_*" y persiste el resultado para que sobreviva a
    reruns posteriores. Corre tras el rerun disparado por el botón.
    """
    mode          = st.session_state.get("_premium_mode", "Mismos fragmentos")
    provider      = st.session_state.get("_premium_provider_sel")
    model         = st.session_state.get("_premium_model_sel")
    top_k_premium = st.session_state.get("_premium_topk_sel")
    max_out       = st.session_state.get("_premium_maxout_sel", 1024)

    prev_query   = st.session_state.get("_last_query", "")
    prev_papers  = st.session_state.get("_last_retrieved_papers", [])
    prev_results = st.session_state.get("_last_results", [])
    prev_project = st.session_state.get("_last_project", "")
    prev_phase   = st.session_state.get("_last_phase", "")
    prev_embed   = st.session_state.get("_last_embed_model", OLLAMA_MODEL_EMBED)

    if not model or not provider:
        st.error("Falta seleccionar provider/modelo de pago.")
        return

    # Metadata de papers (claves de cita) del proyecto de la consulta previa.
    _mj = project_base(prev_project) / prev_project / "metadata" / "papers_metadata.jsonl"
    _mm = _mj.stat().st_mtime if _mj.exists() else 0.0
    papers_meta = load_papers_meta(prev_project, _mm)

    is_deepen = mode == "Profundizar en estos papers"
    if is_deepen:
        # Modo B: re-consultar FAISS restringido a los paper_id rescatados con un
        # top_k mayor. Reutiliza el helper compartido con el chat premium.
        results = _retrieve_paper_deepen_results(
            prev_query, prev_papers, prev_project, prev_phase, prev_embed, top_k_premium,
        )
        if results is None:
            return
        mode_key, mode_label = "premium_deepen", "profundizar en estos papers"
    else:
        # Modo A: exactamente los mismos chunks de la consulta gratuita. No toca FAISS.
        results = [(d["score"], 0, d["m"]) for d in prev_results]
        mode_key, mode_label = "premium_same_chunks", "mismos fragmentos"

    if not results:
        st.warning("No hay fragmentos disponibles para la consulta premium.")
        return

    st.markdown("**Generando respuesta premium…**")
    out_box = st.empty()
    try:
        answer_md, usage_capture, _prompt = synthesize_answer(
            provider, model, results, prev_query, papers_meta, max_out, out_box,
        )
    except Exception as e:
        st.error(f"Error al generar la respuesta premium con {provider}: {e}")
        return

    in_tk  = usage_capture["input_tokens"]
    out_tk = usage_capture["output_tokens"]
    _override = usage_capture.get("cost_usd_override")
    cost = _override if _override is not None else estimate_cost_usd(model, in_tk, out_tk)

    retrieved = list(dict.fromkeys(
        m.get("paper_id", "") for _, _, m in results
        if m.get("paper_id") and m.get("paper_id") != "__attachment__"
    ))

    prov_key = provider.split(" ")[0].lower()
    record_rag_query(
        provider=prov_key, model=model,
        input_tokens=in_tk, output_tokens=out_tk, cost_usd=cost,
        query=prev_query, project=prev_project,
        is_estimated=usage_capture["is_estimated"], mode=mode_key,
    )
    record_rag_query_full(
        category=prev_project, question=prev_query,
        provider=prov_key, model=model, top_k=len(results),
        retrieved_papers=retrieved, answer_md=answer_md,
        estimated_cost=0.0, real_cost=cost, mode=mode_key,
    )

    st.session_state["_premium_answer"] = answer_md
    st.session_state["_premium_info"] = {
        "model": model, "provider": provider,
        "mode_key": mode_key, "mode_label": mode_label,
        "n_chunks": len(results), "cost": cost,
        "in_tk": in_tk, "out_tk": out_tk,
        "is_estimated": usage_capture["is_estimated"],
    }
    st.rerun()


def _estimate_premium_chat_tokens(chunks, history, query, max_out):
    """Estimación grosera (chars/4) del tamaño del payload de un turno de chat."""
    overhead_chars = 500  # instrucciones del sistema sin contar fragmentos
    context_chars = len(_build_context_text(chunks))
    history_chars = sum(len(t.get("content", "")) for t in history)
    query_chars = len(query)
    input_tk = (overhead_chars + context_chars + history_chars + query_chars) // 4
    return input_tk + max_out


def _run_premium_chat(results):
    """Ejecuta un turno del chat premium con memoria.

    ``results`` es la lista de tuplas ``(score, idx, m)`` que se usará como
    contexto (ya sean los chunks fijos de la búsqueda gratuita o los
    re-recuperados en Modo B). Envía el historial completo más la nueva
    pregunta, acumula el coste en session_state y registra el turno con
    mode="premium_chat".
    """
    provider = st.session_state.get("_premium_chat_provider")
    model    = st.session_state.get("_premium_chat_model")
    max_out  = st.session_state.get("_premium_chat_maxout", 1024)
    question = st.session_state.pop("_premium_chat_question", "")

    prev_project = st.session_state.get("_last_project", "")
    history      = list(st.session_state.get("_premium_chat_history", []))

    if not question.strip():
        return
    if not model or not provider:
        st.error("Falta seleccionar provider/modelo de pago.")
        return
    if not results:
        st.warning("No hay fragmentos disponibles para el chat premium.")
        return

    _mj = project_base(prev_project) / prev_project / "metadata" / "papers_metadata.jsonl"
    _mm = _mj.stat().st_mtime if _mj.exists() else 0.0
    papers_meta = load_papers_meta(prev_project, _mm)

    st.markdown("**Generando respuesta del chat…**")
    out_box = st.empty()
    try:
        answer_md, usage_capture, _prompt = synthesize_answer(
            provider, model, results, question, papers_meta, max_out, out_box,
            history=history,
        )
    except Exception as e:
        st.error(f"Error al generar la respuesta del chat con {provider}: {e}")
        return

    in_tk  = usage_capture["input_tokens"]
    out_tk = usage_capture["output_tokens"]
    _override = usage_capture.get("cost_usd_override")
    cost = _override if _override is not None else estimate_cost_usd(model, in_tk, out_tk)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer_md})
    st.session_state["_premium_chat_history"] = history
    st.session_state["_premium_chat_cost"] = st.session_state.get("_premium_chat_cost", 0.0) + cost
    st.session_state["_premium_chat_last_cost"] = cost
    st.session_state["_premium_chat_last_info"] = {
        "model": model, "provider": provider,
        "in_tk": in_tk, "out_tk": out_tk,
        "is_estimated": usage_capture["is_estimated"],
    }

    retrieved = list(dict.fromkeys(
        m.get("paper_id", "") for _, _, m in results
        if m.get("paper_id") and m.get("paper_id") != "__attachment__"
    ))
    prov_key = provider.split(" ")[0].lower()
    record_rag_query(
        provider=prov_key, model=model,
        input_tokens=in_tk, output_tokens=out_tk, cost_usd=cost,
        query=question, project=prev_project,
        is_estimated=usage_capture["is_estimated"], mode="premium_chat",
    )
    record_rag_query_full(
        category=prev_project, question=question,
        provider=prov_key, model=model, top_k=len(results),
        retrieved_papers=retrieved, answer_md=answer_md,
        estimated_cost=0.0, real_cost=cost, mode="premium_chat",
    )
    st.rerun()


def _reset_premium_chat():
    """Callback del botón '🗑 Nuevo hilo' del chat premium."""
    st.session_state["_premium_chat_history"] = []
    st.session_state["_premium_chat_cost"] = 0.0
    st.session_state["_premium_chat_mode"] = "Fragmentos recuperados"
    st.session_state["_premium_chat_topk"] = 15
    # Resetear también las claves de los widgets para que se redibujen con valores por defecto.
    st.session_state["premium_chat_mode"] = "Fragmentos recuperados"
    st.session_state["premium_chat_topk"] = 15
    st.session_state.pop("_premium_chat_last_cost", None)
    st.session_state.pop("_premium_chat_last_info", None)


def _submit_premium_chat():
    """Callback del botón 'Preguntar' del chat premium.

    Se ejecuta antes de que el widget de entrada se vuelva a instanciar, por lo
    que es seguro leer y limpiar ``st.session_state["premium_chat_input"]``.
    """
    question = st.session_state.get("premium_chat_input", "").strip()
    if not question:
        return

    provider = st.session_state.get("premium_provider")
    if provider == "Anthropic (Claude)":
        model = st.session_state.get("premium_model_ant")
    elif provider == "OpenAI (GPT)":
        model = st.session_state.get("premium_model_oai")
    elif provider == "OpenRouter":
        model = st.session_state.get("premium_model_or")
    else:
        model = None
    max_out = st.session_state.get("premium_maxout", 1024)

    if not model or not provider:
        return

    chat_mode = st.session_state.get("premium_chat_mode", "Fragmentos recuperados")
    chat_topk = st.session_state.get("premium_chat_topk", 15)

    st.session_state["_premium_chat_question"] = question
    st.session_state["_premium_chat_provider"] = provider
    st.session_state["_premium_chat_model"]    = model
    st.session_state["_premium_chat_maxout"]   = max_out
    st.session_state["_premium_chat_mode"]     = chat_mode
    st.session_state["_premium_chat_topk"]     = chat_topk
    st.session_state["_do_premium_chat"]       = True
    st.session_state["premium_chat_input"]     = ""




def render_premium_block():
    """Bloque '🔎 Profundizar (modelo de pago)'.

    Visible SOLO si hay una consulta previa con chunks en session_state. El guard
    is_public_app() lo aplica el caller (no se renderiza en la app pública).
    """
    prev_results = st.session_state.get("_last_results")
    if not prev_results:
        return

    # Estado del chat con memoria (independiente del resultado premium de un solo uso).
    if "_premium_chat_history" not in st.session_state:
        st.session_state["_premium_chat_history"] = []
    if "_premium_chat_cost" not in st.session_state:
        st.session_state["_premium_chat_cost"] = 0.0

    st.divider()
    st.subheader("🔎 Profundizar (modelo de pago)")
    prev_query   = st.session_state.get("_last_query", "")
    prev_papers  = st.session_state.get("_last_retrieved_papers", [])
    prev_project = st.session_state.get("_last_project", "")
    st.caption(
        f"Sobre la consulta previa: «{prev_query[:90]}» · "
        f"{len(prev_results)} fragmentos · {len(prev_papers)} papers. "
        "El modelo de pago razona sobre lo ya recuperado por el local (gratis): "
        "solo paga la síntesis, no la recuperación."
    )

    # Handler del flag: corre tras el rerun que dispara el botón "Profundizar".
    if st.session_state.pop("_do_premium", False):
        _run_premium_query()
        return  # _run_premium_query hace st.rerun() al terminar correctamente

    # Handler del flag: corre tras el rerun que dispara el botón "Preguntar" del chat.
    if st.session_state.pop("_do_premium_chat", False):
        chat_mode = st.session_state.get("_premium_chat_mode", "Fragmentos recuperados")
        chat_topk = st.session_state.get("_premium_chat_topk", 15)
        prev_results = st.session_state.get("_last_results", [])
        prev_papers  = st.session_state.get("_last_retrieved_papers", [])
        prev_project = st.session_state.get("_last_project", "")
        prev_phase   = st.session_state.get("_last_phase", "")
        prev_embed   = st.session_state.get("_last_embed_model", OLLAMA_MODEL_EMBED)
        question     = st.session_state.get("_premium_chat_question", "")

        if chat_mode == "Papers completos":
            results = _retrieve_paper_deepen_results(
                question, prev_papers, prev_project, prev_phase, prev_embed, chat_topk,
            )
        else:
            results = [(d["score"], 0, d["m"]) for d in prev_results]

        if not results:
            st.warning("No hay fragmentos disponibles para el chat premium.")
        else:
            _run_premium_chat(results)
        return

    # ── Contexto: papers del conjunto actual (visible durante el chat) ──
    _mj = project_base(prev_project) / prev_project / "metadata" / "papers_metadata.jsonl"
    _mm = _mj.stat().st_mtime if _mj.exists() else 0.0
    papers_meta = load_papers_meta(prev_project, _mm)

    with st.expander(f"📄 Papers del conjunto actual ({len(prev_papers)} papers)", expanded=False):
        for pid in prev_papers:
            rec = papers_meta.get(pid, {})
            title = rec.get("title") or "Sin título"
            authors = rec.get("authors", [])
            if isinstance(authors, list) and authors:
                authors_str = "; ".join(str(a) for a in authors[:3])
                if len(authors) > 3:
                    authors_str += " et al."
            else:
                authors_str = str(authors) if authors else "Autores desconocidos"
            year = rec.get("year") or year_from_paper_id(pid) or "?"
            doi = rec.get("doi", "")
            doi_str = f" · DOI: {doi}" if doi else ""
            st.markdown(f"**{title}** ({authors_str}, {year}){doi_str}")
        if prev_papers:
            _render_papers_export(prev_papers, prev_project, key_prefix="premium_")
            _prem_results = [(d["score"], 0, d["m"]) for d in prev_results]
            _render_chunks_export(_prem_results, prev_project, score_label="score",
                                  key_prefix="premium_")

    # Resultado premium persistido (sobrevive a reruns posteriores). Se muestra
    # junto a la respuesta gratuita, sin sobrescribirla.
    info = st.session_state.get("_premium_info")
    pa   = st.session_state.get("_premium_answer")
    if info and pa:
        st.success(
            f"**Respuesta premium** · modelo `{info['model']}` · "
            f"modo *{info['mode_label']}* · {info['n_chunks']} fragmentos · "
            f"{'coste estimado' if info.get('is_estimated') else 'coste real'} "
            f"**{fmt_cost(info['cost'])}** "
            f"({info['in_tk']:,} in + {info['out_tk']:,} out)"
        )
        st.markdown(pa)
        st.divider()

    # ── Controles ──
    mode = st.radio(
        "Modo",
        ["Mismos fragmentos", "Profundizar en estos papers"],
        key="premium_mode_radio",
        help="A — el modelo de pago razona sobre los MISMOS fragmentos que recuperó "
             "el local (coste mínimo). B — re-consulta FAISS sobre esos mismos papers "
             "recuperando más fragmentos por paper.",
    )
    is_deepen = mode == "Profundizar en estos papers"

    p_provider = st.selectbox(
        "Provider de pago",
        options=["Anthropic (Claude)", "OpenAI (GPT)", "OpenRouter"],
        key="premium_provider",
    )
    p_model = None
    if p_provider == "Anthropic (Claude)":
        ok, msg = check_anthropic_api()
        if not ok:
            st.error(f"Anthropic: {msg}")
        else:
            p_model = st.selectbox("Modelo", options=ANTHROPIC_MODELS, index=1,
                                   key="premium_model_ant")
    elif p_provider == "OpenAI (GPT)":
        ok, msg = check_openai_api()
        if not ok:
            st.error(f"OpenAI: {msg}")
        else:
            p_model = st.selectbox("Modelo", options=OPENAI_MODELS, index=0,
                                   key="premium_model_oai")
    else:  # OpenRouter
        ok, msg = check_openrouter_api()
        if not ok:
            st.error(f"OpenRouter: {msg}")
        else:
            p_model = st.selectbox("Modelo", options=OPENROUTER_MODELS, index=0,
                                   key="premium_model_or")

    p_topk = None
    if is_deepen:
        p_topk = st.slider(
            "Top-k ampliado (fragmentos a recuperar de esos papers)",
            8, 30, 15, key="premium_topk",
        )

    p_maxout = st.slider("Máx tokens respuesta", 256, 4096, 1024, step=256,
                         key="premium_maxout")

    # Pre-estimación de coste (misma lógica heurística que la consulta gratuita).
    if p_model:
        _k_est   = int(p_topk) if is_deepen else len(prev_results)
        _est_in  = (1200 * _k_est + 500) // 4
        _est_out = p_maxout // 3
        _est     = estimate_cost_usd(p_model, _est_in, _est_out)
        if _est > 0:
            st.info(
                f"💰 **Coste estimado**: ~{fmt_cost(_est)} "
                f"({_est_in:,} input + ~{_est_out:,} output tokens, k={_k_est})"
            )
        elif p_provider == "OpenRouter":
            st.info("💰 **Coste**: se calcula tras la consulta (OpenRouter devuelve el coste real)")

    if st.button("🔎 Profundizar", type="primary", key="premium_go",
                 disabled=not p_model):
        st.session_state["_premium_mode"]         = mode
        st.session_state["_premium_provider_sel"] = p_provider
        st.session_state["_premium_model_sel"]    = p_model
        st.session_state["_premium_topk_sel"]     = p_topk
        st.session_state["_premium_maxout_sel"]   = p_maxout
        st.session_state["_do_premium"]           = True
        st.rerun()

    # ── Chat con memoria sobre los papers rescatados ──
    st.divider()
    st.subheader("💬 Chat con memoria sobre estos papers")

    # Inicializar configuración por sesión del chat.
    if "_premium_chat_mode" not in st.session_state:
        st.session_state["_premium_chat_mode"] = "Fragmentos recuperados"
    if "_premium_chat_topk" not in st.session_state:
        st.session_state["_premium_chat_topk"] = 15

    chat_history = st.session_state.get("_premium_chat_history", [])
    chat_cost    = st.session_state.get("_premium_chat_cost", 0.0)

    # Selector de modo del chat (por sesión).
    chat_mode = st.radio(
        "Modo del chat",
        ["Fragmentos recuperados", "Papers completos"],
        key="premium_chat_mode",
        help="A — usa los chunks de la búsqueda gratuita (rápido). "
             "B — re-consulta FAISS sobre los papers rescatados con top-k ampliado (más contexto).",
    )
    chat_topk = None
    if chat_mode == "Papers completos":
        chat_topk = st.slider(
            "Top-k ampliado (fragmentos por turno)",
            8, 30, 15, key="premium_chat_topk",
        )

    for turn in chat_history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    # Aviso de contexto largo (estimación chars/4). En Modo B se escala la
    # estimación según el top-k elegido.
    _chat_input_val = st.session_state.get("premium_chat_input", "")
    _window_limit = LLM_CONTEXT_WINDOWS.get(p_model, 128_000) if p_model else 128_000
    _n_est = len(prev_results)
    if chat_mode == "Papers completos" and chat_topk:
        _n_est = max(_n_est, chat_topk)
    _est_chunks = [d["m"] for d in prev_results[:_n_est]]
    # Si el modo B pide más chunks de los que tenemos, escalamos proporcionalmente.
    if chat_mode == "Papers completos" and chat_topk and len(prev_results) < chat_topk:
        _scale = chat_topk / max(len(prev_results), 1)
        _context_chars = len(_build_context_text([d["m"] for d in prev_results])) * _scale
        _overhead = 500
        _history_chars = sum(len(t.get("content", "")) for t in chat_history)
        _estimated_tk = (_overhead + int(_context_chars) + _history_chars + len(_chat_input_val)) // 4 + (p_maxout or 1024)
    else:
        _estimated_tk = _estimate_premium_chat_tokens(
            _est_chunks, chat_history, _chat_input_val, p_maxout or 1024,
        )
    if _estimated_tk > 0.8 * _window_limit:
        st.warning(
            "La conversación es larga; considera empezar un hilo nuevo o reducir el conjunto. "
            f"Estimación: ~{_estimated_tk:,} tokens / límite ~{_window_limit:,}."
        )

    col_chat1, col_chat2 = st.columns([4, 1])
    with col_chat1:
        st.text_input(
            "Nueva pregunta",
            placeholder="Pregunta de seguimiento sobre los papers rescatados…",
            key="premium_chat_input",
        )
    with col_chat2:
        st.write("")
        st.write("")
        # on_click permite resetear las claves de los widgets sin violar la regla
        # de modificación post-instantiación de Streamlit.
        st.button("🗑 Nuevo hilo", key="premium_chat_reset", on_click=_reset_premium_chat)

    # on_click ejecuta el callback ANTES de reinstanciar el widget de entrada,
    # evitando StreamlitAPIException al limpiar la clave del input.
    st.button(
        "Preguntar", type="primary", key="premium_chat_ask",
        disabled=not (
            p_model
            and st.session_state.get("premium_chat_input", "").strip()
        ),
        on_click=_submit_premium_chat,
    )

    # Métricas de coste del chat.
    last_cost = st.session_state.get("_premium_chat_last_cost")
    if chat_history:
        c1, c2 = st.columns(2)
        c1.metric("Coste acumulado del hilo", fmt_cost(chat_cost))
        if last_cost is not None:
            c2.metric("Último turno", fmt_cost(last_cost))
        last_info = st.session_state.get("_premium_chat_last_info")
        if last_info:
            st.caption(
                f"Último turno: `{last_info['model']}` · "
                f"{last_info['in_tk']:,} in + {last_info['out_tk']:,} out · "
                f"{'estimado' if last_info.get('is_estimated') else 'real'}"
            )


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
    sel_sections = st.multiselect(
        "Secciones",
        options=CANONICAL_SECTIONS,
        default=[],
        help="Filtra por section_canonical (item 32/34). Vacío = todas.",
    )
    usar_year = st.checkbox("Filtrar por año", value=False)
    if usar_year:
        ys, ye = st.slider("Rango de años", 1990, 2026, (1990, 2026))
    else:
        ys = ye = None
    use_hybrid = st.toggle(
        "Recuperación híbrida (denso + BM25)", value=False,
        help="Fusiona FAISS (semántico) con BM25 (léxico exacto: siglas, cepas) "
             "vía RRF. OFF = solo denso.",
    )

    st.divider()
    st.header("Adjunto efímero")
    attach_file = st.file_uploader(
        "Adjuntar documento (opcional)",
        type=["pdf", "txt", "md"],
        help="PDF/TXT/MD que se usará SOLO en esta consulta. No se guarda ni se indexa.",
    )
    attach_text = st.text_area(
        "…o pega texto",
        value="",
        height=80,
        help="Texto libre que también se usará solo en esta consulta.",
    )
    attach_label = st.text_input(
        "Etiqueta de cita del adjunto (opcional)",
        value="",
        help="Aparecerá en la cita, p. ej. '(mi nota; adjunto)'.",
    )
    n_min_attach = st.number_input(
        "Fragmentos del adjunto (cupo mínimo)",
        min_value=0, max_value=8, value=3, step=1,
    )
    if attach_file or attach_text.strip():
        st.caption("📎 El adjunto se usa solo en esta consulta y no se añade al corpus.")

    st.divider()
    st.header("Síntesis LLM")

    do_synth = st.toggle("Sintetizar respuesta con LLM", value=True)

    if do_synth:
        _provider_options = (
            ["Ollama (local)", "Google AI Studio"]
            if is_public_app()
            else ["Ollama (local)", "Anthropic (Claude)", "OpenAI (GPT)", "OpenRouter"]
        )
        provider = st.selectbox("Provider", options=_provider_options, index=0)

        if provider == "Ollama (local)":
            synth_model = st.selectbox("Modelo", options=OLLAMA_MODELS_LLM, index=0)
        elif provider == "Google AI Studio":
            _gai_key = st.text_input(
                "🔑 API Key de Google AI Studio",
                type="password",
                help="Consíguela gratis en https://aistudio.google.com/apikey",
                key="gai_api_key",
            )
            if _gai_key:
                gai_ok, gai_msg = check_google_aistudio_api(_gai_key)
                if not gai_ok:
                    st.error(f"Google AI Studio: {gai_msg}")
                    synth_model = None
                else:
                    synth_model = st.selectbox("Modelo", options=GOOGLE_AISTUDIO_MODELS, index=0)
                    st.session_state["_gai_api_key"] = _gai_key
            else:
                st.info("Introduce tu API key para usar Google AI Studio (gratis).")
                synth_model = None
        elif provider == "Anthropic (Claude)":
            ant_ok, ant_msg = check_anthropic_api()
            if not ant_ok:
                st.error(f"Anthropic: {ant_msg}")
                synth_model = None
            else:
                synth_model = st.selectbox("Modelo", options=ANTHROPIC_MODELS, index=1)
        elif provider == "OpenAI (GPT)":
            oai_ok, oai_msg = check_openai_api()
            if not oai_ok:
                st.error(f"OpenAI: {oai_msg}")
                synth_model = None
            else:
                synth_model = st.selectbox("Modelo", options=OPENAI_MODELS, index=0)
        else:  # OpenRouter
            or_ok, or_msg = check_openrouter_api()
            if not or_ok:
                st.error(f"OpenRouter: {or_msg}")
                synth_model = None
            else:
                synth_model = st.selectbox("Modelo", options=OPENROUTER_MODELS, index=0)

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

_idx_path = project_base(project) / project / "embeddings" / phase / "index.faiss"
_idx_mtime = _idx_path.stat().st_mtime if _idx_path.exists() else 0.0
index, meta, cfg = load_index(project, phase, _idx_mtime)
if index is None:
    st.error("No se pudo cargar el índice. ¿Existen index.faiss y metadata.jsonl?")
    st.stop()

bm25 = load_bm25(project, phase, _idx_mtime) if use_hybrid else None
if use_hybrid and bm25 is None:
    st.warning("rank-bm25 no instalado o índice vacío; usando solo denso.")

embed_model = cfg.get("model", OLLAMA_MODEL_EMBED)

st.markdown(
    f"**Proyecto**: `{project}` · **Fase**: `{phase}` · "
    f"**Chunks**: {len(meta)} · **Modelo embed**: `{embed_model}` ({index.d} dims)"
)

if attach_file or attach_text.strip():
    st.caption("📎 Documento/texto adjunto activo: se usará solo en esta consulta.")

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
    elif provider == "OpenRouter":
        st.info("💰 **Coste**: se calcula tras la consulta (OpenRouter devuelve el coste real)")
    elif provider == "Google AI Studio":
        st.info("💰 **Coste**: gratis (Google AI Studio)")
    else:
        st.info("💰 **Coste**: gratis (Ollama local)")

go = st.button("🔍 Buscar", type="primary", disabled=not query.strip())

if st.session_state.pop("_do_save", False):
    _ans     = st.session_state.get("_last_answer_md", "")
    _papers  = st.session_state.get("_last_retrieved_papers", [])
    _query   = st.session_state.get("_last_query", "")
    _project = st.session_state.get("_last_project", "")
    _model   = st.session_state.get("_last_model", "")
    if _ans:
        _date = datetime.now().strftime("%Y-%m-%d")
        _slug = re.sub(r"[^\w]+", "_", _query.strip()[:40], flags=re.ASCII).strip("_").lower()
        note_filename = f"{_date}_{_project}_{_slug}.md"
        note_content  = f"""# {_query}

**Categoría**: {_project}
**Fecha**: {_date}
**Modelo**: {_model}
**Papers recuperados**: {', '.join(_papers)}

---

{_ans}

---

*Generado con research_agent RAG*
"""
        notes_dir = NAS_ROOT / "notas_rag" / _project
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / note_filename).write_text(note_content, encoding="utf-8")
        st.success(f"Nota guardada: `notas_rag/{_project}/{note_filename}`")

# Bloque premium (modelo de pago) sobre los artículos rescatados por la consulta
# previa. En el camino go=False (rerun del botón premium o página inactiva) se
# renderiza aquí, antes del st.stop(). En el camino go=True se renderiza al final
# de la página (con los _last_results ya actualizados por la búsqueda en curso).
# Solo en la app privada: en la pública NO debe aparecer (evita gasto del grupo).
if not is_public_app() and not go:
    render_premium_block()

if not go:
    st.stop()

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

_type_f = None if type_filter == "(todos)" else type_filter
has_filter = bool(_type_f or paper_filter or sel_sections or ys or ye)
attach_active = bool(attach_file or attach_text.strip())

# --- Adjunto efímero: extracción + troceado + embedding (con caché por hash) ---
attach_mat = None
attach_metas = []
if attach_active:
    attach_cfg = {"target_chars": 1000, "overlap": 150, "model_embed": embed_model}
    if attach_file:
        source_bytes = attach_file.getvalue()
        filename = attach_file.name
    else:
        source_bytes = attach_text.strip().encode("utf-8")
        filename = None
    h = content_hash(source_bytes, attach_cfg)
    cached = st.session_state["attach_cache"].get(h)
    if cached:
        attach_mat = cached["mat"]
        attach_metas = cached["metas"]
    else:
        raw_text = extract_text(source_bytes, filename) if attach_file else attach_text.strip()
        chunks = chunk_text(raw_text, target_chars=attach_cfg["target_chars"], overlap=attach_cfg["overlap"])
        with st.spinner("Generando embeddings del adjunto…"):
            ollama_client = get_ollama_client()
            attach_mat = embed_texts(ollama_client, chunks, embed_model)
        attach_metas = make_attachment_metas(chunks, filename, attach_label)
        st.session_state["attach_cache"][h] = {"mat": attach_mat, "metas": attach_metas}
    # La etiqueta puede cambiar sin cambiar el contenido: actualizar la clave de cita.
    current_cite = attachment_citation_key(filename or "", attach_label or "")
    for m in attach_metas:
        m["_cite"] = current_cite

with st.spinner("Generando embedding y buscando…"):
    ollama_client = get_ollama_client()
    qv = embed_query(ollama_client, query, embed_model).reshape(1, -1)
    pool = pool_size(k, index.ntotal, has_filter)
    d_idx, dist_map = dense_rank(index, qv, pool)
    if use_hybrid and bm25 is not None:
        ranked = rrf_fuse(d_idx, bm25_rank(bm25, query, pool))
    else:
        ranked = [(i, dist_map[i]) for i in d_idx]

    corpus_results = []
    for idx, score in ranked:
        if idx >= len(meta):
            continue
        m = meta[idx]
        if not passes_filters(m, type_=_type_f, paper=paper_filter or None,
                              sections=sel_sections or None,
                              year_start=ys, year_end=ye):
            continue
        corpus_results.append((score, idx, m))
        if len(corpus_results) >= k:
            break

    if attach_active and attach_mat is not None:
        attach_scored = rank_attachment(qv, attach_mat)
        results = fuse_results(
            corpus_results, attach_scored, attach_metas,
            k=k, n_min=n_min_attach,
            hybrid=(use_hybrid and bm25 is not None),
        )
    else:
        results = corpus_results

if not results:
    if sel_sections:
        st.info(
            "Sin resultados para las secciones seleccionadas "
            f"({', '.join(sel_sections)}). Es posible que este índice no esté "
            "re-indexado con `section_canonical` (item 32): re-trocea y "
            "re-indexa con `--force` antes de filtrar por sección."
        )
    st.warning("Sin resultados con esos filtros. Prueba aflojando filtros o cambia la consulta.")
    st.stop()

retrieved_papers = list(dict.fromkeys(
    m.get("paper_id", "") for _, _, m in results
    if m.get("paper_id") and m.get("paper_id") != "__attachment__"
))
st.session_state["_last_retrieved_papers"] = retrieved_papers
st.session_state["_last_project"]          = project

# Persistir los chunks recuperados para una posible consulta premium posterior
# (Modo A "mismos fragmentos"). Solo lo necesario y JSON-serializable: el score
# y la metadata del chunk (texto, sección, paper_id, _cite si es adjunto).
# session_state basta: sobrevive a los reruns dentro de la sesión, que es lo que
# necesita el flujo "consulta gratis → Profundizar a continuación".
st.session_state["_last_results"] = [
    {"score": float(score), "m": m} for score, _idx, m in results
]
st.session_state["_last_query"]       = query
st.session_state["_last_phase"]       = phase
st.session_state["_last_embed_model"] = embed_model
# Una consulta gratuita nueva invalida cualquier respuesta premium anterior
# y también el hilo de chat (el chat va ligado al conjunto de papers actual).
st.session_state.pop("_premium_answer", None)
st.session_state.pop("_premium_info", None)
st.session_state.pop("_premium_chat_history", None)
st.session_state.pop("_premium_chat_cost", None)
st.session_state.pop("_premium_chat_last_cost", None)
st.session_state.pop("_premium_chat_last_info", None)
st.session_state.pop("_premium_chat_mode", None)
st.session_state.pop("_premium_chat_topk", None)

# ---------------------------------------------------------------------------
# Síntesis
# ---------------------------------------------------------------------------

if do_synth and synth_model:
    st.subheader("Respuesta")

    _meta_jsonl = project_base(project) / project / "metadata" / "papers_metadata.jsonl"
    _meta_mtime = _meta_jsonl.stat().st_mtime if _meta_jsonl.exists() else 0.0
    papers_meta = load_papers_meta(project, _meta_mtime)

    # Pintamos manualmente (no st.write_stream) para sustituir [N] por las
    # claves de cita una vez completada la generación.
    out_box = st.empty()
    try:
        answer_md, usage_capture, prompt = synthesize_answer(
            provider, synth_model, results, query, papers_meta,
            max_output_tokens, out_box,
        )
    except Exception as e:
        st.error(f"Error al generar respuesta con {provider}: {e}")
        st.stop()

    st.session_state["_last_answer_md"] = answer_md
    st.session_state["_last_query"]     = query
    st.session_state["_last_model"]     = synth_model

    # Coste real y registro
    in_tk  = usage_capture["input_tokens"]
    out_tk = usage_capture["output_tokens"]
    _override = usage_capture.get("cost_usd_override")
    cost = _override if _override is not None else estimate_cost_usd(synth_model, in_tk, out_tk)

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
    record_rag_query_full(
        category=project,
        question=query,
        provider=provider.split(" ")[0].lower(),
        model=synth_model,
        top_k=k,
        retrieved_papers=retrieved_papers,
        answer_md=answer_md,
        estimated_cost=est_cost if 'est_cost' in dir() else 0.0,
        real_cost=cost,
    )

    col_save1, col_save2 = st.columns([3, 1])
    with col_save2:
        if st.button("💾 Guardar como nota", key="save_note"):
            st.session_state["_do_save"] = True
            st.rerun()

    st.divider()

# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------

st.subheader(f"Chunks recuperados ({len(results)})")

_sl = "rrf" if (use_hybrid and bm25 is not None) else "dist"
for rank, (score, idx, m) in enumerate(results, start=1):
    paper_id   = m.get("paper_id", "?")
    section    = m.get("section", "?")
    section_c  = m.get("section_canonical", "?")
    chunk_type = m.get("type", "?")
    phase_tag  = m.get("phase", "?")
    year       = m.get("year") or year_from_paper_id(paper_id)
    snippet    = m.get("text", "")

    with st.expander(
        f"**[{rank}]** {_sl}={score:.4f} · `{paper_id}` · {year} · {section} ({section_c}) · {chunk_type}",
        expanded=(rank <= 3),
    ):
        st.caption(f"Fase: `{phase_tag}` · Tipo: `{chunk_type}` · {_sl}: {score:.4f}")
        st.markdown(snippet)

st.divider()
_render_papers_export(retrieved_papers, project, key_prefix="")
_render_chunks_export(results, project, score_label=_sl, key_prefix="")

# Bloque premium tras una búsqueda recién ejecutada (go=True): _last_results ya
# refleja esta consulta. (El camino go=False se renderiza arriba, antes del stop.)
if not is_public_app():
    render_premium_block()
