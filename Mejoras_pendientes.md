# Mejoras pendientes — research_agent
> Backlog vivo. Histórico de lo hecho: Mejoras_realizadas.md · Estado/arquitectura: ESTADO.md

## Orden de prioridad (revisión 2026-06-13)
1. ~~`detect_affected_categories` con `normalize_stem`~~ — ✅ **COMPLETADO 2026-06-13** (incluido en puerta de dedup por DOI).
2. Item 37 — golden Q&A.
3. Item 36 — idempotencia.
4. ~~Item 44 — fix `_clean_doi` (recorta sufijos DOI de 3+ letras)~~ — ✅ **CERRADO 2026-06-13**. Verificado en pciq22: DOIs con `:` y barra final se normalizan; `10.1023/B:HYDR.0000008620.87704.3b` se preserva; 53 tests pasan.
5. Item 45 — consolidar utilidades de texto duplicadas pdf_utils↔1_rename. **Nota 2026-06-13:** el trabajo de hoy sobre DOIs tocó ambos ficheros (`normalize_doi`, `normalize_stem`, lookups por stem/título en `doi_manual`). Revisar si introdujo nueva divergencia antes de consolidar.
6. ~~Item 41 — índice viejo all__bge-m3.~~ ✅ COMPLETADO 2026-06-16.
7. Item 35 — OCR (si hay escaneados). Item 31 — MVP libros, tras el 37.
- ~~Timeout job semanal: subir `SCOPUS_TIMEOUT` de 2700 a 5400 (45→90 min)~~ — ✅ **COMPLETADO 2026-06-15** — `run_weekly_scopus.py`: `SCOPUS_TIMEOUT = 5400`; `WEEKLY_CATEGORIES` ampliada con `anoxic_biogas_biodesulfurization`.

## Hallazgos pendientes (revisión 2026-06-12)
- ~~`detect_affected_categories` compara stems por igualdad exacta sin `_norm` → riesgo de reproceso
  por puntuación/guiones.~~ ✅ RESUELTO 2026-06-13.
- **Caso Kisand 2003 (`anoxic`):** DOI `10.1023/B:HYDR.0000008620.87704.3b` quedó reprocesado tras renombrado manual. Verificar que el DOI esté presente en su registro de `papers_metadata.jsonl`; si no, añadirlo vía `doi_manual.xlsx` desde el editor de Artículos.
- ~~`run_scopus` aplica el filtro de activas también a categorías pedidas explícitamente (descarte
  silencioso).~~ ✅ RESUELTO 2026-06-17 — el bloque de filtro en `run_scopus` (`pipeline.py` ~línea 734) ahora se envuelve en `if not categories:`; una petición explícita (CLI/web) tiene prioridad sobre `active_categories.yml`.
- ~~`promote_adhoc_to_category` usa `sort_keys=True` → reordena todo keywords.yml en cada promoción.~~
  ✅ RESUELTO 2026-06-17 — cambiado a `sort_keys=False` en `scripts/pipeline.py`; keywords.yml ya no se reordena en cada promoción.
- **DECISIÓN DOCUMENTADA 2026-06-17 — Filtro de año descarta papers con `year=None` en silencio (`retrieval.py`):**
  `passes_filters()` (líneas 76-80) resuelve `year` desde metadata o `year_from_paper_id`; si sigue siendo `None` y hay filtro de año activo, el chunk no pasa. Comportamiento conocido y aceptado: cuando el usuario pide filtrar por año, excluir papers sin año es lo correcto. No es un bug.
- ~~`section_canonical`: `CANONICAL_SECTIONS` (constants) y `canonical_section()` (3_process) se
  sincronizan a mano → riesgo de drift.~~ ✅ VERIFICADO/RESUELTO 2026-06-17 — no habían divergido: 6 patrones en `_CANON_PATTERNS` + fallback `"other"` + `"table"` asignado en `build_chunk_records` = las 8 etiquetas de `CANONICAL_SECTIONS`. Blindado con `tests/test_canonical_sections.py`.

### Verificaciones pendientes (ficheros no vistos) → item 43.

## Keywords y criterios de búsqueda

Revisar y afinar:
- `config/keywords.yml` — para cribado de PDFs sueltos (flujo inbox)
- `config/scopus_queries.yml` — para búsquedas Scopus directas (flujo scopus)

Categorías con pocas queries actuales (ampliar si hace falta):
- `anoxic_biogas_biodesulfurization` — solo 1 query (12 resultados). **2026-06-15:** anoxic ya está en el cron semanal con esta query. Decisión: no afinar — volumen bajo, falsos positivos de limnología/sedimentos se descartan manualmente.
- `bioleaching_critical_materials` — solo 1 query (39 resultados)

---

## Próximos pasos — items pendientes

### 5. Pequeñas mejoras UX en la web (baja prioridad)

✅ Botón renombrado por DOI en tab Pendientes (2026-05-31) — detalle en Mejoras_realizadas.md.

- **Toggle síntesis OFF**: mostrar aviso visible en el área principal cuando la síntesis está desactivada.
- **Botones por fila en portada**: acción "Procesar pendientes" directa por categoría en la tabla principal.
- **Página de logs en vivo**: `tail -f` de `~/Library/Logs/research_agent/*.log` directamente en la web.
- **Editor doi_manual.xlsx** con `st.data_editor` — actualmente solo visor.

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

## Nuevas mejoras — items pendientes

### 18. Carpeta de cuarentena — MEDIA prioridad (parcialmente cubierto)

Crear `/Volumes/research/quarantine/` para documentos dudosos:
PDF sin texto extraíble, muy corto, sin DOI ni título fiable, material
suplementario, duplicado dudoso.

Desde Streamlit: aceptar / rechazar / mover a categoría / borrar.

✅ Cuarentena REVERSIBLE para duplicados vía `10_Duplicados.py`/`quarantine_paper()` (2026-06-11) — detalle en Mejoras_realizadas.md.

✅ **Restauración REAL desde la UI (2026-06-17):** `restore_from_quarantine()` en `9_cleanup_duplicates.py` + sección "♻️ Restaurar de cuarentena" en `10_Duplicados.py`. Cuarentenas nuevas incluyen `meta_lines` en el manifiesto → la metadata se reinerta automáticamente al restaurar (dedup por `file_key`, backup `.bak`). Manifiestos legacy sin `meta_lines` → warning + regeneración manual con `4_extract_metadata.py`. **Pendiente: validar round-trip `✓ meta` con paper de juguete.**

Pendiente: extender la cuarentena al resto de casos dudosos (PDF sin texto, muy corto,
sin DOI/título fiable, material suplementario) y el OCR del item 35.

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
Parcialmente completado por items 10+11+22+23, salvo que quiera un excel con los datos tabulados.

✅ Catálogo Artículos + export CSV en `11_Articulos.py`; items 10/11/22/23 cubiertos (2026-06-11) — detalle en Mejoras_realizadas.md.

---

## Mejoras de calidad RAG y robustez (2026-06-10) — items pendientes

Propuestas derivadas de la revisión del pipeline. Ordenadas por impacto: 32–34
suben la calidad de recuperación (lo que más determina si el RAG es útil); 35–36
refuerzan la robustez del procesado; 37–39 son evaluación, coste y mantenimiento.

### 33. Recuperación híbrida (denso + BM25) + reranking — ALTA prioridad

✅ v1 (denso+BM25+RRF) completado 2026-06-11 — detalle en Mejoras_realizadas.md.

Pendiente (fase 2): reranking opcional sobre el top-N fusionado con `bge-reranker` (vía Ollama) o
un cross-encoder pequeño, antes de pasar al LLM de síntesis.
- Tocar `8_query_rag.py` y la capa de retrieval de `2_RAG.py` / `7_Revision.py`.
- Toggle en la web para activar/desactivar reranking y comparar.
- Evidencia inicial (2 categorías): híbrido ≤ denso; revisar fusión/pesado BM25+RRF al abordar el reranking.
Ligado al item 37 — sin set de evaluación no se puede medir, y el soporte de rerank en Ollama es dudoso.

### 35. Fallback OCR para PDFs escaneados — MEDIA prioridad

GROBID no extrae nada de un PDF que es imagen → entra vacío al índice.

- Detectar "texto extraído ≈ 0 caracteres" tras `3_process_corpus.py` y disparar OCR.
- `ocrmypdf` (Tesseract) genera un PDF con capa de texto; reintentar GROBID sobre él.
- Idiomas: `eng` (corpus mayoritariamente en inglés).
- Encaja con la carpeta de cuarentena (item 18): si tras OCR sigue vacío → cuarentena.

### ~~36~~. ✅ (36-A completado 2026-06-20) Idempotencia y reanudación por documento — MEDIA prioridad

Estado explícito por PDF (descargado → renombrado → extraído → resumido → indexado)
para que un fallo a mitad no obligue a reprocesar todo ni deje entradas a medias.

- Registro de estado por `paper_id`/`stable_id` (JSON o columna en manifest).
- Complementa el indexado incremental de FAISS (item FAISS incremental, 2026-06-04)
  y el skip logic existente, dándole trazabilidad y reanudación explícita.
- Útil tras timeouts del job semanal o caídas de VPN a mitad de ingesta.
- 36-A completado 2026-06-20: visibilidad por paper en pestaña Pendientes (opción ligera, sin fichero persistente).

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
- ✅ `anoxic_biogas_biodesulfurization` completado 2026-06-20 (4 preguntas, 16 paper_ids). Pendiente: resto de categorías.
- ✅ `run_eval.py` creado y validado (2026-06-20) — CLI, Hit@k + MRR. Resultado inicial anoxic: Hit@8 denso 0.50, híbrido 0.25 (a vigilar).
- Nuevo subitem pendiente: integrar `run_eval.py` en Streamlit (botón + tabla resultados) — prioridad baja, esperar a tener 2-3 categorías más con golden set antes de invertir en la UI.
- ✅ `biogas_upgrading_biomethanation` completado 2026-06-20 (6 preguntas, vía `pool_candidates.py`). Denso Hit@8 1.0/MRR 0.889; híbrido 1.0/0.857.
- Patrón en 2 categorías: híbrido ≤ denso → antes de retunear RRF/reranking (item 33 fase 2), ampliar a más categorías.
- Housekeeping menor (baja prioridad): el golden de anoxic (manual, previo a `pool_candidates.py`) no tiene `questions_`/`review_`; para regenerarlo por pooling habría que extraer antes sus preguntas a `questions_anoxic_biogas_biodesulfurization.json`.

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

### ~~41. Limpiar el índice viejo all__bge-m3~~ — ✅ COMPLETADO (ejecutado 2026-06-16, documentado 2026-06-17)

~~Fase divergente sin `section_canonical`/`year` en sus chunks. Borrar o re-indexar para
que no compita con el índice canónico al vuelo (items 32/34).~~

Fases `all__bge-m3` de 6 categorías movidas a cuarentena el 16/06/2026:
`microalgae`, `advanced_oxidation_processes`, `anoxic_biogas_biodesulfurization`,
`biogas_upgrading_biomethanation`, `bioleaching_critical_materials`, `bioplastics_microplastics`.
Ruta: `quarantine/old_indexes/20260616_011551/<cat>/all__bge-m3/`. ~8,2 MB, reversibles.
Índice canónico vivo de cada categoría: `embeddings/all/index.faiss` (items 32/34).

### ~~44. `_clean_doi` recorta sufijos DOI legítimos~~ — COMPLETADO 2026-06-13

~~El paso general `re.sub(r'[a-zA-Z]{3,}$','')` en `utils/pdf_utils._clean_doi` elimina cualquier cola
de 3+ letras, incluido un sufijo válido (`10.1000/xyz` → `10.1000/`).~~
Corregido con `(?<=\d)[a-zA-Z]{3,}$` — solo recorta alfa-texto pegado a un dígito. Test xfail eliminado.

### ~~45. Utilidades de texto duplicadas y divergentes (pdf_utils ↔ 1_rename)~~ — ✅ COMPLETADO 2026-06-17

Fuente única en `utils/pdf_utils.py`. Las dos divergencias portadas desde `1_rename` (versiones correctas):
- `shorten_title`: `re.sub(r"[^a-z0-9\s\-]"…)` → `re.sub(r"[^a-z0-9\s]"…)` (quitar `\-`).
- `sanitize_filename`: añadido `re.sub(r"\s+", "_", name)` tras el paso de chars inválidos.
`1_rename_papers_by_doi.py` ahora importa `slugify`, `shorten_title`, `sanitize_filename` desde `pdf_utils`; defs locales y banner `# UTILIDADES DE TEXTO` eliminados. Sin cambio de comportamiento en el renombrador. `test_rename.py` repuntado a `utils.pdf_utils`. Suite: 99/99 passed.

### 43. Verificaciones pendientes de la revisión 2026-06-12 — seguimiento
3_process_corpus.py (canonical_section vs CANONICAL_SECTIONS), ~~1_rename_papers_by_doi.py (nombre
largo Scopus en descarga)~~ ✅ CUBIERTO 2026-06-13 (renombrado por DOI antes de reprocesar en Coherencia PDF/MD + tab Pendientes), 4_extract_metadata.py (_norm vs 6_Mantenimiento), 5_build_embeddings.py
(ausencia de papers_metadata.jsonl, clave MVP libros), 8_query_rag.py/2_RAG/7_Revision (cableado
passes_filters). Más: detect_affected_categories con _norm ✅; filtro de activas en run_scopus para
categorías explícitas; sort_keys=True en promote_adhoc_to_category.

### 46. Borrar modelos Ollama obsoletos en pciq22 — BAJA prioridad

Tras validar `qwen2.5:14b-instruct` como único modelo de síntesis local
(formato de citas correcto + síntesis en español sin alucinar), retirados del
selector `gemma3:4b`, `qwen3:8b` y `qwen3:14b`. Siguen ocupando ~18 GB en disco.

Cuando se confirme en uso real que `qwen2.5:14b-instruct` cubre todos los casos
(unos días de uso), liberar espacio en pciq22:

    ollama rm gemma3:4b qwen3:8b qwen3:14b

Ejecución pura de datos (no toca código). Reversible con `ollama pull` si hiciera
falta. Actualizar entonces la lista de "Required Ollama models" en ESTADO.md.
