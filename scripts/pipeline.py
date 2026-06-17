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
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent
NAS_ROOT = Path("/Volumes/research")
CATEGORIAS_DIR = NAS_ROOT / "categorias"
INBOX_DIR = NAS_ROOT / "inbox"
INBOX_CSV_DIR = NAS_ROOT / "inbox_csv"
KNOWN_DOIS_FILE  = NAS_ROOT / "metadatos" / "doi_registry.txt"
QUARANTINE_DIR = NAS_ROOT / "quarantine" / "duplicates"
_KEYWORDS_PATH   = SCRIPTS_DIR.parent / "config" / "keywords.yml"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from utils.constants import OLLAMA_MODEL_EMBED  # noqa: E402

log = logging.getLogger("pipeline")

# Estructura de subcarpetas que debe tener cada proyecto/categoría
_PROJECT_SUBDIRS = [
    "pdfs", "tei", "md_clean", "summaries", "chunks",
    "embeddings", "metadata", "notebooklm_packages", "logs",
]

from utils.constants import CANONICAL_CATEGORIES as _CANONICAL_CATEGORIES


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
    screen_duplicates: bool = True,
) -> Dict[str, Any]:
    """Ejecuta la cadena de procesado completa para una categoría.

    Args:
        category:         nombre de la categoría / proyecto
        on_output:        callback para líneas de salida
        extra_args:       args extra por script, e.g. {"3_process_corpus.py": ["--force"]}
        screen_duplicates: si True, aparta PDFs duplicados antes de procesar

    Returns:
        {"status": "ok"|"error", "steps": {script: result_dict}}
    """
    if screen_duplicates:
        try:
            screen_new_pdfs_against_corpus(category, on_output=on_output)
        except Exception as e:
            log.warning("screen_new_pdfs_against_corpus(%s) falló: %s", category, e)

    # Defaults: todos los flujos usan el modelo de embedding canónico
    _default_extra: Dict[str, List[str]] = {
        "5_build_embeddings.py": ["--model", OLLAMA_MODEL_EMBED],
    }
    # Merge: primero defaults, luego args del caller (así --force se añade, no reemplaza)
    extra: Dict[str, List[str]] = {k: list(v) for k, v in _default_extra.items()}
    for script, caller_args in (extra_args or {}).items():
        extra[script] = extra.get(script, []) + caller_args

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


def _copy_files_skip_existing(src_dir: Path, dst_dir: Path) -> tuple[int, int]:
    """Copia recursivamente src_dir → dst_dir; salta ficheros ya existentes.

    Returns:
        (copied, skipped)
    """
    if not src_dir.exists():
        return 0, 0
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = skipped = 0
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(src_dir)
        dst_file = dst_dir / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        if dst_file.exists():
            skipped += 1
        else:
            shutil.copy(src_file, dst_file)
            copied += 1
    return copied, skipped


def detect_affected_categories() -> List[str]:
    """Categorías con PDFs sin procesar (comparación de stems normalizada)."""
    from utils.pdf_utils import normalize_stem  # noqa: PLC0415
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
        pdf_stems = {normalize_stem(p.stem) for p in pdfs_dir.glob("*.pdf")}
        md_stems = {
            normalize_stem(m.name[:-len(".clean.md")])
            for m in (md_dir.glob("*.clean.md") if md_dir.exists() else [])
        }
        if pdf_stems - md_stems:
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
                        key = _norm_doi_key(parts[0])
                        if key:
                            existing[key] = parts[1]

        pdfs_dir = CATEGORIAS_DIR / category / "pdfs"
        if not pdfs_dir.exists():
            return 0

        added = 0
        for pdf in sorted(pdfs_dir.glob("*.pdf")):
            doi = _norm_doi_key(extract_doi_from_pdf(pdf))
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


def _norm_doi_key(d) -> str:
    """DOI a clave comparable: minúsculas, sin prefijo doi.org, sin '/' final."""
    s = str(d or "").strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    return s.rstrip("/")


def _iter_papers_metadata(base: Path = CATEGORIAS_DIR):
    """Itera (categoria, registro_dict) de los papers_metadata.jsonl del corpus."""
    import json  # noqa: PLC0415
    if not base.exists():
        return
    for pat in ("*/metadata/papers_metadata.jsonl", "*/papers_metadata.jsonl"):
        for jf in sorted(base.glob(pat)):
            cat = jf.parent.parent.name if jf.parent.name == "metadata" else jf.parent.name
            try:
                with jf.open(encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield cat, json.loads(line)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                log.debug("No se pudo leer %s: %s", jf, e)


def _load_corpus_doi_index() -> Dict[str, str]:
    """doi(normalizado) -> 'cat/paper_id' de papers YA procesados. Primaria:
    papers_metadata.jsonl (DOI autoritativo del TEI). Respaldo: doi_registry.txt."""
    idx: Dict[str, str] = {}
    for cat, rec in _iter_papers_metadata():
        doi = _norm_doi_key(rec.get("doi"))
        if doi:
            pid = rec.get("paper_id") or rec.get("stable_id") or rec.get("source_pdf") or ""
            idx.setdefault(doi, f"{cat}/{pid}")
    if KNOWN_DOIS_FILE.exists():
        try:
            for line in KNOWN_DOIS_FILE.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split("\t", 1)
                key = _norm_doi_key(parts[0]) if parts else ""
                if key:
                    idx.setdefault(key, parts[1] if len(parts) > 1 else "?")
        except Exception:
            pass
    return idx


def _pdf_sha256(path: Path) -> str:
    import hashlib  # noqa: PLC0415
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return ""


def screen_new_pdfs_against_corpus(
    category: str,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Aparta a cuarentena los PDFs NUEVOS de categorias/<cat>/pdfs/ cuyo DOI (o
    hash idéntico) ya está en el corpus. No toca PDFs ya procesados ni borra nada:
    mueve a quarantine/duplicates/<ts>/<cat>/. Reversible.
    Returns: {"quarantined": [...], "kept": [...], "no_doi": [...]}"""
    from utils.pdf_utils import extract_doi_from_pdf, normalize_stem  # noqa: PLC0415

    pdfs_dir = CATEGORIAS_DIR / category / "pdfs"
    md_dir = CATEGORIAS_DIR / category / "md_clean"
    out: Dict[str, Any] = {"quarantined": [], "kept": [], "no_doi": []}
    if not pdfs_dir.exists():
        return out

    def emit(msg: str) -> None:
        log.info(msg)
        if on_output:
            on_output(msg)

    md_stems = {
        normalize_stem(m.name[:-len(".clean.md")])
        for m in (md_dir.glob("*.clean.md") if md_dir.exists() else [])
    }
    all_pdfs = sorted(pdfs_dir.glob("*.pdf"))
    new_pdfs = [p for p in all_pdfs if normalize_stem(p.stem) not in md_stems]
    if not new_pdfs:
        return out

    corpus_dois = _load_corpus_doi_index()
    existing_hashes = {
        _pdf_sha256(p) for p in all_pdfs if normalize_stem(p.stem) in md_stems
    }
    existing_hashes.discard("")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    qdir = QUARANTINE_DIR / ts / category
    manifest = QUARANTINE_DIR / ts / "_manifest.csv"
    seen_new: Dict[str, str] = {}
    moved: List[tuple] = []

    for pdf in new_pdfs:
        doi = _norm_doi_key(extract_doi_from_pdf(pdf))
        h = _pdf_sha256(pdf)
        reason = None
        if doi and doi in corpus_dois:
            reason = f"DOI ya en corpus ({corpus_dois[doi]})"
        elif h and h in existing_hashes:
            reason = "PDF idéntico ya en la categoría (hash)"
        elif doi and doi in seen_new:
            reason = f"DOI duplicado en este lote ({seen_new[doi]})"

        if reason:
            qdir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf), str(qdir / pdf.name))
            moved.append((category, pdf.name, reason, str(pdf)))
            out["quarantined"].append({"file": pdf.name, "reason": reason})
            emit(f"  🟡 cuarentena: {pdf.name} — {reason}")
        else:
            if doi:
                seen_new[doi] = pdf.name
            else:
                out["no_doi"].append(pdf.name)
            out["kept"].append(pdf.name)

    if moved:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["category", "filename", "reason", "original_path"])
            w.writerows(moved)
        emit(f"  → {len(moved)} PDF(s) apartados a {qdir}")
    if out["no_doi"]:
        emit(f"  ⚠️ {len(out['no_doi'])} PDF(s) sin DOI legible (no deduplicables "
             f"por DOI): {', '.join(out['no_doi'])}")
    return out


def build_doi_registry_from_nas() -> int:
    """Reconstruye doi_registry.txt con los DOIs del corpus ya procesado.
    Primaria: papers_metadata.jsonl (DOI autoritativo, limpio del TEI).
    Respaldo: extracción del PDF (solo DOIs no vistos). Línea: 'doi\\tcat/filename'."""
    registry: Dict[str, str] = {}
    for cat, rec in _iter_papers_metadata():
        doi = _norm_doi_key(rec.get("doi"))
        if not doi:
            continue
        pid = rec.get("paper_id") or rec.get("stable_id") or rec.get("source_pdf") or ""
        registry.setdefault(doi, f"{cat}/{pid}")
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from utils.pdf_utils import extract_doi_from_pdf  # noqa: PLC0415
        if CATEGORIAS_DIR.exists():
            for cat_dir in sorted(CATEGORIAS_DIR.iterdir()):
                pdfs_dir = cat_dir / "pdfs"
                if not cat_dir.is_dir() or not pdfs_dir.exists():
                    continue
                for pdf in sorted(p for p in pdfs_dir.iterdir()
                                  if p.is_file() and p.suffix.lower() == ".pdf"):
                    try:
                        doi = _norm_doi_key(extract_doi_from_pdf(pdf))
                    except Exception:
                        continue
                    if doi:
                        registry.setdefault(doi, f"{cat_dir.name}/{pdf.name}")
    except Exception as e:
        log.warning("build_doi_registry_from_nas: respaldo PDF falló: %s", e)

    KNOWN_DOIS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with KNOWN_DOIS_FILE.open("w", encoding="utf-8") as f:
        for doi, origen in sorted(registry.items()):
            f.write(f"{doi}\t{origen}\n")
    log.info("doi_registry.txt reconstruido: %d DOIs (metadata + PDFs)", len(registry))
    return len(registry)


_META_STEM_FIELDS = ("paper_id", "source_file", "pdf_file", "filename", "file", "source_pdf", "tei_file")
_META_STEM_SUFFIXES = (".tei.xml", ".clean.md", ".summary.md", ".chunks.jsonl", ".jsonl", ".xml", ".pdf")


def _record_stem(rec) -> str:
    """Stem de fichero de un registro de metadata (alineado con SOURCE_FIELDS de 9_cleanup)."""
    for field in _META_STEM_FIELDS:
        v = rec.get(field)
        if not v:
            continue
        name = Path(str(v).strip()).name
        for suf in _META_STEM_SUFFIXES:
            if name.lower().endswith(suf):
                name = name[: -len(suf)]
                break
        if name:
            return name
    return ""


def prune_orphan_metadata(
    category: str,
    apply: bool = False,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Detecta (apply=False) o elimina (apply=True) registros de papers_metadata.jsonl
    SIN md_clean correspondiente — papers fantasma / ruido del catálogo.
    Reversible: backup .bak + volcado de lo eliminado a metadata/_orphans_<ts>.jsonl
    + per_paper/<stem>* huérfanos movidos a metadata/_orphans_per_paper_<ts>/.
    NO toca FAISS (otro fichero). Returns {orphans, kept, removed, applied}."""
    import json  # noqa: PLC0415
    from utils.pdf_utils import normalize_stem  # noqa: PLC0415

    meta = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
    md_dir = CATEGORIAS_DIR / category / "md_clean"
    out: Dict[str, Any] = {"orphans": [], "kept": 0, "removed": 0, "applied": False}
    if not meta.exists():
        return out

    def emit(m: str) -> None:
        log.info(m)
        if on_output:
            on_output(m)

    md_stems = {
        normalize_stem(m.name[:-len(".clean.md")])
        for m in (md_dir.glob("*.clean.md") if md_dir.exists() else [])
    }

    kept_lines: List[str] = []
    orphan_lines: List[str] = []
    orphan_stems: List[str] = []
    with meta.open(encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            if not s.strip():
                continue
            try:
                rec = json.loads(s)
            except json.JSONDecodeError:
                kept_lines.append(s)          # líneas ilegibles: no tocar
                continue
            stem = _record_stem(rec)
            if stem and normalize_stem(stem) in md_stems:
                kept_lines.append(s)
            else:
                orphan_lines.append(s)
                orphan_stems.append(stem)
                out["orphans"].append({
                    "stem": stem or "(sin id)",
                    "doi": rec.get("doi") or "",
                    "title": (rec.get("title") or "")[:80],
                })

    out["kept"] = len(kept_lines)
    out["removed"] = len(orphan_lines)

    if not orphan_lines:
        emit(f"{category}: sin metadata huérfana ({out['kept']} registros).")
        return out

    emit(f"{category}: {out['removed']} huérfano(s) de {out['removed'] + out['kept']} registros")
    for o in out["orphans"]:
        emit(f"  · {o['stem']}  {o['doi']}  {o['title']}")

    if apply:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(meta, meta.with_name(meta.name + ".bak"))
        meta.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
        (meta.parent / f"_orphans_{ts}.jsonl").write_text(
            "\n".join(orphan_lines) + "\n", encoding="utf-8")
        per_paper = meta.parent / "per_paper"
        if per_paper.exists():
            moved_dir = meta.parent / f"_orphans_per_paper_{ts}"
            for stem in filter(None, orphan_stems):
                for pp in per_paper.glob(f"{stem}*"):
                    moved_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(pp), str(moved_dir / pp.name))
        out["applied"] = True
        emit(f"  ✓ Eliminados {out['removed']} (backup .bak + _orphans_{ts}.jsonl recuperables)")

    return out


def prune_orphan_tei(
    category: str,
    apply: bool = False,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Detecta (apply=False) o mueve a cuarentena (apply=True) ficheros
    tei/*.tei.xml SIN md_clean correspondiente — restos de procesados con
    nombres antiguos, ya saltados por 4_extract_metadata.py ('TEI huérfanos').
    Reversible: mueve a quarantine/orphan_tei/<ts>/<cat>/.
    NO toca metadata ni FAISS. Returns {"orphans": [...], "applied": bool}."""
    from utils.pdf_utils import normalize_stem  # noqa: PLC0415

    tei_dir = CATEGORIAS_DIR / category / "tei"
    md_dir = CATEGORIAS_DIR / category / "md_clean"
    out: Dict[str, Any] = {"orphans": [], "applied": False}
    if not tei_dir.exists():
        return out

    def emit(m: str) -> None:
        log.info(m)
        if on_output:
            on_output(m)

    md_stems = {
        normalize_stem(m.name[:-len(".clean.md")])
        for m in (md_dir.glob("*.clean.md") if md_dir.exists() else [])
    }

    SUF = ".tei.xml"
    orphan_files = [
        p for p in sorted(tei_dir.glob("*" + SUF))
        if normalize_stem(p.name[: -len(SUF)]) not in md_stems
    ]
    out["orphans"] = [p.name for p in orphan_files]
    if not orphan_files:
        emit(f"{category}: sin TEI huérfanos.")
        return out

    emit(f"{category}: {len(orphan_files)} TEI huérfano(s) (sin md_clean):")
    for p in orphan_files:
        emit(f"  · {p.name}")

    if apply:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        qdir = QUARANTINE_DIR.parent / "orphan_tei" / ts / category
        qdir.mkdir(parents=True, exist_ok=True)
        for p in orphan_files:
            shutil.move(str(p), str(qdir / p.name))
        out["applied"] = True
        emit(f"  ✓ Movidos {len(orphan_files)} a {qdir}")
    return out


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

    # --- Filtro de categorías activas ---
    # Solo se aplica en el flujo automático (sin categorías explícitas); una
    # petición explícita del usuario tiene prioridad sobre active_categories.yml.
    if not categories:
        try:
            from utils.constants import CANONICAL_CATEGORIES as _ALL_CATS
            _config_path = Path(__file__).parent.parent / "config" / "active_categories.yml"
            if _config_path.exists():
                import yaml as _yaml
                _active = _yaml.safe_load(_config_path.read_text(encoding="utf-8")).get("active", _ALL_CATS)
                target_cats = [c for c in target_cats if c in _active]
                log.info("Categorías activas tras filtro: %s", target_cats)
        except Exception as e:
            log.warning("No se pudo leer active_categories.yml: %s", e)

    # Actualizar doi_registry antes de descargar para evitar duplicados
    log.info("Actualizando registro de DOIs antes de descargar...")
    try:
        n_dois = build_doi_registry_from_nas()
        log.info("Registro actualizado: %d DOIs conocidos en el NAS", n_dois)
        if handler:
            handler(f"✓ Registro DOIs actualizado: {n_dois} DOIs conocidos")
    except Exception as e:
        log.warning("No se pudo actualizar doi_registry.txt: %s", e)

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
            ["--csv", str(csv_path), "--out-dir", str(pdfs_dir), "--category", cat],
            on_output=handler,
            label=f"download [{cat}]",
        )

        if dl_result["returncode"] != 0:
            results[cat] = {"status": "error", "stage": "download", "details": dl_result}
            continue

        # Renombrar PDFs por DOI antes de procesar.
        # --doi-csv usa el CSV de Scopus como fuente primaria del DOI (por título),
        # más fiable que extraerlo del texto del PDF.
        rename_result = run_step(
            "1_rename_papers_by_doi.py",
            ["--folder", str(pdfs_dir),
             "--apply",
             "--doi-csv", str(csv_path)],
            on_output=handler,
            label=f"rename [{cat}]",
        )
        if rename_result["returncode"] != 0:
            log.warning("Renombrado falló para '%s', continuamos con nombres originales", cat)

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

    # Renombrar PDFs por DOI antes de procesar
    rename_result = run_step(
        "1_rename_papers_by_doi.py",
        ["--folder", str(INBOX_DIR), "--apply"],
        on_output=handler,
        label="rename [inbox]",
    )
    if rename_result["returncode"] != 0:
        log.warning("Renombrado falló en inbox, continuamos")

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

    if overall != "error":
        _pending_csv = NAS_ROOT / "metadatos" / "cribado_pendiente.csv"
        try:
            if _pending_csv.exists():
                _pending_csv.unlink()
                log.info("cribado_pendiente.csv eliminado tras procesado exitoso.")
        except Exception as e:
            log.warning("No se pudo eliminar cribado_pendiente.csv: %s", e)

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
    if not re.fullmatch(r'^[a-z0-9_-]+$', name):
        raise ValueError(f"Nombre de proyecto inválido '{name}': solo minúsculas, dígitos, '_' y '-'")
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

    # Renombrar por DOI antes de procesar para que paper_id == nombre final del PDF
    rename_result = run_step(
        "1_rename_papers_by_doi.py",
        ["--folder", str(dest_pdfs), "--apply"],
        on_output=on_output,
        label=f"rename [{name}]",
    )
    if rename_result["returncode"] != 0:
        log.warning("run_adhoc: renombrado falló — continuando con nombres originales")

    # Cadena de procesado
    proc_result = process_category(name, on_output=on_output, screen_duplicates=False)

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


# ═══════════════════════════════════════════════════════════════════════════
# FLUJO D — Integrar ad-hoc en categoría canónica
# ═══════════════════════════════════════════════════════════════════════════

def integrate_adhoc(
    adhoc_name: str,
    target_category: str,
    delete_source: bool = False,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Integra un proyecto ad-hoc en una categoría canónica.

    Copia los artefactos ya generados (pdfs/, md_clean/, summaries/, chunks/,
    metadata/) de categorias/<adhoc>/ a categorias/<target>/, saltando ficheros
    que ya existen. Después re-indexa solo FAISS del target; el skip logic de
    los demás scripts protege los artefactos ya presentes.

    Args:
        adhoc_name:      nombre del proyecto ad-hoc (debe existir en categorias/)
        target_category: categoría canónica destino (debe estar en _CANONICAL_CATEGORIES)
        delete_source:   si True, borra categorias/<adhoc>/ tras integrar
        on_output:       callback para líneas de salida

    Returns:
        {"status": "ok"|"error", "copied_pdfs": N, "skipped_pdfs": N,
         "totals": {subdir: {"copied": N, "skipped": N}}, ...}
    """
    check_nas()
    handler = _make_output_handler(on_output)

    adhoc_dir  = CATEGORIAS_DIR / adhoc_name
    target_dir = CATEGORIAS_DIR / target_category

    # ── Validaciones ──────────────────────────────────────────────────────
    if not adhoc_dir.exists():
        msg = f"Proyecto ad-hoc no encontrado: {adhoc_dir}"
        handler(f"❌ {msg}")
        return {"status": "error", "message": msg}

    if target_category not in _CANONICAL_CATEGORIES:
        msg = f"'{target_category}' no es una categoría canónica válida"
        handler(f"❌ {msg}")
        return {"status": "error", "message": msg}

    handler(f"Integrando '{adhoc_name}' → '{target_category}'")
    log.info("integrate_adhoc: %s → %s (delete_source=%s)", adhoc_name, target_category, delete_source)

    # ── Asegurar estructura en el destino ─────────────────────────────────
    ensure_project_dirs(target_category)

    # ── Copiar solo PDFs (artefactos se regeneran con nombre correcto tras renombrado) ──
    cp_pdfs, sk_pdfs = _copy_files_skip_existing(
        adhoc_dir / "pdfs", target_dir / "pdfs"
    )
    totals: Dict[str, Dict[str, int]] = {
        "pdfs": {"copied": cp_pdfs, "skipped": sk_pdfs}
    }
    handler(f"  pdfs/: {cp_pdfs} copiados, {sk_pdfs} ya existían")

    copied_pdfs  = cp_pdfs
    skipped_pdfs = sk_pdfs

    # ── Renombrar por DOI antes de procesar ───────────────────────────────
    handler(f"\nRenombrando PDFs por DOI en '{target_category}'…")
    rename_result = run_step(
        "1_rename_papers_by_doi.py",
        ["--folder", str(target_dir / "pdfs"), "--apply"],
        on_output=handler,
        label=f"rename [{target_category}]",
    )
    if rename_result["returncode"] != 0:
        log.warning("integrate_adhoc: renombrado falló — continuando con nombres originales")

    # ── Cadena de procesado completa (skip logic protege artefactos existentes) ──
    handler(f"\nProcesando cadena completa para '{target_category}'…")
    proc_result = process_category(
        target_category,
        on_output=handler,
        extra_args={"5_build_embeddings.py": ["--force"]},
    )

    if proc_result["status"] != "ok":
        log.error("integrate_adhoc: falló process_category para '%s'", target_category)
        return {
            "status":  "error",
            "message": "Falló el procesado de la categoría",
            "totals":  totals,
            "proc":    proc_result,
        }

    # ── Borrar fuente si se pidió ─────────────────────────────────────────
    if delete_source:
        shutil.rmtree(adhoc_dir, ignore_errors=True)
        handler(f"🗑  Proyecto ad-hoc '{adhoc_name}' eliminado.")
        log.info("integrate_adhoc: borrado %s", adhoc_dir)

    handler(f"\n✓ Integración completada: {copied_pdfs} PDFs nuevos añadidos a '{target_category}'")

    return {
        "status":          "ok",
        "adhoc":           adhoc_name,
        "target_category": target_category,
        "copied_pdfs":     copied_pdfs,
        "skipped_pdfs":    skipped_pdfs,
        "totals":          totals,
        "deleted_source":  delete_source,
    }


# ═══════════════════════════════════════════════════════════════════════════
# FLUJO E — Promover ad-hoc a nueva categoría canónica
# ═══════════════════════════════════════════════════════════════════════════

def promote_adhoc_to_category(
    adhoc_name: str,
    new_name: str,
    keywords: List[str],
    delete_source: bool = False,
    on_output: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Promueve un proyecto ad-hoc a una nueva categoría canónica.

    Crea categorias/<new_name>/, copia todos los artefactos del ad-hoc
    (incluyendo embeddings), añade las keywords al YAML y opcionalmente
    borra el proyecto de origen.

    Args:
        adhoc_name:    nombre del proyecto ad-hoc existente
        new_name:      nombre de la nueva categoría (^[a-z0-9_]+$)
        keywords:      lista de keywords para keywords.yml
        delete_source: si True, borra categorias/<adhoc_name>/ tras promover
        on_output:     callback para líneas de salida

    Returns:
        {"status": "ok"|"error", "new_category": str, "copied_pdfs": int,
         "totals": {subdir: {"copied": N, "skipped": N}},
         "keywords_added": int, "deleted_source": bool}
    """
    check_nas()
    handler = _make_output_handler(on_output)

    # ── Validaciones ──────────────────────────────────────────────────────
    if not re.fullmatch(r"[a-z0-9_-]+", new_name):
        msg = f"Nombre inválido '{new_name}': solo letras minúsculas, dígitos, '_' y '-'"
        handler(f"❌ {msg}")
        return {"status": "error", "message": msg}

    new_dir   = CATEGORIAS_DIR / new_name
    adhoc_dir = CATEGORIAS_DIR / adhoc_name

    if new_dir.exists():
        msg = f"Ya existe una categoría con el nombre '{new_name}'"
        handler(f"❌ {msg}")
        return {"status": "error", "message": msg}

    if not adhoc_dir.exists():
        msg = f"Proyecto ad-hoc no encontrado: {adhoc_dir}"
        handler(f"❌ {msg}")
        return {"status": "error", "message": msg}

    handler(f"Promoviendo '{adhoc_name}' → nueva categoría '{new_name}'")
    log.info("promote_adhoc_to_category: %s → %s (delete_source=%s)",
             adhoc_name, new_name, delete_source)

    # ── Crear estructura en el destino ────────────────────────────────────
    ensure_project_dirs(new_name)

    # ── Copiar artefactos (incluye embeddings) ────────────────────────────
    _COPY_SUBDIRS = ["pdfs", "md_clean", "summaries", "chunks", "metadata", "embeddings"]
    totals: Dict[str, Dict[str, int]] = {}

    for subdir in _COPY_SUBDIRS:
        src = adhoc_dir / subdir
        dst = new_dir / subdir
        cp, sk = _copy_files_skip_existing(src, dst)
        totals[subdir] = {"copied": cp, "skipped": sk}
        if cp or sk:
            handler(f"  {subdir}/: {cp} copiados, {sk} ya existían")

    copied_pdfs = totals.get("pdfs", {}).get("copied", 0)

    # ── Actualizar keywords.yml ───────────────────────────────────────────
    kw_added = 0
    try:
        existing_data: dict = {}
        if _KEYWORDS_PATH.exists():
            existing_data = yaml.safe_load(_KEYWORDS_PATH.read_text(encoding="utf-8")) or {}

        # Backup antes de modificar
        if _KEYWORDS_PATH.exists():
            bak = _KEYWORDS_PATH.with_suffix(".yml.bak")
            bak.write_text(_KEYWORDS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

        clean_kw = [k.strip() for k in keywords if k.strip()]
        existing_data[new_name] = clean_kw
        _KEYWORDS_PATH.write_text(
            yaml.safe_dump(existing_data, allow_unicode=True, default_flow_style=False,
                           sort_keys=False),
            encoding="utf-8",
        )
        kw_added = len(clean_kw)
        handler(f"  keywords.yml: {kw_added} keywords añadidas para '{new_name}'")
    except Exception as e:
        handler(f"  ⚠️ No se pudo actualizar keywords.yml: {e}")
        log.warning("promote_adhoc_to_category: error actualizando keywords.yml: %s", e)

    # ── Borrar fuente si se pidió ─────────────────────────────────────────
    if delete_source:
        shutil.rmtree(adhoc_dir, ignore_errors=True)
        handler(f"🗑  Proyecto ad-hoc '{adhoc_name}' eliminado.")
        log.info("promote_adhoc_to_category: borrado %s", adhoc_dir)

    handler(f"\n✓ Nueva categoría '{new_name}' creada con {copied_pdfs} PDFs")

    return {
        "status":         "ok",
        "new_category":   new_name,
        "copied_pdfs":    copied_pdfs,
        "totals":         totals,
        "keywords_added": kw_added,
        "deleted_source": delete_source,
    }


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
