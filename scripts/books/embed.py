#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
books/embed.py — Índice FAISS de libros de docencia (paralelo a 5_build_embeddings.py).

Reutiliza el MISMO núcleo de embedding que los artículos (utils/embeddings.py:
bge-m3 vía Ollama, con truncado-y-reintento por contexto). NO duplica esa lógica.
La escritura del índice sí es propia porque los libros necesitan una política
incremental que 5_build_embeddings.py no ofrece (borrar del índice los chunks de
un libro que cambió).

Salida (espejo del formato de artículos, alineada por orden):
    /Volumes/research/libros_docencia/embeddings/all/
        index.faiss          IndexFlatL2 sobre vectores L2-normalizados (item 55a)
        metadata.jsonl        1 línea por vector, MISMO orden que el índice
        config.json           project, phase, model, chunks, dimension, normalized
        indexed_books.json    {model, dimension, books:{book_id: chunks_sha256}}

Normalización L2 (item 55a): OBLIGATORIA y solidaria con los índices de papers —
14_Preparar_clase.py fusiona este índice con los de categorías POR DISTANCIA, así
que el rollout es atómico: si se normalizan los papers hay que re-embeber libros
en la misma tanda. La caché _vectors/*.npy sigue guardando vectores crudos.

Incremental por HASH de libro (indexed_books.json):
    - Se hashea el fichero chunks/<book_id>.jsonl (captura re-chunking, no solo
      cambios del PDF). Los vectores de cada libro se cachean en
      embeddings/all/_vectors/<book_id>.npy.
    - Libro sin cambios (hash igual + caché válida) → se REUTILIZAN sus vectores
      (no se vuelve a llamar a Ollama).
    - Libro nuevo o cambiado → se (re)embebe; sus vectores viejos desaparecen del
      índice porque este se reensambla por completo desde los chunks actuales.
    - Libro eliminado de chunks/ → queda fuera del índice (y se limpia su caché).
    --force reindexa todo desde cero (ignora caché e indexed_books.json).

CRÍTICO (year/citas): NO se recalcula el year. Cada record de metadata.jsonl se
escribe TAL CUAL viene del chunk (year denormalizado en process.py, doc_type,
section_canonical, heading_path, page_start/page_end incluidos).

Parámetros CLI:
    --collection NAME   Colección/proyecto (defecto: libros_docencia)
    --base DIR          Raíz NAS (defecto: /Volumes/research)
    --phase PHASE       Subcarpeta del índice (defecto: all)
    --model MODEL       Modelo Ollama (defecto: bge-m3)
    --force             Reindexa desde cero
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import faiss

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from dotenv import load_dotenv  # noqa: E402

_ENV_FILE = _SCRIPTS_DIR.parent / "config" / ".env"
load_dotenv(_ENV_FILE if _ENV_FILE.exists() else None)

from utils.constants import OLLAMA_MODEL_EMBED  # noqa: E402
from utils.embeddings import (  # noqa: E402
    embed_texts, make_client, l2_normalize, verify_index_integrity,
)

DEFAULT_BASE = "/Volumes/research"
DEFAULT_COLLECTION = "libros_docencia"
DEFAULT_PHASE = "all"
DEFAULT_MODEL = OLLAMA_MODEL_EMBED
INDEXED_BOOKS_FILE = "indexed_books.json"


def _emit(on_output: Optional[Callable[[str], None]], msg: str) -> None:
    (on_output or print)(msg)


def _chunks_hash(path: Path) -> str:
    """sha256 del fichero de chunks (cualquier cambio → re-embed del libro)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _read_jsonl(path: Path) -> List[Dict]:
    out: List[Dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _load_indexed_books(out_dir: Path) -> dict:
    p = out_dir / INDEXED_BOOKS_FILE
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_indexed_books(out_dir: Path, model: str, dim: int, books: Dict[str, str]) -> None:
    data = {"model": model, "dimension": dim, "books": dict(sorted(books.items()))}
    (out_dir / INDEXED_BOOKS_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_book_embeddings(
    collection: str = DEFAULT_COLLECTION,
    base: str = DEFAULT_BASE,
    phase: str = DEFAULT_PHASE,
    model: Optional[str] = None,
    force: bool = False,
    on_output: Optional[Callable[[str], None]] = None,
) -> dict:
    """Genera/actualiza el índice FAISS de la colección de libros.

    Reutiliza el núcleo de embedding de artículos preservando el year (y todos
    los campos) de cada chunk. Devuelve un resumen con nº de vectores, dimensión
    y desglose de libros (embebidos vs reutilizados).
    """
    model = model or DEFAULT_MODEL
    base_p = Path(base)
    collection_dir = base_p / collection
    chunks_dir = collection_dir / "chunks"
    out_dir = collection_dir / "embeddings" / phase
    cache_dir = out_dir / "_vectors"
    if not chunks_dir.exists():
        raise SystemExit(f"No existe chunks dir: {chunks_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    chunk_files = sorted(chunks_dir.glob("*.jsonl"))
    if not chunk_files:
        raise SystemExit(f"No hay chunks .jsonl en {chunks_dir}")

    prev = _load_indexed_books(out_dir)
    prev_books: Dict[str, str] = prev.get("books", {}) if isinstance(prev, dict) else {}
    if not force and prev.get("model") and prev.get("model") != model:
        _emit(on_output, f"⚠️ El índice usa modelo '{prev.get('model')}' ≠ '{model}'. "
                         "Reindexando desde cero.")
        force = True

    client = make_client()

    _emit(on_output, f"Collection : {collection}")
    _emit(on_output, f"Chunks     : {len(chunk_files)} libros")
    _emit(on_output, f"Model      : {model}")
    _emit(on_output, f"Output     : {out_dir}")
    _emit(on_output, f"Modo       : {'completo (--force)' if force else 'incremental'}\n")

    all_records: List[Dict] = []
    all_vectors: List[np.ndarray] = []
    new_books: Dict[str, str] = {}
    n_embedded = n_reused = 0

    for cf in chunk_files:
        book_id = cf.stem
        records = _read_jsonl(cf)
        if not records:
            continue
        h = _chunks_hash(cf)
        cache_npy = cache_dir / f"{book_id}.npy"

        vectors = None
        if (not force and prev_books.get(book_id) == h and cache_npy.exists()):
            try:
                cached = np.load(cache_npy)
                if cached.shape[0] == len(records):
                    vectors = cached.astype("float32")
            except Exception:
                vectors = None

        if vectors is None:
            _emit(on_output, f"  · embebiendo {book_id[:56]} ({len(records)} chunks)…")
            vecs = embed_texts(client, [r["text"] for r in records], model)
            vectors = np.vstack(vecs).astype("float32")
            np.save(cache_npy, vectors)
            n_embedded += 1
        else:
            _emit(on_output, f"  · reutilizando {book_id[:54]} ({len(records)} chunks, sin cambios)")
            n_reused += 1

        all_records.extend(records)   # metadata TAL CUAL (year preservado)
        all_vectors.append(vectors)
        new_books[book_id] = h

    # Limpieza de caché de libros eliminados de chunks/.
    current_ids = set(new_books)
    for npy in cache_dir.glob("*.npy"):
        if npy.stem not in current_ids:
            npy.unlink()

    if not all_vectors:
        raise SystemExit("No se encontraron chunks para embeddear.")

    # Item 55a: normalizar L2 antes de indexar, igual que los artículos. La
    # caché _vectors/*.npy guarda los vectores CRUDOS (así sigue siendo válida
    # entre versiones); la normalización se aplica siempre aquí, al ensamblar.
    # Obligatorio para libros: 14_Preparar_clase.py fusiona POR DISTANCIA este
    # índice con los de papers, así que si uno solo no está normalizado el cupo
    # de libro deja de competir y la fusión da basura en silencio.
    X = l2_normalize(np.vstack(all_vectors).astype("float32"))
    dim = int(X.shape[1])

    index = faiss.IndexFlatL2(dim)
    index.add(X)
    faiss.write_index(index, str(out_dir / "index.faiss"))

    with (out_dir / "metadata.jsonl").open("w", encoding="utf-8") as f:
        for m in all_records:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    (out_dir / "config.json").write_text(json.dumps({
        "project": collection, "phase": phase, "model": model,
        "chunks": index.ntotal, "dimension": dim,
        "normalized": True,
    }, indent=2), encoding="utf-8")

    # Item 55b: invariante de integridad (ntotal == metadata, ‖v‖ ≈ 1, flag).
    verify_index_integrity(out_dir, index)
    _save_indexed_books(out_dir, model, dim, new_books)

    summary = {
        "vectors": int(index.ntotal), "dimension": dim,
        "books_total": len(new_books), "books_embedded": n_embedded,
        "books_reused": n_reused, "index_path": str(out_dir / "index.faiss"),
    }
    _emit(on_output, f"\nVectores   : {summary['vectors']}  (dim {dim})")
    _emit(on_output, f"Libros     : {summary['books_total']} "
                     f"({n_embedded} embebidos, {n_reused} reutilizados)")
    _emit(on_output, f"Índice     : {summary['index_path']}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Índice FAISS de libros de docencia (bge-m3)")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--phase", default=DEFAULT_PHASE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    build_book_embeddings(
        collection=args.collection, base=args.base, phase=args.phase,
        model=args.model, force=args.force,
    )


if __name__ == "__main__":
    main()
