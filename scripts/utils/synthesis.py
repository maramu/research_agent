# -*- coding: utf-8 -*-
"""
Plantilla de síntesis del RAG — módulo puro (sin streamlit), item 57.

Antes la plantilla existía dos veces: `rag_core.build_default_system` (web) y una copia
literal en `run_rag_batch.synthesize` (batería); la copia ya se desalineó una vez
(item 53). Ahora ambas llaman a `build_system_prompt`.
"""
from __future__ import annotations

from utils.citations import CITE_PROMPT_RULES


def build_system_prompt(context: str) -> str:
    """Prompt de sistema por defecto del RAG, con los fragmentos numerados ya formateados."""
    return f"""Eres un asistente científico. Responde a la pregunta basándote ÚNICAMENTE en los fragmentos numerados que se proporcionan a continuación.

Reglas:
- Si los fragmentos no contienen información suficiente para responder, dilo claramente.
- No inventes datos. No uses conocimiento externo a los fragmentos.
- Responde en el mismo idioma que la pregunta.
{CITE_PROMPT_RULES}

Fragmentos:
{context}

Recuerda: cita con [N] junto a cada dato; sin sección de Referencias."""
