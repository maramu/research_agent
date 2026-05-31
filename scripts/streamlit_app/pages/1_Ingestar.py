# -*- coding: utf-8 -*-
"""
1_📥_Ingestar.py — Ejecutar los tres flujos del pipeline.

Flujos:
  - Scopus: búsqueda Scopus API → descarga → procesado por categoría
  - Inbox:  PDFs en /Volumes/research/inbox → rename → screen → procesado
  - Pendientes: reanudar categorías con PDFs sin md_clean
  - Ad-hoc: carpeta de PDFs → proyecto temporal → procesado + RAG

Cada flujo se ejecuta importando directamente las funciones de pipeline.py
y se enchufa un callback on_output que va volcando líneas a un placeholder
de Streamlit en tiempo real.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Permitir import de utils.py de la carpeta padre
STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
if str(STREAMLIT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP_DIR))

from app_utils import (
    CANONICAL_CATEGORIES, CATEGORIAS_DIR, CONFIG_DIR, INBOX_DIR,
    PIPELINE_AVAILABLE, PIPELINE_IMPORT_ERROR,
    check_grobid, check_nas, check_ollama,
    get_category_stats,
    list_existing_categories,
    load_yaml,
)

st.set_page_config(page_title="Ingestar", page_icon="📥", layout="wide")
st.title("📥 Ingestar")

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if not PIPELINE_AVAILABLE:
    st.error(f"No se puede importar `pipeline.py`: {PIPELINE_IMPORT_ERROR}")
    st.stop()

from pipeline import (  # noqa: F401
    integrate_adhoc,
    process_category,
    promote_adhoc_to_category,
    run_adhoc,
    run_inbox,
    run_inbox_process,
    run_inbox_screen,
    run_scopus,
)

nas_ok,    nas_msg    = check_nas()
ollama_ok, ollama_msg = check_ollama()
grobid_ok, grobid_msg = check_grobid()

c1, c2, c3 = st.columns(3)
c1.markdown(f"**NAS**: {'🟢' if nas_ok else '🔴'} {nas_msg}")
c2.markdown(f"**Ollama**: {'🟢' if ollama_ok else '🔴'} {ollama_msg}")
c3.markdown(f"**GROBID**: {'🟢' if grobid_ok else '🔴'} {grobid_msg}")

if not nas_ok:
    st.error("El NAS no está montado. Acción bloqueada.")
    st.stop()

if not (ollama_ok and grobid_ok):
    st.warning(
        "Ollama o GROBID no responden. Puedes lanzar la ingesta igualmente "
        "pero los pasos que los requieran fallarán."
    )

st.divider()


# ---------------------------------------------------------------------------
# Helper: lanzar un flujo capturando salida en directo
# ---------------------------------------------------------------------------

def execute_with_live_output(fn, label: str, **kwargs):
    """Ejecuta fn(**kwargs, on_output=...) y va volcando líneas a un placeholder.

    Devuelve el dict resultado de la función (o None si hubo excepción).
    """
    log_lines: list[str] = []
    status_box  = st.status(f"Ejecutando {label}…", expanded=True)
    output_box  = status_box.empty()
    MAX_LINES = 200

    def on_output(line: str) -> None:
        log_lines.append(line)
        # Mostrar solo las últimas N líneas para no saturar
        visible = log_lines[-MAX_LINES:]
        output_box.code("\n".join(visible), language="text")

    try:
        result = fn(on_output=on_output, **kwargs)
    except Exception as e:
        status_box.update(label=f"✗ {label} — error: {e}", state="error")
        st.exception(e)
        return None

    overall = result.get("status")
    returncode = result.get("returncode")
    if overall == "ok" or returncode == 0:
        status_box.update(label=f"✓ {label} completado", state="complete")
    elif overall == "partial":
        status_box.update(label=f"⚠️ {label} completado con errores parciales", state="error")
    else:
        status_box.update(label=f"✗ {label} falló", state="error")

    return result


def run_pending_categories(categories: list[str], on_output=None) -> dict:
    """Procesa categorías ya pobladas en categorias/<cat>/pdfs/."""
    results = {}
    for cat in categories:
        if on_output:
            on_output("")
            on_output("=" * 60)
            on_output(f"CATEGORÍA PENDIENTE: {cat}")
            on_output("=" * 60)
        results[cat] = process_category(cat, on_output=on_output)

    ok = sum(1 for item in results.values() if item.get("status") == "ok")
    total = len(results)
    status = "ok" if ok == total else ("partial" if ok > 0 else "error")
    return {"status": status, "categories": results}


def category_resume_row(category: str) -> dict:
    """Resume brechas de procesado para decidir si una categoría necesita reanudar."""
    stats = get_category_stats(category)
    expected = int(stats.get("md_clean") or stats.get("pdfs") or 0)
    missing_md = max(0, int(stats.get("pdfs", 0)) - int(stats.get("md_clean", 0)))
    missing_summaries = max(0, expected - int(stats.get("summaries", 0)))
    missing_chunks = max(0, expected - int(stats.get("chunks", 0)))
    missing_metadata = max(0, expected - int(stats.get("metadata", 0)))

    gaps = []
    if missing_md:
        gaps.append(f"MD limpio: {missing_md}")
    if missing_summaries:
        gaps.append(f"Resúmenes: {missing_summaries}")
    if missing_chunks:
        gaps.append(f"Chunks: {missing_chunks}")
    if missing_metadata:
        gaps.append(f"Metadata: {missing_metadata}")

    return {
        "Categoría": category,
        "PDFs": int(stats.get("pdfs", 0)),
        "MD limpio": int(stats.get("md_clean", 0)),
        "Resúmenes": int(stats.get("summaries", 0)),
        "Chunks": int(stats.get("chunks", 0)),
        "Metadata": int(stats.get("metadata", 0)),
        "FAISS": "✓" if stats.get("embeddings") else "—",
        "Paquetes": int(stats.get("packages", 0)),
        "Brechas": ", ".join(gaps) if gaps else "Completo",
        "_needs_resume": bool(gaps),
    }


# ---------------------------------------------------------------------------
# Auto-recuperación de estado Inbox desde disco
# ---------------------------------------------------------------------------

_pending_csv = INBOX_DIR.parent / "metadatos" / "cribado_pendiente.csv"
if _pending_csv.exists():
    _was_recovered = not st.session_state.get("inbox_screen_done")
    st.session_state["inbox_screen_done"] = True
    st.session_state["inbox_csv_path"] = str(_pending_csv)
    if "inbox_rows" not in st.session_state:
        import csv as _csv_restore
        with _pending_csv.open(encoding="utf-8", newline="") as _f:
            st.session_state["inbox_rows"] = list(_csv_restore.DictReader(_f))
    if _was_recovered:
        st.toast("✅ Estado de Inbox recuperado desde disco")

# ---------------------------------------------------------------------------
# Tabs por flujo
# ---------------------------------------------------------------------------

tab_scopus, tab_inbox, tab_pending, tab_adhoc = st.tabs([
    "🌐 Scopus",
    "📂 Inbox",
    "⏳ Pendientes",
    "🧪 Ad-hoc",
])

# ─────────────────────────────────────────────────────────────────────────────
# FLUJO A — Scopus
# ─────────────────────────────────────────────────────────────────────────────

with tab_scopus:
    st.markdown(
        "Consulta Scopus por categoría con las queries definidas en "
        "`config/scopus_queries.yml`. Los PDFs se descargan directamente a "
        "`categorias/<cat>/pdfs/` y se procesa la cadena completa."
    )

    # Cargar queries para mostrar resumen
    queries_file = CONFIG_DIR / "scopus_queries.yml"
    queries_data = load_yaml(queries_file)
    available_cats = list(queries_data.keys()) if queries_data else CANONICAL_CATEGORIES

    with st.form("scopus_form"):
        sel_cats = st.multiselect(
            "Categorías (vacío = todas)",
            options=available_cats,
            default=[],
            help="Si dejas vacío, se procesan todas las categorías con queries definidas",
        )

        col1, col2 = st.columns(2)
        with col1:
            recent_days = st.number_input(
                "Días recientes (PUBYEAR vs hoy)", min_value=0, max_value=3650,
                value=0, step=1,
                help="0 = sin filtro. Para ingesta semanal usa 7.",
            )
            max_results = st.number_input(
                "Máx. resultados por categoría", min_value=1, max_value=5000,
                value=200, step=50,
            )
            doctype = st.selectbox(
                "Tipo de documento", options=["", "ar", "re", "cp"],
                index=0,
                help="ar=article, re=review, cp=conference paper. Vacío=todos",
            )

        with col2:
            year_start = st.number_input(
                "Año inicio (opcional)", min_value=0, max_value=2100,
                value=0, step=1,
            )
            year_end = st.number_input(
                "Año fin (opcional)", min_value=0, max_value=2100,
                value=0, step=1,
            )
            dry_run = st.checkbox(
                "Dry-run (solo simular, no descargar)",
                value=False,
            )

        submit_scopus = st.form_submit_button(
            "▶ Ejecutar flujo Scopus", type="primary", use_container_width=True,
        )

    if submit_scopus:
        kwargs = {
            "categories":  sel_cats if sel_cats else None,
            "recent_days": int(recent_days) if recent_days else None,
            "max_results": int(max_results),
            "year_start":  int(year_start) if year_start else None,
            "year_end":    int(year_end)   if year_end   else None,
            "doctype":     doctype if doctype else None,
            "queries_file": str(queries_file) if queries_file.exists() else None,
            "dry_run":     dry_run,
        }
        result = execute_with_live_output(run_scopus, "Scopus", **kwargs)
        if result:
            with st.expander("📊 Resumen detallado", expanded=True):
                st.json(result)


# ─────────────────────────────────────────────────────────────────────────────
# FLUJO B — Inbox
# ─────────────────────────────────────────────────────────────────────────────

with tab_inbox:
    st.markdown(
        f"Procesa los PDFs sueltos que tengas en `{INBOX_DIR}`. "
        "**Fase 1** clasifica sin mover — revisa y corrige si es necesario. "
        "**Fase 2** aplica los movimientos y lanza la cadena de procesado."
    )

    n_inbox = sum(1 for _ in INBOX_DIR.rglob("*.pdf")) if INBOX_DIR.exists() else 0
    st.metric("PDFs actualmente en inbox/", n_inbox)

    st.divider()
    st.markdown("##### Acciones rápidas")
    col_rename, col_spacer = st.columns([2, 2])
    with col_rename:
        if st.button(
            "📝 Solo renombrar PDFs (sin clasificar ni procesar)",
            help="Ejecuta 1_rename_papers_by_doi.py sobre los PDFs del inbox",
            disabled=(n_inbox == 0),
            key="btn_rename_only",
        ):
            from pipeline import run_step

            _folder = st.session_state.get("inbox_custom_folder") or str(INBOX_DIR)
            _rename_result = execute_with_live_output(
                lambda on_output: run_step(
                    "1_rename_papers_by_doi.py",
                    ["--folder", _folder, "--apply"],
                    on_output=on_output,
                    label="rename_only",
                ),
                "Renombrado",
            )
            if _rename_result and _rename_result.get("returncode") == 0:
                st.success("✓ Renombrado completado. Los PDFs siguen en inbox/.")

    st.divider()

    # ── Opciones ──────────────────────────────────────────────────────────
    with st.expander("Opciones", expanded=not st.session_state.get("inbox_screen_done")):
        custom_folder = st.text_input(
            "Carpeta de origen (opcional)",
            value="",
            placeholder=str(INBOX_DIR),
            help="Por defecto se usa /Volumes/research/inbox.",
            key="inbox_custom_folder",
        )
        do_rename = st.checkbox(
            "Renombrar por DOI antes del cribado (1_rename_papers_by_doi.py)",
            value=True,
            key="inbox_do_rename",
        )

    # ── Fase 1 — Cribar ───────────────────────────────────────────────────
    col_a, col_b = st.columns([3, 1])
    with col_a:
        btn_cribar = st.button(
            "🔍 Fase 1 — Cribar",
            type="primary",
            disabled=(n_inbox == 0 and not custom_folder),
            key="btn_cribar",
        )
    with col_b:
        if st.button("↺ Reiniciar", key="btn_reset_inbox"):
            for _k in ("inbox_screen_done", "inbox_csv_path", "inbox_rows"):
                st.session_state.pop(_k, None)
            st.rerun()

    if btn_cribar:
        _folders = [custom_folder] if custom_folder else None
        _screen = execute_with_live_output(
            run_inbox_screen, "Cribado",
            folders=_folders,
            rename=do_rename,
        )
        if _screen and _screen.get("status") == "ok":
            st.session_state["inbox_screen_done"] = True
            st.session_state["inbox_csv_path"] = _screen["csv_path"]
            st.session_state["inbox_rows"] = _screen["rows"]
        else:
            st.session_state.pop("inbox_screen_done", None)

    # ── Tabla editable (solo visible tras Fase 1 exitosa) ─────────────────
    if st.session_state.get("inbox_screen_done"):
        import csv as _csv
        import pandas as pd

        _rows = st.session_state["inbox_rows"]
        if not _rows:
            st.info("No se encontraron PDFs en el inbox.")
        else:
            st.markdown("**Revisa y corrige la clasificación antes de procesar:**")

            _display_cols = [
                "ruta_original", "titulo_detectado",
                "clasificacion", "confianza", "metodo", "duplicado_de", "estado",
            ]
            _df = pd.DataFrame(_rows)[_display_cols].copy()
            _df["ruta_original"] = _df["ruta_original"].apply(lambda p: Path(p).name)

            _valid_cats = sorted(set(CANONICAL_CATEGORIES) | {"irrelevante"})
            _edited = st.data_editor(
                _df,
                column_config={
                    "ruta_original":    st.column_config.TextColumn("Archivo",      disabled=True),
                    "titulo_detectado": st.column_config.TextColumn("Título",       disabled=False),
                    "clasificacion":    st.column_config.SelectboxColumn(
                        "Clasificación", options=_valid_cats, required=True,
                    ),
                    "confianza":        st.column_config.TextColumn("Conf.",        disabled=True),
                    "metodo":           st.column_config.TextColumn("Método",       disabled=True),
                    "duplicado_de":     st.column_config.TextColumn("Duplicado de", disabled=True),
                    "estado":           st.column_config.TextColumn("Estado",       disabled=True),
                },
                hide_index=True,
                use_container_width=True,
                key="inbox_edited_df",
            )

            _n_dup = int((_df["estado"] == "DUPLICADO").sum())
            if _n_dup:
                st.warning(
                    f"⚠️ {_n_dup} PDF(s) detectado(s) como **DUPLICADO** — "
                    "se moverán a `/Volumes/research/duplicados/`."
                )

            # ── Fase 2 — Confirmar y procesar ────────────────────────────
            st.divider()
            if st.button("✅ Fase 2 — Confirmar y procesar", type="primary", key="btn_procesar"):
                _csv_path = st.session_state["inbox_csv_path"]
                _orig_rows = st.session_state["inbox_rows"]
                _new_cls_list = _edited["clasificacion"].tolist()
                _new_title_list = _edited["titulo_detectado"].tolist()

                _updated = [
                    {
                        **orig,
                        "clasificacion": new_cls,
                        "titulo_detectado": (new_title or orig["titulo_detectado"]),
                    }
                    for orig, new_cls, new_title in zip(_orig_rows, _new_cls_list, _new_title_list)
                ]
                _fieldnames = [
                    "ruta_original", "doi", "titulo_detectado", "abstract_detectado",
                    "clasificacion", "confianza", "metodo", "duplicado_de", "estado",
                ]
                with open(_csv_path, "w", newline="", encoding="utf-8") as _f:
                    _w = _csv.DictWriter(_f, fieldnames=_fieldnames)
                    _w.writeheader()
                    _w.writerows(_updated)

                _proc = execute_with_live_output(
                    run_inbox_process, "Procesado",
                    csv_path=_csv_path,
                )
                if _proc:
                    with st.expander("📊 Resumen detallado", expanded=True):
                        st.json(_proc)


# ─────────────────────────────────────────────────────────────────────────────
# FLUJO C — Pendientes
# ─────────────────────────────────────────────────────────────────────────────

with tab_pending:
    st.markdown(
        "Reanuda categorías cuya cadena de procesado quedó incompleta. "
        "La tabla compara `md_clean` con resúmenes, chunks y metadata; "
        "esto detecta cortes posteriores al primer procesado del PDF."
    )

    existing_categories = list_existing_categories()
    resume_rows = [
        category_resume_row(cat)
        for cat in existing_categories
        if get_category_stats(cat).get("pdfs", 0) > 0
    ]
    categories_to_resume = [
        row["Categoría"]
        for row in resume_rows
        if row["_needs_resume"]
    ]

    if resume_rows:
        import pandas as pd

        resume_df = pd.DataFrame(resume_rows)
        st.dataframe(
            resume_df.drop(columns=["_needs_resume"]),
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

        st.metric("Categorías incompletas", len(categories_to_resume))
        if not categories_to_resume:
            st.success("No hay brechas de procesado por paper.")
    else:
        st.info("No hay categorías con PDFs en el NAS.")

    st.divider()
    st.markdown("##### 📝 Renombrar PDFs por DOI")
    st.caption(
        "Ejecuta `1_rename_papers_by_doi.py` sobre los PDFs de las categorías "
        "seleccionadas. Los PDFs sin DOI quedan sin renombrar y se registran en "
        "`doi_manual.xlsx`. Haz esto antes de reprocesar si acabas de copiar PDFs "
        "con nombres sucios."
    )

    with st.form("rename_pending_form"):
        selected_rename = st.multiselect(
            "Categorías a renombrar",
            options=existing_categories,
            default=[],
        )
        submit_rename = st.form_submit_button("📝 Renombrar PDFs")

    if submit_rename:
        if not selected_rename:
            st.warning("Selecciona al menos una categoría.")
        else:
            from pipeline import run_step

            rename_errors = []
            for cat in selected_rename:
                _folder = str(CATEGORIAS_DIR / cat / "pdfs")
                res = execute_with_live_output(
                    lambda on_output, _folder=_folder: run_step(
                        "1_rename_papers_by_doi.py",
                        ["--folder", _folder, "--apply"],
                        on_output=on_output,
                        label=f"rename [{cat}]",
                    ),
                    f"rename [{cat}]",
                )
                if res is None or res.get("returncode", 1) != 0:
                    rename_errors.append(cat)

            if rename_errors:
                st.warning(
                    f"Algunas categorías terminaron con errores: {', '.join(rename_errors)}. "
                    "Revisa el log superior."
                )
            else:
                st.success(
                    "✓ Renombrado completado. Comprueba `doi_manual.xlsx` para los PDFs sin DOI. "
                    "Ya puedes pulsar **Reprocesar pendientes**."
                )

    st.divider()

    if not existing_categories:
        st.info("No hay categorías disponibles en el NAS.")
    else:
        with st.form("pending_form"):
            selected_pending = st.multiselect(
                "Categorías a reprocesar",
                options=existing_categories,
                default=categories_to_resume,
                help=(
                    "Por defecto se seleccionan las categorías incompletas. "
                    "También puedes elegir manualmente una categoría completa para regenerar pasos posteriores."
                ),
            )
            submit_pending = st.form_submit_button(
                "▶ Reprocesar pendientes",
                type="primary",
                use_container_width=True,
            )

        if submit_pending:
            if not selected_pending:
                st.warning("Selecciona al menos una categoría.")
            else:
                st.info(
                    f"Reprocesando {len(selected_pending)} categoría(s): "
                    + ", ".join(selected_pending)
                )
                result = execute_with_live_output(
                    run_pending_categories,
                    "Pendientes",
                    categories=selected_pending,
                )
                if result:
                    with st.expander("📊 Resumen detallado", expanded=True):
                        st.json(result)
                    if result.get("status") == "ok":
                        st.success("Pendientes reprocesados correctamente.")
                    elif result.get("status") == "partial":
                        st.warning("Algunas categorías terminaron con errores. Revisa el log superior.")


# ─────────────────────────────────────────────────────────────────────────────
# FLUJO D — Ad-hoc
# ─────────────────────────────────────────────────────────────────────────────

with tab_adhoc:
    st.markdown(
        "Crea un proyecto temporal a partir de una carpeta de PDFs sueltos. "
        "Copia los PDFs a `categorias/<nombre>/pdfs/` y procesa la cadena "
        "completa. No hace cribado ni renombrado: asume que ya están como tú quieres."
    )

    default_name = f"adhoc_{datetime.now().strftime('%Y%m%d_%H%M')}"

    with st.form("adhoc_form"):
        name = st.text_input(
            "Nombre del proyecto",
            value=default_name,
            help="Se creará en categorias/<nombre>/. Usa snake_case sin espacios.",
        )
        pdfs_path = st.text_input(
            "Ruta a la carpeta con los PDFs",
            value="",
            placeholder="/Users/martinramirez/Desktop/papers_revision",
            help="Ruta absoluta. Los PDFs se copian (no se mueven).",
        )

        # Vista previa de PDFs en la ruta
        if pdfs_path:
            p = Path(pdfs_path).expanduser()
            if p.exists() and p.is_dir():
                pdfs_found = list(p.glob("*.pdf"))
                st.caption(f"✓ Carpeta encontrada — {len(pdfs_found)} PDFs detectados")
            else:
                st.caption("⚠️ La carpeta no existe")

        submit_adhoc = st.form_submit_button(
            "▶ Ejecutar flujo Ad-hoc", type="primary", use_container_width=True,
        )

    if submit_adhoc:
        if not name.strip():
            st.error("Falta el nombre del proyecto.")
        elif not pdfs_path.strip():
            st.error("Falta la ruta a la carpeta de PDFs.")
        else:
            result = execute_with_live_output(
                run_adhoc, "Ad-hoc",
                name=name.strip(),
                pdf_dir=str(Path(pdfs_path).expanduser()),
            )
            if result:
                with st.expander("📊 Resumen detallado", expanded=True):
                    st.json(result)
                if result.get("status") == "ok":
                    st.success(
                        f"Proyecto **{result['project']}** listo. "
                        f"Ve a 🔍 RAG para hacer consultas."
                    )

    # ── Integrar / Promover ad-hoc ────────────────────────────────────────

    st.divider()
    st.subheader("🔗 Integrar proyecto ad-hoc")

    _all_cats   = list_existing_categories()
    _adhoc_opts = [c for c in _all_cats if c not in CANONICAL_CATEGORIES]

    if not _adhoc_opts:
        st.info("No hay proyectos ad-hoc disponibles en el NAS.")
    else:
        _adhoc_src = st.selectbox(
            "Proyecto ad-hoc origen",
            options=_adhoc_opts,
            key="integrate_adhoc_src",
        )

        _destino = st.radio(
            "Destino",
            ["Categoría existente", "Nueva categoría"],
            horizontal=True,
            key="integrate_destino",
        )

        if _destino == "Categoría existente":
            st.markdown(
                "Copia los artefactos del proyecto ad-hoc a una categoría canónica "
                "y re-indexa FAISS. Los ficheros ya existentes en el destino se saltan."
            )
            _adhoc_dst = st.selectbox(
                "Categoría destino",
                options=CANONICAL_CATEGORIES,
                key="integrate_adhoc_dst",
            )
            _delete_src = st.checkbox(
                "Borrar proyecto ad-hoc tras la integración",
                value=False,
                key="integrate_adhoc_delete",
            )

            if st.button("▶ Integrar", type="primary", key="btn_integrate_adhoc"):
                _int_result = execute_with_live_output(
                    integrate_adhoc, "Integrar ad-hoc",
                    adhoc_name=_adhoc_src,
                    target_category=_adhoc_dst,
                    delete_source=_delete_src,
                )
                if _int_result:
                    with st.expander("📊 Resumen detallado", expanded=True):
                        st.json(_int_result)
                    if _int_result.get("status") == "ok":
                        st.success(
                            f"**{_adhoc_src}** integrado en **{_adhoc_dst}** — "
                            f"{_int_result['copied_pdfs']} PDFs nuevos, "
                            f"{_int_result['skipped_pdfs']} ya existían."
                        )
                    else:
                        st.error(
                            f"Error en la integración: {_int_result.get('message', 'ver log')}"
                        )

        else:  # Nueva categoría
            st.markdown(
                "Crea una **nueva categoría canónica** a partir del proyecto ad-hoc. "
                "Se copian todos los artefactos (incluidos los índices FAISS) y se "
                "registran las keywords en `config/keywords.yml`."
            )
            _new_name = st.text_input(
                "Nombre de la nueva categoría",
                value="",
                placeholder="p.ej. anaerobic_digestion_sludge",
                help="Solo letras minúsculas, dígitos y '_'. No debe existir ya.",
                key="promote_new_name",
            )
            _new_keywords_raw = st.text_area(
                "Keywords (una por línea)",
                value="",
                height=140,
                placeholder="anaerobic digestion\nbiogas\nsludge treatment",
                key="promote_keywords",
            )
            _delete_src_promote = st.checkbox(
                "Borrar proyecto ad-hoc tras la promoción",
                value=False,
                key="promote_delete_src",
            )

            if st.button("▶ Promover a nueva categoría", type="primary", key="btn_promote_adhoc"):
                _new_kws = [k.strip() for k in _new_keywords_raw.splitlines() if k.strip()]
                if not _new_name.strip():
                    st.error("Indica el nombre de la nueva categoría.")
                else:
                    _promo_result = execute_with_live_output(
                        promote_adhoc_to_category, "Promover ad-hoc",
                        adhoc_name=_adhoc_src,
                        new_name=_new_name.strip(),
                        keywords=_new_kws,
                        delete_source=_delete_src_promote,
                    )
                    if _promo_result:
                        with st.expander("📊 Resumen detallado", expanded=True):
                            st.json(_promo_result)
                        if _promo_result.get("status") == "ok":
                            st.success(
                                f"Nueva categoría **{_promo_result['new_category']}** creada "
                                f"con {_promo_result['copied_pdfs']} PDFs y "
                                f"{_promo_result['keywords_added']} keywords."
                            )
                        else:
                            st.error(
                                f"Error: {_promo_result.get('message', 'ver log')}"
                            )
