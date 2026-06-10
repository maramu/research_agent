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
        index.faiss          ← índice FAISS (IndexFlatL2, dim=1024 para bge-m3)
        metadata.jsonl       ← metadatos de cada chunk (paper_id, section, type, text…)
        config.json          ← project, phase, model, chunks, dimension
        indexed_papers.json  ← paper_ids ya indexados + modelo usado (para modo incremental)

Nomenclatura de la carpeta de salida:
    - Modelo por defecto (bge-m3): embeddings/<phase>/
    - Modelo alternativo:          embeddings/<phase>__<modelo_sanitizado>/
    Esto permite coexistir varios índices con distintos modelos.

Modos de ejecución:
    Sin --force (defecto — incremental):
        - Si no existe índice → crea desde cero (mismo comportamiento que antes).
        - Si existe índice y hay papers nuevos → carga el índice, embeddea solo los
          chunks de papers nuevos (no en indexed_papers.json) y los añade con index.add().
          Actualiza metadata.jsonl (append), config.json y indexed_papers.json.
        - Si existe índice y no hay papers nuevos → imprime "Índice actualizado, nada nuevo"
          y sale sin tocar nada.
    Con --force:
        Re-indexa todo desde cero (comportamiento original). Útil al cambiar modelo
        o tras limpiar duplicados.

Ficheros leídos:
    /Volumes/research/categorias/<project>/chunks/**/*.jsonl
    config/.env

Ficheros escritos:
    /Volumes/research/categorias/<project>/embeddings/<phase>[__<modelo>]/
        index.faiss
        metadata.jsonl
        config.json
        indexed_papers.json

Parámetros CLI:
    --project PROJECT     Nombre del proyecto/categoría (obligatorio)
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)
    --phase PHASE         Etiqueta de fase a indexar, o 'all' (defecto: all)
    --model MODEL         Modelo Ollama de embedding (defecto: bge-m3)
    --batch-size N        Chunks por lote de progreso (defecto: 64)
    --force               Re-indexa todo desde cero aunque ya exista el índice

Variables de entorno (config/.env):
    OLLAMA_HOST           URL del servidor Ollama (defecto: http://pciq22.uca.es:11434)

Dependencias:
    faiss-cpu, numpy, ollama, python-dotenv

Notas:
    - bge-m3 produce embeddings de 1024 dimensiones con contexto de 8192 tokens.
    - El embedding se hace chunk a chunk (Ollama no acepta batch); el parámetro
      --batch-size solo controla la frecuencia de los mensajes de progreso.
    - mxbai-embed-large NO es compatible (contexto 512 vs ~1500 chars por chunk).
    - El modo incremental detecta papers nuevos por paper_id. Si se regeneraron
      chunks de un paper ya indexado (p.ej. tras re-procesar con GROBID), usar
      --force para que queden incluidos correctamente.
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
from utils.constants import OLLAMA_MODEL_EMBED, year_from_paper_id  # noqa: E402

DEFAULT_BASE       = "/Volumes/research/categorias"
DEFAULT_MODEL      = OLLAMA_MODEL_EMBED
DEFAULT_BATCH_SIZE = 64
INDEXED_PAPERS_FILE = "indexed_papers.json"


def _load_indexed_papers(out_dir: Path) -> tuple[set, str]:
    """Devuelve (set de paper_ids ya indexados, modelo usado). Vacío si no existe el fichero."""
    p = out_dir / INDEXED_PAPERS_FILE
    if not p.exists():
        return set(), ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("paper_ids", [])), data.get("model", "")
    except Exception:
        return set(), ""


def _save_indexed_papers(out_dir: Path, paper_ids: set, model: str) -> None:
    data = {"paper_ids": sorted(paper_ids), "model": model}
    (out_dir / INDEXED_PAPERS_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")


_YEAR_KEYS = ("year", "año", "anio", "publication_year", "pub_year")


def _record_year(rec):
    for k in _YEAR_KEYS:
        v = rec.get(k)
        if v:
            try:
                return int(str(v)[:4])
            except (ValueError, TypeError):
                pass
    return None


def _load_pid2year(project_dir: Path) -> dict:
    """Mapea paper_id y stable_id → año desde papers_metadata.jsonl.
    Tolerante: si no existe o falla la lectura, devuelve {} (year vendrá del
    fallback por regex sobre paper_id)."""
    pid2year: dict = {}
    meta_path = project_dir / "metadata" / "papers_metadata.jsonl"
    if not meta_path.exists():
        return pid2year
    try:
        with meta_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                y = _record_year(rec)
                if y is None:
                    continue
                for key in ("paper_id", "stable_id"):
                    pid = rec.get(key)
                    if pid:
                        pid2year[pid] = y
    except Exception as e:
        print(f"Advertencia: no se pudo leer papers_metadata.jsonl ({e}). "
              "Year se derivará solo por regex sobre paper_id.")
    return pid2year


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
    ap = argparse.ArgumentParser(description="Genera embeddings FAISS con Ollama (modo incremental por defecto)")
    ap.add_argument("--project",    required=True, help="Nombre del proyecto (subcarpeta bajo --base)")
    ap.add_argument("--base",       default=DEFAULT_BASE, help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--phase",      default="all",
                    help="Etiqueta de fase a indexar (nombre de categoría, o 'all')")
    ap.add_argument("--model",      default=DEFAULT_MODEL, help=f"Modelo Ollama (defecto: {DEFAULT_MODEL})")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                    help="Chunks por progreso (el embedding es siempre uno a uno en Ollama)")
    ap.add_argument("--force",      action="store_true",
                    help="Re-indexa todo desde cero aunque ya exista el índice")
    args = ap.parse_args()

    base        = Path(args.base)
    project_dir = base / args.project
    chunks_dir  = project_dir / "chunks"
    out_dir     = project_dir / "embeddings" / f"{args.phase}{_model_suffix(args.model)}"
    index_path  = out_dir / "index.faiss"

    if not chunks_dir.exists():
        raise SystemExit(f"No existe chunks dir: {chunks_dir}")

    incremental = index_path.exists() and not args.force

    if incremental:
        indexed_ids, indexed_model = _load_indexed_papers(out_dir)
        if indexed_model and indexed_model != args.model:
            print(
                f"Advertencia: el índice existente usa el modelo '{indexed_model}', "
                f"pero se solicitó '{args.model}'.\n"
                "Usa --force para re-indexar desde cero con el nuevo modelo."
            )
            return
    else:
        indexed_ids = set()

    out_dir.mkdir(parents=True, exist_ok=True)

    ollama_host = os.getenv("OLLAMA_HOST", "http://pciq22.uca.es:11434")
    client      = ollama.Client(host=ollama_host)

    print(f"Project    : {args.project}")
    print(f"Phase      : {args.phase}")
    print(f"Model      : {args.model}")
    print(f"Ollama     : {ollama_host}")
    print(f"Chunks dir : {chunks_dir}")
    print(f"Output dir : {out_dir}")
    print(f"Modo       : {'incremental' if incremental else 'completo'}")
    if incremental:
        print(f"Papers ya indexados: {len(indexed_ids)}")
    print("")

    pid2year = _load_pid2year(project_dir)

    all_vectors: list = []
    all_meta:    list = []
    buf_texts:   list = []
    buf_meta:    list = []

    for rec in iter_chunks(chunks_dir, args.phase):
        if incremental and rec.get("paper_id", "") in indexed_ids:
            continue
        paper_id = rec.get("paper_id", "")
        rec["year"] = pid2year.get(paper_id) or year_from_paper_id(paper_id)
        buf_texts.append(rec["text"])
        buf_meta.append(rec)

        if len(buf_texts) >= args.batch_size:
            print(f"  Embeddiendo {len(buf_texts)} chunks  (procesados: {len(all_meta) + len(buf_texts)})…")
            all_vectors.extend(embed_texts(client, buf_texts, args.model))
            all_meta.extend(buf_meta)
            buf_texts, buf_meta = [], []

    if buf_texts:
        print(f"  Embeddiendo último lote de {len(buf_texts)} chunks…")
        all_vectors.extend(embed_texts(client, buf_texts, args.model))
        all_meta.extend(buf_meta)

    if incremental and not all_vectors:
        print("Índice actualizado, nada nuevo.")
        return

    if not all_vectors:
        raise SystemExit("No se encontraron chunks para embeddear.")

    X = np.vstack(all_vectors)

    if incremental:
        index = faiss.read_index(str(index_path))
        index.add(X)
        with (out_dir / "metadata.jsonl").open("a", encoding="utf-8") as f:
            for m in all_meta:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        new_paper_ids    = {rec.get("paper_id", "") for rec in all_meta}
        all_indexed_ids  = indexed_ids | new_paper_ids
    else:
        dim   = X.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(X)
        with (out_dir / "metadata.jsonl").open("w", encoding="utf-8") as f:
            for m in all_meta:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        all_indexed_ids = {rec.get("paper_id", "") for rec in all_meta}

    faiss.write_index(index, str(index_path))

    dim          = index.d
    total_chunks = index.ntotal

    config = {
        "project":   args.project,
        "phase":     args.phase,
        "model":     args.model,
        "chunks":    total_chunks,
        "dimension": dim,
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    _save_indexed_papers(out_dir, all_indexed_ids, args.model)

    verb = "añadidos al índice" if incremental else "creados"
    print(f"\nChunks {verb} : {len(all_meta)}")
    if incremental:
        print(f"Total en índice    : {total_chunks}")
    print(f"Dimension          : {dim}")
    print(f"FAISS index        : {index_path}")
    print(f"Metadata           : {out_dir / 'metadata.jsonl'}")
    print(f"Config             : {out_dir / 'config.json'}")
    print(f"Indexed papers     : {out_dir / INDEXED_PAPERS_FILE}")


if __name__ == "__main__":
    main()
