# Mejoras pendientes — research_agent
> Backlog vivo. Histórico de lo hecho: Mejoras_realizadas.md · Estado/arquitectura: ESTADO.md

## Orden de prioridad (revisión 2026-06-25)
1. ~~`detect_affected_categories` con `normalize_stem`~~ — ✅ **COMPLETADO 2026-06-13** (incluido en puerta de dedup por DOI).
2. Item 37 — golden Q&A.
3. Item 36 — idempotencia.
4. ~~Item 44 — fix `_clean_doi` (recorta sufijos DOI de 3+ letras)~~ — ✅ **CERRADO 2026-06-13**. Verificado en pciq22: DOIs con `:` y barra final se normalizan; `10.1023/B:HYDR.0000008620.87704.3b` se preserva; 53 tests pasan.
5. Item 45 — consolidar utilidades de texto duplicadas pdf_utils↔1_rename. **Nota 2026-06-13:** el trabajo de hoy sobre DOIs tocó ambos ficheros (`normalize_doi`, `normalize_stem`, lookups por stem/título en `doi_manual`). Revisar si introdujo nueva divergencia antes de consolidar.
6. ~~Item 41 — índice viejo all__bge-m3.~~ ✅ COMPLETADO 2026-06-16.
7. Item 35 — OCR (si hay escaneados). Item 31 — MVP libros, tras el 37.
- ~~Item 49 — completar Hermes Agent (Discord + MCPs)~~ — ✅ **MAYORMENTE COMPLETADO 2026-06-25** (operativo 24/7 con Notion/Calendar/Gmail/Tavily; residuales: override modelo local para Gmail y aplicar plist ingesta 04:00 en pciq22).
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

- ~~Exportar chunks/contexto recuperados en RAG a un formato citable por un LLM externo.~~
  ✅ COMPLETADO 2026-07-04 — botón "⬇️ Descargar chunks (Markdown)" en `2_RAG.py`
  (`build_chunks_markdown` en `utils/export_refs.py`), independiente del ZIP PDF+MD.

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

### 48. RAG: chat multi-búsqueda / dossier editable (Fase 2) — MEDIA prioridad

La Fase 1 del chat con memoria (`2026-06-23`) ata el hilo a la **última búsqueda**
(`_last_results`). La Fase 2 debería permitir:
- Acumular papers de varias búsquedas en un "dossier" editable por el usuario.
- Elegir explícitamente qué papers/chunks entran en el contexto del chat (incluir/excluir).
- Persistir el dossier más allá de la sesión (JSON en `metadatos/rag_sessions/` o similar).
- Continuar un hilo anterior o empezar varios hilos por proyecto.

Motivo: evitar reenviar todos los chunks de una búsqueda amplia y dar control al
usuario sobre el contexto, reduciendo coste y alucinaciones.

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

- **Nota 2026-07-03 (antes de retunear):** el patrón "híbrido ≤ denso" está a
  n=4/n=6 → **sin potencia estadística** para concluir; el item 37 (~25 preguntas)
  es prerrequisito duro. Sobre el pooling: `pool_candidates.py` ya agrupa
  `union(denso, rrf(denso,bm25))`, pero un doc que SOLO encuentra BM25 puede quedar
  fuera (pasa por el filtro RRF antes de agruparse) → ~~añadir `bm25_rank` puro a la
  unión para que el experto también los juzgue y el golden no infravalore al híbrido.~~
  ✅ hecho 2026-07-03 (columna `b{pos}` en `pool_candidates.py`).
  Antes de tocar reranking: (1) revisar la tokenización BM25 de acrónimos/fórmulas
  (H2S, TiO2, NR-SOB) en `utils/retrieval.py`; (2) fusión ponderada a nivel de score
  (α·denso+(1-α)·bm25) o RRF con k bajo (10-20) en vez de k=60 sobre pools diminutos.

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
- **DECISIÓN 2026-07-03 — alcance y método de la ampliación:**
  - Alcance reducido a **3 categorías**: `anoxic_biogas_biodesulfurization`,
    `biogas_upgrading_biomethanation`, `bioplastics_microplastics` (no las 8).
  - **Profundidad antes que amplitud:** llevar anoxic y upgrading a ~25 preguntas
    (tienen baseline denso/híbrido → desbloquean el item 33) antes de sembrar
    plásticos (greenfield, tercer punto de datos).
  - **Sin generador automático — preguntas redactadas a mano.** El flujo del
    2026-06-20 toma `questions_<cat>.json` ya escritas por el experto;
    `pool_candidates.py` NO las genera. Cierra la decisión Mixtral/Mistral:
    **descartada la generación local** — preguntas derivadas por un modelo desde
    los chunks sesgan el benchmark hacia lo recuperable. Un modelo local
    (qwen2.5:14b) solo como apoyo de brainstorming de subtemas, nunca como fuente
    de la pregunta/respuesta final.
  - **Sesgo de pooling y fusión → ver nota del item 33.** El pool de
    `pool_candidates.py` ya es `union(denso, rrf(denso,bm25))`, no denso-only;
    ~~lo pendiente es añadir BM25 puro a la unión para no infravalorar al híbrido.~~
    ✅ hecho 2026-07-03.
  - **Estratificar por arquetipo** (conceptual/paráfrasis, acrónimo/término raro,
    lookup numérico/tabla, multi-salto) para que el golden set diagnostique *en qué*
    ayuda el híbrido, no solo dé un número.
  - **Prerequisito anoxic:** extraer sus preguntas a
    `questions_anoxic_biogas_biodesulfurization.json` (hoy no existe; golden manual
    previo a pool_candidates) antes de poder ampliarlo por pooling. Ojo consistencia:
    su golden se anotó sin pooling (independiente); si se re-poolea, homogeneizar
    o dejar anoxic como está y ampliar solo upgrading + plásticos.

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

### 50. `_fmt_authors` duplicado — BAJA prioridad

`_fmt_authors` duplicado: réplica en `utils/export_refs.py` (`_fmt_authors_md`)
de la lógica de `11_Articulos.py`. Consolidar en un helper compartido (p. ej.
`utils/`) para evitar drift — misma clase que el cerrado item 45, pareja distinta.
BAJA prioridad (formateo cosmético de autores).

### 51. Validación de calidad de metadata — MEDIA prioridad

**Nivel 1 (heurísticas locales, sin red) ✅ COMPLETADO 2026-07-04** —
`scripts/validate_metadata.py` + `scripts/utils/metadata_validation.py`. Detecta
título==revista / prefijo de revista, autores pegados o con afiliación/dígitos,
año/DOI implausibles. Escribe sidecar `metadata/validation_<cat>.jsonl` (solo
lectura sobre `papers_metadata.jsonl`). Detalle en Mejoras_realizadas.md.

**Ajuste 2026-07-04:** `authors_glued` reclasificado a severidad `"info"` (no
cuenta para el sidecar). `forename`/`surname` vienen vacíos en TODO el corpus
(solo `full` pegado) → marcaba ~99% de papers. La **reparación de autores es
sistémica vía Crossref** (adopción en bloque para todos los papers con DOI en el
Nivel 2), NO triaje por-paper. Detalle en Mejoras_realizadas.md.

**Nivel 2 (Crossref por DOI) ✅ COMPLETADO 2026-07-04** — `scripts/utils/
crossref.py` (`fetch_work` works/<doi>) + `compare_with_crossref` /
`validate_category_crossref` en `metadata_validation.py`; flags `--crossref` /
`--limit` en el CLI; en `11_Articulos.py` (privada) filtro "⚠ Solo con
discrepancias" + adopción por campo + **botón de adopción masiva de autores**
(preview → confirmar → `update_metadata_fields`). Crossref SUGIERE, no
sobreescribe. `_crossref_journal` refactorizado para delegar en `fetch_work`
(no queda deuda de consolidación). Detalle en Mejoras_realizadas.md.

**Calibración pendiente (Bloque B, pciq22, run aparte tras push+pull):** correr
Nivel 1 en 1-2 categorías y afinar `AFFILIATION_TOKENS`; correr Nivel 2
(`--crossref [--limit N]`) sobre una categoría conocida, revisar volumen de
`title_recover`/`year_mismatch`/`journal_fill`, probar la adopción por campo y
la adopción masiva de autores en la web privada.

**Ajuste 2026-07-04 (año canónico):** tras datos reales (71/71 `year_mismatch`
contra paper_id, histograma `crossref−local` = {0:96, 1:20, −7:2, −9:1, −51:1}),
Crossref pasa a ser la fuente CANÓNICA del año y paper_id queda como fallback
(solo si Crossref no resuelve o no trae año); los ±1 (print/online) se marcan
`severity="low"`. Detalle en Mejoras_realizadas.md.

**~~Deferred — adopción masiva de AÑO (Crossref)~~ ✅ COMPLETADO 2026-07-04:**
botón de adopción masiva de año análogo al de autores (preview → confirmar →
`update_metadata_fields`) en la sección Crossref de `11_Articulos.py`, con año
canónico published-print (`_pick_year` en `utils/crossref.py`). Detalle en
Mejoras_realizadas.md.

### 43. Verificaciones pendientes de la revisión 2026-06-12 — seguimiento
3_process_corpus.py (canonical_section vs CANONICAL_SECTIONS), ~~1_rename_papers_by_doi.py (nombre
largo Scopus en descarga)~~ ✅ CUBIERTO 2026-06-13 (renombrado por DOI antes de reprocesar en Coherencia PDF/MD + tab Pendientes), 4_extract_metadata.py (_norm vs 6_Mantenimiento), 5_build_embeddings.py
(ausencia de papers_metadata.jsonl, clave MVP libros), 8_query_rag.py/2_RAG/7_Revision (cableado
passes_filters). Más: detect_affected_categories con _norm ✅; filtro de activas en run_scopus para
categorías explícitas; sort_keys=True en promote_adhoc_to_category.

### ~~46. Borrar modelos Ollama obsoletos en pciq22~~ — ✅ COMPLETADO 2026-06-26

Todos los modelos candidatos borrados. También se borró `qwen3:8b` (ya no es base
de Hermes — modelo local descartado) y `nomic-embed-text` (reemplazado por bge-m3).

Modelos activos en pciq22: `qwen2.5:14b-instruct` (RAG síntesis) + `bge-m3`
(embeddings). RAM liberada: ~19+ GB.

### 49. Hermes Agent — pendiente residual — BAJA prioridad

**Estado 2026-06-25:** infraestructura completa y operativa. Hermes funciona 24/7
desde Discord con Notion + Google Calendar + Gmail + Tavily, sobre OpenRouter
(`deepseek/deepseek-v4-flash`) como default. Detalles en `ESTADO.md` →
subsección "Hermes Agent (productividad personal)".

**🔴 Estado 2026-07-01 (cont.): PAUSADO por auditoría de seguridad** —
contenedor parado, token OAuth de Google revocado, autorización Notion
revocada, LaunchAgents nativos archivados. Detalle de hallazgos en
`Mejoras_realizadas.md` → sesión 2026-07-01 (cont.). Los residuales de más
abajo relacionados con arrancar/mantener el servicio (plist de ingesta,
archivar plists nativos, etc.) quedan **en pausa** mientras Hermes esté
parado — no son pendientes activos hasta la reactivación.

#### REACTIVACIÓN — requisitos obligatorios antes de volver a levantar Hermes

**No reactivar con la configuración actual.** Checklist mínimo:

- [ ] Re-autenticar Google con scopes MÍNIMOS: Gmail → `gmail.readonly` +
      `gmail.compose`; Calendar → `calendar.readonly` (o `calendar.events` si
      se quiere crear/editar). Editar los arrays `AUTH_SCOPES` de ambos
      paquetes MCP y **fijar versión** (instalación estable en `/opt/data`, no
      `npx -y` efímero que sobrescribe las ediciones — cierra también el
      pendiente ya existente del pin de versión de `@shinzolabs/gmail-mcp`,
      ver residual más abajo).
- [ ] Quitar el mount directo de `docker.sock`. Si se conserva terminal
      sandboxed (opción elegida antes de pausar): meter
      `docker-socket-proxy` (`tecnativa/docker-socket-proxy`) limitando la
      API Docker a create/start/stop, sin Privileged ni Binds arbitrarios.
- [ ] Endurecer el contenedor padre: `cap_drop`, `security_opt
      no-new-privileges`, `read_only` donde se pueda, y no montar `~/.hermes`
      entero en rw.
- [ ] `tools.include` explícito de solo-lectura para Calendar y Notion.

Histórico de completados:
- [x] Discord: bot, token, intents, invitación, gateway, **LaunchAgent 24/7**.
- [x] MCPs: Notion, Google Calendar, Gmail (instalados y validados desde Discord).
- [x] Web search: Tavily.
- [x] Keep-warm cron del modelo local.
- [x] Seguridad: terminal/code_execution/browser/computer_use desactivados.

Residuales:
- [ ] **Override Gmail con modelo local** — **Estado:** plan B (Rapid-MLX) **PROBADO y
      bloqueado por un bug de streaming de Rapid-MLX 0.9.7** (issues **#197/#344**,
      abiertos upstream). El modelo y el modo no-streaming OK (`tool_calls`
      estructurado por curl); Hermes fuerza streaming, NO configurable → recibe
      respuesta vacía. Diagnóstico completo en `Mejoras_realizadas.md` → sesión
      2026-06-28 (cont.).
  - **En espera del fix upstream:** suscrito a issues #197/#344 y a Releases del repo
    `raullenchai/Rapid-MLX`. **Día del fix:** `uv tool upgrade rapid-mlx` + reapuntar
    provider Hermes a `localhost:8000` + `bootstrap` del LaunchAgent
    `com.martin.rapidmlx`. Todo lo demás ya montado.
  - **Provider actual de Hermes:** OpenRouter (`google/gemini-3.5-flash`); Gmail
    funcional vía OpenRouter (validado). Matiz privacidad: correo sensible (datos de
    alumnado) pasa por OpenRouter — para esos casos esperar al tool-calling local.
  - **Sub-items futuros:** probar **GPT-OSS 20B** o **Qwen3-Coder** en Rapid-MLX
    (formato de tool-call distinto al XML de Qwen3.5; podría esquivar el bug de
    streaming).
- [~] *(en pausa mientras Hermes esté parado)* Archivar el plist
      `com.hermes.gateway.plist` (inerte) → `mv` a `~/.hermes/_plist_archive/`
      para que no arranque al login; gateway válido = `ai.hermes.gateway`.
- [ ] Evaluar pin de versión del MCP Homebrew `@shinzolabs/gmail-mcp` (autoupdate de
      Homebrew → riesgo de drift de esquema/nombres que rompa la whitelist).
- [ ] Migración config v30→31 pendiente (con backup, fuera de sesión).
- [ ] **Hardening SSH en pciq22** (`PasswordAuthentication no`) — aviso del security
      audit de Hermes; prioridad media si solo se accede por VPN.
- [~] *(en pausa mientras Hermes esté parado)* Ollama y GROBID se securizaron
      con autenticación Bearer real (2026-07-08, ver `ESTADO.md` y
      `Mejoras_realizadas.md`): Ollama ya no acepta conexiones directas de
      red, solo `127.0.0.1:11435` + proxy Caddy en `:11434` con token. Si la
      config de Hermes apuntaba a Ollama directo, al reactivarlo deberá
      apuntar a `http://host.docker.internal:11434` (Caddy, no el puerto
      loopback — un contenedor no lo alcanza) **con** cabecera
      `Authorization: Bearer <token>`.
- [~] *(en pausa mientras Hermes esté parado)* Aplicar plist ingesta 04:00 en
      pciq22 (commit en repo hecho; falta `git pull` + `cp deployment/... ~/Library/LaunchAgents/` +
      `launchctl bootout/bootstrap`).
- [~] *(en pausa mientras Hermes esté parado)* Archivar `ai.hermes.gateway.plist`
      y `com.hermes.gateway.plist` (LaunchAgents nativos, inertes tras la
      migración a Docker 2026-07-01) — verificar primero con `launchctl list |
      grep hermes` que no sigan activos (riesgo de doble-gateway compitiendo
      por `~/.hermes`). Nota: ya archivados a `.disabled` como parte de las
      acciones de pausa del 2026-07-01 (cont.); pendiente verificación formal
      con `launchctl list`.
- [ ] Diagnosticar cuelgue sin error de `qwen3:14b-hermes` en Docker con
      tool-calling (`get_current_time`, "qué día es hoy") — patrón distinto al
      error explícito ya documentado arriba (`tool_call requires a name
      argument`). Reproducir con `docker compose logs -f` + doble curl directo
      a Ollama desde dentro del contenedor para descartar la capa de red.

**Progreso 2026-06-26:** modelo local descartado, Gemini 2.5 Flash como default,
limpieza Ollama completa. Solo queda el plist de la ingesta como residual real.

**Progreso 2026-06-27/28:** reabierto el override local con `qwen3:14b`. Saneados
Modelfile (thinking), whitelist Gmail (7 tools), SOUL.md, `context_length`/`num_ctx`
(64000) y doble-gateway. **Diagnóstico cerrado:** el tool-calling local de Gmail
falla en la ruta Hermes→`/v1` de Ollama (envoltorio deferred-tools); modelo y Ollama
exonerados por eliminación (curl `/api/chat` OK, curl `/v1` con tool mínima OK,
prompt 3.400 vs 14.300 falla igual, `tool_use_enforcement: none` no ayuda). → Plan B:
Rapid-MLX como backend alternativo. Detalle en `Mejoras_realizadas.md` → sesión
2026-06-27/28.

**Progreso 2026-06-28 (cont.):** plan B (Rapid-MLX 0.9.7 + `Qwen3.5-9B-4bit`,
puerto 8000, LaunchAgent `com.martin.rapidmlx`) PROBADO: tool-calling en no-streaming
OK (curl), funcionó una vez end-to-end. BLOQUEADO por bug de streaming de Rapid-MLX
(issues #197/#344, abiertos): en streaming no promociona la tool-call a estructurado
y Hermes —que fuerza streaming sin opción— recibe respuesta vacía. Vuelta a OpenRouter
(`google/gemini-3.5-flash`); Rapid-MLX queda instalado a la espera del fix upstream.
Incidente: `config.yaml` erosionado por ediciones `sed` (perdido `mcp_servers`),
restaurado desde backup. Detalle en `Mejoras_realizadas.md` → sesión 2026-06-28 (cont.).

**Progreso 2026-07-01:** migración completa de LaunchAgent nativo a **Docker
Compose** (imagen oficial `nousresearch/hermes-agent`, `~/.hermes` montado como
`/opt/data`). Terminal activado con sandbox `backend: docker` (contenedor hermano,
scope verificado a `~/hermes_workspace` + `~/.hermes/cache/documents`). Config
saneada (YAML roto, `custom_providers` dict→lista, wrapper Gmail no portable →
`npx` directo, rutas Gmail/Calendar → `/opt/data`). Google Calendar: token fijado a
`/opt/data/google-calendar-tokens.json`; re-auth OAuth vía Docker no funciona,
hecha nativamente en el host. `ollama-local` accesible vía
`host.docker.internal:11434`. Verificado Gmail/Notion/Calendar operativos desde
Discord. Nueva incidencia sin cerrar: cuelgue silencioso de `qwen3:14b-hermes` con
tool-calling en Docker (distinto del error ya documentado). Detalle en
`Mejoras_realizadas.md` → sesión 2026-07-01 (fuera de este repo: `~/.hermes` +
`~/hermes-docker`).

---

## Agente Obsidian — `tools/obsidian.py` + `scripts/agent_chat.py` (2026-07-09)

Base ya completada (garantía de escritura en código + CLI con tool-calling y
confirmación humana) — detalle en `Mejoras_realizadas.md`. Pendiente:

- **Explorar Camino A — cliente MCP dentro de Obsidian** (candidato: plugin
  **Local LLM Hub**): envolver `tools/obsidian.py` como servidor MCP stdio y
  apuntar el plugin a él, para tener chat con streaming dentro de Obsidian
  conservando la garantía de escritura solo en `00_Inbox/`. **Verificación
  crítica previa:** confirmar que el plugin permite poner sus vault-tools
  propias en "Off" (escriben sin restricción de carpeta) manteniendo activas
  las tools MCP externas; si no se pueden desacoplar, este plugin no sirve.
  Nota: es un plugin beta (BRAT), solo escritorio.
- *(Opcional)* Envolver el agente en una página Streamlit con confirmación
  humana visual y previsualización Markdown, si el uso por CLI se queda corto.
- *(Opcional)* **RAG-como-tool:** unificar el agente de escritura con el
  retrieval semántico (exponer el RAG como una tool más) para flujos
  "consulta semántica → síntesis → nota en Inbox" en una sola conversación.
  Hoy están separados a propósito (ver decisión en `Mejoras_realizadas.md`).
- ~~**Batería de consultas RAG desatendida (`run_rag_batch.py`):** script
  headless que, dado un YAML de preguntas, escribe un `.md` por pregunta con
  respuesta sintetizada + chunks recuperados, reutilizando código de
  producción sin tocar `2_RAG.py`. (Prompt ya redactado, pendiente de
  ejecutar.)~~ — ✅ **COMPLETADO 2026-07-09/10**: CLI `run_rag_batch.py` +
  página Streamlit `13_RAG_multiple.py` (solo app privada) + `synth_timeout`
  configurable. Detalle en `Mejoras_realizadas.md`. Pendiente de ejecución
  real en pciq22 (solo verificado en casa: `py_compile`/`grep` estáticos).
  Deuda y trabajo futuro derivados:
  - **Deuda de consolidación (BAJA prioridad):** la plantilla `system_content`
    de síntesis vive DUPLICADA en `run_rag_batch.py` (función `synthesize`) y
    en `2_RAG.py` (`synthesize_answer`) — la página `13_RAG_multiple.py` no
    añade una tercera copia porque reutiliza `run_batch()`. Candidata a
    extraer a un `utils/synthesis.py` compartido; misma clase de problema que
    los items 45/50 (utilidades duplicadas entre CLI/Streamlit), pareja
    distinta. No urge — importa sobre todo si se retoma una evaluación
    rigurosa (item 37, golden Q&A) donde el prompt deba ser IDÉNTICO entre la
    web y la batería.
  - **Futuro (no planificado):** (a) batería en la app pública con síntesis
    Gemini en vez de Ollama, para evitar contención del único servicio Ollama
    local cuando varios usuarios consultan RAG a la vez (ver nota operativa en
    `ESTADO.md`); (b) ejecución en segundo plano que sobreviva al cierre del
    navegador — hoy `13_RAG_multiple.py` es síncrona y muere si se cierra la
    pestaña a mitad de batería (para tandas largas, usar el CLI en pciq22).
