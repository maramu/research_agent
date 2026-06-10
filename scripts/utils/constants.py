# -*- coding: utf-8 -*-
"""
Constantes compartidas entre scripts/ y streamlit_app/.
"""

import re

# Modelo de embedding por defecto usado en build_embeddings y query_rag.
# Cambiar aquí afecta a todos los puntos de uso.
OLLAMA_MODEL_EMBED = "bge-m3"

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

# Secciones canónicas (debe coincidir con canonical_section() de
# 3_process_corpus.py, item 32, más "table"). Fuente de verdad única para
# el filtrado por sección en la query RAG (item 34).
CANONICAL_SECTIONS = [
    "abstract", "introduction", "methods", "results",
    "discussion", "conclusion", "table", "other",
]


def year_from_paper_id(pid: str):
    """Devuelve el primer año (1900–2039) hallado en el paper_id, o None."""
    m = re.search(r"(19\d{2}|20[0-3]\d)", pid or "")
    return int(m.group(1)) if m else None
