# Mejoras realizadas — research_agent
> Histórico append-only (lo más nuevo arriba). Backlog: Mejoras_pendientes.md · Estado/arquitectura: ESTADO.md

---

### Cierre de hallazgos pendientes (2026-06-17)

- **sort_keys=True en `promote_adhoc_to_category`** — corregido a `sort_keys=False` en `scripts/pipeline.py` (línea 1253); keywords.yml ya no se reordena alfabéticamente en cada promoción, la categoría nueva se añade al final.
- **Filtro de año descarta papers con `year=None` en silencio** — documentado como decisión aceptada. Función `passes_filters()` en `scripts/utils/retrieval.py` líneas 76-80: si `year` no está en metadata ni es derivable de `paper_id`, el chunk se excluye cuando hay filtro de año activo. Comportamiento correcto, no requiere cambio.

---

### 47. Adjuntar documentos efímeros a la consulta RAG ✓ (16/06/2026)

Permite adjuntar PDF/txt/md o pegar texto junto a la consulta en `2_RAG.py`.
El documento es efímero (no se indexa ni ingiere al corpus) pero citable con
clave propia `(Etiqueta; adjunto)`.

Implementación:
- `utils/attachments.py`: extracción (`pymupdf`), troceado simple, embedding
  al vuelo con bge-m3, búsqueda en memoria, fusión "híbrido sensato".
- `utils/citations.py`: `attachment_citation_key()`, `build_cite_map` con
  soporte de campo `_cite` en metadata de chunks de adjunto.
- `2_RAG.py`: uploader + text_area + etiqueta de cita + cupo mínimo
  configurable (default 3) + caché por hash en `st.session_state`.
- Fusión: cupo mínimo garantizado del adjunto + resto por distancia (no
  híbrido) o solo corpus (híbrido, escalas RRF vs L2 no comparables).
- Nueva dependencia: `pymupdf` (instalada en venv `rag_papers` en pciq22).

---

### ✅ Ingesta semanal: añadir anoxic_biogas_biodesulfurization + timeout 5400s (2026-06-15)

- `scripts/run_weekly_scopus.py`: `WEEKLY_CATEGORIES` ahora incluye `"anoxic_biogas_biodesulfurization"` además de `"biogas_upgrading_biomethanation"`.
- `SCOPUS_TIMEOUT = 5400` (antes 2700) — cierra el ítem pendiente del timeout del job semanal (referenciado como "item 4" en notas previas).
- `active_categories.yml`: `anoxic_biogas_biodesulfurization` ya estaba activa, sin cambios necesarios.
- Decisión: la query Scopus de anoxic se deja sin afinar (1 query, ~12 resultados/semana); los falsos positivos de limnología/sedimentos se descartan a mano en la tab Pendientes.

---

## Hecho hoy (2026-06-14)

- ### Fix: filas "ya en corpus" descuadraban el informe de descarga
  `3a_download_pdfs.py` — el branch de skip por `doi_registry` hacía `continue` sin añadir a
  `results`, rompiendo la alineación posicional de `save_results()`
  (`aligned = source_df.iloc[:len(results)]` + `pd.concat(axis=1)`): las filas saltadas se
  quedaban en el informe emparejadas con el `download_status` de otra fila → acababan en
  `pendientes_manual` y descuadraban todas las columnas a partir del primer skip.

  Fix: nuevo estado `DownloadStatus.SKIPPED_CORPUS = "ya en corpus"`; el branch ahora añade
  siempre un resultado con ese status antes del `continue`. Queda fuera de `pending_mask`
  (`{NOT_DOWNLOADED, ERROR}`) → excluido de pendientes; `record()` no se llama en ese branch
  → `skipped_registry` sin doble conteo.

  Verificado en producción (`anoxic_biogas_biodesulfurization`): 86 filas → 61 `ya en corpus`,
  23 `no descargado`, 2 sin DOI; columnas alineadas. Los 23 restantes confirmados fuera de
  corpus (registry=0/metadata=0): ruido de query + paywalls, pendientes legítimos.

- ### Fix: `update_doi_registry` normaliza claves con `_norm_doi_key`
  `pipeline.py::update_doi_registry()` guardaba el DOI crudo de `extract_doi_from_pdf` y leía
  las claves del registro sin normalizar, divergiendo de `build_doi_registry_from_nas()` (que
  usa `_norm_doi_key`: minúsculas, sin prefijo `doi.org/`, sin `/` final). Alineados ambos
  escritores con `_norm_doi_key`.

  Verificación posterior en `doi_registry.txt`: 3 entradas con mayúsculas (sin prefijo/barra)
  detectadas — benignas, ambos lectores (`3a_download_pdfs.py` y `_load_corpus_doi_index`)
  normalizan a minúsculas al cargar; se autocorregirán en próxima reescritura.

---

## Hecho hoy (2026-06-13)

- **Cierre de sesión — consolidación de hoy.**
  - Puerta de dedup por DOI en `process_category` (`screen_new_pdfs_against_corpus`) + registro autoritativo desde `papers_metadata.jsonl`.
  - `detect_affected_categories` con `normalize_stem`; dedup por título ignora grupos con ≥2 DOIs distintos.
  - Cuatro capas de coherencia PDF/MD/Metadata/TEI: `prune_orphan_metadata`, `prune_orphan_tei`, y "Corregir" renombra por DOI antes de reprocesar.
  - Fix DOIs (item 44): barra final, `:` válido, fallback Crossref/doi_manual; `4_extract_metadata.py` preserva `title`/`doi`/`journal`/`year`/`authors` y usa Crossref por DOI para journal (181/183 en `biogas_upgrading`).
  - Editor de **Artículos** (privado): edita título/año/autores/revista/DOI, filtros, borrado reversible (cuarentena + re-index FAISS).
  - **Verificado en pciq22:** `4_extract_metadata.py` reporta 0 TEI huérfanos en las 10 categorías (39 ficheros movidos a `quarantine/orphan_tei/`).
  - Detalles técnicos en las entradas anteriores de hoy y en `ESTADO.md`.

- **Limpieza de TEI huérfanos (`pipeline.py` + `6_Mantenimiento.py`).**
  - Nueva función `prune_orphan_tei(category, apply, on_output)`: detecta/mueve a cuarentena ficheros `tei/*.tei.xml` sin `md_clean` correspondiente (restos de procesados con nombres antiguos, ya saltados por `4_extract_metadata.py`). Reversible en `/Volumes/research/quarantine/orphan_tei/<ts>/<cat>/`.
  - Nuevo bloque "🗄 TEI huérfanos (tei ↔ md_clean)" en **6_Mantenimiento → Coherencia PDF/MD**: multiselect de categorías, botón "🔍 Detectar TEI huérfanos" (tabla Categoría/Fichero TEI) y "🗄 Mover a cuarentena" (condicional). No afecta a metadata ni FAISS.

- **`4_extract_metadata.py` fallback de revista vía Crossref por DOI.**
  - Nuevo helper `_crossref_journal(doi)` consulta `https://api.crossref.org/works/<doi>` y extrae `container-title`; cacheado en memoria + `time.sleep(0.1)` de cortesía.
  - Orden de resolución de `journal`: previo no vacío > TEI > Crossref por DOI. La preservación de campos manuales sigue intacta.

- **`4_extract_metadata.py` preserva correcciones manuales al reextraer.**
  - Nuevo conjunto `PRESERVE_FIELDS = ("title", "doi", "journal", "year", "authors")` y helper `_is_filled(v)`.
  - Al reextraer, si el registro previo de `papers_metadata.jsonl` tiene alguno de esos campos relleno, se conserva (gana sobre el TEI); solo se rellena desde el TEI cuando el previo está vacío/ausente.
  - Sustituye la preservación específica anterior de `doi`/`journal`; mantiene el fallback de DOI a `doi_manual.xlsx` cuando no hay ni TEI ni previo.
  - `quality_score`/`warnings` se calculan después de aplicar la preservación, sobre el registro final.

- **Título editable en el editor de Artículos (`11_Articulos.py`).**
  - En `st.data_editor` de la sección "✏️ Editar / 🗑 eliminar", la columna `title` pasa a editable (`disabled=False`) manteniendo `width="large"`.
  - El handler de "💾 Guardar cambios" detecta cambios de título junto a DOI/año/autores/revista y los incluye en `updates[pid]["title"]`.
  - `update_metadata_fields` aplica el campo `title` al reescribir `papers_metadata.jsonl` (backup `.bak` previo).

- **Filtros en el editor de artículos (`11_Articulos.py`).**
  - Buscador de texto (título/DOI/autor) + radio "Mostrar": Todos / Sin DOI / Sin año / Sin autores / Incompletos.
  - `_incompleto(r)`: True si falta DOI, año o autores.
  - El `key` del `st.data_editor` incluye `hash((q_ed, mostrar))` → reset automático del editor al cambiar filtro.
  - Botón Crossref, editor y botones Guardar/Eliminar envueltos en `if not edit_rows: … else: …`.

- **Editor de artículos + borrado reversible (`11_Articulos.py`).**
  - `get_category_stats` en `app_utils.py`: columna "Metadata" ya cuenta líneas del `papers_metadata.jsonl` (no per_paper/*.metadata.json obsoletos).
  - `_parse_authors_text`: heurística "Forename Surname; …" — último token = apellido (antes asumía formato "Apellido, Nombre").
  - `delete_papers`: simplificado — cuarentena a `quarantine/deleted/<ts>/`, re-index vía `pipeline.run_step` (ya no usa subprocess directo), devuelve `{"deleted", "dest"}`.
  - Bloque `if not PUBLIC:` reescrito: `st.data_editor` con TODAS las filas de la categoría (no solo sin-DOI); columnas editables DOI + Año + Autores + Revista; checkbox `_sel` para marcar borrado; botón "Guardar cambios" → `update_metadata_fields()` (backup `.bak`); botón "Eliminar seleccionados" → `delete_papers()` + re-index FAISS (cuarentena reversible).

- **Item 44 cerrado + fix barra final + `:` en DOI + fallback Crossref + emparejado doi_manual.**
  - `utils/pdf_utils.py`: `_clean_doi` conservador — paso general
    `re.sub(r'[a-zA-Z]{3,}$','')` → `re.sub(r'(?<=\d)[a-zA-Z]{3,}$','')`:
    solo recorta alfa-texto pegado a un dígito (`129348Abstract`, `example2within`);
    sufijos válidos tras `/` o `-` (`10.1000/xyz`, `10.1023/B:HYDR…3b`) se conservan.
    Nueva función pública `normalize_doi(doi)`: strip + quita prefijo URL + `rstrip("/")`.
    Test `xfail(strict)` de item 44 eliminado; ahora pasa como test normal.
  - `1_rename_papers_by_doi.py`: importa `normalize_doi`, `normalize_stem`;
    `load_doi_manual` indexa también por stem normalizado y título normalizado (lookup robusto);
    `process_pdf` intenta los tres ejes; `normalize_doi(doi)` antes de Crossref (elimina
    barra final → no más 404 para `10.1002/bit.26092/`); handler HTTPError conserva el
    fichero si el DOI es válido (`HTTP_ERROR_<N>_DOI_KNOWN`).
  - Tests: `TestNormalizeDoi` (6 casos), `test_colon_doi_preserved`, caso HYDR en
    `TestDOIRegex`. **53 passed** (era 56 passed 1 xfailed).

- **`detect_title_duplicates` ignora grupos con ≥2 DOIs distintos.**
  Un mismo título con DOIs distintos son artículos diferentes, no duplicados.
  La dedup por título solo aplica ahora a papers sin DOI (o todos con el mismo DOI).
  Cambio mínimo: reemplazado el list-comprehension final por un bucle que filtra
  `distinct_dois = {p["doi"] for p in papers if p.get("doi")}` y salta el grupo
  si `len(distinct_dois) >= 2`. Emite `log.debug` para trazabilidad.

- **Poda de metadata huérfana — COMPLETADO.**
  - `pipeline.py`: constantes `_META_STEM_FIELDS` / `_META_STEM_SUFFIXES`, helper privado
    `_record_stem(rec)` (extrae stem normalizable de cualquier campo identificador del registro),
    y función pública `prune_orphan_metadata(category, apply, on_output)`.
    Detecta registros de `papers_metadata.jsonl` sin `md_clean` correspondiente (papers
    fantasma / ruido del catálogo). Reversible: backup `.bak` + volcado de eliminados a
    `metadata/_orphans_<ts>.jsonl` + per_paper huérfanos movidos a
    `metadata/_orphans_per_paper_<ts>/`. No toca el índice FAISS.
  - `6_Mantenimiento.py`: tercer bloque en el expander **Coherencia PDF/MD** —
    "🧹 Metadata huérfana (metadata ↔ md_clean)". Multiselect de categorías (todas por
    defecto), botón "🔍 Detectar" → tabla de orphans con columnas Categoría/stem/doi/title,
    botón "🗑 Eliminar huérfanos" condicional (patrón flag + `st.rerun()`), caption
    aclaratorio sobre no-impacto en FAISS.

---

## Hecho hoy (2026-06-13)

- **Puerta de deduplicación por DOI en `pipeline.py` — COMPLETADO.**
  - Nueva constante `QUARANTINE_DIR = NAS_ROOT / "quarantine" / "duplicates"`.
  - Nuevos helpers privados: `_norm_doi_key` (normaliza DOI a clave comparable),
    `_iter_papers_metadata` (itera `papers_metadata.jsonl` del corpus),
    `_load_corpus_doi_index` (construye índice DOI→ubicación desde metadata + registro),
    `_pdf_sha256` (hash SHA-256 de un PDF).
  - Nueva función `screen_new_pdfs_against_corpus(category, on_output)`: detecta PDFs
    NUEVOS (sin `md_clean` correspondiente) cuyo DOI o hash binario ya están en el corpus
    y los mueve a `quarantine/duplicates/<ts>/<cat>/` con `_manifest.csv`. Reversible.
    Emite `🟡 cuarentena: <fichero> — <razón>` por PDF apartado.
  - `process_category()`: nuevo parámetro `screen_duplicates: bool = True`; si True,
    llama a `screen_new_pdfs_against_corpus` antes de la cadena de procesado (tolerante
    a fallos: aviso y continúa). Flujos Scopus e Inbox lo heredan con True.
  - `run_adhoc()`: pasa `screen_duplicates=False` (los PDFs ad-hoc son intencionales,
    no pasan por la puerta).
  - `build_doi_registry_from_nas()` **reescrito como autoritativo**: fuente primaria
    `papers_metadata.jsonl` (DOI limpio del TEI); respaldo extracción PDF para DOIs
    no vistos en metadata. Claves normalizadas por `_norm_doi_key` (minúsculas, sin
    prefijo `doi.org`, sin `/` final). Antes solo leía PDFs.
  - `detect_affected_categories()`: ahora compara stems con `normalize_stem` (de
    `utils/pdf_utils`) en lugar de igualdad exacta — cierra hallazgo nº 1 del backlog.

- **Item 39 (tests pytest + refactor `_norm`) — COMPLETADO y verificado.** Las tres `_norm`
  (4_extract_metadata.py, 6_Mantenimiento.py, 1_Ingestar.py) eran idénticas → extraídas a
  `normalize_stem(s)` en `utils/pdf_utils.py` (cuerpo exacto); los tres importan
  `normalize_stem as _norm` (diff mínimo, llamadas intactas). Eliminado el `import unicodedata`
  ya inútil en 4_extract_metadata.py (verificado: grep vacío). Suite nueva en `tests/`
  (`conftest.py` añade scripts/ a sys.path; `pytest.ini` en raíz): `test_pdf_utils.py`
  (DOI_REGEX incl. SICI `<>`, `_clean_doi`, `extract_doi_from_text`, `slugify`, `strip_accents`,
  `normalize_stem`) y `test_rename.py` (`shorten_title`/`sanitize_filename` de 1_rename vía
  importlib). **56 passed, 1 xfailed**. `pytest>=8.0` en requirements. Verificado en pciq22:
  Coherencia PDF/MD sin cambios.
- **Dos hallazgos de los tests → backlog:** item 44 (`_clean_doi` recorta sufijos DOI legítimos de
  3+ letras: `10.1000/xyz`→`10.1000/`) e item 45 (utilidades de texto duplicadas y DIVERGENTES
  entre `pdf_utils` —stale— y `1_rename` —con el fix de 2026-05-28—; el renombrado usa las
  correctas de 1_rename).

---

## Hecho hoy (2026-06-12)

- **Item 42 (higiene) — núcleo aplicado y verificado:** pipeline.py (copy2→copy en
  `_copy_files_skip_existing`; eliminado el fallback inalcanzable de `_CANONICAL_CATEGORIES` +
  `sys.path.insert` duplicado; regex de `promote_adhoc_to_category` alineado a `[a-z0-9_-]+`);
  keywords.yml (quitado typo `photocataysis` y espacio final de `monolithic`); `config/.env` de
  pciq22 (`SMPT_TO→SMTP_TO`, verificado una sola línea). Streamlit reiniciado, ambas instancias
  status 0. Pendiente del 42: copy2→copy en `9_cleanup_duplicates.py`. Diferido: ampliar
  keywords de `microalgae` (al reactivar la categoría). Menor: `or os.getenv("SMPT_TO")` en
  run_weekly_scopus.py es ahora código muerto inofensivo.
- **Item 40 (backup) — baseline manual hecho y verificado:** copia completa /Volumes/research →
  research_bk; decisiones y comando definitivo fijados en el item 40. Página de UI pendiente.

---

## Verificaciones completadas

### ✅ Sesión 2026-06-10/11 — items 32/33/34, chunking robusto, páginas Duplicados/Artículos, gestión DOIs y revista

Resumen de la sesión (detalle ampliado en los bloques siguientes y en ESTADO.md):

- **Item 32 — ROLLOUT COMPLETO:** las 8 categorías re-troceadas (`3_process_corpus.py
  --force-md`, re-chunk desde TEI existente, sin GROBID) + re-indexadas
  (`5_build_embeddings.py --force`). Cierra el "pendiente: re-trocear el resto".
  `section_canonical` + `year` poblados en todas.
- **Item 33 — recuperación híbrida densa+BM25+RRF ✅** (commit 17be44b): nuevo
  `scripts/utils/retrieval.py` (`tokenize`, `build_bm25`, `dense_rank`, `bm25_rank`,
  `rrf_fuse` con RRF_K=60, `passes_filters`, `pool_size`); BM25 en memoria al vuelo desde
  `metadata.jsonl`; flag `--hybrid` en `8_query_rag.py`; toggle OFF por defecto en
  `2_RAG`/`7_Revision`; `rank-bm25` en requirements. RERANKING aplazado a fase 2 (item 37).
- **Item 34 ✅** (commits d9f7a54, 9345c78): filtrado por sección (`--sections`) y por año
  (`--year-start`/`--year-end`) en `8_query_rag.py` + UI en `2_RAG`/`7_Revision`;
  `CANONICAL_SECTIONS` y `year_from_paper_id` en `utils/constants.py`; `5_build_embeddings.py`
  denormaliza `year` en `metadata.jsonl`. La REVISTA (descartada en su día) ahora SÍ:
  extracción desde TEI en `4_extract_metadata.py` + filtro/columna en la página Artículos.
- **Fix robustez de chunking** (commits 6454008, a05bb14): `MAX_EMBED_CHARS` +
  `_split_to_max_chars` en `3_process_corpus.py` (texto Y tablas — antes las tablas se emitían
  enteras) + truncación REACTIVA por contexto en `5_build_embeddings.py` (captura
  `ResponseError`, trunca y reintenta; el `text` de metadata queda completo).
- **Página Duplicados** (`10_Duplicados.py`, solo privada; commit fb320a9): detección en vivo
  título+hash, cuarentena REVERSIBLE (mueve a `/Volumes/research/quarantine/duplicates/<ts>/`
  + `_manifest`, quita la línea de `papers_metadata.jsonl` con `.bak`) vía `quarantine_paper()`
  en `9_cleanup_duplicates.py`; guard de falsos positivos en grupos por título (≥2 PDFs o ≥2
  DOIs → "No es duplicado" por defecto + aviso); `importlib` con registro en `sys.modules`
  antes de `exec_module` (dataclass Python 3.13).
- **Página Artículos** (`11_Articulos.py`, privada+pública; commit 37d0e7c): resumen por
  categoría (`get_categories_summary`/`category_summary_row` en `app_utils.py`, columna "Sin
  DOI") + listado desde `papers_metadata.jsonl` (filtros texto/año/revista/DOI, DOI como
  `LinkColumn`, autores legibles `_fmt_authors`, export CSV).
- **Gestión de DOIs faltantes** (privada; commits b9e4eea, 9e95227): columna Sin DOI, filtro,
  asignación manual + sugerencia Crossref (`crossref_suggest` con título+apellido1+año,
  `mailto=UNPAYWALL_EMAIL`), escritura a `papers_metadata.jsonl` (`.bak`) + upsert
  `doi_manual.xlsx` (`assign_dois`).
- **`4_extract_metadata.py`** (commits a1c377e, 622d0a6): revista desde TEI
  (`monogr/title[@level='j']` + fallback); fallback de DOI a `doi_manual.xlsx`; preservación de
  `doi`/`journal` no vacíos al reextraer; salta TEI huérfanos sin `md_clean` (imprime la lista)
  → la metadata refleja el corpus real, sin papers fantasma.

---

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

**No tocado (correcto):**
- Docstrings en `0_scopus_api.py:19` y `3a_download_pdfs.py:41,58` — no son rutas funcionales
- Todas las referencias a `pciq22.uca.es` son URLs de red (`OLLAMA_HOST`, `GROBID_URL`) — correctas
- `/Volumes/research/` en código — correcto en ambas máquinas

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

---

### ✅ RAG multi-provider + cost tracking (completado 2026-05-20)

- Anthropic (Claude) y OpenAI (GPT) añadidos como providers de síntesis
- Contador de uso mensual en `/Volumes/research/metadatos/rag_usage/`
- Pre-estimación de coste antes de cada consulta
- bge-m3 disponible como índice alternativo a nomic para `anoxic_biogas_biodesulfurization`

---

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

## Items completados (numerados)

### ✅ 39. Tests pytest + refactor `_norm`→`normalize_stem` (completado 2026-06-13)
Ver detalle en "Hecho hoy (2026-06-13)" arriba. Hallazgos derivados: items 44 y 45 (Mejoras_pendientes.md).

---

### ✅ 42. Lote de higiene revisión 2026-06-12 (completado 2026-06-12)
Aplicado y verificado: pipeline.py (copy2→copy en _copy_files_skip_existing; fallback muerto de
_CANONICAL_CATEGORIES + sys.path.insert duplicado eliminados; regex adhoc/promote alineado a
[a-z0-9_-]+); keywords.yml (typo photocataysis y espacio final de monolithic);
9_cleanup_duplicates.py (copy2→copy en rewrite_metadata, línea 581); config/.env de pciq22
(SMPT_TO→SMTP_TO, una sola línea). Diferido: ampliar keywords de microalgae (al reactivar la
categoría). Menor: `or os.getenv("SMPT_TO")` en run_weekly_scopus.py es ya código muerto inofensivo.

---

### ✅ 40. Backup de FAISS + categorias/ a research_bk — COMPLETADO (2026-06-12)

Manual (NAS de casa por VPN + montaje SMB; NO automático, un job programado fallaría en silencio).
Comando: `/opt/homebrew/bin/rsync -rv --size-only --no-perms --no-owner --no-group` + excludes de
dirs de sistema macOS, de /Volumes/research/ a la RAÍZ de /Volumes/research_bk/. `--size-only`
porque el SMB del Synology no conserva el mtime (comparar por tiempo re-copia en bucle). rsync
clásico de Homebrew, no el openrsync nativo. `#recycle` con auto-vaciado 15–30 días. No `--inplace`.
UI: página `12_Backup.py` (privada) con detección de montaje (`os.path.ismount`), fecha/antigüedad
desde `last_backup.json`, botones "Ver qué cambiaría" (dry-run con conteo) y "Copiar ahora", conteo
legible ("✅ Todo al día" / "📋 N ficheros"); banner de antigüedad en portada (umbral 15 días);
helper `read_last_backup()` en app_utils. Verificado 2026-06-12: dry-run convergente (0 ficheros);
primera copia por botón OK (last_backup.json 2026-06-12 23:17, "hace 0 días").

---

### ✅ 34. Filtrado por sección y año — marcador (2026-06-11)

Ver detalles en sección "Verificaciones completadas" arriba.

---

### ✅ 33 (v1). Recuperación híbrida denso+BM25+RRF — marcador (2026-06-11)

v1 completado. Reranking aplazado a fase 2 (ver Mejoras_pendientes.md item 33).
Ver detalles en sección "Verificaciones completadas" arriba.

---

### ✅ 32. Chunking consciente de la estructura (completado 2026-06-10; rollout 2026-06-11)

`section_canonical` jerárquico + etiqueta `"table"` en los chunks JSONL. Commit b097744.

**Implementación en `3_process_corpus.py`:**
- `split_by_headings()` devuelve ahora `(título, texto, nivel)` — el nivel es el nº de `#` iniciales; el preamble recibe nivel 0.
- Nueva función `canonical_section(title)` clasifica un título de heading en una de 7 etiquetas: `abstract | introduction | methods | results | discussion | conclusion | other`.
- `build_chunk_records()` mantiene un mapa `ancestros: Dict[int, Tuple[str, str]]`. Al procesar un heading nivel L: actualiza el mapa y elimina niveles > L; busca el canonical más cercano subiendo de L a 1 que no sea `"other"`.
- Subsecciones descriptivas (p. ej. "Reactor operation", "Microbial community analysis") heredan el canonical del heading padre (methods/results).
- Chunks de tabla (`type=="table"`): `section_canonical = "table"` fijo.

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

El `other` residual (38.5%) es cola larga de títulos descriptivos no-IMRaD — residuo legítimo.

---

### ✅ 29. Página de actividad (completado 2026-06-05)

`scripts/streamlit_app/pages/9_Actividad.py` — página solo para la app privada:
- Sección 1: uso RAG mes actual (`rag_usage_YYYY-MM.jsonl`) — métricas + tabla modelos de pago.
- Sección 2: últimas 20 consultas RAG (`rag_queries_YYYY-MM.jsonl`) en orden inverso.
- Sección 3: corpus por método de ingesta (source_type) leído de `papers_metadata.jsonl` por categoría.
- Sección 4: errores `[ERROR]` de los 5 logs más recientes en `research_agent/logs/`.
- Guard `is_public_app()` → `st.stop()` directo; app privada requiere `check_password("PRIVATE_APP_PASSWORD")`.
- Botón "🔄 Actualizar" + manejo de excepciones por sección.

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
- **Logging a fichero**: `FileHandler` en `PROJECT_DIR/logs/run_weekly_scopus_YYYY-MM-DD.log` + `StreamHandler` (stdout). Guard `if not log.handlers` para evitar duplicados.

`deployment/com.research_agent.scopus_weekly.plist` — LaunchAgent:
- `StartCalendarInterval`: lunes a las 06:00 (Weekday=1, Hour=6).
- `RunAtLoad: false` — solo se lanza los lunes, no al instalar.
- Logs en `~/Library/Logs/research_agent/scopus_weekly.{log,err.log}`.

---

### ✅ 10. Instancia RAG pública (puerto 8502) (completado 2026-06-05)

Segunda instancia Streamlit con páginas RAG + Revisión bibliográfica, sin ingesta
ni configuración, limitada a Ollama. `app_public.py` con `st.navigation`, autenticación
por `check_password("PUBLIC_APP_PASSWORD")` e `is_public_app()` para filtrar providers.
Segundo plist launchd en `deployment/com.research_agent.streamlit_public.plist`.

---

### ✅ 26. Health checks extendidos (completado 2026-05-27)

`app.py` — segunda fila de columnas bajo NAS/Ollama/GROBID:
- **Espacio libre NAS**: `shutil.disk_usage(NAS_ROOT)` → libre / total en GB; aviso si < 10 GB.
- **bge-m3 disponible**: GET `{OLLAMA_HOST}/api/tags` → busca "bge-m3" en nombres de modelos.
- **Permisos escritura NAS**: `os.access(CATEGORIAS_DIR, os.W_OK)`.
- **Latencia**: `check_ollama()` y `check_grobid()` miden tiempo de respuesta con `time.time()`.

---

### ✅ Selector de categorías activas (completado 2026-06-01)

`config/active_categories.yml` — nuevo fichero YAML con lista `active:` de categorías habilitadas. Las categorías inactivas no se incluyen en búsquedas Scopus, RAG ni Pendientes.

`app_utils.py` — tres nuevas funciones: `load_active_categories()` (lee el YAML, fallback a `CANONICAL_CATEGORIES`), `save_active_categories(active)` (escribe con backup `.bak` via `save_yaml()`), `is_category_active(category)`. Constante `ACTIVE_CATEGORIES_FILE`.

`6_Mantenimiento.py` — nueva **Sección 1 — Categorías activas** (expander expandido por defecto): `st.multiselect` sobre `CANONICAL_CATEGORIES`, caption explicativo, botón guardar con aviso si selección vacía. Secciones anteriores renumeradas 2–6.

`app.py` — filas de categorías inactivas en gris con `df.style.apply(_style_inactive, axis=1)`.

`pipeline.run_scopus()` — filtra `target_cats` contra la lista activa antes del bucle de descarga/procesado.

---

### ✅ 25. corpus_manifest.json (completado 2026-06-01)

`scripts/utils/corpus_manifest.py` — nuevo módulo con:
- `build_manifest(category, base)` — dict con 11 campos: `category`, `generated_at`, `n_pdfs`, `n_md_clean`, `n_chunks`, `n_papers_metadata`, `avg_quality_score`, `faiss_indexes`, `keywords_hash`, `git_commit`, `faiss_stale`.
- `write_manifest(category, base)` → escribe `categorias/<cat>/corpus_manifest.json`, devuelve ruta.
- `read_manifest(category, base)` → lee JSON o devuelve `{}`.
- CLI: `python3 corpus_manifest.py --project <cat> [--base DIR]`.

`app_utils.get_corpus_manifest(category)` — wrapper con `try/except` para uso desde Streamlit.

---

### ✅ 19. Detección avanzada de duplicados (completado 2026-06-01)

`9_cleanup_duplicates.py` ampliado con dos nuevos detectores (sin tocar la lógica DOI existente):

- `normalize_title(title)` — lowercase, strip puntuación, colapsa espacios.
- `pdf_sha256(pdf_path)` — hash SHA-256 del binario PDF.
- `detect_title_duplicates(cats, base)` — agrupa por título normalizado (≥10 chars), devuelve grupos con ≥2 papers.
- `detect_hash_duplicates(cats, base)` — agrupa PDFs por hash SHA-256, devuelve grupos con ≥2 ficheros.
- `write_duplicate_report(decisions_doi, title_dups, hash_dups, out_path)` — genera `metadatos/duplicate_report.xlsx` con tres hojas: **DOI**, **Titulo** y **Hash**.

---

### ✅ 5. Botón renombrado por DOI en tab Pendientes (completado 2026-05-31)

Permite renombrar PDFs copiados directamente a `categorias/<cat>/pdfs/` sin pasar por inbox.
Compara stems de PDFs contra md_clean con `_norm` y salta PDFs ya procesados.

---

### ✅ 7. README.md global + docstrings (completo 2026-05-29)

Documentación final del proyecto: README de primer nivel con visión general,
y docstrings en los scripts numerados que aún no los tienen.
Docstrings completos añadidos a los 12 scripts numerados (0–9 + 3a + 3b): nivel completo con parámetros CLI, ficheros leídos/escritos y dependencias.

---

### ✅ 13. Validar API keys con llamada real (resuelto 2026-05-29)

`check_anthropic_api()` y `check_openai_api()` hacen GET `/v1/models`; devuelven `(False, "Key inválida o revocada (401)")` si la key está revocada, `(False, "Timeout (5s)")` si no hay red.

---

### ✅ 18. Cuarentena reversible para duplicados (completado 2026-06-11)

La página Duplicados (`10_Duplicados.py`) implementa cuarentena REVERSIBLE para duplicados:
mueve PDF + artefactos a `/Volumes/research/quarantine/duplicates/<ts>/` con `_manifest`
y quita la línea de `papers_metadata.jsonl` (con `.bak`) vía `quarantine_paper()` en
`9_cleanup_duplicates.py`. Extensión al resto de casos dudosos: PENDIENTE (ver Mejoras_pendientes.md).

---

### ✅ 24. Catálogo Artículos + export CSV (completado 2026-06-11)

La página Artículos (`11_Articulos.py`, privada+pública) ofrece el catálogo bibliográfico
filtrable (texto/año/revista/DOI) con resumen por categoría y **export CSV** de la vista
filtrada — equivale al `index.xlsx`/tabla de datos del paquete. Junto con el ZIP de papers
+ BibTeX (items 10/11/22/23) cubre la mayor parte de la colección por tema.
Pendiente: solo el `index.xlsx` tabulado con datos completos (ver Mejoras_pendientes.md item 24).

---

### ✅ 23. Exportar BibTeX/RIS (completado 2026-05-28)

A partir de metadata y DOI, generar `selected_papers.bib` / `.ris` / `.csv`
para integración con Zotero y escritura de artículos y tesis.

---

### ✅ 22. Modo revisión bibliográfica (completado 2026-05-28)

Nueva página Streamlit `📚 Revisión bibliográfica` con prompts especializados:
estado del arte, tabla de artículos clave, lagunas de conocimiento, comparativa
de mecanismos, introducción preliminar.

Entradas: categoría, rango de años, keywords de enfoque, modelo de síntesis.
Salidas: Markdown, Word, ZIP con papers utilizados, BibTeX.

---

### ✅ 21. Guardar respuesta RAG como nota (completado 2026-05-28)

Botón en `2_RAG.py` tras consulta: "Guardar como nota Markdown".
Ruta: `/Volumes/research/notas_rag/<categoria>/YYYY-MM-DD_<categoria>_<slug>.md`

---

### ✅ 20. Log completo de consultas RAG (completado 2026-05-28)

Registro ampliado en `rag_usage/` con la pregunta, papers recuperados y respuesta generada.
Ruta: `/Volumes/research/metadatos/rag_queries/rag_queries_YYYY-MM.jsonl`
Permite reproducir respuestas usadas en proyectos o artículos.

---

### ✅ 17. Panel de calidad del corpus + quality_score (completado 2026-05-28)

**Panel (portada — expander "Calidad del corpus"):** métricas por categoría:
% PDFs con DOI, con título, con año, con resumen, con referencias, duplicados, con warnings.

**`quality_score` en metadata** (calcular en `4_extract_metadata.py`):
```json
{
  "quality_score": 0.86,
  "warnings": ["no_references_extracted", "short_md_clean", "missing_doi"]
}
```

---

### ✅ 15. Registro de DOI pendientes de descarga (completado 2026-05-28)

`/Volumes/research/metadatos/pendientes_descarga.csv`
Campos: `doi`, `title`, `year`, `category`, `landing_url`, `status`, `reason`, `last_checked`, `notes`
Estados: `pending | downloaded | manual | blocked | no_pdf_found | duplicate | wrong_document`

---

### ✅ 13b. Actualizar DEFAULT_MODEL en 5_build_embeddings.py (resuelto 2026-05-28)

`5_build_embeddings.py` — añadido `import sys`, path guard y
`from utils.constants import OLLAMA_MODEL_EMBED`. `DEFAULT_MODEL = OLLAMA_MODEL_EMBED`.
Ahora lanzar el script directamente por CLI sin `--model` usa bge-m3 por defecto.

---

### ✅ 11. Exportar papers desde RAG (completado 2026-05-28)

Tras consulta RAG, botón "Exportar papers relacionados" que genera ZIP descargable
con PDFs + md_clean (+ opcional summaries) de los `paper_id`s recuperados.
Implementado con `zipfile` en memoria + `st.download_button` en `2_RAG.py`.

---

### ✅ 6. Actualizar precios en app_utils.py (completado 2026-05-27)

`LLM_PRICING` verificado a 2026-05-27. Único cambio:
`claude-opus-4-7`: $15/$75 → **$5/$25** (precio del Opus 4.7, no del antiguo Opus 4.1).
Fuentes: platform.claude.com/docs · developers.openai.com/api/docs/pricing

---

### ✅ 12. Validar nombre proyecto en run_adhoc() (completado 2026-05-27)

`pipeline.py` — `run_adhoc()`, justo antes de `check_nas()`:
```python
if not re.fullmatch(r'^[a-z0-9_-]+$', name):
    raise ValueError(f"Nombre de proyecto inválido '{name}': solo minúsculas, dígitos, '_' y '-'")
```

---

### ✅ 16. Normalización estable de paper_id (completado 2026-05-26, verificado 2026-05-27)

`stable_id` añadido a metadata (ver item 14). `paper_id` NO cambiado — sigue siendo el
stem del fichero TEI y es la clave de todos los artefactos (md_clean, chunks, embeddings).
`stable_id = _doi_slug(doi)` cuando hay DOI, else `paper_id`. Permite enlazar el mismo
paper procesado con distintos nombres de fichero a lo largo del tiempo.
Verificado en producción 2026-05-27. Página 6_Mantenimiento.py incluye sección "Backfill metadata"
que detecta y rellena papers sin `stable_id`.

---

### ✅ 14. Registro de procedencia de PDFs (completado 2026-05-26, verificado 2026-05-27)

`4_extract_metadata.py` — campos añadidos a cada registro de `papers_metadata.jsonl`:
- `stable_id` — slug DOI si hay DOI, else `paper_id` (item 16)
- `processed_date` — `date.today().isoformat()` en el momento de procesar
- `source_type` — arg `--source-type` o auto-detect (`adhoc` si project starts with "adhoc")
- `download_source` — mapeado desde `descarga_cache.json["method"]` por DOI
- `download_url` — `pdf_url` del cache entry
- `access_type` — `open_access` / `institutional` / `unknown` según método
- `download_date` — `cached_at[:10]` del cache entry

---

### ✅ 1. Mejorar el editor de keywords en la web (completado 2026-05-25)

Implementada **Opción B — textarea por categoría**: un `st.text_area` por categoría, una keyword por línea. Sin dependencias extra. Botón "Guardar todo" arriba y abajo, backup `.bak` automático, badge de delta (+N/-N) en el expander de resumen.

---

### ✅ 2. Optimizar paquetes NotebookLM para uso con GPTs custom (completado 2026-05-25)

Implementado en `6_make_packages.py`:
- **Cabecera de corpus** al inicio del FULLTEXT: categoría, nº papers, periodo (año min-max), fecha, primeras 6 keywords de `keywords.yml`
- **Estructura por paper**: `# Paper: <id>` / DOI / Año / **Resumen** / `---` / **Texto completo**
- Año extraído de metadata JSONL o parseado del paper_id con regex `(19\d{2}|20[0-3]\d)`

---

### ✅ 3. Integrar proyecto ad-hoc en categoría canónica (completado 2026-05-25)

Implementado en `pipeline.integrate_adhoc()` + `pipeline.promote_adhoc_to_category()` + sección **🔗 Integrar proyecto ad-hoc** en `1_Ingestar.py` (tab Ad-hoc):

**`integrate_adhoc(adhoc, target, delete_source)`** — merge en categoría existente:
- Copia pdfs/, md_clean/, summaries/, chunks/, metadata/ con skip por fichero existente (`_copy_files_skip_existing()`)
- Re-indexa solo FAISS del target (`5_build_embeddings.py --project <target>`)
- Checkbox "Borrar ad-hoc tras integración" → `shutil.rmtree` si marcado

**`promote_adhoc_to_category(adhoc, new_name, keywords, delete_source)`** — nueva categoría:
- Copia también embeddings/ (FAISS ya no necesita re-indexarse)
- Registra keywords en `config/keywords.yml` (con backup `.bak`)
- Valida nombre (`^[a-z0-9_]+$`) y que la categoría no exista previamente

---

### ✅ 8. Decisión final nomic vs bge-m3 (completado 2026-05-25)

bge-m3 adoptado como modelo de producción. `utils/constants.py` centraliza el valor; `app_utils.py` y `8_query_rag.py` importan de ahí. Los índices nomic se conservan en el NAS pero no son el default.

---

### ✅ 9. Fix integrate_adhoc() y run_adhoc() — renombrado antes de procesar (resuelto 2026-05-27)

Ver sección "Verificaciones completadas" — Bug #1 y #2.
