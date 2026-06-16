# -*- coding: utf-8 -*-
"""
Generación de claves de cita (Apellido, Año; DOI) para el contexto del RAG.

Sin dependencia de streamlit, para que tanto las páginas Streamlit como el CLI
8_query_rag.py puedan reutilizarlo. La fuente de datos es
`<base>/<project>/metadata/papers_metadata.jsonl`, donde cada registro tiene al
menos: paper_id, doi, year, authors (lista de dicts con full/forename/surname).
Cuando no hay metadata o el paper_id no aparece, se cae a heurísticas sobre el
propio paper_id sin lanzar excepción.
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional

from utils.constants import year_from_paper_id

# Tokens "Mayúscula + minúsculas" usados para descomponer nombres concatenados
# tipo "AndrePauss" / "DLWise" en sus palabras capitalizadas.
_CAMEL_WORD = re.compile(r"[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+")
# paper_id renombrado por DOI/Crossref: "AAAA_apellido_resto...".
_PAPER_ID_RE = re.compile(r"^(\d{4})_([A-Za-zÁÉÍÓÚÑÜáéíóúñü]+)")


def load_papers_metadata(project: str, base: Path) -> Dict[str, dict]:
    """Lee `<base>/<project>/metadata/papers_metadata.jsonl`.

    Devuelve {paper_id: record}. Si el fichero no existe, devuelve {}.
    """
    path = Path(base) / project / "metadata" / "papers_metadata.jsonl"
    if not path.exists():
        return {}
    out: Dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = rec.get("paper_id")
            if pid:
                out[pid] = rec
    return out


def _surname_from_paper_id(paper_id: str) -> Optional[str]:
    """Heurística de fallback: paper_id sigue el patrón 'AAAA_apellido_resto...'.

    Extrae el segundo segmento (separado por '_') y lo capitaliza. Devuelve
    None si no hace match.
    """
    m = _PAPER_ID_RE.match(paper_id or "")
    if not m:
        return None
    return m.group(2).capitalize()


def _surname_from_full(full: str) -> Optional[str]:
    """Extrae el apellido de un nombre completo, también si viene concatenado.

    'AndrePauss' -> 'Pauss', 'DLWise' -> 'Wise', 'Peter Weiland' -> 'Weiland'.
    Toma la última palabra capitalizada de longitud >= 2.
    """
    words = _CAMEL_WORD.findall(full or "")
    if words:
        return words[-1]
    # Sin palabras camelCase: usar el último token separado por espacios.
    tokens = [t for t in (full or "").split() if len(t) >= 2]
    return tokens[-1].capitalize() if tokens else None


def first_author_surname(paper_id: str, papers_meta: Dict[str, dict]) -> str:
    """Apellido del primer autor.

    Prioriza el campo de autores de papers_meta[paper_id]; si no hay registro o
    el dato no es utilizable, cae a la heurística sobre el paper_id. Si todo
    falla, devuelve '?'.
    """
    rec = papers_meta.get(paper_id) or {}
    authors = rec.get("authors") or []
    if authors:
        first = authors[0] if isinstance(authors[0], dict) else {}
        surname = (first.get("surname") or "").strip()
        if surname:
            return surname[:1].upper() + surname[1:]
        guess = _surname_from_full(first.get("full") or "")
        if guess:
            return guess
    fallback = _surname_from_paper_id(paper_id)
    return fallback or "?"


def citation_key(paper_id: str, papers_meta: Dict[str, dict]) -> str:
    """Clave de cita '(Apellido, Año; DOI)' lista para insertar en el contexto.

    Sin DOI -> '(Apellido, Año)'. Año ausente -> 's.f.'.
    """
    surname = first_author_surname(paper_id, papers_meta)
    rec = papers_meta.get(paper_id) or {}
    year = rec.get("year") or year_from_paper_id(paper_id)
    doi = rec.get("doi")
    year_str = str(year) if year else "s.f."
    if doi:
        return f"({surname}, {year_str}; {doi})"
    return f"({surname}, {year_str})"


def attachment_citation_key(filename: str | None, label: str | None) -> str:
    """Clave de cita sintética para un documento adjunto efímero.

    - Si ``label`` no está vacía -> ``(label; adjunto)``.
    - Si ``filename`` casa con el patrón ``AAAA_apellido_...`` ->
      ``(Apellido, Año; adjunto)``.
    - Si ``filename`` tiene stem -> ``(stem; adjunto)``.
    - En cualquier otro caso -> ``(adjunto)``.
    """
    label = (label or "").strip()
    if label:
        return f"({label}; adjunto)"

    filename = filename or ""
    surname = _surname_from_paper_id(filename)
    if surname:
        year = year_from_paper_id(filename)
        year_str = str(year) if year else "s.f."
        return f"({surname}, {year_str}; adjunto)"

    stem = Path(filename).stem if filename else ""
    if stem:
        return f"({stem}; adjunto)"
    return "(adjunto)"


# Reglas de citado para insertar en los prompts de síntesis. El LLM cita con la
# etiqueta [N] (fácil de cumplir); nosotros sustituimos [N] por la clave real en
# post-proceso (apply_citations). SIN llaves { } para no interferir con .format().
CITE_PROMPT_RULES = (
    "Cita SIEMPRE con la etiqueta [N] del fragmento, colocada justo después "
    "del dato o afirmación que respalda (no agrupes las citas al final del "
    "párrafo). Si una frase combina varias fuentes, ponlas juntas: [1][3]. "
    "Usa ÚNICAMENTE las etiquetas [N] que aparecen en los fragmentos. "
    "NO inventes autores, años, DOIs, revistas, volúmenes ni páginas. "
    "NO añadas una sección de 'Referencias', 'Bibliografía' o 'References' "
    "al final: las referencias se generan automáticamente."
)


def build_cite_map(results, papers_meta: Dict[str, dict]) -> Dict[int, str]:
    """results: lista de tuplas (..., m) en el MISMO orden que el contexto [N].

    Devuelve {N: '(Apellido, Año; DOI)'} con N empezando en 1. Si un chunk
    trae su propia clave en ``m['_cite']`` (adjuntos efímeros), se usa esa.
    """
    cmap: Dict[int, str] = {}
    for i, item in enumerate(results, 1):
        m = item[-1]  # el dict de metadata es el último elemento de la tupla
        key = m.get("_cite") or citation_key(m.get("paper_id", ""), papers_meta)
        cmap[i] = key
    return cmap


_REFS_HEADING = re.compile(
    r"\n+\s*(#+\s*)?(referencias|bibliograf[íi]a|references)\s*:?\s*\n.*$",
    re.IGNORECASE | re.DOTALL,
)


def strip_reference_section(text: str) -> str:
    """Elimina un bloque final de Referencias/Bibliografía/References que el
    modelo haya añadido pese a la instrucción."""
    return _REFS_HEADING.sub("", text).rstrip()


# Una etiqueta [N] y, opcionalmente, las contiguas separadas por espacios:
# '[1]', '[1][3]', '[1] [3]'. No consume el espacio que sigue al último
# corchete (para no pegar la cita a la palabra siguiente).
_CITE_GROUP = re.compile(r"\[\d+\](?:\s*\[\d+\])*")


def apply_citations(text: str, cite_map: Dict[int, str]) -> str:
    """Sustituye cada [N] por su clave (Apellido, Año; DOI). [N] desconocido
    se deja intacto. Colapsa secuencias pegadas: '[1][3]' -> '(...; ...)'."""
    text = strip_reference_section(text)

    def _repl_group(mobj):
        nums = re.findall(r"\[(\d+)\]", mobj.group(0))
        keys = []
        for n in nums:
            k = cite_map.get(int(n))
            if k:
                # quita los paréntesis externos para fusionar varios en uno
                keys.append(k.strip().lstrip("(").rstrip(")"))
        if not keys:
            return mobj.group(0)
        return "(" + "; ".join(keys) + ")"

    return _CITE_GROUP.sub(_repl_group, text)
