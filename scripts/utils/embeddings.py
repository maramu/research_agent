# -*- coding: utf-8 -*-
"""
Helpers de embedding compartidos (Ollama, bge-m3).

Extraído de 5_build_embeddings.py para reutilizar el MISMO núcleo de embedding
desde el pipeline de libros (books/embed.py) sin duplicarlo ni alterar el
comportamiento de artículos. La escritura del índice FAISS / metadata.jsonl la
hace cada caller (artículos vs libros tienen políticas incrementales distintas).
"""

import os

import numpy as np

from utils.constants import MAX_EMBED_CHARS


def make_client(host: str | None = None):
    """Crea un cliente Ollama apuntando a OLLAMA_HOST (o al host indicado)."""
    import ollama
    host = host or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11435")
    return ollama.Client(host=host)


def embed_texts(client, texts: list, model: str) -> list:
    """Embeddea uno a uno. Si un chunk excede el contexto del modelo, lo trunca
    progresivamente (2/3 cada vez) y reintenta: la densidad en tokens del texto
    con fórmulas/subíndices puede superar el contexto aun con pocos caracteres.

    Devuelve una lista de np.ndarray float32 (uno por texto, en orden).
    """
    out = []
    for text in texts:
        t = text if len(text) <= MAX_EMBED_CHARS else text[:MAX_EMBED_CHARS]
        for _ in range(8):
            try:
                resp = client.embeddings(model=model, prompt=t)
                out.append(np.array(resp["embedding"], dtype="float32"))
                break
            except Exception as e:
                if "context length" in str(e).lower() and len(t) > 400:
                    t = t[: max(400, (len(t) * 2) // 3)]
                    print(f"  ⚠️ chunk excede contexto; truncado a {len(t)} chars y reintentando")
                else:
                    raise
        else:
            raise RuntimeError("No se pudo embeber un chunk ni tras truncarlo al mínimo")
    return out
