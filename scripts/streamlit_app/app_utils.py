# -*- coding: utf-8 -*-
"""
app_utils.py — Helpers compartidos para la app Streamlit de research_agent.

Centraliza:
  - Inserción de scripts/ en sys.path para importar pipeline.py
  - Health checks (NAS, Ollama, GROBID)
  - Conteos por categoría (PDFs, MDs, summaries, embeddings…)
  - Carga/guardado de YAML
  - Constantes de paths
  - Pricing de modelos LLM comerciales + tracking de uso mensual
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# sys.path — para que las pages puedan hacer `from pipeline import ...`
# ---------------------------------------------------------------------------

STREAMLIT_APP_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR       = STREAMLIT_APP_DIR.parent
PROJECT_ROOT      = SCRIPTS_DIR.parent
CONFIG_DIR        = PROJECT_ROOT / "config"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_ENV_FILE = CONFIG_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

# Reexports de pipeline
try:
    from pipeline import (  # noqa: F401
        run_scopus, run_inbox, run_adhoc,
        process_category, detect_affected_categories, ensure_project_dirs,
        check_nas as _check_nas_pipeline,
        NAS_ROOT, CATEGORIAS_DIR, INBOX_DIR, INBOX_CSV_DIR,
    )
    PIPELINE_AVAILABLE = True
    PIPELINE_IMPORT_ERROR = None
except Exception as e:
    PIPELINE_AVAILABLE = False
    PIPELINE_IMPORT_ERROR = str(e)
    NAS_ROOT       = Path("/Volumes/research")
    CATEGORIAS_DIR = NAS_ROOT / "categorias"
    INBOX_DIR      = NAS_ROOT / "inbox"
    INBOX_CSV_DIR  = NAS_ROOT / "inbox_csv"

METADATOS_DIR   = NAS_ROOT / "metadatos"
DOI_MANUAL_XLSX = METADATOS_DIR / "doi_manual.xlsx"
RAG_USAGE_DIR   = METADATOS_DIR / "rag_usage"  # uno por mes: rag_usage_YYYY-MM.jsonl

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://pciq22.uca.es:11434")
GROBID_URL  = os.getenv("GROBID_URL",  "http://pciq22.uca.es:8070")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ---------------------------------------------------------------------------
# Categorías canónicas
# ---------------------------------------------------------------------------

from utils.constants import OLLAMA_MODEL_EMBED, CANONICAL_CATEGORIES  # noqa: E402

# ---------------------------------------------------------------------------
# Modelos disponibles por provider
# ---------------------------------------------------------------------------

OLLAMA_MODELS_LLM     = ["qwen2.5:14b-instruct"]
OLLAMA_EMBED_MODELS   = ["nomic-embed-text", "bge-m3", "snowflake-arctic-embed:l"]
# OLLAMA_MODEL_EMBED imported from utils.constants

ANTHROPIC_MODELS = [
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]

OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
]

OPENROUTER_MODELS = [
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
    "moonshotai/kimi-k2.6",
    "z-ai/glm-5.2",
]

# ---------------------------------------------------------------------------
# Pricing — USD por 1M tokens (input / output)
#
# IMPORTANTE: estos precios son APROXIMADOS, verifica los actuales antes de
# usar en serio:
#   - Anthropic: https://docs.claude.com/en/docs/about-claude/pricing
#   - OpenAI:    https://openai.com/api/pricing
# ---------------------------------------------------------------------------

# Precios verificados: 2026-05-27
# Anthropic: https://platform.claude.com/docs/en/docs/about-claude/models
# OpenAI:    https://developers.openai.com/api/docs/pricing
LLM_PRICING: Dict[str, Dict[str, float]] = {
    # Anthropic
    "claude-haiku-4-5":  {"input": 1.00, "output":  5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-7":   {"input": 5.00, "output": 25.00},
    # OpenAI
    "gpt-4o-mini":       {"input": 0.15, "output":  0.60},
    "gpt-4o":            {"input": 2.50, "output": 10.00},
    # OpenRouter — coste real leído de la respuesta de la API (usage.include),
    # no precios estáticos; ver stream_openrouter() en 2_RAG.py
    # Ollama — local, sin coste
    "qwen2.5:14b-instruct": {"input": 0.0,   "output": 0.0},
}

# Ventanas de contexto aproximadas (tokens) para los modelos usables en RAG.
# Se usan para advertir cuando un hilo de chat se acerca al límite.
LLM_CONTEXT_WINDOWS: Dict[str, int] = {
    # Anthropic
    "claude-haiku-4-5":  200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-7":   200_000,
    # OpenAI
    "gpt-4o-mini": 128_000,
    "gpt-4o":      128_000,
    # OpenRouter (valores conservadores/estimados)
    "deepseek/deepseek-v4-flash": 64_000,
    "deepseek/deepseek-v4-pro":   64_000,
    "moonshotai/kimi-k2.6":      256_000,
    "z-ai/glm-5.2":              128_000,
    # Ollama
    "qwen2.5:14b-instruct": 32_768,
}


def model_provider(model: str) -> str:
    """Devuelve el provider de un model id."""
    if model in ANTHROPIC_MODELS:
        return "anthropic"
    if model in OPENAI_MODELS:
        return "openai"
    if model in OPENROUTER_MODELS:
        return "openrouter"
    return "ollama"


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calcula el coste en USD a partir de los tokens y el pricing del modelo."""
    pricing = LLM_PRICING.get(model)
    if not pricing:
        return 0.0
    return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]


def approx_tokens_from_chars(text: str) -> int:
    """Aproximación grosera: 1 token ≈ 4 chars en inglés (mas en español)."""
    return max(1, len(text) // 4)


def estimate_cost_pre_query(
    model: str,
    prompt_text: str,
    expected_output_tokens: int = 500,
) -> Tuple[int, int, float]:
    """Pre-estimación antes de lanzar la consulta. Devuelve (input_tk, output_tk, usd)."""
    input_tk  = approx_tokens_from_chars(prompt_text)
    output_tk = expected_output_tokens
    cost      = estimate_cost_usd(model, input_tk, output_tk)
    return input_tk, output_tk, cost


# ---------------------------------------------------------------------------
# Tracking de uso mensual (rag_usage_YYYY-MM.jsonl)
# ---------------------------------------------------------------------------

def _current_usage_file() -> Path:
    """Devuelve la ruta del fichero de uso del mes actual."""
    RAG_USAGE_DIR.mkdir(parents=True, exist_ok=True)
    month = datetime.now().strftime("%Y-%m")
    return RAG_USAGE_DIR / f"rag_usage_{month}.jsonl"


def record_rag_query(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    query: str,
    project: str,
    is_estimated: bool = False,
    mode: str = "standard",
) -> None:
    """Apenda un registro al jsonl del mes actual.

    ``mode`` distingue el tipo de consulta ("standard" o, para la consulta de
    pago sobre artículos ya rescatados, "premium_same_chunks"/"premium_deepen").

    Si el NAS no está accesible, falla silenciosamente — no se quiere bloquear
    la respuesta del RAG por no poder escribir el contador.
    """
    try:
        usage_file = _current_usage_file()
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "provider":      provider,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "cost_usd":      round(cost_usd, 6),
            "is_estimated":  is_estimated,
            "project":       project,
            "query_preview": (query or "")[:120],
            "mode":          mode,
        }
        with usage_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def record_rag_query_full(
    *,
    category: str,
    question: str,
    provider: str,
    model: str,
    top_k: int,
    retrieved_papers: list[str],
    answer_md: str,
    estimated_cost: float,
    real_cost: float,
    mode: str = "standard",
) -> None:
    """Guarda log completo en rag_queries/rag_queries_YYYY-MM.jsonl.

    ``mode`` distingue consultas estándar de las premium sobre artículos ya
    rescatados ("premium_same_chunks"/"premium_deepen").
    """
    now = datetime.now()
    record = {
        "date":             now.strftime("%Y-%m-%d %H:%M"),
        "category":         category,
        "question":         question,
        "provider":         provider,
        "model":            model,
        "top_k":            top_k,
        "retrieved_papers": retrieved_papers,
        "answer_md":        answer_md,
        "estimated_cost":   estimated_cost,
        "real_cost":        real_cost,
        "mode":             mode,
    }
    out_dir = NAS_ROOT / "metadatos" / "rag_queries"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"rag_queries_{now.strftime('%Y-%m')}.jsonl"
    with out_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_monthly_usage(month: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve totales del mes pedido (defecto: actual).

    Estructura:
      {
        "month": "2026-05",
        "n_queries": int,
        "total_cost_usd": float,
        "by_provider": {"anthropic": {"queries": n, "cost_usd": x}, ...},
        "by_model":    {model_id: {"queries": n, "cost_usd": x}, ...},
      }
    """
    month_str = month or datetime.now().strftime("%Y-%m")
    usage_file = RAG_USAGE_DIR / f"rag_usage_{month_str}.jsonl"

    totals = {
        "month":          month_str,
        "n_queries":      0,
        "total_cost_usd": 0.0,
        "by_provider":    {},
        "by_model":       {},
    }
    if not usage_file.exists():
        return totals

    try:
        with usage_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                totals["n_queries"] += 1
                cost = float(rec.get("cost_usd", 0.0))
                totals["total_cost_usd"] += cost

                prov = rec.get("provider", "?")
                totals["by_provider"].setdefault(prov, {"queries": 0, "cost_usd": 0.0})
                totals["by_provider"][prov]["queries"]  += 1
                totals["by_provider"][prov]["cost_usd"] += cost

                model = rec.get("model", "?")
                totals["by_model"].setdefault(model, {"queries": 0, "cost_usd": 0.0})
                totals["by_model"][model]["queries"]  += 1
                totals["by_model"][model]["cost_usd"] += cost
    except Exception:
        pass

    return totals


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def check_nas() -> Tuple[bool, str]:
    if NAS_ROOT.exists() and NAS_ROOT.is_dir():
        return True, f"Montado en {NAS_ROOT}"
    return False, f"No existe {NAS_ROOT}. Monta con: open smb://synology/research"


def check_ollama(timeout: float = 2.0) -> Tuple[bool, str]:
    try:
        t0 = time.time()
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if r.ok:
            n = len(r.json().get("models", []))
            return True, f"OK ({n} modelos) — {ms} ms"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Conexión rechazada (¿VPN UCA activa?)"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


def check_grobid(timeout: float = 2.0) -> Tuple[bool, str]:
    try:
        t0 = time.time()
        r = requests.get(f"{GROBID_URL}/api/isalive", timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if r.ok and r.text.strip().lower() == "true":
            return True, f"OK (isalive=true) — {ms} ms"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Conexión rechazada (¿VPN UCA activa?)"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


def check_nas_space(threshold_gb: float = 10.0) -> Tuple[bool, float, float]:
    """Devuelve (ok, libre_gb, total_gb). ok=True si libre >= threshold_gb."""
    if not NAS_ROOT.exists():
        return False, 0.0, 0.0
    try:
        usage = shutil.disk_usage(str(NAS_ROOT))
        free_gb  = usage.free  / 1e9
        total_gb = usage.total / 1e9
        return free_gb >= threshold_gb, free_gb, total_gb
    except Exception:
        return False, 0.0, 0.0


def check_ollama_model(model: str = "bge-m3", timeout: float = 2.0) -> Tuple[bool, str]:
    """Comprueba si un modelo concreto está disponible en Ollama."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=timeout)
        if r.ok:
            names = [m.get("name", "") for m in r.json().get("models", [])]
            found = any(model in n for n in names)
            return found, ("Disponible" if found else "No encontrado en Ollama")
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Conexión rechazada (¿VPN UCA activa?)"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


def check_nas_writable() -> Tuple[bool, str]:
    """Comprueba permisos de escritura en categorias/."""
    if not CATEGORIAS_DIR.exists():
        return False, f"No existe {CATEGORIAS_DIR}"
    ok = os.access(str(CATEGORIAS_DIR), os.W_OK)
    return ok, ("Escritura OK" if ok else "Sin permisos de escritura")


def check_anthropic_api(timeout: float = 5.0) -> Tuple[bool, str]:
    """Verifica la API key de Anthropic con una llamada real a /v1/models."""
    if not ANTHROPIC_API_KEY:
        return False, "ANTHROPIC_API_KEY no configurada en config/.env"
    if not ANTHROPIC_API_KEY.startswith("sk-ant-"):
        return False, "Formato inesperado"
    try:
        r = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            return True, "OK"
        if r.status_code == 401:
            return False, "Key inválida o revocada (401)"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


def check_openai_api(timeout: float = 5.0) -> Tuple[bool, str]:
    """Verifica la API key de OpenAI con una llamada real a /v1/models."""
    if not OPENAI_API_KEY:
        return False, "OPENAI_API_KEY no configurada en config/.env"
    if not OPENAI_API_KEY.startswith("sk-"):
        return False, "Formato inesperado"
    try:
        r = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=timeout,
        )
        if r.status_code == 200:
            return True, "OK"
        if r.status_code == 401:
            return False, "Key inválida o revocada (401)"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


def check_openrouter_api(timeout: float = 5.0) -> Tuple[bool, str]:
    """Verifica la API key de OpenRouter con una llamada a /credits."""
    if not OPENROUTER_API_KEY:
        return False, "OPENROUTER_API_KEY no configurada en config/.env"
    if not OPENROUTER_API_KEY.startswith("sk-or-"):
        return False, "Formato inesperado (se espera sk-or-...)"
    try:
        r = requests.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=timeout,
        )
        if r.status_code == 200:
            return True, "OK"
        if r.status_code == 401:
            return False, "Key inválida o revocada (401)"
        # endpoint distinto/cambio API: no bloquear si el formato es válido
        return True, f"No verificado (HTTP {r.status_code}), formato válido"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


# ---------------------------------------------------------------------------
# Stats por categoría
# ---------------------------------------------------------------------------

def list_existing_categories() -> List[str]:
    if not CATEGORIAS_DIR.exists():
        return []
    return sorted(d.name for d in CATEGORIAS_DIR.iterdir() if d.is_dir())


def get_category_stats(category: str) -> Dict[str, Any]:
    cat_dir = CATEGORIAS_DIR / category
    if not cat_dir.exists():
        return {
            "exists": False,
            "pdfs": 0, "tei": 0, "md_clean": 0, "summaries": 0,
            "chunks": 0, "metadata": 0, "embeddings": False,
            "packages": 0, "pending": 0,
        }

    def count(subdir: str, pattern: str) -> int:
        d = cat_dir / subdir
        if not d.exists():
            return 0
        return sum(1 for _ in d.glob(pattern))

    n_pdfs = count("pdfs",     "*.pdf")
    n_md   = count("md_clean", "*.clean.md")
    pending = max(0, n_pdfs - n_md)

    embeddings_dir = cat_dir / "embeddings"
    has_embeddings = embeddings_dir.exists() and any(
        (sub / "index.faiss").exists()
        for sub in embeddings_dir.iterdir()
        if sub.is_dir()
    )

    # ── DOI faltantes desde papers_metadata.jsonl ──
    n_sin_doi = 0
    n_total_meta = 0
    jsonl_path = cat_dir / "metadata" / "papers_metadata.jsonl"
    if jsonl_path.exists():
        try:
            with jsonl_path.open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        d = json.loads(s)
                    except Exception:
                        continue
                    n_total_meta += 1
                    doi = d.get("doi", "")
                    if not doi or not str(doi).strip():
                        n_sin_doi += 1
        except Exception:
            pass

    return {
        "exists":     True,
        "pdfs":       n_pdfs,
        "tei":        count("tei",      "*.tei.xml"),
        "md_clean":   n_md,
        "summaries":  count("summaries", "*.summary.md"),
        "chunks":     count("chunks",   "*.jsonl"),
        "metadata":   n_total_meta,
        "embeddings": has_embeddings,
        "packages":   count("notebooklm_packages", "*"),
        "pending":    pending,
        "n_sin_doi":  n_sin_doi,
        "n_total_meta": n_total_meta,
    }


def category_summary_row(category: str) -> Dict[str, Any]:
    """Fila-resumen de procesado de una categoría.

    Mismas columnas que la tabla de la portada (app.py) y la pestaña
    «Pendientes» (1_Ingestar.py): PDFs, MD limpio, Resúmenes, Chunks, Metadata,
    FAISS (✓/✗), Paquetes y las Brechas detectadas comparando md_clean con el
    resto de artefactos.
    """
    stats = get_category_stats(category)
    expected = int(stats.get("md_clean") or stats.get("pdfs") or 0)
    missing_md = max(0, int(stats.get("pdfs", 0)) - int(stats.get("md_clean", 0)))
    missing_summaries = max(0, expected - int(stats.get("summaries", 0)))
    missing_chunks = max(0, expected - int(stats.get("chunks", 0)))
    missing_metadata = max(0, expected - int(stats.get("metadata", 0)))

    gaps = []
    if missing_md:
        gaps.append(f"MD limpio: {missing_md}")
    if missing_summaries:
        gaps.append(f"Resúmenes: {missing_summaries}")
    if missing_chunks:
        gaps.append(f"Chunks: {missing_chunks}")
    if missing_metadata:
        gaps.append(f"Metadata: {missing_metadata}")

    return {
        "Categoría": category,
        "PDFs": int(stats.get("pdfs", 0)),
        "MD limpio": int(stats.get("md_clean", 0)),
        "Resúmenes": int(stats.get("summaries", 0)),
        "Chunks": int(stats.get("chunks", 0)),
        "Metadata": int(stats.get("metadata", 0)),
        "FAISS": "✓" if stats.get("embeddings") else "✗",
        "Paquetes": int(stats.get("packages", 0)),
        "Brechas": ", ".join(gaps) if gaps else "Completo",
        "Sin DOI": int(stats.get("n_sin_doi", 0)),
    }


def get_categories_summary(
    categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Resumen por categoría (una fila por categoría con PDFs).

    Reutiliza `get_category_stats` para producir las mismas columnas que la
    portada / pestaña Pendientes. Si `categories` es None, recorre todas las
    categorías existentes en el NAS.
    """
    if categories is None:
        categories = list_existing_categories()
    rows: List[Dict[str, Any]] = []
    for cat in categories:
        stats = get_category_stats(cat)
        if stats.get("pdfs", 0) <= 0:
            continue
        rows.append(category_summary_row(cat))
    return rows


def get_category_quality(category: str) -> dict:
    """
    Lee papers_metadata.jsonl y agrega métricas de calidad.
    Devuelve dict con:
      n_total, n_with_score, avg_score,
      pct_doi, pct_title, pct_year, pct_abstract, pct_refs,
      top_warnings: list[(warning, count)] (top 5)
    """
    from collections import Counter
    jsonl = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
    if not jsonl.exists():
        return {}

    scores, warnings_all = [], []
    has_doi = has_title = has_year = has_abstract = has_refs = n = 0
    try:
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except Exception:
                    continue
                n += 1
                if m.get("doi"):       has_doi      += 1
                if m.get("title"):     has_title    += 1
                if m.get("year"):      has_year     += 1
                if m.get("abstract"):  has_abstract += 1
                if (m.get("n_references") or 0) >= 5: has_refs += 1
                qs = m.get("quality_score")
                if qs is not None:
                    scores.append(float(qs))
                warnings_all.extend(m.get("warnings") or [])
    except Exception:
        return {}

    if n == 0:
        return {}

    return {
        "n_total":      n,
        "n_with_score": len(scores),
        "avg_score":    round(sum(scores) / len(scores), 2) if scores else None,
        "pct_doi":      round(100 * has_doi      / n),
        "pct_title":    round(100 * has_title    / n),
        "pct_year":     round(100 * has_year     / n),
        "pct_abstract": round(100 * has_abstract / n),
        "pct_refs":     round(100 * has_refs     / n),
        "top_warnings": Counter(warnings_all).most_common(5),
    }


def list_embedding_phases(category: str) -> List[str]:
    """Devuelve fases (subcarpetas de embeddings/) con índice FAISS construido.

    Soporta múltiples modelos: subcarpetas pueden ser '<phase>' (default nomic) o
    '<phase>__<modelo>' (sufijo de modelo para alternativas como mxbai).
    """
    emb_dir = CATEGORIAS_DIR / category / "embeddings"
    if not emb_dir.exists():
        return []
    return sorted(
        sub.name for sub in emb_dir.iterdir()
        if sub.is_dir() and (sub / "index.faiss").exists()
    )


def embedding_phase_model(category: str, phase: str) -> str:
    """Devuelve el modelo de embedding declarado en config.json del índice."""
    cfg_path = CATEGORIAS_DIR / category / "embeddings" / phase / "config.json"
    if not cfg_path.exists():
        return "?"
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8")).get("model", "?")
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data, f,
            allow_unicode=True, sort_keys=False,
            default_flow_style=False, indent=2,
        )


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def human_status_icon(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def short_path(p: Path, max_len: int = 60) -> str:
    s = str(p)
    return s if len(s) <= max_len else "…" + s[-max_len:]


def fmt_cost(usd: float) -> str:
    """Formato amigable: $0.0012 si es muy bajo, $0.05 si es razonable."""
    if usd == 0:
        return "gratis"
    if usd < 0.001:
        return f"${usd*1000:.2f}m"   # milicentavos
    if usd < 1:
        return f"${usd:.4f}"
    return f"${usd:.2f}"


def get_corpus_manifest(category: str) -> Dict[str, Any]:
    """Lee el corpus_manifest.json de la categoría; devuelve {} si no existe o falla."""
    try:
        from utils.corpus_manifest import read_manifest
        return read_manifest(category, CATEGORIAS_DIR)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Categorías activas
# ---------------------------------------------------------------------------

ACTIVE_CATEGORIES_FILE = CONFIG_DIR / "active_categories.yml"


def load_active_categories() -> List[str]:
    """Devuelve la lista de categorías activas; CANONICAL_CATEGORIES como fallback."""
    try:
        data = load_yaml(ACTIVE_CATEGORIES_FILE)
        active = data.get("active")
        if isinstance(active, list) and active:
            return active
    except Exception:
        pass
    return list(CANONICAL_CATEGORIES)


def save_active_categories(active: List[str]) -> None:
    """Escribe active_categories.yml con backup previo."""
    save_yaml(ACTIVE_CATEGORIES_FILE, {"active": active})


def is_category_active(category: str) -> bool:
    """True si la categoría está en la lista de activas."""
    return category in load_active_categories()

def read_last_backup() -> "dict | None":
    """Lee /Volumes/research/metadatos/last_backup.json; None si no existe o falla."""
    path = NAS_ROOT / "metadatos" / "last_backup.json"
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_public_app() -> bool:
    """True cuando la instancia corre como app pública (puerto 8502).

    Se activa con la variable de entorno PUBLIC_APP=true, inyectada
    desde el plist de launchd de la instancia pública.
    """
    return os.getenv("PUBLIC_APP", "").lower() in ("1", "true", "yes")


def check_password(env_var: str = "PRIVATE_APP_PASSWORD") -> bool:
    """Muestra un formulario de contraseña y devuelve True si el usuario
    está autenticado.

    - La contraseña se lee de la variable de entorno `env_var` (leída
      desde config/.env al arrancar la app).
    - El estado de autenticación se guarda en st.session_state bajo la
      clave f"auth_{env_var}" para que persista durante la sesión.
    - Si la variable de entorno no está configurada, deja pasar (facilita
      el desarrollo local sin contraseña).

    Uso en cada página:
        from app_utils import check_password, is_public_app
        env = "PUBLIC_APP_PASSWORD" if is_public_app() else "PRIVATE_APP_PASSWORD"
        if not check_password(env):
            st.stop()
    """
    import streamlit as st  # import local para no forzar dependencia en módulos CLI

    session_key = f"auth_{env_var}"
    if st.session_state.get(session_key):
        return True

    correct = os.getenv(env_var, "")
    if not correct:
        # Sin contraseña configurada → acceso libre (útil en dev)
        st.session_state[session_key] = True
        return True

    # Formulario de login
    st.markdown("## 🔐 Acceso restringido")
    with st.form("login_form", clear_on_submit=True):
        pwd = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        if pwd == correct:
            st.session_state[session_key] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

    return False


def get_paper_status(category: str) -> list[dict]:
    """
    Devuelve una lista de dicts, uno por paper_id detectado en pdfs/,
    con el estado de cada artefacto esperado.

    Campos por fila:
        paper_id, pdf, tei, md_clean, chunks, summary, metadata, embedded

    Solo incluye papers con al menos un artefacto ausente (incompletos).
    """
    import json as _json

    cat_dir = CATEGORIAS_DIR / category
    pdfs_dir      = cat_dir / "pdfs"
    tei_dir       = cat_dir / "tei"
    md_dir        = cat_dir / "md_clean"
    chunks_dir    = cat_dir / "chunks"
    summaries_dir = cat_dir / "summaries"
    meta_dir      = cat_dir / "metadata"
    embed_dir     = cat_dir / "embeddings" / "all"

    # paper_ids ya indexados en FAISS
    indexed_papers_path = embed_dir / "indexed_papers.json"
    indexed_ids: set[str] = set()
    if indexed_papers_path.exists():
        try:
            data = _json.loads(indexed_papers_path.read_text(encoding="utf-8"))
            indexed_ids = set(data.get("paper_ids", []))
        except Exception:
            pass

    # paper_ids con metadata
    meta_ids: set[str] = set()
    meta_path = meta_dir / "papers_metadata.jsonl"
    if meta_path.exists():
        try:
            with meta_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = _json.loads(line)
                    pid = rec.get("paper_id") or rec.get("stable_id")
                    if pid:
                        meta_ids.add(pid)
        except Exception:
            pass

    if not pdfs_dir.exists():
        return []

    rows = []
    for pdf in sorted(pdfs_dir.glob("*.pdf")):
        try:
            from utils.pdf_utils import normalize_stem
            paper_id = normalize_stem(pdf.stem)
        except Exception:
            paper_id = pdf.stem

        status = {
            "paper_id": paper_id,
            "pdf":      True,
            "tei":      (tei_dir      / f"{paper_id}.tei.xml").exists(),
            "md_clean": (md_dir       / f"{paper_id}.clean.md").exists(),
            "chunks":   (chunks_dir   / f"{paper_id}.jsonl").exists(),
            "summary":  (summaries_dir/ f"{paper_id}.summary.md").exists(),
            "metadata": paper_id in meta_ids,
            "embedded": paper_id in indexed_ids,
        }

        if not all(status[k] for k in ("tei", "md_clean", "chunks",
                                        "summary", "metadata", "embedded")):
            rows.append(status)

    return rows
