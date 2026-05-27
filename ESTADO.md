# research_agent — Estado del proyecto

## Infraestructura

| Componente | Detalle |
|---|---|
| Mac mini M4 Pro (casa) | 32GB RAM, modo servidor 24/7, ejecuta scripts y Streamlit |
| NAS (casa) | `/Volumes/research/` — almacenamiento (PDFs, MDs, chunks, embeddings) |
| Mac mini Pro (UCA) | `pciq22.uca.es` — host de Ollama + GROBID |
| Scripts | `/Volumes/Disco/proyectos/research_agent/scripts/` |
| Config | `/Volumes/Disco/proyectos/research_agent/config/` |
| Venv | `~/venvs/rag_papers` (Python 3.13) |
| GROBID | Docker, `http://pciq22.uca.es:8070` |
| Ollama | `http://pciq22.uca.es:11434` |
| Streamlit | `http://<ip-mac-mini>:8501` — servicio launchd 24/7 |
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

```
research_agent/
├── config/
│   ├── .env                          ← claves API, hosts
│   ├── keywords.yml                  ← palabras clave para cribado (8 categorías)
│   └── scopus_queries.yml            ← queries Scopus por categoría
├── scripts/
│   ├── pipeline.py                   ← orquestador (módulo importable)
│   ├── run_pipeline.py               ← CLI del orquestador (scopus/inbox/adhoc)
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
│   │   └── constants.py              ← Constantes compartidas (OLLAMA_MODEL_EMBED)
│   └── streamlit_app/                ← Interfaz web (Streamlit)
│       ├── app.py                    ← portada: health checks + tabla categorías
│       ├── app_utils.py              ← helpers compartidos (renombrado para no
│       │                               colisionar con scripts/utils/)
│       ├── README.md                 ← instrucciones despliegue + launchd
│       └── pages/
│           ├── 1_Ingestar.py         ← scopus / inbox / adhoc con progreso live
│           ├── 2_RAG.py              ← retrieval FAISS + síntesis LLM opcional
│           ├── 3_Keywords.py         ← editor estructurado de keywords.yml
│           ├── 4_Scopus_queries.py   ← editor de scopus_queries.yml
│           └── 5_DOI_manual.py       ← visor filtrable de doi_manual.xlsx
├── deployment/
│   └── com.research_agent.streamlit.plist   ← LaunchAgent del servicio Streamlit
├── logs/                             ← logs antiguos de scripts numerados
├── .gitignore
└── requirements.txt
```

## Scripts (orden de ejecución)

| Script | Función | Estado |
|---|---|---|
| `0_scopus_api.py` | Consulta Scopus Search API por categoría. Queries en `config/scopus_queries.yml` | ✅ |
| `1_rename_papers_by_doi.py` | Renombra PDFs via DOI + Crossref. Gestiona `doi_manual.xlsx` | ✅ |
| `2_screen_pdfs.py` | Clasifica PDFs en 8 categorías via keywords + Ollama | ✅ |
| `3_process_corpus.py` | PDF → TEI (GROBID) → MD clean → chunks JSONL | ✅ |
| `3a_download_pdfs.py` | Descarga PDFs desde CSV Scopus via Unpaywall + Elsevier API | ✅ |
| `3b_summarize.py` | Genera resúmenes con qwen3:14b | ✅ |
| `4_extract_metadata.py` | Extrae metadatos de TEI XML (título, DOI, autores, refs). Añade `stable_id`, `processed_date`, `source_type`, `download_source`, `download_url`, `access_type`, `download_date`. Arg `--source-type`. Verificado en producción 2026-05-27. | ✅ |
| `5_build_embeddings.py` | Genera índice FAISS con bge-m3 via Ollama | ✅ |
| `6_make_packages.py` | Crea paquetes NotebookLM (FULLTEXT, REFERENCES, INDEX) | ✅ |
| `7_make_master_index.py` | Genera MASTER_INDEX.md por categoría | ✅ |
| `8_query_rag.py` | Consultas RAG sobre índice FAISS (CLI) | ✅ |
| `9_cleanup_duplicates.py` | Detecta y elimina PDFs duplicados por DOI | ✅ |
| `pipeline.py` | Orquestador: cinco flujos (`run_scopus`, `run_inbox`, `run_adhoc`, `integrate_adhoc`, `promote_adhoc_to_category`). Helpers: `_copy_files_skip_existing()`, `_CANONICAL_CATEGORIES`. Importable por Streamlit | ✅ |
| `run_pipeline.py` | CLI del orquestador con subcomandos | ✅ |
| `streamlit_app/` | Interfaz web sobre el pipeline (ver sección dedicada) | ✅ |
| `utils/pdf_utils.py` | Funciones comunes (DOI, slugify, texto) | ✅ |

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
| `app.py` (portada) | Health checks en 2 filas: NAS / Ollama (+ latencia) / GROBID (+ latencia) + espacio libre NAS / bge-m3 disponible / permisos escritura NAS. Tabla de categorías con conteos (PDFs, pendientes, MD, resúmenes, chunks, metadata, FAISS, paquetes). |
| `1_Ingestar` | 4 tabs: **Scopus** / **Inbox** / **Pendientes** / **Ad-hoc**. Progreso en directo vía `on_output`. Pendientes: tabla de brechas por categoría con reprocesado selectivo. Ad-hoc: formulario + sección **🔗 Integrar ad-hoc en categoría** (selectbox origen/destino, checkbox borrar fuente, llama a `integrate_adhoc()`). |
| `2_RAG` | Búsqueda FAISS sobre cualquier proyecto+fase. Filtros por tipo y paper_id. Selector de provider (Ollama / Anthropic / OpenAI) y modelo. Toggle síntesis LLM con streaming. Pre-estimación de coste pre-query. Coste real post-query. Contador acumulado mensual en sidebar. |
| `3_Keywords` | Editor por textarea de `config/keywords.yml` (una keyword por línea, backup .bak automático) |
| `4_Scopus_queries` | Editor por categoría de `config/scopus_queries.yml` (multilínea, añadir/duplicar/borrar queries) |
| `5_DOI_manual` | Visor con filtros de `doi_manual.xlsx`, descarga CSV de vista filtrada |
| `6_Mantenimiento` | 4 secciones expandibles: **Backfill metadata** (detecta papers sin `stable_id`, re-ejecuta `4_extract_metadata.py` por categoría) / **Re-indexar FAISS** (multiselect categorías, todas por defecto, `--force bge-m3`) / **Limpieza de duplicados** (preview → apply condicional, con aviso de re-indexado) / **Reconstruir doi_registry** (llama a `build_doi_registry_from_nas()` directamente). Probada en producción 2026-05-27. |

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
| Plist en repo | `deployment/com.research_agent.streamlit.plist` |
| Instalado en | `~/Library/LaunchAgents/com.research_agent.streamlit.plist` |
| Etiqueta | `com.research_agent.streamlit` |
| Comando | `python3.13 -m streamlit run app.py …` (NO el shim `streamlit`) |
| Logs | `~/Library/Logs/research_agent/streamlit.{log,err.log}` |
| KeepAlive | true (reinicia automáticamente si se cae) |
| RunAtLoad | true (arranca al login) |

Comandos día a día:

```bash
# Estado
launchctl list | grep streamlit

# Log en vivo
tail -f ~/Library/Logs/research_agent/streamlit.log

# Parar / arrancar / recargar
launchctl bootout  gui/$(id -u)/com.research_agent.streamlit
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit.plist
```

### Acceso

- Mac mini (local): `http://localhost:8501`
- LAN (en casa): `http://192.168.0.17:8501`
- Fuera (con VPN casa activa): `http://192.168.0.17:8501`
- **NO** expuesto a internet (URL pública del router NO funciona — y bien que está)

## Configuración (config/.env)

```
OLLAMA_HOST=http://pciq22.uca.es:11434
OLLAMA_API_KEY=<clave>
GROBID_URL=http://pciq22.uca.es:8070
GROBID_TIMEOUT=600
UNPAYWALL_EMAIL=martin.ramirez@uca.es
ELSEVIER_API_KEY=<clave>
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

1. ~~**`0_scopus_api.py`**~~ ✅ — consulta Scopus API con queries personalizadas
2. ~~**Orquestador + ingesta continua**~~ ✅ — `pipeline.py` + `run_pipeline.py`
3. ~~**Interfaz web Streamlit**~~ ✅ — 5 páginas + servicio launchd 24/7
4. ~~**RAG multi-provider + cost tracking**~~ ✅ — Ollama / Anthropic / OpenAI con streaming y contador mensual
5. ~~**Re-embeddear con bge-m3**~~ ✅ — bge-m3 es el modelo de producción; `utils/constants.py` es la fuente de verdad
6. ~~**Mejorar editor keywords**~~ ✅ — textarea por categoría, una keyword por línea, sin dependencias extra
7. **Cron/launchd para ingesta semanal automática** — pendiente:
   ```bash
   0 6 * * 1  cd /Volumes/Disco/proyectos/research_agent/scripts && \
              /Users/martinramirez/venvs/rag_papers/bin/python run_pipeline.py scopus --recent-days 7
   ```
8. ~~**Procedencia PDFs + stable_id**~~ ✅ — `4_extract_metadata.py` con campos de provenance e identificador estable
9. **README.md global + docstrings** — documentación final de todos los scripts
9. **Mejoras UX menores** (según rozaduras de uso real):
   - ~~Editor `keywords.yml` — textarea por categoría (una keyword por línea)~~ ✅ (completado 2026-05-25)
   - Aviso visible cuando toggle síntesis RAG está OFF
   - Botones por fila en portada para procesar pendientes por categoría
   - Página de logs en vivo
   - Editor `doi_manual.xlsx` con `st.data_editor`

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
- `_CANONICAL_CATEGORIES` en `pipeline.py` es una copia deliberada de `app_utils.CANONICAL_CATEGORIES` — se duplica para evitar el import circular `app_utils → pipeline`. Si se añade una categoría, actualizar **ambos** sitios.
- `stable_id` en metadata: slug del DOI si existe, `paper_id` original si no. Campo estable independiente del nombre de fichero (item 16). Papers procesados antes del item 16 carecen de este campo — rellenar con página **6_Mantenimiento** → sección Backfill metadata.
- Procedencia en metadata: `source_type` (scopus/inbox/adhoc/manual), `download_source`, `access_type`, `download_url`, `download_date`, `processed_date`. Leído automáticamente de `descarga_cache.json` por DOI; arg `--source-type` para forzarlo (item 14). Verificado en producción 2026-05-27.
- `_copy_files_skip_existing(src, dst)` en `pipeline.py`: copia recursiva con `rglob`, skip por existencia de fichero, preserva subdirectorios. Usada por `integrate_adhoc()` y `promote_adhoc_to_category()`.
- `run_adhoc()` en `pipeline.py`: valida el nombre del proyecto con `re.fullmatch(r'^[a-z0-9_-]+$', name)` antes de crear directorios. Lanza `ValueError` si el nombre contiene espacios, mayúsculas o caracteres no permitidos.
- `integrate_adhoc(adhoc, target, delete_source)` en `pipeline.py`: copia pdfs/, md_clean/, summaries/, chunks/, metadata/ de un proyecto ad-hoc a una categoría canónica existente y re-indexa FAISS del destino. Los ficheros ya existentes se saltan.
- `promote_adhoc_to_category(adhoc, new_name, keywords, delete_source)` en `pipeline.py`: crea una nueva categoría canónica desde un ad-hoc copiando también embeddings/ y registrando keywords en `config/keywords.yml`. Valida nombre (`^[a-z0-9_]+$`) y que la categoría no exista previamente.

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
