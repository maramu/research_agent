# -*- coding: utf-8 -*-
"""
14_Preparar_clase.py — Prepara material docente contrastando el MANUAL de
docencia (libros_docencia) con los PAPERS recientes de una o varias categorías.

Solo app privada. Cero lógica duplicada: reutiliza rag_core (índices,
proveedores, síntesis con citas, export) y utils.attachments.fuse_results
(fusión con cupo mínimo garantizado, el mismo patrón "híbrido sensato" de los
adjuntos). Todos los índices comparten bge-m3 → los scores L2 son comparables.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for _d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import (
    OLLAMA_MODEL_EMBED, OLLAMA_MODELS_LLM,
    ANTHROPIC_MODELS, OPENAI_MODELS, OPENROUTER_MODELS,
    ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY,
    BOOKS_PROJECT, project_base,
    check_nas, check_ollama, estimate_cost_usd, fmt_cost,
    list_existing_categories, record_rag_query, record_rag_query_full,
    check_password, is_public_app,
)
from rag_core import (
    load_index, load_papers_meta, get_ollama_client, embed_query,
    _build_context_text, synthesize_answer,
)
from utils.constants import year_from_paper_id
from utils.citations import citation_for_chunk, CITE_PROMPT_RULES
from utils.retrieval import dense_rank
from utils.attachments import fuse_results
from utils.export_refs import build_chunks_markdown

st.set_page_config(page_title="Preparar clase", page_icon="🎓", layout="wide")

# ── Solo app privada ──────────────────────────────────────────────────────────
if is_public_app():
    st.error("Esta página solo está disponible en la app privada.")
    st.stop()
if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()

st.title("🎓 Preparar clase")
st.caption("Contrasta el **manual de docencia** con los **papers recientes** y cita "
           "cada fuente en su formato (libro: cap.+página; paper: autor, año, DOI).")

# ── Pre-flight ────────────────────────────────────────────────────────────────
nas_ok, nas_msg = check_nas()
ollama_ok, ollama_msg = check_ollama()
c1, c2 = st.columns(2)
c1.markdown(f"**NAS**: {'🟢' if nas_ok else '🔴'} {nas_msg}")
c2.markdown(f"**Ollama**: {'🟢' if ollama_ok else '🔴'} {ollama_msg}")
if not nas_ok:
    st.error("El NAS no está montado.")
    st.stop()
if not ollama_ok:
    st.error("Ollama no está accesible (se necesita para embeber la consulta).")
    st.stop()

st.divider()

# ── Entrada ───────────────────────────────────────────────────────────────────
question = st.text_area("Pregunta / tema de la clase", height=90,
                        placeholder="p.ej. Medición y control del oxígeno disuelto en biorreactores")

_all_cats = [c for c in list_existing_categories() if c != BOOKS_PROJECT]
sel_cats = st.multiselect("Categorías de papers", options=_all_cats,
                          default=_all_cats[:1] if _all_cats else [])
col_a, col_b, col_c = st.columns(3)
include_books = col_a.toggle("Incluir libros de docencia", value=True)
top_k = col_b.slider("Fragmentos totales (top-k)", 4, 20, 10)
book_quota = col_c.slider("Cupo mínimo de libro", 0, 8, 3,
                          help="Fragmentos de libro garantizados para que no los "
                               "tape el volumen de papers.")

# ── Selector de proveedor/modelo (por defecto un proveedor capaz) ─────────────
_providers = []
if ANTHROPIC_API_KEY:
    _providers.append("Anthropic (Claude)")
if OPENAI_API_KEY:
    _providers.append("OpenAI (GPT)")
if OPENROUTER_API_KEY:
    _providers.append("OpenRouter")
_providers.append("Ollama (local)")  # siempre disponible como opción

_MODELS_BY_PROVIDER = {
    "Anthropic (Claude)": (ANTHROPIC_MODELS, 1),   # sonnet por defecto
    "OpenAI (GPT)":       (OPENAI_MODELS, 1),
    "OpenRouter":         (OPENROUTER_MODELS, 1),
    "Ollama (local)":     (OLLAMA_MODELS_LLM, 0),
}

col_p, col_m = st.columns(2)
provider = col_p.selectbox(
    "Proveedor de síntesis", options=_providers, index=0,
    help="El contraste depende de citar bien; por defecto un proveedor capaz. "
         "El modelo local queda como opción.",
)
_models, _mdef = _MODELS_BY_PROVIDER[provider]
synth_model = col_m.selectbox("Modelo", options=_models,
                              index=min(_mdef, len(_models) - 1))

go = st.button("🎓 Preparar", type="primary", disabled=not question.strip())

st.divider()


# ── Recuperación multi-índice + fusión con cupo de libro ──────────────────────
def _retrieve_category(cat: str, qv, pool_mult: int):
    idx_path = project_base(cat) / cat / "embeddings" / "all" / "index.faiss"
    mtime = idx_path.stat().st_mtime if idx_path.exists() else 0.0
    index, meta, _cfg = load_index(cat, "all", mtime)
    if index is None:
        return []
    pool = min(index.ntotal, max(top_k * pool_mult, 50))
    d_idx, dist_map = dense_rank(index, qv, pool)
    return [(dist_map[i], i, meta[i]) for i in d_idx]


if go:
    if not sel_cats and not include_books:
        st.warning("Selecciona al menos una categoría o activa los libros.")
        st.stop()

    client = get_ollama_client()
    qv = embed_query(client, question, OLLAMA_MODEL_EMBED).reshape(1, -1)

    # Corpus de papers (L2 comparable entre índices por compartir bge-m3).
    corpus_results = []
    for cat in sel_cats:
        corpus_results.extend(_retrieve_category(cat, qv, pool_mult=8))
    corpus_results.sort(key=lambda x: x[0])

    # Metadata de citas: merge de todas las fuentes (papers + libros).
    papers_meta: dict = {}
    for proj in list(sel_cats) + ([BOOKS_PROJECT] if include_books else []):
        _mj = project_base(proj) / proj / "metadata" / "papers_metadata.jsonl"
        _mt = _mj.stat().st_mtime if _mj.exists() else 0.0
        papers_meta.update(load_papers_meta(proj, _mt))

    # Fusión con cupo mínimo de libro (mismo patrón que los adjuntos).
    if include_books:
        b_idx_path = project_base(BOOKS_PROJECT) / BOOKS_PROJECT / "embeddings" / "all" / "index.faiss"
        b_mtime = b_idx_path.stat().st_mtime if b_idx_path.exists() else 0.0
        b_index, b_meta, _bcfg = load_index(BOOKS_PROJECT, "all", b_mtime)
        if b_index is None:
            st.warning("No hay índice de libros_docencia; se usan solo papers.")
            results = corpus_results[:top_k]
        else:
            b_pool = min(b_index.ntotal, max(book_quota * 5, 30))
            bd_idx, bd_map = dense_rank(b_index, qv, b_pool)
            book_scored = [(i, bd_map[i]) for i in bd_idx]
            results = fuse_results(corpus_results, book_scored, b_meta,
                                   k=top_k, n_min=book_quota, hybrid=False)
    else:
        results = corpus_results[:top_k]

    if not results:
        st.error("No se recuperó ningún fragmento. ¿Están construidos los índices?")
        st.stop()

    st.session_state["_pc_results"] = results
    st.session_state["_pc_papers_meta"] = papers_meta
    st.session_state["_pc_query"] = question

    # ── Síntesis con contraste explícito libro ↔ papers ───────────────────────
    context = _build_context_text(m for _, _, m in results)
    system_content = f"""Eres un asistente que prepara material docente. Dispones de fragmentos numerados de DOS tipos de fuente:
- MANUAL / LIBRO de docencia: base conceptual establecida.
- PAPERS recientes: matices, avances y excepciones.

Estructura la respuesta CONTRASTANDO explícitamente ambas: primero lo que dice el
manual y, a continuación, cómo los papers recientes lo matizan o actualizan
(fórmula: "según el manual … ; los papers recientes matizan …").
Si un tipo de fuente no aporta, dilo.
{CITE_PROMPT_RULES}
IMPORTANTE: conserva las etiquetas [N] EXACTAS de cada fragmento (no las cambies
ni las quites); cada afirmación lleva su [N].

Fragmentos:
{context}

Recuerda: cita con [N] junto a cada dato; sin sección de Referencias."""

    st.subheader("Respuesta (manual ↔ papers)")
    out_box = st.empty()
    try:
        answer_md, usage, _prompt = synthesize_answer(
            provider, synth_model, results, question, papers_meta,
            2500, out_box, system_content=system_content,
        )
    except Exception as e:
        st.error(f"Error al generar con {provider}: {e}")
        st.stop()

    # Coste + registro (reutilizado).
    in_tk, out_tk = usage["input_tokens"], usage["output_tokens"]
    _ov = usage.get("cost_usd_override")
    cost = _ov if _ov is not None else estimate_cost_usd(synth_model, in_tk, out_tk)
    label = "Coste estimado" if usage["is_estimated"] else "Coste real"
    st.caption(f"📊 {label}: **{fmt_cost(cost)}** · {in_tk:,}+{out_tk:,} tokens · `{synth_model}`")

    retrieved_papers = sorted({m.get("paper_id") for _, _, m in results if m.get("paper_id")})
    record_rag_query(
        provider=provider.split(" ")[0].lower(), model=synth_model,
        input_tokens=in_tk, output_tokens=out_tk, cost_usd=cost,
        query=question, project="preparar_clase",
        is_estimated=usage["is_estimated"], mode="preparar_clase",
    )
    record_rag_query_full(
        category="preparar_clase", question=question,
        provider=provider.split(" ")[0].lower(), model=synth_model,
        top_k=top_k, retrieved_papers=retrieved_papers,
        answer_md=answer_md, estimated_cost=0.0, real_cost=cost,
    )

    st.divider()


# ── Panel de fragmentos (distingue libro vs paper) ────────────────────────────
_results = st.session_state.get("_pc_results")
_pm = st.session_state.get("_pc_papers_meta", {})
if _results:
    n_books = sum(1 for _, _, m in _results if m.get("doc_type") == "book")
    n_papers = len(_results) - n_books
    st.subheader(f"Fragmentos recuperados · 📘 {n_books} libro · 📄 {n_papers} papers")

    for rank, (score, _idx, m) in enumerate(_results, start=1):
        is_book = m.get("doc_type") == "book"
        icon = "📘" if is_book else "📄"
        kind = "LIBRO" if is_book else "PAPER"
        cite = citation_for_chunk(m, _pm)
        if is_book:
            head = (f"{icon} **[{rank}]** `{kind}` · dist={score:.1f} · "
                    f"{m.get('heading_path', '?')} · pp. "
                    f"{m.get('page_start', '?')}-{m.get('page_end', '?')}")
        else:
            year = m.get("year") or year_from_paper_id(m.get("paper_id", ""))
            head = (f"{icon} **[{rank}]** `{kind}` · dist={score:.1f} · "
                    f"{m.get('paper_id', '?')} · {year} · {m.get('section', '?')}")
        with st.expander(head, expanded=(rank <= 3)):
            st.caption(f"Cita: {cite}")
            st.markdown(m.get("text", ""))

    # Export de chunks (reutiliza build_chunks_markdown con la metadata fusionada).
    st.divider()
    _md = build_chunks_markdown(
        _results, "preparar_clase", project_base(BOOKS_PROJECT), _pm,
        query=st.session_state.get("_pc_query"), score_label="dist",
    )
    st.download_button(
        "⬇️ Descargar fragmentos (Markdown con referencias)",
        data=_md.encode("utf-8"),
        file_name="preparar_clase_fragmentos.md",
        mime="text/markdown",
        key="pc_dl_chunks",
    )
