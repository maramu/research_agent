# -*- coding: utf-8 -*-
"""
0_scopus_api.py — Paso 0 del pipeline research_agent

Consulta la Scopus Search API por categoría de investigación y genera CSVs
listos para ser procesados por 3a_download_pdfs.py.

Posición en el pipeline:
    scopus_queries.yml → 0_scopus_api.py → inbox_csv/ → 3a_download_pdfs.py

Ficheros leídos:
    config/scopus_queries.yml          ← queries Scopus por categoría (YAML)
    config/.env                        ← ELSEVIER_API_KEY, ELSEVIER_INSTTOKEN

Ficheros escritos:
    /Volumes/research/inbox_csv/
        scopus_<categoria>_<YYYYMMDD>.csv   ← un CSV por categoría procesada
        scopus_ALL_<YYYYMMDD>.csv           ← CSV global combinado
    /Volumes/Disco/proyectos/research_agent/logs/
        0_scopus_api_<timestamp>.log

Parámetros CLI:
    --queries YAML        Ruta al YAML de queries (defecto: config/scopus_queries.yml)
    --category NOMBRE     Categoría a procesar; repetible para varias (defecto: todas)
    --max N               Máximo de resultados por categoría tras dedup (defecto: 200)
    --year-start AÑO      Solo artículos desde este año inclusive
    --year-end AÑO        Solo artículos hasta este año inclusive
    --doctype TIPO        Filtro tipo Scopus: ar=article, re=review, cp=conference paper
    --recent-days N       Solo artículos indexados en los últimos N días (RECENT(N))
    --out-dir DIR         Directorio de salida para los CSVs
    --log LOG             Ruta al fichero de log
    --sleep SEG           Pausa entre peticiones a la API en segundos (defecto: 1.0)
    --dry-run             Muestra totales sin descargar ni guardar nada

Variables de entorno (config/.env):
    ELSEVIER_API_KEY      Clave de la Elsevier Developer API (obligatoria)
    ELSEVIER_INSTTOKEN    Token institucional opcional para acceso ampliado

Dependencias:
    pandas, requests, pyyaml, python-dotenv, urllib3

Ejemplos:
    python 0_scopus_api.py
    python 0_scopus_api.py --category microalgae --year-start 2020 --max 500
    python 0_scopus_api.py --recent-days 7
    python 0_scopus_api.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent
_DOTENV_PATH = _SCRIPT_DIR.parent / "config" / ".env"
load_dotenv(_DOTENV_PATH)
load_dotenv()

NAS_ROOT = Path("/Volumes/research")
_LOGS_DIR = Path("/Volumes/Disco/proyectos/research_agent/logs")

_SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
_PAGE_SIZE = 25  # máximo permitido por la API Scopus

# Campos solicitados a la API
_FIELDS = ",".join([
    "dc:identifier",
    "dc:title",
    "prism:doi",
    "dc:creator",
    "prism:coverDate",
    "prism:publicationName",
    "prism:volume",
    "prism:issueIdentifier",
    "prism:pageRange",
    "citedby-count",
    "subtypeDescription",
    "openaccess",
    "prism:url",
])


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(log_file: Optional[Path] = None) -> None:
    logger = logging.getLogger("scopus")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(ch)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
        logger.addHandler(fh)


log = logging.getLogger("scopus")


# ---------------------------------------------------------------------------
# Validación NAS
# ---------------------------------------------------------------------------

def check_nas_mounted() -> None:
    if not NAS_ROOT.exists():
        sys.exit(
            f"\nError: el NAS no está montado en {NAS_ROOT}\n"
            "Monta la unidad antes de ejecutar este script:\n"
            "  - Finder → Red → Synology → research, o\n"
            "  - usa: open smb://synology/research\n"
        )


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.getenv("ELSEVIER_API_KEY", ""))
    insttoken: str = field(default_factory=lambda: os.getenv("ELSEVIER_INSTTOKEN", ""))
    queries_file: Path = field(default_factory=lambda: _SCRIPT_DIR.parent / "config" / "scopus_queries.yml")
    out_dir: Path = field(default_factory=lambda: NAS_ROOT / "inbox_csv")
    log_file: Path = field(
        default_factory=lambda: _LOGS_DIR
        / f"0_scopus_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    categories: List[str] = field(default_factory=list)
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    max_results: int = 200
    doctype: Optional[str] = None
    recent_days: Optional[int] = None
    sleep: float = 1.0
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Sesión HTTP
# ---------------------------------------------------------------------------

def build_session(cfg: Config) -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        respect_retry_after_header=True,
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    headers: Dict[str, str] = {
        "X-ELS-APIKey": cfg.api_key,
        "Accept": "application/json",
    }
    if cfg.insttoken:
        headers["X-ELS-Insttoken"] = cfg.insttoken
    session.headers.update(headers)
    return session


# ---------------------------------------------------------------------------
# Carga de queries YAML
# ---------------------------------------------------------------------------

def load_queries(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        sys.exit(
            f"\nError: no se encontró el fichero de queries: {path}\n"
            "Crea config/scopus_queries.yml en la raíz del proyecto o usa --queries para indicar la ruta.\n"
        )
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        sys.exit(
            f"Error: {path} no tiene el formato esperado "
            "(debe ser un dict YAML: categoria → lista de queries)."
        )
    # Filtrar entradas sin queries (e.g. irrelevante: [])
    return {k: v for k, v in data.items() if v}


# ---------------------------------------------------------------------------
# Construcción de query con filtros
# ---------------------------------------------------------------------------

def build_query(base: str, cfg: Config) -> str:
    """Envuelve la query base con los filtros de año, doctype y recent_days."""
    parts = [f"({base})"]
    if cfg.year_start:
        parts.append(f"PUBYEAR > {cfg.year_start - 1}")
    if cfg.year_end:
        parts.append(f"PUBYEAR < {cfg.year_end + 1}")
    if cfg.doctype:
        parts.append(f"DOCTYPE({cfg.doctype})")
    if cfg.recent_days is not None:
        parts.append(f"RECENT({cfg.recent_days})")
    return " AND ".join(parts)


# ---------------------------------------------------------------------------
# Petición a la API (una página)
# ---------------------------------------------------------------------------

def fetch_page(
    session: requests.Session,
    query: str,
    start: int,
    cfg: Config,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "query": query,
        "count": _PAGE_SIZE,
        "start": start,
        "field": _FIELDS,
        "sort": "-citedby-count",
    }
    for attempt in range(1, 4):
        try:
            resp = session.get(_SCOPUS_SEARCH_URL, params=params, timeout=(10, 30))
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                log.warning("Rate-limit 429. Esperando %d s…", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            log.warning("Intento %d/3 fallido: %s", attempt, exc)
            time.sleep(cfg.sleep * attempt * 3)
    raise RuntimeError(f"No se pudo obtener la página start={start} tras 3 intentos.")


# ---------------------------------------------------------------------------
# Parseo de un registro
# ---------------------------------------------------------------------------

def parse_entry(entry: Dict[str, Any]) -> Dict[str, str]:
    doi = (entry.get("prism:doi", "") or "").strip()
    cover_date = (entry.get("prism:coverDate", "") or "")
    year = cover_date[:4] if cover_date else ""
    return {
        "DOI":          doi,
        "Title":        (entry.get("dc:title", "") or "").strip(),
        "Authors":      (entry.get("dc:creator", "") or "").strip(),
        "Year":         year,
        "Journal":      (entry.get("prism:publicationName", "") or "").strip(),
        "Volume":       (entry.get("prism:volume", "") or "").strip(),
        "Issue":        (entry.get("prism:issueIdentifier", "") or "").strip(),
        "Pages":        (entry.get("prism:pageRange", "") or "").strip(),
        "CitedBy":      str(entry.get("citedby-count", "") or ""),
        "DocType":      (entry.get("subtypeDescription", "") or "").strip(),
        "OpenAccess":   str(entry.get("openaccess", "") or ""),
        "ScopusURL":    (entry.get("prism:url", "") or "").strip(),
        "ScopusID":     (entry.get("dc:identifier", "") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Búsqueda paginada de una query
# ---------------------------------------------------------------------------

def search_query(
    session: requests.Session,
    query_str: str,
    cfg: Config,
    label: str = "",
) -> List[Dict[str, str]]:
    full_query = build_query(query_str, cfg)
    log.debug("    Query completa: %s", full_query)

    # Primera página → también nos da el total disponible en la API
    data = fetch_page(session, full_query, start=0, cfg=cfg)
    sr = data.get("search-results", {})
    total_str = sr.get("opensearch:totalResults", "0")
    total_api = int(total_str) if str(total_str).isdigit() else 0

    effective_max = min(cfg.max_results, total_api)
    log.info("    %s → %d en API, recuperando hasta %d", label, total_api, effective_max)

    if cfg.dry_run:
        return []

    records: List[Dict[str, str]] = []
    for entry in sr.get("entry", []):
        if "error" not in entry:
            records.append(parse_entry(entry))

    start = _PAGE_SIZE
    time.sleep(cfg.sleep)

    while start < effective_max:
        page_data = fetch_page(session, full_query, start=start, cfg=cfg)
        entries = page_data.get("search-results", {}).get("entry", [])
        if not entries:
            break
        for entry in entries:
            if "error" not in entry:
                records.append(parse_entry(entry))
        start += _PAGE_SIZE
        time.sleep(cfg.sleep)

    return records[:effective_max]


# ---------------------------------------------------------------------------
# Procesado de una categoría completa
# ---------------------------------------------------------------------------

def process_category(
    category: str,
    queries: List[str],
    session: requests.Session,
    cfg: Config,
    run_date: str,
) -> Optional[pd.DataFrame]:
    log.info("══════════════════════════════════════════")
    log.info("Categoría: %s  (%d queries)", category, len(queries))

    all_records: List[Dict[str, str]] = []

    for i, q in enumerate(queries, start=1):
        log.info("  [%d/%d] %s…", i, len(queries), q[:90])
        try:
            records = search_query(
                session=session,
                query_str=q,
                cfg=cfg,
                label=f"q{i}/{len(queries)}",
            )
            all_records.extend(records)
        except Exception as exc:
            log.error("  Error en query %d: %s", i, exc)

    if cfg.dry_run:
        log.info("  [DRY-RUN] Sin guardado.")
        return None

    if not all_records:
        log.warning("  Sin resultados para '%s'.", category)
        return None

    df = pd.DataFrame(all_records)
    n_raw = len(df)

    # Deduplicar por DOI (mantener el más citado)
    df["_cites_num"] = pd.to_numeric(df["CitedBy"], errors="coerce").fillna(0)
    df = df.sort_values("_cites_num", ascending=False)
    has_doi = df["DOI"].str.strip().ne("")
    df_doi    = df[has_doi].drop_duplicates(subset="DOI", keep="first")
    df_no_doi = df[~has_doi]
    df = pd.concat([df_doi, df_no_doi], ignore_index=True).drop(columns=["_cites_num"])

    n_dedup = len(df)
    log.info("  Resultados: %d brutos → %d tras dedup por DOI", n_raw, n_dedup)

    # Columna de trazabilidad
    df.insert(0, "scopus_category", category)

    # Guardar CSV de la categoría
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.out_dir / f"scopus_{category}_{run_date}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    log.info("  → %s", out_path)

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "0_scopus_api — Consulta Scopus Search API por categoría y genera "
            "CSVs compatibles con 3a_download_pdfs.py. "
            f"Requiere NAS en {NAS_ROOT} y ELSEVIER_API_KEY en config/.env."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--queries", default=None, metavar="YAML",
        help="Ruta al YAML de queries (por defecto: config/scopus_queries.yml en la raíz del proyecto).",
    )
    parser.add_argument(
        "--category", action="append", dest="categories", metavar="NOMBRE",
        help=(
            "Categoría a procesar (repetible). "
            "Por defecto se procesan todas las del YAML."
        ),
    )
    parser.add_argument(
        "--max", type=int, default=200, metavar="N",
        help="Máximo de resultados por categoría (tras dedup). Por defecto: 200.",
    )
    parser.add_argument(
        "--year-start", type=int, default=None, metavar="AÑO",
        help="Incluir solo artículos desde este año (inclusive).",
    )
    parser.add_argument(
        "--year-end", type=int, default=None, metavar="AÑO",
        help="Incluir solo artículos hasta este año (inclusive).",
    )
    parser.add_argument(
        "--doctype", default=None, metavar="TIPO",
        help=(
            "Filtrar tipo de documento Scopus: "
            "ar=article, re=review, cp=conference paper. "
            "Por defecto: sin filtro."
        ),
    )
    parser.add_argument(
        "--out-dir", default=None, metavar="DIR",
        help=f"Directorio de salida para los CSVs (por defecto: {NAS_ROOT}/inbox_csv/).",
    )
    parser.add_argument(
        "--log", default=None, metavar="LOG",
        help="Ruta al log (por defecto: logs/0_scopus_api_<timestamp>.log).",
    )
    parser.add_argument(
        "--sleep", type=float, default=1.0, metavar="SEG",
        help="Pausa en segundos entre peticiones a la API. Por defecto: 1.0.",
    )
    parser.add_argument(
        "--recent-days", type=int, default=None, metavar="N",
        help=(
            "Solo artículos indexados en Scopus en los últimos N días "
            "(usa el operador RECENT(N)). Útil para ingesta incremental: "
            "--recent-days 7 trae lo nuevo de la última semana."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Muestra cuántos resultados hay por query sin descargar ni guardar nada.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    check_nas_mounted()
    args = parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    cfg = Config(
        queries_file=Path(args.queries) if args.queries else _SCRIPT_DIR.parent / "config" / "scopus_queries.yml",
        out_dir=Path(args.out_dir) if args.out_dir else NAS_ROOT / "inbox_csv",
        log_file=Path(args.log) if args.log else _LOGS_DIR / f"0_scopus_api_{ts}.log",
        categories=args.categories or [],
        year_start=args.year_start,
        year_end=args.year_end,
        max_results=args.max,
        doctype=args.doctype,
        recent_days=args.recent_days,
        sleep=args.sleep,
        dry_run=args.dry_run,
    )

    setup_logging(None if cfg.dry_run else cfg.log_file)

    # Validaciones
    if not cfg.api_key:
        sys.exit(
            "\nError: falta ELSEVIER_API_KEY.\n"
            "Obtén tu clave en https://dev.elsevier.com y añade al fichero config/.env:\n"
            "  ELSEVIER_API_KEY=tu_clave_aquí\n"
        )

    all_queries = load_queries(cfg.queries_file)

    if cfg.categories:
        unknown = [c for c in cfg.categories if c not in all_queries]
        if unknown:
            sys.exit(
                f"\nCategorías no encontradas en {cfg.queries_file.name}: "
                f"{', '.join(unknown)}\n"
                f"Disponibles: {', '.join(all_queries.keys())}\n"
            )
        selected = {k: all_queries[k] for k in cfg.categories}
    else:
        selected = all_queries

    log.info("=== 0_scopus_api — %s ===", datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("Categorías seleccionadas: %s", ", ".join(selected.keys()))
    log.info("Max resultados/categoría: %d", cfg.max_results)
    if cfg.year_start:
        log.info("Año desde: %d", cfg.year_start)
    if cfg.year_end:
        log.info("Año hasta: %d", cfg.year_end)
    if cfg.doctype:
        log.info("Doctype: %s", cfg.doctype)
    if cfg.recent_days is not None:
        log.info("Recent days: %d", cfg.recent_days)
    if cfg.dry_run:
        log.info("*** MODO DRY-RUN — no se guardará ningún fichero ***")

    session = build_session(cfg)
    run_date = datetime.now().strftime("%Y%m%d")

    all_dfs: List[pd.DataFrame] = []
    summary: List[Dict[str, Any]] = []

    for category, queries in selected.items():
        df = process_category(
            category=category,
            queries=queries,
            session=session,
            cfg=cfg,
            run_date=run_date,
        )
        n = len(df) if df is not None else 0
        summary.append({"category": category, "records": n})
        if df is not None and not df.empty:
            all_dfs.append(df)

    # CSV global combinado
    if all_dfs and not cfg.dry_run:
        combined = pd.concat(all_dfs, ignore_index=True)
        combined_path = cfg.out_dir / f"scopus_ALL_{run_date}.csv"
        combined.to_csv(combined_path, index=False, encoding="utf-8-sig")
        log.info("CSV global: %s (%d filas)", combined_path, len(combined))

    # Resumen final
    log.info("")
    log.info("══════════════════════════════════════════")
    log.info("RESUMEN FINAL")
    log.info("══════════════════════════════════════════")
    total = 0
    for row in summary:
        log.info("  %-42s %4d artículos", row["category"], row["records"])
        total += row["records"]
    log.info("  %-42s %4d", "TOTAL", total)

    if not cfg.dry_run:
        log.info("")
        log.info("Directorio CSV: %s", cfg.out_dir)
        log.info("Siguiente paso:")
        log.info(
            "  python 3a_download_pdfs.py --csv %s/scopus_<categoria>_%s.csv",
            cfg.out_dir, run_date,
        )


if __name__ == "__main__":
    main()
