# Mejoras pendientes — research_agent
> Backlog vivo. Histórico de lo hecho: Mejoras_realizadas.md · Estado/arquitectura: ESTADO.md

## Orden de prioridad (revisión 2026-06-25)
1. ~~`detect_affected_categories` con `normalize_stem`~~ — ✅ **COMPLETADO 2026-06-13** (incluido en puerta de dedup por DOI).
2. Item 37 — golden Q&A.
3. Item 36 — idempotencia.
4. ~~Item 44 — fix `_clean_doi` (recorta sufijos DOI de 3+ letras)~~ — ✅ **CERRADO 2026-06-13**. Verificado en pciq22: DOIs con `:` y barra final se normalizan; `10.1023/B:HYDR.0000008620.87704.3b` se preserva; 53 tests pasan.
5. Item 45 — consolidar utilidades de texto duplicadas pdf_utils↔1_rename. **Nota 2026-06-13:** el trabajo de hoy sobre DOIs tocó ambos ficheros (`normalize_doi`, `normalize_stem`, lookups por stem/título en `doi_manual`). Revisar si introdujo nueva divergencia antes de consolidar.
6. ~~Item 41 — índice viejo all__bge-m3.~~ ✅ COMPLETADO 2026-06-16.
7. Item 35 — OCR (si hay escaneados). ~~Item 31 — MVP libros~~ ✅ **MVP HECHO 2026-07-10** (falta eval Hit@k/MRR con golden manual).
- ~~Item 49 — completar Hermes Agent (Discord + MCPs)~~ — ✅ **MAYORMENTE COMPLETADO 2026-06-25** (operativo 24/7 con Notion/Calendar/Gmail/Tavily; residuales: override modelo local para Gmail y aplicar plist ingesta 04:00 en pciq22).
- ~~Timeout job semanal: subir `SCOPUS_TIMEOUT` de 2700 a 5400 (45→90 min)~~ — ✅ **COMPLETADO 2026-06-15** — `run_weekly_scopus.py`: `SCOPUS_TIMEOUT = 5400`; `WEEKLY_CATEGORIES` ampliada con `anoxic_biogas_biodesulfurization`.

## Orden de prioridad (revisión 2026-07-20 — auditoría externa Kimi K2)
> Detalle y justificación: `docs/auditorias/2026-07-20_auditoria_externa.md`.
> Items 52–61 nuevos (bloque al final); el resto son anotaciones fechadas dentro de items existentes. El orden 2026-06-25 sigue vigente para lo no tocado aquí.

1. **Item 52 (P0) — `num_ctx` + `temperature` en las DOS rutas de síntesis.** Verificar antes en pciq22 (`ollama ps`, columna CONTEXT); fix de 30 min. Degradación silenciosa potencialmente activa hoy.
2. **Item 53 — default `hybrid` → `False` en `run_rag_batch.py`** (verificar `grep setdefault`). 2 min.
3. **Item 33 (anotado) — tokenizer BM25** (acrónimos/fórmulas/tildes/griegas, índice + query) → re-correr eval denso/híbrido después.
4. **Item 54 — `run_weekly_scopus`:** aplicar plist 04:00 + LaunchDaemon + timeout con kill real.
5. **Item 55 — integridad índice↔metadata:** norma de embeddings (verificar `np.linalg.norm`) + `assert ntotal==len(meta)` + orden de escritura de `indexed_papers.json`.
6. **Item 37 (anotado) — harness de eval:** Wilson/McNemar/Recall/Precision/arquetipo/deriva + excluir preguntas sin relevantes.
7. **Item 57 — desduplicar el núcleo RAG** antes del primer uso investigativo de la batería.
8. **Items 56, 58, 59, 60, 61** — higiene de pipeline, TLS del Bearer, observabilidad, reproducibilidad y fiabilidad de citas (P1–P2, ver bloque final).

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
- **Auditoría externa 2026-07-20:** añadir (a) **copia cifrada del `config/.env`** (age/gpg,
  passphrase en gestor externo) como paso de `12_Backup.py` — hoy es la ÚNICA copia de todas
  las API keys/passwords, fuera de git y del rsync de `/Volumes/research/`; (b) versionar la
  infra que solo vive en pciq22: `~/grobid-compose.yml` y
  `~/Library/LaunchAgents/com.martin.ollama.plist` → `deployment/` (no llevan secretos). Ver
  también item 60.

### 28. Subagente navegador OpenClaw — Bloque C

Para resolver descargas fallidas donde Unpaywall/Elsevier no encuentran PDF
pero la landing page tiene botón accesible.

**OpenClaw** (antes Clawdbot/Moltbot) es un agente autónomo open-source
self-hosted que puede navegar la web y ejecutar acciones. Actualmente bajo
fundación independiente con apoyo de OpenAI (MIT license).

Entrada: `pendientes_descarga.csv` (item 15, prerequisito).
Reglas: sin saltarse paywalls, sin captchas, pausas entre accesos, límite por sesión,
parar ante 403/429.

**2026-07-12 (item 15):** añadido snooze de 2 años (`snooze_until` +
`pending_active()`/`snooze()`/`unsnooze()` en `download_registry.py` +
página `15_Pendientes.py`) para sacar del email semanal los DOIs sin
interés/acceso — detalle en `Mejoras_realizadas.md`. El subagente OpenClaw
(item 28) seguiría alimentándose de `pending_active()`, así no intentaría
descargas de DOIs ya descartados/pospuestos por el usuario.
**✅ Verificado en pciq22 (2026-07-12, cont.):** round-trip funcional contra
un DOI real (snooze → excluido de `run_weekly_scopus.py --dry-run` →
unsnooze → reaparece), `pendientes_descarga.csv` confirmado intacto tras la
prueba. Detalle en `Mejoras_realizadas.md`.

**✅ CERRADO 2026-07-12 (cont.) — desincronización registro↔corpus:** la
propia verificación destapó que `mark_downloaded()` solo la llama
`3a_download_pdfs.py`; DOIs ingestados por otra vía (PDF manual) se
quedaban `pending` para siempre aunque el paper ya existiera. Nueva
`download_registry.reconcile_with_corpus()` cruza pendientes contra
`papers_metadata.jsonl` de todas las categorías y marca `downloaded` los ya
ingestados; corre automáticamente en `15_Pendientes.py` (aviso visible) y
antes del email semanal. Ejecutada ya contra el NAS real: **37
reconciliados** — de 35 "pendientes activos" reportados por el usuario, 34
ya estaban en el corpus. Detalle en `Mejoras_realizadas.md`.
- **Auditoría externa 2026-07-20 — recomendación: CONGELAR (de-scope).** Tras la
  reconciliación registro↔corpus (34/35 ya estaban en el corpus), los pendientes reales son
  ~1 → el ROI del subagente navegador se desploma. Mantener en espera hasta que haya un
  volumen de descargas fallidas que lo justifique.

### 30. Documentación para el grupo — ALTA si se comparte

- **Guía rápida**: cómo buscar artículos, cómo hacer buenas preguntas RAG,
  cómo exportar papers, cómo citar correctamente.
- **Política de uso**: no descargas masivas, no saltarse paywalls, no compartir
  PDFs fuera del grupo si la licencia no lo permite, respetar acceso institucional.
- **Auditoría externa 2026-07-20 — subir a P1, prerrequisito de difundir `:8502`:** la app
  pública ya está desplegada (password compartida + Gemini BYOK) sin guía ni política, y
  registra consultas (`rag_queries_*.jsonl`) sin aviso de transparencia. Mínimo antes de
  difusión amplia: `st.caption` permanente "verifica cada afirmación contra el fragmento
  citado", nota de registro de consultas y normas de licencia. Quick-win con mayor ratio
  protección/esfuerzo del backlog (medio día).

### 31. Pipeline para libros de docencia — ✅ MVP hecho (2026-07-10) / eval pendiente

**MVP funcional** (detalle en Mejoras_realizadas.md y ESTADO.md): estructura NAS
`/Volumes/research/libros_docencia/`, `scripts/books/{process,embed,query}.py`
(PyMuPDF+TOC, limpieza, skip de front/back matter, índice bge-m3/FAISS propio con
borrado incremental), citas de libro (`Autor (Año), Libro, cap., p.`) vía
`citation_for_chunk`, y página "Preparar clase" (contraste manual↔papers). Validado
con **1 libro** (Najafpour 2007, 153 chunks).

Diseño confirmado en el MVP:
- Parser: pymupdf en lugar de GROBID ✅
- TOC del PDF → metadata jerárquica (capítulo, páginas físicas) por chunk ✅
- Sin 4_extract_metadata.py ni 3b_summarize.py ✅
- Reutiliza: bge-m3, FAISS, infraestructura Streamlit ✅

**Pendiente — hardening / fase 2:**
- **Evaluación Hit@k/MRR** con **golden manual** (8-12 preguntas escritas a mano)
  — bloqueante para dar el item por cerrado del todo.
- **Ingesta epub opcional**: usar epub si el PDF es malo/escaneado o si el epub trae
  `page-list` con las páginas de la edición impresa; si no, seguir con PDF.
- Evaluar **PyMuPDF4LLM** o **Docling** como extractor alternativo para libros
  difíciles.
- Mapear **página IMPRESA** (page labels del PDF) además de la física.
- **Render LaTeX** en "Preparar clase": convertir `\( \)` → `$ $` para que Streamlit
  renderice las ecuaciones.
- **Deduplicar citas repetidas** del mismo capítulo/páginas en el render de
  referencias.

Escalar de 1 → 30+ libros de bioprocesos cuando la evaluación valide la calidad.
- **Auditoría externa 2026-07-20:** hacer "Mapear página IMPRESA (page labels)" **antes** de
  escalar de 1 a 30 libros — re-procesar 30 libros después es evitable. La detección barata de
  escaneado (texto≈0 → cuarentena, items 18/35) puede implementarse ya.

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

- **Auditoría externa 2026-07-20 (`docs/auditorias/2026-07-20_auditoria_externa.md`):**
  confirmado en código que `tokenize` = `re.findall(r"[a-z0-9]+", text.lower())` destruye
  `NR-SOB`, `Fe(II)`, cargas, letras griegas (α/β/μ) y parte palabras con tilde
  (`desulfurización`→`desulfurizaci`+`n`), **tanto en el texto indexado como en la query**.
  Consecuencia: la comparación denso-vs-híbrido (anoxic 0.50→0.25, biogas MRR 0.889→0.857)
  se hizo con un BM25 que no ve los términos donde BM25 aportaría → la conclusión "denso
  gana" puede ser correcta por parsimonia, pero la evidencia no la sostiene. Fix:
  `[a-z0-9]+(?:-[a-z0-9]+)*` + `strip_accents`/NFKD + tests (H2S, TiO2, NR-SOB, Fe(II), kLa).
  Secuencia obligada: arreglar tokenizer → re-correr eval → decidir híbrido.
  **Corrección de la propia auditoría:** retira su punto "(2) RRF k=60 sobre pools diminutos"
  — `pool_size()` devuelve `max(k*10, 200)` (pools de 200/brazo), régimen donde k=60 es
  defendible; la raíz es el tokenizer, no la fusión.
- **Reranking (fase 2):** confirmado que `bge-reranker` NO se sirve desde Ollama. Vías reales
  sin violar Ollama 0.30.7: (a) CrossEncoder `bge-reranker-v2-m3` en `sentence-transformers`
  (rerank top-20 <1 s en M4, añade torch al venv); (b) LLM-as-reranker pointwise con qwen2.5
  (cero dependencias) para la evaluación inicial.

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
- **Auditoría externa 2026-07-20:** el harness (`run_eval.py`) necesita, en una sola
  iteración antes de generar golden nuevos: (a) **excluir preguntas con
  `relevant_paper_ids: []`** — hoy `pool_candidates.py::cmd_build` las escribe al golden y
  en `run_eval` dan `hit=0/rr=0` siempre, inflando el fracaso aparente; (b) **IC de Wilson**
  para Hit@k y **bootstrap** por pregunta para MRR; (c) **McNemar** (test emparejado) para
  denso-vs-híbrido; (d) **Recall@k y Precision@k** (anoxic ~4 relevantes/pregunta; Hit@8 solo
  mira si cae *alguno*; para reranking importarán Precision@3-5 y MRR); (e) **métricas por
  `archetype`** además del global; (f) diagnóstico gratis: **Jaccard top-k denso vs top-k
  BM25** por pregunta (≈1 ⇒ fusión decorativa); (g) escribir en el CSV **`index.ntotal`, max
  `processed_date`, git commit y hash del golden** (deriva del corpus entre runs;
  `corpus_manifest.py` ya genera casi todo). Reformular en docs: "sin evidencia de beneficio
  del híbrido a n=10; OFF por parsimonia", no "denso gana". El Hit@8=1.0 de biogas es casi
  seguro artefacto de pooling.

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
- **Auditoría externa 2026-07-20:** ampliar la suite al **núcleo de recuperación**, hoy sin
  tests: `utils/retrieval.py` (`dense_rank`, `bm25_rank`, `rrf_fuse`, `passes_filters` con
  `year=None` + filtro activo, `pool_size`), el tokenizer (H2S/TiO2/NR-SOB tras el fix del
  item 33) y `run_eval.py`. Son funciones que devuelven resultados distintos sin lanzar error.
  Sobre fixtures, sin Ollama ni FAISS real.

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

**~~Deferred — "mantener campo, no volver a sugerir"~~ ✅ COMPLETADO
2026-07-12:** las sugerencias Crossref rechazadas (título/revista/año/autores)
reaparecían en cada re-escaneo, tanto en el listado por-campo como en las
adopciones masivas de autores y año. Registro nuevo `utils/validation_overrides.py`
(`metadatos/validation_overrides.csv`) marca `(categoría, paper_id, campo)` como
verificado; filtrado tanto en `validate_metadata.py`/`metadata_validation.py`
(no entra al sidecar en origen) como en `11_Articulos.py` (oculta al instante,
sin esperar a re-validar; evita re-consultar Crossref en las previews masivas).
Botones "✋ Mantener {campo}" junto a cada "Adoptar", incluido el lote masivo de
año ±1 (antes solo-lectura) y los "saltados" (sin DOI/miss/sin año, con
"🚫 No reintentar año"). Panel "🔓 Campos marcados como verificados" con
"↩ Revertir" para deshacer. Detalle en Mejoras_realizadas.md.
**✅ Verificado en pciq22 (2026-07-12, cont.):** round-trip funcional contra
el sidecar real (categoría `biological_gas_odor_treatment`) — marcar
"Mantener" → re-ejecutar `validate_metadata.py --crossref` → confirmado que
el issue no reaparece en origen → revertido sin dejar rastro. Detalle en
`Mejoras_realizadas.md`.

**✅ CERRADO 2026-07-12 (cont.) — bugs destapados por la propia
verificación:** (1) dejar un campo vacío en el editor guardaba la cadena
literal `"<NA>"` (bug real de `pd.NA`+`str()`, no solo visual) —
`journal`/`doi` ahora se pueden vaciar de verdad, `title`/`year`/`authors`
siguen protegidos; (2) un DOI correcto no resuelto en Crossref
(`crossref_miss`) no tenía forma de marcarse como revisado — `doi` añadido
a `validation_overrides.FIELDS`, botón "✋ Mantener DOI", y el criterio de
flagging ampliado (antes un miss aislado sin otro issue era invisible en
todo el pipeline); (3) los diagnósticos locales Nivel 1 (`doi_malformed`,
`title_eq_journal`…) eran de solo lectura, ahora también tienen "Mantener".
Además, un DOI real mal extraído (punto en vez de barra,
`10.22034.gjesm.2026.03.10`) corregido en el NAS tras confirmar con
`doi.org` que la versión con barra resuelve. Detalle en
`Mejoras_realizadas.md`.

**✅ CERRADO 2026-07-12 (cont.) — rendimiento adopción masiva:** "Previsualizar
adopción de autores/año" barría TODOS los DOI de la categoría en cada clic;
ahora los candidatos salen del sidecar (`authors_mismatch` /
`year_mismatch` con `suggested_source=="crossref"`) y solo se consulta
Crossref en vivo (autores) o nada en absoluto (año, ya viene como `int` en
el sidecar) para el subconjunto que de verdad difiere. Detalle en
`Mejoras_realizadas.md`.

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


---

## Auditoría externa (Kimi K2, 2026-07-20) — items nuevos 52–61
> Origen: `docs/auditorias/2026-07-20_auditoria_externa.md`. Los items marcados **VERIFICAR
> (pciq22)** son inferencias de lectura de código: confirmar en pciq22 antes de editar en casa.
> Disciplina de dos máquinas: verificación/ejecución en pciq22, edición/commit en casa.

### 52. `num_ctx` + `temperature` en las dos rutas de síntesis — P0 (crítico)

`rag_core.py::stream_ollama` y `run_rag_batch.py::synthesize` llaman a `client.generate(...)`
**sin `options`** → Ollama usa `num_ctx=4096` por defecto y trunca el prompt en silencio
(descarta los tokens más antiguos: system prompt + primeros chunks). Con top_k=8 y chunks de
hasta 8000 chars se supera 4096 en consultas normales. `apply_citations` post-procesa las
claves `[N]` que el modelo sí menciona → la respuesta truncada **parece** correctamente citada.
Temperatura sin fijar (default 0.8 en Ollama) para síntesis con citas.

- **VERIFICAR (pciq22):** `ollama ps` (columna CONTEXT) durante una consulta real. CONTEXT=4096
  ⇒ confirmado. Opcional: contrastar `input_tokens` estimado (chars//4) contra 4096 en los
  `rag_usage_*.jsonl` para acotar el daño histórico.
- **Fix (casa → commit → pull → pciq22):** `options={"num_ctx": 8192, "temperature": 0.0}` en
  ambas funciones. 8192 sobra para top_k=8; 16384 solo si se sube top_k (agranda el KV-cache —
  cabe en 24 GB con qwen2.5:14b + bge-m3, pero elegir a conciencia). Documentar ambos valores en
  ESTADO.md junto a los modelos.

### 53. Default `hybrid` → `False` en `run_rag_batch.py` — P1 (2 min)

La batería usaría híbrido **ON** (`cfg.setdefault("hybrid", True)`) mientras la política de
producción es OFF ("denso gana") → **no reproduce producción**. Es la copia del núcleo RAG (item
57) ya desalineada en un parámetro de comportamiento.

- **VERIFICAR:** `grep -n 'setdefault("hybrid"' scripts/run_rag_batch.py`. Si es `True` →
  cambiar a `False` (el YAML puede seguir forzándolo explícitamente cuando se quiera).

### 54. `run_weekly_scopus`: ingesta semanal robusta — P1

Tres grietas apiladas en la función central del sistema:
1. **Plist 04:00 sin aplicar** (residual del item 49): `git pull` + `cp deployment/... ~/Library/LaunchAgents/` + `launchctl bootout/bootstrap`.
2. **LaunchAgent con `WakeOnLaunchDate` que se pierde sin sesión gráfica** (mismo fallo del 16/18-jul en `daily_question`) → migrar a **LaunchDaemon** (`UserName` + `HOME`, verificar SMTP en frío como se hizo con `claude`).
3. **El "timeout de 90 min" no termina el proceso:** `ThreadPoolExecutor` + `future.result(timeout=5400)` + `executor.shutdown(wait=False)` con threads **no-daemon** → el email sale pero el proceso sigue vivo hasta que `run_scopus` acaba de verdad (launchd ve el job vivo, Ollama ocupado). Además `pdf_after` se cuenta en el instante del timeout → números del email incoherentes con el estado final. Sustituir el thread por `subprocess.Popen([...], start_new_session=True)` + `wait(timeout=5400)` + `os.killpg(os.getpgid(p.pid), SIGKILL)` al expirar (kill real del árbol de procesos). ~30 líneas.

### 55. Integridad índice ↔ metadata — P1

- (a) **Norma de embeddings — VERIFICAR (pciq22):** `5_build_embeddings.py` usa
  `faiss.IndexFlatL2` sin `faiss.normalize_L2`; `attachments.py` lo documenta ("NO normaliza").
  Si bge-m3 vía Ollama no devuelve vectores normalizados, la similitud no es coseno. Comprobar en
  3 líneas contra el Ollama de prod: embeber un texto y `np.linalg.norm(v)`. Si ≈1.0 → documentar
  "Ollama normaliza, L2≈coseno" y cerrar; si no → normalizar en `embed_texts` (idempotente) y
  re-indexar.
- (b) **`assert index.ntotal == len(meta)`** al cargar en los 5 consumidores (`run_eval.py`,
  `pool_candidates.py`, `run_rag_batch.py`, `8_query_rag.py`, `2_RAG.py`); mejor en el loader
  compartido del item 57. Hoy todos hacen `if idx >= len(meta): continue`, tolerando una
  desalineación parcial en silencio.
- (c) En `5_build_embeddings.py`, escribir `indexed_papers.json` **antes** de `write_index` (hoy
  es lo último → un kill entre ambos deja vectores sin registrar → duplicados en el siguiente run).

### 56. Robustez del pipeline — P2

- (a) **FileHandler leak** en `pipeline.py::_setup_pipeline_log`: cada `run_scopus`/`run_inbox_*`
  hace `log.addHandler(fh)` sin `removeHandler`; Streamlit importa `pipeline` in-process y vive
  semanas → handlers acumulados (logs cruzados) + leak de fd. `run_weekly_scopus.py` sí tiene guard
  (`if not log.handlers`); portarlo (try/finally o `_setup` idempotente).
- (b) **`run_step` sin timeout:** lectura bloqueante de `process.stdout` sin watchdog → un hijo
  colgado (GROBID muerto, red) bloquea el pipeline. Watchdog por inactividad (N min sin línea →
  `process.kill()`) al menos en pasos de red (`0_scopus_api`, `3a_download`, `3_process`).
- (c) **Quitar el `--force` obsoleto** de `integrate_adhoc` → `5_build_embeddings.py` (data del
  2026-05-27, previo al incremental del 2026-06-04; re-indexa toda la categoría por 2 papers).
- (d) Inconsistencias menores: `run_books` es `raise NotImplementedError` mientras ESTADO.md lo
  describe funcional (código muerto contradictorio); docstring de `run_adhoc` dice "no renombra"
  pero sí; docstring de `8_query_rag.py` obsoleto ("nomic-embed-text", "k*5"); `iter_chunks` usa
  `chunk["text"]` (usar `.get` → evita `KeyError`).

### 57. Desduplicar el núcleo RAG — P1

`load_metadata` y `embed_query` copiadas VERBATIM en 4 sitios (`8_query_rag.py`, `run_eval.py`,
`pool_candidates.py`, `run_rag_batch.py`); la plantilla de síntesis en `rag_core.py::build_default_system`
+ copia en `run_rag_batch.py::synthesize`; y `2_RAG.py` importa un **tercer** `embed_texts` desde
`utils/attachments.py`. Extraer a `utils/`: `load_index_and_meta` (con el assert del item 55b),
`embed_query`, y `utils/synthesis.py` (plantilla, módulo puro sin streamlit). Hacer **antes** del
primer uso serio de la batería para investigación (item 37): la copia ya se desalineó una vez (item
53). Extiende la "deuda de consolidación" anotada bajo `run_rag_batch.py` y el item 50 (pareja
distinta). ~2–3 h.

### 58. TLS / túnel para el Bearer de Ollama — P1 (seguridad)

Caddy en `http://pciq22.uca.es:11434` exige Bearer pero el canal es **HTTP plano** → el token
(`OLLAMA_API_KEY`) circula en claro por la red del campus (interceptable en el segmento). Opciones:
(a) `tls internal` de Caddy + repartir el cert raíz a los pocos clientes (Obsidian) — la menos
friccionante a medio plazo; (b) cert UCA si `pciq22.uca.es` puede obtenerlo; (c) cerrar `:11434` a
la red y usar túnel SSH (`ssh -L 11434:127.0.0.1:11435`) si el único cliente remoto sois vosotros por
VPN. Relacionado: `PasswordAuthentication no` en pciq22 (ya en el checklist del item 49).

### 59. Observabilidad: healthcheck + rotación de logs — P2

- (a) **Rotación** vía `newsyslog` (`/etc/newsyslog.d/research_agent.conf`) para logs de
  Streamlit/Caddy/scopus (hoy crecen sin límite). ~10 min.
- (b) **Healthcheck** barato (launchd): `curl -fsS` a `:8501`, `:8502`, `:11434` (con token) y
  GROBID `/api/isalive`; email solo si falla (reutiliza el SMTP de `run_weekly_scopus.py`). Cierra el
  hueco "me entero por el usuario". ~50 líneas.

### 60. Reproducibilidad: lockfile + configs versionadas + runbook — P1

- (a) `pip freeze > requirements-lock.txt` desde `~/venvs/rag_papers` en pciq22, versionado (la regla
  manual de replicar entre los dos venvs ya falló una vez con un Python 3.14 desinstalado).
- (b) Versionar `~/grobid-compose.yml` y `com.martin.ollama.plist` → `deployment/` (ver item 27).
- (c) Aviso en portada/health si los dos venvs divergen.
- (d) **Runbook mínimo de recuperación de pciq22:** montar `research_bk` → `pip install -r
  requirements-lock.txt` → re-aplicar `deployment/` → re-emitir `.env` desde el gestor. Los índices
  FAISS son **regenerables desde chunks** — decirlo explícitamente (nadie debe entrar en pánico por el
  índice).

### 61. Fiabilidad de citas + coste — P2

- (a) **Chequeo determinista post-síntesis:** verificar que todo `[N]` citado existe entre los chunks
  enviados; marcar citas huérfanas en la UI. Gratis; refuerza el item 52. (Verificación de *entailment*
  —que el chunk sustente la afirmación— más adelante y solo para notas guardadas.)
- (b) `download_registry.py`: `upsert`/`mark_downloaded`/`snooze` comparan DOI **sin normalizar case**
  (`reconcile_with_corpus` sí) → normalizar con `_norm_doi_key` en todas las vías.
- (c) **VERIFICAR:** la pre-estimación de coste en `2_RAG.py` (`app_utils.estimate_cost_usd`) asume
  ~1200 chars/chunk cuando el tope real es 8000 → podría subestimar ~6x el input en providers de pago.
