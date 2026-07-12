#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_weekly_scopus.py — Ingesta Scopus semanal + email resumen.

Ejecuta run_scopus() para WEEKLY_CATEGORIES con recent_days=7,
luego envía un email HTML con los resultados y los DOIs pendientes.

Uso directo:
    python3 run_weekly_scopus.py            # ejecución real
    python3 run_weekly_scopus.py --dry-run  # imprime HTML en stdout, no ejecuta nada
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import smtplib
import socket
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPTS_DIR.parent
CONFIG_DIR  = PROJECT_DIR / "config"
NAS_ROOT    = Path("/Volumes/research")
CATEGORIAS_DIR = NAS_ROOT / "categorias"
METADATOS_DIR  = NAS_ROOT / "metadatos"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Cargar .env antes de cualquier os.getenv
from dotenv import load_dotenv  # noqa: E402
load_dotenv(CONFIG_DIR / ".env")

from pipeline import run_scopus  # noqa: E402
from utils import download_registry  # noqa: E402

# ---------------------------------------------------------------------------
# Categorías a procesar cada semana
# ---------------------------------------------------------------------------

WEEKLY_CATEGORIES: list[str] = [
    "biogas_upgrading_biomethanation",
    "anoxic_biogas_biodesulfurization",
    "bioplastics_microplastics",
]

SCOPUS_TIMEOUT = 5400  # 90 minutos — evita colgarse si 3a_download_pdfs.py no responde

# ---------------------------------------------------------------------------
# Configuración SMTP (leída de .env)
# ---------------------------------------------------------------------------

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
# Soporta SMTP_TO y el alias SMPT_TO (typo que puede estar en .env existente)
SMTP_TO       = os.getenv("SMTP_TO") or os.getenv("SMPT_TO") or SMTP_USER

# ---------------------------------------------------------------------------
# Helpers de conteo
# ---------------------------------------------------------------------------

def _count_pdfs(cat: str) -> int:
    d = CATEGORIAS_DIR / cat / "pdfs"
    return len(list(d.glob("*.pdf"))) if d.exists() else 0


def _count_chunks(cat: str) -> int:
    d = CATEGORIAS_DIR / cat / "chunks"
    if not d.exists():
        return 0
    total = 0
    for jsonl in d.glob("*.jsonl"):
        try:
            total += sum(1 for ln in jsonl.open(encoding="utf-8") if ln.strip())
        except Exception:
            pass
    return total


def _load_pending_dois() -> list[dict]:
    n_reconciliados = download_registry.reconcile_with_corpus()
    if n_reconciliados:
        logging.getLogger("weekly_scopus").info(
            "Reconciliados %d DOI(s) pendientes ya presentes en el corpus "
            "(ingesta fuera de 3a_download_pdfs.py).", n_reconciliados)
    df = download_registry.load()
    if df.empty:
        return []
    rows = download_registry.pending_active(df).to_dict("records")
    # Ordenar: categoría ascendente, last_checked descendente (stable sort en 2 pasos)
    rows.sort(key=lambda r: r.get("last_checked", ""), reverse=True)
    rows.sort(key=lambda r: r.get("category", ""))
    return rows


def _status_icon(status: str) -> str:
    return {
        "ok": "✅", "partial": "⚠️", "error": "❌",
        "skipped": "⏭️", "timeout": "⏱️",
    }.get(status, "❓")

# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: Arial, sans-serif; font-size: 14px; color: #222; margin: 20px; }
h2   { color: #2c5282; border-bottom: 2px solid #bee3f8; padding-bottom: 6px; }
h3   { color: #4a5568; margin-top: 24px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th { background: #2c5282; color: white; padding: 8px 12px; text-align: left; }
td { padding: 7px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:nth-child(even) { background: #f7fafc; }
.pill-ok   { background:#c6f6d5; color:#276749; padding:2px 8px; border-radius:12px; font-weight:bold; }
.pill-err  { background:#fed7d7; color:#c53030; padding:2px 8px; border-radius:12px; font-weight:bold; }
.pill-warn { background:#fefcbf; color:#744210; padding:2px 8px; border-radius:12px; font-weight:bold; }
.ok    { color:#276749; font-weight:bold; }
.error { color:#c53030; font-weight:bold; }
.warn  { color:#b7791f; font-weight:bold; }
a  { color:#3182ce; }
.footer { margin-top:32px; font-size:12px; color:#718096;
          border-top:1px solid #e2e8f0; padding-top:8px; }
"""


# DEPRECATED — se usa build_html_single_cat() desde 2026-07-01
def build_html(
    run_date: str,
    duration_s: float,
    overall: str,
    pdf_diffs: dict[str, tuple[int, int]],
    chunk_totals: dict[str, int],
    cat_results: dict[str, dict],
    pending: list[dict],
    log_path: str,
    error_msg: str = "",
) -> str:
    icon = _status_icon(overall)
    status_class = {
        "ok": "ok", "partial": "warn", "error": "error", "timeout": "warn",
    }.get(overall, "warn")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
<h2>📄 Ingesta Scopus semanal — {run_date}</h2>
<p>Duración: <strong>{duration_s:.1f}s</strong> &nbsp;|&nbsp;
   Estado general: <span class="{status_class}">{icon} {overall.upper()}</span></p>
"""

    if error_msg:
        html += (
            f'<p class="error">⛔ Error durante la ejecución: '
            f"<code>{error_msg}</code></p>\n"
        )

    # ── Resultados por categoría ──────────────────────────────────────────
    html += "<h3>📂 Resultados por categoría</h3>\n<table>\n"
    html += (
        "<tr><th>Categoría</th><th>Estado</th>"
        "<th>PDFs nuevos</th><th>Chunks totales</th></tr>\n"
    )
    for cat in WEEKLY_CATEGORIES:
        result = cat_results.get(cat, {})
        status = result.get("status", "—")
        before, after = pdf_diffs.get(cat, (0, 0))
        new_pdfs = after - before
        chunks = chunk_totals.get(cat, "—") if status == "ok" else "—"
        pill = {"ok": "pill-ok", "error": "pill-err", "timeout": "pill-warn"}.get(status, "pill-warn")
        html += (
            f"<tr><td>{cat}</td>"
            f"<td><span class='{pill}'>{_status_icon(status)} {status}</span></td>"
            f"<td>+{new_pdfs}</td>"
            f"<td>{chunks}</td></tr>\n"
        )
    html += "</table>\n"

    # ── DOIs pendientes de descarga ───────────────────────────────────────
    html += "<h3>⬇️ DOIs pendientes de descarga</h3>\n"
    if not pending:
        html += '<p class="ok">✅ Sin DOIs pendientes de descarga.</p>\n'
    else:
        html += f"<p>Total: <strong>{len(pending)}</strong> DOI(s) con status <em>pending</em>.</p>\n"
        html += (
            "<table>\n<tr><th>Título</th><th>Año</th><th>Categoría</th>"
            "<th>Motivo</th><th>Enlace</th></tr>\n"
        )
        for row in pending:
            title  = (row.get("title",    "") or "")[:60]
            year   = row.get("year",      "")
            cat    = row.get("category",  "")
            reason = (row.get("reason",   "") or "")[:80]
            url    = row.get("landing_url", "")
            link   = f'<a href="{url}">🔗 ver</a>' if url else "—"
            html += (
                f"<tr><td>{title}</td><td>{year}</td><td>{cat}</td>"
                f"<td><small>{reason}</small></td><td>{link}</td></tr>\n"
            )
        html += "</table>\n"

    # ── Pie ───────────────────────────────────────────────────────────────
    html += f"""
<div class="footer">
  <p>Host: <code>{socket.gethostname()}</code>
     &nbsp;|&nbsp; Log: <code>{log_path}</code></p>
  <p>Generado por <code>research_agent/scripts/run_weekly_scopus.py</code></p>
</div>
</body></html>
"""
    return html

def build_html_single_cat(
    cat: str,
    run_date: str,
    duration_s: float,
    overall_cat: str,
    pdf_before: int,
    pdf_after: int,
    chunk_total: int | str,
    pending_cat: list[dict],
    log_path: str,
    error_msg: str = "",
) -> str:
    icon = _status_icon(overall_cat)
    status_class = {
        "ok": "ok", "partial": "warn", "error": "error", "timeout": "warn",
    }.get(overall_cat, "warn")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
<h2>📄 Ingesta Scopus semanal — {run_date} — {cat}</h2>
<p>Duración: <strong>{duration_s:.1f}s</strong> &nbsp;|&nbsp;
   Estado general: <span class="{status_class}">{icon} {overall_cat.upper()}</span></p>
"""

    if error_msg:
        html += (
            f'<p class="error">⛔ Error durante la ejecución: '
            f"<code>{error_msg}</code></p>\n"
        )

    # ── Resultado ─────────────────────────────────────────────────────────
    new_pdfs = pdf_after - pdf_before
    pill = {"ok": "pill-ok", "error": "pill-err", "timeout": "pill-warn"}.get(overall_cat, "pill-warn")
    chunks_display = chunk_total if overall_cat == "ok" else "—"

    html += "<h3>📂 Resultado</h3>\n<table>\n"
    html += (
        "<tr><th>Categoría</th><th>Estado</th>"
        "<th>PDFs nuevos</th><th>Chunks totales</th></tr>\n"
    )
    html += (
        f"<tr><td>{cat}</td>"
        f"<td><span class='{pill}'>{_status_icon(overall_cat)} {overall_cat}</span></td>"
        f"<td>+{new_pdfs}</td>"
        f"<td>{chunks_display}</td></tr>\n"
    )
    html += "</table>\n"

    # ── DOIs pendientes de descarga ────────────────────────────────────────
    html += "<h3>⬇️ DOIs pendientes de descarga</h3>\n"
    if not pending_cat:
        html += '<p class="ok">✅ Sin DOIs pendientes de descarga.</p>\n'
    else:
        html += f"<p>Total: <strong>{len(pending_cat)}</strong> DOI(s) con status <em>pending</em>.</p>\n"
        html += (
            "<table>\n<tr><th>Título</th><th>Año</th><th>Categoría</th>"
            "<th>Motivo</th><th>Enlace</th></tr>\n"
        )
        for row in pending_cat:
            title  = (row.get("title",    "") or "")[:60]
            year   = row.get("year",      "")
            cat_r  = row.get("category",  "")
            reason = (row.get("reason",   "") or "")[:80]
            url    = row.get("landing_url", "")
            link   = f'<a href="{url}">🔗 ver</a>' if url else "—"
            html += (
                f"<tr><td>{title}</td><td>{year}</td><td>{cat_r}</td>"
                f"<td><small>{reason}</small></td><td>{link}</td></tr>\n"
            )
        html += "</table>\n"

    # ── Pie ───────────────────────────────────────────────────────────────
    html += f"""
<div class="footer">
  <p>Host: <code>{socket.gethostname()}</code>
     &nbsp;|&nbsp; Log: <code>{log_path}</code></p>
  <p>Generado por <code>research_agent/scripts/run_weekly_scopus.py</code></p>
</div>
</body></html>
"""
    return html


# ---------------------------------------------------------------------------
# Per-category email dispatcher
# ---------------------------------------------------------------------------

def send_category_emails(
    run_date: str,
    duration_s: float,
    overall: str,
    pdf_diffs: dict[str, tuple[int, int]],
    chunk_totals: dict[str, int],
    cat_results: dict[str, dict],
    pending: list[dict],
    log_path: str,
    error_msg: str = "",
    dry_run: bool = False,
) -> None:
    log = logging.getLogger("weekly_scopus")
    failed_htmls: list[str] = []

    for cat in WEEKLY_CATEGORIES:
        result = cat_results.get(cat, {})
        overall_cat = result.get("status", "error")
        before, after = pdf_diffs.get(cat, (0, 0))
        new_pdfs = after - before
        chunk_total: int | str = chunk_totals.get(cat, "—") if overall_cat == "ok" else "—"
        pending_cat = [r for r in pending if r.get("category", "") == cat]

        subject = (
            f"[research_agent] {cat} — {run_date} — "
            f"{new_pdfs} nuevos / {len(pending_cat)} pendientes"
        )
        html = build_html_single_cat(
            cat=cat,
            run_date=run_date,
            duration_s=duration_s,
            overall_cat=overall_cat,
            pdf_before=before,
            pdf_after=after,
            chunk_total=chunk_total,
            pending_cat=pending_cat,
            log_path=log_path,
            error_msg=error_msg,
        )

        if dry_run:
            print(f"\n{'=' * 60}\n=== {cat} ===\n{'=' * 60}")
            print(html)
            continue

        try:
            send_email(subject, html)
            log.info("Email enviado [%s] a %s", cat, SMTP_TO)
        except Exception as exc:
            log.error("ERROR enviando email [%s]: %s", cat, exc)
            failed_htmls.append(f"<!-- === {cat} === -->\n{html}")

    if failed_htmls:
        fallback = Path("/tmp/research_agent_weekly_report.html")
        fallback.write_text("\n".join(failed_htmls), encoding="utf-8")
        log.error("HTML de categorías fallidas guardado en %s", fallback)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = SMTP_TO
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [SMTP_TO], msg.as_string())

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(dry_run: bool = False) -> None:
    run_date = datetime.now().strftime("%Y-%m-%d")

    # ── Logging a fichero ─────────────────────────────────────────────────
    logs_dir = PROJECT_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(logs_dir / f"run_weekly_scopus_{run_date}.log")

    log = logging.getLogger("weekly_scopus")
    log.setLevel(logging.INFO)
    if not log.handlers:
        _fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(_fmt)
        log.addHandler(fh)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(_fmt)
        log.addHandler(sh)

    log.info("=== run_weekly_scopus iniciado%s ===", " (dry-run)" if dry_run else "")

    # Contar PDFs antes de la ingesta
    pdf_before = {cat: _count_pdfs(cat) for cat in WEEKLY_CATEGORIES}

    overall   = "ok"
    error_msg = ""
    cat_results: dict[str, dict] = {}
    t_start = time.monotonic()

    if dry_run:
        cat_results = {cat: {"status": "ok"} for cat in WEEKLY_CATEGORIES}
    else:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        # año vigente + anterior: recent_days filtra por fecha de indexación, no de publicación
        future = executor.submit(
            run_scopus,
            categories=WEEKLY_CATEGORIES,
            recent_days=7,
            year_start=datetime.now().year - 1,
        )
        try:
            result    = future.result(timeout=SCOPUS_TIMEOUT)
            cat_results = result.get("categories", {})
            overall     = result.get("status", "error")
            log.info("run_scopus completado — estado: %s", overall)
        except concurrent.futures.TimeoutError:
            error_msg = (
                f"run_scopus superó el timeout de {SCOPUS_TIMEOUT}s "
                f"({SCOPUS_TIMEOUT // 60} min). El subproceso sigue en background."
            )
            overall   = "timeout"
            cat_results = {cat: {"status": "timeout"} for cat in WEEKLY_CATEGORIES}
            log.error("TIMEOUT — %s", error_msg)
        except Exception as exc:
            error_msg   = str(exc)
            overall     = "error"
            cat_results = {
                cat: {"status": "error", "reason": error_msg}
                for cat in WEEKLY_CATEGORIES
            }
            log.error("Excepción en run_scopus: %s", error_msg)
        finally:
            # No esperar al hilo — el email debe salir aunque run_scopus siga corriendo
            executor.shutdown(wait=False)

    duration_s = time.monotonic() - t_start

    # Contar PDFs después y chunks totales
    pdf_after    = {cat: _count_pdfs(cat)  for cat in WEEKLY_CATEGORIES}
    chunk_totals = {cat: _count_chunks(cat) for cat in WEEKLY_CATEGORIES}
    pdf_diffs    = {cat: (pdf_before[cat], pdf_after[cat]) for cat in WEEKLY_CATEGORIES}

    # DOIs pendientes
    pending = _load_pending_dois()

    send_category_emails(
        run_date=run_date,
        duration_s=duration_s,
        overall=overall,
        pdf_diffs=pdf_diffs,
        chunk_totals=chunk_totals,
        cat_results=cat_results,
        pending=pending,
        log_path=log_path,
        error_msg=error_msg,
        dry_run=dry_run,
    )

    if dry_run:
        log.info("=== dry-run finalizado ===")
        return

    log.info(
        "=== run_weekly_scopus finalizado — estado: %s, duración: %.1fs ===",
        overall, duration_s,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingesta Scopus semanal + email resumen."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprime el HTML en stdout sin enviar email ni ejecutar Scopus.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
