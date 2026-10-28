#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
9_cleanup_duplicates.py — Mantenimiento del pipeline research_agent

Detecta y elimina artículos duplicados por DOI dentro de cada categoría
y entre categorías. Usa papers_metadata.jsonl como fuente de verdad.

Criterio de desempate para elegir cuál conservar (en orden de prioridad):
    1. Nombre limpio Crossref (todo minúsculas, sin DOI embebido en el stem)
    2. Mayor completeness (campos no vacíos en metadata)
    3. Stem alfabéticamente menor
    4. Número de línea en el JSONL

Modos de operación:
    --preview   Solo muestra duplicados detectados, sin modificar nada (defecto)
    --apply     Elimina los secundarios y reescribe papers_metadata.jsonl con backup

Ficheros leídos:
    /Volumes/research/categorias/<categoria>/metadata/papers_metadata.jsonl
    /Volumes/research/categorias/                      ← estructura completa de artefactos

Ficheros escritos (solo con --apply):
    /Volumes/research/categorias/<categoria>/metadata/
        papers_metadata.jsonl          ← reescrito sin duplicados
        papers_metadata.jsonl.bak      ← backup del original
    /Volumes/research/categorias/<categoria>/
        pdfs/<paper_id>.pdf            ← eliminado (duplicado secundario)
        tei/<paper_id>.tei.xml         ← eliminado
        md_clean/<paper_id>.clean.md   ← eliminado
        chunks/<paper_id>.jsonl        ← eliminado
        summaries/<paper_id>.summary.md← eliminado
        metadata/per_paper/<paper_id>* ← eliminado
    logs/9_cleanup_duplicates.log

Parámetros CLI:
    --preview             Solo muestra duplicados (sin modificar nada)
    --apply               Elimina duplicados y reescribe JSONL
    --category CAT        Procesa solo esta categoría (defecto: todas)
    --doi DOI             Muestra el grupo de duplicados para un DOI concreto
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)

Dependencias:
    (solo stdlib)

Notas:
    - Ejecutar --preview periódicamente, especialmente tras ingestas masivas
      o renombrados por Crossref.
    - Tras --apply, el script indica qué categorías necesitan re-indexado FAISS:
      python3 5_build_embeddings.py --project <cat> --model bge-m3 --force
    - La detección es solo por DOI idéntico. Duplicados por título similar o
      mismo autor+año se tratan en el item 19 (detección avanzada, pendiente).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


# ============================================================
# CONSTANTES
# ============================================================

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "9_cleanup_duplicates.log"

DEFAULT_BASE = Path("/Volumes/research/categorias")

CATEGORIES = [
    "biological_gas_odor_treatment",
    "anoxic_biogas_biodesulfurization",
    "bioplastics_microplastics",
    "biogas_upgrading_biomethanation",
    "microalgae",
    "single_cell_protein",
    "advanced_oxidation_processes",
    "bioleaching_critical_materials",
]

SOURCE_FIELDS = [
    "paper_id",
    "source_file",
    "pdf_file",
    "filename",
    "file",
    "source_pdf",
    "tei_file",
]

CATEGORY_KEYWORDS = {
    "biological_gas_odor_treatment": {
        "odor", "odour", "biofilter", "biofiltration", "voc", "volatile", "gas treatment",
    },
    "anoxic_biogas_biodesulfurization": {
        "anoxic", "biodesulfurization", "biodesulphurization", "desulfurization",
        "desulphurization", "h2s", "hydrogen sulfide", "nitrate", "nitrite",
    },
    "bioplastics_microplastics": {
        "bioplastic", "bioplastics", "microplastic", "microplastics", "pla", "pbat",
        "pha", "biodegradation",
    },
    "biogas_upgrading_biomethanation": {
        "biogas upgrading", "biomethanation", "methanation", "biomethane",
        "methane", "co2", "trickle bed",
    },
    "microalgae": {
        "microalgae", "microalga", "algae", "algal", "chlorella", "spirulina",
        "scenedesmus", "photobioreactor",
    },
    "single_cell_protein": {
        "single cell protein", "scp", "microbial protein", "protein production",
        "protein-rich", "protein rich",
    },
    "advanced_oxidation_processes": {
        "advanced oxidation", "aop", "photocatalysis", "fenton", "ozonation",
        "persulfate", "hydroxyl radical",
    },
    "bioleaching_critical_materials": {
        "bioleaching", "critical materials", "critical raw materials", "rare earth",
        "lithium", "cobalt", "nickel", "e-waste", "electronic waste",
    },
}

PDF_EXTS = [".pdf", ".PDF"]
_PREFIX_MATCH_MIN_KEY = 60  # longitud mínima de file_key para el match por prefijo de PDF

log = logging.getLogger("cleanup_duplicates")


# ============================================================
# MODELOS
# ============================================================

@dataclass(frozen=True)
class PaperRecord:
    doi: str
    category: str
    stem: str
    metadata_path: Path
    line_no: int
    raw_line: str
    data: dict[str, Any]
    source_field: str


@dataclass(frozen=True)
class DuplicateDecision:
    doi: str
    duplicate_type: str
    keep: PaperRecord
    remove: PaperRecord
    reason: str


# ============================================================
# LOGGING
# ============================================================

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cleanup_duplicates")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)
    return logger


# ============================================================
# UTILIDADES
# ============================================================

def normalize_doi(doi: Any) -> str:
    value = str(doi or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = value.rstrip("/")
    return value


def strip_known_suffixes(name: str) -> str:
    for suffix in (".tei.xml", ".clean.md", ".summary.md", ".chunks.jsonl", ".jsonl", ".xml", ".pdf"):
        if name.lower().endswith(suffix.lower()):
            return name[: -len(suffix)]
    return name


def infer_stem(rec: dict[str, Any]) -> tuple[Optional[str], str]:
    for field in SOURCE_FIELDS:
        value = rec.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if not value:
            continue
        stem = strip_known_suffixes(Path(str(value)).name)
        if stem:
            return stem, field
    return None, ""


def nonempty_score(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return 1 if value.strip() else 0
    if isinstance(value, (list, tuple, set, dict)):
        return 1 if value else 0
    return 1


def metadata_completeness(rec: PaperRecord) -> int:
    return sum(nonempty_score(v) for v in rec.data.values())


def category_relevance_score(rec: PaperRecord) -> int:
    text = " ".join(
        str(rec.data.get(k) or "")
        for k in ("title", "abstract", "journal", "phase", "project")
    ).lower()
    return sum(1 for kw in CATEGORY_KEYWORDS.get(rec.category, set()) if kw in text)


def file_key(stem: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def _is_clean_stem(stem: str) -> bool:
    """True si el stem es nombre limpio Crossref: todo minúsculas y sin DOI embebido."""
    if stem != stem.lower():
        return False
    if re.search(r"_10_\d{4,5}_", stem):
        return False
    return True


def category_dirs(base: Path, selected: Optional[list[str]]) -> list[str]:
    cats = selected or CATEGORIES
    return sorted(dict.fromkeys(cats))


def read_metadata(category: str, base: Path) -> list[PaperRecord]:
    meta_path = base / category / "metadata" / "papers_metadata.jsonl"
    if not meta_path.exists():
        log.warning("⚠ No existe metadata, salto categoría: %s", meta_path)
        return []

    records: list[PaperRecord] = []
    with meta_path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("⚠ JSON inválido en %s:%d: %s", meta_path, line_no, exc)
                continue

            doi = normalize_doi(data.get("doi"))
            if not doi:
                continue
            stem, source_field = infer_stem(data)
            if not stem:
                log.warning("⚠ Registro con DOI sin identificador de archivo en %s:%d (%s)", meta_path, line_no, doi)
                continue
            records.append(
                PaperRecord(
                    doi=doi,
                    category=category,
                    stem=stem,
                    metadata_path=meta_path,
                    line_no=line_no,
                    raw_line=line,
                    data=data,
                    source_field=source_field,
                )
            )
    log.debug("Leídos %d registros con DOI de %s", len(records), meta_path)
    return records


def build_registry(categories: list[str], base: Path) -> dict[str, list[PaperRecord]]:
    registry: dict[str, list[PaperRecord]] = defaultdict(list)
    for category in categories:
        for rec in read_metadata(category, base):
            registry[rec.doi].append(rec)
    return dict(registry)


def build_stem_index(registry: dict[str, list[PaperRecord]]) -> dict[tuple[str, str], PaperRecord]:
    """Índice {(category, stem): PaperRecord} para lookup desde hash_dups."""
    index: dict[tuple[str, str], PaperRecord] = {}
    for records in registry.values():
        for rec in records:
            index[(rec.category, rec.stem)] = rec
    return index


def choose_keep_intra(records: list[PaperRecord]) -> tuple[PaperRecord, str]:
    ordered = sorted(
        records,
        key=lambda r: (not _is_clean_stem(r.stem), -metadata_completeness(r), r.stem.lower(), r.line_no),
    )
    keep = ordered[0]
    reason = (
        f"metadata más completa ({metadata_completeness(keep)} campos no vacíos); "
        "desempate: nombre limpio Crossref > mayúsculas/DOI embebido > stem alfabético"
    )
    return keep, reason


def choose_keep_cross(records: list[PaperRecord]) -> tuple[PaperRecord, str]:
    relevance = {r: category_relevance_score(r) for r in records}
    best_score = max(relevance.values())
    best = [r for r, score in relevance.items() if score == best_score]
    if best_score > 0 and len(best) == 1:
        keep = best[0]
        return keep, f"categoría más específica por keywords ({best_score} coincidencias)"

    ordered = sorted(
        records,
        key=lambda r: (not _is_clean_stem(r.stem), r.category.lower(), -metadata_completeness(r), r.stem.lower(), r.line_no),
    )
    keep = ordered[0]
    return keep, "sin categoría específica obvia; primera por orden alfabético de categoría"


def decide_duplicates(registry: dict[str, list[PaperRecord]]) -> list[DuplicateDecision]:
    decisions: list[DuplicateDecision] = []
    for doi, records in sorted(registry.items()):
        if len(records) < 2:
            continue

        by_category: dict[str, list[PaperRecord]] = defaultdict(list)
        for rec in records:
            by_category[rec.category].append(rec)

        # Intra-categoría: decide dentro de cada categoría.
        for category, group in sorted(by_category.items()):
            if len(group) < 2:
                continue
            keep, reason = choose_keep_intra(group)
            for remove in sorted((r for r in group if r != keep), key=lambda r: (r.stem.lower(), r.line_no)):
                decisions.append(
                    DuplicateDecision(
                        doi=doi,
                        duplicate_type="intra",
                        keep=keep,
                        remove=remove,
                        reason=reason,
                    )
                )

        # Cross-categoría: usa un candidato por categoría para no mezclar
        # duplicados internos con la decisión global.
        category_representatives: list[PaperRecord] = []
        for group in by_category.values():
            if len(group) == 1:
                category_representatives.append(group[0])
            else:
                keep, _ = choose_keep_intra(group)
                category_representatives.append(keep)

        if len(category_representatives) < 2:
            continue
        keep_cross, reason = choose_keep_cross(category_representatives)
        for remove in sorted(
            (r for r in category_representatives if r != keep_cross),
            key=lambda r: (r.category.lower(), r.stem.lower(), r.line_no),
        ):
            decisions.append(
                DuplicateDecision(
                    doi=doi,
                    duplicate_type="cross",
                    keep=keep_cross,
                    remove=remove,
                    reason=reason,
                )
            )

    return dedupe_removals(decisions)


def dedupe_removals(decisions: list[DuplicateDecision]) -> list[DuplicateDecision]:
    """Evita intentar eliminar dos veces el mismo registro en casos mixtos."""
    seen: set[tuple[str, str, int, str]] = set()
    out: list[DuplicateDecision] = []
    for dec in decisions:
        key = (dec.remove.category, str(dec.remove.metadata_path), dec.remove.line_no, dec.remove.stem)
        if key in seen:
            continue
        seen.add(key)
        out.append(dec)
    return out


def pairwise_rows(decisions: list[DuplicateDecision]) -> list[tuple[str, str, str, str, str, str]]:
    rows = []
    for dec in decisions:
        rows.append((
            dec.doi,
            dec.keep.category,
            dec.keep.stem,
            dec.remove.category,
            dec.remove.stem,
            dec.duplicate_type,
        ))
    return rows


def print_table(rows: list[tuple[str, str, str, str, str, str]]) -> None:
    headers = ("DOI", "categoría_1", "archivo_1", "categoría_2", "archivo_2", "tipo")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = min(max(widths[i], len(cell)), 52)

    def fmt_cell(cell: str, width: int) -> str:
        if len(cell) > width:
            cell = cell[: width - 1] + "…"
        return cell.ljust(width)

    print(" | ".join(fmt_cell(h, widths[i]) for i, h in enumerate(headers)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(fmt_cell(cell, widths[i]) for i, cell in enumerate(row)))


def summarize(decisions: list[DuplicateDecision]) -> None:
    intra = [d for d in decisions if d.duplicate_type == "intra"]
    cross = [d for d in decisions if d.duplicate_type == "cross"]
    intra_categories = {d.remove.category for d in intra}
    print("")
    print(f"Duplicados intra-categoría: {len(intra)} en {len(intra_categories)} categorías")
    print(f"Duplicados cross-categoría: {len(cross)}")


def print_decision_details(decisions: list[DuplicateDecision]) -> None:
    if not decisions:
        return
    print("")
    print("Decisiones:")
    for dec in decisions:
        print(f"- DOI {dec.doi} [{dec.duplicate_type}]")
        print(f"  Conserva: {dec.keep.category}/{dec.keep.stem}")
        print(f"  Elimina : {dec.remove.category}/{dec.remove.stem}")
        print(f"  Motivo  : {dec.reason}")


def candidate_paths(project_dir: Path, stem: str) -> list[Path]:
    candidates: list[Path] = []
    candidates.extend(project_dir / "pdfs" / f"{stem}{ext}" for ext in PDF_EXTS)
    candidates.append(project_dir / "tei" / f"{stem}.tei.xml")
    candidates.append(project_dir / "tei" / f"{stem}.xml")
    candidates.append(project_dir / "md_clean" / f"{stem}.clean.md")
    candidates.append(project_dir / "summaries" / f"{stem}.summary.md")
    candidates.append(project_dir / "chunks" / f"{stem}.chunks.jsonl")
    candidates.append(project_dir / "chunks" / f"{stem}.jsonl")

    # Fallback difuso: localiza también artefactos antiguos cuyo nombre difiere
    # levemente del stem (guiones, espacios o corchetes) pero conserva la misma
    # clave normalizada. Antes esto solo cubría pdfs/; sin cubrir también
    # tei/md_clean/chunks/summaries, una cuarentena podía mover el PDF y dejar
    # huérfanos el resto de artefactos (o viceversa), que luego "resucitaban"
    # al reprocesar la categoría.
    target_key = file_key(stem)
    _FUZZY_DIRS = (
        ("pdfs",      tuple(PDF_EXTS)),
        ("tei",       (".tei.xml", ".xml")),
        ("md_clean",  (".clean.md",)),
        ("summaries", (".summary.md",)),
        ("chunks",    (".chunks.jsonl", ".jsonl")),
    )
    for sub, exts in _FUZZY_DIRS:
        sub_dir = project_dir / sub
        if not sub_dir.exists():
            continue
        for f in sub_dir.iterdir():
            if not f.is_file():
                continue
            for ext in exts:
                if f.name.endswith(ext) and file_key(f.name[: -len(ext)]) == target_key:
                    candidates.append(f)
                    break

    # Fallback por prefijo (solo pdfs/): el stem del paper_id puede estar
    # truncado respecto al nombre real del PDF (p.ej. stem "..._Thiobacil_10_108"
    # vs PDF "... Thiobacil [10.1080_0959...].pdf"). Exige una clave larga para
    # no confundir papers distintos con títulos que empiezan igual.
    if len(target_key) >= _PREFIX_MATCH_MIN_KEY:
        pdf_dir = project_dir / "pdfs"
        if pdf_dir.exists():
            for f in pdf_dir.iterdir():
                if f.is_file() and f.suffix in PDF_EXTS and \
                        file_key(f.stem).startswith(target_key):
                    candidates.append(f)

    seen: set[Path] = set()
    unique = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def delete_secondary_files(rec: PaperRecord, base: Path) -> list[Path]:
    project_dir = base / rec.category
    deleted: list[Path] = []
    for path in candidate_paths(project_dir, rec.stem):
        if path.exists():
            path.unlink()
            deleted.append(path)
            log.info("Eliminado: %s", path)
        else:
            log.warning("No existe, continúo: %s", path)
    return deleted


# Ficheros auxiliares con una fila/línea por paper_id que quarantine_paper() limpia
# (item 72). Rutas relativas a la categoría.
def _aux_line_files(category: str) -> list[tuple[str, str]]:
    return [
        (f"metadata/validation_{category}.jsonl", "jsonl"),
        ("logs/3_process_corpus_report.csv", "csv"),
        ("logs/3b_summarize_report.csv", "csv"),
    ]


def _strip_paper_lines(path: Path, fmt: str, target_key: str) -> list[str]:
    """Quita de `path` las líneas cuyo paper_id (file_key) == target_key y las
    devuelve tal cual (para guardarlas en el manifiesto). Backup `.bak`."""
    if not path.exists():
        return []
    has_bom = path.read_bytes()[:3] == b"\xef\xbb\xbf"
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines:
        return []
    kept: list[str] = []
    removed: list[str] = []
    idx = None
    body = lines
    if fmt == "csv":
        hdr = next(csv.reader([lines[0]]))
        if "paper_id" not in hdr:
            return []
        idx = hdr.index("paper_id")
        kept.append(lines[0])
        body = lines[1:]
    for ln in body:
        if not ln.strip():
            continue
        pid = ""
        try:
            if fmt == "csv":
                row = next(csv.reader([ln]))
                pid = row[idx] if idx < len(row) else ""
            else:
                pid = json.loads(ln).get("paper_id") or ""
        except Exception:
            pass
        if pid and file_key(pid) == target_key:
            removed.append(ln)
        else:
            kept.append(ln)
    if removed:
        shutil.copy(path, path.with_name(path.name + ".bak"))
        path.write_text("\n".join(kept) + "\n", encoding="utf-8-sig" if has_bom else "utf-8")
    return removed


def quarantine_paper(category: str, paper_id: str, base: Path, dest_root: Path) -> tuple[list[tuple[Path, Path]], bool]:
    """Mueve los artefactos de un paper a cuarentena (reversible) y lo quita de
    papers_metadata.jsonl. Devuelve (lista de (origen, destino) movidos, metadata_actualizada)."""
    project_dir = base / category
    dest_dir = Path(dest_root) / category
    moved: list[tuple[Path, Path]] = []

    # Quitar del papers_metadata.jsonl por file_key del stem (con backup .bak).
    # Se hace ANTES de mover ficheros para poder usar el DOI retirado como
    # último fallback al localizar el PDF (ver más abajo).
    meta_path = project_dir / "metadata" / "papers_metadata.jsonl"
    meta_updated = False
    removed_lines: list[str] = []
    removed_doi = ""
    if meta_path.exists():
        target_key = file_key(paper_id)
        kept: list[str] = []
        with meta_path.open(encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    data = json.loads(s)
                except Exception:
                    kept.append(line.rstrip("\n")); continue
                stem, _ = infer_stem(data)
                if stem and file_key(stem) == target_key:
                    removed_lines.append(line.rstrip("\n"))
                    removed_doi = normalize_doi(data.get("doi") or "") or removed_doi
                    continue
                kept.append(line.rstrip("\n"))
        if removed_lines:
            shutil.copy(meta_path, meta_path.with_name(meta_path.name + ".bak"))
            meta_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            meta_updated = True
            log.info("Metadata: %d línea(s) quitada(s) de %s", len(removed_lines), meta_path)

    # references.jsonl: quitar las referencias extraídas de este paper (item 70).
    # Antes quedaban como filas huérfanas bajo un paper_id que ya no existe.
    # Se guardan en el manifiesto para que restore_from_quarantine() las devuelva.
    removed_refs: list[str] = []
    refs_path = project_dir / "metadata" / "references.jsonl"
    if refs_path.exists():
        target_key = file_key(paper_id)
        kept_refs: list[str] = []
        with refs_path.open(encoding="utf-8") as f:
            for line in f:
                s = line.rstrip("\n")
                if not s.strip():
                    continue
                try:
                    rid = json.loads(s).get("paper_id") or ""
                except Exception:
                    kept_refs.append(s); continue
                if rid and file_key(rid) == target_key:
                    removed_refs.append(s)
                else:
                    kept_refs.append(s)
        if removed_refs:
            shutil.copy(refs_path, refs_path.with_name(refs_path.name + ".bak"))
            refs_path.write_text("\n".join(kept_refs) + ("\n" if kept_refs else ""),
                                 encoding="utf-8")
            log.info("References: %d línea(s) quitada(s) de %s", len(removed_refs), refs_path)

    # Sidecar de validación + informes de logs/: una fila por paper (item 72).
    extra_lines: dict[str, list[str]] = {}
    for rel, fmt in _aux_line_files(category):
        got = _strip_paper_lines(project_dir / rel, fmt, file_key(paper_id))
        if got:
            extra_lines[rel] = got

    # Artefactos estándar (pdf, tei, md_clean, summary, chunks) vía candidate_paths
    paths = list(candidate_paths(project_dir, paper_id))
    # logs/<stem>.log (reversible: viaja a cuarentena con el resto)
    log_f = project_dir / "logs" / f"{paper_id}.log"
    if log_f.exists():
        paths.append(log_f)
    # per_paper/<stem>*
    per_paper = project_dir / "metadata" / "per_paper"
    if per_paper.exists():
        paths.extend(sorted(per_paper.glob(f"{paper_id}*")))

    # Fallback por DOI: si ni el match exacto ni el difuso de candidate_paths
    # localizaron ningún PDF (nombre del PDF demasiado distinto del stem,
    # p.ej. nunca renombrado), busca en pdfs/ uno cuyo DOI embebido coincida
    # con el de la metadata retirada. Sin esto, ese PDF quedaba huérfano en
    # pdfs/ tras la cuarentena y "resucitaba" (se reprocesaba como nuevo) en
    # el siguiente reproceso de la categoría.
    if removed_doi and not any(p.suffix in PDF_EXTS and p.exists() for p in paths):
        pdf_dir = project_dir / "pdfs"
        if pdf_dir.exists():
            try:
                from utils.pdf_utils import extract_doi_from_pdf  # perezoso: PyMuPDF
            except Exception:
                extract_doi_from_pdf = None
            if extract_doi_from_pdf is not None:
                for pdf in sorted(pdf_dir.iterdir()):
                    if pdf.is_file() and pdf.suffix in PDF_EXTS:
                        found = normalize_doi(extract_doi_from_pdf(pdf) or "")
                        if found and found == removed_doi:
                            paths.append(pdf)
                            log.info("PDF localizado por DOI (nombre no coincidía): %s", pdf)
                            break

    for path in paths:
        if path.exists():
            rel = path.relative_to(project_dir)
            target = dest_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))   # mismo volumen (SSD) → rename rápido
            moved.append((path, target))
            log.info("Cuarentena: %s -> %s", path, target)

    # Manifiesto para poder restaurar (ficheros movidos + líneas de metadata retiradas)
    if moved or removed_lines or removed_refs or extra_lines:
        dest_dir.mkdir(parents=True, exist_ok=True)
        manifest = dest_dir / f"_manifest_{paper_id}.json"
        manifest.write_text(json.dumps(
            {"category": category, "paper_id": paper_id,
             "moved": [[str(o), str(t)] for o, t in moved],
             "meta_lines": removed_lines,
             "refs_lines": removed_refs,
             "extra_lines": extra_lines},
            indent=2, ensure_ascii=False), encoding="utf-8")
    return moved, meta_updated


def restore_from_quarantine(
    manifest_path: Path, base: Path
) -> tuple[list[tuple[Path, Path]], bool, list[str]]:
    """Restaura (reversible) un paper desde cuarentena a partir de su manifiesto.

    Inverso de quarantine_paper(): devuelve los artefactos a su sitio y reañade
    las líneas retiradas de papers_metadata.jsonl, sin sobrescribir nada existente.

    Devuelve (restaurados, meta_updated, warnings):
      - restaurados: lista de (orig, target) devueltos a su ubicación original.
      - meta_updated: True si se reescribió papers_metadata.jsonl con líneas recuperadas.
      - warnings: incidencias no fatales (ficheros no restaurables, manifiesto antiguo…).
    """
    warnings: list[str] = []
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    category = data.get("category", "")
    moved = data.get("moved", []) or []
    meta_lines = data.get("meta_lines", []) or []

    # ── Ficheros: mover de vuelta solo si el destino no existe ya ─────────────
    restored: list[tuple[Path, Path]] = []
    for entry in moved:
        orig, target = Path(entry[0]), Path(entry[1])
        if not target.exists():
            warnings.append(f"falta en cuarentena, no se restaura: {target}")
            continue
        if orig.exists():
            warnings.append(f"el destino ya existe, no se sobrescribe: {orig}")
            continue
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(orig))   # mismo volumen (SSD) → rename rápido
        restored.append((orig, target))
        log.info("Restaurado: %s -> %s", target, orig)

    # ── Metadata: reañadir solo las líneas cuyo file_key no esté ya presente ──
    meta_updated = False
    if meta_lines:
        meta_path = base / category / "metadata" / "papers_metadata.jsonl"
        existing_keys: set[str] = set()
        kept: list[str] = []
        if meta_path.exists():
            with meta_path.open(encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    kept.append(line.rstrip("\n"))
                    try:
                        rec = json.loads(s)
                    except Exception:
                        continue
                    stem, _ = infer_stem(rec)
                    if stem:
                        existing_keys.add(file_key(stem))

        to_add: list[str] = []
        for raw in meta_lines:
            try:
                rec = json.loads(raw)
            except Exception:
                to_add.append(raw)        # no parseable: reañadir tal cual
                continue
            stem, _ = infer_stem(rec)
            key = file_key(stem) if stem else None
            if key is not None and key in existing_keys:
                continue                  # ya presente, no duplicar
            to_add.append(raw)
            if key is not None:
                existing_keys.add(key)

        if to_add:
            if meta_path.exists():
                shutil.copy(meta_path, meta_path.with_name(meta_path.name + ".bak"))
            else:
                meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text("\n".join(kept + to_add) + "\n", encoding="utf-8")
            meta_updated = True
            log.info("Metadata: %d línea(s) restaurada(s) en %s", len(to_add), meta_path)
    elif restored:
        warnings.append(
            "manifiesto antiguo sin meta_lines: regenera con "
            f"4_extract_metadata.py --project {category}")

    # ── References: reañadir las líneas retiradas (sin duplicar) ──────────────
    refs_lines = data.get("refs_lines", []) or []
    if refs_lines:
        refs_path = base / category / "metadata" / "references.jsonl"
        have: list[str] = []
        if refs_path.exists():
            have = [l.rstrip("\n") for l in refs_path.read_text(encoding="utf-8").splitlines()
                    if l.strip()]
        have_set = set(have)
        to_add_refs = [l for l in refs_lines if l not in have_set]
        if to_add_refs:
            if refs_path.exists():
                shutil.copy(refs_path, refs_path.with_name(refs_path.name + ".bak"))
            else:
                refs_path.parent.mkdir(parents=True, exist_ok=True)
            refs_path.write_text("\n".join(have + to_add_refs) + "\n", encoding="utf-8")
            log.info("References: %d línea(s) restaurada(s) en %s", len(to_add_refs), refs_path)

    # ── Sidecar de validación + informes de logs/ ─────────────────────────────
    for rel, lines in (data.get("extra_lines", {}) or {}).items():
        fpath = base / category / rel
        if not fpath.exists() or not lines:
            continue
        has_bom = fpath.read_bytes()[:3] == b"\xef\xbb\xbf"
        have = fpath.read_text(encoding="utf-8-sig").splitlines()
        have_set = set(have)
        add = [l for l in lines if l not in have_set]
        if add:
            shutil.copy(fpath, fpath.with_name(fpath.name + ".bak"))
            fpath.write_text("\n".join(have + add) + "\n",
                             encoding="utf-8-sig" if has_bom else "utf-8")

    return restored, meta_updated, warnings


def purge_quarantine_manifest(manifest_path: Path, quarantine_root: Path) -> int:
    """Borra DEFINITIVAMENTE (irreversible) los ficheros de un manifiesto de
    cuarentena y el propio manifiesto. Solo toca rutas dentro de
    `quarantine_root`; poda los directorios que queden vacíos. Devuelve el
    nº de ficheros borrados (sin contar el manifiesto)."""
    manifest_path = Path(manifest_path)
    root = Path(quarantine_root).resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    removed = 0
    for entry in data.get("moved", []) or []:
        target = Path(entry[1])
        try:
            target.resolve().relative_to(root)
        except ValueError:
            log.warning("Fuera de la cuarentena, no se borra: %s", target)
            continue
        if target.is_file():
            target.unlink()
            removed += 1
            log.info("Purgado: %s", target)
    manifest_path.unlink()
    for d in sorted({manifest_path.parent, *(Path(e[1]).parent for e in data.get("moved", []) or [])},
                    key=lambda x: len(x.parts), reverse=True):
        cur = d
        while cur.resolve() != root and root in cur.resolve().parents:
            try:
                cur.rmdir()          # solo si está vacío
            except OSError:
                break
            cur = cur.parent
    return removed


# ============================================================
# RENOMBRADO DE PAPERS YA PROCESADOS (item 68)
# ============================================================
# A diferencia de 1_rename_papers_by_doi.py (que solo renombra el PDF, antes
# de que existan TEI/md_clean/chunks — paso 1 del pipeline, inbox/), esto
# renombra un paper YA PROCESADO: hay que tocar todos los sitios donde vive
# su paper_id o un reproceso posterior lo trataría como huérfano (el PDF
# nuevo sin TEI/md_clean, o viceversa — el mismo defecto que resucitaba
# papers en cuarentena, ver item 66).

_RENAME_ARTIFACT_DIRS = (
    ("tei",       (".tei.xml", ".xml")),
    ("md_clean",  (".clean.md",)),
    ("summaries", (".summary.md",)),
    ("chunks",    (".chunks.jsonl", ".jsonl")),
)


def build_new_paper_id(rec: dict, max_words: int = 8) -> str:
    """Construye el nombre canónico `{año}_{apellido}_{título_corto}` (mismo
    esquema que `1_rename_papers_by_doi.py::build_new_filename`) a partir de
    un registro YA CORREGIDO de `papers_metadata.jsonl` — sin llamar a
    Crossref: usa title/year/authors locales, que es justo lo que el usuario
    acaba de arreglar a mano en el editor de Artículos."""
    from utils.pdf_utils import slugify, shorten_title, sanitize_filename  # noqa: PLC0415

    year = str(rec.get("year") or "0000")
    authors = rec.get("authors") or []
    surname = ""
    if authors:
        a0 = authors[0]
        if isinstance(a0, dict):
            surname = (a0.get("surname") or "").strip()
            if not surname:
                full = (a0.get("full") or "").strip()
                surname = full.split()[-1] if full else ""
        else:
            txt = str(a0).strip()
            surname = txt.split()[-1] if txt else ""
    surname_slug = slugify(surname) or "unknownauthor"
    title = (rec.get("title") or "").strip() or "untitled"
    short_title = shorten_title(title, max_words=max_words)
    filename = sanitize_filename(f"{year}_{surname_slug}_{short_title}.pdf")
    return Path(filename).stem


def _existing_artifact_paths(project_dir: Path, stem: str) -> list[Path]:
    """Rutas que existirían para `stem` en cada carpeta de artefactos, EXISTAN
    o no (a diferencia de candidate_paths, que solo busca ficheros de OTRO
    stem a mover). Se usa para detectar colisión con un `new_id` candidato."""
    paths = [project_dir / "pdfs" / f"{stem}{ext}" for ext in PDF_EXTS]
    for sub, exts in _RENAME_ARTIFACT_DIRS:
        paths.extend(project_dir / sub / f"{stem}{ext}" for ext in exts)
    paths.append(project_dir / "metadata" / "per_paper" / f"{stem}.metadata.json")
    paths.append(project_dir / "metadata" / "per_paper" / f"{stem}.references.json")
    return paths


def _patch_jsonl_field(path: Path, field: str, old_val: str, new_val: str) -> bool:
    """Reescribe `path` (JSONL) sustituyendo `field` donde valga `old_val`.
    Backup `.bak` solo si hay cambios. Devuelve True si se modificó algo."""
    lines: list[str] = []
    changed = False
    with path.open(encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            stripped = s.strip()
            if not stripped:
                lines.append(s)
                continue
            try:
                d = json.loads(stripped)
            except Exception:
                lines.append(s)
                continue
            if d.get(field) == old_val:
                d[field] = new_val
                changed = True
                s = json.dumps(d, ensure_ascii=False)
            lines.append(s)
    if changed:
        shutil.copy(path, path.with_name(path.name + ".bak"))
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return changed


def _patch_papers_metadata(meta_path: Path, old_id: str, new_id: str, project_dir: Path) -> bool:
    """Como _patch_jsonl_field pero además actualiza stable_id (si coincidía
    con el paper_id viejo, caso sin DOI) y tei_file (ruta al nuevo TEI)."""
    lines: list[str] = []
    changed = False
    with meta_path.open(encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            stripped = s.strip()
            if not stripped:
                lines.append(s)
                continue
            try:
                d = json.loads(stripped)
            except Exception:
                lines.append(s)
                continue
            if d.get("paper_id") == old_id:
                d["paper_id"] = new_id
                if d.get("stable_id") == old_id:
                    d["stable_id"] = new_id
                if d.get("tei_file"):
                    d["tei_file"] = str(project_dir / "tei" / f"{new_id}.tei.xml")
                changed = True
                s = json.dumps(d, ensure_ascii=False)
            lines.append(s)
    if changed:
        shutil.copy(meta_path, meta_path.with_name(meta_path.name + ".bak"))
        meta_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return changed


def rename_paper(category: str, old_id: str, new_id: str, base: Path) -> dict:
    """Renombra TODOS los artefactos de un paper ya procesado de `old_id` a
    `new_id` y actualiza su paper_id en cada sitio donde vive: ficheros
    (pdf/tei/md_clean/chunks/summary/per_paper), papers_metadata.jsonl,
    references.jsonl, el campo interno "paper_id" de cada chunk,
    embeddings/*/metadata.jsonl, embeddings/*/indexed_papers.json y
    validation_overrides.csv. El índice FAISS (index.faiss) NO se toca: es
    puramente posicional, correlacionado por orden con metadata.jsonl, así
    que no hace falta re-embeber nada.

    Valida ANTES de mover nada que ningún artefacto de `new_id` exista ya
    (si lo hace, levanta FileExistsError sin tocar un solo fichero — nunca
    deja un renombrado a medias). Cada JSON/JSONL tocado se respalda en
    `.bak` antes de escribir, igual que el resto del pipeline; no hay un
    "restore_from_rename" dedicado (a diferencia de la cuarentena) — para
    deshacer, restaura los `.bak` y revierte los renombrados de fichero con
    la lista `files_renamed` del resultado.

    Devuelve {"old_id","new_id","category","files_renamed":[[old,new],...],
              "patched":[...]} o {"skipped": motivo} si old_id==new_id.
    """
    if old_id == new_id:
        return {"old_id": old_id, "new_id": new_id, "category": category,
                "files_renamed": [], "patched": [], "skipped": "mismo nombre"}

    project_dir = base / category

    # ── Validación: ningún artefacto de new_id puede existir ya ──
    for target in _existing_artifact_paths(project_dir, new_id):
        if target.exists():
            raise FileExistsError(
                f"Ya existe {target}: elige otro nombre o no renombres '{old_id}'."
            )

    files_renamed: list[tuple[Path, Path]] = []
    patched: list[str] = []

    # 1) pdf + tei + md_clean + summaries + chunks (candidate_paths ya incluye
    #    el fallback difuso/por DOI si el nombre actual no es exacto)
    for path in candidate_paths(project_dir, old_id):
        if not path.exists():
            continue
        new_name = None
        if path.parent.name == "pdfs" and path.suffix in PDF_EXTS:
            new_name = f"{new_id}.pdf"
        else:
            for sub, exts in _RENAME_ARTIFACT_DIRS:
                if path.parent.name != sub:
                    continue
                for ext in exts:
                    if path.name.endswith(ext):
                        new_name = f"{new_id}{ext}"
                        break
                break
        if new_name is None:
            continue
        target = path.with_name(new_name)
        path.rename(target)
        files_renamed.append((path, target))
        log.info("Renombrado: %s -> %s", path, target)

    # 2) per_paper/<old_id>.metadata.json + .references.json: renombrar y
    #    parchear paper_id/stable_id/tei_file dentro del .metadata.json
    per_paper = project_dir / "metadata" / "per_paper"
    if per_paper.exists():
        for p in sorted(per_paper.glob(f"{old_id}.*")):
            suffix = p.name[len(old_id):]
            target = per_paper / f"{new_id}{suffix}"
            p.rename(target)
            files_renamed.append((p, target))
            log.info("Renombrado: %s -> %s", p, target)
            if suffix == ".metadata.json":
                try:
                    d = json.loads(target.read_text(encoding="utf-8"))
                    if d.get("paper_id") == old_id:
                        d["paper_id"] = new_id
                    if d.get("stable_id") == old_id:
                        d["stable_id"] = new_id
                    if d.get("tei_file"):
                        d["tei_file"] = str(project_dir / "tei" / f"{new_id}.tei.xml")
                    target.write_text(
                        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as e:
                    log.warning("No se pudo parchear %s: %s", target, e)

    # 3) campo interno "paper_id" de cada línea de chunks/<new_id>.*
    chunks_dir = project_dir / "chunks"
    if chunks_dir.exists():
        for ext in (".chunks.jsonl", ".jsonl"):
            cpath = chunks_dir / f"{new_id}{ext}"
            if cpath.exists() and _patch_jsonl_field(cpath, "paper_id", old_id, new_id):
                patched.append(str(cpath))

    # 4) papers_metadata.jsonl (paper_id + stable_id + tei_file)
    meta_path = project_dir / "metadata" / "papers_metadata.jsonl"
    if meta_path.exists() and _patch_papers_metadata(meta_path, old_id, new_id, project_dir):
        patched.append(str(meta_path))

    # 5) references.jsonl
    refs_path = project_dir / "metadata" / "references.jsonl"
    if refs_path.exists() and _patch_jsonl_field(refs_path, "paper_id", old_id, new_id):
        patched.append(str(refs_path))

    # 6) embeddings/*/metadata.jsonl + indexed_papers.json — el índice FAISS
    #    es posicional y no se toca; solo su metadata lateral.
    emb_dir = project_dir / "embeddings"
    if emb_dir.exists():
        for phase_dir in sorted(p for p in emb_dir.iterdir() if p.is_dir()):
            emeta = phase_dir / "metadata.jsonl"
            if emeta.exists() and _patch_jsonl_field(emeta, "paper_id", old_id, new_id):
                patched.append(str(emeta))
            idx_path = phase_dir / "indexed_papers.json"
            if idx_path.exists():
                try:
                    data = json.loads(idx_path.read_text(encoding="utf-8"))
                    ids = data.get("paper_ids", [])
                    if old_id in ids:
                        shutil.copy(idx_path, idx_path.with_name(idx_path.name + ".bak"))
                        data["paper_ids"] = sorted((set(ids) - {old_id}) | {new_id})
                        idx_path.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                        patched.append(str(idx_path))
                except Exception as e:
                    log.warning("No se pudo parchear %s: %s", idx_path, e)

    # 7) validation_overrides.csv (campos "verificados" del usuario)
    try:
        from utils import validation_overrides  # noqa: PLC0415
        if validation_overrides.rename_paper_id(category, old_id, new_id):
            patched.append("validation_overrides.csv")
    except Exception as e:
        log.warning("No se pudo actualizar validation_overrides.csv: %s", e)

    return {
        "old_id": old_id, "new_id": new_id, "category": category,
        "files_renamed": [[str(o), str(t)] for o, t in files_renamed],
        "patched": patched,
    }


def rewrite_metadata(decisions: list[DuplicateDecision]) -> None:
    removals_by_meta: dict[Path, set[int]] = defaultdict(set)
    for dec in decisions:
        removals_by_meta[dec.remove.metadata_path].add(dec.remove.line_no)

    for meta_path, line_numbers in sorted(removals_by_meta.items(), key=lambda item: str(item[0])):
        if not meta_path.exists():
            log.warning("No existe metadata al reescribir, salto: %s", meta_path)
            continue

        backup = meta_path.with_name(meta_path.name + ".bak")
        shutil.copy(meta_path, backup)
        log.info("Backup metadata: %s", backup)

        kept_lines: list[str] = []
        removed = 0
        with meta_path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if line_no in line_numbers:
                    removed += 1
                    continue
                kept_lines.append(line.rstrip("\n"))

        meta_path.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
        log.info("Metadata reescrita: %s (%d líneas eliminadas)", meta_path, removed)


def affected_categories(decisions: Iterable[DuplicateDecision]) -> list[str]:
    return sorted({dec.remove.category for dec in decisions})


def has_bge_m3_index(category: str, base: Path) -> bool:
    embeddings_dir = base / category / "embeddings"
    if not embeddings_dir.exists():
        return False
    return any(p.is_dir() and "bge-m3" in p.name for p in embeddings_dir.iterdir())


def print_reindex_commands(categories: list[str], base: Path) -> None:
    if not categories:
        return
    print("")
    print("Categorías afectadas que necesitan re-indexar:")
    for category in categories:
        print(f"  python 5_build_embeddings.py --project {category} --model bge-m3 --force")


def apply_cleanup(decisions: list[DuplicateDecision], base: Path) -> list[Path]:
    deleted_files: list[Path] = []
    for dec in decisions:
        log.info(
            "DOI %s [%s]: conservo %s/%s; elimino %s/%s. Motivo: %s",
            dec.doi,
            dec.duplicate_type,
            dec.keep.category,
            dec.keep.stem,
            dec.remove.category,
            dec.remove.stem,
            dec.reason,
        )
        deleted_files.extend(delete_secondary_files(dec.remove, base))

    rewrite_metadata(decisions)
    return deleted_files


def apply_hash_cleanup(
    hash_dups: list[dict],
    stem_index: dict[tuple[str, str], PaperRecord],
    base: Path,
) -> tuple[list[Path], int, list[str]]:
    """Elimina duplicados por hash PDF usando la misma lógica de desempate que DOI."""
    deleted_files: list[Path] = []
    removed_count = 0
    affected: set[str] = set()
    meta_decisions: list[DuplicateDecision] = []

    for group in hash_dups:
        papers = group["papers"]
        if len(papers) < 2:
            continue

        # Misma prioridad que choose_keep_intra: nombre limpio Crossref > stem alfabético
        sorted_papers = sorted(
            papers,
            key=lambda p: (not _is_clean_stem(p["paper_id"]), p["paper_id"].lower()),
        )
        keep_paper = sorted_papers[0]

        for remove_paper in sorted_papers[1:]:
            category = remove_paper["category"]
            stem = remove_paper["paper_id"]
            project_dir = base / category

            for path in candidate_paths(project_dir, stem):
                if path.exists():
                    path.unlink()
                    deleted_files.append(path)
                    log.info("Hash-dup eliminado: %s", path)
                else:
                    log.debug("No existe (hash-dup): %s", path)

            affected.add(category)
            removed_count += 1

            # Reescribir JSONL si existe registro para el eliminado
            remove_rec = stem_index.get((category, stem))
            if remove_rec is not None:
                keep_rec = stem_index.get((keep_paper["category"], keep_paper["paper_id"]))
                meta_decisions.append(
                    DuplicateDecision(
                        doi=remove_rec.doi,
                        duplicate_type="hash",
                        keep=keep_rec if keep_rec is not None else remove_rec,
                        remove=remove_rec,
                        reason="PDF idéntico por SHA-256; nombre limpio Crossref > stem alfabético",
                    )
                )

    if meta_decisions:
        rewrite_metadata(meta_decisions)

    return deleted_files, removed_count, sorted(affected)


# ============================================================
# DETECCIÓN AVANZADA DE DUPLICADOS
# ============================================================

def normalize_title(title: str) -> str:
    if title is None:
        return ""
    text = str(title).lower()
    text = re.sub(r'[^\w\s]', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def pdf_sha256(pdf_path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    except Exception:
        return None


def detect_title_duplicates(cats: list[str], base: Path) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for category in cats:
        meta_path = base / category / "metadata" / "papers_metadata.jsonl"
        if not meta_path.exists():
            continue
        try:
            with meta_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    title = data.get("title") or ""
                    norm = normalize_title(title)
                    if len(norm) < 10:
                        continue
                    stem, _ = infer_stem(data)
                    groups[norm].append({
                        "category": category,
                        "paper_id": stem or "",
                        "doi":      normalize_doi(data.get("doi") or ""),
                        "title":    title,
                        "year":     data.get("year"),
                    })
        except Exception:
            continue
    result: list[dict] = []
    for norm, papers in sorted(groups.items()):
        if len(papers) < 2:
            continue
        distinct_dois = {p["doi"] for p in papers if p.get("doi")}
        if len(distinct_dois) >= 2:
            # Mismo título pero DOIs distintos → artículos diferentes, NO duplicado.
            log.debug("Título compartido con %d DOIs distintos, ignorado: %.60s",
                      len(distinct_dois), norm)
            continue
        result.append({"match_type": "title", "norm_title": norm, "papers": papers})
    return result


def detect_hash_duplicates(cats: list[str], base: Path) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for category in cats:
        pdfs_dir = base / category / "pdfs"
        if not pdfs_dir.exists():
            continue
        for pdf in sorted(pdfs_dir.iterdir()):
            if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
                continue
            sha = pdf_sha256(pdf)
            if sha is None:
                continue
            groups[sha].append({
                "category": category,
                "paper_id": pdf.stem,
                "pdf_path": str(pdf),
            })
    return [
        {"match_type": "hash", "sha256": sha, "papers": papers}
        for sha, papers in sorted(groups.items())
        if len(papers) >= 2
    ]


def write_duplicate_report(
    decisions_doi: list[DuplicateDecision],
    title_dups: list[dict],
    hash_dups: list[dict],
    out_path: Path,
) -> Optional[Path]:
    try:
        import openpyxl
    except ImportError:
        print("⚠ openpyxl no instalado — no se genera el informe Excel (pip install openpyxl)")
        return None

    wb = openpyxl.Workbook()

    ws_doi = wb.active
    ws_doi.title = "DOI"
    ws_doi.append(["doi", "category_keep", "stem_keep", "category_remove", "stem_remove", "reason", "type"])
    for dec in decisions_doi:
        ws_doi.append([
            dec.doi,
            dec.keep.category,
            dec.keep.stem,
            dec.remove.category,
            dec.remove.stem,
            dec.reason,
            dec.duplicate_type,
        ])

    ws_title = wb.create_sheet("Titulo")
    ws_title.append(["norm_title", "category", "paper_id", "doi", "title", "year", "recommended_action"])
    for group in title_dups:
        for paper in group["papers"]:
            ws_title.append([
                group["norm_title"],
                paper["category"],
                paper["paper_id"],
                paper["doi"],
                paper["title"],
                paper["year"],
                "revisar_manual",
            ])

    ws_hash = wb.create_sheet("Hash")
    ws_hash.append(["sha256", "category", "paper_id", "pdf_path", "recommended_action"])
    for group in hash_dups:
        for paper in group["papers"]:
            ws_hash.append([
                group["sha256"],
                paper["category"],
                paper["paper_id"],
                paper["pdf_path"],
                "revisar_manual",
            ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return out_path


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Detecta y limpia duplicados por DOI ya procesados")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Solo informar, no modificar nada (defecto)")
    mode.add_argument("--apply", action="store_true", help="Ejecutar la limpieza")
    ap.add_argument("--dry-run", action="store_true", help="Alias de --preview")
    ap.add_argument("--category", action="append", choices=CATEGORIES, help="Limitar a una categoría (repetible)")
    ap.add_argument("--doi", help="Resolver un DOI concreto manualmente")
    ap.add_argument("--base", default=str(DEFAULT_BASE), help=f"Directorio base (defecto: {DEFAULT_BASE})")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging()

    base = Path(args.base)
    cats = category_dirs(base, args.category)
    doi_filter = normalize_doi(args.doi) if args.doi else ""
    apply_mode = bool(args.apply and not args.dry_run)

    log.info("Base: %s", base)
    log.info("Categorías: %s", ", ".join(cats))
    log.info("Modo: %s", "apply" if apply_mode else "preview")

    registry = build_registry(cats, base)
    if doi_filter:
        registry = {doi: records for doi, records in registry.items() if doi == doi_filter}
        if not registry:
            print(f"No se ha encontrado DOI: {doi_filter}")
            return 0

    decisions = decide_duplicates(registry)
    rows = pairwise_rows(decisions)

    if rows:
        print_table(rows)
    else:
        print("No se han encontrado duplicados por DOI.")

    print_decision_details(decisions)
    summarize(decisions)

    title_dups = detect_title_duplicates(cats, base)
    hash_dups  = detect_hash_duplicates(cats, base)
    print(f"Duplicados por título: {len(title_dups)}")
    print(f"Duplicados por hash PDF: {len(hash_dups)}")
    if title_dups or hash_dups:
        print("Ver informe Excel para revisión manual.")
    report_path = write_duplicate_report(
        decisions, title_dups, hash_dups,
        base.parent / "metadatos" / "duplicate_report.xlsx",
    )
    if report_path:
        print(report_path)

    if not apply_mode:
        print("")
        print("Usa --apply para eliminar los secundarios")
        print("No se ha modificado nada.")
        print(f"Log: {LOG_FILE}")
        return 0

    if not decisions and not hash_dups:
        print("No hay secundarios que eliminar.")
        print(f"Log: {LOG_FILE}")
        return 0

    stem_index = build_stem_index(registry)

    deleted_doi: list[Path] = []
    if decisions:
        deleted_doi = apply_cleanup(decisions, base)
    affected_doi = affected_categories(decisions)

    deleted_hash, hash_removed_count, affected_hash = apply_hash_cleanup(hash_dups, stem_index, base)

    all_deleted = deleted_doi + deleted_hash
    all_affected = sorted(set(affected_doi) | set(affected_hash))

    print("")
    print(f"Duplicados DOI eliminados: {len(decisions)}")
    print(f"Duplicados hash eliminados: {hash_removed_count}")
    print("Archivos eliminados:")
    if all_deleted:
        for path in all_deleted:
            print(f"  {path}")
    else:
        print("  (ninguno; los archivos secundarios ya no existían)")
    print_reindex_commands(all_affected, base)
    print(f"Log: {LOG_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
