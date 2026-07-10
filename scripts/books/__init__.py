# -*- coding: utf-8 -*-
"""
Pipeline PARALELO para libros de docencia (item 31).

Reutiliza bge-m3 + FAISS + Streamlit del pipeline de artículos, pero SIN GROBID:
solo PDF de texto extraíble. Estructura NAS espejo bajo
/Volumes/research/libros_docencia/ (pdfs, md_clean, chunks, embeddings,
metadata, logs).

Módulos:
    process.py  PDF de texto → md_clean → chunks JSONL (+ libros_metadata.jsonl
                y metadata/papers_metadata.jsonl derivado para citas/año).
    embed.py    Genera el índice FAISS reutilizando la lógica de embeddings de
                artículos parametrizada a libros_docencia (NO duplica
                5_build_embeddings.py; preserva el year denormalizado del chunk).
    query.py    Wrapper fino sobre 8_query_rag.py con --project libros_docencia.

Esqueleto: firmas + docstrings. Sin lógica todavía.
"""
