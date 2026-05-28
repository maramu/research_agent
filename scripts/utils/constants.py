# -*- coding: utf-8 -*-
"""
Constantes compartidas entre scripts/ y streamlit_app/.
"""

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
