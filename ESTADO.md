# research_agent — Estado del proyecto

## Infraestructura

| Componente | Detalle |
|---|---|
| Mac mini M4 Pro (casa) | edición de código, acceso remoto — ya no ejecuta Streamlit ni pipeline |
| NAS (casa) | backup — /Volumes/research_bk |
| Mac mini Pro (UCA) (pciq22.uca.es) | máquina principal — scripts, Streamlit, datos, Ollama, GROBID |
| Scripts | `/Users/martinramirez/proyectos/research_agent/scripts/` |
| Config | `/Volumes/Disco/proyectos/research_agent/config/` |
| Venv | `~/venvs/rag_papers` (Python 3.13 via Homebrew /opt/homebrew/bin/python3.13) |
| GROBID | Docker (ARM64 nativo), imagen `grobid/grobid:0.9.0-crf`, compose en `~/grobid-compose.yml` |
| Ollama | `http://pciq22.uca.es:11434` |
| Streamlit | `http://<ip-pciq22>:8501` — servicio launchd 24/7 en pciq22 |
| GitHub | `https://github.com/maramu/research_agent` |

## Modelos Ollama disponibles

- `qwen3:14b` — resúmenes detallados
- `gemma3:4b` — cribado rápido de abstracts
- `qwen3:8b` — uso general (RAG: síntesis por defecto en la web)
- ~~`nomic-embed-text`~~ — embeddings FAISS (768 dims) — **retirado**, reemplazado por bge-m3
- `bge-m3` — embeddings FAISS (8192 ctx, 1024 dims, multilingüe) — **modelo de producción**

## Estructura NAS

```
/Volumes/research/
├── inbox/              ← PDFs nuevos sin procesar (flujo inbox)
├── inbox_csv/          ← CSVs de Scopus (manual o via 0_scopus_api.py)
├── fallidos/           ← PDFs no clasificables
├── metadatos/          ← CSVs globales, doi_manual.xlsx, cache
│   └── rag_usage/      ← registros de uso RAG (rag_usage_YYYY-MM.jsonl)
└── categorias/
    ├── biogas_upgrading_biomethanation/        ← validado pipeline completo
    ├── bioplastics_microplastics/
    ├── biological_gas_odor_treatment/
    ├── anoxic_biogas_biodesulfurization/       ← validado pipeline completo
    ├── microalgae/
    ├── single_cell_protein/
    ├── advanced_oxidation_processes/
    └── bioleaching_critical_materials/
        ├── pdfs/
        ├── md_clean/
        ├── summaries/
        ├── chunks/
        ├── embeddings/
        ├── metadata/
        ├── notebooklm_packages/
        ├── tei/
        └── logs/
```

## Estructura del proyecto

> **Documentación del proyecto:**
> - **ESTADO.md** (este fichero) — estado y arquitectura actuales del proyecto.
> - **Mejoras_pendientes.md** — backlog vivo + orden de prioridad.
> - **Mejoras_realizadas.md** — histórico de trabajo completado (append-only, lo más nuevo arriba).
> - **Mejoras_copia20260612.md** — copia congelada del backlog original (referencia histórica).

```
research_agent/
├── config/
│   ├── .env                          ← claves API, hosts (NO subir a git)
│   ├── .env.example                  ← plantilla de variables (sí subir a git)
│   ├── keywords.yml                  ← palabras clave para cribado (8 categorías)
│   ├── scopus_queries.yml            ← queries Scopus por categoría
│   └── active_categories.yml         ← lista de categorías activas (excluye inactivas de Scopus/RAG)
├── scripts/
│   ├── pipeline.py                   ← orquestador (módulo importable)
│   ├── run_pipeline.py               ← CLI del orquestador (scopus/inbox/adhoc)
│   ├── run_weekly_scopus.py          ← ingesta semanal autónoma + email resumen
│   ├── 0_scopus_api.py               ← búsqueda Scopus API
│   ├── 1_rename_papers_by_doi.py
│   ├── 2_screen_pdfs.py
│   ├── 3_process_corpus.py
│   ├── 3a_download_pdfs.py
│   ├── 3b_summarize.py
│   ├── 4_extract_metadata.py
│   ├── 5_build_embeddings.py
│   ├── 6_make_packages.py
│   ├── 7_make_master_index.py
│   ├── 8_query_rag.py
│   ├── utils/
│   │   ├── pdf_utils.py
│   │   ├── constants.py              ← Constantes compartidas (OLLAMA_MODEL_EMBED, CANONICAL_CATEGORIES,
│   │   │                               CANONICAL_SECTIONS, year_from_paper_id, MAX_EMBED_CHARS)
│   │   ├── retrieval.py              ← Funciones de recuperación: BM25 + RRF + filtros (item 33)
│   │   └── corpus_manifest.py        ← Genera/lee corpus_manifest.json por categoría
│   └── streamlit_app/                ← Interfaz web (Streamlit)
│       ├── app.py                    ← portada: health checks + tabla categorías
│       ├── app_utils.py              ← helpers compartidos (renombrado para no
│       │                               colisionar con scripts/utils/).
│       │                               Incluye check_password(), is_public_app()
│       ├── README.md                 ← instrucciones despliegue + launchd
│       └── pages/
│           ├── 1_Ingestar.py         ← scopus / inbox / adhoc con progreso live
│           ├── 2_RAG.py              ← retrieval FAISS + síntesis LLM opcional
│           ├── 3_Keywords.py         ← editor estructurado de keywords.yml
│           ├── 4_Scopus_queries.py   ← editor de scopus_queries.yml
│           ├── 5_DOI_manual.py       ← visor filtrable de doi_manual.xlsx
│           ├── 6_Mantenimiento.py    ← mantenimiento corpus (6 secciones)
│           ├── 7_Revision.py         ← revisión bibliográfica (5 prompts)
│           ├── 8_Exportar.py         ← exportar BibTeX/RIS/CSV por categoría
│           ├── 9_Actividad.py        ← actividad sistema (solo app privada)
│           ├── 10_Duplicados.py      ← revisión de duplicados + cuarentena reversible (privada)
│           └── 11_Articulos.py       ← catálogo bibliográfico filtrable; editor DOI/Año/Autores/Revista + borrado reversible (solo privada)
├── deployment/
│   ├── com.research_agent.streamlit.plist        ← LaunchAgent Streamlit privado (8501)
│   ├── com.research_agent.streamlit_public.plist ← LaunchAgent Streamlit público (8502)
│   └── com.research_agent.scopus_weekly.plist    ← LaunchAgent ingesta semanal (lunes 06:00)
├── logs/                             ← logs antiguos de scripts numerados
├── tests/                            ← suite pytest (item 39)
│   ├── conftest.py                   ← añade scripts/ a sys.path
│   ├── test_pdf_utils.py             ← DOI_REGEX, _clean_doi, slugify, strip_accents, normalize_stem
│   └── test_rename.py                ← shorten_title, sanitize_filename (importlib desde 1_rename)
├── pytest.ini
├── .gitignore
└── requirements.txt
```

## Scripts (orden de ejecución)

| Script | Función | Estado |
|---|---|---|
| `0_scopus_api.py` | Consulta Scopus Search API por categoría. Queries en `config/scopus_queries.yml` | ✅ |
| `1_rename_papers_by_doi.py` | Renombra PDFs via DOI + Crossref. Gestiona `doi_manual.xlsx`. **2026-06-09**: nueva fuente DOI `--doi-csv`. **2026-06-13 (item 44):** lookup robusto en `doi_manual`: además de clave exacta, indexa por `normalize_stem(stem)` y `normalize_title(título_extraído)`; normaliza DOI antes de llamar a Crossref (`normalize_doi` — barra final → no más 404 para `10.1002/bit.26092/`); handler HTTPError conserva el fichero si hay DOI válido (no mueve a fallidos). | ✅ |
- Eliminada `DOI_REGEX` duplicada y funciones `clean_doi`, `extract_doi_from_text`, `extract_doi_from_pdf` — ahora importa desde `utils.pdf_utils` (commit d1ea84d)
| `2_screen_pdfs.py` | Clasifica PDFs en 8 categorías via keywords + Ollama | ✅ |
| `3_process_corpus.py` | PDF → TEI (GROBID) → MD clean → chunks JSONL. **2026-06-10 (item 32)**: campo `section_canonical` en cada chunk con herencia jerárquica de heading — `split_by_headings()` devuelve nivel del heading; `build_chunk_records()` mantiene mapa ancestros `nivel→canonical` y sube niveles hasta encontrar una etiqueta que no sea "other". 7 etiquetas: `abstract \| introduction \| methods \| results \| discussion \| conclusion \| other`. Chunks de tabla: `section_canonical="table"`. El campo `section` (título hoja crudo) queda intacto. Commit b097744. **2026-06-11**: chunks capados a `MAX_EMBED_CHARS` vía `_split_to_max_chars` (texto y TABLAS, que antes se emitían enteras); `section_part` añadido a registros de tabla. | ✅ |
| `3a_download_pdfs.py` | Descarga PDFs desde CSV Scopus via Unpaywall + Elsevier API. **Bug fix 2026-06-09**: doi_registry check corregido (`_line.strip().split("\t")[0].lower()` — el fichero tiene formato `doi\tcategory/filename`; antes el split tab faltaba y nunca detectaba duplicados ya en corpus). | ✅ |
| `3b_summarize.py` | Genera resúmenes con qwen3:14b | ✅ |
| `4_extract_metadata.py` | Extrae metadatos de TEI XML (título, DOI, autores, refs). Añade `stable_id`, `processed_date`, `source_type`, `download_source`, `download_url`, `access_type`, `download_date`. Arg `--source-type`. Verificado en producción 2026-05-27. **2026-06-11**: extrae **revista** del TEI (`monogr/title[@level='j']` + fallback) al campo `journal`; **fallback de DOI** a `doi_manual.xlsx` cuando el TEI no lo trae (por nombre de archivo y título normalizado); **preserva** `doi`/`journal` previos no vacíos al reextraer (no los machaca con vacío del TEI, backup `.bak`); **salta TEI huérfanos** sin `md_clean` correspondiente (imprime la lista) para no generar papers fantasma. **2026-06-13**: preservación generalizada a `title`/`doi`/`journal`/`year`/`authors` (`PRESERVE_FIELDS`) para que las correcciones manuales desde el editor de Artículos sobrevivan a una re-extracción; un campo vacío/ausente previo fuerza refresco desde el TEI. **2026-06-13**: fallback de `journal` vía Crossref por DOI cuando ni el TEI ni el registro previo traen revista. | ✅ |
| `5_build_embeddings.py` | Genera índice FAISS con bge-m3 via Ollama. **Modo incremental por defecto**: solo embeddea papers nuevos (no en `indexed_papers.json`); `--force` para re-indexar todo desde cero. **2026-06-11**: escribe `year` en metadata.jsonl (denormalizado desde `papers_metadata.jsonl` + fallback regex); `embed_texts` con truncado reactivo ante exceso de contexto. | ✅ |
| `6_make_packages.py` | Crea paquetes NotebookLM (FULLTEXT, REFERENCES, INDEX) | ✅ |
| `7_make_master_index.py` | Genera MASTER_INDEX.md por categoría | ✅ |
| `8_query_rag.py` | Consultas RAG sobre índice FAISS (CLI). **2026-06-11**: nuevos flags `--sections`, `--year-start`/`--year-end`, `--hybrid`. | ✅ |
| `9_cleanup_duplicates.py` | Detecta y elimina PDFs duplicados por DOI. Detección avanzada por título normalizado (solo grupos donde todos los papers comparten DOI o carecen de él — grupos con ≥2 DOIs distintos se ignoran como artículos diferentes) y hash SHA-256 con informe `metadatos/duplicate_report.xlsx` (3 hojas: DOI/Titulo/Hash). **2026-06-09**: nueva función `apply_hash_cleanup()` — `--apply` ahora elimina también duplicados por hash PDF (no solo DOI); desempate por nombre limpio Crossref. **2026-06-11**: nueva función `quarantine_paper()` — cuarentena REVERSIBLE que mueve PDF + artefactos a `/Volumes/research/quarantine/duplicates/<ts>/` con `_manifest` y quita la línea del paper de `papers_metadata.jsonl` (backup `.bak`). Usada por la página Duplicados (`10_Duplicados.py`). Commit fb320a9. **2026-06-12 (item 42):** copy2→copy en `rewrite_metadata`. | ✅ |
| `utils/corpus_manifest.py` | Genera `corpus_manifest.json` por categoría: n_pdfs, n_chunks, quality_score, faiss_indexes, faiss_stale, keywords_hash, git_commit. CLI + API pública `read_manifest()` | ✅ |
| `utils/retrieval.py` (NUEVO, item 33, 2026-06-11) | Funciones de recuperación: `dense_rank`, `bm25_rank`, `rrf_fuse` (RRF_K=60), `passes_filters` (centraliza filtros items 32/34), `pool_size`, `build_bm25`, `tokenize`. BM25 al vuelo desde metadata.jsonl, alineado con FAISS por orden. | ✅ |
| `utils/constants.py` | Constantes compartidas. **2026-06-11**: añadidas `CANONICAL_SECTIONS`, `year_from_paper_id`, `MAX_EMBED_CHARS` (junto a `OLLAMA_MODEL_EMBED`, `CANONICAL_CATEGORIES`). | ✅ |
| `pipeline.py` | Orquestador: cinco flujos (`run_scopus`, `run_inbox`, `run_adhoc`, `integrate_adhoc`, `promote_adhoc_to_category`). Helpers: `_copy_files_skip_existing()`. `_CANONICAL_CATEGORIES` importado de `utils/constants.py`. Importable por Streamlit. **Fixes 2026-06-09**: (1) `run_scopus()` llama a `build_doi_registry_from_nas()` antes del bucle de categorías; (2) `run_scopus()` pasa `--doi-csv` al paso de renombrado; (3) `run_inbox_process()` añade paso de renombrado antes de `detect_affected_categories()`. **2026-06-12 (item 42):** copy2→copy en `_copy_files_skip_existing`; eliminado el fallback inline de `_CANONICAL_CATEGORIES`; regex de `promote_adhoc_to_category` alineado a `[a-z0-9_-]+`. **2026-06-13:** puerta de dedup por DOI — `screen_new_pdfs_against_corpus()` + `build_doi_registry_from_nas()` reescrito + `detect_affected_categories()` con `normalize_stem`. **2026-06-13 (poda metadata):** `_META_STEM_FIELDS`, `_META_STEM_SUFFIXES`, `_record_stem()` y `prune_orphan_metadata()` — detecta/elimina registros de `papers_metadata.jsonl` sin `md_clean` (papers fantasma); reversible con `.bak` + `_orphans_<ts>.jsonl` + `_orphans_per_paper_<ts>/`. | ✅ |
| `run_pipeline.py` | CLI del orquestador con subcomandos | ✅ |
| `streamlit_app/` | Interfaz web sobre el pipeline (ver sección dedicada) | ✅ |
| `utils/pdf_utils.py` | Funciones comunes (DOI, slugify, texto). **2026-06-13 (item 39):** `normalize_stem()`. **2026-06-13 (item 44):** `normalize_doi(doi)` — strip/prefijo/barra final; `_clean_doi` conservador: ya no recorta sufijos de 3+ letras salvo que sigan directamente a un dígito (`(?<=\d)[a-zA-Z]{3,}$`); el DOI `10.1000/xyz` y similares quedan intactos; `10.1023/B:HYDR.0000008620.87704.3b` soportado por `DOI_REGEX` y `_clean_doi`. | ✅ |
- `DOI_REGEX` ampliado para capturar `<`, `>` en DOIs Wiley/ACS SICI antiguos (commit 95c119f)
- `_clean_doi` ampliado con dos pasos: paso Wiley/ACS `(-[a-zA-Z])[a-zA-Z]{2,}$` para anclar sufijo legítimo + paso general `[a-zA-Z]{3,}$` para eliminar texto alfabético pegado al final del DOI (commit 2483494)
| `utils/download_registry.py` | Registro persistente de DOIs pendientes de descarga (pendientes_descarga.csv) | ✅ |
| `utils/export_refs.py` | BibTeX/RIS/CSV + ZIP papers (`build_papers_zip` con fallback año+autor: paper_id exacto → stable_id desde jsonl → glob prefijo 20 chars) | ✅ |
| `streamlit_app/pages/7_Revision.py` | Revisión bibliográfica: 5 prompts especializados, streaming 3 providers, ZIP+BibTeX papers usados, guardar nota NAS | ✅ |
| `streamlit_app/pages/8_Exportar.py` | Exportar bibliografía por categoría: filtros año/DOI/quality, BibTeX/RIS/CSV descargables | ✅ |
| `streamlit_app/app_public.py` (portada pública, puerto 8502) | `st.navigation` con 3 páginas: RAG + Revisión bibliográfica + **Artículos** (catálogo bibliográfico filtrable; en la app pública sin la gestión de DOIs, que es privada). Autenticación con `check_password("PUBLIC_APP_PASSWORD")`. Solo Ollama disponible (filtrado en `2_RAG.py` con `is_public_app()`). | ✅ |
| `run_weekly_scopus.py` | Ingesta Scopus semanal autónoma. Ejecuta `run_scopus(WEEKLY_CATEGORIES, recent_days=7)`, cuenta PDFs nuevos y chunks, lee `pendientes_descarga.csv` y envía email HTML resumen via Gmail STARTTLS. Timeout 45 min via `ThreadPoolExecutor` + `future.result(timeout=2700)`; estado `"timeout"` si se supera y el email se envía igualmente. Logging a fichero (`logs/run_weekly_scopus_YYYY-MM-DD.log`) + stdout. Fallback HTML a `/tmp/`. `--dry-run` imprime HTML sin ejecutar. Config SMTP desde `.env`. | ✅ |

## Tres flujos del pipeline

Cada uno accesible tanto por CLI (`run_pipeline.py`) como por la interfaz web
(página **📥 Ingestar**, tres tabs).

### Flujo A — Scopus (categorizado de origen)

No necesita cribado: la query de Scopus ya define la categoría.

```
0_scopus_api   → inbox_csv/scopus_<cat>_<fecha>.csv
3a_download    → categorias/<cat>/pdfs/  (--out-dir directo)
3_process      → tei/ + md_clean/ + chunks/
3b_summarize   → summaries/
4_extract      → metadata/
5_embeddings   → embeddings/
6_packages     → notebooklm_packages/
7_index        → MASTER_INDEX.md
```

```bash
python run_pipeline.py scopus --recent-days 7
python run_pipeline.py scopus --category microalgae --max 500 --year-start 2020
```

### Flujo B — Inbox (PDFs sueltos sin clasificar)

```
1_rename       → inbox/ (renombrados) + doi_manual.xlsx
2_screen       → categorias/<cat>/pdfs/ + fallidos/
3_process … 7_index  (solo categorías con PDFs nuevos)
```

```bash
python run_pipeline.py inbox
```

### Flujo C — Ad-hoc (proyecto temporal)

```
carpeta PDFs → categorias/<nombre>/pdfs/ (copia)
3_process … 7_index
8_query_rag → consultas RAG
```

```bash
python run_pipeline.py adhoc --name revision_metanol --pdfs ~/papers_metanol
python 8_query_rag.py --project revision_metanol "tu pregunta"
```

## Interfaz web (Streamlit)

Todos los flujos del pipeline son accesibles desde la web, además de
herramientas adicionales (RAG, editores de configuración, visor de DOIs).

| Página | Función |
|---|---|
| `app.py` (portada) | Health checks en 2 filas: NAS / Ollama (+ latencia) / GROBID (+ latencia) + espacio libre NAS / bge-m3 disponible / permisos escritura NAS. Tabla de categorías con conteos (PDFs, pendientes, MD, resúmenes, chunks, metadata, FAISS, paquetes). Filas de categorías inactivas en gris (`df.style.apply`). **Banner de backup** (solo app privada): aviso si `last_backup.json` no existe o la última copia tiene >15 días. |
| `1_Ingestar` | 4 tabs: **Scopus** / **Inbox** / **Pendientes** / **Ad-hoc**. Progreso en directo vía `on_output`. Pendientes: tabla de brechas por categoría con reprocesado selectivo. Ad-hoc: formulario + sección **🔗 Integrar ad-hoc en categoría** (selectbox origen/destino, checkbox borrar fuente, llama a `integrate_adhoc()`). Auto-recuperación de estado Inbox al inicio: si `cribado_pendiente.csv` existe en disco (p.ej. tras reinicio launchd), restaura `session_state` y muestra toast. Tab Pendientes: botón 📝 Renombrar PDFs por DOI por categoría (ejecuta `1_rename_papers_by_doi.py --folder categorias/<cat>/pdfs --apply`; PDFs sin DOI se registran en `doi_manual.xlsx`). Usar antes de Reprocesar cuando se copian PDFs con nombres sucios directamente a `pdfs/`. Botón 📝 Renombrar PDFs por DOI protegido: salta PDFs que ya tienen md_clean correspondiente, procesando solo PDFs realmente nuevos. |
| `2_RAG` | Búsqueda FAISS sobre cualquier proyecto+fase. Filtros por tipo y paper_id. Selector de provider (Ollama / Anthropic / OpenAI) y modelo. Toggle síntesis LLM con streaming. Pre-estimación de coste pre-query. Coste real post-query. Contador acumulado mensual en sidebar. Log completo de consultas en `metadatos/rag_queries/rag_queries_YYYY-MM.jsonl` (10 campos: pregunta, papers recuperados, respuesta, costes). Botón "💾 Guardar como nota" → `notas_rag/<proyecto>/YYYY-MM-DD_<proyecto>_<slug>.md`. Patrón flag+`st.rerun()` para persistencia entre reruns de Streamlit. Expander "📦 Exportar papers recuperados": ZIP en memoria con PDFs y/o md_clean de los papers recuperados (fallback año+autor para PDFs renombrados por Crossref). Botón guardar nota movido al bloque de síntesis (fix rerun). **2026-06-11**: multiselect de Secciones (item 34), filtro de año opt-in, toggle "Recuperación híbrida (denso+BM25)" OFF por defecto (`load_bm25` cacheado por mtime), etiqueta rrf/dist en resultados. |
| `3_Keywords` | Editor por textarea de `config/keywords.yml` (una keyword por línea, backup .bak automático) |
| `4_Scopus_queries` | Editor por categoría de `config/scopus_queries.yml` (multilínea, añadir/duplicar/borrar queries) |
| `5_DOI_manual` | Visor con filtros de `doi_manual.xlsx`, descarga CSV de vista filtrada. Filtros: búsqueda libre, status, **Solo sin DOI** (checkbox), **Fecha desde** (date_input). |
| `6_Mantenimiento` | 6 secciones expandibles: **Categorías activas** (multiselect sobre CANONICAL_CATEGORIES, guarda `active_categories.yml`) / **Backfill metadata** (detecta papers sin `stable_id`, re-ejecuta `4_extract_metadata.py` por categoría) / **Re-indexar FAISS** (multiselect categorías, todas por defecto, `--force bge-m3`) / **Limpieza de duplicados** (preview → apply condicional, con aviso de re-indexado) / **Reconstruir doi_registry** (llama a `build_doi_registry_from_nas()` directamente) / **Coherencia PDF/MD** (3 casos: PDF↔MD — detecta huérfanos y PDFs sin MD con corrección automática + reprocesado; MD↔PDF — MDs sin PDF; **Metadata↔MD** — detecta y elimina registros de `papers_metadata.jsonl` sin `md_clean` vía `prune_orphan_metadata()`, reversible con `.bak` + `_orphans_<ts>.jsonl`). |
| `7_Revision` | Revisión bibliográfica con 5 prompts especializados (estado del arte, tabla de artículos clave, lagunas, comparativa, introducción). RAG sobre categoría+fase, streaming en 3 providers. Descarga Markdown + guardar en NAS (`notas_rag/`). Patrón flag+`st.rerun()`. Expander "📦 Exportar papers usados": ZIP (PDF+MD) + BibTeX generado desde `papers_metadata.jsonl`. Fragmentos usados en expander colapsado. **2026-06-11**: toggle "Recuperación híbrida (denso+BM25)" OFF por defecto, multiselect de Secciones (item 34) y filtro de año opt-in. |
| `8_Exportar` | Exporta bibliografía de una categoría a BibTeX / RIS / CSV. Filtros: rango de años, solo-DOI, quality score mínimo. Vista previa de papers seleccionados + 3 botones de descarga. |
| `9_Actividad` | Solo app privada. 4 secciones: uso RAG mes actual (métricas + tabla modelos de pago), últimas 20 consultas RAG, corpus por método de ingesta (`source_type`), errores recientes en `research_agent/logs/`. |
| `10_Duplicados` | Solo app privada. Detección en vivo de duplicados por título normalizado y hash SHA-256 (vía `9_cleanup_duplicates.py` cargado con `importlib`, registrado en `sys.modules` antes de `exec_module` por la dataclass de Python 3.13). Cuarentena REVERSIBLE: mueve PDF + artefactos a `/Volumes/research/quarantine/duplicates/<ts>/` con `_manifest` y quita la línea de `papers_metadata.jsonl` (`.bak`). Guard de falsos positivos en grupos por título (≥2 PDFs o ≥2 DOIs distintos → "No es duplicado" por defecto + aviso). |
| `11_Articulos` | Privada + pública. Catálogo bibliográfico: resumen por categoría (`get_categories_summary`/`category_summary_row` en `app_utils.py`, columna "Metadata" cuenta líneas del `papers_metadata.jsonl`) + listado con filtros (texto título/DOI/autor, año, revista, radio Con/Sin DOI), DOI como `LinkColumn`, autores legibles y export CSV. **Editor (solo privada):** `st.data_editor` con todas las filas de la categoría — edita DOI, Año, Autores (sep. `;`, heurística último-token=apellido) y Revista; checkboxes `_sel` para marcar borrado. "Sugerir DOIs" llama a Crossref para los sin-DOI. "Guardar cambios" llama a `update_metadata_fields()` (escribe `papers_metadata.jsonl` + upsert `doi_manual.xlsx`, backup `.bak`). "Eliminar seleccionados" llama a `delete_papers()` (cuarentena reversible → `quarantine/deleted/<ts>/` + re-index FAISS vía `pipeline.run_step`). |
| `12_Backup` | Solo app privada. Backup manual del corpus (`categorias/` + `metadatos/`) a `research_bk` vía `rsync --size-only`. Detección de montaje SMB (`os.path.ismount`), fecha/antigüedad de la última copia (`last_backup.json`), botones "Ver qué cambiaría" (dry-run con conteo legible) y "Copiar ahora". |

Importa directamente `pipeline.py` (no subprocess separado). Watchdog instalado
para auto-recarga al editar ficheros.

## Despliegue

### Mac mini en modo servidor 24/7

```bash
sudo pmset -c sleep 0          # no se duerme nunca
sudo pmset -c disksleep 0      # discos no se duermen
sudo pmset -c displaysleep 0   # pantalla irrelevante
sudo pmset -c hibernatemode 0  # sin hibernación
sudo pmset -c womp 1           # wake on network
sudo pmset -c autorestart 1    # reinicio automático tras corte de luz
```

Consumo idle ≈ 5-10W.

### Streamlit como servicio launchd

| Aspecto | Valor |
|---|---|
**Instancia privada (puerto 8501 — `app.py`)**

| Aspecto | Valor |
|---|---|
| Plist en repo | `deployment/com.research_agent.streamlit.plist` |
| Instalado en | `~/Library/LaunchAgents/com.research_agent.streamlit.plist` |
| Etiqueta | `com.research_agent.streamlit` |
| Comando | `/Users/martinramirez/venvs/rag_papers/bin/python3 -m streamlit run app.py` |
| WorkingDirectory | `/Users/martinramirez/proyectos/research_agent/scripts/streamlit_app` |
| Logs | `~/Library/Logs/research_agent/streamlit.{log,err.log}` |
| KeepAlive | true (reinicia automáticamente si se cae) |
| RunAtLoad | true (arranca al login) |

**Instancia pública (puerto 8502 — `app_public.py`)**

| Aspecto | Valor |
|---|---|
| Plist en repo | `deployment/com.research_agent.streamlit_public.plist` |
| Instalado en | `~/Library/LaunchAgents/com.research_agent.streamlit_public.plist` |
| Etiqueta | `com.research_agent.streamlit_public` |
| Comando | `PUBLIC_APP=true /Users/martinramirez/venvs/rag_papers/bin/python3 -m streamlit run app_public.py --server.port 8502` |
| WorkingDirectory | `/Users/martinramirez/proyectos/research_agent/scripts/streamlit_app` |
| Logs | `~/Library/Logs/research_agent/streamlit_public.{log,err.log}` |
| KeepAlive | true |
| RunAtLoad | true |

**Ingesta Scopus semanal (`run_weekly_scopus.py`)**

| Aspecto | Valor |
|---|---|
| Plist en repo | `deployment/com.research_agent.scopus_weekly.plist` |
| Instalado en | `~/Library/LaunchAgents/com.research_agent.scopus_weekly.plist` |
| Etiqueta | `com.research_agent.scopus_weekly` |
| Comando | `python3.13 run_weekly_scopus.py` (venv) |
| WorkingDirectory | `/Users/martinramirez/proyectos/research_agent/scripts` |
| Logs | `~/Library/Logs/research_agent/scopus_weekly.{log,err.log}` |
| Schedule | Lunes a las 06:00 (`StartCalendarInterval`) |
| RunAtLoad | false |
| KeepAlive | false |

Comandos día a día:

```bash
# Estado
launchctl list | grep streamlit

# Log en vivo
tail -f ~/Library/Logs/research_agent/streamlit.log

# Parar / arrancar / recargar
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit.plist

# Publico
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit_public.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit_public.plist

```

### Acceso

- Red UCA (local): `http://10.142.6.107:8501`
- Fuera (con VPN UCA activa): `http://10.142.6.107:8501`
- Mac mini de casa: acceso solo para edición de código vía git
- **NO** expuesto a internet (URL pública del router NO funciona — y bien que está)

## Configuración (config/.env)

```
OLLAMA_HOST=http://pciq22.uca.es:11434
OLLAMA_API_KEY=<clave>
GROBID_URL=http://pciq22.uca.es:8070
GROBID_TIMEOUT=600
UNPAYWALL_EMAIL=martin.ramirez@uca.es
ELSEVIER_API_KEY=<clave>
PRIVATE_APP_PASSWORD=<contraseña instancia privada>
PUBLIC_APP_PASSWORD=<contraseña instancia pública>
```

## Queries Scopus (config/scopus_queries.yml)

YAML con queries por categoría en sintaxis Scopus (`TITLE-ABS-KEY`, `AND`,
`OR`, `W/N`). Independientes de `keywords.yml` (que solo se usa para cribado
de PDFs sueltos en el flujo inbox).

Editor visual disponible en la página **📚 Scopus_queries** de la web.

## Categorías de investigación (config/keywords.yml)

1. `biological_gas_odor_treatment`
2. `anoxic_biogas_biodesulfurization` ← validado pipeline completo (Scopus → RAG)
3. `bioplastics_microplastics`
4. `biogas_upgrading_biomethanation` ← validado pipeline completo
5. `microalgae`
6. `single_cell_protein`
7. `advanced_oxidation_processes`
8. `bioleaching_critical_materials`

## Plan pendiente (por orden)

El backlog vivo y el orden de prioridad están en `Mejoras_pendientes.md`. El histórico de lo realizado, en `Mejoras_realizadas.md`. Este documento (ESTADO.md) describe el estado y la arquitectura actuales del proyecto.

## Notas importantes

- Ollama en `pciq22.uca.es` solo accesible desde red UCA o VPN. Las consultas RAG con Anthropic/OpenAI NO requieren VPN UCA (útil cuando la VPN cae)
- `mxbai-embed-large` NO es compatible con los chunks actuales (512 ctx vs ~1500 chars por chunk). Usar `bge-m3` (8192 ctx) como alternativa a nomic
- Los registros de coste RAG se guardan en `/Volumes/research/metadatos/rag_usage/rag_usage_YYYY-MM.jsonl`
- Descargas Elsevier requieren VPN activa (autenticación por IP institucional)
- GROBID puede necesitar warm-up tras inactividad (primera llamada lenta)
- El cribado (`2_screen`) usa keywords primero (rápido) y Ollama como fallback
- El cribado NO es necesario para el flujo Scopus (la query ya define la categoría)
- `doi_manual.xlsx` en `/Volumes/research/metadatos/` acumula todos los DOIs procesados
- Skip automático en todos los scripts: no reprocesa lo ya existente
- FAISS para embeddings (no ChromaDB), manteniendo scripts originales
- Argumentos inconsistentes entre scripts: `--phase` (3_process, 3b_summarize) vs `--project` (4–8). El orquestador absorbe la diferencia.
- `CANONICAL_CATEGORIES` y `OLLAMA_MODEL_EMBED` centralizadas en `utils/constants.py` — fuente de verdad única. `pipeline.py` importa `_CANONICAL_CATEGORIES` desde ahí con fallback inline (`except ImportError`); `app_utils.py` usa import fusionado. **Si se añade una categoría, solo actualizar `utils/constants.py`.**
- `stable_id` en metadata: slug del DOI si existe, `paper_id` original si no. Campo estable independiente del nombre de fichero (item 16). Papers procesados antes del item 16 carecen de este campo — rellenar con página **6_Mantenimiento** → sección Backfill metadata.
- Procedencia en metadata: `source_type` (scopus/inbox/adhoc/manual), `download_source`, `access_type`, `download_url`, `download_date`, `processed_date`. Leído automáticamente de `descarga_cache.json` por DOI; arg `--source-type` para forzarlo (item 14). Verificado en producción 2026-05-27.
- `_copy_files_skip_existing(src, dst)` en `pipeline.py`: copia recursiva con `rglob`, skip por existencia de fichero, preserva subdirectorios. Usada por `integrate_adhoc()` y `promote_adhoc_to_category()`.
- `run_adhoc()` en `pipeline.py`: valida el nombre del proyecto con `re.fullmatch(r'^[a-z0-9_-]+$', name)` antes de crear directorios. Lanza `ValueError` si el nombre contiene espacios, mayúsculas o caracteres no permitidos.
- `pendientes_descarga.csv` en `/Volumes/research/metadatos/`: registro persistente acumulado de DOIs fallidos entre lotes. Actualizado automáticamente por `3a_download_pdfs.py --category <cat>`. Helper en `utils/download_registry.py` (`upsert`, `mark_downloaded`, `load`). Prerequisito del item 28.
- `integrate_adhoc(adhoc, target, delete_source)` en `pipeline.py`: copia pdfs/, md_clean/, summaries/, chunks/, metadata/ de un proyecto ad-hoc a una categoría canónica existente y re-indexa FAISS del destino. Los ficheros ya existentes se saltan.
- `promote_adhoc_to_category(adhoc, new_name, keywords, delete_source)` en `pipeline.py`: crea una nueva categoría canónica desde un ad-hoc copiando también embeddings/ y registrando keywords en `config/keywords.yml`. Valida nombre (`^[a-z0-9_]+$`) y que la categoría no exista previamente.
- `quality_score` (0–1) y `warnings` añadidos a cada registro de `papers_metadata.jsonl` por `4_extract_metadata.py`. 7 criterios: título, DOI, abstract, año, autores, refs<5, md_clean corto. Papers procesados antes del item 17 no tienen el campo — rellenar con **Mantenimiento → Backfill metadata**. Panel "📊 Calidad del corpus" en portada Streamlit (expander, solo categorías con metadata existente).
- `active_categories.yml` en `config/`: lista YAML `active:` con las categorías habilitadas. Editado desde la web (Mantenimiento → Sección 1). Las inactivas se muestran en gris en portada y se excluyen de `run_scopus()`. Fallback a `CANONICAL_CATEGORIES` si el fichero no existe o está vacío.
- `corpus_manifest.json` en `categorias/<cat>/`: generado con `utils/corpus_manifest.py`; contiene métricas de estado del corpus (n_pdfs, n_chunks, quality_score, faiss_indexes, faiss_stale, keywords_hash, git_commit). Actualizar tras ingestas o re-indexados. `app_utils.get_corpus_manifest()` lo lee para la portada.
- `1_rename_papers_by_doi.py` genera nombres con solo guiones bajos desde 2026-05-28 (fix guiones/espacios en `shorten_title` y `sanitize_filename`). PDFs renombrados antes pueden tener guiones en el stem — usar **Mantenimiento → Coherencia PDF/MD** para detectar y corregir los artefactos con nombre viejo.
- ZIP export en RAG (`2_RAG.py`) y Revisión (`7_Revision.py`) usa `build_papers_zip` con fallback: paper_id exacto → stable_id desde `papers_metadata.jsonl` → glob por prefijo. Resuelve PDFs cuyo paper_id (nombre viejo) ya no coincide con el stem del PDF renombrado por Crossref.
- `section_canonical` en chunks JSONL (item 32, 2026-06-10): herencia jerárquica del heading más cercano que clasifique (abstract/introduction/methods/results/discussion/conclusion); subsecciones descriptivas sin patrón IMRaD heredan del padre. Chunks de tabla → `"table"`. El campo `section` (título hoja crudo) queda intacto. **No es retroactivo**: categorías procesadas antes del item 32 no tienen el campo — re-trocear con `--force` para poblarlo.
- `metadata.jsonl` por chunk incluye ahora `section_canonical` (item 32) y `year` (item 34, denormalizado desde `papers_metadata.jsonl` + fallback regex sobre paper_id).
- `utils/retrieval.py` centraliza la recuperación: BM25 al vuelo (sin artefacto, alineado con FAISS por orden), fusión RRF (k=60) y filtros (`passes_filters`). Toggle híbrido OFF por defecto en CLI (`--hybrid`) y web.
- `MAX_EMBED_CHARS=8000` (`utils/constants.py`): tope de chunk + truncado reactivo en el embed para no exceder el contexto de bge-m3 con texto denso en fórmulas/subíndices.
- `requirements.txt`: dependencias `rank-bm25` y `pytest>=8.0`.
- **Tests (item 39):** `tests/` con `pytest` (`conftest.py` añade `scripts/` a sys.path; `pytest.ini` en raíz). `normalize_stem` en `utils/pdf_utils.py` unifica el antiguo `_norm` de los 3 ficheros. Regresión de DOI/título/stem: 56 passed, 1 xfailed (xfail strict = bug `_clean_doi`, item 44). Hallazgos abiertos: items 44 (`_clean_doi` recorta sufijos DOI de 3+ letras) y 45 (utilidades de texto duplicadas y divergentes `pdf_utils`↔`1_rename`).
- **Rollout item 32 completado (2026-06-11):** las 8 categorías re-troceadas + re-indexadas (`3_process_corpus.py --force-md` + `5_build_embeddings.py --force`); `section_canonical` y `year` poblados en `metadata.jsonl` de todas. Ya no queda el "pendiente: re-trocear el resto".
- **Revista desde TEI:** `4_extract_metadata.py` extrae `journal` del `monogr/title[@level='j']` del TEI (con fallback). Filtro y columna de revista disponibles en la página Artículos. Se descartó en su día y ahora sí se incorpora.
- **`4_extract_metadata.py` salta TEI huérfanos:** solo emite metadata para TEI con `md_clean` correspondiente (comparación por stem normalizado `_norm`), evitando papers fantasma en `papers_metadata.jsonl` por restos de dedup/renombrados; imprime la lista de saltados. Además: fallback de DOI a `doi_manual.xlsx` y preservación de `title`/`doi`/`journal`/`year`/`authors` no vacíos al reextraer (las correcciones manuales del editor de Artículos sobreviven).
- **Cuarentena reversible de duplicados:** página Duplicados (`10_Duplicados.py`, privada) + `quarantine_paper()` en `9_cleanup_duplicates.py` mueven PDF + artefactos a `/Volumes/research/quarantine/duplicates/<ts>/` (con `_manifest`) y quitan la línea de `papers_metadata.jsonl` con `.bak` — operación deshacible, no borra ficheros.
- **Backup a research_bk (item 40, completado 2026-06-12):** manual (NAS de casa por VPN + montaje SMB; no automático). `/opt/homebrew/bin/rsync -rv --size-only --no-perms --no-owner --no-group` + excludes de dirs de sistema macOS, de `/Volumes/research/` a la RAÍZ de `/Volumes/research_bk/`. `--size-only` porque el SMB del Synology no conserva el mtime (comparar por tiempo re-copia en bucle). rsync clásico de Homebrew, NO el openrsync nativo. `#recycle` con auto-vaciado 15–30 días. No `--inplace`. UI: página `12_Backup.py` (privada) + banner de antigüedad en portada (>15 días). Verificado: dry-run convergente (0 ficheros); primera copia por botón OK.

### Streamlit / launchd — gotchas aprendidos durante el despliegue

- **No usar el shim `~/venvs/.../bin/streamlit`** desde launchd: macOS 15+ le pone `com.apple.provenance` y bloquea el spawn con `EX_CONFIG` (78). Solución: invocar el intérprete Python directamente con `-m streamlit`.
- **Logs NO en `/Volumes/Disco/` ni `/Volumes/research/`**: TCC bloquea a los launchd user agents la escritura en volúmenes externos. Los logs van a `~/Library/Logs/research_agent/`.
- **No usar emojis en nombres de fichero de `pages/`**: macOS los guarda en Unicode NFD y Streamlit no descubre las páginas en sidebar. Los iconos visuales se ponen con `st.set_page_config(page_icon="📥", ...)` dentro del fichero.
- **Módulo de helpers de la web se llama `app_utils.py`, NO `utils.py`**: hay colisión con el paquete `scripts/utils/` (que contiene `pdf_utils.py`) cuando `scripts/` está en `sys.path`. Python resuelve al paquete viejo en lugar de al módulo de la app.
- **Verificación de salud al cargar el plist**: tras `launchctl bootstrap`, comprobar con `launchctl list | grep streamlit` que sale PID + status `0`. Si sale `-  78`, mirar logs de launchd con:
  ```bash
  log show --predicate 'process == "launchd"' --last 5m --info 2>/dev/null \
      | grep -iE "research_agent|streamlit" | tail -20
  ```

### Decisión arquitectónica

Streamlit corre en el **Mac mini de casa** (no en el NAS ni en el Mac mini Pro
UCA) porque:
- Scripts y venv ya viven ahí
- El NAS está montado **localmente** → I/O rápida (la mayoría del trabajo es
  leer/escribir ficheros del NAS)
- Ollama/GROBID son llamadas HTTP cortas, perfectamente tolerables sobre VPN UCA
- Es la única máquina con acceso simultáneo y cómodo a ambos recursos
- GROBID corre en Docker ARM64 nativo (`grobid/grobid:0.9.0-crf`) en pciq22. Compose en `~/grobid-compose.yml`. Docker Desktop configurado para arrancar al login.
- Mac mini de casa ya no ejecuta Streamlit ni pipeline. Servicio launchd eliminado. Modo hibernación restaurado (pmset). Repo conservado en `/Volumes/Disco/proyectos/research_agent/` para edición.
- Datos migrados del NAS Synology (casa) al SSD Crucial X9 4TB montado en `/Volumes/research/` en pciq22. NAS pasa a backup.

### Ollama — instalación en pciq22

- **Método:** tarball oficial de GitHub (NO Homebrew, NO install.sh — ambos dan versiones corruptas en ARM64)
- **Binario:** `/usr/local/bin/ollama`
- **Libs:** `/usr/local/lib/ollama/` (llama-server, llama-quantize, libggml-*.dylib)
- **Modelos:** `~/.ollama/models/`
- **Servicio:** LaunchAgent `~/Library/LaunchAgents/com.martin.ollama.plist` (`OLLAMA_HOST=0.0.0.0:11434`)
- **Logs:** `~/ollama.launchd.log` / `~/ollama.launchd.err`

**Para actualizar:**
1. Descargar `https://github.com/ollama/ollama/releases/download/vX.Y.Z/ollama-darwin.tgz`
2. `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.martin.ollama.plist`
3. Extraer y copiar binarios a `/usr/local/bin/` y `/usr/local/lib/ollama/`
4. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.martin.ollama.plist`

⚠️ Los modelos en `~/.ollama/models/` no se tocan al actualizar.
⚠️ Evitar abrir Ollama.app — interfiere con el servicio headless.
