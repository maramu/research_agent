# Notas pendientes — research_agent

## 🔴 Bugs pendientes

### Fix integrate_adhoc() — renombrado antes de copiar

`integrate_adhoc()` copia PDFs y luego el renombrado por DOI crea ficheros `_2`
porque el original ya existe en el destino. Orden correcto:
1. Copiar PDFs a destino
2. Renombrar por DOI (`1_rename_papers_by_doi.py`)
3. Procesar cadena completa (`process_category()`)

Hasta que se implemente: tras `integrate_adhoc()` hay que reprocesar manualmente
con `3_process_corpus → 3b_summarize → 4_extract → 5_build_embeddings`.

### Fix run_adhoc() — mismo problema de raíz

Los PDFs del ad-hoc se procesan con nombres originales. Al renombrarlos después,
los chunks/summaries/metadata quedan huérfanos. Renombrar por DOI debe ir
antes de `process_category()` también en `run_adhoc()`.

### Bug #1 — integrate_adhoc() crea ficheros _2 (duplicados)

`integrate_adhoc()` copia PDFs y luego `1_rename_papers_by_doi.py` crea `_2`
porque el original ya existe en el destino.
Orden correcto: copiar PDFs → renombrar por DOI → `process_category()`.
**Workaround actual:** borrar `_2` manualmente + reprocesar con `--force`.

### Bug #2 — Streamlit cachea índice FAISS tras re-indexado

Tras regenerar el índice FAISS, la web sigue usando el anterior hasta reiniciar
el servicio launchd. Añadir botón "Recargar índices" en sidebar de `2_RAG.py`
o invalidar cache automáticamente detectando cambio en `mtime` del `index.faiss`.

---

## Verificaciones completadas

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

- **Toggle síntesis OFF**: cuando el toggle de "Sintetizar respuesta con LLM"
  está desactivado, mostrar un aviso visible en el área principal
  (ej. "Síntesis desactivada — activa el toggle en la sidebar para obtener
  una respuesta con citas") en lugar de pasar silenciosamente a mostrar solo chunks.
  Evita confusión de "¿por qué no responde?".
- **Botones por fila en portada**: acción "Procesar pendientes" directa por categoría
  en la tabla principal, sin tener que ir a la tab de Ingestar.
- **Página de logs en vivo**: `tail -f` de `~/Library/Logs/research_agent/*.log`
  directamente en la web.
- **Editor doi_manual.xlsx** con `st.data_editor` — actualmente solo visor.

### 6. Actualizar precios en app_utils.py

Los precios en `LLM_PRICING` son aproximados a fecha 2026-05-20. Verificar
periódicamente en:
- Anthropic: https://docs.claude.com/en/docs/about-claude/pricing
- OpenAI: https://openai.com/api/pricing

### 7. README.md global + docstrings

Documentación final del proyecto: README de primer nivel con visión general,
y docstrings en los scripts numerados que aún no los tienen.

### ✅ 8. Decisión final nomic vs bge-m3 (completado 2026-05-25)

bge-m3 adoptado como modelo de producción. `utils/constants.py` centraliza el valor; `app_utils.py` y `8_query_rag.py` importan de ahí. Los índices nomic se conservan en el NAS pero no son el default.

### 9. Fix integrate_adhoc() y run_adhoc() — renombrado antes de procesar

Ver sección "🔴 Bugs pendientes" arriba.
Requiere modificar `pipeline.py`: llamar a `1_rename_papers_by_doi.py`
como paso previo al procesado en ambas funciones.
Hasta que se implemente: tras `integrate_adhoc()` reprocesar manualmente con
`3_process_corpus → 3b_summarize → 4_extract → 5_build_embeddings --force`.

### 10. Instancia RAG pública (puerto 8502)

Segunda instancia Streamlit solo con página RAG, sin ingesta ni configuración,
limitada a Ollama (gratuito). Para compartir con colaboradores.
Requiere segundo plist launchd en puerto 8502 y control de acceso (VPN o similar).

### 11. Exportar papers desde RAG

Tras consulta RAG, botón "Exportar papers relacionados" que genera ZIP descargable
con PDFs + md_clean (+ opcional summaries) de los `paper_id`s recuperados.
Implementar con `zipfile` en memoria + `st.download_button` en `2_RAG.py`.

### 12. Validar nombre proyecto en run_adhoc() (revision.md — mejora C)

```python
import re
if not re.match(r'^[a-z0-9_-]+$', name):
    raise ValueError(f"Nombre de proyecto inválido: {name}")
```

### 13. Validar API keys con llamada real (revision.md — mejora F)

`check_anthropic_api()` y `check_openai_api()` solo validan formato.
Hacer una llamada barata (`list models`) para verificar que la key no está revocada.


### C. Validar el nombre de proyecto en `run_adhoc()`

Evitar caracteres peligrosos como `/`, `..`, espacios:

```python
import re
if not re.match(r'^[a-z0-9_-]+$', name):
    raise ValueError(f"Nombre de proyecto inválido: {name}")
```
### F. Validar API keys con una llamada real

`check_anthropic_api()` y `check_openai_api()` solo comprueban que la key existe y tiene el formato esperado. Una key revocada pasaría el check y fallaría al generar. Idealmente hacer una llamada barata (ej. list models) para verificar que la key es válida.
