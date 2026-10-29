# -*- coding: utf-8 -*-
"""
Helpers de embedding compartidos (Ollama, bge-m3).

Extraído de 5_build_embeddings.py para reutilizar el MISMO núcleo de embedding
desde el pipeline de libros (books/embed.py) sin duplicarlo ni alterar el
comportamiento de artículos. La escritura del índice FAISS / metadata.jsonl la
hace cada caller (artículos vs libros tienen políticas incrementales distintas).

Aquí vive también la ÚNICA implementación de la normalización L2 (item 55a):
la usan los dos constructores de índice (5_build_embeddings.py, books/embed.py)
y las dos rutas de consulta (utils/retrieval.dense_rank,
utils/attachments.rank_attachment). No duplicar en ningún otro sitio.
"""

import json
import os
from pathlib import Path

import numpy as np

from utils.constants import MAX_EMBED_CHARS

# Tolerancia de la norma L2 media de un índice para considerarlo normalizado.
NORM_TOL = 1e-3

# Número máximo de vectores que se reconstruyen del índice para medir la norma
# media (evita duplicar en RAM un índice enorme; con IndexFlat el orden de
# inserción se preserva, así que los primeros N son los más antiguos —
# justo los que interesan para detectar un índice viejo sin normalizar).
NORM_SAMPLE = 50_000


def make_client(host: str | None = None):
    """Crea un cliente Ollama apuntando a OLLAMA_HOST (o al host indicado)."""
    import ollama
    host = host or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11435")
    return ollama.Client(host=host)


def l2_normalize(vectors) -> np.ndarray:
    """Normaliza L2 por filas y devuelve SIEMPRE una copia float32 contigua.

    Item 55a: bge-m3 vía Ollama devuelve vectores sin normalizar (‖v‖ ≈ 27,1),
    así que la similitud L2 del índice no era coseno. Sobre vectores unitarios
    el orden por L2 coincide exactamente con el del coseno
    (‖q-d‖² = ‖q‖² - 2·q·d + 1, y ‖q‖² es constante para todos los d), por eso
    los índices siguen siendo IndexFlatL2 y "menor = mejor" no cambia en ningún
    consumidor.

    La COPIA es obligatoria: ``faiss.normalize_L2`` muta in-place y los callers
    reutilizan su vector de consulta (2_RAG lo pasa después a rank_attachment;
    14_Preparar_clase lo reutiliza en varios índices).

    Un vector nulo se devuelve nulo (no se divide por cero).
    """
    a = np.array(vectors, dtype="float32", copy=True)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    norms = np.linalg.norm(a, axis=1, keepdims=True)
    np.maximum(norms, 1e-12, out=norms)
    a /= norms
    return np.ascontiguousarray(a)


def index_mean_norm(index, limit: int = NORM_SAMPLE) -> float:
    """Norma L2 media de (hasta ``limit``) vectores del índice. 0.0 si está vacío."""
    n = min(int(index.ntotal), int(limit))
    if n <= 0:
        return 0.0
    vecs = np.asarray(index.reconstruct_n(0, n), dtype="float32")
    return float(np.linalg.norm(vecs, axis=1).mean())


def assert_index_normalized(index, context: str = "") -> float:
    """Falla ruidosamente si los vectores del índice no son unitarios (item 55b).

    Se usa ANTES de añadir al índice en modo incremental: un índice construido
    antes del item 55a tiene ‖v‖ ≈ 27 y mezclarle vectores normalizados daría un
    ranking basura en silencio. Devuelve la norma media si todo está bien.
    """
    mean_norm = index_mean_norm(index)
    if abs(mean_norm - 1.0) > NORM_TOL:
        raise SystemExit(
            f"ÍNDICE SIN NORMALIZAR{f' ({context})' if context else ''}: la norma L2 media "
            f"de sus vectores es {mean_norm:.4f}, se esperaba 1.0 ± {NORM_TOL}.\n"
            "Es un índice construido antes del item 55a. Re-indexa desde cero con "
            "--force; no se puede mezclar con vectores normalizados."
        )
    return mean_norm


def verify_index_integrity(out_dir, index) -> tuple[int, float]:
    """Invariante de integridad del item 55b. Error RUIDOSO, nunca warning.

    Comprueba las tres cosas al terminar de construir un índice:
      1. ``index.ntotal`` == número de líneas de ``metadata.jsonl``;
      2. norma L2 media de los vectores ≈ 1,0 (detecta un índice sin normalizar);
      3. ``config.json`` declara ``"normalized": true`` (detecta un rollout
         parcial: 14_Preparar_clase.py mezcla varios índices por distancia, así
         que un índice sin normalizar entre los demás da basura sin avisar).

    Devuelve (n_vectores, norma_media).
    """
    out_dir   = Path(out_dir)
    meta_path = out_dir / "metadata.jsonl"

    if not meta_path.exists():
        raise SystemExit(f"INTEGRIDAD (55b): no existe {meta_path}")

    with meta_path.open(encoding="utf-8") as f:
        n_meta = sum(1 for line in f if line.strip())

    if index.ntotal != n_meta:
        raise SystemExit(
            f"INTEGRIDAD (55b): index.ntotal={index.ntotal} != len(metadata)={n_meta} "
            f"en {out_dir}.\nÍndice y metadata están desalineados: los resultados de "
            "la consulta apuntarían al chunk equivocado. Re-indexa con --force."
        )

    mean_norm = index_mean_norm(index)
    if abs(mean_norm - 1.0) > NORM_TOL:
        raise SystemExit(
            f"INTEGRIDAD (55b): la norma L2 media del índice en {out_dir} es "
            f"{mean_norm:.4f}, se esperaba 1.0 ± {NORM_TOL}.\n"
            "Los vectores no se normalizaron (item 55a)."
        )

    cfg_path = out_dir / "config.json"
    if not cfg_path.exists():
        raise SystemExit(f"INTEGRIDAD (55b): no existe {cfg_path}")
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"INTEGRIDAD (55b): config.json ilegible en {out_dir}: {e}")
    if cfg.get("normalized") is not True:
        raise SystemExit(
            f"INTEGRIDAD (55b): config.json de {out_dir} no declara "
            '"normalized": true.\nSin ese flag un rollout parcial es indetectable '
            "para los consumidores multi-índice (14_Preparar_clase.py)."
        )

    return n_meta, mean_norm


EMBED_BATCH = 16          # textos por llamada a /api/embed
_batch_disabled = False   # se activa si el servidor no soporta /api/embed


def _embed_one_by_one(client, texts: list, model: str, truncated_out: list | None) -> list:
    """Camino original: un chunk por llamada; si excede el contexto del modelo lo
    trunca progresivamente (2/3 cada vez) y reintenta."""
    out = []
    for text in texts:
        full_len = len(text)
        t = text if full_len <= MAX_EMBED_CHARS else text[:MAX_EMBED_CHARS]
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
        if truncated_out is not None:
            truncated_out.append(len(t) < full_len)
    return out


def embed_texts(client, texts: list, model: str, truncated_out: list | None = None,
                batch: int = EMBED_BATCH) -> list:
    """Embeddea `texts` en lotes de `batch` con /api/embed (item 77): una llamada
    por lote en vez de una por chunk, ≈2× más rápido (medido; coseno 0,9999999 con
    el camino uno a uno). Se pide ``truncate=False`` para que un chunk que excede
    el contexto DÉ ERROR en vez de truncarse en silencio; ese lote cae entonces al
    camino uno a uno, que sí trunca progresivamente y lo anota. Si el servidor no
    soporta /api/embed se usa siempre el camino uno a uno.

    Devuelve una lista de np.ndarray float32 (uno por texto, en orden). Los
    vectores se devuelven CRUDOS (sin normalizar): normaliza el constructor del
    índice con ``l2_normalize`` justo antes de ``index.add``.

    ``truncated_out`` (opcional, P2 de la auditoría Kimi): si se pasa una lista,
    se le añade un booleano por texto indicando si el vector representa solo
    PARTE del texto — sea por el recorte previo a ``MAX_EMBED_CHARS`` o por el
    truncado reactivo. El caller lo persiste como ``embed_truncated`` en
    metadata.jsonl para poder auditar qué vectores no cubren su texto completo.
    """
    global _batch_disabled
    out: list = []
    for i in range(0, len(texts), max(1, batch)):
        chunk = texts[i:i + batch]
        done = False
        if not _batch_disabled and len(chunk) > 1 and hasattr(client, "embed"):
            clipped = [t if len(t) <= MAX_EMBED_CHARS else t[:MAX_EMBED_CHARS] for t in chunk]
            try:
                resp = client.embed(model=model, input=clipped, truncate=False)
                embs = resp["embeddings"]
                if len(embs) != len(chunk):
                    raise RuntimeError("lote con nº de vectores distinto")
                out.extend(np.array(e, dtype="float32") for e in embs)
                if truncated_out is not None:
                    truncated_out.extend(len(c) < len(t) for c, t in zip(clipped, chunk))
                done = True
            except Exception as e:
                msg = str(e).lower()
                if not ("context" in msg or "length" in msg or "too long" in msg):
                    _batch_disabled = True       # servidor sin /api/embed u otro fallo
                    print(f"  ℹ️ embedding por lotes desactivado ({type(e).__name__}); uno a uno")
        if not done:
            out.extend(_embed_one_by_one(client, chunk, model, truncated_out))
    return out


def check_index_vs_chunks(out_dir, chunks_dir) -> tuple:
    """Coherencia EXTERNA índice ↔ chunks (item 55d). `verify_index_integrity`
    solo ve la coherencia interna (ntotal == len(metadata)) y NO detecta vectores
    fantasma. Devuelve (fantasmas, sin_indexar):
      · fantasmas   = paper_id en el índice SIN fichero de chunks en disco;
      · sin_indexar = paper_id con chunks en disco que el índice no contiene.
    """
    out_dir, chunks_dir = Path(out_dir), Path(chunks_dir)
    in_index = set()
    mp = out_dir / "metadata.jsonl"
    if mp.exists():
        for ln in mp.read_text(encoding="utf-8").splitlines():
            try:
                in_index.add(json.loads(ln).get("paper_id", ""))
            except Exception:
                pass
    in_index.discard("")
    on_disk = set()
    for p in chunks_dir.rglob("*.jsonl"):
        n = p.name
        on_disk.add(n[:-len(".chunks.jsonl")] if n.endswith(".chunks.jsonl") else n[:-len(".jsonl")])
    return in_index - on_disk, on_disk - in_index


def prune_papers_from_index(out_dir, paper_ids) -> int:
    """Quita de un índice FAISS (IndexFlat, posicional) los vectores de unos
    paper_id SIN re-embeber nada (item 75). Borrar un paper no necesita
    recalcular los demás: se eliminan sus filas del índice y de metadata.jsonl
    (mismo orden, así que siguen alineados) y se actualizan config.json e
    indexed_papers.json. Escritura atómica (temporal + os.replace) y verificación
    de integridad al final.

    Devuelve el nº de vectores eliminados. Lanza ValueError si índice y
    metadata ya estaban desalineados (el llamador debe entonces reconstruir con
    ``5_build_embeddings.py --force``) o si el índice no es de tipo plano.
    """
    import faiss  # perezoso: solo hace falta en este camino

    out_dir = Path(out_dir)
    ids = set(paper_ids)
    idx_path, meta_path = out_dir / "index.faiss", out_dir / "metadata.jsonl"
    index = faiss.read_index(str(idx_path))
    if not isinstance(faiss.downcast_index(index), faiss.IndexFlat):
        raise ValueError(f"índice no plano ({type(index).__name__}): reconstruir con --force")
    lines = [l for l in meta_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if index.ntotal != len(lines):
        raise ValueError(f"índice ({index.ntotal}) y metadata ({len(lines)}) desalineados")

    drop = [i for i, l in enumerate(lines) if json.loads(l).get("paper_id") in ids]
    if not drop:
        return 0
    keep = [l for i, l in enumerate(lines) if i not in set(drop)]
    index.remove_ids(np.array(drop, dtype=np.int64))

    tmp_idx, tmp_meta = idx_path.with_suffix(".faiss.tmp"), meta_path.with_suffix(".jsonl.tmp")
    faiss.write_index(index, str(tmp_idx))
    tmp_meta.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    os.replace(tmp_idx, idx_path)
    os.replace(tmp_meta, meta_path)

    cfg_path = out_dir / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["chunks"] = index.ntotal
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    ip = out_dir / "indexed_papers.json"
    if ip.exists():
        data = json.loads(ip.read_text(encoding="utf-8"))
        data["paper_ids"] = sorted(set(data.get("paper_ids", [])) - ids)
        ip.write_text(json.dumps(data, indent=2), encoding="utf-8")

    if index.ntotal:
        verify_index_integrity(out_dir, index)
    return len(drop)
