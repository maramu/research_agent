# -*- coding: utf-8 -*-
"""
Helpers puros para documentos efímeros adjuntos a una consulta RAG.

Sin dependencia de Streamlit: puede importarse tanto desde la página 2_RAG.py
como desde tests. La única dependencia "pesada" opcional es pymupdf (fitz)
para extraer texto de PDFs.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from utils.citations import attachment_citation_key
from utils.constants import year_from_paper_id
from utils.embeddings import l2_normalize

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - pymupdf se instala en el entorno de ejecución
    fitz = None

TARGET_CHARS_DEFAULT = 1000
OVERLAP_DEFAULT = 150


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extrae texto plano de PDF, TXT o MD.

    - PDF: PyMuPDF (fitz.open con stream).
    - TXT/MD: decodificación UTF-8 tolerante.
    - Otros: ValueError.
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        if fitz is None:
            raise ImportError(
                "pymupdf (fitz) no está instalado; instálalo para extraer texto de PDFs."
            )
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            return "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()

    if ext in (".txt", ".md"):
        return file_bytes.decode("utf-8", errors="replace")

    raise ValueError(
        f"Formato no soportado: '{ext}'. Usa .pdf, .txt o .md."
    )


def chunk_text(text: str, target_chars: int = TARGET_CHARS_DEFAULT,
               overlap: int = OVERLAP_DEFAULT) -> List[str]:
    """Troceado simple por párrafos con solape.

    Agrupa párrafos consecutivos hasta aproximadamente ``target_chars``,
    arrastra los últimos ``overlap`` caracteres del chunk anterior al
    siguiente, y descarta fragmentos vacíos o menores de 30 caracteres.
    """
    if not text or not text.strip():
        return []

    # Separar por líneas en blanco y descartar párrafos vacíos.
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    def _flush() -> None:
        nonlocal current, current_len
        if not current:
            return
        body = "\n\n".join(current)
        if len(body) >= 30:
            chunks.append(body)
        current = []
        current_len = 0

    for para in paras:
        # Si añadir el párrafo supera el tope, cerramos el chunk actual.
        if current and current_len + len(para) + 2 > target_chars:
            prev = "\n\n".join(current)
            _flush()
            # Solape: arrancamos el siguiente chunk con el final del anterior.
            if overlap > 0 and prev:
                tail = prev[-overlap:]
                current = [tail]
                current_len = len(tail)

        current.append(para)
        current_len += len(para) + 2  # +2 por el "\n\n" aproximado

    _flush()
    return chunks


def embed_texts(client, texts: List[str], model: str) -> np.ndarray:
    """Embebe una lista de textos con el MISMO cliente+modelo de la query.

    Devuelve una matriz float32 de forma (n_texts, dims) con los vectores
    CRUDOS. La normalización (item 55a) la aplica ``rank_attachment`` justo
    antes de medir distancias, para que las matrices ya cacheadas en
    ``session_state`` sigan sirviendo sin recalcular embeddings.
    """
    if not texts:
        return np.empty((0, 0), dtype="float32")

    vectors = []
    for prompt in texts:
        resp = client.embeddings(model=model, prompt=prompt)
        vectors.append(np.array(resp["embedding"], dtype="float32"))
    return np.vstack(vectors)


def rank_attachment(qv: np.ndarray, mat: np.ndarray) -> List[Tuple[int, float]]:
    """Distancia L2 al cuadrado entre la query y cada chunk del adjunto.

    Devuelve ``[(idx_chunk, dist)]`` ordenado de menor a mayor distancia.
    No usa FAISS: para un adjunto efímero con pocos chunks numpy basta.

    Item 55a: normaliza query y matriz (sobre copias, vía el helper único de
    ``utils.embeddings``) porque ``fuse_results`` MEZCLA POR DISTANCIA estos
    valores con los del corpus, cuyo índice ya está normalizado. Sin esto el
    adjunto arrastraría distancias de escala ~700 (‖v‖ ≈ 27) contra las de
    escala [0, 2] del corpus y no ganaría nunca una plaza de relleno.
    """
    if mat.shape[0] == 0:
        return []

    q = l2_normalize(qv)
    m = l2_normalize(mat)
    dists = ((m - q) ** 2).sum(axis=1)
    order = np.argsort(dists, kind="stable")
    return [(int(i), float(dists[i])) for i in order]


def fuse_results(corpus_results, attach_scored, attach_metas, k: int,
                 n_min: int, hybrid: bool):
    """Fusiona resultados del corpus con chunks de un adjunto efímero.

    Parámetros
    ----------
    corpus_results : list[(score, idx, m)]
        Resultados ya filtrados/truncados del corpus. En modo no híbrido
        ``score`` es distancia L2 (menor = mejor); en híbrido ``score`` es
        RRF (mayor = mejor).
    attach_scored : list[(a_idx, dist)]
        Chunks del adjunto ordenados por distancia L2 ascendente.
    attach_metas : list[dict]
        Metadatas de los chunks del adjunto, indexadas por ``a_idx``.
    k : int
        Número total de fragmentos a devolver.
    n_min : int
        Cupo mínimo garantizado de chunks del adjunto.
    hybrid : bool
        True si el corpus viene de RRF (score de rango, NO comparable con
        distancias L2).

    Lógica
    ------
    1. Se reservan ``min(n_min, k, disponibles)`` chunks del adjunto (los
       más cercanos a la query).
    2. El resto de plazas se rellenan:
       - Modo no híbrido: mezclando el resto del adjunto con el corpus por
         distancia L2 (la distancia del corpus es comparable).
       - Modo híbrido: ÚNICAMENTE con resultados del corpus en su orden RRF.
         No se mezcla por distancia con el adjunto porque RRF (rango) y L2
         (distancia) tienen escalas distintas e incomparables.
    3. Orden de salida: por distancia ascendente en modo no híbrido; cupo del
       adjunto primero y luego corpus en orden RRF en modo híbrido.

    Devuelve ``[(score, idx, m)]`` listo para numerar [N] en el contexto.
    """
    n_attach = min(len(attach_scored), len(attach_metas))
    n_guaranteed = min(int(n_min), k, n_attach)

    guaranteed = [
        (float(dist), -1, attach_metas[a_idx])
        for a_idx, dist in attach_scored[:n_guaranteed]
    ]

    remaining = k - n_guaranteed
    if remaining <= 0:
        final = guaranteed
    elif not hybrid:
        rest_attach = [
            (float(dist), -1, attach_metas[a_idx])
            for a_idx, dist in attach_scored[n_guaranteed:]
        ]
        candidates = rest_attach + list(corpus_results)
        fill = sorted(candidates, key=lambda x: x[0])[:remaining]
        final = guaranteed + fill
        final.sort(key=lambda x: x[0])
    else:
        # En híbrido los scores del corpus son RRF (mayor=mejor). No es
        # comparable con distancias L2, así que no mezclamos por distancia:
        # el adjunto aporta solo su cupo garantizado y el resto se toma del
        # corpus en su orden RRF.
        fill = list(corpus_results)[:remaining]
        final = guaranteed + fill

    return final


def make_attachment_metas(chunks: List[str], filename: str | None,
                          label: str | None) -> List[Dict[str, Any]]:
    """Crea metadatas sintéticas para los chunks de un adjunto.

    Comparten forma con los metadatos del corpus para que el bucle de
    contexto y ``build_cite_map`` no necesiten ramas especiales.
    """
    cite = attachment_citation_key(filename or "", label or "")
    year = year_from_paper_id(filename or "")
    return [
        {
            "text": chunk,
            "section": "ADJUNTO",
            "section_canonical": "attachment",
            "type": "text",
            "paper_id": "__attachment__",
            "year": year,
            "_attachment": True,
            "_cite": cite,
        }
        for chunk in chunks
    ]


def content_hash(source_bytes: bytes, cfg: dict) -> str:
    """Hash del contenido + configuración de troceado/modelo.

    Permite reutilizar embeddings de un adjunto idéntico sin volver a
    llamar al modelo de embedding.
    """
    payload = source_bytes + repr(cfg).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
