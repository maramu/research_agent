#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
healthcheck.py — comprobación barata del estado de pciq22 (item 59b).

Comprueba (solo lectura, sin tokens): Streamlit privado :8501 y público :8502, Ollama directo
127.0.0.1:11435, el proxy Caddy :11434 (debe responder 401 sin Bearer), GROBID :8070 y que
/Volumes/research esté montado. Si algo falla envía UN email (SMTP de config/.env, como
run_weekly_scopus.py) y no vuelve a avisar mientras el conjunto de fallos no cambie.

Uso:
    python3 scripts/healthcheck.py --dry-run     # imprime el resultado, no envía nada
    python3 scripts/healthcheck.py               # para launchd (ver deployment/com.research_agent.healthcheck.plist)

Código de salida: 0 todo bien · 1 algún fallo.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPTS_DIR.parent / "config"
STATE_FILE = Path.home() / ".cache" / "research_agent" / "healthcheck_state.json"

# (nombre, url, código HTTP esperado, texto que debe contener la respuesta o None)
CHECKS = [
    ("Streamlit privado :8501", "http://127.0.0.1:8501/_stcore/health", 200, "ok"),
    ("Streamlit público :8502", "http://127.0.0.1:8502/_stcore/health", 200, "ok"),
    ("Ollama 127.0.0.1:11435", "http://127.0.0.1:11435/api/version", 200, "version"),
    ("Caddy :11434 (401 sin Bearer)", "http://127.0.0.1:11434/api/version", 401, None),
    ("GROBID :8070", "http://127.0.0.1:8070/api/isalive", 200, "true"),
]
DATA_DIR = Path("/Volumes/research/categorias")


def fetch(url: str, timeout: int = 8) -> tuple:
    """(status, cuerpo). status=0 si no hay conexión."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:      # 401 de Caddy llega aquí
        return e.code, ""
    except Exception:
        return 0, ""


def run_checks(fetcher=fetch, data_dir: Path = DATA_DIR) -> list:
    """Lista de textos de fallo (vacía si todo está bien)."""
    fails = []
    for name, url, want_status, want_text in CHECKS:
        status, body = fetcher(url)
        if status != want_status:
            fails.append(f"{name}: HTTP {status or 'sin conexión'} (esperado {want_status})")
        elif want_text and want_text not in body.lower():
            fails.append(f"{name}: respuesta inesperada")
    if not data_dir.exists():
        fails.append(f"Datos: {data_dir} no está montado")
    return fails


def _send_email(subject: str, body: str) -> None:
    from dotenv import load_dotenv
    load_dotenv(CONFIG_DIR / ".env")
    user = os.getenv("SMTP_USER", "")
    to = os.getenv("SMTP_TO") or os.getenv("SMPT_TO") or user
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"),
                      int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
        s.ehlo(); s.starttls(); s.login(user, os.getenv("SMTP_PASSWORD", ""))
        s.sendmail(user, [to], msg.as_string())


def main() -> int:
    ap = argparse.ArgumentParser(description="Healthcheck de pciq22")
    ap.add_argument("--dry-run", action="store_true", help="solo imprime; no envía email ni guarda estado")
    args = ap.parse_args()
    fails = run_checks()
    print("OK: todo responde" if not fails else "FALLOS:\n- " + "\n- ".join(fails))
    if args.dry_run:
        return 1 if fails else 0
    try:
        previous = json.loads(STATE_FILE.read_text()).get("fails", [])
    except Exception:
        previous = []
    if sorted(fails) != sorted(previous):                 # solo avisa cuando cambia el conjunto
        if fails:
            _send_email("[research_agent] pciq22: fallo de servicios", "\n".join(fails))
        elif previous:
            _send_email("[research_agent] pciq22: servicios recuperados", "Todo vuelve a responder.")
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"fails": fails}))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
