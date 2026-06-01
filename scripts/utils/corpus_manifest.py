# -*- coding: utf-8 -*-
"""
corpus_manifest.py — Genera y lee el manifiesto de corpus para una categoría.

Escribe categorias/<category>/corpus_manifest.json con métricas de estado:
n_pdfs, n_md_clean, n_chunks, calidad de metadatos, índices FAISS, etc.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


def _count_lines(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _git_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _keywords_hash(category: str) -> Optional[str]:
    """SHA1 (8 chars) del bloque de keywords del category en config/keywords.yml."""
    kw_path = Path(__file__).resolve().parent.parent.parent / "config" / "keywords.yml"
    if not kw_path.exists():
        return None
    try:
        import yaml
        with kw_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        block = data.get(category)
        if block is None:
            return None
        raw = json.dumps(block, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode()).hexdigest()[:8]
    except Exception:
        return None


def _faiss_indexes(category: str, base: Path) -> list:
    emb_dir = base / category / "embeddings"
    if not emb_dir.exists():
        return []
    result = []
    for sub in sorted(emb_dir.iterdir()):
        if not sub.is_dir():
            continue
        index_path = sub / "index.faiss"
        if not index_path.exists():
            continue
        cfg_path = sub / "config.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        except Exception:
            cfg = {}
        mtime = datetime.fromtimestamp(index_path.stat().st_mtime).isoformat()
        result.append({
            "phase":     sub.name,
            "model":     cfg.get("model"),
            "chunks":    cfg.get("chunks"),
            "dimension": cfg.get("dimension"),
            "mtime":     mtime,
        })
    return result


def _faiss_stale(category: str, base: Path) -> bool:
    """True si algún PDF en pdfs/ es más nuevo que el index.faiss más reciente."""
    pdfs_dir = base / category / "pdfs"
    emb_dir  = base / category / "embeddings"

    pdfs = list(pdfs_dir.glob("*.pdf")) if pdfs_dir.exists() else []
    if not pdfs:
        return False

    index_files = []
    if emb_dir.exists():
        for sub in emb_dir.iterdir():
            idx = sub / "index.faiss"
            if idx.exists():
                index_files.append(idx)

    if not index_files:
        return True

    latest_index_mtime = max(f.stat().st_mtime for f in index_files)
    return any(p.stat().st_mtime > latest_index_mtime for p in pdfs)


def build_manifest(category: str, base: Path) -> dict:
    """Construye y devuelve el dict del manifiesto para una categoría."""
    cat_dir = base / category

    pdfs_dir = cat_dir / "pdfs"
    n_pdfs = sum(1 for _ in pdfs_dir.glob("*.pdf")) if pdfs_dir.exists() else 0

    md_dir = cat_dir / "md_clean"
    n_md_clean = sum(1 for _ in md_dir.glob("*.clean.md")) if md_dir.exists() else 0

    chunks_dir = cat_dir / "chunks"
    n_chunks = 0
    if chunks_dir.exists():
        for jf in chunks_dir.glob("*.jsonl"):
            n_chunks += _count_lines(jf)

    meta_path = cat_dir / "metadata" / "papers_metadata.jsonl"
    n_papers_metadata = 0
    avg_quality_score = None
    if meta_path.exists():
        scores = []
        try:
            with meta_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    n_papers_metadata += 1
                    try:
                        rec = json.loads(line)
                        qs = rec.get("quality_score")
                        if qs is not None:
                            scores.append(float(qs))
                    except Exception:
                        pass
        except Exception:
            pass
        if scores:
            avg_quality_score = round(sum(scores) / len(scores), 3)

    return {
        "category":          category,
        "generated_at":      datetime.now().isoformat(),
        "n_pdfs":            n_pdfs,
        "n_md_clean":        n_md_clean,
        "n_chunks":          n_chunks,
        "n_papers_metadata": n_papers_metadata,
        "avg_quality_score": avg_quality_score,
        "faiss_indexes":     _faiss_indexes(category, base),
        "keywords_hash":     _keywords_hash(category),
        "git_commit":        _git_commit(),
        "faiss_stale":       _faiss_stale(category, base),
    }


def write_manifest(category: str, base: Path) -> Path:
    """Genera y escribe el manifiesto; devuelve la ruta del fichero creado."""
    manifest = build_manifest(category, base)
    out_path = base / category / "corpus_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def read_manifest(category: str, base: Path) -> dict:
    """Lee el manifiesto si existe; devuelve {} si no."""
    path = base / category / "corpus_manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera corpus_manifest.json para una categoría."
    )
    parser.add_argument("--project", required=True, help="Nombre de la categoría")
    parser.add_argument(
        "--base",
        default="/Volumes/research/categorias",
        help="Directorio raíz de categorías (defecto: /Volumes/research/categorias)",
    )
    args = parser.parse_args()
    out = write_manifest(args.project, Path(args.base))
    print(out)
