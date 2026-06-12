# -*- coding: utf-8 -*-
"""
12_Backup.py — Copia de seguridad de /Volumes/research → /Volumes/research_bk (solo app privada).
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for _d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import is_public_app, check_password, read_last_backup

st.set_page_config(page_title="Backup", page_icon="💾", layout="wide")

if is_public_app():
    st.stop()

if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

RESEARCH    = Path("/Volumes/research")
RESEARCH_BK = Path("/Volumes/research_bk")
RSYNC       = "/opt/homebrew/bin/rsync"
LAST_BACKUP = RESEARCH / "metadatos" / "last_backup.json"

BASE_FLAGS = [
    "-rv", "--size-only", "--no-perms", "--no-owner", "--no-group",
    "--exclude=.DS_Store", "--exclude=.Trashes", "--exclude=.fseventsd",
    "--exclude=.Spotlight-V100", "--exclude=.DocumentRevisions-V100",
    "--exclude=.TemporaryItems",
]

# ---------------------------------------------------------------------------
# Estado de montaje y última copia
# ---------------------------------------------------------------------------

st.title("💾 Backup")

mounted = os.path.ismount(str(RESEARCH_BK))

if not mounted:
    st.warning("Monta research_bk: VPN + Finder → Conectar al servidor, y recarga")

lb = read_last_backup()
if lb:
    try:
        last_dt = datetime.fromisoformat(lb["last_backup"])
        dias = (datetime.now() - last_dt).days
        st.metric("Último backup", last_dt.strftime("%Y-%m-%d %H:%M"),
                  delta=f"hace {dias} días", delta_color="inverse")
    except Exception:
        st.caption(f"Último backup: {lb.get('last_backup', '?')}")
else:
    st.caption("Último backup: **nunca**")

st.divider()

# ---------------------------------------------------------------------------
# Helper de streaming
# ---------------------------------------------------------------------------

def run_rsync(dry: bool) -> tuple[int, list[str]]:
    cmd = [RSYNC] + (["-n"] if dry else []) + BASE_FLAGS + [
        str(RESEARCH) + "/",
        str(RESEARCH_BK) + "/",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines: list[str] = []
    placeholder = st.empty()
    for raw in proc.stdout:
        lines.append(raw.rstrip())
        placeholder.code("\n".join(lines[-60:]), language="text")
    proc.wait()
    return proc.returncode, lines

# ---------------------------------------------------------------------------
# Botones
# ---------------------------------------------------------------------------

col_dry, col_real = st.columns(2)

with col_dry:
    if st.button("🔍 Ver qué cambiaría", disabled=not mounted, use_container_width=True):
        with st.spinner("Simulando rsync…"):
            rc, lines = run_rsync(dry=True)
        if rc == 0:
            st.success(f"Simulacro completado — {len(lines)} líneas de salida")
        else:
            st.error(f"rsync terminó con código {rc}")
            st.code("\n".join(lines[-15:]), language="text")

with col_real:
    if st.button("💾 Copiar ahora", disabled=not mounted, use_container_width=True,
                 type="primary"):
        st.session_state["_backup_running"] = True
        st.rerun()

if st.session_state.get("_backup_running"):
    st.session_state.pop("_backup_running", None)
    with st.spinner("Copiando…"):
        rc, lines = run_rsync(dry=False)
    if rc == 0:
        rec = {"last_backup": datetime.now().isoformat(timespec="seconds"), "exit_code": 0}
        try:
            LAST_BACKUP.parent.mkdir(parents=True, exist_ok=True)
            with LAST_BACKUP.open("w", encoding="utf-8") as f:
                json.dump(rec, f)
        except Exception as e:
            st.warning(f"No se pudo escribir el registro: {e}")
        st.success("✅ Backup completado")
        st.rerun()
    else:
        st.error(f"rsync terminó con código {rc} — últimas líneas:")
        st.code("\n".join(lines[-15:]), language="text")
