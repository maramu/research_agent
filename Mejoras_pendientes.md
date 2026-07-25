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
> Detalle y justificación: `2026-07-20_auditoria_externa.md` (raíz del repo — corregido 2026-07-25;
> el path `docs/auditorias/...` que aparecía aquí antes no existe, el fichero siempre vivió en la
> raíz, ver también auditoría de chunks más abajo).
> Items 52–61 nuevos (bloque al final); el resto son anotaciones fechadas dentro de items existentes. El orden 2026-06-25 sigue vigente para lo no tocado aquí.

> **Verificación 2026-07-20 (pciq22, solo lectura): items 52, 53 y 55a CONFIRMADOS** — pasan de "verificar" a fix. Evidencia en cada item.

1. **Item 52 (P0) — ✅ CONFIRMADO — `num_ctx` + `temperature` en las CUATRO llamadas a `client.generate`** (síntesis app + batería + resúmenes + cribado). Log muestra truncados reales hoy (`prompt=15851 → 4095`). Fix casa: `num_ctx=16384, temperature=0.0`.
2. **Item 53 — ✅ CONFIRMADO — default `hybrid` → `False`** (`run_rag_batch.py:202`). 2 min, mismo commit que el 52.
3. **Item 55a — ✅ CONFIRMADO — bge-m3 sin normalizar (‖v‖=27.1) → similitud del corpus no es coseno.** Renormalizar índice + query (sin re-embeber) **con** el item 33 y **antes** de re-correr la eval. Sesión propia (edición casa + re-index pciq22).
4. **Item 33 (anotado) — tokenizer BM25** (acrónimos/fórmulas/tildes/griegas, índice + query). Va junto al 55a → re-correr eval denso/híbrido después de ambos.
5. **Item 54 — `run_weekly_scopus`:** aplicar plist 04:00 + LaunchDaemon + timeout con kill real.
6. **Item 55b/c — integridad índice↔metadata:** `assert ntotal==len(meta)` + orden de escritura de `indexed_papers.json`.
7. **Item 37 (anotado) — harness de eval:** Wilson/McNemar/Recall/Precision/arquetipo/deriva + excluir preguntas sin relevantes.
8. **Item 57 — desduplicar el núcleo RAG** antes del primer uso investigativo de la batería.
9. **Items 56, 58, 59, 60, 61** — higiene de pipeline, TLS del Bearer, observabilidad, reproducibilidad y fiabilidad de citas (P1–P2, ver bloque final).

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

✅ **Tokenizer BM25 arreglado 2026-07-26** (`utils/retrieval.py::tokenize`). Era el prerrequisito
duro que la auditoría marcaba como "arreglar tokenizer → re-correr eval → decidir híbrido"; el
primer paso está hecho. No requiere reindexado: BM25 se construye al vuelo desde `metadata.jsonl`.
Cambios, todos simétricos entre indexado y consulta:
  - tildes plegadas vía NFKD → `desulfurización` es UN token y casa con `desulfurizacion`;
  - griegas minúsculas conservadas (α/β/μ), con `µ` (signo micro) plegado a `μ` (mu griega);
  - acrónimos con guion como un token **y además sus partes** (`NR-SOB` → `nr-sob`, `nr`, `sob`) —
    emitir solo el compuesto habría sido una REGRESIÓN frente al tokenizer viejo, que sí encontraba
    `sob`;
  - tokens mixtos letra/dígito emitidos también por segmentos (`h2s` → `h2s`, `h`, `2`, `s`;
    `tio2` → `tio2`, `tio`, `2`). **Esto es lo que hace que la consulta "H2S" case con el corpus**,
    donde los subíndices vienen aplanados como "H 2 S" — coherente con la decisión explícita de NO
    reescribir el texto del corpus.
  - `Fe(II)` sigue tokenizando `fe` + `ii` (igual que antes): meter paréntesis en el alfabeto pegaría
    basura tipo `(see`, y no se pierde nada respecto al comportamiento previo.
Tests: `tests/test_bm25_tokenizer.py` (22 casos + 2 end-to-end sobre BM25Okapi).
**OJO al interpretar la eval:** este cambio altera el ranking BM25 y por tanto el híbrido, así que
el "antes/después" contra la línea base vieja NO es limpio — y a n=4/n=6 tampoco tendría potencia
(ver item 37, que bloquea la fase 2).

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
- **Auditoría de chunks 2026-07-25:** refuerza el arreglo del tokenizer BM25. DECISIÓN EXPLÍCITA:
  NO normalizar el aplanado de subíndices (H₂S → "H 2 S", presente en ~13/16 chunks con química)
  reescribiendo el texto. Es constante en todo el corpus y para recuperación densa la consistencia
  vale más que la fidelidad — bge-m3 lo ve igual en chunk y consulta. El daño real es en BM25, donde
  `[a-z0-9]+` lo parte en h/2/s, y ahí el arreglo es el tokenizer. Reescribir el texto obligaría a
  re-embeber y arriesga falsos positivos. Se descarta también el defecto "Table N ." con espacio
  espurio (58/165 = 35%): cosmético, el tokenizer ya descarta los puntos. Prevalencia ≠ importancia.

### 35. Fallback OCR para PDFs escaneados — MEDIA prioridad

GROBID no extrae nada de un PDF que es imagen → entra vacío al índice.

- Detectar "texto extraído ≈ 0 caracteres" tras `3_process_corpus.py` y disparar OCR.
- `ocrmypdf` (Tesseract) genera un PDF con capa de texto; reintentar GROBID sobre él.
- Idiomas: `eng` (corpus mayoritariamente en inglés).
- Encaja con la carpeta de cuarentena (item 18): si tras OCR sigue vacío → cuarentena.
- **Auditoría de chunks 2026-07-25:** caso nuevo que el filtro NO caza. 1989_anderson tiene texto
  extraíble (pasa `text_extractable=true`) pero el texto está degradado por OCR: `~`→`-`,
  `10⁻⁹`→`10m9` (el exponente cambia de valor), `CO₃²⁻`→`CO:-`, "Saanich Inler", "sediment mps".
  Peor caso que un escaneado limpio sin texto, porque entra al corpus sin aviso. Considerar un
  chequeo de calidad de OCR además del binario texto/no-texto. (OJO: este paper es 1989_anderson,
  NO 1998_searcy — searcy salió como el chunk más limpio de los 16.)

### ~~36~~. ✅ (36-A completado 2026-06-20) Idempotencia y reanudación por documento — MEDIA prioridad

Estado explícito por PDF (descargado → renombrado → extraído → resumido → indexado)
para que un fallo a mitad no obligue a reprocesar todo ni deje entradas a medias.

- Registro de estado por `paper_id`/`stable_id` (JSON o columna en manifest).
- Complementa el indexado incremental de FAISS (item FAISS incremental, 2026-06-04)
  y el skip logic existente, dándole trazabilidad y reanudación explícita.
- Útil tras timeouts del job semanal o caídas de VPN a mitad de ingesta.
- 36-A completado 2026-06-20: visibilidad por paper en pestaña Pendientes (opción ligera, sin fichero persistente).

### 37. Set de evaluación del RAG (golden Q&A) — ⛔ PRIORIDAD ELEVADA 2026-07-26: CUELLO DE BOTELLA DEL PROYECTO

> **ANOTACIÓN 2026-07-26 — la línea base NO sirve para probar mejoras, solo para detectar
> regresiones.** La línea base del 2026-07-26 tiene **n=4** (anoxic) y **n=6** (upgrading):
> - con n=4, **una sola pregunta mueve Hit@8 25 puntos** — no hay resolución para medir nada;
> - **upgrading ya está saturado** en 6/6, así que por construcción no puede mejorar;
> - el MRR de upgrading se movió de **0,889 (junio) a 0,708 (hoy)** por **pura deriva de corpus**,
>   sin ningún cambio de retrieval de por medio; el suelo de ruido es de **~0,18 de MRR**.
>
> Conclusión operativa: la línea base vale como **ALARMA DE REGRESIÓN** (si algo se hunde, se ha
> roto algo), **NO como prueba de mejora**. Cualquier "antes/después" a este n es ruido.
>
> **El item 37 BLOQUEA ahora:** la fase 2 del item 33 (reranking) y cualquier antes/después de los
> items 62, 63 y 55a. Los cuatro cambios alteran el ranking y sin ~25 preguntas por categoría no
> hay forma de atribuir el efecto a ninguno. Es el cuello de botella del proyecto: mientras no se
> amplíe, el resto de trabajo de calidad de retrieval se hace a ciegas.

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
- **Auditoría de chunks 2026-07-25:** anotar el golden a nivel de CHUNK, no de paper. El item 64
  (pureza del corpus) es prerrequisito: no anotar sobre un corpus con papers fuera de dominio.

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
- ✅ **CERRADO 2026-07-26 con evidencia ejecutada** — `table` SÍ está en CANONICAL_SECTIONS
  (8 etiquetas) y `passes_filters` usa `if sections and ...`, así que sin selección pasan todos
  los chunks. La sospecha de pérdida sistemática de tablas por el filtro de sección era infundada.

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

### 52. `num_ctx` + `temperature` en las llamadas a `client.generate` — P0 (crítico) — ✅ CONFIRMADO 2026-07-20

Las llamadas a `client.generate(...)` van **sin `options`** → Ollama usa `num_ctx=4096` por
defecto y trunca el prompt en silencio (mantiene los primeros `keep` tokens + la cola reciente,
descarta system prompt + primeros chunks). `apply_citations` post-procesa las claves `[N]` que el
modelo sí menciona → la respuesta truncada **parece** correctamente citada. Temperatura sin fijar
(default 0.8) para síntesis con citas.

- **CONFIRMADO 2026-07-20 (pciq22, solo lectura):** (a) sin `options` en `rag_core.py:233`
  (`stream_ollama`) y `run_rag_batch.py:139` (`synthesize`) — **y también** en `3b_summarize.py:123`
  y `2_screen_pdfs.py:385` (resúmenes y cribado truncaban igual). (b) `ollama show
  qwen2.5:14b-instruct --modelfile | grep num_ctx` no devuelve nada → runtime cae a 4096; `ollama ps`
  mostró el modelo cargado a CONTEXT=4096. (c) **Daño real en producción hoy mismo** en
  `~/ollama.launchd.err`: `truncating input prompt limit=4096 prompt=15851 keep=4 new=4095` (y
  prompts de 13141, 9219, 4933 tokens, todos recortados a ~4095). Las consultas grandes pierden ~¾
  del contexto.
- **Fix (casa → commit → push → pull → pciq22 → reiniciar Streamlit):**
  `options={"num_ctx": 16384, "temperature": 0.0}` en las **cuatro** llamadas (para resúmenes,
  `temperature` puede quedar según su uso; `num_ctx` es imprescindible en las cuatro). **Corrección
  2026-07-20:** el 8192 que se barajó es insuficiente — se han visto prompts reales de 15851 tokens;
  16384 cubre lo observado, 32768 da margen total (qwen2.5:14b aguanta 32k; el KV-cache cabe en
  24 GB pero multiplica con `OLLAMA_NUM_PARALLEL`). Seguimiento (sub-item): además de subir `num_ctx`,
  acotar el prompt ensamblado (top_k o presupuesto de chars/chunk) para no depender de un contexto
  siempre creciente. Documentar los valores en ESTADO.md.
- **Cola abierta (sub-items, tras cerrar 52 el 2026-07-20):**
  - **52-a — Re-run selectivo pre-fix.** Resúmenes (`3b_summarize`) y cribados (`2_screen_pdfs`)
    generados antes de `6fec8b9` corrían a num_ctx=4096 → posible texto truncado en papers largos.
    Identificar afectados (prompt estimado `chars//4` > ~4096 en logs de esos pasos) y re-ejecutar
    solo esos. No rehacer a ciegas. Prioridad baja.
  - **52-b — Acotar el prompt ensamblado.** Añadir presupuesto duro (cap de top_k o de chars/chunk)
    en el ensamblado de síntesis para que el prompt no pueda exceder num_ctx por diseño; con prompts
    vistos de ~15.851 tok, subir contexto no basta a largo plazo. Formaliza el "seguimiento" del 52.

### 53. Default `hybrid` → `False` en `run_rag_batch.py` — P1 (2 min) — ✅ CONFIRMADO 2026-07-20

La batería corre híbrido **ON** mientras la política de producción es OFF ("denso gana") → **no
reproduce producción**. Es la copia del núcleo RAG (item 57) ya desalineada en un parámetro de
comportamiento.

- **CONFIRMADO 2026-07-20:** `run_rag_batch.py:202` → `cfg.setdefault("hybrid", True)`.
- **Fix (casa):** cambiar el default a `False` (el YAML de la query puede seguir forzándolo
  explícitamente cuando se quiera). Puede ir en el mismo commit que el item 52.

### 54. `run_weekly_scopus`: ingesta semanal robusta — P1

Tres grietas apiladas en la función central del sistema:
1. **Plist 04:00 sin aplicar** (residual del item 49): `git pull` + `cp deployment/... ~/Library/LaunchAgents/` + `launchctl bootout/bootstrap`.
2. **LaunchAgent con `WakeOnLaunchDate` que se pierde sin sesión gráfica** (mismo fallo del 16/18-jul en `daily_question`) → migrar a **LaunchDaemon** (`UserName` + `HOME`, verificar SMTP en frío como se hizo con `claude`).
3. **El "timeout de 90 min" no termina el proceso:** `ThreadPoolExecutor` + `future.result(timeout=5400)` + `executor.shutdown(wait=False)` con threads **no-daemon** → el email sale pero el proceso sigue vivo hasta que `run_scopus` acaba de verdad (launchd ve el job vivo, Ollama ocupado). Además `pdf_after` se cuenta en el instante del timeout → números del email incoherentes con el estado final. Sustituir el thread por `subprocess.Popen([...], start_new_session=True)` + `wait(timeout=5400)` + `os.killpg(os.getpgid(p.pid), SIGKILL)` al expirar (kill real del árbol de procesos). ~30 líneas.

### 55. Integridad índice ↔ metadata — P1 — (a) y (b) ✅ RESUELTOS EN CÓDIGO 2026-07-26, PENDIENTES DE ROLLOUT

> **ESTADO 2026-07-26:**
> - **55a ✅ en código.** Normalización L2 en UN SOLO SITIO por lado: helper único
>   `utils.embeddings.l2_normalize()` (con copia obligatoria — `faiss.normalize_L2` muta in-place y
>   los callers reutilizan su `qv`), aplicado en los **dos** constructores de índice
>   (`5_build_embeddings.py` y `books/embed.py`) y en las **dos** rutas de consulta
>   (`utils.retrieval.dense_rank` y `utils.attachments.rank_attachment`).
>   **Se MANTIENE `IndexFlatL2`**, no se cambia a `IndexFlatIP`: sobre vectores unitarios el orden
>   L2 es exactamente el del coseno (`‖q-d‖² = ‖q‖² - 2·q·d + 1`, con `‖q‖²` constante), así que
>   ningún consumidor tiene que invertir su "menor = mejor" — habría sido tocar 8 call sites y
>   `fuse_results` para cero ganancia de ranking. Como ya no hay que reconstruir vectores, el plan
>   de `index.reconstruct_n` + renormalizar in situ que proponía la auditoría queda descartado: se
>   re-embebe en la misma tanda que el re-chunk de 62/63, que era obligatorio de todos modos.
>   **Hallazgo del inventario de rutas:** no eran 4 rutas densas sino **8 call sites en 7 ficheros**
>   (además de 8_query_rag / run_rag_batch / 2_RAG / 7_Revision: `run_eval.py`,
>   `pool_candidates.py`, `14_Preparar_clase.py` ×2 y un SEGUNDO call site en `2_RAG.py`, el de
>   "Profundizar en estos papers"). Ninguna llamaba a `index.search()` directamente, así que
>   normalizar dentro de `dense_rank` las cubre todas. Guard estructural en
>   `tests/test_retrieval_normalization.py`: falla si aparece un `*index*.search(` fuera de
>   `retrieval.py` o un tercer constructor de índice FAISS.
>   **Dos superficies que NO pasan por `dense_rank` y había que tocar igual:**
>   `utils/attachments.py` (calculaba L2 crudo en numpy y `fuse_results` MEZCLA POR DISTANCIA esos
>   valores con los del corpus → el adjunto no habría ganado nunca una plaza de relleno) y
>   `books/embed.py` (su índice se fusiona por distancia con los de papers en
>   `14_Preparar_clase.py` → el cupo de libro habría dejado de competir).
> - **55b ✅ en código**, en su versión de constructor (no la de los 5 consumidores). Al terminar de
>   construir un índice, `verify_index_integrity()` comprueba las tres cosas y **aborta con
>   SystemExit, no con warning**: `index.ntotal == len(metadata.jsonl)`, norma L2 media ≈ 1,0 y el
>   flag `"normalized": true` de `config.json`. El modo incremental además llama a
>   `assert_index_normalized()` **antes de escribir nada**, así que un índice pre-55a se detecta y
>   aborta limpio pidiendo `--force` en vez de quedarse mezclado.
>   **Nuevo `"normalized": true` en config.json** (papers y libros): sin ese flag un rollout parcial
>   es INDETECTABLE para `14_Preparar_clase.py:138`, que ordena por distancia mezclando varios
>   índices — daría resultados basura en silencio.
> - **Sigue PENDIENTE la parte (b) original** (`assert index.ntotal == len(meta)` en los 5
>   consumidores al CARGAR) y la **(c)** (orden de escritura de `indexed_papers.json`).

- (a) **Norma de embeddings — ✅ CONFIRMADO 2026-07-20:** bge-m3 vía Ollama **NO** normaliza
  (‖v‖ = **27.11**, dim 1024, ≠ 1.0), y el índice es `IndexFlatL2` sobre vectores crudos →
  **la similitud de TODO el corpus no es coseno** (penaliza por magnitud, no semántica). Fix, en dos
  lados que deben ser consistentes: (1) **índice** — no hace falta re-embeber: reconstruir los
  vectores (`index.reconstruct_n`), `faiss.normalize_L2`, reconstruir el índice (`IndexFlatIP`, o
  `IndexFlatL2` sobre normalizados — monótono con coseno) y guardar; (2) **query** — normalizar el
  vector de consulta en `embed_query`/`embed_texts` antes de buscar. Barato en cómputo (sin llamadas
  a Ollama), pero **cambia la recuperación** → secuenciar **con** el tokenizer (item 33) y **antes**
  de re-correr la eval (ambos alteran el ranking; si no, se contamina la atribución). La parte de
  editar código va en casa; el reconstruir/normalizar el índice es ejecución en pciq22 (sesión
  propia, con `.bak` del índice antes).
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
  Streamlit/Caddy/scopus (hoy crecen sin límite). ~10 min. **Concreto 2026-07-20:** el log del
  servidor Ollama es **`~/ollama.launchd.err`** (StandardErrorPath del plist), **ya en 58 MB y
  creciendo** — incluir en la rotación. (Corrección de runbook: NO está en
  `~/.ollama/logs/server.log`, que está vacío; usar `~/ollama.launchd.err` para cualquier `grep` de
  diagnóstico de Ollama, p. ej. truncados del item 52.)
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

---

## Auditoría de calidad de chunks vs PDF original (2026-07-25) — items nuevos 62–64
> Origen: informe en `/Volumes/research/metadatos/auditoria_chunks/2026-07-25/informe.md` (NAS,
> fuera de git) — pendiente copiar a la raíz del repo como `2026-07-25_auditoria_chunks.md` desde
> pciq22 para versionarlo (mismo patrón real que `2026-07-20_auditoria_externa.md`, la auditoría
> Kimi: raíz del repo, no `docs/auditorias/`). Muestra estratificada de 16 chunks (semilla 20260725)
> de `anoxic_biogas_biodesulfurization` (1741 chunks, 87 papers), comparada contra la página
> renderizada del PDF original (no contra `md_clean`), protocolo a ciegas.

### 62. `canonical_section()` se aplica al título del paper — ✅ RESUELTO EN CÓDIGO 2026-07-26, PENDIENTE DE ROLLOUT

`canonical_section()` compara el título completo del paper (que actúa como heading H1) contra las
keywords de sección, así que el bloque de portada (autores + DOI, chunk_index=1) hereda
methods/results. Ejemplos: 2025_brito ("Operational" → methods), 2014_mora ("characterization" →
results). Medido: 31 de 87 chunks chunk_index=1 tienen section_canonical distinto de other/abstract
— COTA SUPERIOR medida por proxy, no verificado que los 31 sean portada sin contenido real
(2018_zheng tiene abstract completo y salió "other"). En términos de corpus son 31/1741 = 1,8%, no
"un tercio".

**CORRECCIÓN 2026-07-26 — el daño NO es ventaja injusta en el ranking.** La versión anterior de este
item afirmaba que estos chunks "compiten con ventaja injusta por el top-8 porque contienen el título
del paper". Es FALSO. La verificación P3 muestra que el texto del chunk es solo
`**Authors:** … **Year/DOI**` y NO contiene el título: el título es el heading H1, que se usa para
CLASIFICAR (de ahí la fuga) pero no entra en el texto del chunk ni, por tanto, en su vector. El daño
real es **lastre muerto que diluye el pool** de candidatos, no ventaja en consultas temáticas.

**CORRECCIÓN 2026-07-26 — el alcance real es MUCHO mayor que la portada.** El defecto no se limita a
los chunks de portada. Por el ascenso de ancestros (`3_process_corpus.py`, resolución del canonical
efectivo: sube de `level` hasta 1 buscando el primer ancestro ≠ "other"), en todo paper cuyo título
case con un patrón, **TODA subsección del cuerpo que no clasifique por sí misma hereda la etiqueta
del título** en vez de caer a "other". Una `## Site description` bajo un título con "Operational"
salía etiquetada `methods`. El fix es el mismo (no clasificar el H1), pero:
  - el número de chunks afectados es muy superior a los 823 de portada — es "todas las subsecciones
    no clasificables de todos los papers con título que casa", sin medir todavía;
  - **el residuo `other` CRECERÁ tras el rollout**, y eso es lo correcto: hoy hay chunks etiquetados
    methods/results que nunca lo fueron. Un filtro por sección que antes los devolvía dejará de
    hacerlo. No confundir esa caída de volumen con una regresión.

**CIFRA REAL de portadas vacías (2026-07-26):** **809 de 823** chunks de portada de las 8 categorías
están vacíos de contenido propio (< 200 chars de prosa tras quitar `**Authors:**`/`**Year|DOI**`).
No 215: los 215 eran solo los MAL ETIQUETADOS; los otros 598 ya estaban en "other" y están igual de
vacíos. Los 4 casos MIXTO (≥ 200 chars de prosa) no se tocan y quedan bien etiquetados por sí solos
gracias al 62.1.

Causa raíz: `constants.py:29-32` + `3_process_corpus.py:376-396`.

**FIX IMPLEMENTADO 2026-07-26** (`3_process_corpus.py`):
- **62.1** — no se aplica `canonical_section()` a `level <= 1`. Ojo: el bloque de portada es
  **nivel 1**, no nivel 0. El nivel 0 (preámbulo) ya devolvía "other" y además viene siempre vacío
  porque `md_clean` empieza con el `# título`; el bloque de autores/DOI es la sección cuyo heading
  ES el H1 del título. El cuerpo nunca es nivel 1 (`_extract_div_content` arranca en `depth=2`).
- **62.2 — DECISIÓN: FUSIONAR con el chunk siguiente, no excluir del índice.** Así los autores
  siguen siendo recuperables y no quedan vectores muertos. Regla DE CONTENIDO (no posicional),
  `merge_empty_cover_blocks()`, con las cuatro guardas: sin chunk siguiente se emite tal cual; si
  el fusionado superaría MAX_EMBED_CHARS no se fusiona; el fusionado hereda el `section_canonical`
  del SIGUIENTE, nunca el del remanente; `chunk_index` se renumera tras las fusiones.

**DECISIÓN 2026-07-25:** se hace por re-chunk + re-embed (reindexar es aceptable), no por backfill
de `metadata.jsonl`, para no divergir código↔datos.

Prioridad: ALTA (el defecto de mayor prevalencia del corpus). Tests: `tests/test_chunking.py`.

### 63. Fusión de filas de tabla y caption huérfano en el fallback del splitter — ✅ RESUELTO EN CÓDIGO 2026-07-26, PENDIENTE DE ROLLOUT

`extract_tables_md` (`3_process_corpus.py:303-363`, rama sin columna "Exp.") une las filas de una
tabla con un solo `\n`, y `_split_to_max_chars` (489-521) solo reconoce párrafos separados por
`\n\n`. Toda la tabla es UN párrafo para el splitter; si supera `MAX_EMBED_CHARS=8000` cae a la
rama de emergencia por palabras (507-513), que descarta los saltos de línea y reconstruye por
palabras sueltas, DESTRUYENDO el límite entre filas. Confirmado en 2023_almenglo #34 (7993 chars):
las filas de Soreanu 2010, Baspinar 2011, Chinalia 2012 y Montebello 2012 quedan fusionadas en una
sola entrada, y aparece `-1000-1500` que es la concatenación de un "sin dato" con el rango de otro
estudio. Una pregunta tipo "¿qué pH usó Baspinar 2011?" puede responderse con el pH de otro
estudio, con cita aparentemente trazable (agrava la P1 de la auditoría Kimi). El MISMO bug explica
el caption huérfano: #33 es el caption solo (107 chars) y #34 los datos sin caption — son los 2 de
165 chunks de tabla sin "Table N" en los primeros caracteres. Un solo arreglo cierra los dos.

Prevalencia: 1/165 tablas ≥7500 chars (0,6%), pero CRÍTICO cuando ocurre, y crece con papers de
tablas grandes.

**DECISIÓN 2026-07-25:** arreglar en ORIGEN — unir filas con `\n\n` en `extract_tables_md`, de modo
que la ruta normal del splitter corte en frontera de fila. Se descartó el parche defensivo de hacer
el fallback consciente de `\n` (menor radio de explosión pero deja el desajuste de diseño intacto).
Implica re-chunk + re-embed de las 8 categorías, aceptado. Añadir además el fallback consciente de
`\n` como cinturón y tirantes.

**VERIFICAR ANTES DEL ROLLOUT:** si `golden_<cat>.jsonl` referencia `chunk_id`, un re-chunk lo
invalida — comprobar en `/Volumes/research/metadatos/eval/` antes de lanzar.

**FIX IMPLEMENTADO 2026-07-26** (`3_process_corpus.py`):
- **63.1** — `extract_tables_md` une las filas con `\n\n` en AMBAS ramas (con y sin columna "Exp."),
  de modo que cada fila es un párrafo y el splitter corta en frontera de fila por su ruta normal.
  El dict de tabla se parte ahora en `header_md` (heading + caption) y `body_md` (solo filas).
- **63.2** — nueva `_split_long_para()`: la rama de emergencia degrada por niveles
  (párrafo → líneas → palabras dentro de una línea → corte duro de token atómico) en vez de hacer
  `para.split()` + `" ".join`. OJO: `books/process.py:132` reutiliza `_split_to_max_chars`, así que
  esto cambia también los CHUNKS de libros → libros necesita re-trocear, no solo re-embeber.
- **63.3** — el heading + caption se antepone a CADA parte de una tabla troceada, con el presupuesto
  descontado antes de trocear el cuerpo para que ninguna parte se pase de MAX_EMBED_CHARS. No se
  repite la fila de cabecera: el markdown ya lleva el nombre de columna inline en cada celda.
- El caption huérfano de 107 chars (almenglo #33) desaparece por 63.1, así que NO necesitó la regla
  de fusión del 62.2. Confirmado en test: todas las partes empiezan por `### Table N` + caption.

Tests: `tests/test_chunking.py` (80 filas intactas, ninguna partida ni fusionada, todas las partes
con ancla, fallback que preserva las fronteras de línea).

**P2 de la auditoría Kimi (2026-07-20) sobre `embed_truncated` — ✅ RESUELTO EN CÓDIGO 2026-07-26,
PENDIENTE DE ROLLOUT.** `utils/embeddings.embed_texts` acepta `truncated_out` (lista opcional) y
`5_build_embeddings.py` persiste `embed_truncated: bool` por chunk en `metadata.jsonl`, cubriendo las
dos vías de truncado (recorte previo a `MAX_EMBED_CHARS` y truncado reactivo por contexto). El
resumen del script imprime el recuento de truncados. Se hizo en la misma tanda que 62/63/55 porque
si no habría que reindexar dos veces. NO se persiste en libros: la caché `_vectors/*.npy` reutiliza
vectores sin flags y no merece la complicación (anotado como residuo menor). Contexto original:
ahora tiene razón funcional, no de higiene, en vez de solo higiene como cuando se registró
(`2026-07-20_auditoria_externa.md`, sección "P2 — Truncado reactivo de embeddings sin auditoría +
divergencia vector↔texto"). 2023_almenglo #34 mide 7993 chars, topa en `MAX_EMBED_CHARS` y es
candidato casi seguro al truncado reactivo de `embed_texts`: texto con filas ya fusionadas por este
mismo bug Y vector representando dos tercios de ese texto ya corrupto. Es el caso peor conocido del
corpus — refuerzo concreto para retomar el `embed_truncated: true` (+ longitud original) en
`metadata.jsonl` que propuso Kimi.

Prioridad: ALTA.

### 64. Pureza del corpus: papers fuera de dominio en anoxic — MEDIA prioridad

Entre los papers tocados por la muestra hay al menos 4 fuera de dominio: 1989_anderson (uranio en
sedimentos de Saanich Inlet), 1997_gervais (migración vertical de Cryptomonas/Chromatium),
2018_zheng (isótopos de mercurio, euxinia mesoproterozoica) y discutiblemente 1998_searcy
(reducción de azufre en eritrocitos humanos). La muestra era dirigida, así que NO es una estimación
de prevalencia. Pero `Mejoras_pendientes.md` da por hecho que "los falsos positivos de
limnología/sedimentos se descartan manualmente" (ver categoría `anoxic_biogas_biodesulfurization`
más arriba) y estos sobrevivieron. Es un problema de cribado, no de extracción, y contamina el
corpus sobre el que se va a anotar el golden del item 37.

Acción: revisar los 87 títulos de anoxic a mano (~30 min) y cuarentenar los fuera de dominio con el
mecanismo reversible existente.

**Anotación 2026-07-26 — quinto paper fuera de dominio.** Aparece
`2004_shikano_volcanic_heat_flux` (lago Katanuma), encontrado INCIDENTALMENTE en la verificación P3,
sin buscarlo. Van cinco, y los fuera de dominio siguen apareciendo sin buscarlos, así que la
prevalencia real es probablemente **muy superior a 4/87** y el conteo actual es un suelo, no una
estimación.

**PENDIENTE DE MIRAR (diagnóstico gratis, hazlo antes de la revisión manual):** anoxic tiene
Hit@8 **0,50** con MRR **0,098** frente a **1,00** y **0,708** de upgrading. Revisar en el CSV por
pregunta **qué papers salen por encima del correcto**. Si son los de limnología/sedimentos, el item
64 se adelanta al resto: significa que la contaminación del corpus, y no el retrieval, explica la
diferencia entre categorías. Un MRR de 0,098 está cerca del suelo de ruido (~0,18), lo que es
compatible con esa hipótesis.

Prioridad: MEDIA, antes del item 37.

### Descartado con evidencia 2026-07-25 (auditoría de calidad de chunks)

- **No se están perdiendo tablas en la extracción:** 176 tablas en TEI → 165 chunks de tabla;
  caption presente en 163/165; 70 de 87 papers con ≥1 tabla (verificado que los papers sin tablas de
  la muestra genuinamente no las tienen); los 6 valores numéricos del golden de anoxic están todos
  presentes y todos en chunks de tabla.
- **Cambio de extractor (Docling / PyMuPDF4LLM) para PAPERS: CERRADO, sin evidencia.** Solo 2
  defectos de techo de GROBID en 16 chunks (tabla fragmentada en 3 `<figure>` con celdas ya vacías
  en el XML en 2021_valdebenito; fórmula partida en `$$CH$$` + texto suelto en 2018_shihab) y 0/6
  CRÍTICOS entre los chunks de control. Sigue vigente evaluarlos para LIBROS difíciles (item 31).
- **4 de 16 CRÍTICOS es sesgo de muestreo intencional:** 3 de los 4 son chunks de tabla o de
  resultados con fórmulas, sobre-representados a propósito en el diseño. Entre los controles, 0/6.
- **Corrupción heredada del PDF fuente, fuera de nuestro alcance:** 1997_gervais
  "Müggelsee"→"Miiggelsee" (confirmado presente ya en la capa de texto nativa del PDF, antes de
  GROBID).
- **Menor, sin acción:** 2014_mora tiene un 8º autor espurio ": D Cantero" (GROBID capturó el
  bloque de afiliaciones como `<author>`); 2018_zheng pierde el nombre chino del autor y produce
  "O cean" por un drop-cap de PNAS.
