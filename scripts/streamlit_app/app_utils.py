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

# ---------------------------------------------------------------------------
# Categorías canónicas
# ---------------------------------------------------------------------------

from utils.constants import OLLAMA_MODEL_EMBED, CANONICAL_CATEGORIES  # noqa: E402

# ---------------------------------------------------------------------------
# Modelos disponibles por provider
# ---------------------------------------------------------------------------

OLLAMA_MODELS_LLM     = ["qwen3:14b", "qwen3:8b", "gemma3:4b"]
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
    # Ollama — local, sin coste
    "qwen3:14b":         {"input": 0.0,   "output": 0.0},
    "qwen3:8b":          {"input": 0.0,   "output": 0.0},
    "gemma3:4b":         {"input": 0.0,   "output": 0.0},
}


def model_provider(model: str) -> str:
    """Devuelve el provider de un model id."""
    if model in ANTHROPIC_MODELS:
        return "anthropic"
    if model in OPENAI_MODELS:
        return "openai"
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
) -> None:
    """Apenda un registro al jsonl del mes actual.

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
        }
        with usage_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


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


def check_anthropic_api() -> Tuple[bool, str]:
    if not ANTHROPIC_API_KEY:
        return False, "ANTHROPIC_API_KEY no configurada en config/.env"
    if not ANTHROPIC_API_KEY.startswith("sk-ant-"):
        return False, "API key con formato inesperado"
    return True, "Configurada"


def check_openai_api() -> Tuple[bool, str]:
    if not OPENAI_API_KEY:
        return False, "OPENAI_API_KEY no configurada en config/.env"
    if not OPENAI_API_KEY.startswith("sk-"):
        return False, "API key con formato inesperado"
    return True, "Configurada"


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

    metadata_per_paper_dir = cat_dir / "metadata" / "per_paper"
    n_metadata = (
        sum(1 for _ in metadata_per_paper_dir.glob("*.metadata.json"))
        if metadata_per_paper_dir.exists()
        else 0
    )

    embeddings_dir = cat_dir / "embeddings"
    has_embeddings = embeddings_dir.exists() and any(
        (sub / "index.faiss").exists()
        for sub in embeddings_dir.iterdir()
        if sub.is_dir()
    )

    return {
        "exists":     True,
        "pdfs":       n_pdfs,
        "tei":        count("tei",      "*.tei.xml"),
        "md_clean":   n_md,
        "summaries":  count("summaries", "*.summary.md"),
        "chunks":     count("chunks",   "*.jsonl"),
        "metadata":   n_metadata,
        "embeddings": has_embeddings,
        "packages":   count("notebooklm_packages", "*"),
        "pending":    pending,
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
