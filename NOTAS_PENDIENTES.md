# Notas pendientes — research_agent

---

## Verificaciones completadas

### ✅ Item 34 — Filtrado por sección y año en la query (2026-06-11)
- utils/constants.py: CANONICAL_SECTIONS (abstract, introduction, methods, results,
  discussion, conclusion, table, other) y year_from_paper_id() como fuente única.
- 8_query_rag.py: --sections (filtra section_canonical), --year-start/--year-end
  (rango inclusivo). Año resuelto por m['year'] con fallback regex sobre paper_id.
- 5_build_embeddings.py: denormaliza `year` en cada registro de metadata.jsonl
  (_load_pid2year desde papers_metadata.jsonl con lookup tolerante de campo +
  fallback year_from_paper_id).
- 2_RAG.py / 7_Revision.py: multiselect de secciones + filtro de año opt-in (checkbox + slider).
- Revista: descartada explícitamente.
- Verificado en anoxic: --sections methods,results excluye introduction/abstract/other;
  --year-start 2020 deja fuera el review de 2008. El año funciona ya por fallback regex
  y pasa a autoritativo (TEI) tras re-indexar.

---

### ✅ Item 33 (v1) — Recuperación híbrida denso + BM25 con RRF (2026-06-11)
- requirements.txt: rank-bm25.
- scripts/utils/retrieval.py (NUEVO): tokenize, build_bm25, dense_rank, bm25_rank,
  rrf_fuse (RRF_K=60), passes_filters (centraliza filtros items 32/34), pool_size.
- BM25 al vuelo desde metadata.jsonl (sin artefacto, sin re-index; orden alineado con
  vectores FAISS). Cacheado por mtime en Streamlit (load_bm25); one-shot en CLI.
- 8_query_rag.py: --hybrid. 2_RAG.py / 7_Revision.py: toggle "Recuperación híbrida"
  OFF por defecto; etiqueta rrf/dist en resultados.
- Verificado A/B con query de siglas (NR-SOB): el híbrido sube matches léxicos y papers
  de comunidad microbiana que el denso no traía en top-8.
- Reranking: PENDIENTE (fase 2), ligado al item 37 — sin set de evaluación no se puede
  medir, y el soporte de rerank en Ollama es dudoso.

---

### ✅ Fix robustez de chunking — tope de tamaño + truncado reactivo (2026-06-11)
- Problema: chunks que exceden el contexto de bge-m3 (8192 tokens). Dos fugas: (1) las
  tablas se emitían enteras sin trocear en build_chunk_records; (2) el tope por palabras
  no controla tokens — el texto de GROBID con fórmulas/subíndices espaciados (H 2 S,
  S-SO 4 2-) puede superar 1 token/char, así que <8000 chars ya revientan el contexto.
- utils/constants.py: MAX_EMBED_CHARS = 8000.
- 3_process_corpus.py: helper _split_to_max_chars aplicado al texto (renumerando
  section_part) y a las tablas (antes iban enteras); section_part añadido a registros
  de tabla.
- 5_build_embeddings.py: embed_texts con truncado REACTIVO — captura el error de contexto
  y trunca 2/3 hasta que entra (el truncado fijo por chars no bastaba). El campo `text`
  de metadata queda completo; solo el vector usa el texto truncado.
- Verificado: microalgae embebía con un chunk truncado a 3635 chars (~2,25 tokens/char) y completó.

---

### ✅ Item 32 — rollout completado (2026-06-11)
- Re-troceadas + re-indexadas las 8 categorías con 3_process_corpus.py --force-md
  (re-chunk desde TEI existente, sin GROBID) + 5_build_embeddings.py --force --model bge-m3.
- section_canonical y year poblados en metadata.jsonl de todas las categorías; tablas
  capadas; FAISS reconstruido. Cierra el "pendiente: re-trocear el resto" del item 32 (2026-06-10).

---

### ✅ Pipeline ingesta Scopus — fixes robustez (2026-06-09)

Serie de fixes críticos detectados durante la ingesta manual tras corte de luz:

**Bug doi_registry check (`3a_download_pdfs.py` línea 1509):**
- `_line.strip().lower()` → `_line.strip().split("\t")[0].lower()`
- El fichero `doi_registry.txt` tiene formato `doi\tcategory/filename`. Sin el split
  se añadía la línea completa al set y la comparación `doi.lower() in known_corpus_dois`
  siempre fallaba → descargaba todos los artículos en cada ingesta sin detectar duplicados.

**Actualizar doi_registry antes de descargar (`pipeline.py` — `run_scopus()`):**
- Añadido `build_doi_registry_from_nas()` justo antes del bucle `for cat in target_cats:`
- Equivalente a lo que ya hacía `run_inbox_screen()`. Garantiza que el registro refleja
  el estado real del NAS antes de cada descarga.

**Renombrado automático por DOI en `run_scopus()` (`pipeline.py`):**
- Insertado paso `1_rename_papers_by_doi.py --apply` después de descargar y antes
  de `process_category()`. Si falla, warning y continúa.

**Renombrado automático por DOI en `run_inbox_process()` (`pipeline.py`):**
- Mismo fix: renombrado antes de `detect_affected_categories()`.

**Eliminación automática de duplicados por hash en `9_cleanup_duplicates.py`:**
- Nueva función `apply_hash_cleanup()`: ordena por prioridad nombre limpio, elimina
  PDF + artefactos de los secundarios. `main()` con `--apply` ahora procesa también
  hash_dups además de DOI dups.

**DOI desde CSV de Scopus en `1_rename_papers_by_doi.py`:**
- Nueva fuente de DOI: prioridad 2 entre doi_manual y extract_doi_from_pdf.
- `load_doi_from_csv(csv_path)` → `{título_normalizado: doi}` usando normalize_title
  de 9_cleanup_duplicates.py (importado por importlib).
- `_extract_title_from_filename(stem)` extrae el título del nombre largo de Scopus.
- `--doi-csv PATH` nuevo argumento CLI.
- `pipeline.py run_scopus()` pasa `--doi-csv str(csv_path)` al renombrado.
- Fallback completo si no se pasa `--doi-csv` o el CSV no es legible.

**Resultado verificado:** prueba controlada con `--max 20` mostró `Ya en corpus: N`
alto, `Descargados: N` solo artículos realmente nuevos, 0 duplicados, 0 huérfanos.

---

### ✅ Renombrado automático por DOI en pipeline (completado 2026-06-09)

Fix implementado en `pipeline.py`:
- `run_scopus()` (línea ~495): renombra PDFs por DOI **después de descargar, antes de procesar**
- `run_inbox_process()` (línea ~615): renombra PDFs en inbox **después de screen [apply], antes de detectar categorías**

Si el renombrado falla (DOI no en Crossref), se emite warning pero el pipeline continúa con los nombres originales.

Resultado: **Cero artefactos huérfanos** en futuras ejecuciones de `run_scopus()` e `run_inbox()`.

---

### ✅ Fix guards autenticación páginas privadas (2026-06-05)

Añadido guard de autenticación en las 6 páginas que carecían de él:
`1_Ingestar.py`, `3_Keywords.py`, `4_Scopus_queries.py`, `5_DOI_manual.py`,
`6_Mantenimiento.py`, `8_Exportar.py`.

Patrón insertado justo después de cada `st.set_page_config()`:
```python
from app_utils import check_password, is_public_app
if is_public_app():
    st.stop()
if not check_password("PRIVATE_APP_PASSWORD"):
    st.stop()
```

Contexto: `2_RAG.py` y `7_Revision.py` ya tenían guard propio (usan `is_public_app()`
para elegir entre `PUBLIC_APP_PASSWORD` y `PRIVATE_APP_PASSWORD`). `9_Actividad.py`
solo hace `is_public_app()` → `st.stop()` (exclusiva de la app privada, sin prompt
de contraseña).

---

### ✅ FAISS incremental + filtros DOI manual (2026-06-04)

**`scripts/5_build_embeddings.py`** — indexado incremental por defecto:
- Nuevo fichero `indexed_papers.json` junto al índice FAISS: lista de `paper_ids` ya indexados + modelo.
- Sin `--force`: si el índice existe, solo embeddea chunks de papers nuevos (`paper_id` no en `indexed_papers.json`). Carga el índice con `faiss.read_index()`, añade con `index.add()`, hace append en `metadata.jsonl` y actualiza `config.json` + `indexed_papers.json`.
- Si no hay papers nuevos → imprime "Índice actualizado, nada nuevo" y sale.
- Si el modelo del índice existente no coincide con `--model` → avisa y sale (usar `--force`).
- Con `--force` → comportamiento original (re-indexar todo).
- `config.json` refleja ahora `index.ntotal` (total acumulado) en lugar de solo el lote actual.

**`scripts/streamlit_app/pages/5_DOI_manual.py`** — dos filtros nuevos en el expander 🔍 Filtros:
- **Solo sin DOI** (checkbox): muestra solo filas con columna `doi` vacía o NaN.
- **Fecha desde** (date_input): filtra por columna de fecha de creación; detecta automáticamente columnas `fecha`, `fecha_creacion`, `fecha_registro`, `created_at`, `date` o dtype datetime. Si la columna no existe, el filtro se ignora silenciosamente.
- Ambos filtros se aplican en cascada con los existentes (status + búsqueda libre).

---

### ✅ Fix flujo PDFs manuales + protección renombrado (2026-06-04)

Problema detectado: al copiar PDFs manuales directamente a `categorias/<cat>/pdfs/` 
y luego usar "Renombrar por DOI", el script renombraba también PDFs ya procesados 
generando artefactos huérfanos y duplicados.

Fixes aplicados:
- `1_Ingestar.py` — botón "Renombrar por DOI" en tab Pendientes ahora compara 
  stems de PDFs contra md_clean con `_norm` (NFKC + `[\s\.\-,]+→_` + colapso) 
  y salta PDFs que ya tienen md_clean. Muestra cuántos se saltan y cuántos se procesan.

Flujo correcto para PDFs manuales cuando se conoce la categoría:
1. Copiar PDFs a `categorias/<cat>/pdfs/`
2. Pendientes → Renombrar por DOI en esa categoría (solo toca PDFs sin md_clean)
3. Pendientes → Reprocesar esa categoría

⚠️ NUNCA usar "Renombrar por DOI" en una categoría que mezcle PDFs ya procesados 
con PDFs nuevos sin haber comprobado primero qué tiene md_clean. El fix lo protege 
automáticamente pero conviene entender el flujo.

---

### ✅ Fix normalización coherencia PDF/MD (2026-06-04)

Sección 5 "Coherencia PDF/MD" de `6_Mantenimiento.py` — función `_norm` mejorada para evitar falsos positivos en la detección de huérfanos:

- Normalización Unicode NFKC: resuelve ligaduras tipográficas (`ﬁ` → `fi`)
- Regex ampliado `[\s\.\-,]+`: cubre puntos, comas y guiones además de espacios
- Colapso de guiones bajos múltiples con `re.sub(r"_+", "_", s)`
- `strip("_")` para eliminar guiones bajos al inicio/fin del stem

Casos que generaban falsos positivos resueltos:
- PDFs con nombres `10. 2012-06 A...` vs MDs `10_2012_06_A...` (puntos)
- PDFs con comas en el título (`Purification, Upgrading...`) vs MDs sin coma
- PDFs con guiones residuales (`fe_ii_-persulfate`) vs MDs normalizados
- Ligadura `ﬁ` en nombre de fichero generada por GROBID

Commit: `fix: normalización PDF/MD — puntos, comas, ligaduras unicode, colapso guiones bajos`

---

### ✅ Verificación de rutas hardcodeadas post-migración (2026-06-04)

Revisados todos los `.py` del proyecto buscando rutas de la máquina anterior `/Volumes/Disco/`:

**Ficheros corregidos:**
- `scripts/0_scopus_api.py:78` — `_LOGS_DIR` ahora usa `_SCRIPT_DIR.parent / "logs"`
- `scripts/3a_download_pdfs.py` — añadida constante `_LOGS_DIR = Path(__file__).parent.parent / "logs"` a nivel de módulo; eliminadas 4 ocurrencias de la ruta hardcodeada (`_NAS_SUBDIRS`, `Config.log_file`, `parse_args()`, `main()`)
- `ESTADO.md` — tabla infraestructura y ejemplo cron actualizados a `/Users/martinramirez/...`
- `NOTAS_PENDIENTES.md` — ejemplo cron actualizado

**No tocado (correcto):**
- Docstrings en `0_scopus_api.py:19` y `3a_download_pdfs.py:41,58` — no son rutas funcionales
- Todas las referencias a `pciq22.uca.es` son URLs de red (`OLLAMA_HOST`, `GROBID_URL`) — correctas
- `/Volumes/research/` en código — correcto en ambas máquinas

**Duda menor (no aplicada):**
- `streamlit_app/pages/1_Ingestar.py:599` — `placeholder="/Users/martinramirez/Desktop/papers_revision"` es texto de ayuda en un campo de entrada vacío. No es funcional, pero menciona un path del usuario. Cambiar a texto genérico si se comparte la app con otros.

---

### ✅ Migración a pciq22 + SSD Crucial X9 4TB (2026-06-03)

Pipeline completo migrado del Mac mini de casa a `pciq22.uca.es`:
- SSD Crucial X9 4TB formateado APFS, montado en `/Volumes/research/` — reemplaza NAS como almacenamiento principal
- Repo clonado en `/Users/martinramirez/proyectos/research_agent/`
- Venv rehecho con Python 3.13 (Homebrew)
- Streamlit como servicio launchd (plist en `deployment/`)
- GROBID migrado a imagen ARM64 nativa `grobid/grobid:0.9.0-crf` (antes `lfoppiano/grobid:0.8.1` amd64 con emulación)
- Todos los health checks verdes: NAS, Ollama, GROBID, bge-m3, escritura, 3999 GB libres
- Mac mini de casa: launchd eliminado, hibernación restaurada, repo conservado para edición
- NAS Synology casa: renombrado a `research_bk`, rol de backup

---

### ✅ Coherencia PDF/MD + fix nombres Crossref (2026-05-28)

`1_rename_papers_by_doi.py` — dos fixes en generación de nombres:
- `shorten_title`: elimina `\-` del regex → guiones se convierten en espacios y luego en `_` igual que el resto (`gas-liquid` → `gas_liquid`)
- `sanitize_filename`: nuevo `re.sub(r"\s+", "_")` antes del colapso de guiones bajos → espacios residuales nunca llegan al nombre final

`6_Mantenimiento.py` — nueva sección 5 "🔗 Coherencia PDF/MD":
- Detecta PDFs sin md_clean y md_clean huérfanos sin PDF
- Comparación normalizada (espacios/guiones → `_`, lowercase) para evitar falsos positivos por diferencias de puntuación
- Botón "Corregir": elimina artefactos huérfanos (md_clean, chunks, summaries, metadata per-paper) y relanza `3_process_corpus.py`

`utils/export_refs.py` — `build_papers_zip` con fallback año+apellido:
- Lookup: paper_id exacto → stable_id desde papers_metadata.jsonl → glob por prefijo (primeros 20 chars)
- Resuelve el caso de paper_ids viejos cuyos PDFs fueron renombrados por Crossref

---

### ✅ Refactorización constants + resiliencia inbox + limpieza debug prints (2026-05-28)

**`utils/constants.py`** — `CANONICAL_CATEGORIES` añadida como fuente de verdad única (junto con `OLLAMA_MODEL_EMBED`).

**`pipeline.py`** — bloque `_CANONICAL_CATEGORIES` hardcoded eliminado; importa desde `utils.constants` con fallback inline `except ImportError`.

**`app_utils.py`** — import fusionado: `from utils.constants import OLLAMA_MODEL_EMBED, CANONICAL_CATEGORIES`; línea suelta de `OLLAMA_MODEL_EMBED` y bloque literal de 10 líneas eliminados.

**`1_Ingestar.py`** — bloque de auto-recuperación de estado Inbox añadido antes de los tabs: si `cribado_pendiente.csv` existe en disco al reiniciar launchd, restaura `inbox_screen_done`, `inbox_csv_path` e `inbox_rows` en `session_state` y muestra `st.toast`.

**`1_rename_papers_by_doi.py`** — eliminados todos los `print("[DEBUG]...")` en `append_doi_not_found`, `update_renamed_in_excel` y `main` (24 líneas suprimidas). Excepciones convertidas a `log.warning()`. Añadidos `import logging` y `log = logging.getLogger(__name__)`.

---

### ✅ Bug caché FAISS Streamlit (resuelto 2026-05-27)

`2_RAG.py` — `load_index()` recibe `index_mtime: float` como tercer parámetro del
cache key de `@st.cache_resource`. La caché se invalida automáticamente cuando cambia
el `mtime` del `index.faiss` en disco — sin necesidad de reiniciar launchd.
`st_mtime` se calcula antes de llamar a `load_index()`; si el fichero no existe
devuelve `0.0` (capturado por el bloque `index is None`).

---

### ✅ pipeline.py — modelo de embedding de producción (resuelto 2026-05-27)

`pipeline.py` — dos cambios:
- Línea 53-55: import de `OLLAMA_MODEL_EMBED` desde `utils/constants.py` con path guard,
  siguiendo el mismo patrón que `app_utils.py`.
- Línea 183-189: `process_category()` define `_default_extra` con `--model bge-m3`
  para `5_build_embeddings.py` y lo mergea con el `extra_args` del caller. Todos los
  flujos (adhoc, inbox, scopus, integrate) usan bge-m3 automáticamente.

---

### ✅ Bug #1 y #2 — renombrado antes de procesar en run_adhoc() e integrate_adhoc() (resuelto 2026-05-27)

**Problema:** los PDFs se procesaban con sus nombres originales. Al renombrar por DOI
después, los artefactos (md_clean, chunks, summaries, metadata) quedaban huérfanos,
y `integrate_adhoc()` generaba ficheros `_2` al encontrar el PDF original ya presente
en el destino.

**Solución implementada en `pipeline.py`:**

`run_adhoc()` (línea 677): insertado rename step entre copia de PDFs y `process_category()`.
Si Crossref falla (rc != 0) se loguea warning y continúa con nombre original — el pipeline
no se interrumpe.

`integrate_adhoc()` (línea 757): antes copiaba 5 subdirs + re-indexaba solo FAISS.
Ahora: copia solo `pdfs/` → rename → `process_category()` completa. Los artefactos
existentes en el target están protegidos por el skip logic de cada script.
El contrato de retorno (`status`, `copied_pdfs`, `skipped_pdfs`, `totals`) es idéntico
— `1_Ingestar.py` no se toca.

**Consecuencia importante:** `integrate_adhoc()` ahora necesita GROBID y Ollama
disponibles (antes bastaba FAISS). Si la VPN UCA no está activa al integrar, GROBID
fallará y `process_category()` devolverá `status: "error"`. La UI lo muestra correctamente.

**Fix adicional (2026-05-27):** `integrate_adhoc()` pasa `--force` a `5_build_embeddings.py`
via `extra_args` para que el índice FAISS se regenere siempre tras integrar, incluyendo
los papers nuevos.

**Nota para proyectos ad-hoc anteriores al fix:** `integrate_adhoc()` ya no copia
md_clean/summaries/chunks/metadata del ad-hoc (se regeneran con nombre correcto).
Si se integra un ad-hoc procesado antes del fix, los artefactos con nombres viejos
quedarán huérfanos en el target — borrarlos manualmente o reprocesar con `--force`.

**Duplicados por nombre:** si el paper ya existe en la categoría destino con un nombre
ligeramente distinto (mayúsculas, guiones vs guiones bajos), el rename genera una segunda
copia. Detectar y limpiar manualmente hasta que el item 19 (detección avanzada de
duplicados) esté implementado.

---

### ✅ PDFs manuales en categorías (verificado 2026-05-16)

**Caso de prueba:** PDF manual `35. 2020-07 A. Algal reseach.pdf` en `microalgae/pdfs/`

**Resultados:**
- ✅ `3_process_corpus.py` procesa PDFs con nombres no-DOI (normaliza espacios a `_`)
- ✅ Skip logic funciona: segunda ejecución salta el PDF ya procesado
- ✅ Cadena completa OK: summarize → metadata → embeddings
- ✅ RAG query recupera chunks del PDF manual correctamente

**Comportamiento confirmado:**
- PDFs añadidos manualmente a cualquier `categorias/<cat>/pdfs/` se procesan en la siguiente ejecución
- No requieren nombres DOI (aunque se normalizan)
- Scripts saltan automáticamente lo ya procesado
- Mezcla de PDFs manuales + Scopus en la misma categoría: ambos se procesan sin conflicto

---

### ✅ Interfaz Streamlit + despliegue launchd (completado 2026-05-20)

- 5 páginas funcionando: Ingestar, RAG, Keywords, Scopus queries, DOI manual
- Servicio launchd corriendo 24/7 con auto-restart
- Mac mini configurado en modo servidor (pmset)
- Acceso desde portátil por LAN y VPN casa confirmado

**Gotchas documentados en ESTADO.md** (ver sección correspondiente).

---

### ✅ RAG multi-provider + cost tracking (completado 2026-05-20)

- Anthropic (Claude) y OpenAI (GPT) añadidos como providers de síntesis
- Contador de uso mensual en `/Volumes/research/metadatos/rag_usage/`
- Pre-estimación de coste antes de cada consulta
- bge-m3 disponible como índice alternativo a nomic para `anoxic_biogas_biodesulfurization`

### ✅ Tab Pendientes para reprocesado selectivo (completado 2026-05-21)

**Problema:** si una ingesta se corta (Streamlit reiniciado, VPN caída, timeout), no había forma sencilla de reanudar desde la web — había que lanzar comandos manuales por categoría.

**Solución implementada:**
- Nueva pestaña **Pendientes** en `1_Ingestar.py` (4 tabs ahora: Scopus / Inbox / Pendientes / Ad-hoc)
- Tabla de brechas por categoría: PDFs, MD limpio, Resúmenes, Chunks, Metadata, FAISS, Paquetes
- Lógica de detección de incompletitud: categorías con faltantes en MD/resúmenes/chunks/metadata
- Selector de categorías + botón "Reprocesar pendientes" → ejecuta `process_category()` con skip logic
- Salida en vivo igual que los otros flujos

**Caso de uso real:** `bioplastics_microplastics` con 64 PDFs, 64 MD, pero solo 50 resúmenes y 8 metadata → detectado correctamente como incompleto y reprocesado desde la web sin comandos manuales.

---

### ✅ 9_cleanup_duplicates.py — desempate por nombre limpio + apply (resuelto 2026-05-28)

**Problema:** `choose_keep_intra()` ordenaba por stem alfabético en caso de empate en completeness.
Los stems viejos con inicial de autor (`_J_`, `_J_J_`, `_A_`) caen antes que la primera
palabra del nombre limpio Crossref → el script conservaba el nombre sucio en 3 de 7 casos:
Das 2022, González Cortés 2023, Lenis 2026.

**Solución implementada en `9_cleanup_duplicates.py`:**
- `_is_clean_stem(stem)`: devuelve `True` si el stem es todo minúsculas y no contiene
  DOI embebido (`_10_\d{4,5}_`).
- Sort key en `choose_keep_intra()` y `choose_keep_cross()`:
  `(not _is_clean_stem, -completeness, stem.lower(), line_no)`.
  Los nombres limpios Crossref siempre ganan sobre nombres con mayúsculas o DOI embebido.
- `print_reindex_commands()` actualizado: muestra `--model bge-m3 --force` en lugar de nomic.

**Ejecutado:**
- `--apply`: 7 duplicados eliminados, 28 ficheros borrados en `anoxic_biogas_biodesulfurization`
  y `biogas_upgrading_biomethanation`. Metadata reescrita con backup `.bak`.
- Re-indexado FAISS con bge-m3 --force: anoxic (1704 chunks), biogas (171 chunks).

**Nota de uso:** `9_cleanup_duplicates.py --preview` debe ejecutarse periódicamente
(especialmente tras ingestas masivas o renombrados). Al hacer `--apply`, el propio script
indica qué categorías necesitan `5_build_embeddings.py --model bge-m3 --force`.

---

### ✅ Re-embeddear todas las categorías con bge-m3 (completado 2026-05-25)

bge-m3 adoptado como modelo de producción. `utils/constants.py` es la fuente de verdad (`OLLAMA_MODEL_EMBED = "bge-m3"`); importado por `8_query_rag.py` y `app_utils.py`. Índices nomic conservados pero no usados como default.

---

## Keywords y criterios de búsqueda

Revisar y afinar:
- `config/keywords.yml` — para cribado de PDFs sueltos (flujo inbox)
- `config/scopus_queries.yml` — para búsquedas Scopus directas (flujo scopus)

Categorías con pocas queries actuales (ampliar si hace falta):
- `anoxic_biogas_biodesulfurization` — solo 1 query (12 resultados)
- `bioleaching_critical_materials` — solo 1 query (39 resultados)

---

## Próximos pasos (orden sugerido)

### ✅ 1. Mejorar el editor de keywords en la web (completado 2026-05-25)

Implementada **Opción B — textarea por categoría**: un `st.text_area` por categoría, una keyword por línea. Sin dependencias extra. Botón "Guardar todo" arriba y abajo, backup `.bak` automático, badge de delta (+N/-N) en el expander de resumen. `st.data_editor` y `import pandas` eliminados.

### ✅ 2. Optimizar paquetes NotebookLM para uso con GPTs custom (completado 2026-05-25)

Implementado en `6_make_packages.py`:
- **Cabecera de corpus** al inicio del FULLTEXT: categoría, nº papers, periodo (año min-max), fecha, primeras 6 keywords de `keywords.yml`
- **Estructura por paper**: `# Paper: <id>` / DOI / Año / **Resumen** (de `summaries/<id>.summary.md` si existe) / `---` / **Texto completo**
- Año extraído de metadata JSONL o parseado del paper_id con regex `(19\d{2}|20[0-3]\d)`
- `REFERENCES` e `INDEX` sin cambios; skip logic y modo `--repack-all` intactos
- c) Split por sub-tema: pendiente (requiere clustering previo)

---

### ✅ 3. Integrar proyecto ad-hoc en categoría canónica (completado 2026-05-25)

Implementado en `pipeline.integrate_adhoc()` + `pipeline.promote_adhoc_to_category()` + sección **🔗 Integrar proyecto ad-hoc** en `1_Ingestar.py` (tab Ad-hoc):

**`integrate_adhoc(adhoc, target, delete_source)`** — merge en categoría existente:
- Copia pdfs/, md_clean/, summaries/, chunks/, metadata/ con skip por fichero existente (`_copy_files_skip_existing()`)
- Re-indexa solo FAISS del target (`5_build_embeddings.py --project <target>`)
- Checkbox "Borrar ad-hoc tras integración" → `shutil.rmtree` si marcado
- Devuelve `{"status", "copied_pdfs", "skipped_pdfs", "totals", ...}`

**`promote_adhoc_to_category(adhoc, new_name, keywords, delete_source)`** — nueva categoría:
- Copia también embeddings/ (FAISS ya no necesita re-indexarse)
- Registra keywords en `config/keywords.yml` (con backup `.bak`)
- Valida nombre (`^[a-z0-9_]+$`) y que la categoría no exista previamente
- Devuelve `{"status", "new_category", "copied_pdfs", "totals", "keywords_added", "deleted_source"}`

**UI** — radio button "Categoría existente" / "Nueva categoría" en la sección 🔗 del tab Ad-hoc:
- `_CANONICAL_CATEGORIES` duplicado en `pipeline.py` para evitar import circular con `app_utils`

---

### ✅ 4. Cron/launchd para ingesta Scopus semanal automática (completado 2026-06-05)

`scripts/run_weekly_scopus.py` — script autónomo que:
- Ejecuta `run_scopus(categories=WEEKLY_CATEGORIES, recent_days=7)` (actualmente solo `biogas_upgrading_biomethanation`).
- **Timeout 45 min**: `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=2700)`. Si se supera → estado `"timeout"`, `executor.shutdown(wait=False)` para no bloquear el hilo principal; el email se envía igualmente.
- Cuenta PDFs antes/después para calcular nuevos; cuenta chunks totales tras procesar.
- Lee `pendientes_descarga.csv`, filtra status=="pending", ordena cat asc + last_checked desc.
- Construye email HTML con tabla de resultados + tabla DOIs pendientes (con enlaces clicables).
- Envía via `smtplib` + Gmail STARTTLS. Fallback: escribe HTML en `/tmp/research_agent_weekly_report.html`.
- Soporta `--dry-run` (imprime HTML en stdout sin ejecutar Scopus ni enviar email).
- Config SMTP desde `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TO`.
- **Logging a fichero**: `FileHandler` en `PROJECT_DIR/logs/run_weekly_scopus_YYYY-MM-DD.log` + `StreamHandler` (stdout). Captura inicio, fin, estado, timeout, errores y envío de email. Guard `if not log.handlers` para evitar duplicados.

`deployment/com.research_agent.scopus_weekly.plist` — LaunchAgent:
- `StartCalendarInterval`: lunes a las 06:00 (Weekday=1, Hour=6).
- `RunAtLoad: false` — solo se lanza los lunes, no al instalar.
- Logs en `~/Library/Logs/research_agent/scopus_weekly.{log,err.log}`.

Para instalar en pciq22:
```bash
cp deployment/com.research_agent.scopus_weekly.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.scopus_weekly.plist
launchctl list | grep scopus
```

### 5. Pequeñas mejoras UX en la web (baja prioridad)

- **Toggle síntesis OFF**: mostrar aviso visible en el área principal cuando la síntesis está desactivada.
- **Botones por fila en portada**: acción "Procesar pendientes" directa por categoría en la tabla principal.
- **Página de logs en vivo**: `tail -f` de `~/Library/Logs/research_agent/*.log` directamente en la web.
- **Editor doi_manual.xlsx** con `st.data_editor` — actualmente solo visor.

✅ Botón renombrado por DOI en tab Pendientes (2026-05-31) — permite renombrar PDFs copiados directamente a `categorias/<cat>/pdfs/` sin pasar por inbox.

### ✅ 6. Actualizar precios en app_utils.py (completado 2026-05-27)

`LLM_PRICING` verificado a 2026-05-27. Único cambio:
`claude-opus-4-7`: $15/$75 → **$5/$25** (precio del Opus 4.7, no del antiguo Opus 4.1).
Resto de modelos ya eran correctos. Comentario de fecha añadido encima del dict.
Fuentes: platform.claude.com/docs/en/docs/about-claude/models · developers.openai.com/api/docs/pricing

### ✅ 7. README.md global + docstrings (completo 2026-05-29)

Documentación final del proyecto: README de primer nivel con visión general,
y docstrings en los scripts numerados que aún no los tienen.
Incluir: qué es research_agent, qué puede hacer, cómo acceder, qué categorías
existen, cómo hacer consultas RAG, cómo añadir PDFs, limitaciones, buenas
prácticas. **Prioritario si se comparte con el grupo.**

Nota: Docstrings completos añadidos a los 12 scripts numerados (0–9 + 3a + 3b): nivel completo con parámetros CLI, ficheros leídos/escritos y dependencias.

### ✅ 8. Decisión final nomic vs bge-m3 (completado 2026-05-25)

bge-m3 adoptado como modelo de producción. `utils/constants.py` centraliza el valor; `app_utils.py` y `8_query_rag.py` importan de ahí. Los índices nomic se conservan en el NAS pero no son el default.

### ✅ 9. Fix integrate_adhoc() y run_adhoc() — renombrado antes de procesar (resuelto 2026-05-27)

Ver sección "Verificaciones completadas" — Bug #1 y #2.

### ✅ 10. Instancia RAG pública (puerto 8502) (completado 2026-06-05)

Segunda instancia Streamlit con páginas RAG + Revisión bibliográfica, sin ingesta
ni configuración, limitada a Ollama. `app_public.py` con `st.navigation`, autenticación
por `check_password("PUBLIC_APP_PASSWORD")` e `is_public_app()` para filtrar providers.
Segundo plist launchd en `deployment/com.research_agent.streamlit_public.plist`.

### ✅ 11. Exportar papers desde RAG (completado 2026-05-28)

Tras consulta RAG, botón "Exportar papers relacionados" que genera ZIP descargable
con PDFs + md_clean (+ opcional summaries) de los `paper_id`s recuperados.
Implementar con `zipfile` en memoria + `st.download_button` en `2_RAG.py`.

### ✅ 12. Validar nombre proyecto en run_adhoc() (completado 2026-05-27)

`pipeline.py` — `run_adhoc()`, justo antes de `check_nas()`:
```python
if not re.fullmatch(r'^[a-z0-9_-]+$', name):
    raise ValueError(f"Nombre de proyecto inválido '{name}': solo minúsculas, dígitos, '_' y '-'")
```
`re` ya estaba importado. La validación rechaza nombres con espacios, mayúsculas o caracteres especiales antes de crear ningún directorio.

### ✅ 13. Validar API keys con llamada real (resuelto 2026-05-29)

`check_anthropic_api()` y `check_openai_api()` solo validan formato.
Hacer una llamada barata (`list models`) para verificar que la key no está revocada.
Nota: `check_anthropic_api()` y `check_openai_api()` hacen GET `/v1/models`; devuelven `(False, "Key inválida o revocada (401)")` si la key está revocada, `(False, "Timeout (5s)")` si no hay red.

### ✅ 13b. Actualizar DEFAULT_MODEL en 5_build_embeddings.py (resuelto 2026-05-28)

`5_build_embeddings.py` — añadido `import sys`, path guard y
`from utils.constants import OLLAMA_MODEL_EMBED`. `DEFAULT_MODEL = OLLAMA_MODEL_EMBED`.
Ahora lanzar el script directamente por CLI sin `--model` usa bge-m3 por defecto.

---

## Nuevas mejoras (2026-05-26)

### ✅ 14. Registro de procedencia de PDFs (completado 2026-05-26, verificado 2026-05-27)

`4_extract_metadata.py` — campos añadidos a cada registro de `papers_metadata.jsonl`:
- `stable_id` — slug DOI si hay DOI, else `paper_id` (item 16)
- `processed_date` — `date.today().isoformat()` en el momento de procesar
- `source_type` — arg `--source-type` o auto-detect (`adhoc` si project starts with "adhoc")
- `download_source` — mapeado desde `descarga_cache.json["method"]` por DOI
- `download_url` — `pdf_url` del cache entry
- `access_type` — `open_access` / `institutional` / `unknown` según método
- `download_date` — `cached_at[:10]` del cache entry

Constantes `_CACHE_PATH` y `_METHOD_TO_SOURCE` añadidas tras `DEFAULT_BASE`.
Helpers: `_doi_slug()`, `_load_prov_cache()`, `_norm_doi()`, `_infer_provenance()`. Arg `--source-type`.
`pipeline.py` no modificado: la auto-detección es suficiente. `paper_id` sin cambios (compatibilidad).
Verificado en producción 2026-05-27: campos presentes en JSONL de `anoxic_biogas_biodesulfurization` y `biogas_upgrading_biomethanation`.

### ✅ 15. Registro de DOI pendientes de descarga (completado 2026-05-28)

Crear y mantener:
```
/Volumes/research/metadatos/pendientes_descarga.csv
```

Campos: `doi`, `title`, `year`, `category`, `landing_url`, `status`, `reason`, `last_checked`, `notes`

Estados: `pending | downloaded | manual | blocked | no_pdf_found | duplicate | wrong_document`

Prerequisito para el subagente navegador (item 28).

### ✅ 16. Normalización estable de paper_id (completado 2026-05-26, verificado 2026-05-27)

`stable_id` añadido a metadata (ver item 14). `paper_id` NO cambiado — sigue siendo el
stem del fichero TEI y es la clave de todos los artefactos (md_clean, chunks, embeddings).
`stable_id = _doi_slug(doi)` cuando hay DOI, else `paper_id`. Permite enlazar el mismo
paper procesado con distintos nombres de fichero a lo largo del tiempo.
Verificado en producción 2026-05-27. Página 6_Mantenimiento.py incluye sección "Backfill metadata"
que detecta y rellenar papers sin `stable_id` (los procesados antes de este ítem).

### ✅ 17. Panel de calidad del corpus + quality_score (completado 2026-05-28)

**Panel (portada o página nueva "Calidad"):** métricas por categoría:
% PDFs con DOI, con título, con año, con resumen, con referencias, duplicados, con warnings.

**`quality_score` en metadata** (calcular en `4_extract_metadata.py`):
```json
{
  "quality_score": 0.86,
  "warnings": ["no_references_extracted", "short_md_clean", "missing_doi"]
}
```

Una vez implementado, el informe mensual de calidad (revisión mensual) sale
gratis como agregación de estos campos.

### 18. Carpeta de cuarentena — MEDIA prioridad

Crear `/Volumes/research/quarantine/` para documentos dudosos:
PDF sin texto extraíble, muy corto, sin DOI ni título fiable, material
suplementario, duplicado dudoso.

Desde Streamlit: aceptar / rechazar / mover a categoría / borrar.

### ✅ 19. Detección avanzada de duplicados (completado 2026-06-01)

`9_cleanup_duplicates.py` ampliado con dos nuevos detectores (sin tocar la lógica DOI existente):

- `normalize_title(title)` — lowercase, strip puntuación, colapsa espacios.
- `pdf_sha256(pdf_path)` — hash SHA-256 del binario PDF.
- `detect_title_duplicates(cats, base)` — agrupa por título normalizado (≥10 chars), devuelve grupos con ≥2 papers.
- `detect_hash_duplicates(cats, base)` — agrupa PDFs por hash SHA-256, devuelve grupos con ≥2 ficheros.
- `write_duplicate_report(decisions_doi, title_dups, hash_dups, out_path)` — genera `metadatos/duplicate_report.xlsx` con tres hojas: **DOI** (decisiones automáticas), **Titulo** y **Hash** (revisión manual). `openpyxl` con `try/except ImportError`.

En `main()`: los dos detectores se ejecutan siempre (preview y apply), se imprime resumen y se genera el Excel.

### ✅ 20. Log completo de consultas RAG (completado 2026-05-28)

Ampliar el registro existente en `rag_usage/` para guardar también la pregunta,
los papers recuperados y la respuesta generada:

```json
{
  "date": "YYYY-MM-DD HH:MM",
  "category": "...",
  "question": "...",
  "provider": "ollama | openai | anthropic",
  "model": "...",
  "top_k": 12,
  "retrieved_papers": ["...", "..."],
  "answer_md": "...",
  "estimated_cost": 0.0,
  "real_cost": 0.0
}
```

Ruta: `/Volumes/research/metadatos/rag_queries/rag_queries_YYYY-MM.jsonl`

Permite reproducir respuestas usadas en proyectos o artículos.

### ✅ 21. Guardar respuesta RAG como nota (completado 2026-05-28)

Botón en `2_RAG.py` tras consulta: "Guardar como nota Markdown".

Ruta: `/Volumes/research/notas_rag/<categoria>/YYYY-MM-DD_<categoria>_<slug>.md`

Convierte el RAG en herramienta de escritura científica. Relacionado con item 11
(exportar papers) — pueden implementarse juntos.

### ✅ 22. Modo revisión bibliográfica (completado 2026-05-28)

Nueva página Streamlit `📚 Revisión bibliográfica` con prompts especializados:
estado del arte, tabla de artículos clave, lagunas de conocimiento, comparativa
de mecanismos, introducción preliminar.

Entradas: categoría, rango de años, keywords de enfoque, modelo de síntesis.
Salidas: Markdown, Word, ZIP con papers utilizados, BibTeX.

### ✅ 23. Exportar BibTeX/RIS (completado 2026-05-28)

A partir de metadata y DOI, generar `selected_papers.bib` / `.ris` / `.csv`
para integración con Zotero y escritura de artículos y tesis.

### 24. Colecciones para colaboradores — MEDIA prioridad

Paquetes exportables por tema:
```
/Volumes/research/exports/proyecto_<nombre>_<fecha>/
    papers.zip
    references.bib
    resumen_estado_arte.md
    index.xlsx
```

Facilita trabajo de grupo y dirección de alumnos.
Parcialmente completado por items 10+11+22+23, salbo que quiera un excel con los datos tabulados

### ✅ 25. corpus_manifest.json (completado 2026-06-01)

`scripts/utils/corpus_manifest.py` — nuevo módulo con:
- `build_manifest(category, base)` — dict con 11 campos: `category`, `generated_at`, `n_pdfs`, `n_md_clean`, `n_chunks` (líneas totales en todos los JSONL), `n_papers_metadata`, `avg_quality_score`, `faiss_indexes` (lista por subcarpeta con phase/model/chunks/dimension/mtime), `keywords_hash` (SHA1-8 del bloque YAML de la categoría), `git_commit`, `faiss_stale` (bool: algún PDF más nuevo que el índice más reciente).
- `write_manifest(category, base)` → escribe `categorias/<cat>/corpus_manifest.json`, devuelve ruta.
- `read_manifest(category, base)` → lee JSON o devuelve `{}`.
- CLI: `python3 corpus_manifest.py --project <cat> [--base DIR]`.

`app_utils.get_corpus_manifest(category)` — wrapper con `try/except` para uso desde Streamlit.

### ✅ Selector de categorías activas (completado 2026-06-01)

`config/active_categories.yml` — nuevo fichero YAML con lista `active:` de categorías habilitadas. Las categorías inactivas no se incluyen en búsquedas Scopus, RAG ni Pendientes.

`app_utils.py` — tres nuevas funciones: `load_active_categories()` (lee el YAML, fallback a `CANONICAL_CATEGORIES`), `save_active_categories(active)` (escribe con backup `.bak` via `save_yaml()`), `is_category_active(category)`. Constante `ACTIVE_CATEGORIES_FILE`.

`6_Mantenimiento.py` — nueva **Sección 1 — Categorías activas** (expander expandido por defecto): `st.multiselect` sobre `CANONICAL_CATEGORIES`, caption explicativo, botón guardar con aviso si selección vacía. Secciones anteriores renumeradas 2–6.

`app.py` — filas de categorías inactivas en gris con `df.style.apply(_style_inactive, axis=1)`.

`pipeline.run_scopus()` — filtra `target_cats` contra la lista activa antes del bucle de descarga/procesado. Bloque `try/except` silencioso si el YAML no existe.

---

### ✅ 26. Health checks extendidos (completado 2026-05-27)

`app.py` — segunda fila de columnas bajo NAS/Ollama/GROBID:
- **Espacio libre NAS**: `shutil.disk_usage(NAS_ROOT)` → libre / total en GB; aviso si < 10 GB.
- **bge-m3 disponible**: GET `{OLLAMA_HOST}/api/tags` → busca "bge-m3" en nombres de modelos.
- **Permisos escritura NAS**: `os.access(CATEGORIAS_DIR, os.W_OK)`.
- **Latencia**: `check_ollama()` y `check_grobid()` miden tiempo de respuesta con `time.time()` e incluyen N ms en el mensaje. Funciones en `app_utils.py`; `(bool, str)` sin cambio de firma.
Estado FAISS por categoría: pendiente (requiere lógica por fila en tabla de categorías).

### 27. Backup config extendido — MEDIA prioridad

Extender los backups `.bak` actuales a:
`keywords.yml`, `scopus_queries.yml`, `.env.example` (sin claves), `doi_manual.xlsx`, manifests.

Ruta: `/Volumes/research/metadatos/backups_config/`

### 28. Subagente navegador OpenClaw — Bloque C

Para resolver descargas fallidas donde Unpaywall/Elsevier no encuentran PDF
pero la landing page tiene botón accesible.

**OpenClaw** (antes Clawdbot/Moltbot) es un agente autónomo open-source
self-hosted que puede navegar la web y ejecutar acciones. Actualmente bajo
fundación independiente con apoyo de OpenAI (MIT license).

Entrada: `pendientes_descarga.csv` (item 15, prerequisito).
Reglas: sin saltarse paywalls, sin captchas, pausas entre accesos, límite por sesión,
parar ante 403/429.

### ✅ 29. Página de actividad (completado 2026-06-05)

`scripts/streamlit_app/pages/9_Actividad.py` — página solo para la app privada:
- Sección 1: uso RAG mes actual (`rag_usage_YYYY-MM.jsonl`) — métricas + tabla modelos de pago.
- Sección 2: últimas 20 consultas RAG (`rag_queries_YYYY-MM.jsonl`) en orden inverso.
- Sección 3: corpus por método de ingesta (source_type) leído de `papers_metadata.jsonl` por categoría.
- Sección 4: errores `[ERROR]` de los 5 logs más recientes en `research_agent/logs/`.
- Guard `is_public_app()` → `st.stop()` directo; app privada requiere `check_password("PRIVATE_APP_PASSWORD")`.
- Botón "🔄 Actualizar" + manejo de excepciones por sección.

### 30. Documentación para el grupo — ALTA si se comparte

- **Guía rápida**: cómo buscar artículos, cómo hacer buenas preguntas RAG,
  cómo exportar papers, cómo citar correctamente.
- **Política de uso**: no descargas masivas, no saltarse paywalls, no compartir
  PDFs fuera del grupo si la licencia no lo permite, respetar acceso institucional.

### 31. Pipeline para libros de docencia — futuro

Pipeline paralelo a categorias/ para 30+ libros de bioprocesos (texto
extraíble, inglés). Estructura propuesta: libros_docencia/bioprocesos/.

Diferencias con el pipeline actual:
- Parser: pymupdf en lugar de GROBID (libros no son papers)
- TOC del PDF → metadata jerárquica (capítulo, sección, páginas) por chunk
- Sin 4_extract_metadata.py ni 3b_summarize.py (no aplican a libros)
- Reutiliza: bge-m3, FAISS, infraestructura Streamlit

Casos de uso:
- RAG con citas precisas (libro, capítulo, página) para preparar clases
- Comparar tratamiento de un mismo concepto en varios libros
- Página "Preparar clase" que consulta libros + papers de las categorías
  relevantes (microalgae, biogas_upgrading, etc.) y sintetiza
  "manual dice X, papers recientes matizan Y"

MVP: 2-3 libros como proyecto ad-hoc adaptado, validar utilidad antes
de productizar.

Considerar primero: terminar items 4, 7, 15, 17-25, 30.

---

## Mejoras de calidad RAG y robustez (2026-06-10)

Propuestas derivadas de la revisión del pipeline. Ordenadas por impacto: 32–34
suben la calidad de recuperación (lo que más determina si el RAG es útil); 35–36
refuerzan la robustez del procesado; 37–40 son evaluación, coste y mantenimiento.

### ✅ 32. Chunking consciente de la estructura (completado 2026-06-10; rollout completado 2026-06-11)

`section_canonical` jerárquico + etiqueta `"table"` en los chunks JSONL. Commit b097744.

**Implementación en `3_process_corpus.py`:**
- `split_by_headings()` devuelve ahora `(título, texto, nivel)` — el nivel es el nº de `#` iniciales; el preamble recibe nivel 0.
- Nueva función `canonical_section(title)` clasifica un título de heading en una de 7 etiquetas: `abstract | introduction | methods | results | discussion | conclusion | other`.
- `build_chunk_records()` mantiene un mapa `ancestros: Dict[int, Tuple[str, str]]`. Al procesar un heading nivel L: actualiza el mapa y elimina niveles > L; busca el canonical más cercano subiendo de L a 1 que no sea `"other"`.
- Subsecciones descriptivas (p. ej. "Reactor operation", "Microbial community analysis") heredan el canonical del heading padre (methods/results).
- Chunks de tabla (`type=="table"`): `section_canonical = "table"` fijo.
- El campo `section` (título hoja crudo, lo usa `8_query_rag.py`) queda intacto.

**Verificado en `anoxic_biogas_biodesulfurization` (943 chunks):**

| section_canonical | chunks | % |
|---|---|---|
| other | 363 | 38.5% |
| methods | 167 | 17.7% |
| results | 143 | 15.2% |
| table | 89 | 9.4% |
| conclusion | 73 | 7.7% |
| introduction | 67 | 7.1% |
| abstract | 41 | 4.3% |

El `other` residual (38.5%) es cola larga de títulos descriptivos no-IMRaD (subsecciones muy específicas sin patrón de keyword reconocible) — residuo legítimo. FAISS re-indexado con `--force`.

**✅ Rollout completado (2026-06-11):** re-troceadas + re-indexadas las 8 categorías con `3_process_corpus.py --force-md` + `5_build_embeddings.py --force --model bge-m3`. `section_canonical` y `year` poblados en todas; tablas capadas; FAISS reconstruido.

### ✅ v1 (híbrido denso+BM25+RRF) 2026-06-11; reranking en fase 2, pendiente
### 33. Recuperación híbrida (denso + BM25) + reranking — ALTA prioridad

FAISS es solo denso: captura semántica pero se le escapan los *matches* léxicos
exactos que importan en el dominio (siglas `NR-SOB`, `H2S`, `TiO2`, nombres de
cepas como `Acidithiobacillus`, códigos `PHA/PHB`).

- Añadir índice BM25 por categoría con `rank-bm25` (en memoria, suficiente para
  miles de papers; sin montar Elasticsearch). Construir el índice desde los mismos
  chunks JSONL.
- Fusionar resultados denso + BM25 con **Reciprocal Rank Fusion** (RRF): combina por
  posición sin normalizar puntuaciones de escalas distintas.
- Reranking opcional sobre el top-N fusionado con `bge-reranker` (vía Ollama) o un
  cross-encoder pequeño, antes de pasar al LLM de síntesis.
- Tocar `8_query_rag.py` y la capa de retrieval de `2_RAG.py` / `7_Revision.py`.
  Toggle en la web para activar/desactivar híbrido y comparar.

### ✅ 2026-06-11 (sección + año; revista descartada)
### 34. Filtrado por metadato en la query — ALTA prioridad

Permitir filtrar **antes/durante** la recuperación por categoría, rango de años,
revista y (si está el item 32) sección.

- Implementar con `IndexIDMap` + post-filtrado sobre `metadata.jsonl`, o índice por
  categoría ya existente + filtro de año/revista en el set de candidatos.
- Reduce ruido cuando la pregunta es claramente de una categoría/periodo concreto.
- UI: selectores de año (rango) y revista en `2_RAG.py`, además del filtro de
  categoría/fase ya presente.

### 35. Fallback OCR para PDFs escaneados — MEDIA prioridad

GROBID no extrae nada de un PDF que es imagen → entra vacío al índice.

- Detectar "texto extraído ≈ 0 caracteres" tras `3_process_corpus.py` y disparar OCR.
- `ocrmypdf` (Tesseract) genera un PDF con capa de texto; reintentar GROBID sobre él.
- Idiomas: `eng` (corpus mayoritariamente en inglés).
- Encaja con la carpeta de cuarentena (item 18): si tras OCR sigue vacío → cuarentena.

### 36. Idempotencia y reanudación por documento — MEDIA prioridad

Estado explícito por PDF (descargado → renombrado → extraído → resumido → indexado)
para que un fallo a mitad no obligue a reprocesar todo ni deje entradas a medias.

- Registro de estado por `paper_id`/`stable_id` (JSON o columna en manifest).
- Complementa el indexado incremental de FAISS (item FAISS incremental, 2026-06-04)
  y el skip logic existente, dándole trazabilidad y reanudación explícita.
- Útil tras timeouts del job semanal o caídas de VPN a mitad de ingesta.

### 37. Set de evaluación del RAG (golden Q&A) — MEDIA prioridad (siguiente paso natural)

**Siguiente paso natural tras 32/33/34 (2026-06-11):** es la única forma de medir si el
chunking estructural (32), el híbrido denso+BM25 (33) y los filtros sección/año (34)
mejoran o empeoran, y de justificar objetivamente el reranking pendiente de la fase 2 del item 33.

Conjunto de pares pregunta/respuesta de referencia por categoría que se corre tras
cualquier cambio de chunking, embeddings, modelo o estrategia de retrieval.

- 5–10 preguntas por categoría con los `paper_id`/secciones esperados.
- Métricas de recuperación (hit@k, MRR) y, opcionalmente, evaluación de la síntesis.
- Es la única forma objetiva de saber si los items 32/33/34 mejoran o empeoran.
- Guardar en `metadatos/eval/golden_<categoria>.jsonl` + script `eval_rag.py`.

### 38. Batch API de Anthropic para resúmenes — BAJA prioridad

Los resúmenes/metadatos no necesitan tiempo real → procesar por lotes abarata.

- Usar la Batch API de Anthropic para `3b_summarize.py` cuando el provider sea Claude.
- Cachear el resumen por DOI/`stable_id` para no recalcular al reprocesar.
- Solo aplica si se usa Claude para resúmenes; el default sigue siendo qwen3:14b local.

### 39. Tests pytest + verificación AST en CI ligero — MEDIA prioridad

Formalizar como tests la verificación AST que ya se incluye en los prompts de Claude Code.

- `pytest` sobre `_clean_doi`, `DOI_REGEX` (incluido el caso Wiley/ACS SICI con `<>`),
  `sanitize_filename`/`shorten_title` y `_norm` de coherencia PDF/MD.
- Tests de regresión para los bugs ya documentados (guiones vs guiones bajos,
  ligaduras Unicode, sufijos de DOI).
- Opcional: hook pre-commit que corra `pytest` + parseo AST de los scripts tocados.

### 40. Backup automático de FAISS + categorias a research_bk — MEDIA prioridad

Distinto del item 27 (backup de config): aquí se respalda el **corpus y los índices**.

- Snapshot programado (LaunchAgent) de los índices FAISS y de `categorias/` al NAS
  Synology `research_bk`.
- Ahora que todo vive en el SSD Crucial X9 de `pciq22`, el NAS queda como única copia.
- Recordar restricciones NAS ya documentadas: usar `shutil.copy` (no `copy2`),
  evitar `mv` (usar `cp`), `Path.mkdir()` puede fallar en el mount bajo Python 3.13.

### 41. Limpiar el índice viejo all__bge-m3 de anoxic — BAJA prioridad

Fase divergente sin `section_canonical`/`year` en sus chunks. Borrar o re-indexar para
que no compita con el índice canónico al vuelo (items 32/34).
