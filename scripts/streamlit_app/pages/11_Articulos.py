# -*- coding: utf-8 -*-
"""
11_Articulos.py — Catálogo bibliográfico filtrable (privado y público).

Dos secciones:
  A) Tabla resumen por categoría (mismas columnas que la portada / Pendientes).
  B) Listado de artículos de una categoría (o todas) con filtros por texto
     (título/DOI/autor), año, revista y solo-con-DOI; DOI clicable, export CSV
     y métricas de la selección.

No ejecuta nada sobre el corpus: solo lee papers_metadata.jsonl por categoría.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime, date
from pathlib import Path

import openpyxl
import pandas as pd
import requests
import streamlit as st

# Permitir import de app_utils.py de la carpeta padre (mismo patrón que 2_RAG.py)
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = STREAMLIT_APP_DIR.parent
for _d in (str(STREAMLIT_APP_DIR), str(SCRIPTS_DIR)):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from app_utils import (
    CATEGORIAS_DIR, DOI_MANUAL_XLSX, METADATOS_DIR,
    check_password, is_public_app,
    list_existing_categories, get_categories_summary,
)

# ── Helpers para DOI ──

# Email para Crossref (usa UNPAYWALL_EMAIL de config/.env como mailto educado)
_CROSSREF_MAILTO = os.getenv("UNPAYWALL_EMAIL", "")


def _fmt_authors(authors):
    """Convierte la lista de autores (dicts/strings) en texto legible."""
    if not authors:
        return ""
    if isinstance(authors, str):
        return authors
    out = []
    for a in authors:
        if isinstance(a, dict):
            fn = (a.get("forename") or "").strip()
            sn = (a.get("surname") or "").strip()
            nombre = (fn + " " + sn).strip() or (a.get("full") or "").strip()
        else:
            nombre = str(a)
        if nombre:
            out.append(nombre)
    return "; ".join(out)


def _first_author_surname(authors) -> str:
    """Apellido del primer autor (best-effort) para afinar Crossref."""
    if not authors:
        return ""
    if isinstance(authors, list):
        a = authors[0]
        if isinstance(a, dict):
            return (a.get("surname") or "").strip() or (a.get("full") or "").strip()
        return str(a).strip()
    if isinstance(authors, str):
        first = authors.split(";")[0].split(",")[0].strip()
        return first.split()[-1] if first else ""
    return ""


def crossref_suggest(title: str, mailto: str = "",
                     author: str = "", year: str = "") -> list[dict]:
    """Busca candidatos de DOI en Crossref por título bibliográfico.

    Si están disponibles, añade apellido del primer autor y año a la
    query.bibliographic para mejorar la precisión del match. El contrato
    de salida (doi/title/year/journal) no cambia.
    """
    if not title or not title.strip():
        return []
    try:
        biblio = title.strip()
        extra = " ".join(p for p in (str(author).strip(), str(year).strip()) if p)
        if extra:
            biblio = f"{biblio} {extra}"
        params = {"query.bibliographic": biblio, "rows": 3}
        if not mailto:
            mailto = _CROSSREF_MAILTO
        if mailto:
            params["mailto"] = mailto
        r = requests.get(
            "https://api.crossref.org/works",
            params=params, timeout=15,
        )
        items = r.json().get("message", {}).get("items", [])
    except Exception:
        return []
    out = []
    for it in items:
        out.append({
            "doi":     it.get("DOI", ""),
            "title":   (it.get("title") or [""])[0],
            "year":    (it.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0],
            "journal": (it.get("container-title") or [""])[0],
        })
    return out


def assign_dois(category: str, updates: dict) -> int:
    """Actualiza papers_metadata.jsonl y doi_manual.xlsx con DOIs nuevos.

    Args:
        category: Nombre de la categoría.
        updates:  {paper_id: {"doi": str, "journal": str|None}}.

    Ambas escrituras hacen backup .bak previo.
    Devuelve el número de registros actualizados en el jsonl.
    """
    if not updates:
        return 0

    meta = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
    changed = 0
    if meta.exists():
        # Backup del jsonl
        bak = meta.with_suffix(meta.suffix + ".bak")
        shutil.copy(meta, bak)
        lines = []
        with meta.open(encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                d = json.loads(s)
                pid = d.get("paper_id") or d.get("stable_id") or ""
                if pid in updates and updates[pid].get("doi"):
                    d["doi"] = updates[pid]["doi"]
                    if updates[pid].get("journal") and not d.get("journal"):
                        d["journal"] = updates[pid]["journal"]
                    changed += 1
                lines.append(json.dumps(d, ensure_ascii=False))
        meta.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── Upsert en doi_manual.xlsx (mismo esquema que 1_rename_papers_by_doi.py) ──
    doi_xlsx = DOI_MANUAL_XLSX

    # Backup del xlsx
    if doi_xlsx.exists():
        bak_xlsx = doi_xlsx.with_name(doi_xlsx.name + ".bak")
        shutil.copy(doi_xlsx, bak_xlsx)

    if doi_xlsx.exists():
        wb = openpyxl.load_workbook(doi_xlsx)
        ws = wb.active
        # Leer existentes: {nombre_archivo -> row_idx (1-based)}
        existing: dict[str, int] = {}
        if ws.max_row is not None and ws.max_row >= 2:
            for row_idx in range(2, ws.max_row + 1):
                val = ws.cell(row=row_idx, column=1).value
                if val is not None:
                    existing[str(val).strip()] = row_idx
        # Localizar columna fecha_inclusion (o añadirla)
        n_cols = ws.max_column or 2
        header = [ws.cell(row=1, column=c).value for c in range(1, n_cols + 1)]
        hl = [str(h).strip().lower() if h is not None else "" for h in header]
        if "fecha_inclusion" in hl:
            fecha_col = hl.index("fecha_inclusion") + 1
        else:
            fecha_col = n_cols + 1
            ws.cell(row=1, column=fecha_col).value = "fecha_inclusion"
        today = date.today().isoformat()
        for pid, udata in updates.items():
            doi = udata.get("doi", "")
            if not doi:
                continue
            # En doi_manual la clave es nombre_archivo (stem del PDF con .pdf)
            nombre = pid + ".pdf"
            if nombre in existing:
                row_idx = existing[nombre]
                if not ws.cell(row=row_idx, column=2).value:
                    ws.cell(row=row_idx, column=2).value = doi
            else:
                row_data = [None] * fecha_col
                row_data[0] = nombre
                row_data[1] = doi
                row_data[fecha_col - 1] = today
                ws.append(row_data)
                existing[nombre] = ws.max_row
        wb.save(doi_xlsx)
    else:
        # Crear xlsx nuevo con cabecera
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["nombre_archivo", "doi", "fecha_inclusion"])
        today = date.today().isoformat()
        for pid, udata in updates.items():
            doi = udata.get("doi", "")
            if not doi:
                continue
            ws.append([pid + ".pdf", doi, today])
        wb.save(doi_xlsx)

    return changed


# ── Fin helpers DOI ─────────────────────────────────────────────────────────

st.set_page_config(page_title="Artículos", page_icon="📋", layout="wide")

_pwd = "PUBLIC_APP_PASSWORD" if is_public_app() else "PRIVATE_APP_PASSWORD"
if not check_password(_pwd):
    st.stop()

st.title("📋 Catálogo de artículos")

PUBLIC = is_public_app()


# ───────────────────────────────────────────────────────────────────────────
# SECCIÓN A — Tabla resumen por categoría
# ───────────────────────────────────────────────────────────────────────────

st.subheader("Resumen por categoría")


def _all_meta_mtime() -> float:
    cats = list_existing_categories()
    mtimes = []
    for cat in cats:
        p = CATEGORIAS_DIR / cat / "metadata" / "papers_metadata.jsonl"
        if p.exists():
            mtimes.append(p.stat().st_mtime)
    return max(mtimes) if mtimes else 0.0


@st.cache_data(show_spinner="Calculando resumen por categoría…")
def _summary_rows(mtime: float) -> list[dict]:
    return get_categories_summary()


summary = _summary_rows(_all_meta_mtime())
if summary:
    st.dataframe(
        pd.DataFrame(summary),
        hide_index=True,
        use_container_width=True,
        column_config={
            "PDFs": st.column_config.NumberColumn(width="small"),
            "MD limpio": st.column_config.NumberColumn(width="small"),
            "Resúmenes": st.column_config.NumberColumn(width="small"),
            "Chunks": st.column_config.NumberColumn(width="small"),
            "Metadata": st.column_config.NumberColumn(width="small"),
            "Paquetes": st.column_config.NumberColumn(width="small"),
            "Brechas": st.column_config.TextColumn(width="large"),
        },
    )
else:
    st.info("No hay categorías con PDFs en el NAS.")

st.divider()


# ───────────────────────────────────────────────────────────────────────────
# SECCIÓN B — Listado de artículos
# ───────────────────────────────────────────────────────────────────────────

st.subheader("Listado de artículos")


@st.cache_data(show_spinner="Cargando artículos…")
def load_articles(category: str, mtime: float) -> list[dict]:
    meta = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
    rows = []
    if meta.exists():
        with meta.open(encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    d = json.loads(s)
                except Exception:
                    continue
                authors_raw = d.get("authors")
                authors = _fmt_authors(authors_raw)
                first_author = _first_author_surname(authors_raw)
                refs = d.get("references")
                n_refs = len(refs) if isinstance(refs, list) else (d.get("n_references") or "")
                rows.append({
                    "category":      category,
                    "title":         d.get("title") or "",
                    "year":          d.get("year"),
                    "journal":       d.get("journal") or d.get("venue") or "",
                    "doi":           d.get("doi") or "",
                    "authors":       authors or "",
                    "first_author":  first_author,
                    "n_refs":        n_refs,
                    "quality_score": d.get("quality_score"),
                    "source_type":   d.get("source_type") or "",
                    "access_type":   d.get("access_type") or "",
                    "paper_id":      d.get("paper_id") or d.get("stable_id") or "",
                })
    return rows


def _meta_mtime(category: str) -> float:
    meta = CATEGORIAS_DIR / category / "metadata" / "papers_metadata.jsonl"
    return meta.stat().st_mtime if meta.exists() else 0.0


categories = list_existing_categories()
if not categories:
    st.info("No hay categorías en el NAS.")
    st.stop()

# ── Controles ────────────────────────────────────────────────────────────────
TODAS = "(Todas)"
sel = st.selectbox("Categoría", options=[TODAS] + categories, index=0)

if sel == TODAS:
    rows: list[dict] = []
    for cat in categories:
        rows.extend(load_articles(cat, _meta_mtime(cat)))
else:
    rows = load_articles(sel, _meta_mtime(sel))

if not rows:
    if sel == TODAS:
        st.info("No hay artículos con metadata (papers_metadata.jsonl) en ninguna categoría.")
    else:
        st.info(f"La categoría `{sel}` no tiene papers_metadata.jsonl o está vacío.")
    st.stop()

c1, c2 = st.columns([2, 1])
with c1:
    txt = st.text_input(
        "Búsqueda (título, DOI o autores)",
        value="",
        placeholder="Ej: anaerobic digestion, 10.1016/…, García",
    )
with c2:
    journals = sorted({r["journal"] for r in rows if r["journal"]})
    sel_journals = st.multiselect("Revista (opcional)", options=journals, default=[])

c3, c4 = st.columns([2, 1])
with c3:
    years = [int(r["year"]) for r in rows if isinstance(r["year"], (int, float)) or
             (isinstance(r["year"], str) and r["year"].strip().isdigit())]
    if years:
        y_min, y_max = min(years), max(years)
        usar_year = st.checkbox("Filtrar por año", value=False)
        if usar_year and y_min < y_max:
            ys, ye = st.slider("Rango de años", y_min, y_max, (y_min, y_max))
        elif usar_year:
            ys = ye = y_min
        else:
            ys = ye = None
    else:
        ys = ye = None
with c4:
    doi_filter = st.radio(
        "DOI", options=["Todos", "Con DOI", "Sin DOI"],
        index=0, horizontal=True, key="doi_filter",
    )
    solo_doi = (doi_filter == "Con DOI")
    solo_sin_doi = (doi_filter == "Sin DOI")


# ── Aplicar filtros en cascada ───────────────────────────────────────────────
def _year_int(v):
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


filtered = rows
if txt.strip():
    q = txt.strip().lower()
    filtered = [
        r for r in filtered
        if q in str(r["title"]).lower()
        or q in str(r["doi"]).lower()
        or q in str(r["authors"]).lower()
    ]
if sel_journals:
    jset = set(sel_journals)
    filtered = [r for r in filtered if r["journal"] in jset]
if ys is not None and ye is not None:
    filtered = [
        r for r in filtered
        if (_y := _year_int(r["year"])) is not None and ys <= _y <= ye
    ]
if solo_sin_doi:
    filtered = [r for r in filtered if not str(r["doi"]).strip()]
elif solo_doi:
    filtered = [r for r in filtered if str(r["doi"]).strip()]

st.caption(f"**{len(filtered)}** artículo(s) tras filtrar (de {len(rows)} cargados).")

if not filtered:
    st.warning("Sin resultados con esos filtros. Prueba aflojando los filtros.")
    st.stop()

# ── Tira de métricas ─────────────────────────────────────────────────────────
n_art = len(filtered)
n_doi = sum(1 for r in filtered if str(r["doi"]).strip())
pct_doi = round(100 * n_doi / n_art) if n_art else 0
f_years = [y for r in filtered if (y := _year_int(r["year"])) is not None]
qscores = [float(r["quality_score"]) for r in filtered
           if isinstance(r["quality_score"], (int, float))]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Artículos", n_art)
m2.metric("% con DOI", f"{pct_doi}%")
m3.metric("Años", f"{min(f_years)}–{max(f_years)}" if f_years else "—")
m4.metric("Calidad media", f"{sum(qscores) / len(qscores):.2f}" if qscores else "—")

# ── Tabla ────────────────────────────────────────────────────────────────────
df = pd.DataFrame(filtered)
df["doi_url"] = df["doi"].apply(
    lambda d: f"https://doi.org/{d}" if str(d).strip() else "")

if PUBLIC:
    cols = ["title", "year", "journal", "doi_url"]
else:
    cols = ["title", "year", "journal", "doi_url", "authors", "n_refs",
            "quality_score", "source_type", "access_type", "paper_id"]

col_config = {
    "title":         st.column_config.TextColumn("Título", width="large"),
    "year":          st.column_config.NumberColumn("Año", width="small"),
    "journal":       st.column_config.TextColumn("Revista"),
    "doi_url":       st.column_config.LinkColumn(
        "DOI", display_text=r"https://doi\.org/(.+)"),
    "authors":       st.column_config.TextColumn("Autores"),
    "n_refs":        st.column_config.NumberColumn("Refs", width="small"),
    "quality_score": st.column_config.NumberColumn("Calidad", width="small"),
    "source_type":   st.column_config.TextColumn("Origen"),
    "access_type":   st.column_config.TextColumn("Acceso"),
    "paper_id":      st.column_config.TextColumn("paper_id"),
}

st.dataframe(
    df[cols],
    hide_index=True,
    use_container_width=True,
    column_config=col_config,
)

# ── Export CSV de la vista filtrada ──────────────────────────────────────────
_today = datetime.now().strftime("%Y-%m-%d")
_slug = "todas" if sel == TODAS else sel
csv_bytes = df[cols].to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ Exportar CSV (vista filtrada)",
    data=csv_bytes,
    file_name=f"articulos_{_slug}_{_today}.csv",
    mime="text/csv",
)


# ───────────────────────────────────────────────────────────────────────────
# ✏️ Asignar DOIs faltantes (SOLO INSTANCIA PRIVADA)
# ───────────────────────────────────────────────────────────────────────────
if not PUBLIC:
    st.divider()
    st.subheader("✏️ Asignar DOIs faltantes")

    # Solo permitir edición si hay una categoría concreta seleccionada
    if sel == TODAS:
        st.info(
            "Selecciona una categoría concreta en el selector de arriba "
            "para habilitar la edición de DOIs."
        )
    else:
        # Subconjunto sin DOI de la categoría actual
        sin_doi_rows = load_articles(sel, _meta_mtime(sel))
        sin_doi_rows = [r for r in sin_doi_rows if not str(r["doi"]).strip()]

        if not sin_doi_rows:
            st.success("Todos los artículos de esta categoría tienen DOI. ¡Perfecto!")
        else:
            st.caption(
                f"{len(sin_doi_rows)} artículo(s) sin DOI en **{sel}** "
                f"(de {len(rows)} cargados)."
            )

            # ── Botón: sugerir desde Crossref ──
            sug_key = f"doi_suggestions_{sel}"
            nonce = st.session_state.get("doi_editor_nonce", 0)
            ccol1, ccol2 = st.columns([3, 1])
            with ccol1:
                if st.button("🔎 Sugerir desde Crossref (visibles)", use_container_width=True):
                    with st.spinner(f"Consultando Crossref para {len(sin_doi_rows)} artículos…"):
                        suggestions = {}
                        n_sug = 0
                        for i, r in enumerate(sin_doi_rows):
                            title = r.get("title", "")
                            if title:
                                cands = crossref_suggest(
                                    title,
                                    author=r.get("first_author", ""),
                                    year=str(r.get("year") or ""),
                                )
                                if cands:
                                    suggestions[r["paper_id"]] = cands[0]
                                    n_sug += 1
                            if i < len(sin_doi_rows) - 1:
                                time.sleep(0.3)
                        st.session_state[sug_key] = suggestions
                        # Bump del nonce → fuerza reset del st.data_editor con
                        # los DOIs sugeridos pre-rellenados.
                        st.session_state["doi_editor_nonce"] = nonce + 1
                        st.success(
                            f"Crossref encontró {n_sug} candidato(s) "
                            f"de {len(sin_doi_rows)}."
                        )
                        st.rerun()
            with ccol2:
                if st.button("🗑️ Limpiar", use_container_width=True):
                    st.session_state.pop(sug_key, None)
                    # Bump del nonce → resetea el estado del editor.
                    st.session_state["doi_editor_nonce"] = nonce + 1
                    st.rerun()

            suggestions = st.session_state.get(sug_key, {})

            # Construir dataframe para el editor: una sola columna DOI editable
            # (pre-rellenada con la sugerencia) + verificación Crossref disabled.
            editor_rows = []
            for r in sin_doi_rows:
                pid = r["paper_id"]
                sug = suggestions.get(pid, {})
                match_parts = [
                    str(sug.get("title") or "").strip(),
                    str(sug.get("year") or "").strip(),
                    str(sug.get("journal") or "").strip(),
                ]
                match_txt = " · ".join(p for p in match_parts if p)
                editor_rows.append({
                    "paper_id":     pid,
                    "title":        r.get("title", ""),
                    "year":         r.get("year", ""),
                    "journal":      r.get("journal", ""),
                    # DOI editable, pre-rellenado con la sugerencia si existe
                    "doi":          str(sug.get("doi") or ""),
                    "match":        match_txt,
                })

            if not editor_rows:
                st.info("No hay filas para editar.")
            else:
                df_editor = pd.DataFrame(editor_rows)

                col_cfg = {
                    "paper_id": st.column_config.TextColumn("paper_id", disabled=True),
                    "title":    st.column_config.TextColumn("Título", disabled=True, width="large"),
                    "year":     st.column_config.NumberColumn("Año", disabled=True, width="small"),
                    "journal":  st.column_config.TextColumn("Revista", disabled=True, width="medium"),
                    "doi":      st.column_config.TextColumn(
                        "✏️ DOI (editable)", disabled=False, width="medium"),
                    "match":    st.column_config.TextColumn(
                        "Coincidencia Crossref (título · año · revista)",
                        disabled=True, width="large"),
                }

                edited = st.data_editor(
                    df_editor,
                    column_config=col_cfg,
                    column_order=["paper_id", "title", "year", "journal", "doi", "match"],
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key=f"doi_data_editor_{sel}_{nonce}",
                )

                # Botón guardar — leer DOIs del DataFrame DEVUELTO por el editor
                if st.button("💾 Guardar DOIs", type="primary", use_container_width=True):
                    updates = {}
                    for _, row in edited.iterrows():
                        doi_val = str(row.get("doi", "")).strip()
                        if doi_val:
                            updates[row["paper_id"]] = {
                                "doi": doi_val,
                                "journal": str(row.get("journal", "")).strip() or None,
                            }
                    if not updates:
                        st.warning("No hay DOIs nuevos para guardar.")
                    else:
                        n_changed = assign_dois(sel, updates)
                        st.success(
                            f"✓ {n_changed} registro(s) actualizado(s) en "
                            f"papers_metadata.jsonl y doi_manual.xlsx. "
                            f"Backups guardados con extensión .bak."
                        )
                        st.session_state.pop(sug_key, None)
                        st.session_state["doi_editor_nonce"] = nonce + 1
                        st.rerun()
