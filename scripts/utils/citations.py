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


# Reglas de citado para insertar en los prompts de síntesis. SIN llaves { } para
# no interferir con str.format().
CITATION_INSTRUCTIONS = (
    "Reglas de citado:\n"
    "- Cita usando EXACTAMENTE la clave de cita que precede a cada fragmento, "
    "con el formato (Apellido, Año; DOI). No uses [N] ni el paper_id como cita.\n"
    "- Coloca cada cita junto al dato o afirmación concreta que respalda; no "
    "agrupes todas las citas al final del párrafo.\n"
    "- Si una frase combina varias fuentes, incluye todas sus claves dentro del "
    "mismo paréntesis separadas por ';'.\n"
    "- No inventes autores, años ni DOIs: usa solo los que aparecen en las "
    "claves de cita del contexto."
)
