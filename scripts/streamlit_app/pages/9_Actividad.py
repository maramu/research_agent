# -*- coding: utf-8 -*-
"""
9_Actividad.py — Actividad reciente del sistema (solo app privada).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for _d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import (
    CANONICAL_CATEGORIES, CATEGORIAS_DIR, NAS_ROOT,
    check_password, fmt_cost, is_public_app,
)

st.set_page_config(page_title="Actividad", page_icon="📊", layout="wide")

if is_public_app():
    st.stop()

if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()

st.title("📊 Actividad reciente")

if st.button("🔄 Actualizar"):
    st.rerun()

_YM = datetime.now().strftime("%Y-%m")

# ── Sección 1 — Uso RAG (mes actual) ─────────────────────────────────────────
with st.expander("📈 Uso RAG — mes actual", expanded=True):
    try:
        usage_path = NAS_ROOT / "metadatos" / "rag_usage" / f"rag_usage_{_YM}.jsonl"
        if not usage_path.exists():
            st.info("Sin consultas este mes.")
        else:
            records = []
            with open(usage_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            if not records:
                st.info("Sin consultas este mes.")
            else:
                total_queries = len(records)
                total_cost = sum(r.get("cost_usd", 0.0) for r in records)
                col1, col2 = st.columns(2)
                col1.metric("Total consultas", total_queries)
                col2.metric("Coste acumulado", fmt_cost(total_cost))

                model_stats: dict = {}
                for r in records:
                    model = r.get("model", "desconocido")
                    cost = r.get("cost_usd", 0.0)
                    if model not in model_stats:
                        model_stats[model] = {
                            "consultas": 0,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "coste": 0.0,
                        }
                    model_stats[model]["consultas"] += 1
                    model_stats[model]["input_tokens"] += r.get("input_tokens", 0)
                    model_stats[model]["output_tokens"] += r.get("output_tokens", 0)
                    model_stats[model]["coste"] += cost

                paid_rows = [
                    {
                        "modelo": m,
                        "consultas": s["consultas"],
                        "tokens input": s["input_tokens"],
                        "tokens output": s["output_tokens"],
                        "coste": fmt_cost(s["coste"]),
                    }
                    for m, s in model_stats.items()
                    if s["coste"] > 0
                ]
                if paid_rows:
                    st.dataframe(paid_rows, hide_index=True)
                else:
                    st.caption("Solo consultas Ollama este mes (sin coste).")
    except Exception as exc:
        st.warning(f"Error leyendo uso RAG: {exc}")

# ── Sección 2 — Últimas consultas RAG ────────────────────────────────────────
with st.expander("🔍 Últimas consultas RAG", expanded=True):
    try:
        queries_path = (
            NAS_ROOT / "metadatos" / "rag_queries" / f"rag_queries_{_YM}.jsonl"
        )
        if not queries_path.exists():
            st.info("Sin consultas este mes.")
        else:
            entries = []
            with open(queries_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            if not entries:
                st.info("Sin consultas este mes.")
            else:
                last_20 = entries[-20:][::-1]
                rows = [
                    {
                        "fecha": e.get("date", ""),
                        "categoría": e.get("category", ""),
                        "pregunta": (e.get("question", "") or "")[:80],
                        "modelo": e.get("model", ""),
                        "coste": fmt_cost(
                            e.get("real_cost", e.get("estimated_cost", 0.0))
                        ),
                    }
                    for e in last_20
                ]
                st.dataframe(rows, hide_index=True)
    except Exception as exc:
        st.warning(f"Error leyendo consultas RAG: {exc}")

# ── Sección 3 — Corpus por método de ingesta ─────────────────────────────────
with st.expander("📂 Corpus por método de ingesta", expanded=True):
    try:
        corpus_rows = []
        for cat in CANONICAL_CATEGORIES:
            jsonl_path = CATEGORIAS_DIR / cat / "metadata" / "papers_metadata.jsonl"
            if not jsonl_path.exists():
                continue
            counts: dict = {
                "scopus": 0, "inbox": 0, "adhoc": 0, "manual": 0, "desconocido": 0,
            }
            total = 0
            with open(jsonl_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    total += 1
                    src = rec.get("source_type") or "desconocido"
                    if src in counts:
                        counts[src] += 1
                    else:
                        counts["desconocido"] += 1
            if total > 0:
                corpus_rows.append(
                    {
                        "categoría": cat,
                        "total": total,
                        "scopus": counts["scopus"],
                        "inbox": counts["inbox"],
                        "adhoc": counts["adhoc"],
                        "manual": counts["manual"],
                    }
                )
        if corpus_rows:
            st.dataframe(corpus_rows, hide_index=True)
        else:
            st.info("No hay metadata de corpus disponible.")
    except Exception as exc:
        st.warning(f"Error construyendo tabla de corpus: {exc}")

# ── Sección 4 — Errores recientes ────────────────────────────────────────────
with st.expander("🔴 Errores recientes", expanded=True):
    try:
        logs_dir = SCRIPTS_DIR.parent / "logs"
        if not logs_dir.exists():
            st.info("Directorio de logs no encontrado.")
        else:
            log_files = sorted(
                logs_dir.glob("*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            files_with_errors = []
            for lf in log_files:
                try:
                    error_lines = [
                        ln.rstrip()
                        for ln in lf.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()
                        if "[ERROR]" in ln
                    ]
                    if error_lines:
                        files_with_errors.append((lf, error_lines))
                except Exception:
                    continue
            if not files_with_errors:
                st.success("Sin errores en los logs recientes.")
            else:
                for lf, error_lines in files_with_errors[:5]:
                    st.markdown(f"**{lf.name}**")
                    st.code("\n".join(error_lines))
    except Exception as exc:
        st.warning(f"Error leyendo logs: {exc}")
