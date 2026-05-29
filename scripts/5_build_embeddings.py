#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5_build_embeddings.py — Paso 5 del pipeline research_agent

Genera un índice FAISS de embeddings vectoriales a partir de los chunks JSONL
del proyecto, usando Ollama (modelo bge-m3 por defecto).

Posición en el pipeline:
    categorias/<project>/chunks/ → 5_build_embeddings.py → embeddings/

Estructura del índice de salida:
    embeddings/<phase>[__<modelo>]/
        index.faiss      ← índice FAISS (IndexFlatL2, dim=1024 para bge-m3)
        metadata.jsonl   ← metadatos de cada chunk (paper_id, section, type, text…)
        config.json      ← project, phase, model, chunks, dimension

Nomenclatura de la carpeta de salida:
    - Modelo por defecto (bge-m3): embeddings/<phase>/
    - Modelo alternativo:          embeddings/<phase>__<modelo_sanitizado>/
    Esto permite coexistir varios índices con distintos modelos.

Skip logic:
    Si index.faiss ya existe y --force no está activo, el script sale sin hacer nada.

Ficheros leídos:
    /Volumes/research/categorias/<project>/chunks/**/*.jsonl
    config/.env

Ficheros escritos:
    /Volumes/research/categorias/<project>/embeddings/<phase>[__<modelo>]/
        index.faiss
        metadata.jsonl
        config.json

Parámetros CLI:
    --project PROJECT     Nombre del proyecto/categoría (obligatorio)
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)
    --phase PHASE         Etiqueta de fase a indexar, o 'all' (defecto: all)
    --model MODEL         Modelo Ollama de embedding (defecto: bge-m3)
    --batch-size N        Chunks por lote de progreso (defecto: 64)
    --force               Sobrescribe el índice aunque ya exista

Variables de entorno (config/.env):
    OLLAMA_HOST           URL del servidor Ollama (defecto: http://pciq22.uca.es:11434)

Dependencias:
    faiss-cpu, numpy, ollama, python-dotenv

Notas:
    - bge-m3 produce embeddings de 1024 dimensiones con contexto de 8192 tokens.
    - El embedding se hace chunk a chunk (Ollama no acepta batch); el parámetro
      --batch-size solo controla la frecuencia de los mensajes de progreso.
    - mxbai-embed-large NO es compatible (contexto 512 vs ~1500 chars por chunk).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import faiss
import ollama
from dotenv import load_dotenv

# ── Cargar config/.env ────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from utils.constants import OLLAMA_MODEL_EMBED  # noqa: E402

DEFAULT_BASE       = "/Volumes/research/categorias"
DEFAULT_MODEL      = OLLAMA_MODEL_EMBED
DEFAULT_BATCH_SIZE = 64


def phase_from_path(p: Path) -> str:
    parts = p.parts
    for i, part in enumerate(parts):
        if part == "chunks" and i + 1 < len(parts) - 1:
            return parts[i + 1]
    return "unknown"


def iter_chunks(chunks_dir: Path, phase_filter: str):
    """Itera todos los chunks .jsonl recursivamente, filtrando por fase."""
    for jsonl_path in sorted(chunks_dir.rglob("*.jsonl")):
        path_phase = phase_from_path(jsonl_path)
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                rec_phase = rec.get("phase", path_phase)
                if phase_filter != "all" and rec_phase != phase_filter:
                    continue
                if "phase" not in rec:
                    rec["phase"] = path_phase
                yield rec


def embed_texts(client: ollama.Client, texts: list, model: str) -> list:
    """Embedding de una lista de textos usando Ollama (uno a uno)."""
    return [
        np.array(client.embeddings(model=model, prompt=text)["embedding"], dtype="float32")
        for text in texts
    ]


def _model_suffix(model: str) -> str:
    """Sufijo para el directorio de salida según el modelo.
    Mantiene compatibilidad: el modelo por defecto no añade sufijo."""
    if model == DEFAULT_MODEL:
        return ""
    safe = model.replace(":", "_").replace("/", "_")
    return f"__{safe}"


def main():
    ap = argparse.ArgumentParser(description="Genera embeddings FAISS con Ollama nomic-embed-text")
    ap.add_argument("--project",    required=True, help="Nombre del proyecto (subcarpeta bajo --base)")
    ap.add_argument("--base",       default=DEFAULT_BASE, help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--phase",      default="all",
                    help="Etiqueta de fase a indexar (nombre de categoría, o 'all')")
    ap.add_argument("--model",      default=DEFAULT_MODEL, help=f"Modelo Ollama (defecto: {DEFAULT_MODEL})")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                    help="Chunks por progreso (el embedding es siempre uno a uno en Ollama)")
    ap.add_argument("--force",      action="store_true",
                    help="Sobrescribe el índice aunque ya exista")
    args = ap.parse_args()

    base        = Path(args.base)
    project_dir = base / args.project
    chunks_dir  = project_dir / "chunks"
    out_dir     = project_dir / "embeddings" / f"{args.phase}{_model_suffix(args.model)}"

    if not chunks_dir.exists():
        raise SystemExit(f"No existe chunks dir: {chunks_dir}")

    if (out_dir / "index.faiss").exists() and not args.force:
        print(f"Índice existente, salto: {out_dir / 'index.faiss'}")
        print("Usa --force para re-indexar y sobrescribirlo.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    ollama_host = os.getenv("OLLAMA_HOST", "http://pciq22.uca.es:11434")
    client      = ollama.Client(host=ollama_host)
    print(f"Project    : {args.project}")
    print(f"Phase      : {args.phase}")
    print(f"Model      : {args.model}")
    print(f"Ollama     : {ollama_host}")
    print(f"Chunks dir : {chunks_dir}")
    print(f"Output dir : {out_dir}")
    print("")

    all_vectors: list = []
    all_meta:    list = []
    buf_texts:   list = []
    buf_meta:    list = []

    for rec in iter_chunks(chunks_dir, args.phase):
        buf_texts.append(rec["text"])
        buf_meta.append(rec)

        if len(buf_texts) >= args.batch_size:
            print(f"  Embeddiendo {len(buf_texts)} chunks  (total procesados: {len(all_meta) + len(buf_texts)})…")
            all_vectors.extend(embed_texts(client, buf_texts, args.model))
            all_meta.extend(buf_meta)
            buf_texts, buf_meta = [], []

    if buf_texts:
        print(f"  Embeddiendo último lote de {len(buf_texts)} chunks…")
        all_vectors.extend(embed_texts(client, buf_texts, args.model))
        all_meta.extend(buf_meta)

    if not all_vectors:
        raise SystemExit("No se encontraron chunks para embeddear.")

    X   = np.vstack(all_vectors)
    dim = X.shape[1]

    index = faiss.IndexFlatL2(dim)
    index.add(X)

    faiss.write_index(index, str(out_dir / "index.faiss"))

    with (out_dir / "metadata.jsonl").open("w", encoding="utf-8") as f:
        for m in all_meta:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    config = {
        "project":   args.project,
        "phase":     args.phase,
        "model":     args.model,
        "chunks":    len(all_meta),
        "dimension": dim,
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"\nEmbeddings creados : {len(all_meta)} chunks")
    print(f"Dimension          : {dim}")
    print(f"FAISS index        : {out_dir / 'index.faiss'}")
    print(f"Metadata           : {out_dir / 'metadata.jsonl'}")
    print(f"Config             : {out_dir / 'config.json'}")


if __name__ == "__main__":
    main()
