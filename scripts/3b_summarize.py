#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3b_summarize.py — Paso 3b del pipeline research_agent

Genera resúmenes estructurados de artículos científicos usando Ollama.
Los resúmenes se usan en 6_make_packages.py para enriquecer el FULLTEXT
de los paquetes NotebookLM.

Posición en el pipeline:
    md_clean/<paper_id>.clean.md → 3b_summarize.py → summaries/<paper_id>.summary.md

Estructura del resumen generado (800-1000 palabras en inglés):
    - Main objective
    - Methodology (setup, condiciones, escala, técnicas analíticas)
    - Main results (datos cuantitativos)
    - Discussion (mecanismos, comparativa con literatura, limitaciones)
    - Conclusions (implicaciones prácticas, trabajo futuro)
    - Keywords (8-10 términos técnicos)

Skip logic:
    Si <paper_id>.summary.md ya existe y --force no está activo, el paper
    se salta. Permite reanudar sin reprocesar lo ya completado.

Ficheros leídos:
    /Volumes/research/categorias/<phase>/md_clean/*.clean.md
    config/.env

Ficheros escritos:
    /Volumes/research/categorias/<phase>/summaries/<paper_id>.summary.md
    /Volumes/research/categorias/<phase>/logs/3b_summarize_report.csv

Parámetros CLI:
    --phase PHASE         Nombre de la categoría/fase a procesar (obligatorio)
    --base DIR            Directorio raíz (defecto: /Volumes/research/categorias)
    --model MODEL         Modelo Ollama (defecto: qwen3:14b)
    --timeout N           Timeout por llamada a Ollama en segundos (defecto: 300)
    --limit N             Procesa solo los primeros N artículos
    --sleep SEG           Pausa entre artículos en segundos
    --force               Reprocesa aunque el resumen ya exista
    --dry-run             Lista artículos a procesar sin llamar a Ollama

Variables de entorno (config/.env):
    OLLAMA_HOST           URL del servidor Ollama (defecto: http://127.0.0.1:11435)

Dependencias:
    ollama, python-dotenv

Notas:
    - Papers con menos de 100 palabras en el .clean.md se saltan
      automáticamente (marcados como 'skipped_empty' en el CSV).
    - qwen3:14b es el modelo recomendado para calidad; gemma3:4b es más
      rápido pero produce resúmenes menos detallados.
"""

import argparse
import csv
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import ollama
from dotenv import load_dotenv

# ── Cargar config/.env antes de leer variables de entorno ────────────────────
_ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

DEFAULT_BASE  = "/Volumes/research/categorias"
OLLAMA_HOST   = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11435")
DEFAULT_MODEL = "qwen3:14b"

VALID_PHASES = [
    "biological_gas_odor_treatment",
    "anoxic_biogas_biodesulfurization",
    "bioplastics_microplastics",
    "biogas_upgrading_biomethanation",
    "microalgae",
    "single_cell_protein",
    "advanced_oxidation_processes",
    "bioleaching_critical_materials",
]

SYSTEM_PROMPT = (
    "You are a scientific paper summarizer. "
    "Respond ONLY with the structured summary. "
    "Do not ask questions. Do not add commentary."
)

SUMMARIZE_PROMPT = """\
Provide a detailed structured summary (800-1000 words) in English with these sections:

- **Main objective**: What problem does this paper address, why is it relevant, and what gap in knowledge does it fill?
- **Methodology**: Detailed experimental setup, reactor types and dimensions, operating conditions (temperature, pH, HRT, OLR, gas flow rates), scale (lab/pilot/full), analytical techniques used, and duration of experiments
- **Main results**: All important findings with specific quantitative data (efficiencies, rates, concentrations, yields, percentages). Include data from tables and figures when available
- **Discussion**: Key interpretations, comparisons with previous literature, explanations of mechanisms, limitations acknowledged by authors
- **Conclusions**: Main takeaways, practical implications, and future research directions suggested
- **Keywords**: 8-10 relevant technical terms

Be precise and exhaustive with numerical values. /no_think

Paper:
{contenido_md}

Provide ONLY the structured summary. Do not ask questions or add any commentary after the summary."""


# ============================================================
# SUMMARIZACIÓN
# ============================================================

def summarize_paper(
    client: ollama.Client,
    md_content: str,
    model: str,
    timeout: int,
) -> str:
    prompt = SUMMARIZE_PROMPT.format(contenido_md=md_content)
    resp = client.generate(
        model=model,
        system=SYSTEM_PROMPT,
        prompt=prompt,
        stream=False,
        options={"temperature": 0.3, "num_predict": 2048, "num_ctx": 16384},
    )
    return resp["response"].strip()


# ============================================================
# INFORME
# ============================================================

def write_report(report_rows: List[Dict], project_dir: Path) -> None:
    report_dir = project_dir / "logs"
    os.makedirs(str(report_dir), exist_ok=True)
    report_path = report_dir / "3b_summarize_report.csv"

    fieldnames = ["paper_id", "md_path", "summary_path",
                  "status", "error", "seconds", "words_in", "words_out"]

    with report_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(report_rows)

    print(f"Report CSV:  {report_path}")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Genera resúmenes estructurados de artículos científicos con Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--phase", required=True,
        metavar="PHASE",
        help="Nombre de la fase/categoría del proyecto (p.ej. 'bioreactores', 'adhoc_xyz')",
    )
    ap.add_argument("--base",    default=DEFAULT_BASE,
                    help=f"Directorio raíz (defecto: {DEFAULT_BASE})")
    ap.add_argument("--model",   default=DEFAULT_MODEL,
                    help=f"Modelo Ollama (defecto: {DEFAULT_MODEL})")
    ap.add_argument("--timeout", type=int, default=300,
                    help="Timeout por llamada a Ollama en segundos (defecto: 300)")
    ap.add_argument("--limit",   type=int, default=0,
                    help="Procesar solo N artículos (0 = todos)")
    ap.add_argument("--sleep",   type=float, default=0.0,
                    help="Pausa entre artículos en segundos")
    ap.add_argument("--force",   action="store_true",
                    help="Reprocessar aunque el resumen ya exista")
    ap.add_argument("--dry-run", action="store_true",
                    help="Solo lista lo que haría, sin llamar a Ollama")
    args = ap.parse_args()

    base         = Path(args.base)
    project_dir  = base / args.phase
    md_clean_dir = project_dir / "md_clean"
    summaries_dir= project_dir / "summaries"

    if not md_clean_dir.exists():
        raise SystemExit(f"No existe md_clean dir: {md_clean_dir}")

    summaries_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "logs").mkdir(parents=True, exist_ok=True)

    # ── Recoger ficheros .clean.md ────────────────────────────
    md_files: List[Path] = sorted(
        set(md_clean_dir.glob("*.clean.md")) | set(md_clean_dir.rglob("*.clean.md"))
    )
    if not md_files:
        raise SystemExit(f"No se encontraron .clean.md en: {md_clean_dir}")

    if args.limit and args.limit > 0:
        md_files = md_files[: args.limit]

    client = ollama.Client(host=OLLAMA_HOST)

    print(f"Phase      : {args.phase}")
    print(f"Base       : {base}")
    print(f"md_clean   : {md_clean_dir}")
    print(f"Summaries  : {summaries_dir}")
    print(f"Artículos  : {len(md_files)}")
    print(f"Modelo     : {args.model}")
    print(f"Ollama     : {OLLAMA_HOST}")
    if args.dry_run:
        print("Modo       : DRY-RUN")
    print("")

    report_rows: List[Dict] = []
    total  = len(md_files)
    errors = 0

    for idx, md_path in enumerate(md_files, start=1):
        paper_id     = md_path.name.replace(".clean.md", "")
        summary_path = summaries_dir / f"{paper_id}.summary.md"

        row: Dict = {
            "paper_id":     paper_id,
            "md_path":      str(md_path),
            "summary_path": str(summary_path),
            "status":       "",
            "error":        "",
            "seconds":      0.0,
            "words_in":     0,
            "words_out":    0,
        }

        print(f"[{idx}/{total}] {paper_id} ...", end=" ", flush=True)

        # ── Skip si ya existe ─────────────────────────────────
        if summary_path.exists() and not args.force:
            print("SKIP (exists)")
            row["status"] = "skipped_exists"
            report_rows.append(row)
            continue

        # ── Dry-run ───────────────────────────────────────────
        if args.dry_run:
            print("DRY-RUN")
            row["status"] = "dry_run"
            report_rows.append(row)
            continue

        # ── Leer Markdown ─────────────────────────────────────
        try:
            md_content = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"ERROR_LECTURA")
            row["status"] = "error_lectura"
            row["error"]  = str(e)
            errors += 1
            report_rows.append(row)
            continue

        words_in = len(md_content.split())
        row["words_in"] = words_in

        if words_in < 100:
            print(f"SKIP_VACIO ({words_in} palabras)")
            row["status"] = "skipped_empty"
            report_rows.append(row)
            continue

        # ── Llamar a Ollama ───────────────────────────────────
        t0 = time.time()
        try:
            summary = summarize_paper(client, md_content, args.model, args.timeout)
            dt = time.time() - t0

            summary_path.write_text(summary, encoding="utf-8")

            words_out       = len(summary.split())
            row["status"]   = "ok"
            row["seconds"]  = round(dt, 1)
            row["words_out"]= words_out
            print(f"OK  ({words_out} palabras, {dt:.1f}s)")

        except Exception as e:
            dt = time.time() - t0
            row["status"]  = "error_ollama"
            row["error"]   = str(e)
            row["seconds"] = round(dt, 1)
            errors += 1
            print(f"ERROR  ({e})")

        report_rows.append(row)

        if args.sleep > 0:
            time.sleep(args.sleep)

    # ── Informe ───────────────────────────────────────────────
    write_report(report_rows, project_dir)

    ok      = sum(1 for r in report_rows if r["status"] == "ok")
    skipped = sum(1 for r in report_rows if r["status"].startswith("skipped"))
    dry     = sum(1 for r in report_rows if r["status"] == "dry_run")

    print(f"\n{'=' * 60}")
    print(f"Phase      : {args.phase}")
    print(f"Artículos  : {total}")
    print(f"OK         : {ok}")
    print(f"Skipped    : {skipped}")
    print(f"Errors     : {errors}")
    if dry:
        print(f"Dry-run    : {dry}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
