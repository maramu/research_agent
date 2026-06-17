# -*- coding: utf-8 -*-
"""
10_Duplicados.py — Revisión manual de duplicados (solo app privada).

Detecta duplicados por TÍTULO y por HASH del PDF reutilizando la lógica de
9_cleanup_duplicates.py. Permite elegir manualmente qué candidato conservar,
descargar cada PDF, mover los demás a CUARENTENA (reversible, no borrado duro)
y re-indexar las categorías afectadas.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

# Permitir import de app_utils.py de la carpeta padre (mismo patrón que 2_RAG.py)
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for _d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import CATEGORIAS_DIR, check_password, is_public_app

st.set_page_config(page_title="Duplicados", page_icon="🧹", layout="wide")

# Guard: página solo privada
if is_public_app():
    st.stop()
if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()

st.title("🧹 Revisión de duplicados")

# ── Importar 9_cleanup_duplicates.py por ruta (nombre no importable) ──────────
_spec = importlib.util.spec_from_file_location(
    "cleanup_dups", str(SCRIPTS_DIR / "9_cleanup_duplicates.py"))
cleanup = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cleanup          # <-- necesario para @dataclass
_spec.loader.exec_module(cleanup)


# ── Detección cacheada con invalidación tras aplicar ─────────────────────────
if "dup_nonce" not in st.session_state:
    st.session_state.dup_nonce = 0


@st.cache_data(show_spinner="Escaneando duplicados…")
def scan(nonce: int):
    cats = list(cleanup.CATEGORIES)
    base = CATEGORIAS_DIR
    return (cleanup.detect_title_duplicates(cats, base),
            cleanup.detect_hash_duplicates(cats, base))


title_dups, hash_dups = scan(st.session_state.dup_nonce)

if st.button("🔄 Re-escanear"):
    st.session_state.dup_nonce += 1
    st.rerun()


# ── Helper: resolver y leer el PDF de un candidato (botón de descarga) ───────
def _pdf_bytes(category, paper_id):
    for p in cleanup.candidate_paths(CATEGORIAS_DIR / category, paper_id):
        if p.suffix.lower() == ".pdf" and p.exists():
            try:
                return p.name, p.read_bytes()
            except Exception:
                return None, None
    return None, None


def _has_pdf(category, paper_id):
    for p in cleanup.candidate_paths(CATEGORIAS_DIR / category, paper_id):
        if p.suffix.lower() == ".pdf" and p.exists():
            return True
    return False


def _default_keep_index(papers):
    # prioridad: tiene PDF > stem limpio Crossref > orden original
    order = sorted(range(len(papers)), key=lambda i: (
        not _has_pdf(papers[i]["category"], papers[i]["paper_id"]),
        not cleanup._is_clean_stem(papers[i]["paper_id"]),
        i,
    ))
    return order[0]


KEEP_ALL_LABEL = "✅ No es duplicado — conservar todos"


def _candidate_label(c) -> str:
    return (f"{c['category']} · {c['paper_id']} · {c.get('year', '') or ''} · "
            f"DOI {c.get('doi', '') or '—'}")


def render_group(section: str, gi: int, group: dict, is_title: bool) -> None:
    """Renderiza un grupo de duplicados (común a título y hash)."""
    papers = group["papers"]

    if is_title:
        header = group.get("norm_title", "")
        st.markdown(f"**Título:** {header}")
    else:
        header = group.get("sha256", "")
        st.markdown(f"**SHA-256:** `{header}`")

    if is_title:
        # Guard falsos positivos: varios PDFs reales y/o DOIs distintos sugieren
        # papers diferentes con el mismo título normalizado → no borrar por defecto.
        pdfs_con = sum(1 for c in papers if _has_pdf(c["category"], c["paper_id"]))
        dois = {(c.get("doi") or "").strip() for c in papers if (c.get("doi") or "").strip()}
        riesgo = pdfs_con >= 2 or len(dois) >= 2
        if riesgo:
            st.warning(
                "⚠️ Varios candidatos con PDF y/o DOIs distintos: posible falso positivo "
                "(mismo título, papers diferentes). Por defecto NO se borra — revisa antes.")
            default_index = len(papers)            # índice de "conservar todos"
        else:
            default_index = _default_keep_index(papers)
    else:
        # Hash-dups: byte-idénticos = duplicados reales, sin guard.
        default_index = _default_keep_index(papers)

    labels = [_candidate_label(c) for c in papers]
    options = labels + [KEEP_ALL_LABEL]
    st.radio(
        "Conservar:",
        options=options,
        index=default_index,
        key=f"{section}_{gi}",
    )

    # Botón de descarga del PDF de cada candidato
    for ci, c in enumerate(papers):
        st.caption(_candidate_label(c))
        name, data = _pdf_bytes(c["category"], c["paper_id"])
        if data:
            st.download_button(
                f"⬇️ {name}",
                data=data,
                file_name=name,
                mime="application/pdf",
                key=f"dl_{section}_{gi}_{ci}",
            )
        else:
            st.caption("PDF no encontrado")

    st.divider()


# ── Secciones ────────────────────────────────────────────────────────────────
tab_title, tab_hash = st.tabs(["Por título", "Por hash PDF"])

with tab_title:
    if not title_dups:
        st.success("Sin duplicados por título.")
    else:
        for gi, group in enumerate(title_dups):
            render_group("title", gi, group, is_title=True)

with tab_hash:
    if not hash_dups:
        st.success("Sin duplicados por hash PDF.")
    else:
        for gi, group in enumerate(hash_dups):
            render_group("hash", gi, group, is_title=False)


# ── Cálculo de a-cuarentena ──────────────────────────────────────────────────
def _compute_to_quarantine() -> list[tuple[str, str]]:
    to_quarantine: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for section, groups in (("title", title_dups), ("hash", hash_dups)):
        for gi, group in enumerate(groups):
            papers = group["papers"]
            choice = st.session_state.get(f"{section}_{gi}")
            if choice is None or choice == KEEP_ALL_LABEL:
                continue
            labels = [_candidate_label(c) for c in papers]
            keep_idx = labels.index(choice) if choice in labels else None
            for i, c in enumerate(papers):
                if i == keep_idx:
                    continue
                key = (c["category"], c["paper_id"])
                if key in seen:
                    continue
                seen.add(key)
                to_quarantine.append(key)
    return to_quarantine


to_quarantine = _compute_to_quarantine()


# ── Confirmación y aplicación ────────────────────────────────────────────────
st.header("Mover a cuarentena")

if to_quarantine:
    st.warning(
        f"Se moverán a cuarentena **{len(to_quarantine)}** paper(s):\n\n"
        + "\n".join(f"- `{cat}` · {pid}" for cat, pid in to_quarantine)
    )
else:
    st.info("Nada seleccionado para cuarentena (todos marcados como «conservar»).")

confirm = st.checkbox(
    "Confirmo mover a cuarentena los seleccionados", key="dup_confirm")

if st.button(
    "🗑️ Mover a cuarentena",
    type="primary",
    disabled=(not to_quarantine or not confirm),
):
    dest_root = (CATEGORIAS_DIR.parent / "quarantine" / "duplicates"
                 / datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    affected: set[str] = set()
    total_moved = 0
    for category, pid in to_quarantine:
        moved, _ = cleanup.quarantine_paper(category, pid, CATEGORIAS_DIR, dest_root)
        total_moved += len(moved)
        if moved:
            affected.add(category)
    st.session_state["dup_affected"] = sorted(affected)
    st.session_state.dup_nonce += 1          # invalida el escaneo
    st.success(f"Movidos {total_moved} ficheros a {dest_root}")
    st.rerun()


# ── Re-indexado de categorías afectadas ──────────────────────────────────────
dup_affected = st.session_state.get("dup_affected", [])

if dup_affected:
    st.header("Re-indexado")
    st.markdown(
        "Categorías afectadas por la última cuarentena: "
        + ", ".join(f"`{c}`" for c in dup_affected)
    )

    if st.button("🔁 Reprocesar (re-indexar) categorías afectadas", type="primary"):
        results: dict[str, int] = {}
        for cat in dup_affected:
            st.subheader(f"📁 {cat}")
            log_lines: list[str] = []
            status_box = st.status(f"Re-indexando {cat}…", expanded=True)
            output_box = status_box.empty()
            cmd = [
                sys.executable, str(SCRIPTS_DIR / "5_build_embeddings.py"),
                "--project", cat, "--force", "--model", "bge-m3",
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:  # type: ignore[union-attr]
                log_lines.append(line.rstrip("\n"))
                output_box.code("\n".join(log_lines[-200:]), language="text")
            rc = proc.wait()
            results[cat] = rc
            if rc == 0:
                status_box.update(label=f"✓ {cat} re-indexado", state="complete")
            else:
                status_box.update(label=f"✗ {cat} falló (rc={rc})", state="error")

        ok = [c for c, rc in results.items() if rc == 0]
        ko = [c for c, rc in results.items() if rc != 0]
        if ok:
            st.success(f"OK: {', '.join(ok)}")
        if ko:
            st.error(f"Error: {', '.join(ko)}")
        # Limpiar para no re-ejecutar accidentalmente
        st.session_state.pop("dup_affected", None)


# ── Restaurar de cuarentena ──────────────────────────────────────────────────
st.header("♻️ Restaurar de cuarentena")

_DUP_QUARANTINE = CATEGORIAS_DIR.parent / "quarantine" / "duplicates"

# Warnings y resumen de la última restauración (sobreviven al st.rerun)
for _w in st.session_state.pop("restore_warnings", []):
    st.warning(_w)
_flash = st.session_state.pop("restore_flash", None)
if _flash:
    st.success(_flash)


@st.cache_data(show_spinner="Escaneando cuarentena…")
def scan_quarantine(nonce: int):
    """{ts: [{manifest, category, paper_id, has_meta}, …]} ordenado por ts desc."""
    out: dict[str, list[dict]] = {}
    if not _DUP_QUARANTINE.exists():
        return out
    for mp in sorted(_DUP_QUARANTINE.glob("*/*/_manifest_*.json")):
        rel = mp.relative_to(_DUP_QUARANTINE).parts
        if len(rel) < 2:
            continue
        ts = rel[0]
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.setdefault(ts, []).append({
            "manifest": str(mp),
            "category": data.get("category", rel[1]),
            "paper_id": data.get("paper_id", ""),
            "has_meta": bool(data.get("meta_lines")),
        })
    return dict(sorted(out.items(), key=lambda kv: kv[0], reverse=True))


_quarantine = scan_quarantine(st.session_state.dup_nonce)

if not _quarantine:
    st.info("No hay nada en cuarentena de duplicados.")
else:
    ts_sel = st.selectbox(
        "Lote de cuarentena (timestamp):", list(_quarantine.keys()), key="restore_ts")
    entries = _quarantine.get(ts_sel, [])

    def _entry_label(e: dict) -> str:
        flag = "✓ meta" if e["has_meta"] else "✗ sin meta"
        return f"{e['category']} · {e['paper_id']} · {flag}"

    labels = [_entry_label(e) for e in entries]
    chosen = st.multiselect("Manifiestos a restaurar:", options=labels, key="restore_sel")
    selected_entries = [e for e, lab in zip(entries, labels) if lab in chosen]

    if selected_entries:
        st.warning(
            f"Se restaurarán **{len(selected_entries)}** paper(s):\n\n"
            + "\n".join(
                f"- `{e['category']}` · {e['paper_id']}"
                + ("" if e["has_meta"] else " (sin meta_lines)")
                for e in selected_entries)
        )
    else:
        st.info("Nada seleccionado para restaurar.")

    restore_confirm = st.checkbox(
        "Confirmo restaurar los seleccionados", key="restore_confirm")

    if st.button(
        "♻️ Restaurar",
        type="primary",
        disabled=(not selected_entries or not restore_confirm),
    ):
        affected: set[str] = set(st.session_state.get("dup_affected", []))
        total_restored = 0
        all_warnings: list[str] = []
        for e in selected_entries:
            restored, meta_updated, warns = cleanup.restore_from_quarantine(
                Path(e["manifest"]), CATEGORIAS_DIR)
            total_restored += len(restored)
            all_warnings.extend(warns)
            if restored or meta_updated:
                affected.add(e["category"])
        st.session_state["dup_affected"] = sorted(affected)
        st.session_state["restore_warnings"] = all_warnings
        st.session_state["restore_flash"] = (
            f"Restaurados {total_restored} fichero(s) desde cuarentena.")
        st.session_state.dup_nonce += 1          # invalida escaneos cacheados
        st.rerun()
