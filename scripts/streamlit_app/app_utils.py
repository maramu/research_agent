# -*- coding: utf-8 -*-
"""
utils.py — Helpers compartidos para la app Streamlit de research_agent.

Centraliza:
  - Inserción de scripts/ en sys.path para importar pipeline.py
  - Health checks (NAS, Ollama, GROBID)
  - Conteos por categoría (PDFs, MDs, summaries, embeddings…)
  - Carga/guardado de YAML
  - Constantes de paths
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# sys.path — para que las pages puedan hacer `from pipeline import ...`
# ---------------------------------------------------------------------------

STREAMLIT_APP_DIR = Path(__file__).resolve().parent      # .../scripts/streamlit_app/
SCRIPTS_DIR       = STREAMLIT_APP_DIR.parent              # .../scripts/
PROJECT_ROOT      = SCRIPTS_DIR.parent                    # .../research_agent/
CONFIG_DIR        = PROJECT_ROOT / "config"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Cargar config/.env (mismo patrón que el resto de scripts)
_ENV_FILE = CONFIG_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

# Reexports de pipeline (lazy, para no romper si scripts/ aún no tiene pipeline.py)
try:
    from pipeline import (  # noqa: F401
        run_scopus,
        run_inbox,
        run_adhoc,
        process_category,
        detect_affected_categories,
        ensure_project_dirs,
        check_nas as _check_nas_pipeline,
        NAS_ROOT,
        CATEGORIAS_DIR,
        INBOX_DIR,
        INBOX_CSV_DIR,
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

METADATOS_DIR = NAS_ROOT / "metadatos"
DOI_MANUAL_XLSX = METADATOS_DIR / "doi_manual.xlsx"

# Endpoints (mismos defaults que el resto del proyecto)
OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "http://pciq22.uca.es:11434")
GROBID_URL   = os.getenv("GROBID_URL",   "http://pciq22.uca.es:8070")

# Catálogo de categorías "oficiales" (las 8 del proyecto)
CANONICAL_CATEGORIES = [
    "biological_gas_odor_treatment",
    "anoxic_biogas_biodesulfurization",
    "bioplastics_microplastics",
    "biogas_upgrading_biomethanation",
    "microalgae",
    "single_cell_protein",
    "advanced_oxidation_processes",
    "bioleaching_critical_materials",
]

# Modelos Ollama disponibles (según ESTADO.md)
OLLAMA_MODELS_LLM = ["qwen3:14b", "qwen3:8b", "gemma3:4b"]
OLLAMA_MODEL_EMBED = "nomic-embed-text"


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def check_nas() -> Tuple[bool, str]:
    """¿NAS montado? Devuelve (ok, mensaje)."""
    if NAS_ROOT.exists() and NAS_ROOT.is_dir():
        return True, f"Montado en {NAS_ROOT}"
    return False, f"No existe {NAS_ROOT}. Monta con: open smb://synology/research"


def check_ollama(timeout: float = 2.0) -> Tuple[bool, str]:
    """¿Ollama alcanzable? Devuelve (ok, mensaje)."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=timeout)
        if r.ok:
            n_models = len(r.json().get("models", []))
            return True, f"OK ({n_models} modelos disponibles)"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Conexión rechazada (¿VPN UCA activa?)"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


def check_grobid(timeout: float = 2.0) -> Tuple[bool, str]:
    """¿GROBID alcanzable? Devuelve (ok, mensaje)."""
    try:
        r = requests.get(f"{GROBID_URL}/api/isalive", timeout=timeout)
        if r.ok and r.text.strip().lower() == "true":
            return True, "OK (isalive=true)"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Conexión rechazada (¿VPN UCA activa?)"
    except requests.exceptions.Timeout:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, f"Error: {e}"


# ---------------------------------------------------------------------------
# Stats por categoría
# ---------------------------------------------------------------------------

def list_existing_categories() -> List[str]:
    """Lista categorías que existen físicamente en categorias/."""
    if not CATEGORIAS_DIR.exists():
        return []
    return sorted(d.name for d in CATEGORIAS_DIR.iterdir() if d.is_dir())


def get_category_stats(category: str) -> Dict[str, Any]:
    """Devuelve conteos de artefactos por etapa para una categoría.

    Cada conteo es 0 si la subcarpeta no existe.
    """
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

    # Pendientes: PDFs sin su correspondiente MD. Tolerante a normalización
    # de nombres entre PDF y .clean.md (los stems no siempre coinciden 1:1
    # porque 3_process_corpus.py puede normalizar espacios a "_").
    pending = max(0, n_pdfs - n_md)

    # Metadata: 4_extract_metadata.py guarda los ficheros per-paper en
    # metadata/per_paper/<paper_id>.metadata.json
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
    """Devuelve fases (subcarpetas de embeddings/) con índice FAISS construido."""
    emb_dir = CATEGORIAS_DIR / category / "embeddings"
    if not emb_dir.exists():
        return []
    return sorted(
        sub.name for sub in emb_dir.iterdir()
        if sub.is_dir() and (sub / "index.faiss").exists()
    )


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> Dict[str, Any]:
    """Carga YAML como dict. Devuelve {} si no existe."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def save_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Guarda dict como YAML, con backup .bak previo si existe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data, f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            indent=2,
        )


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def human_status_icon(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def short_path(p: Path, max_len: int = 60) -> str:
    s = str(p)
    if len(s) <= max_len:
        return s
    return "…" + s[-max_len:]
