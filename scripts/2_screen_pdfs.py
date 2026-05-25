#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2_screen_pdfs.py

Clasifica PDFs científicos con Ollama (gemma3:4b) en categorías temáticas,
detecta duplicados por DOI y puede mover los archivos a carpetas destino.

Uso:
    python3 2_screen_pdfs.py --folders /ruta/pdfs1 /ruta/pdfs2
    python3 2_screen_pdfs.py --folders /ruta/pdfs --apply
    python3 2_screen_pdfs.py --folders /ruta/pdfs --output-csv /tmp/resultado.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import ollama
import yaml
from dotenv import load_dotenv

# -- importar utilidades del mismo paquete --
sys.path.insert(0, str(Path(__file__).parent))
from utils.pdf_utils import extract_doi_from_pdf

# Reutilizar funciones de Crossref del script de renombrado
try:
    import importlib.util
    _rename_script = Path(__file__).parent / "1_rename_papers_by_doi.py"
    _spec = importlib.util.spec_from_file_location("rename_utils", _rename_script)
    _rename_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_rename_mod)
    fetch_crossref_metadata = _rename_mod.fetch_crossref_metadata
    extract_title_from_metadata = _rename_mod.extract_title
    CROSSREF_AVAILABLE = True
except Exception as e:
    fetch_crossref_metadata = None
    extract_title_from_metadata = None
    CROSSREF_AVAILABLE = False
    print(f"Advertencia: no se pudo cargar Crossref helpers: {e}")

# ============================================================
# CONSTANTES
# ============================================================

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "2_screen_pdfs.log"

DEFAULT_OUTPUT_CSV = Path("/Volumes/research/metadatos/cribado_inicial.csv")
DEFAULT_DEST_BASE = Path("/Volumes/research/categorias")
FALLIDOS_DIR = Path("/Volumes/research/fallidos")
DUPLICADOS_DIR = Path("/Volumes/research/duplicados")
KNOWN_DOIS_FILE = Path("/Volumes/research/metadatos/doi_registry.txt")

LOW_CONFIDENCE_THRESHOLD = 0.6
CROSSREF_EMAIL = "martin.ramirez@uca.es"  # para Crossref API (educado: identificarse)

VALID_CATEGORIES = {
    "biological_gas_odor_treatment",
    "anoxic_biogas_biodesulfurization",
    "bioplastics_microplastics",
    "biogas_upgrading_biomethanation",
    "microalgae",
    "single_cell_protein",
    "advanced_oxidation_processes",
    "bioleaching_critical_materials",
    "irrelevante",
}

# Heading that stops title scanning
TITLE_STOP = re.compile(
    r"^\s*(abstract|resumen|keywords?|palabras\s+clave|introduction|introducción|doi\b)",
    re.IGNORECASE,
)
# "Abstract" / "Resumen" as a standalone heading line (tolerates surrounding spaces)
ABSTRACT_HEADING = re.compile(
    r"(?m)^[ \t]*(abstract|resumen)[ \t]*$",
    re.IGNORECASE,
)
# Section heading that marks the end of the abstract body
SECTION_CUT = re.compile(
    r"^\s*(keywords?|palabras\s+clave|introduction|introducción|"
    r"highlights?|graphical\s+abstract|1[\s.]\s*\w)",
    re.IGNORECASE,
)
# Journal / publisher metadata lines to skip when hunting for abstract text
HEADER_NOISE_LINE = re.compile(
    r"^\s*("
    r"\d{4}"                                            # bare year
    r"|vol\.?\s*\d+"                                    # volume
    r"|doi\s*:"                                         # DOI label
    r"|https?://"                                       # URL
    r"|received\s*:"                                    # received date
    r"|accepted\s*:"                                    # accepted date
    r"|available\s+online"
    r"|©"
    r"|\bISSN\b"
    r"|elsevier|springer|wiley|mdpi|taylor\s*&"
    r"|[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,4}"      # email
    r")",
    re.IGNORECASE,
)


# ============================================================
# SETUP
# ============================================================

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("screen_pdfs")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    return logger


def load_known_dois(path: Path) -> dict[str, str]:
    """Lee doi_registry.txt (doi\\torigencategoria/archivo) y devuelve {doi: origen}."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    result[parts[0]] = parts[1]
    except Exception as e:
        print(f"Advertencia: no se pudo leer {path}: {e}")
    return result


def load_keywords(yml_path: Path) -> dict[str, list[str]]:
    """Carga el fichero de palabras clave. Devuelve {} si no existe o hay error."""
    if not yml_path.exists():
        return {}
    try:
        with yml_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return {}
        return {cat: [str(kw) for kw in kws] for cat, kws in data.items() if isinstance(kws, list)}
    except Exception as e:
        print(f"Advertencia: no se pudo leer {yml_path}: {e}")
        return {}


def load_config() -> dict:
    env_path = PROJECT_ROOT / "config" / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(PROJECT_ROOT / ".env")
    return {
        "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "gemma3:4b"),
    }


# ============================================================
# DETECCIÓN DE TÍTULO Y ABSTRACT
# ============================================================

def detect_title_and_abstract(first_page_text: str, multi_page_text: str) -> tuple[str, str]:
    """Detect title from page 1; search abstract across up to 3 pages."""
    # --- Title: first meaningful lines before any section marker ---
    lines = [ln.strip() for ln in first_page_text.split("\n") if ln.strip()]
    title_lines: list[str] = []
    for line in lines[:12]:
        if TITLE_STOP.match(line):
            break
        if len(line) < 4:
            continue
        title_lines.append(line)
        if len(" ".join(title_lines)) > 350:
            break
    title = " ".join(title_lines[:4]).strip()

    # --- Abstract: strategy 1 — explicit "Abstract" / "Resumen" heading ---
    abstract = ""
    match = ABSTRACT_HEADING.search(multi_page_text)
    if match:
        snippet = multi_page_text[match.end():]
        end = re.search(
            r"\n\s*\n|^\s*(keywords?|introduction|1[\s.]\s*\w|©|highlights?)",
            snippet[:2000],
            re.IGNORECASE | re.MULTILINE,
        )
        body = snippet[: end.start() if end else 1500].strip()
        if len(body) > 80:
            abstract = body[:1500]

    # --- Abstract: strategy 2 — skip journal-header noise, grab first dense paragraph ---
    if not abstract:
        abstract = _extract_abstract_fallback(multi_page_text)

    return title, abstract


def _extract_abstract_fallback(text: str) -> str:
    """Skip header-noise lines; return the first body paragraph (up to 1500 chars)."""
    body_lines: list[str] = []
    skipping_header = True
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if SECTION_CUT.match(s):
            break
        if skipping_header:
            if HEADER_NOISE_LINE.match(s) or len(s) < 45:
                continue
            skipping_header = False
        body_lines.append(s)
        if len(" ".join(body_lines)) > 1400:
            break
    result = " ".join(body_lines).strip()
    return result[:1500] if result else text[:500].strip()


# ============================================================
# CLASIFICACIÓN — ETAPA 1: PALABRAS CLAVE
# ============================================================

def classify_with_keywords(
    titulo: str,
    abstract: str,
    keywords: dict[str, list[str]],
) -> tuple[Optional[str], float, str]:
    """Etapa 1: búsqueda de palabras clave (case-insensitive) en título + abstract.

    Devuelve (categoria, 1.0, 'keywords') si solo una categoría tiene coincidencias.
    Devuelve (None, 0.0, '')        si hay ambigüedad entre categorías o ninguna coincide
                                    → el llamador debe pasar a Ollama.
    """
    if not keywords:
        return None, 0.0, ""

    # Collapse all whitespace (including PDF line-breaks mid-phrase) before matching
    text = re.sub(r"[\s ]+", " ", titulo + " " + abstract).lower()
    hits: dict[str, int] = {
        cat: sum(1 for kw in kws if kw.lower() in text)
        for cat, kws in keywords.items()
    }
    matched = {cat: n for cat, n in hits.items() if n > 0}

    if len(matched) == 1:
        return next(iter(matched)), 1.0, "keywords"
    # 0 matches o ambigüedad entre categorías → Ollama
    return None, 0.0, ""


# ============================================================
# CLASIFICACIÓN — ETAPA 2: OLLAMA
# ============================================================

def classify_with_ollama(
    titulo: str,
    abstract: str,
    client: ollama.Client,
    model: str,
    logger: logging.Logger,
) -> tuple[str, float]:
    """Clasifica el artículo en una categoría usando Ollama. Devuelve (categoría, confianza)."""
    prompt = (
        "Eres un experto en ingeniería ambiental y biotecnología.\n"
        "Clasifica el siguiente artículo científico en UNA de estas categorías:\n"
        "- biological_gas_odor_treatment: biofiltración, filtros biológicos, BTF, VOCs, eliminación de olores\n"
        "- anoxic_biogas_biodesulfurization: desulfuración anóxica, H2S, NR-SOB, azufre elemental, biogás, siloxano\n"
        "- bioplastics_microplastics: microplásticos, bioplásticos, PLA, PBAT, PHA, PHB, polietileno, digestión anaerobia\n"
        "- biogas_upgrading_biomethanation: upgrading de biogás, biometanación, power-to-gas, HF-MBR, BES\n"
        "- microalgae: microalgas, fotobiorreactor, fijación de CO2, secuestro de carbono, Chlorella, Nannochloropsis\n"
        "- single_cell_protein: proteína unicelular, SCP, proteína microbiana, MOB, Methylococcus capsulatus\n"
        "- advanced_oxidation_processes: fotocatálisis, TiO2, ZnO, AOPs, foto-Fenton\n"
        "- bioleaching_critical_materials: biolixiviación, PGMs, catalizadores de automoción, Acidithiobacillus\n"
        "- irrelevante: no encaja claramente en ninguna de las anteriores\n\n"
        f"Título: {titulo}\n\n"
        f"Abstract: {abstract}\n\n"
        "Responde ÚNICAMENTE con JSON válido en este formato exacto (sin texto extra):\n"
        '{"clasificacion": "biological_gas_odor_treatment", "confianza": 0.95}'
    )

    resp = client.generate(model=model, prompt=prompt, format="json", stream=False,
                           options={"temperature": 0.1})
    response_text = resp["response"]

    parsed = json.loads(response_text)
    clasificacion = str(parsed.get("clasificacion", "irrelevante")).lower().strip()
    confianza = float(parsed.get("confianza", 0.0))

    if clasificacion not in VALID_CATEGORIES:
        logger.warning(f"Categoría inválida de Ollama: '{clasificacion}' → 'irrelevante'")
        clasificacion = "irrelevante"
    confianza = max(0.0, min(1.0, confianza))

    return clasificacion, confianza


# ============================================================
# RECOLECCIÓN DE PDFs
# ============================================================

def collect_pdfs(folders: list[Path]) -> list[Path]:
    """Recorre recursivamente las carpetas y devuelve todos los PDFs encontrados."""
    seen: set[Path] = set()
    result: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            print(f"  Advertencia: '{folder}' no existe o no es un directorio, se omite.")
            continue
        for p in sorted(folder.rglob("*")):
            if p.suffix.lower() == ".pdf" and p not in seen:
                seen.add(p)
                result.append(p)
    return result


# ============================================================
# PROCESADO DE UN PDF
# ============================================================

def process_pdf(
    pdf_path: Path,
    doi_registry: dict[str, str],
    client: ollama.Client,
    ollama_model: str,
    logger: logging.Logger,
    keywords: dict[str, list[str]],
) -> dict:
    result: dict = {
        "ruta_original": str(pdf_path),
        "doi": "",
        "titulo_detectado": "",
        "abstract_detectado": "",
        "clasificacion": "",
        "confianza": "",
        "metodo": "",
        "duplicado_de": "",
        "estado": "",
    }

    # Extraer texto de las primeras 3 páginas (el abstract puede estar en la pág. 2)
    try:
        with fitz.open(pdf_path) as doc:
            pages_text = [
                doc[i].get_text("text", sort=True)
                for i in range(min(3, len(doc)))
            ]
    except Exception as e:
        logger.error(f"Error abriendo {pdf_path.name}: {e}")
        result["estado"] = "ERROR_LECTURA_PDF"
        return result

    first_page_text = pages_text[0] if pages_text else ""
    multi_page_text = "\n".join(pages_text)

    # Extraer DOI primero (lo necesitamos para Crossref)
    doi = extract_doi_from_pdf(pdf_path)
    result["doi"] = doi or ""

    # Intentar obtener título de Crossref si hay DOI
    titulo = ""
    abstract = ""

    if doi and CROSSREF_AVAILABLE:
        try:
            metadata = fetch_crossref_metadata(doi, email=CROSSREF_EMAIL)
            titulo = extract_title_from_metadata(metadata)
            logger.info(f"{pdf_path.name}: título obtenido de Crossref (DOI: {doi})")
            # Breve delay para no saturar la API
            import time
            time.sleep(0.15)
        except Exception as e:
            logger.warning(f"{pdf_path.name}: Crossref falló ({e}), usando parsing PDF")

    # Fallback: parsear del PDF si no hay DOI válido o Crossref falló
    if not titulo:
        titulo, abstract = detect_title_and_abstract(first_page_text, multi_page_text)
    else:
        # Si tenemos título de Crossref, aún así parsear abstract del PDF
        _, abstract = detect_title_and_abstract(first_page_text, multi_page_text)

    result["titulo_detectado"] = titulo
    result["abstract_detectado"] = abstract

    # Detección de duplicados
    if doi:
        if doi in doi_registry:
            result["duplicado_de"] = doi_registry[doi]
            result["estado"] = "DUPLICADO"
            logger.info(f"Duplicado detectado: {pdf_path.name} — mismo DOI que {doi_registry[doi]}")
            return result
        doi_registry[doi] = str(pdf_path)

    # Etapa 1: palabras clave
    cat_kw, conf_kw, metodo_kw = classify_with_keywords(titulo, abstract, keywords)
    if cat_kw is not None:
        result["clasificacion"] = cat_kw
        result["confianza"] = f"{conf_kw:.2f}"
        result["metodo"] = metodo_kw
        result["estado"] = "OK"
        logger.info(f"{pdf_path.name}: {cat_kw} (keywords, {conf_kw:.2f})")
        return result

    # Etapa 2: Ollama (sin coincidencia clara por keywords)
    try:
        clasificacion, confianza = classify_with_ollama(
            titulo, abstract, client, ollama_model, logger
        )
        result["clasificacion"] = clasificacion
        result["confianza"] = f"{confianza:.2f}"
        result["metodo"] = "llm"
        result["estado"] = "OK"
        logger.info(f"{pdf_path.name}: {clasificacion} (llm, {confianza:.2f})")
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido de Ollama para {pdf_path.name}: {e}")
        result["clasificacion"] = "irrelevante"
        result["confianza"] = "0.00"
        result["metodo"] = "llm"
        result["estado"] = "ERROR_CLASIFICACION"
    except Exception as e:
        logger.error(f"Error clasificando {pdf_path.name}: {e}")
        result["clasificacion"] = "irrelevante"
        result["confianza"] = "0.00"
        result["metodo"] = "llm"
        result["estado"] = "ERROR_CLASIFICACION"

    return result


# ============================================================
# CSV
# ============================================================

def save_csv(rows: list[dict], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ruta_original", "doi", "titulo_detectado", "abstract_detectado",
        "clasificacion", "confianza", "metodo", "duplicado_de", "estado",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# MOVIMIENTO DE ARCHIVOS (modo --apply)
# ============================================================

def _move_file(src: Path, dest_dir: Path, logger: logging.Logger) -> Optional[Path]:
    """Mueve src a dest_dir, añadiendo sufijo numérico si hay colisión. Devuelve destino o None."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    counter = 2
    while dest.exists():
        dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    try:
        shutil.move(str(src), str(dest))
        return dest
    except Exception as e:
        logger.error(f"Error moviendo {src.name}: {e}")
        return None


def apply_moves(
    rows: list[dict],
    dest_base: Path,
    fallidos_dir: Path,
    logger: logging.Logger,
    duplicados_dir: Path = DUPLICADOS_DIR,
) -> dict[str, int]:
    """Mueve los PDFs clasificados según resultado:
    - clasificacion válida y confianza >= 0.6 → dest_base/<categoria>/pdfs/
    - clasificacion == 'irrelevante' o confianza < 0.6 → fallidos_dir/
    - DUPLICADO → duplicados_dir/
    - ERROR_* → se omiten (no se mueven)
    """
    moved: dict[str, int] = {}
    for row in rows:
        estado = row["estado"]
        clasificacion = row["clasificacion"]

        if estado in ("ERROR_LECTURA_PDF", "ERROR_CLASIFICACION"):
            continue

        src = Path(row["ruta_original"])
        if not src.exists():
            logger.warning(f"Archivo no encontrado para mover: {src}")
            continue

        if estado == "DUPLICADO":
            dest = _move_file(src, duplicados_dir, logger)
            if dest:
                logger.info(f"Duplicado movido: {src.name} → {dest}")
                moved["duplicados"] = moved.get("duplicados", 0) + 1
            continue

        try:
            confianza = float(row["confianza"]) if row["confianza"] else 0.0
        except ValueError:
            confianza = 0.0

        if clasificacion == "irrelevante" or confianza < LOW_CONFIDENCE_THRESHOLD:
            dest = _move_file(src, fallidos_dir, logger)
            if dest:
                logger.info(f"Fallido: {src.name} → {dest}  (cat={clasificacion}, conf={confianza:.2f})")
                moved["fallidos"] = moved.get("fallidos", 0) + 1
        elif clasificacion:
            dest = _move_file(src, dest_base / clasificacion / "pdfs", logger)
            if dest:
                logger.info(f"Movido: {src.name} → {dest}")
                moved[clasificacion] = moved.get(clasificacion, 0) + 1

    return moved


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clasificar PDFs científicos con Ollama y detectar duplicados por DOI"
    )
    parser.add_argument(
        "--folders", nargs="+", required=True,
        help="Uno o varios directorios con PDFs (búsqueda recursiva)",
    )
    parser.add_argument(
        "--output-csv", default=str(DEFAULT_OUTPUT_CSV),
        help=f"CSV de salida (por defecto: {DEFAULT_OUTPUT_CSV})",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--preview", action="store_true",
        help="Solo genera CSV, no mueve nada (comportamiento por defecto)",
    )
    mode_group.add_argument(
        "--apply", action="store_true",
        help=f"Mueve los PDFs clasificados a {DEFAULT_DEST_BASE}/<categoria>/pdfs/",
    )
    parser.add_argument(
        "--from-csv", default=None, metavar="PATH",
        help="Cargar clasificaciones desde CSV existente; omite re-clasificar los PDFs",
    )
    args = parser.parse_args()
    apply_mode = args.apply

    config = load_config()
    ollama_host = config["ollama_host"]
    ollama_model = config["ollama_model"]
    client = ollama.Client(host=ollama_host, timeout=120)

    keywords = load_keywords(PROJECT_ROOT / "config" / "keywords.yml")

    logger = setup_logging()
    logger.info(f"=== 2_screen_pdfs.py | modo={'APPLY' if apply_mode else 'PREVIEW'} ===")

    # ── Modo --from-csv: cargar filas pre-clasificadas y salir ────────────
    if args.from_csv:
        from_csv_path = Path(args.from_csv)
        logger.info(f"Modo from-csv: {from_csv_path} | apply={apply_mode}")
        if not from_csv_path.exists():
            print(f"Error: CSV no encontrado: {from_csv_path}")
            return 1
        with from_csv_path.open(encoding="utf-8", newline="") as f:
            rows: list[dict] = list(csv.DictReader(f))
        print(f"CSV cargado: {from_csv_path}  ({len(rows)} filas)")
        if apply_mode:
            print("Aplicando movimientos desde CSV...")
            moved_counts = apply_moves(rows, DEFAULT_DEST_BASE, FALLIDOS_DIR, logger)
            ok_count = sum(v for k, v in moved_counts.items() if k not in ("fallidos", "duplicados"))
            print(f"  → clasificados movidos: {ok_count}")
            print(f"  → fallidos:             {moved_counts.get('fallidos', 0)}")
            print(f"  → duplicados: {moved_counts.get('duplicados', 0)} movidos  [{DUPLICADOS_DIR}]")
        else:
            for row in rows:
                print(f"  {Path(row['ruta_original']).name}: {row['clasificacion']} ({row['confianza']}) [{row['estado']}]")
        logger.info(f"=== Fin from-csv: {len(rows)} filas ===")
        return 0

    folders = [Path(f).expanduser().resolve() for f in args.folders]
    pdfs = collect_pdfs(folders)

    if not pdfs:
        print("No se encontraron PDFs en las carpetas indicadas.")
        logger.warning("Sin PDFs encontrados.")
        return 0

    output_csv = Path(args.output_csv)

    print(f"\nCarpetas:  {', '.join(str(f) for f in folders)}")
    print(f"PDFs:      {len(pdfs)}")
    print(f"Modo:      {'APPLY — moverá archivos clasificados' if apply_mode else 'PREVIEW — solo CSV'}")
    kw_total = sum(len(v) for v in keywords.values())
    print(f"Keywords:  {len(keywords)} categorías, {kw_total} términos  →  ambigüos pasan a Ollama")
    print(f"Ollama:    {ollama_host}  modelo: {ollama_model}")
    print(f"CSV:       {output_csv}")
    print("-" * 80)

    rows: list[dict] = []
    doi_registry: dict[str, str] = load_known_dois(KNOWN_DOIS_FILE)
    logger.info(f"DOIs conocidos precargados: {len(doi_registry)}")
    print(f"DOIs conocidos:  {len(doi_registry)} (cargados de doi_registry.txt)")
    total = len(pdfs)
    errors = 0

    for i, pdf_path in enumerate(pdfs, start=1):
        print(f"[{i}/{total}] {pdf_path.name} ...", end=" ", flush=True)
        logger.info(f"[{i}/{total}] {pdf_path}")

        row = process_pdf(pdf_path, doi_registry, client, ollama_model, logger, keywords)
        rows.append(row)

        estado = row["estado"]
        if estado == "DUPLICADO":
            print(f"DUPLICADO de {Path(row['duplicado_de']).name}")
        elif "ERROR" in estado:
            errors += 1
            print(f"ERROR ({estado})")
        else:
            print(f"{row['clasificacion']} ({row['confianza']}) [{row['metodo']}]")

    save_csv(rows, output_csv)
    logger.info(f"CSV guardado: {output_csv}")
    print(f"\nCSV guardado en: {output_csv}")

    moved_counts: dict[str, int] = {}
    if apply_mode:
        print("\nMoviendo archivos clasificados...")
        moved_counts = apply_moves(rows, DEFAULT_DEST_BASE, FALLIDOS_DIR, logger)

    # Resumen
    ok_rows = [r for r in rows if r["estado"] == "OK"]
    cat_counts = Counter(r["clasificacion"] for r in ok_rows)
    kw_count = sum(1 for r in ok_rows if r["metodo"] == "keywords")
    llm_count = sum(1 for r in ok_rows if r["metodo"] == "llm")
    duplicates = sum(1 for r in rows if r["estado"] == "DUPLICADO")

    print("\n" + "=" * 80)
    print("RESUMEN")
    print("=" * 80)
    print(f"Total procesados:     {total}")
    for cat in (
        "biological_gas_odor_treatment",
        "anoxic_biogas_biodesulfurization",
        "bioplastics_microplastics",
        "biogas_upgrading_biomethanation",
        "microalgae",
        "single_cell_protein",
        "advanced_oxidation_processes",
        "bioleaching_critical_materials",
        "irrelevante",
    ):
        n = cat_counts.get(cat, 0)
        suffix = f"  → {moved_counts.get(cat, 0)} movidos" if apply_mode and cat != "irrelevante" else ""
        print(f"  {cat:<28} {n}{suffix}")
    if apply_mode:
        print(f"  {'→ fallidos (irrel. / conf<0.6)':<28}   {moved_counts.get('fallidos', 0)} movidos  [{FALLIDOS_DIR}]")
        print(f"  → duplicados: {moved_counts.get('duplicados', 0)} movidos  [{DUPLICADOS_DIR}]")
    print(f"Duplicados:           {duplicates}")
    print(f"Errores:              {errors}")
    print(f"Método keywords:      {kw_count}")
    print(f"Método llm:           {llm_count}")
    print(f"Log:                  {LOG_FILE}")
    print(f"CSV:                  {output_csv}")

    logger.info(
        f"=== Fin: {total} PDFs | {len(ok_rows)} OK | {duplicates} dup | {errors} err ==="
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
