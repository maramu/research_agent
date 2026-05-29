# -*- coding: utf-8 -*-
"""
3a_download_pdfs.py — Paso 3a del pipeline research_agent

Descarga PDFs académicos desde un CSV de cribado usando múltiples fuentes:
  1) Semantic Scholar (OA, sin clave)
  2) Unpaywall
  3) Elsevier TDM API (requiere ELSEVIER_API_KEY en config/.env)
  4) DOI content negotiation / redirección
  5) Scraping de la página del publisher (Elsevier, Wiley, MDPI)

Cada PDF descargado se valida con PyMuPDF: se rechaza si tiene menos de
min_pdf_pages páginas o menos de min_pdf_words palabras extraíbles.

Posición en el pipeline:
  1_rename+doi_manual.xlsx  →  2_screen_keywords.py  →  3a_download_pdfs.py  →  inbox/

Uso legítimo:
  - artículos open access
  - artículos accesibles por IP institucional (red UCA / VPN UCA)

Configuración en config/.env (o .env local):
  UNPAYWALL_EMAIL=tu_email@uca.es
  ELSEVIER_API_KEY=xxxx   (opcional, obtener gratis en dev.elsevier.com)
  HTTP_PROXY=http://proxy.uca.es:3128   (opcional)
  HTTPS_PROXY=http://proxy.uca.es:3128  (opcional)

Caché: /Volumes/research/metadatos/descarga_cache.json  (compartida entre lotes)
  Guarda resultados por DOI para reanudar sin repetir descargas ya completadas.
  Si el PDF guardado en caché ya no existe en disco, se reintenta la descarga.
  Las entradas expiran tras cache_max_age_days.

Requiere NAS montado en /Volumes/research antes de ejecutar.

Estructura NAS relevante:
  /Volumes/research/
  ├── inbox/          ← PDFs descargados (plano o en subcarpeta --phase)
  └── metadatos/      ← caché, resultados XLSX/CSV, HTML de pendientes

Logs:
  /Volumes/Disco/proyectos/research_agent/logs/

Ejemplos de uso:
  # a) dry-run con fase concreta
  python 3a_download_pdfs.py --csv /Volumes/research/metadatos/cribado_phase1A.csv --dry-run

  # b) prueba con 10 artículos
  python 3a_download_pdfs.py --csv cribado_phase1A.csv --max 10

  # c) ejecución completa con phase (PDFs en inbox/phase1A/)
  python 3a_download_pdfs.py --csv cribado_phase1A.csv --phase phase1A

  # d) ejecución completa con rutas explícitas
  python 3a_download_pdfs.py \\
    --csv /Volumes/research/metadatos/cribado_phase1B.csv \\
    --out-dir /Volumes/research/inbox/phase1B \\
    --cache /Volumes/research/metadatos/descarga_cache.json \\
    --log /Volumes/Disco/proyectos/research_agent/logs/3a_download_phase1B.log \\
    --report /Volumes/research/metadatos/resultado_descarga_phase1B.xlsx \\
    --report-csv /Volumes/research/metadatos/resultado_descarga_phase1B.csv \\
    --pending-html /Volumes/research/metadatos/pendientes_manual_phase1B.html \\
    --pending-csv /Volumes/research/metadatos/pendientes_manual_phase1B.csv

  # e) timeout por artículo ajustado
  python 3a_download_pdfs.py --csv archivo.csv --max-seconds-per-article 45

  # f) saltar artículos concretos por índice 1-based
  python 3a_download_pdfs.py --csv archivo.csv --skip-rows 15,181,190-195

Ficheros leídos:
    <csv>                                                ← CSV con columnas DOI, Title, etc.
    /Volumes/research/metadatos/descarga_cache.json      ← caché de descargas previas
    config/.env                                          ← claves y proxies

Ficheros escritos:
    <out-dir>/*.pdf                                      ← PDFs descargados y validados
    /Volumes/research/metadatos/descarga_cache.json      ← actualizado con cada descarga
    /Volumes/research/metadatos/pendientes_descarga.csv  ← DOIs fallidos acumulados
    <report>.xlsx / <report>.csv                         ← informe de resultados
    logs/3a_download_<timestamp>.log

Parámetros CLI clave:
    --csv PATH            CSV de entrada con DOIs (obligatorio)
    --out-dir DIR         Carpeta destino de los PDFs
    --phase PHASE         Subcarpeta dentro de inbox/ (alternativa a --out-dir)
    --category CAT        Categoría para registrar en pendientes_descarga.csv
    --cache PATH          Ruta de la caché JSON
    --max N               Descarga solo los primeros N artículos
    --dry-run             Simula sin descargar ni escribir
    --force               Ignora la caché y reintenta todo
    --min-pages N         Mínimo de páginas para aceptar un PDF (defecto: 3)
    --min-words N         Mínimo de palabras extraíbles (defecto: 200)
    --report PATH         Ruta del XLSX de informe
    --report-csv PATH     Ruta del CSV de informe

Variables de entorno (config/.env):
    UNPAYWALL_EMAIL       Email para la API Unpaywall (obligatorio para Unpaywall)
    ELSEVIER_API_KEY      Clave Elsevier TDM API (opcional)
    HTTP_PROXY            Proxy HTTP (opcional, para red UCA)
    HTTPS_PROXY           Proxy HTTPS (opcional, para red UCA)

Dependencias:
    pymupdf (fitz), requests, pandas, openpyxl, python-dotenv

Notas:
    - Las descargas Elsevier requieren VPN UCA activa (autenticación por IP).
    - La caché expira tras cache_max_age_days días; si el PDF en caché no existe
      en disco se reintenta automáticamente.

"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import re
import signal
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from html import escape as html_escape
from urllib.parse import urljoin
from urllib3.util.retry import Retry

_DOTENV_PATH = Path(__file__).parent.parent / "config" / ".env"
load_dotenv(_DOTENV_PATH)  # config/.env (nivel de proyecto)
load_dotenv()              # fallback: .env local o variables de entorno ya establecidas

try:
    import tls_client as _tls_client_mod
    _HAS_TLS_CLIENT = True
except ImportError:
    _HAS_TLS_CLIENT = False

try:
    import fitz
    _HAS_PYMUPDF = True
except ImportError:
    _HAS_PYMUPDF = False

try:
    sys.path.insert(0, str(Path(__file__).parent))
    from utils.download_registry import upsert as _registry_upsert, mark_downloaded as _registry_mark_downloaded
    _HAS_REGISTRY = True
except Exception:
    _HAS_REGISTRY = False

# ---------------------------------------------------------------------------
# NAS — raíz y estructura esperada
# ---------------------------------------------------------------------------

NAS_ROOT = Path("/Volumes/research")

# Subcarpetas que se crean automáticamente si el NAS está montado
_NAS_SUBDIRS = [
    NAS_ROOT / "inbox",
    NAS_ROOT / "inbox_csv",
    NAS_ROOT / "metadatos",
    Path("/Volumes/Disco/proyectos/research_agent/logs"),
]


def check_nas_mounted() -> None:
    """Aborta con mensaje claro si /Volumes/research no está accesible."""
    if not NAS_ROOT.exists():
        sys.exit(
            f"\nError: el NAS no está montado en {NAS_ROOT}\n"
            "Monta la unidad antes de ejecutar este script:\n"
            "  - Abre el Finder → Red → Synology → research, o\n"
            "  - usa: open smb://synology/research\n"
        )


def ensure_nas_structure() -> None:
    """Crea las subcarpetas del NAS si no existen. Solo actúa si NAS_ROOT ya está montado."""
    created = []
    for d in _NAS_SUBDIRS:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d))
    if created:
        log.info("Subcarpetas creadas en NAS: %s", ", ".join(created))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(log_file: Optional[Path] = None) -> None:
    logger = logging.getLogger("descarga")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
        logger.addHandler(fh)


log = logging.getLogger("descarga")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

@dataclass
class Config:
    csv_file: str = str(NAS_ROOT / "inbox_csv" / "scopus_results.csv")
    output_dir: Path = field(default_factory=lambda: NAS_ROOT / "inbox")
    results_xlsx: str = str(NAS_ROOT / "metadatos" / "descarga_results.xlsx")
    results_csv: str  = str(NAS_ROOT / "metadatos" / "descarga_results.csv")
    log_file: Path = field(default_factory=lambda: Path("/Volumes/Disco/proyectos/research_agent/logs") / "3a_download_pdfs.log")
    cache_file: str = str(NAS_ROOT / "metadatos" / "descarga_cache.json")
    cache_max_age_days: int = 30  # 0 = sin expiración
    # Pendientes manuales: HTML navegable + CSV plano, ambos en metadatos/
    pending_html: str = str(NAS_ROOT / "metadatos" / "pendientes_manual.html")
    pending_csv: str  = str(NAS_ROOT / "metadatos" / "pendientes_manual.csv")

    unpaywall_email: str = field(default_factory=lambda: os.getenv("UNPAYWALL_EMAIL", ""))
    elsevier_api_key: str = field(default_factory=lambda: os.getenv("ELSEVIER_API_KEY", ""))

    sleep_between_requests: float = 1.0
    timeout: Tuple[int, int] = (10, 20)
    max_articles: Optional[int] = None
    max_seconds_per_article: int = 75
    skip_rows: set = field(default_factory=set)  # índices 1-based a saltar
    min_pdf_pages: int = 3
    min_pdf_words: int = 800
    keep_suspect_pdfs: bool = False

    dry_run: bool = False
    category: str = ""
    use_cache: bool = True
    no_elsevier_api: bool = False

    http_proxy: str = field(default_factory=lambda: os.getenv("HTTP_PROXY", ""))
    https_proxy: str = field(default_factory=lambda: os.getenv("HTTPS_PROXY", ""))


# ---------------------------------------------------------------------------
# Tipos y constantes
# ---------------------------------------------------------------------------

class DownloadStatus(str, Enum):
    DOWNLOADED    = "descargado"
    ALREADY_EXISTS = "ya existía"
    NOT_DOWNLOADED = "no descargado"
    NO_DOI        = "sin DOI"
    ERROR         = "error"
    DRY_RUN       = "dry-run"


DONE_STATUSES = {DownloadStatus.DOWNLOADED, DownloadStatus.ALREADY_EXISTS}

# DOI válido: prefijo 10. + 4-9 dígitos de registrante + sufijo no vacío
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")

DownloadResult = Dict[str, Any]
PublisherHandler = Callable[[str, Path, "Config"], Tuple[bool, str, Optional[str]]]


# ---------------------------------------------------------------------------
# Sesión HTTP
# ---------------------------------------------------------------------------

_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    if _session is None:
        raise RuntimeError("Sesión HTTP no inicializada.")
    return _session


def build_session(cfg: Config) -> requests.Session:
    global _session
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=2,  # esperas: 2 s, 4 s, 8 s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    })
    proxies = {}
    if cfg.http_proxy:
        proxies["http"] = cfg.http_proxy
    if cfg.https_proxy:
        proxies["https"] = cfg.https_proxy
    if proxies:
        session.proxies.update(proxies)
        log.info("Proxy configurado: %s", proxies)
    _session = session
    return session


def safe_request(method: str, url: str, cfg: Config, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", cfg.timeout)
    return get_session().request(method, url, **kwargs)


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    total: int = 0
    from_cache: int = 0
    downloaded: int = 0
    already_exists: int = 0
    failed: int = 0
    no_doi: int = 0
    by_method: Dict[str, int] = field(default_factory=dict)

    def record(self, res: DownloadResult) -> None:
        status = res.get("status", "")
        method = res.get("method", "")
        if status == DownloadStatus.DOWNLOADED:
            self.downloaded += 1
            self.by_method[method] = self.by_method.get(method, 0) + 1
        elif status == DownloadStatus.ALREADY_EXISTS:
            self.already_exists += 1
        elif status == DownloadStatus.NO_DOI:
            self.no_doi += 1
        else:
            self.failed += 1

    def summary(self) -> str:
        lines = [
            f"Total:          {self.total}",
            f"Descargados:    {self.downloaded}",
            f"Ya existían:    {self.already_exists}",
            f"Desde caché:    {self.from_cache}",
            f"Sin DOI:        {self.no_doi}",
            f"Fallidos:       {self.failed}",
        ]
        if self.by_method:
            lines.append("Por método:")
            for m, n in sorted(self.by_method.items(), key=lambda x: -x[1]):
                lines.append(f"  {m}: {n}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def clean_text(x: Any) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def clean_filename(text: str, max_len: int = 160) -> str:
    text = unicodedata.normalize("NFC", text)
    # Caracteres de control, caracteres no permitidos en rutas y path traversal
    text = re.sub(r'[\x00-\x1f\x7f\\/*?:"<>|]', "", text)
    text = text.replace("..", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len].rstrip(" .")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_skip_rows(value: str) -> set:
    """Convierte una cadena de índices/rangos 1-based separados por comas en un set de enteros.

    Ejemplos:
      "15,181"       → {15, 181}
      "15,181,190-195" → {15, 181, 190, 191, 192, 193, 194, 195}
    """
    result: set = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            parts = token.split("-", 1)
            try:
                start, end = int(parts[0].strip()), int(parts[1].strip())
                result.update(range(start, end + 1))
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"Rango inválido en --skip-rows: '{token}'. Formato esperado: N-M"
                )
        else:
            try:
                result.add(int(token))
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"Valor inválido en --skip-rows: '{token}'. Se esperan enteros."
                )
    return result


def detect_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    norm = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in norm:
            return norm[cand.lower()]
    for c in df.columns:
        cl = c.lower().strip()
        for cand in candidates:
            if cand.lower() in cl:
                return c
    return None


def first_author(authors: str) -> str:
    if not authors:
        return "Autor"
    parts = authors.split(";")[0].strip()
    parts = re.sub(r"\s+", " ", parts)
    return clean_filename(parts.replace(",", ""))[:40] or "Autor"


def normalize_doi(doi: Any) -> str:
    if not isinstance(doi, str) or not doi.strip():
        return ""
    doi = doi.strip()
    for prefix in (
        "https://doi.org/", "http://doi.org/",
        "https://dx.doi.org/", "http://dx.doi.org/",
    ):
        doi = doi.replace(prefix, "")
    doi = doi.strip()
    return doi if DOI_PATTERN.match(doi) else ""


def sanitize_doi_for_filename(doi: str) -> str:
    """Convierte un DOI en cadena válida para nombres de archivo.
    Sustituye '/' por '_' y elimina caracteres no permitidos en rutas.
    Ejemplo: '10.1016/j.jhazmat.2025.123456' → '10.1016_j.jhazmat.2025.123456'
    """
    doi = doi.replace("/", "_")
    doi = re.sub(r'[\x00-\x1f\x7f\\*?:"<>|]', "", doi)
    return doi.strip(" .")


def is_pdf_bytes(data: bytes) -> bool:
    return data[:4] == b"%PDF"


def extract_pii(url: str) -> Optional[str]:
    m = re.search(r"/pii/([A-Z0-9]{17,18})", url, re.IGNORECASE)
    return m.group(1).upper() if m else None


def detect_publisher(url: str) -> str:
    u = url.lower()
    if "sciencedirect.com" in u or "elsevier.com" in u:
        return "elsevier"
    if "link.springer.com" in u or "springer.com" in u:
        return "springer"
    if "onlinelibrary.wiley.com" in u or "wiley.com" in u:
        return "wiley"
    if "tandfonline.com" in u:
        return "taylor_francis"
    if "mdpi.com" in u:
        return "mdpi"
    return "unknown"


def is_pdf_response(resp: requests.Response) -> bool:
    ctype = resp.headers.get("Content-Type", "").lower()
    dispo = resp.headers.get("Content-Disposition", "").lower()
    if "application/pdf" in ctype:
        return True
    if "pdf" in dispo:
        return True
    # Solo confiar en la URL si termina en .pdf, no en /pdf-viewer u otros falsos positivos
    if re.search(r"\.pdf($|\?|#)", resp.url.lower()):
        return True
    return False


def save_response_pdf(resp: requests.Response, filepath: Path) -> bool:
    """Guarda la respuesta en disco validando magic bytes. Devuelve False si no es PDF real."""
    chunks: List[bytes] = []
    first = True
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        if first:
            if not is_pdf_bytes(chunk):
                return False
            first = False
        chunks.append(chunk)
    if not chunks:
        return False
    with open(filepath, "wb") as f:
        for chunk in chunks:
            f.write(chunk)
    return True


def pdf_text_stats(filepath: Path) -> Tuple[int, int, str]:
    """Devuelve (paginas, palabras_extraibles, error)."""
    if not _HAS_PYMUPDF:
        return 0, 0, "PyMuPDF no instalado"
    try:
        with fitz.open(filepath) as doc:
            words = 0
            for page in doc:
                words += len(page.get_text("text").split())
            return doc.page_count, words, ""
    except Exception as e:
        return 0, 0, str(e)


def validate_downloaded_pdf(filepath: Path, cfg: Config) -> Tuple[bool, str]:
    """
    Evita marcar como OK PDFs que son solo portada, preview, suplemento o
    primera pagina. Son PDFs validos, pero no sirven para GROBID/Markdown.
    """
    if not filepath.exists():
        return False, "archivo no existe tras descarga"
    pages, words, err = pdf_text_stats(filepath)
    if err:
        return False, f"PDF no validable ({err})"
    if pages < cfg.min_pdf_pages:
        return False, (
            f"PDF sospechoso: {pages} paginas y {words} palabras "
            f"(min {cfg.min_pdf_pages} paginas)"
        )
    if words < cfg.min_pdf_words:
        return False, (
            f"PDF sospechoso: {pages} paginas y {words} palabras "
            f"(min {cfg.min_pdf_words} palabras extraibles)"
        )
    return True, f"PDF validado: {pages} paginas, {words} palabras"


def reject_suspect_pdf(filepath: Path, cfg: Config) -> None:
    if cfg.keep_suspect_pdfs:
        return
    try:
        filepath.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Publisher-specific handlers
# ---------------------------------------------------------------------------

def try_elsevier_sd_pdf(
    landing_url: str, filepath: Path, cfg: Config
) -> Tuple[bool, str, Optional[str]]:
    """
    Descarga PDF de ScienceDirect via acceso institucional por IP.

    Nota importante: ScienceDirect suele bloquear las rutas /pdf y /pdfft
    si la sesión HTTP no tiene una cookie institucional válida. Abrir el
    enlace en el navegador puede funcionar porque el navegador sí conserva
    la autenticación SSO/VPN, pero requests no puede reutilizarla por sí solo.

    Flujo:
    1. Visita landing para establecer cookies de sesión.
    2. Prueba rutas de descarga conocidas con headers de navegador.
    3. Si la respuesta es PDF directo → guarda.
    4. Si la respuesta es HTML (visor embebido) → extrae el enlace PDF real
       del HTML y lo descarga.
    """
    pii = extract_pii(landing_url)
    if not pii:
        return False, "PII no encontrada en la URL", None

    try:
        safe_request(
            "GET", landing_url, cfg,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
        )
    except Exception:
        pass

    base = f"https://www.sciencedirect.com/science/article/pii/{pii}"
    pdf_candidates = [
        f"{base}/pdfft?isDTMRedir=true&download=true",
        f"{base}/pdf",
        f"{base}/pdf?download=true",
    ]

    saw_403 = False

    for pdf_url in pdf_candidates:
        try:
            resp = safe_request(
                "GET", pdf_url, cfg,
                headers={
                    "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
                    "Referer": landing_url,
                    "Origin": "https://www.sciencedirect.com",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin",
                },
                allow_redirects=True,
                stream=True,
            )
            ct = resp.headers.get("Content-Type", "?")
            final_url = resp.url
            log.debug("[SD] HTTP %s | %s | %s", resp.status_code, ct[:50], final_url[:80])

            if resp.status_code == 403:
                saw_403 = True
                resp.close()
                continue

            if not resp.ok:
                resp.close()
                continue

            if save_response_pdf(resp, filepath):
                return True, "OK (directo)", final_url

            try:
                html_resp = safe_request(
                    "GET", final_url, cfg,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        "Referer": landing_url,
                    },
                    allow_redirects=True,
                )
                html_ct = html_resp.headers.get("Content-Type", "")
                if html_resp.ok and "html" in html_ct.lower():
                    pdf_link = extract_pdf_link_from_html(html_resp.text, final_url)
                    if pdf_link:
                        log.debug("[SD→HTML] Enlace PDF: %s", pdf_link[:80])
                        ok, msg, url2 = download_pdf_from_url(pdf_link, filepath, cfg, referer=final_url)
                        if ok:
                            return True, "OK (via HTML)", url2
                        log.debug("[SD→HTML] Fallo: %s", msg)
                    else:
                        log.debug("[SD→HTML] No se encontró enlace PDF en el visor")
                elif html_resp.ok and "pdf" in html_ct.lower():
                    if save_response_pdf(html_resp, filepath):
                        return True, "OK (re-request)", html_resp.url
            except Exception as e2:
                log.debug("[SD→HTML] Error: %s", e2)

        except Exception as e:
            log.debug("[SD] Error: %s", e)

    if saw_403:
        return (
            False,
            "ScienceDirect devuelve HTTP 403: falta sesión institucional válida o acceso por Elsevier API",
            landing_url,
        )
    return False, "Ninguna ruta PDF de ScienceDirect tuvo éxito", None


def try_wiley_pdf(
    landing_url: str, filepath: Path, cfg: Config
) -> Tuple[bool, str, Optional[str]]:
    """
    Descarga PDF de Wiley Online Library via acceso institucional por IP.

    Flujo:
    1. Visita landing para establecer cookies de sesión.
    2. Prueba pdfdirect (descarga directa, la más fiable con IP institucional).
    3. Fallback a /doi/pdf/ (puede devolver visor HTML).
    4. Si HTML → extrae enlace PDF del visor y descarga.
    """
    m = re.search(r"/doi/(?:abs/|full/|epdf/|pdf/|pdfdirect/)?(10\.\S+)", landing_url)
    if not m:
        return False, "DOI no encontrado en la URL de Wiley", None
    doi = m.group(1).rstrip("/")

    try:
        safe_request(
            "GET", landing_url, cfg,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
        )
    except Exception:
        pass

    base = "https://onlinelibrary.wiley.com/doi"
    pdf_candidates = [
        f"{base}/pdfdirect/{doi}",   # descarga directa sin visor
        f"{base}/epdf/{doi}",        # visor embebido — iframe con el PDF real
        f"{base}/pdf/{doi}",         # visor clásico
    ]

    saw_403 = False

    for pdf_url in pdf_candidates:
        try:
            resp = safe_request(
                "GET", pdf_url, cfg,
                headers={
                    "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
                    "Referer": landing_url,
                    "Origin": "https://onlinelibrary.wiley.com",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin",
                },
                allow_redirects=True,
                stream=True,
            )
            ct = resp.headers.get("Content-Type", "?")
            final_url = resp.url
            log.debug("[Wiley] HTTP %s | %s | %s", resp.status_code, ct[:50], final_url[:80])

            if resp.status_code == 403:
                saw_403 = True
                resp.close()
                continue

            if not resp.ok:
                resp.close()
                continue

            if save_response_pdf(resp, filepath):
                return True, "OK (directo)", final_url

            try:
                html_resp = safe_request(
                    "GET", final_url, cfg,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        "Referer": landing_url,
                    },
                    allow_redirects=True,
                )
                html_ct = html_resp.headers.get("Content-Type", "")
                if html_resp.ok and "html" in html_ct.lower():
                    pdf_link = extract_pdf_link_from_html(html_resp.text, final_url)
                    if pdf_link:
                        log.debug("[Wiley→HTML] Enlace PDF: %s", pdf_link[:80])
                        ok, msg, url2 = download_pdf_from_url(pdf_link, filepath, cfg, referer=final_url)
                        if ok:
                            return True, "OK (via HTML)", url2
                        log.debug("[Wiley→HTML] Fallo: %s", msg)
                    else:
                        log.debug("[Wiley→HTML] No se encontró enlace PDF en el visor")
                elif html_resp.ok and "pdf" in html_ct.lower():
                    if save_response_pdf(html_resp, filepath):
                        return True, "OK (re-request)", html_resp.url
            except Exception as e2:
                log.debug("[Wiley→HTML] Error: %s", e2)

        except Exception as e:
            log.debug("[Wiley] Error: %s", e)

    if saw_403:
        return (
            False,
            "Wiley devuelve HTTP 403: falta sesión institucional o artículo fuera de suscripción UCA",
            landing_url,
        )
    return False, "Ninguna ruta PDF de Wiley tuvo éxito", None


def try_mdpi_pdf(
    landing_url: str, filepath: Path, cfg: Config
) -> Tuple[bool, str, Optional[str]]:
    """
    Descarga PDF de MDPI añadiendo /pdf al final de la URL del artículo.
    MDPI usa Akamai bot-protection que bloquea el fingerprint TLS de requests/OpenSSL.
    Requiere `pip install tls-client` para suplantar el fingerprint TLS de Chrome.
    Sin tls-client esta fuente siempre devuelve 403.
    """
    if not _HAS_TLS_CLIENT:
        return False, "MDPI bloqueado por Akamai (instala tls-client: pip install tls-client)", None

    base = landing_url.split("?")[0].split("#")[0].rstrip("/")
    pdf_url = base if base.endswith("/pdf") else f"{base}/pdf"

    try:
        session = _tls_client_mod.Session(
            client_identifier="chrome_120",
            random_tls_extension_order=True,
        )
        resp = session.get(
            pdf_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,text/html,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Referer": landing_url,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        log.debug("[MDPI] HTTP %s | %s | %s",
                  resp.status_code,
                  resp.headers.get("Content-Type", "?")[:50],
                  pdf_url[:80])

        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}", pdf_url

        content = resp.content
        if not is_pdf_bytes(content):
            return False, "Respuesta no es PDF válido (magic bytes)", pdf_url

        filepath.write_bytes(content)
        return True, "OK (tls-client)", pdf_url

    except Exception as e:
        return False, str(e), None


# Registro de handlers por publisher — añade nuevos publishers aquí
PUBLISHER_PDF_HANDLERS: Dict[str, PublisherHandler] = {
    "elsevier": try_elsevier_sd_pdf,
    "wiley": try_wiley_pdf,
    "mdpi": try_mdpi_pdf,
    # "springer": try_springer_pdf,
}


# ---------------------------------------------------------------------------
# Caché (resume entre ejecuciones)
# ---------------------------------------------------------------------------

def load_cache(cfg: Config) -> Dict[str, Any]:
    if not cfg.use_cache:
        return {}
    p = Path(cfg.cache_file)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: Dict[str, Any], cfg: Config) -> None:
    with open(cfg.cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def is_cache_entry_valid(entry: Dict[str, Any], max_age_days: int) -> bool:
    if max_age_days == 0:
        return True
    cached_at = entry.get("cached_at")
    if not cached_at:
        return True  # Entradas antiguas sin timestamp: considerar válidas
    try:
        dt = datetime.fromisoformat(cached_at)
        return datetime.now() - dt < timedelta(days=max_age_days)
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------

def get_semantic_scholar_pdf_url(doi: str, cfg: Config) -> Optional[str]:
    """API gratuita, sin clave. Muy fiable para artículos OA (MDPI, arXiv, etc.)."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    try:
        resp = safe_request("GET", url, cfg, params={"fields": "openAccessPdf"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        oa = data.get("openAccessPdf") or {}
        return oa.get("url")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Elsevier TDM API
# ---------------------------------------------------------------------------

def try_elsevier_api(doi: str, filepath: Path, cfg: Config) -> Tuple[bool, str, Optional[str]]:
    """
    Usa la API de Text & Data Mining de Elsevier.
    Requiere ELSEVIER_API_KEY (gratuita en dev.elsevier.com).
    Funciona para artículos Elsevier/ScienceDirect con acceso institucional.
    """
    if not cfg.elsevier_api_key:
        return False, "Sin ELSEVIER_API_KEY en .env", None
    url = f"https://api.elsevier.com/content/article/doi/{doi}"
    try:
        resp = safe_request(
            "GET", url, cfg,
            headers={
                "X-ELS-APIKey": cfg.elsevier_api_key,
                "Accept": "application/pdf",
                "X-ELS-ResourceVersion": "version=VOR",
            },
            allow_redirects=True,
            stream=True,
        )
        if not resp.ok:
            return False, f"HTTP {resp.status_code}", resp.url
        if save_response_pdf(resp, filepath):
            return True, "OK", resp.url
        return False, "Contenido no es PDF válido", resp.url
    except Exception as e:
        return False, str(e), None


# ---------------------------------------------------------------------------
# Unpaywall
# ---------------------------------------------------------------------------

def get_unpaywall_pdf_url(doi: str, cfg: Config) -> Optional[str]:
    url = f"https://api.unpaywall.org/v2/{doi}"
    resp = safe_request("GET", url, cfg, params={"email": cfg.unpaywall_email})
    if resp.status_code != 200:
        return None
    data = resp.json()
    best = data.get("best_oa_location") or {}
    return best.get("url_for_pdf") or best.get("url")


# ---------------------------------------------------------------------------
# DOI → PDF directo
# ---------------------------------------------------------------------------

def try_doi_as_pdf(doi: str, cfg: Config) -> Tuple[Optional[requests.Response], Optional[str]]:
    doi_url = f"https://doi.org/{doi}"
    try:
        resp = safe_request(
            "GET", doi_url, cfg,
            headers={"Accept": "application/pdf"},
            allow_redirects=True,
            stream=True,
        )
        if resp.ok and is_pdf_response(resp):
            return resp, resp.url
        return None, resp.url
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Landing page → PDF
# ---------------------------------------------------------------------------

PDF_PATTERNS = [
    r"/pdf",
    r"\.pdf($|\?)",
    r"/pdfdirect",
    r"/articlepdf",
    r"/content/pdf/",
    r"/fullpdf",
    r"/download/pdf",
    r"/pdfft",           # ScienceDirect
    r"isDTMRedir",       # ScienceDirect direct-to-media
]


def score_pdf_link(href: str, text: str) -> int:
    href_l = href.lower()
    text_l = text.lower()
    score = 0
    if any(re.search(p, href_l) for p in PDF_PATTERNS):
        score += 10
    if "pdfft" in href_l or "istdmredir" in href_l:
        score += 8
    if "pdf" in text_l:
        score += 5
    if "download" in text_l:
        score += 2
    if "full text pdf" in text_l:
        score += 4
    if href_l.startswith("javascript:"):
        score -= 5
    return score


def extract_pdf_link_from_html(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    is_mdpi = "mdpi.com" in base_url.lower()

    # 1) Meta tags — estándar de publishers académicos
    for attrs in [
        {"name": "citation_pdf_url"},
        {"property": "citation_pdf_url"},
        {"name": "dc.identifier"},
        {"name": "DC.Identifier"},
    ]:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            content = tag["content"].strip()
            # MDPI añade ?v=timestamp que puede romper la descarga directa
            if is_mdpi:
                content = content.split("?")[0]
            if ".pdf" in content.lower() or "/pdf" in content.lower():
                return urljoin(base_url, content)

    # 2) iframe/embed — Wiley epdf y otros visores embebidos
    for tag in soup.find_all(["iframe", "embed"], src=True):
        src = tag["src"].strip()
        full = urljoin(base_url, src)
        if any(re.search(p, full.lower()) for p in PDF_PATTERNS) or "pdf" in full.lower():
            return full

    # 2b) Botones específicos de MDPI — clases CSS y textos característicos
    if is_mdpi:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(" ", strip=True).lower()
            class_str = " ".join(a.get("class", [])).lower()
            full = urljoin(base_url, href)
            full_l = full.lower()
            if not (".pdf" in full_l or "/pdf" in full_l):
                continue
            if any(c in class_str for c in ("pdf", "download", "btn-pdf", "ful-text")):
                return full
            if any(t in text for t in ("download pdf", "pdf download", "full-text pdf", "pdf version")):
                return full

    # 3) Links <a> con scoring
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        full = urljoin(base_url, href)
        sc = score_pdf_link(full, text)
        if sc > 0:
            candidates.append((sc, full))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def get_landing_page_from_doi(doi: str, cfg: Config) -> Tuple[Optional[str], Optional[str]]:
    doi_url = f"https://doi.org/{doi}"
    try:
        resp = safe_request("GET", doi_url, cfg, allow_redirects=True)
        if resp.ok:
            return resp.text, resp.url
        return None, resp.url
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def download_pdf_from_url(
    url: str, filepath: Path, cfg: Config, referer: str = ""
) -> Tuple[bool, str, Optional[str]]:
    try:
        extra_headers = {"Referer": referer} if referer else {}
        resp = safe_request("GET", url, cfg, headers=extra_headers, allow_redirects=True, stream=True)
        final_url = resp.url

        if not resp.ok:
            return False, f"HTTP {resp.status_code}", final_url

        if is_pdf_response(resp):
            if not save_response_pdf(resp, filepath):
                return False, "Cabeceras indican PDF pero el contenido no lo es", final_url
            return True, "OK", final_url

        ctype = resp.headers.get("Content-Type", "").lower()
        if "html" in ctype:
            pdf_link = extract_pdf_link_from_html(resp.text, final_url)
            if pdf_link:
                resp2 = safe_request("GET", pdf_link, cfg, allow_redirects=True, stream=True)
                final_url2 = resp2.url
                if resp2.ok and is_pdf_response(resp2):
                    if not save_response_pdf(resp2, filepath):
                        return False, "Enlace localizado pero contenido no es PDF", final_url2
                    return True, "OK", final_url2
                return False, f"Enlace localizado pero no descargable (HTTP {resp2.status_code})", final_url2

        return False, f"No parece PDF (Content-Type: {ctype})", final_url

    except Exception as e:
        return False, str(e), None


# ---------------------------------------------------------------------------
# Lógica principal por artículo
# ---------------------------------------------------------------------------

def build_output_filename(year: str, authors: str, title: str, doi: str = "") -> str:
    """Genera el nombre de archivo del PDF con el formato:
       YYYY - PrimerAutor - TituloCorto [DOI_sanitizado].pdf

    Si el nombre excede MAX_TOTAL chars se recorta TituloCorto, nunca el año, autor ni DOI.
    """
    MAX_TOTAL = 145  # objetivo en caracteres para el stem (sin .pdf)

    year_str = clean_filename(year or "s.f.")
    fa = first_author(authors)
    doi_part = f" [{sanitize_doi_for_filename(doi)}]" if doi else ""

    # Presupuesto para el título = total disponible - partes fijas
    # Estructura: "{year_str} - {fa} - {title}{doi_part}"
    overhead = len(year_str) + 3 + len(fa) + 3 + len(doi_part)
    title_budget = max(MAX_TOTAL - overhead, 10)

    title_clean = clean_filename(title or "Sin_titulo", max_len=title_budget)
    return f"{year_str} - {fa} - {title_clean}{doi_part}.pdf"


def try_download_article(
    doi: str,
    title: str,
    year: str,
    authors: str,
    cfg: Config,
) -> DownloadResult:
    result: DownloadResult = {
        "doi": doi, "title": title, "year": year, "authors": authors,
        "status": "", "method": "", "pdf_url": "", "saved_file": "", "error": "",
        "source_pdf": "auto",  # marca de origen; "manual" se usará en la fase de importación manual
        "pdf_pages": "", "pdf_words": "", "pdf_validation": "",
    }

    # Los PDFs van directamente en output_dir, sin subcarpeta por año
    filename = build_output_filename(year, authors, title, doi)
    filepath = cfg.output_dir / filename

    def finish_download(method: str, pdf_url: str) -> Optional[DownloadResult]:
        ok_pdf, validation_msg = validate_downloaded_pdf(filepath, cfg)
        pages, words, _ = pdf_text_stats(filepath)
        if not ok_pdf:
            reject_suspect_pdf(filepath, cfg)
            errors.append(f"{method}: {validation_msg}")
            return None
        result.update(
            status=DownloadStatus.DOWNLOADED,
            method=method,
            pdf_url=pdf_url,
            saved_file=str(filepath),
            pdf_pages=pages,
            pdf_words=words,
            pdf_validation=validation_msg,
        )
        return result

    if filepath.exists():
        ok_pdf, validation_msg = validate_downloaded_pdf(filepath, cfg)
        pages, words, _ = pdf_text_stats(filepath)
        if ok_pdf:
            result.update(
                status=DownloadStatus.ALREADY_EXISTS,
                method="local",
                saved_file=str(filepath),
                pdf_pages=pages,
                pdf_words=words,
                pdf_validation=validation_msg,
            )
            return result
        reject_suspect_pdf(filepath, cfg)

    if cfg.dry_run:
        result.update(status=DownloadStatus.DRY_RUN, method="", saved_file="")
        return result

    ensure_dir(cfg.output_dir)
    errors: List[str] = []

    # 1) Semantic Scholar — fiable para OA (MDPI, arXiv, PubMed, etc.)
    try:
        ss_url = get_semantic_scholar_pdf_url(doi, cfg)
        if ss_url:
            ok, msg, final_url = download_pdf_from_url(ss_url, filepath, cfg)
            if ok:
                finished = finish_download("semantic_scholar", final_url or ss_url)
                if finished:
                    return finished
            errors.append(f"SemanticScholar: {msg}")
    except Exception as e:
        errors.append(f"SemanticScholar excepción: {e}")

    # 2) Unpaywall
    try:
        pdf_url = get_unpaywall_pdf_url(doi, cfg)
        if pdf_url:
            ok, msg, final_url = download_pdf_from_url(pdf_url, filepath, cfg)
            if ok:
                finished = finish_download("unpaywall", final_url or pdf_url)
                if finished:
                    return finished
            errors.append(f"Unpaywall: {msg}")
    except Exception as e:
        errors.append(f"Unpaywall excepción: {e}")

    # 3) DOI → PDF directo (Accept: application/pdf)
    try:
        resp_pdf, final_url = try_doi_as_pdf(doi, cfg)
        if resp_pdf is not None:
            if save_response_pdf(resp_pdf, filepath):
                finished = finish_download("doi_accept_pdf", final_url or "")
                if finished:
                    return finished
            errors.append("DOI-PDF: contenido no válido")
    except Exception as e:
        errors.append(f"DOI-PDF excepción: {e}")

    # 4) Elsevier TDM API — mejor que scraping cuando hay clave configurada
    if not cfg.no_elsevier_api and (doi.startswith("10.1016/") or doi.startswith("10.1006/")):
        try:
            ok, msg, final_url = try_elsevier_api(doi, filepath, cfg)
            if ok:
                finished = finish_download("elsevier_api", final_url or "")
                if finished:
                    return finished
            errors.append(f"ElsevierAPI: {msg}")
        except Exception as e:
            errors.append(f"ElsevierAPI excepción: {e}")

    # 5) Landing page — scraping genérico + handler específico por publisher
    try:
        html, landing_url = get_landing_page_from_doi(doi, cfg)
        if html and landing_url:
            publisher = detect_publisher(landing_url)

            # 5a) Scraping genérico (meta citation_pdf_url + links con score)
            pdf_link = extract_pdf_link_from_html(html, landing_url)
            if pdf_link:
                ok, msg, final_url = download_pdf_from_url(pdf_link, filepath, cfg)
                if ok:
                    finished = finish_download("landing_page_pdf", final_url or pdf_link)
                    if finished:
                        return finished
                errors.append(f"Landing scraping: {msg}")
            else:
                errors.append(f"Landing page ({publisher}): no se encontró enlace PDF")

            # 5b) Handler específico por publisher (p.ej. ScienceDirect, Wiley)
            handler = PUBLISHER_PDF_HANDLERS.get(publisher)
            if handler:
                ok, msg, final_url = handler(landing_url, filepath, cfg)
                if ok:
                    finished = finish_download(f"{publisher}_specific", final_url or "")
                    if finished:
                        return finished
                errors.append(f"{publisher.capitalize()} específico: {msg}")
        else:
            errors.append("No se pudo resolver la landing page")
    except Exception as e:
        errors.append(f"Landing page excepción: {e}")

    result.update(status=DownloadStatus.NOT_DOWNLOADED, method="ninguno", error=" | ".join(errors))
    return result


# ---------------------------------------------------------------------------
# HTML report para descarga manual
# ---------------------------------------------------------------------------

def save_html_report(pending: pd.DataFrame, filepath: Path) -> None:
    """Genera un HTML con los artículos fallidos y botones DOI clicables."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows: List[str] = []
    for i, row in enumerate(pending.itertuples(index=False), start=1):
        title   = html_escape(str(getattr(row, "title", "") or ""))
        year    = html_escape(str(getattr(row, "year", "") or ""))
        authors = html_escape(str(getattr(row, "authors", "") or ""))
        error   = html_escape(str(getattr(row, "download_error", "") or ""))
        status  = html_escape(str(getattr(row, "download_status", "") or ""))
        doi_url = html_escape(str(getattr(row, "url", "") or ""))
        btn = f'<a class="btn" href="{doi_url}" target="_blank">Abrir</a>' if doi_url else "—"
        rows.append(
            f"    <tr><td>{i}</td>"
            f'<td class="title">{title}</td>'
            f"<td>{year}</td>"
            f'<td class="authors">{authors}</td>'
            f'<td class="status">{status}</td>'
            f'<td class="error">{error}</td>'
            f"<td>{btn}</td></tr>"
        )

    count = len(pending)
    plural = "s" if count != 1 else ""
    body = "\n".join(rows)

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Pendientes descarga manual — {date_str}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; padding: 2rem;
          color: #1a1a1a; max-width: 1400px; margin: auto; }}
  h1   {{ font-size: 1.1rem; margin-bottom: .3rem; }}
  p.meta {{ color: #666; font-size: .85rem; margin-bottom: 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .86rem; }}
  th    {{ background: #2c3e50; color: #fff; padding: 8px 12px;
           text-align: left; white-space: nowrap; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  td    {{ padding: 6px 12px; border-bottom: 1px solid #dde; vertical-align: top; }}
  .title   {{ max-width: 360px; }}
  .authors {{ max-width: 200px; color: #444; }}
  .error   {{ max-width: 280px; color: #c0392b; font-size: .8rem; }}
  a.btn {{ display: inline-block; padding: 3px 12px; background: #2980b9; color: #fff;
           border-radius: 4px; text-decoration: none; font-size: .8rem; white-space: nowrap; }}
  a.btn:hover {{ background: #1f618d; }}
</style>
</head>
<body>
<h1>Artículos pendientes de descarga manual</h1>
<p class="meta">Generado: {date_str} &nbsp;·&nbsp; {count} artículo{plural}</p>
<table>
  <thead>
    <tr><th>#</th><th>Título</th><th>Año</th><th>Autores</th><th>Estado</th><th>Error</th><th>DOI</th></tr>
  </thead>
  <tbody>
{body}
  </tbody>
</table>
</body>
</html>
"""
    filepath.write_text(doc, encoding="utf-8")


# ---------------------------------------------------------------------------
# Download Manager
# ---------------------------------------------------------------------------

class DownloadManager:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.stats = Stats()
        self.cache: Dict[str, Any] = {}
        self._shutdown = False

    def setup(self) -> None:
        setup_logging(self.cfg.log_file)
        build_session(self.cfg)
        ensure_dir(self.cfg.output_dir)
        self.cache = load_cache(self.cfg)
        # Registra en el log las rutas absolutas efectivas usadas en esta ejecución
        log.info("=== Rutas efectivas ===")
        log.info("  CSV entrada    : %s", Path(self.cfg.csv_file).resolve())
        log.info("  PDFs salida    : %s", self.cfg.output_dir.resolve())
        log.info("  Log            : %s", self.cfg.log_file.resolve())
        log.info("  Resultados     : %s", Path(self.cfg.results_xlsx).resolve())
        log.info("  Resultados CSV : %s", Path(self.cfg.results_csv).resolve())
        log.info("  Pendientes HTML: %s", Path(self.cfg.pending_html).resolve())
        log.info("  Pendientes CSV : %s", Path(self.cfg.pending_csv).resolve())
        log.info("  Caché          : %s", Path(self.cfg.cache_file).resolve())
        log.info("======================")

    def register_signals(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        log.warning("Señal %s recibida. Guardando caché y cerrando...", signal.Signals(signum).name)
        self._shutdown = True

    def _is_cached(self, doi: str) -> bool:
        if not doi or doi not in self.cache:
            return False
        entry = self.cache[doi]
        if not is_cache_entry_valid(entry, self.cfg.cache_max_age_days):
            return False
        if entry.get("status") not in DONE_STATUSES:
            return False
        # Si el PDF estaba guardado pero ya no existe en disco → forzar reintento
        saved = entry.get("saved_file", "")
        if saved and not Path(saved).exists():
            return False
        if saved:
            ok_pdf, validation_msg = validate_downloaded_pdf(Path(saved), self.cfg)
            if not ok_pdf:
                log.warning("Caché inválida para %s: %s", doi, validation_msg)
                reject_suspect_pdf(Path(saved), self.cfg)
                return False
        else:
            return False
        return True

    def process_article(
        self, idx: int, total: int, doi: str, title: str, year: str, authors: str
    ) -> DownloadResult:
        if self._is_cached(doi):
            log.info("[%d/%d] CACHÉ ✓  %s | %s", idx, total, doi, title[:60])
            self.stats.from_cache += 1
            cached_res = dict(self.cache[doi])
            cached_res["_from_cache"] = True
            return cached_res

        log.info("[%d/%d] %s | %s", idx, total, doi or "SIN DOI", title[:80])

        if not doi:
            return {
                "doi": "", "title": title, "year": year, "authors": authors,
                "status": DownloadStatus.NO_DOI, "method": "", "pdf_url": "",
                "saved_file": "", "error": "Registro sin DOI", "source_pdf": "",
            }

        limit = self.cfg.max_seconds_per_article
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    try_download_article,
                    doi=doi, title=title, year=year, authors=authors, cfg=self.cfg,
                )
                res = future.result(timeout=limit)
        except concurrent.futures.TimeoutError:
            log.warning(
                "  → TIMEOUT (%d s) para DOI %s — pasando al siguiente artículo", limit, doi
            )
            res = {
                "doi": doi, "title": title, "year": year, "authors": authors,
                "status": DownloadStatus.NOT_DOWNLOADED, "method": "timeout",
                "pdf_url": "", "saved_file": "",
                "error": f"Tiempo máximo por artículo superado ({limit} s)",
                "source_pdf": "",
            }
        except Exception as e:
            log.error("Excepción inesperada para DOI %s: %s", doi, e)
            res = {
                "doi": doi, "title": title, "year": year, "authors": authors,
                "status": DownloadStatus.ERROR, "method": "", "pdf_url": "",
                "saved_file": "", "error": str(e), "source_pdf": "",
            }

        log.info("  → %s via %s", res.get("status", "?"), res.get("method") or "—")

        if res.get("status") in DONE_STATUSES:
            res["cached_at"] = datetime.now().isoformat()
            self.cache[doi] = res
            save_cache(self.cache, self.cfg)

        return res

    def run(self, df: pd.DataFrame) -> Tuple[List[DownloadResult], pd.DataFrame]:
        doi_col     = detect_column(df, ["DOI"])
        title_col   = detect_column(df, ["Title", "Article title", "Document title"])
        year_col    = detect_column(df, ["Year", "Publication Year", "PubYear"])
        authors_col = detect_column(df, ["Authors", "Author Names", "Author(s)"])

        if not doi_col:
            raise ValueError("No se encontró columna DOI en el CSV.")
        if not title_col:
            raise ValueError("No se encontró columna de título en el CSV.")

        log.info(
            "Columnas detectadas: DOI=%s, Title=%s, Year=%s, Authors=%s",
            doi_col, title_col, year_col, authors_col,
        )

        subset = df if self.cfg.max_articles is None else df.head(self.cfg.max_articles)
        total = len(subset)
        self.stats.total = total

        results: List[DownloadResult] = []

        for idx, (_, row) in enumerate(subset.iterrows(), start=1):
            if self._shutdown:
                log.warning("Proceso interrumpido en artículo %d/%d.", idx - 1, total)
                break

            doi     = normalize_doi(clean_text(row.get(doi_col, "")))
            title   = clean_text(row.get(title_col, ""))
            year    = clean_text(row.get(year_col, "")) if year_col else ""
            authors = clean_text(row.get(authors_col, "")) if authors_col else ""

            if idx in self.cfg.skip_rows:
                log.info("[%d/%d] SKIP manual → %s | %s", idx, total, doi or "SIN DOI", title[:80])
                res = {
                    "doi": doi, "title": title, "year": year, "authors": authors,
                    "status": DownloadStatus.NOT_DOWNLOADED, "method": "skipped_by_user",
                    "pdf_url": "", "saved_file": "",
                    "error": "Saltado manualmente por --skip-rows",
                    "source_pdf": "",
                }
                results.append(res)
                self.stats.record(res)
                continue

            res = self.process_article(idx, total, doi, title, year, authors)
            results.append(res)
            self.stats.record(res)

            # Solo omitir la pausa si el resultado venía de caché ANTES de procesar,
            # no si acaba de descargarse y de guardarse en caché ahora.
            skip_sleep = res.get("status") in {
                DownloadStatus.ALREADY_EXISTS,
                DownloadStatus.NO_DOI,
                DownloadStatus.DRY_RUN,
            } or res.get("_from_cache", False)
            if not self._shutdown and not skip_sleep:
                time.sleep(self.cfg.sleep_between_requests)

        return results, subset

    def save_results(self, results: List[DownloadResult], source_df: pd.DataFrame) -> None:
        """Combina las columnas originales del CSV con las columnas de descarga y exporta.

        Preserva todas las columnas del CSV de entrada (topic_primary, doc_class, phase,
        relevance_score, etc.) para que la salida pueda usarse directamente en la fase
        de conversión a Markdown o empaquetado posterior.
        """
        if not results:
            return

        # Alinear source_df con resultados (puede ser más corto si el proceso fue interrumpido)
        aligned = source_df.iloc[: len(results)].reset_index(drop=True)

        # Construir columnas de descarga con prefijo download_
        dl_rows = []
        for res in results:
            dl_rows.append({
                "download_status": res.get("status", ""),
                "download_method": res.get("method", ""),
                "pdf_url":         res.get("pdf_url", ""),
                "saved_file":      res.get("saved_file", ""),
                "download_error":  res.get("error", ""),
                "pdf_pages":       res.get("pdf_pages", ""),
                "pdf_words":       res.get("pdf_words", ""),
                "pdf_validation":  res.get("pdf_validation", ""),
                "source_pdf":      res.get("source_pdf", "auto") or "auto",
                "cached_at":       res.get("cached_at", ""),
            })
        dl_df = pd.DataFrame(dl_rows)

        # DataFrame combinado: columnas originales + columnas de descarga
        out = pd.concat([aligned, dl_df], axis=1)

        # TODO (fase 2 — importación manual):
        #   Escanear /Volumes/research/inbox/manual_import/, emparejar PDFs con DOIs
        #   y añadir filas con source_pdf="manual" al DataFrame antes de exportar.

        # --- Detectar columnas originales para el informe de pendientes ---
        doi_col     = detect_column(aligned, ["DOI"])
        title_col   = detect_column(aligned, ["Title", "Article title", "Document title"])
        year_col    = detect_column(aligned, ["Year", "Publication Year", "PubYear"])
        authors_col = detect_column(aligned, ["Authors", "Author Names", "Author(s)"])

        pending_mask = out["download_status"].isin([
            DownloadStatus.NOT_DOWNLOADED, DownloadStatus.ERROR
        ])
        pend_src = out[pending_mask].reset_index(drop=True)

        def _col(df: pd.DataFrame, col: Optional[str]) -> pd.Series:
            return df[col] if col else pd.Series([""] * len(df))

        pend_report = pd.DataFrame({
            "title":           _col(pend_src, title_col).values,
            "year":            _col(pend_src, year_col).values,
            "authors":         _col(pend_src, authors_col).values,
            "doi":             _col(pend_src, doi_col).values,
            "url":             _col(pend_src, doi_col).apply(
                                   lambda d: f"https://doi.org/{d}"
                                   if pd.notna(d) and str(d).strip() else ""
                               ).values if doi_col else [""] * len(pend_src),
            "download_error":  pend_src["download_error"].values,
            "saved_file":      pend_src["saved_file"].values,
            "download_status": pend_src["download_status"].values,
        })

        # --- Excel (dos hojas) ---
        xlsx_path = Path(self.cfg.results_xlsx)
        xlsx_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(xlsx_path), engine="openpyxl") as writer:
            out.to_excel(writer, sheet_name="Todos", index=False)
            pend_report.to_excel(writer, sheet_name="Pendientes_manual", index=False)
        log.info("Resultados XLSX en %s", xlsx_path.resolve())

        # --- CSV completo de resultados ---
        csv_path = Path(self.cfg.results_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(str(csv_path), index=False, encoding="utf-8-sig")
        log.info("Resultados CSV en %s", csv_path.resolve())

        # --- Pendientes: HTML navegable + CSV plano ---
        if not pend_report.empty:
            html_path = Path(self.cfg.pending_html)
            html_path.parent.mkdir(parents=True, exist_ok=True)
            save_html_report(pend_report, html_path)
            log.info("HTML pendientes en %s", html_path.resolve())

            csv_pend = Path(self.cfg.pending_csv)
            pend_report.to_csv(str(csv_pend), index=False, encoding="utf-8-sig")
            log.info("CSV pendientes en %s", csv_pend.resolve())

        # --- Actualizar registro persistente de pendientes ---
        if _HAS_REGISTRY and not self.cfg.dry_run:
            try:
                pending_rows = pend_report.to_dict("records")
                added = _registry_upsert(pending_rows, category=self.cfg.category)
                log.info("Registro pendientes: %d entradas nuevas añadidas", added)

                # Marcar como descargados los que sí se resolvieron
                downloaded_dois = [
                    r.get("doi", "") for r in results
                    if r.get("status") in DONE_STATUSES and r.get("doi")
                ]
                if downloaded_dois:
                    _registry_mark_downloaded(downloaded_dois)
            except Exception as e:
                log.warning("No se pudo actualizar registro de pendientes: %s", e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    METADATOS_DIR = NAS_ROOT / "metadatos"
    LOGS_DIR = Path("/Volumes/Disco/proyectos/research_agent/logs")
    parser = argparse.ArgumentParser(
        description=(
            "3a_download_pdfs — Paso 3a del pipeline research_agent. "
            "Descarga PDFs académicos desde un CSV de cribado por lotes. "
            f"Requiere NAS montado en {NAS_ROOT}."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # --- Entrada ---
    parser.add_argument(
        "--csv", default=None,
        help="Ruta al CSV de cribado generado por 2_screen_keywords.py",
    )
    parser.add_argument(
        "--max", type=int, default=None,
        help="Limitar a N artículos (útil para pruebas)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simular sin descargar PDFs",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Ignorar caché existente",
    )
    parser.add_argument(
        "--out-dir", default=None,
        help=f"Directorio de salida para los PDFs (por defecto {NAS_ROOT}/inbox/)",
    )
    parser.add_argument(
        "--phase", default=None, metavar="FASE",
        help=(
            "Subfolder dentro de /Volumes/research/inbox/ donde guardar los PDFs. "
            "Ej: --phase phase1A  →  PDFs en /Volumes/research/inbox/phase1A/. "
            "Ignorado si se pasa --out-dir."
        ),
    )
    parser.add_argument(
        "--cache-age", type=int, default=30,
        help="Días máximos para reutilizar entradas de caché (0 = sin límite)",
    )
    parser.add_argument(
        "--max-seconds-per-article", type=int, default=75, metavar="SEG",
        help="Tiempo máximo total por artículo antes de pasar al siguiente (por defecto: 75 s)",
    )
    parser.add_argument(
        "--min-pdf-pages", type=int, default=3, metavar="N",
        help="Mínimo de páginas para aceptar una descarga como full text (por defecto: 3)",
    )
    parser.add_argument(
        "--min-pdf-words", type=int, default=800, metavar="N",
        help="Mínimo de palabras extraíbles para aceptar una descarga como full text (por defecto: 800)",
    )
    parser.add_argument(
        "--keep-suspect-pdfs", action="store_true",
        help="Conservar PDFs sospechosos en disco aunque se marquen como no descargados",
    )
    parser.add_argument(
        "--no-elsevier-api", action="store_true",
        help=(
            "Omitir la Elsevier TDM API (método 4). Útil cuando la API solo devuelve "
            "la primera página del PDF; los artículos Elsevier van directamente a pendientes."
        ),
    )
    parser.add_argument(
        "--skip-rows", default=None, metavar="ÍNDICES",
        help=(
            "Índices 1-based separados por comas (y/o rangos N-M) de artículos a saltar. "
            "Ej: --skip-rows 15,181  o  --skip-rows 15,181,190-195"
        ),
    )
    # --- Rutas de salida (opcionales; si se omiten se derivan del stem del CSV) ---
    parser.add_argument(
        "--report", default=None, metavar="XLSX",
        help=f"Ruta al Excel de resultados (por defecto {METADATOS_DIR}/resultado_descarga_<stem>.xlsx)",
    )
    parser.add_argument(
        "--report-csv", default=None, metavar="CSV",
        help=f"Ruta al CSV de resultados (por defecto {METADATOS_DIR}/resultado_descarga_<stem>.csv)",
    )
    parser.add_argument(
        "--log", default=None, metavar="LOG",
        help=f"Ruta al fichero de log (por defecto {LOGS_DIR}/3a_download_<stem>.log)",
    )
    parser.add_argument(
        "--cache", default=None, metavar="JSON",
        help=f"Ruta al fichero de caché (por defecto {METADATOS_DIR}/descarga_cache.json)",
    )
    parser.add_argument(
        "--pending-html", default=None, metavar="HTML",
        help=f"Ruta al HTML de pendientes (por defecto {METADATOS_DIR}/pendientes_manual_<stem>.html)",
    )
    parser.add_argument(
        "--pending-csv", default=None, metavar="CSV",
        help=f"Ruta al CSV de pendientes (por defecto {METADATOS_DIR}/pendientes_manual_<stem>.csv)",
    )
    parser.add_argument(
        "--category", default="",
        help="Categoría del pipeline (para registro de pendientes)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Verificación temprana: el NAS debe estar montado antes de cualquier otra acción
    check_nas_mounted()

    args = parse_args()

    # --- Calcular rutas automáticas desde el stem del CSV ---
    csv_path = Path(args.csv) if args.csv else Path("scopus_results.csv")
    stem = csv_path.stem  # e.g. "cribado_global_phase1A"
    METADATOS_DIR = NAS_ROOT / "metadatos"
    LOGS_DIR = Path("/Volumes/Disco/proyectos/research_agent/logs")

    # output_dir: --out-dir > --phase > inbox/
    if args.out_dir:
        output_dir = Path(args.out_dir)
    elif args.phase:
        output_dir = NAS_ROOT / "inbox" / args.phase
    else:
        output_dir = NAS_ROOT / "inbox"

    cfg = Config(
        csv_file           = str(csv_path),
        output_dir         = output_dir,
        results_xlsx       = args.report       or str(METADATOS_DIR / f"resultado_descarga_{stem}.xlsx"),
        results_csv        = args.report_csv   or str(METADATOS_DIR / f"resultado_descarga_{stem}.csv"),
        log_file           = Path(args.log)    if args.log    else LOGS_DIR / f"3a_download_{stem}.log",
        cache_file         = args.cache        or str(METADATOS_DIR / "descarga_cache.json"),
        pending_html       = args.pending_html or str(METADATOS_DIR / f"pendientes_manual_{stem}.html"),
        pending_csv        = args.pending_csv  or str(METADATOS_DIR / f"pendientes_manual_{stem}.csv"),
        max_articles              = args.max,
        dry_run                   = args.dry_run,
        category                  = args.category,
        use_cache                 = not args.no_cache,
        cache_max_age_days        = args.cache_age,
        max_seconds_per_article   = args.max_seconds_per_article,
        min_pdf_pages             = args.min_pdf_pages,
        min_pdf_words             = args.min_pdf_words,
        keep_suspect_pdfs         = args.keep_suspect_pdfs,
        skip_rows                 = parse_skip_rows(args.skip_rows) if args.skip_rows else set(),
        no_elsevier_api           = args.no_elsevier_api,
    )

    # Crea subcarpetas del NAS que falten
    ensure_nas_structure()

    if not cfg.unpaywall_email:
        sys.exit(
            "Error: falta UNPAYWALL_EMAIL en config/.env o .env local\n"
            "Añade la línea:  UNPAYWALL_EMAIL=tu_email@uca.es"
        )

    if not Path(cfg.csv_file).exists():
        sys.exit(
            f"Error: no existe '{cfg.csv_file}'.\n"
            "Pasa la ruta del CSV de cribado con --csv, o ejecuta\n"
            "2_screen_keywords.py primero para generarlo."
        )

    manager = DownloadManager(cfg)
    manager.setup()
    manager.register_signals()

    if cfg.dry_run:
        log.info("=== MODO DRY-RUN: no se descargará ningún PDF ===")

    df = pd.read_csv(
    cfg.csv_file,
    sep=None,
    engine="python",
    encoding="utf-8-sig",
    dtype=str
    )
    df.columns = [str(c).strip() for c in df.columns]


    results, source_df = manager.run(df)
    manager.save_results(results, source_df)

    print("\n" + manager.stats.summary())
    print(f"\nPDFs en:          {cfg.output_dir.resolve()}")
    print(f"Resumen XLSX:     {Path(cfg.results_xlsx).resolve()}")
    print(f"Resumen CSV:      {Path(cfg.results_csv).resolve()}")
    print(f"Pendientes HTML:  {Path(cfg.pending_html).resolve()}")
    print(f"Pendientes CSV:   {Path(cfg.pending_csv).resolve()}")
    print(f"Log en:           {cfg.log_file.resolve()}")


if __name__ == "__main__":
    main()
