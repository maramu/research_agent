# Notas pendientes — research_agent

---

## Verificaciones completadas

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

### 4. Cron/launchd para ingesta Scopus semanal automática

Pendiente. Ejemplo de LaunchAgent o cron:
```bash
0 6 * * 1  cd /Volumes/Disco/proyectos/research_agent/scripts && \
           /Users/martinramirez/venvs/rag_papers/bin/python run_pipeline.py \
           scopus --recent-days 7
```

### 5. Pequeñas mejoras UX en la web (baja prioridad)

- **Toggle síntesis OFF**: mostrar aviso visible en el área principal cuando la síntesis está desactivada.
- **Botones por fila en portada**: acción "Procesar pendientes" directa por categoría en la tabla principal.
- **Página de logs en vivo**: `tail -f` de `~/Library/Logs/research_agent/*.log` directamente en la web.
- **Editor doi_manual.xlsx** con `st.data_editor` — actualmente solo visor.

### ✅ 6. Actualizar precios en app_utils.py (completado 2026-05-27)

`LLM_PRICING` verificado a 2026-05-27. Único cambio:
`claude-opus-4-7`: $15/$75 → **$5/$25** (precio del Opus 4.7, no del antiguo Opus 4.1).
Resto de modelos ya eran correctos. Comentario de fecha añadido encima del dict.
Fuentes: platform.claude.com/docs/en/docs/about-claude/models · developers.openai.com/api/docs/pricing

### 7. README.md global + docstrings

Documentación final del proyecto: README de primer nivel con visión general,
y docstrings en los scripts numerados que aún no los tienen.
Incluir: qué es research_agent, qué puede hacer, cómo acceder, qué categorías
existen, cómo hacer consultas RAG, cómo añadir PDFs, limitaciones, buenas
prácticas. **Prioritario si se comparte con el grupo.**

### ✅ 8. Decisión final nomic vs bge-m3 (completado 2026-05-25)

bge-m3 adoptado como modelo de producción. `utils/constants.py` centraliza el valor; `app_utils.py` y `8_query_rag.py` importan de ahí. Los índices nomic se conservan en el NAS pero no son el default.

### ✅ 9. Fix integrate_adhoc() y run_adhoc() — renombrado antes de procesar (resuelto 2026-05-27)

Ver sección "Verificaciones completadas" — Bug #1 y #2.

### 10. Instancia RAG pública (puerto 8502)

Segunda instancia Streamlit solo con página RAG, sin ingesta ni configuración,
limitada a Ollama (gratuito). Para compartir con colaboradores.
Requiere segundo plist launchd en puerto 8502 y control de acceso (VPN o similar).

### 11. Exportar papers desde RAG

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

### 13. Validar API keys con llamada real

`check_anthropic_api()` y `check_openai_api()` solo validan formato.
Hacer una llamada barata (`list models`) para verificar que la key no está revocada.

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

### 19. Detección avanzada de duplicados — MEDIA prioridad

Ampliar `9_cleanup_duplicates.py` con criterios adicionales:
mismo título normalizado, mismo primer autor + año + título similar, mismo hash PDF.

Generar informe `/Volumes/research/metadatos/duplicate_report.xlsx` con columnas:
`paper_id_1`, `paper_id_2`, `category_1`, `category_2`, `match_type`, `confidence`, `recommended_action`.

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

### 25. corpus_manifest.json — MEDIA prioridad

Manifiesto por categoría con: nº PDFs, nº chunks, modelo de embedding,
modelo de resumen, URL GROBID, hash de keywords, commit git, mtime del índice FAISS.

Útil para reproducibilidad y para detectar cuándo un índice está desactualizado.

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

### 29. Página de actividad — BAJA-MEDIA prioridad

Mostrar en Streamlit: últimas ingestas, últimos errores, últimas consultas RAG,
uso mensual de modelos. Parte de los datos ya existen en `rag_usage/`.

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