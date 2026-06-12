# Mejoras pendientes — research_agent
> Backlog vivo. Histórico de lo hecho: Mejoras_realizadas.md · Estado/arquitectura: ESTADO.md

## Orden de prioridad (revisión 2026-06-12)
1. Item 40 — backup: baseline HECHO; falta la página/botón.
2. Item 42 — cerrar resto: copy2 de 9_cleanup (microalgae diferido).
3. Item 39 — tests pytest (_clean_doi, DOI_REGEX SICI, sanitize_filename/shorten_title, _norm).
4. `detect_affected_categories` con `_norm` (tras tener tests).
5. Item 37 — golden Q&A.   6. Item 36 — idempotencia.   7. Item 41 — índice viejo all__bge-m3.
8. Item 35 — OCR (si hay escaneados).   Item 31 — MVP libros, tras el 37.

## Hallazgos pendientes (revisión 2026-06-12)
- `detect_affected_categories` compara stems por igualdad exacta sin `_norm` → riesgo de reproceso
  por puntuación/guiones. PENDIENTE.
- `run_scopus` aplica el filtro de activas también a categorías pedidas explícitamente (descarte
  silencioso). PENDIENTE/menor.
- `promote_adhoc_to_category` usa `sort_keys=True` → reordena todo keywords.yml en cada promoción.
  PENDIENTE/menor.
- Filtro de año descarta papers con year=None en silencio (retrieval.py). Documentar.
- `section_canonical`: `CANONICAL_SECTIONS` (constants) y `canonical_section()` (3_process) se
  sincronizan a mano → riesgo de drift. Verificar.

### Verificaciones pendientes (ficheros no vistos) → item 43.

## Keywords y criterios de búsqueda

Revisar y afinar:
- `config/keywords.yml` — para cribado de PDFs sueltos (flujo inbox)
- `config/scopus_queries.yml` — para búsquedas Scopus directas (flujo scopus)

Categorías con pocas queries actuales (ampliar si hace falta):
- `anoxic_biogas_biodesulfurization` — solo 1 query (12 resultados)
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
refuerzan la robustez del procesado; 37–40 son evaluación, coste y mantenimiento.

### 33. Recuperación híbrida (denso + BM25) + reranking — ALTA prioridad

✅ v1 (denso+BM25+RRF) completado 2026-06-11 — detalle en Mejoras_realizadas.md.

Pendiente (fase 2): reranking opcional sobre el top-N fusionado con `bge-reranker` (vía Ollama) o
un cross-encoder pequeño, antes de pasar al LLM de síntesis.
- Tocar `8_query_rag.py` y la capa de retrieval de `2_RAG.py` / `7_Revision.py`.
- Toggle en la web para activar/desactivar reranking y comparar.
Ligado al item 37 — sin set de evaluación no se puede medir, y el soporte de rerank en Ollama es dudoso.

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

✅ Baseline rsync manual verificado (2026-06-12); replanteado a manual (comando definitivo, `--size-only`, `#recycle`) — detalle completo en Mejoras_realizadas.md.

**Pendiente (replanteado 2026-06-12):**
- Disparador = botón en la web; aviso = banner en portada (umbral 15 días).
- NO será LaunchAgent programado: research_bk (Synology de casa) solo es accesible por VPN +
  montaje SMB manual, así que un job automático fallaría en silencio.
- PENDIENTE: página `12_Backup.py` (detección de montaje, last_backup.json, botones simulacro/
  copiar) + banner en portada + helper `read_last_backup()` en app_utils.py.

### 41. Limpiar el índice viejo all__bge-m3 de anoxic — BAJA prioridad

Fase divergente sin `section_canonical`/`year` en sus chunks. Borrar o re-indexar para
que no compita con el índice canónico al vuelo (items 32/34).

### 43. Verificaciones pendientes de la revisión 2026-06-12 — seguimiento
3_process_corpus.py (canonical_section vs CANONICAL_SECTIONS), 1_rename_papers_by_doi.py (nombre
largo Scopus en descarga), 4_extract_metadata.py (_norm vs 6_Mantenimiento), 5_build_embeddings.py
(ausencia de papers_metadata.jsonl, clave MVP libros), 8_query_rag.py/2_RAG/7_Revision (cableado
passes_filters). Más: detect_affected_categories con _norm; filtro de activas en run_scopus para
categorías explícitas; sort_keys=True en promote_adhoc_to_category.
