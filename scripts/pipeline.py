# -*- coding: utf-8 -*-
"""
pipeline.py — Orquestador del pipeline research_agent

Tres flujos:
  - run_scopus()  → Búsqueda Scopus → descarga → directo a categoría → procesado
  - run_inbox()   → PDFs en inbox → renombrar → cribado → categorías → procesado
  - run_adhoc()   → Carpeta de PDFs → proyecto temporal → procesado + RAG

Uso como módulo (Streamlit, scripts, notebooks):
    from pipeline import run_scopus, run_inbox, run_adhoc

    run_scopus(categories=["microalgae"], recent_days=7)
    run_inbox()
    run_adhoc("revision_metanol", "/Users/martin/papers_metanol")

Uso desde CLI (terminal, cron):
    python run_pipeline.py scopus --recent-days 7
    python run_pipeline.py inbox
    python run_pipeline.py adhoc --name revision_metanol --pdfs /ruta/pdfs

Cada función acepta un callback on_output(line: str) para capturar la salida
línea a línea — útil para st.write() en Streamlit.
"""

from __future__ import annotations

import csv
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent
NAS_ROOT = Path("/Volumes/research")
CATEGORIAS_DIR = NAS_ROOT / "categorias"
INBOX_DIR = NAS_ROOT / "inbox"
INBOX_CSV_DIR = NAS_ROOT / "inbox_csv"
KNOWN_DOIS_FILE = NAS_ROOT / "metadatos" / "doi_registry.txt"

log = logging.getLogger("pipeline")

# Estructura de subcarpetas que debe tener cada proyecto/categoría
_PROJECT_SUBDIRS = [
    "pdfs", "tei", "md_clean", "summaries", "chunks",
    "embeddings", "metadata", "notebooklm_packages", "logs",
]


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

def check_nas() -> None:
    """Verifica que el NAS está montado. Lanza RuntimeError si no."""
    if not NAS_ROOT.exists():
        raise RuntimeError(
            f"NAS no montado en {NAS_ROOT}. "
            "Monta con: open smb://synology/research"
        )


# ---------------------------------------------------------------------------
# Ejecución de scripts
# ---------------------------------------------------------------------------

def run_step(
    script: str,
    args: List[str],
    on_output: Optional[Callable[[str], None]] = None,
    label: str = "",
) -> Dict[str, Any]:
    """Ejecuta un script del pipeline como subproceso.

    Args:
        script:    nombre del fichero (e.g. "3_process_corpus.py")
        args:      lista de argumentos CLI
        on_output: callback que recibe cada línea de salida (para Streamlit)
        label:     etiqueta para logs (e.g. "process_corpus [microalgae]")

    Returns:
        {"returncode": int, "output": list[str], "script": str}
    """
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + args
    tag = label or script

    log.info("▶ %s %s", tag, " ".join(args))

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(SCRIPTS_DIR),
        )
    except FileNotFoundError:
        msg = f"Script no encontrado: {SCRIPTS_DIR / script}"
        log.error(msg)
        return {"returncode": -1, "output": [msg], "script": script}

    output_lines: List[str] = []
    for line in process.stdout:
        line = line.rstrip("\n")
        output_lines.append(line)
        if on_output:
            on_output(line)
        else:
            print(line)
    process.wait()

    rc = process.returncode
    if rc != 0:
        log.error("✗ %s falló (rc=%d)", tag, rc)
    else:
        log.info("✓ %s completado", tag)

    return {"returncode": rc, "output": output_lines, "script": script}


# ---------------------------------------------------------------------------
# Cadena de procesado (común a los tres flujos)
# ---------------------------------------------------------------------------

# Pasos de procesado: (script, argumento para el nombre de proyecto)
_PROCESS_CHAIN = [
    ("3_process_corpus.py",    "--phase"),
    ("3b_summarize.py",        "--phase"),
    ("4_extract_metadata.py",  "--project"),
    ("5_build_embeddings.py",  "--project"),
    ("6_make_packages.py",     "--project"),
    ("7_make_master_index.py", "--project"),
]


def process_category(
    category: str,
    on_output: Optional[Callable[[str], None]] = None,
    extra_args: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Ejecuta la cadena de procesado completa para una categoría.

    Args:
        category:   nombre de la categoría / proyecto
        on_output:  callback para líneas de salida
        extra_args: args extra por script, e.g. {"3_process_corpus.py": ["--force"]}

    Returns:
        {"status": "ok"|"error", "steps": {script: result_dict}}
    """
    extra = extra_args or {}
    steps_results: Dict[str, Any] = {}
    status = "ok"

    for script, arg_name in _PROCESS_CHAIN:
        args = [arg_name, category] + extra.get(script, [])
        label = f"{script} [{category}]"
        result = run_step(script, args, on_output=on_output, label=label)
        steps_results[script] = result

        if result["returncode"] != 0:
            status = "error"
            log.error("Cadena interrumpida en %s para '%s'.", script, category)
            break

    if status == "ok":
        new_dois = update_doi_registry(category)
        log.info("DOI registry: +%d DOIs nuevos para '%s'", new_dois, category)

    return {"status": status, "steps": steps_results}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def ensure_project_dirs(project_name: str) -> Path:
    """Crea la estructura de carpetas para un proyecto bajo categorias/."""
    project_dir = CATEGORIAS_DIR / project_name
    for sub in _PROJECT_SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir


def detect_affected_categories() -> List[str]:
    """Devuelve las categorías que tienen PDFs sin procesar en pdfs/.

    Un PDF está "sin procesar" si no tiene su correspondiente fichero en md_clean/.
    """
    affected = []
    if not CATEGORIAS_DIR.exists():
        return affected

    for cat_dir in sorted(CATEGORIAS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        pdfs_dir = cat_dir / "pdfs"
        md_dir = cat_dir / "md_clean"
        if not pdfs_dir.exists():
            continue

        pdf_stems = {p.stem for p in pdfs_dir.glob("*.pdf")}
        # md_clean files end with .clean.md — el stem real es sin ".clean"
        md_stems = set()
        for m in md_dir.glob("*.clean.md") if md_dir.exists() else []:
            md_stems.add(m.name.replace(".clean.md", ""))

        new_pdfs = pdf_stems - md_stems
        if new_pdfs:
            affected.append(cat_dir.name)

    return affected


def update_doi_registry(category: str) -> int:
    """Actualiza doi_registry.txt con los DOIs de categorias/<category>/pdfs/.

    Devuelve el número de DOIs nuevos añadidos. Tolerante a fallos.
    """
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from utils.pdf_utils import extract_doi_from_pdf  # noqa: PLC0415

        existing: Dict[str, str] = {}
        if KNOWN_DOIS_FILE.exists():
            with KNOWN_DOIS_FILE.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        existing[parts[0]] = parts[1]

        pdfs_dir = CATEGORIAS_DIR / category / "pdfs"
        if not pdfs_dir.exists():
            return 0

        added = 0
        for pdf in sorted(pdfs_dir.glob("*.pdf")):
            doi = extract_doi_from_pdf(pdf)
            if doi and doi not in existing:
                existing[doi] = f"{category}/{pdf.name}"
                added += 1

        if added > 0:
            KNOWN_DOIS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with KNOWN_DOIS_FILE.open("w", encoding="utf-8") as f:
                for doi, origen in sorted(existing.items()):
                    f.write(f"{doi}\t{origen}\n")

        return added
    except Exception as e:
        log.warning("update_doi_registry(%s) falló: %s", category, e)
        return 0


def build_doi_registry_from_nas() -> int:
    """Escanea todas las categorías y reconstruye doi_registry.txt desde cero.

    Lee los PDFs de categorias/*/pdfs/ y extrae DOIs. Es útil antes del cribado
    para detectar duplicados contra artículos ya procesados.

    Returns:
        Número total de DOIs registrados.
    """
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from utils.pdf_utils import extract_doi_from_pdf  # noqa: PLC0415
    except Exception as e:
        log.warning("No se pudo importar extract_doi_from_pdf: %s", e)
        return 0

    registry: Dict[str, str] = {}

    if not CATEGORIAS_DIR.exists():
        return 0

    for cat_dir in sorted(CATEGORIAS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        pdfs_dir = cat_dir / "pdfs"
        if not pdfs_dir.exists():
            continue

        pdfs = sorted(
            p for p in pdfs_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".pdf"
        )
        for pdf in pdfs:
            try:
                doi = extract_doi_from_pdf(pdf)
                if doi and doi not in registry:
                    registry[doi] = f"{cat_dir.name}/{pdf.name}"
            except Exception as e:
                log.debug("Error extrayendo DOI de %s: %s", pdf.name, e)
                continue

    KNOWN_DOIS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with KNOWN_DOIS_FILE.open("w", encoding="utf-8") as f:
        for doi, origen in sorted(registry.items()):
            f.write(f"{doi}\t{origen}\n")

    log.info("doi_registry.txt reconstruido: %d DOIs desde el NAS", len(registry))
    return len(registry)


# ═══════════════════════════════════════════════════════════════════════════
# FLUJO A — Scopus
# ═══════════════════════════════════════════════════════════════════════════

def run_scopus(
    categories: Optional[List[str]] = None,
    recent_days: Optional[int] = None,
    max_results: int = 200,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
    doctype: Optional[str] = None,
    queries_file: Optional[str] = None,
    dry_run: bool = False,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Flujo A: Scopus API → descarga → directo a categoría → procesado.

    Pasos:
      1. 0_scopus_api.py  → genera CSVs en inbox_csv/
      2. 3a_download_pdfs.py  → descarga PDFs directo a categorias/<cat>/pdfs/
      3. Cadena de procesado (3_process … 7_master_index) por cada categoría

    Args:
        categories:   lista de categorías a buscar (None = todas las del YAML)
        recent_days:  solo artículos indexados en los últimos N días
        max_results:  máximo de resultados por categoría
        year_start:   filtro año desde (inclusive)
        year_end:     filtro año hasta (inclusive)
        doctype:      filtro tipo doc Scopus ("ar", "re", etc.)
        queries_file: ruta al YAML de queries (None = config/scopus_queries.yml)
        dry_run:      solo muestra totales sin guardar ni descargar
        on_output:    callback para líneas de salida

    Returns:
        {"status": "ok"|"partial"|"error", "categories": {cat: result}}
    """
    check_nas()
    _setup_pipeline_log("scopus")
    log.info("=== run_scopus iniciado ===")
    handler = _make_output_handler(on_output)
    run_date = datetime.now().strftime("%Y%m%d")
    results: Dict[str, Any] = {}

    # --- Paso 1: búsqueda Scopus ---
    scopus_args = [
        "--max", str(max_results),
    ]
    if queries_file:
        scopus_args += ["--queries", queries_file]
    if categories:
        for c in categories:
            scopus_args += ["--category", c]
    if recent_days is not None:
        scopus_args += ["--recent-days", str(recent_days)]
    if year_start is not None:
        scopus_args += ["--year-start", str(year_start)]
    if year_end is not None:
        scopus_args += ["--year-end", str(year_end)]
    if doctype:
        scopus_args += ["--doctype", doctype]
    if dry_run:
        scopus_args.append("--dry-run")

    scopus_result = run_step("0_scopus_api.py", scopus_args, on_output=handler)
    if scopus_result["returncode"] != 0:
        return {"status": "error", "stage": "scopus_search", "details": scopus_result}

    if dry_run:
        return {"status": "ok", "mode": "dry_run", "scopus": scopus_result}

    # --- Determinar qué categorías se buscaron ---
    # Si no se especificaron, leer del YAML (o asumir todas las que generaron CSV)
    if categories:
        target_cats = categories
    else:
        # Buscar CSVs generados hoy
        target_cats = []
        for csv_file in sorted(INBOX_CSV_DIR.glob(f"scopus_*_{run_date}.csv")):
            name = csv_file.stem  # scopus_microalgae_20260515
            parts = name.split("_")
            # Extraer categoría (todo entre "scopus_" y "_YYYYMMDD")
            if len(parts) >= 3 and parts[-1] == run_date:
                cat = "_".join(parts[1:-1])
                if cat != "ALL":
                    target_cats.append(cat)

    # --- Paso 2 y 3: descargar + procesar por categoría ---
    for cat in target_cats:
        log.info("═" * 50)
        log.info("CATEGORÍA: %s", cat)

        csv_path = INBOX_CSV_DIR / f"scopus_{cat}_{run_date}.csv"
        if not csv_path.exists():
            log.warning("CSV no encontrado: %s — saltando.", csv_path)
            results[cat] = {"status": "skipped", "reason": "CSV no existe"}
            continue

        # Asegurar estructura de directorios
        ensure_project_dirs(cat)
        pdfs_dir = CATEGORIAS_DIR / cat / "pdfs"

        # Descargar directamente a categorias/<cat>/pdfs/
        dl_result = run_step(
            "3a_download_pdfs.py",
            ["--csv", str(csv_path), "--out-dir", str(pdfs_dir)],
            on_output=handler,
            label=f"download [{cat}]",
        )

        if dl_result["returncode"] != 0:
            results[cat] = {"status": "error", "stage": "download", "details": dl_result}
            continue

        # Cadena de procesado
        proc_result = process_category(cat, on_output=handler)
        results[cat] = proc_result

    # --- Resumen ---
    ok = sum(1 for r in results.values() if r.get("status") == "ok")
    total = len(results)
    overall = "ok" if ok == total else ("partial" if ok > 0 else "error")

    summary = {"status": overall, "categories": results, "date": run_date}
    _log_summary("SCOPUS", results)
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# FLUJO B — Inbox (PDFs sueltos)
# ═══════════════════════════════════════════════════════════════════════════

def run_inbox_screen(
    folders: Optional[List[str]] = None,
    rename: bool = True,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Fase 1 del flujo Inbox: renombrar + cribado sin mover PDFs.

    Genera cribado_pendiente.csv con la clasificación propuesta.

    Returns:
        {"status": "ok", "csv_path": str, "rows": [dicts del CSV]}
    """
    check_nas()
    _setup_pipeline_log("inbox_screen")
    log.info("=== run_inbox_screen iniciado ===")
    handler = _make_output_handler(on_output)
    inbox_folders = folders or [str(INBOX_DIR)]
    pending_csv = NAS_ROOT / "metadatos" / "cribado_pendiente.csv"

    if rename:
        rename_result = run_step(
            "1_rename_papers_by_doi.py",
            ["--folder", inbox_folders[0], "--apply"],
            on_output=handler,
            label="rename",
        )
        if rename_result["returncode"] != 0:
            log.warning("Renombrado falló, pero continuamos con el cribado.")

    if handler:
        handler("Actualizando registro de DOIs del NAS...")
    try:
        n_dois = build_doi_registry_from_nas()
        log.info("Registro de DOIs actualizado: %d DOIs conocidos", n_dois)
        if handler:
            handler(f"✓ Registro actualizado: {n_dois} DOIs conocidos en el NAS")
    except Exception as e:
        log.warning("Error actualizando doi_registry.txt: %s", e)
        if handler:
            handler(f"⚠️ No se pudo actualizar registro de DOIs: {e}")

    screen_args = ["--folders"] + inbox_folders + ["--output-csv", str(pending_csv)]
    screen_result = run_step(
        "2_screen_pdfs.py",
        screen_args,
        on_output=handler,
        label="screen [preview]",
    )
    if screen_result["returncode"] != 0:
        return {"status": "error", "stage": "screen", "details": screen_result}

    rows: List[Dict[str, Any]] = []
    if pending_csv.exists():
        with pending_csv.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

    return {"status": "ok", "csv_path": str(pending_csv), "rows": rows}


def run_inbox_process(
    csv_path: Optional[str] = None,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Fase 2 del flujo Inbox: aplicar movimientos y procesar categorías afectadas.

    Toma el CSV de cribado (csv_path o cribado_pendiente.csv por defecto).

    Returns:
        {"status": "ok"|"partial"|"error", "categories": {cat: result}}
    """
    check_nas()
    _setup_pipeline_log("inbox_process")
    log.info("=== run_inbox_process iniciado ===")
    handler = _make_output_handler(on_output)

    effective_csv = (
        Path(csv_path) if csv_path
        else NAS_ROOT / "metadatos" / "cribado_pendiente.csv"
    )
    inbox_folders = [str(INBOX_DIR)]

    screen_args = (
        ["--folders"] + inbox_folders
        + ["--apply", "--from-csv", str(effective_csv)]
    )
    screen_result = run_step(
        "2_screen_pdfs.py",
        screen_args,
        on_output=handler,
        label="screen [apply]",
    )
    if screen_result["returncode"] != 0:
        return {"status": "error", "stage": "screen", "details": screen_result}

    affected = detect_affected_categories()
    if not affected:
        log.info("No hay PDFs nuevos que procesar tras el cribado.")
        return {"status": "ok", "categories": {}, "message": "sin novedades"}

    log.info("Categorías con PDFs nuevos: %s", ", ".join(affected))

    results: Dict[str, Any] = {}
    for cat in affected:
        log.info("═" * 50)
        log.info("CATEGORÍA: %s", cat)
        proc_result = process_category(cat, on_output=handler)
        results[cat] = proc_result

    ok = sum(1 for r in results.values() if r.get("status") == "ok")
    total = len(results)
    overall = "ok" if ok == total else ("partial" if ok > 0 else "error")

    summary: Dict[str, Any] = {"status": overall, "categories": results}
    _log_summary("INBOX", results)
    return summary


def run_inbox(
    folders: Optional[List[str]] = None,
    rename: bool = True,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Flujo B completo: cribar + procesar en secuencia.

    Wrapper de compatibilidad para CLI y cron. Equivale a llamar
    run_inbox_screen() seguido de run_inbox_process().
    """
    screen = run_inbox_screen(folders=folders, rename=rename, on_output=on_output)
    if screen.get("status") != "ok":
        return screen
    return run_inbox_process(csv_path=screen.get("csv_path"), on_output=on_output)


# ═══════════════════════════════════════════════════════════════════════════
# FLUJO C — Ad-hoc
# ═══════════════════════════════════════════════════════════════════════════

def run_adhoc(
    name: str,
    pdf_dir: str,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Flujo C: carpeta de PDFs → proyecto ad-hoc → procesado completo + RAG.

    Crea un proyecto bajo categorias/<name>/, copia los PDFs y ejecuta
    la cadena de procesado completa. No hace cribado ni renombrado.

    Args:
        name:       nombre del proyecto ad-hoc (e.g. "revision_metanol")
        pdf_dir:    carpeta con los PDFs de origen
        on_output:  callback para líneas de salida

    Returns:
        {"status": "ok"|"error", "project": name, "steps": {script: result}}
    """
    check_nas()
    source = Path(pdf_dir)

    if not source.exists():
        raise FileNotFoundError(f"Carpeta de PDFs no encontrada: {source}")

    pdfs = list(source.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontraron PDFs en {source}")

    log.info("═" * 50)
    log.info("PROYECTO AD-HOC: %s", name)
    log.info("Fuente: %s (%d PDFs)", source, len(pdfs))

    # Crear estructura del proyecto
    project_dir = ensure_project_dirs(name)
    dest_pdfs = project_dir / "pdfs"

    # Copiar PDFs (no mover — el origen puede ser del usuario)
    copied = 0
    skipped = 0
    for pdf in pdfs:
        dest = dest_pdfs / pdf.name
        if dest.exists():
            skipped += 1
            continue
        shutil.copy(pdf, dest)
        copied += 1

    msg = f"PDFs copiados: {copied}, ya existían: {skipped}"
    log.info(msg)
    if on_output:
        on_output(msg)

    # Cadena de procesado
    proc_result = process_category(name, on_output=on_output)

    summary = {
        "status": proc_result["status"],
        "project": name,
        "pdfs_copied": copied,
        "pdfs_skipped": skipped,
        "pdfs_total": len(pdfs),
        "steps": proc_result["steps"],
        "query_cmd": f'python 8_query_rag.py --project {name} "tu pregunta aquí"',
    }

    if proc_result["status"] == "ok":
        log.info("Proyecto '%s' listo para consultas RAG.", name)
        log.info("  python 8_query_rag.py --project %s \"tu pregunta\"", name)

    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_pipeline_log(flow: str) -> Path:
    """Crea un FileHandler con timestamp para el logger pipeline y devuelve su Path."""
    logs_dir = SCRIPTS_DIR.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"pipeline_{flow}_{ts}.log"
    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(fh)
    return log_path


def _make_output_handler(
    on_output: Optional[Callable[[str], None]] = None,
) -> Callable[[str], None]:
    """Devuelve un callable que loguea cada línea y la reenvía a on_output."""
    def handler(line: str) -> None:
        log.info("[out] %s", line)
        if on_output:
            on_output(line)
    return handler


def _log_summary(flow: str, results: Dict[str, Any]) -> None:
    """Imprime resumen final de un flujo."""
    log.info("")
    log.info("═" * 50)
    log.info("RESUMEN %s", flow)
    log.info("═" * 50)
    for cat, res in results.items():
        status = res.get("status", "?")
        icon = "✓" if status == "ok" else "✗"
        log.info("  %s %-40s %s", icon, cat, status)
