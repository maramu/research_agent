# -*- coding: utf-8 -*-
"""
7_Revision.py — Modo revisión bibliográfica con prompts especializados.
Realiza RAG sobre una categoría con prompts orientados a escritura científica.
"""
import json
import sys
from pathlib import Path

import faiss
import numpy as np
import ollama
import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from utils.export_refs import build_papers_zip, load_papers, to_bibtex
from utils.constants import CANONICAL_SECTIONS, year_from_paper_id
from app_utils import (
    ANTHROPIC_MODELS, OPENAI_MODELS, OLLAMA_MODELS_LLM, OLLAMA_MODEL_EMBED,
    OLLAMA_HOST, ANTHROPIC_API_KEY, OPENAI_API_KEY,
    CATEGORIAS_DIR, LLM_PRICING,
    check_nas, check_ollama,
    estimate_cost_usd, fmt_cost,
    list_existing_categories, list_embedding_phases, embedding_phase_model,
    check_anthropic_api, check_openai_api, check_password, is_public_app,
)

st.set_page_config(
    page_title="Revisión bibliográfica", page_icon="📚", layout="wide"
)
_pwd_env = "PUBLIC_APP_PASSWORD" if is_public_app() else "PRIVATE_APP_PASSWORD"
if not check_password(_pwd_env):
    st.stop()

st.title("📚 Revisión bibliográfica")

st.caption(
    "RAG con prompts especializados para escritura científica. "
    "Selecciona categoría, tipo de síntesis y foco temático."
)

# ── Health checks ─────────────────────────────────────────────────────────────
nas_ok,    nas_msg    = check_nas()
ollama_ok, ollama_msg = check_ollama()
c1, c2 = st.columns(2)
c1.markdown(f"**NAS**: {'🟢' if nas_ok else '🔴'} {nas_msg}")
c2.markdown(f"**Ollama**: {'🟢' if ollama_ok else '🔴'} {ollama_msg}")
if not nas_ok or not ollama_ok:
    st.stop()
st.divider()

# ── Prompts especializados ────────────────────────────────────────────────────
_PROMPTS = {
    "Estado del arte": (
        "Eres un experto científico. Basándote ÚNICAMENTE en los fragmentos "
        "numerados, escribe una síntesis del estado del arte sobre: {focus}.\n"
        "Estructura: (1) Contexto y relevancia, (2) Principales enfoques y "
        "tecnologías, (3) Resultados destacados, (4) Tendencias recientes.\n"
        "Cita las fuentes con [N].\n\n"
        "Fragmentos:\n{context}\n\nSíntesis:"
    ),
    "Artículos clave (tabla Markdown)": (
        "Basándote en los fragmentos numerados, genera una tabla Markdown "
        "con los artículos más relevantes sobre: {focus}.\n"
        "Columnas: | Cita | Año | Metodología | Resultados principales |\n"
        "Incluye al menos los fragmentos más informativos.\n\n"
        "Fragmentos:\n{context}\n\nTabla:"
    ),
    "Lagunas de conocimiento": (
        "Basándote en los fragmentos numerados, identifica lagunas de "
        "conocimiento y líneas de investigación futura sobre: {focus}.\n"
        "Estructura: (1) Aspectos no estudiados, (2) Contradicciones entre "
        "estudios, (3) Limitaciones metodológicas, (4) Preguntas abiertas.\n"
        "Cita con [N].\n\n"
        "Fragmentos:\n{context}\n\nAnálisis:"
    ),
    "Comparativa de mecanismos": (
        "Basándote en los fragmentos numerados, compara mecanismos, procesos "
        "o estrategias sobre: {focus}.\n"
        "Usa tabla Markdown cuando sea útil. Destaca similitudes, diferencias "
        "y condiciones óptimas. Cita con [N].\n\n"
        "Fragmentos:\n{context}\n\nComparativa:"
    ),
    "Introducción preliminar": (
        "Eres un científico redactando la introducción de un artículo sobre "
        "{focus}. Basándote ÚNICAMENTE en los fragmentos numerados, escribe "
        "3-4 párrafos: contexto del problema, estado del arte, brecha de "
        "conocimiento, objetivo implícito. Estilo académico, citas con [N].\n\n"
        "Fragmentos:\n{context}\n\nIntroducción:"
    ),
}

# ── Caché FAISS ───────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Cargando índice FAISS…")
def _load_index(project: str, phase: str, mtime: float):
    emb_dir   = CATEGORIAS_DIR / project / "embeddings" / phase
    idx_path  = emb_dir / "index.faiss"
    meta_path = emb_dir / "metadata.jsonl"
    cfg_path  = emb_dir / "config.json"
    if not (idx_path.exists() and meta_path.exists()):
        return None, None, {}
    index = faiss.read_index(str(idx_path))
    meta = []
    with meta_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                meta.append(json.loads(line))
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    return index, meta, cfg


@st.cache_resource(show_spinner=False)
def _ollama_client():
    return ollama.Client(host=OLLAMA_HOST, timeout=120)


@st.cache_resource(show_spinner=False)
def _anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@st.cache_resource(show_spinner=False)
def _openai_client():
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Corpus")
    projects = list_existing_categories()
    if not projects:
        st.error("No hay categorías disponibles.")
        st.stop()
    project = st.selectbox("Categoría", options=projects)

    phases = list_embedding_phases(project)
    if not phases:
        st.error("Sin índice FAISS para esta categoría.")
        st.stop()
    phase_labels = {
        p: f"{p}  ·  ({embedding_phase_model(project, p)})" for p in phases
    }
    phase = st.selectbox("Índice", options=phases,
                         format_func=lambda p: phase_labels[p])

    k = st.slider("Top-k chunks", 5, 40, 15)
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

    st.divider()
    st.header("Síntesis")

    _provider_options = (
        ["Ollama (local)"]
        if is_public_app()
        else ["Ollama (local)", "Anthropic (Claude)", "OpenAI (GPT)"]
    )
    provider = st.selectbox("Provider", _provider_options)

    if provider == "Ollama (local)":
        synth_model = st.selectbox("Modelo", OLLAMA_MODELS_LLM, index=0)
    elif provider == "Anthropic (Claude)":
        ant_ok, ant_msg = check_anthropic_api()
        if not ant_ok:
            st.error(ant_msg)
            synth_model = None
        else:
            synth_model = st.selectbox("Modelo", ANTHROPIC_MODELS, index=1)
    else:
        oai_ok, oai_msg = check_openai_api()
        if not oai_ok:
            st.error(oai_msg)
            synth_model = None
        else:
            synth_model = st.selectbox("Modelo", OPENAI_MODELS, index=0)

    max_tokens = st.slider("Máx tokens respuesta", 512, 8192, 2048, 256)

# ── Main ──────────────────────────────────────────────────────────────────────
prompt_type = st.radio(
    "Tipo de síntesis",
    options=list(_PROMPTS.keys()),
    horizontal=True,
)

focus = st.text_input(
    "Foco temático",
    placeholder=(
        "Ej: eliminación de H2S en biogás mediante bacterias NR-SOB en "
        "condiciones anóxicas"
    ),
)

# Estimación coste
if synth_model and focus:
    avg_chars  = 1200 * k + 500
    est_in_tk  = avg_chars // 4
    est_out_tk = max_tokens // 3
    est_cost   = estimate_cost_usd(synth_model, est_in_tk, est_out_tk)
    if est_cost > 0:
        st.info(
            f"💰 Coste estimado: ~{fmt_cost(est_cost)} "
            f"({est_in_tk:,} input + ~{est_out_tk:,} output tokens, k={k})"
        )

go = st.button("📚 Generar revisión", type="primary",
               disabled=not (focus.strip() and synth_model))

# ── Handle save flag ──────────────────────────────────────────────────────────
if st.session_state.pop("_rev_do_save", False):
    import re as _re
    from datetime import datetime as _dt
    _ans     = st.session_state.get("_rev_answer_md", "")
    _focus   = st.session_state.get("_rev_focus", "")
    _project = st.session_state.get("_rev_project", "")
    _ptype   = st.session_state.get("_rev_prompt_type", "")
    if _ans:
        _date = _dt.now().strftime("%Y-%m-%d")
        _slug = _re.sub(r"[^\w]+", "_", _focus.strip()[:40],
                        flags=_re.ASCII).strip("_").lower()
        _fname = f"{_date}_{_project}_{_slug}.md"
        _header = (
            f"# {_ptype}: {_focus}\n\n"
            f"**Categoría**: {_project}  \n"
            f"**Fecha**: {_date}\n\n---\n\n"
        )
        notes_dir = CATEGORIAS_DIR.parent / "notas_rag" / _project
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / _fname).write_text(_header + _ans, encoding="utf-8")
        st.success(f"Nota guardada: `notas_rag/{_project}/{_fname}`")

if not go:
    st.stop()

# ── Retrieval ─────────────────────────────────────────────────────────────────
_idx_path = CATEGORIAS_DIR / project / "embeddings" / phase / "index.faiss"
_mtime    = _idx_path.stat().st_mtime if _idx_path.exists() else 0.0
index, meta, cfg = _load_index(project, phase, _mtime)
if index is None:
    st.error("No se pudo cargar el índice FAISS.")
    st.stop()

embed_model = cfg.get("model", OLLAMA_MODEL_EMBED)

with st.spinner("Buscando fragmentos relevantes…"):
    ol_client = _ollama_client()
    resp = ol_client.embeddings(model=embed_model, prompt=focus)
    qv = np.array(resp["embedding"], dtype="float32").reshape(1, -1)
    has_filter = bool(sel_sections or ys or ye)
    n_fetch    = index.ntotal if has_filter else min(index.ntotal, k * 3)
    D, I = index.search(qv, n_fetch)

results = []
for dist, idx in zip(D[0].tolist(), I[0].tolist()):
    if idx < 0 or idx >= len(meta):
        continue
    m = meta[idx]
    if sel_sections and m.get("section_canonical") not in sel_sections:
        continue
    year = m.get("year") or year_from_paper_id(m.get("paper_id", ""))
    if (ys and (year is None or year < ys)) or (ye and (year is None or year > ye)):
        continue
    results.append((dist, idx, m))
    if len(results) >= k:
        break

if not results:
    if sel_sections:
        st.info(
            "Sin resultados para las secciones seleccionadas "
            f"({', '.join(sel_sections)}). Es posible que este índice no esté "
            "re-indexado con `section_canonical` (item 32): re-trocea y "
            "re-indexa con `--force` antes de filtrar por sección."
        )
    st.warning("Sin resultados. Prueba con otro foco temático o más chunks.")
    st.stop()

# ── Construcción del contexto ─────────────────────────────────────────────────
context_parts = []
for i, (_, _, m) in enumerate(results, 1):
    snippet  = m.get("text", "").strip()
    paper_id = m.get("paper_id", "?")
    section  = m.get("section", "?")
    context_parts.append(f"[{i}] ({paper_id}, {section})\n{snippet}")
context = "\n\n---\n\n".join(context_parts)

prompt_template = _PROMPTS[prompt_type]
prompt = prompt_template.format(focus=focus, context=context)

# ── Streaming ─────────────────────────────────────────────────────────────────
st.subheader(f"📝 {prompt_type}")
usage_capture = {"input_tokens": 0, "output_tokens": 0, "is_estimated": False}


def _stream_ollama():
    full = ""
    for chunk in ol_client.generate(model=synth_model, prompt=prompt, stream=True):
        text = chunk.get("response", "")
        full += text
        yield text
    usage_capture["input_tokens"]  = max(1, len(prompt) // 4)
    usage_capture["output_tokens"] = max(1, len(full) // 4)
    usage_capture["is_estimated"]  = True


def _stream_anthropic():
    client = _anthropic_client()
    with client.messages.stream(
        model=synth_model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
        final = stream.get_final_message()
        usage_capture["input_tokens"]  = final.usage.input_tokens
        usage_capture["output_tokens"] = final.usage.output_tokens


def _stream_openai():
    client = _openai_client()
    for chunk in client.chat.completions.create(
        model=synth_model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        stream=True, stream_options={"include_usage": True},
    ):
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
        if getattr(chunk, "usage", None):
            usage_capture["input_tokens"]  = chunk.usage.prompt_tokens
            usage_capture["output_tokens"] = chunk.usage.completion_tokens


try:
    if provider == "Ollama (local)":
        answer_md = st.write_stream(_stream_ollama())
    elif provider == "Anthropic (Claude)":
        answer_md = st.write_stream(_stream_anthropic())
    else:
        answer_md = st.write_stream(_stream_openai())
except Exception as e:
    st.error(f"Error al generar respuesta: {e}")
    st.stop()

# Persistir para el botón de guardar
st.session_state["_rev_answer_md"]   = answer_md
st.session_state["_rev_focus"]       = focus
st.session_state["_rev_project"]     = project
st.session_state["_rev_prompt_type"] = prompt_type

in_tk  = usage_capture["input_tokens"]
out_tk = usage_capture["output_tokens"]
cost   = estimate_cost_usd(synth_model, in_tk, out_tk)
label  = "estimado" if usage_capture["is_estimated"] else "real"
st.caption(
    f"📊 Coste {label}: **{fmt_cost(cost)}** · "
    f"{in_tk:,} input + {out_tk:,} output tokens · `{synth_model}`"
)

# Descargar Markdown + guardar en NAS
col1, col2 = st.columns([2, 1])
with col1:
    st.download_button(
        "⬇️ Descargar como Markdown",
        data=answer_md,
        file_name=f"{project}_{prompt_type.replace(' ', '_')}.md",
        mime="text/markdown",
        key="dl_revision",
    )
with col2:
    if st.button("💾 Guardar en NAS", key="save_revision"):
        st.session_state["_rev_do_save"] = True
        st.rerun()

# ── Exportar papers usados ───────────────────────────────────────────────────
st.divider()
with st.expander("📦 Exportar papers usados en esta revisión", expanded=False):
    _rev_papers = list(dict.fromkeys(
        m.get("paper_id", "") for _, _, m in results if m.get("paper_id")
    ))
    st.caption(f"{len(_rev_papers)} papers únicos recuperados.")

    # ZIP
    _col1, _col2 = st.columns(2)
    _inc_pdf = _col1.checkbox("PDF",       value=True, key="rev_zip_pdf")
    _inc_md  = _col2.checkbox("MD limpio", value=True, key="rev_zip_md")
    if _inc_pdf or _inc_md:
        _zip = build_papers_zip(
            _rev_papers, project, CATEGORIAS_DIR,
            include_pdf=_inc_pdf, include_md=_inc_md,
        )
        st.download_button(
            f"⬇️ ZIP papers ({len(_rev_papers)})",
            data=_zip,
            file_name=f"{project}_revision_papers.zip",
            mime="application/zip",
            key="rev_dl_zip",
        )

    # BibTeX desde metadata
    _jsonl = CATEGORIAS_DIR / project / "metadata" / "papers_metadata.jsonl"
    if _jsonl.exists():
        _all = load_papers(_jsonl)
        _sel = [m for m in _all if m.get("paper_id") in set(_rev_papers)]
        if _sel:
            st.download_button(
                f"📚 BibTeX ({len(_sel)} papers)",
                data=to_bibtex(_sel),
                file_name=f"{project}_revision.bib",
                mime="text/plain",
                key="rev_dl_bib",
            )

# ── Fragmentos usados ─────────────────────────────────────────────────────────
st.divider()
with st.expander(f"Fragmentos recuperados ({len(results)})", expanded=False):
    for rank, (dist, _, m) in enumerate(results, 1):
        _yr = m.get("year") or year_from_paper_id(m.get("paper_id", ""))
        st.markdown(
            f"**[{rank}]** `{m.get('paper_id', '?')}` · {_yr} · "
            f"{m.get('section', '?')} ({m.get('section_canonical', '?')}) · "
            f"dist={dist:.4f}"
        )
        st.markdown(m.get("text", ""))
        st.divider()
