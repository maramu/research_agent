# research_agent — Estado del proyecto

## Infraestructura

| Componente | Detalle |
|---|---|
| Mac mini M4 Pro (casa) | edición de código, acceso remoto — ya no ejecuta Streamlit ni pipeline |
| NAS (casa) | backup — /Volumes/research_bk |
| Mac mini Pro (UCA) (pciq22.uca.es) | máquina principal — scripts, Streamlit, datos, Ollama, GROBID |
| Scripts | `/Users/martinramirez/proyectos/research_agent/scripts/` |
| Config | `/Volumes/Disco/proyectos/research_agent/config/` |
| Venv | `~/venvs/rag_papers` (Python 3.13 via Homebrew /opt/homebrew/bin/python3.13) — **el venv bueno del proyecto**; ver nota abajo |
| GROBID | Docker (ARM64 nativo), imagen `grobid/grobid:0.9.0-crf`, compose en `~/grobid-compose.yml` |
| Ollama | Solo loopback (`127.0.0.1:11435`); remoto vía proxy Caddy con Bearer en `http://pciq22.uca.es:11434` — ver [Ollama — instalación en pciq22](#ollama--instalación-en-pciq22) |
| Streamlit | `http://<ip-pciq22>:8501` — servicio launchd 24/7 en pciq22 |
| GitHub | `https://github.com/maramu/research_agent` |

> ⚠️ **Venv de despliegue: `~/venvs/rag_papers`.** Es el que usan los
> LaunchAgents de Streamlit (privado/público) — cualquier cambio en
> dependencias de producción va ahí.
>
> **`.venv/` del repo (`research_agent/.venv/`) — recreado 2026-07-12.**
> Apuntaba a `python3.14` de Homebrew (symlinks rotos, ya desinstalado);
> recreado con `python3.13 -m venv .venv` (mismo Python que
> `~/venvs/rag_papers`) + `pip install -r requirements.txt`, sin errores.
> Es el venv para trabajo **ad-hoc en terminal** (`pytest`,
> `validate_metadata.py`, scripts sueltos) — NO lo usa ningún LaunchAgent;
> si se toca una dependencia de producción, replicar también en
> `~/venvs/rag_papers`.

### Hermes Agent (productividad personal)

> 🔴 **PAUSADO (2026-07-01) — auditoría de seguridad.** Estado actual: **INERTE /
> sin riesgo activo**. Contenedor parado y eliminado (`docker compose down`),
> token OAuth de Google revocado, LaunchAgents nativos archivados a `.disabled`.
> **NO reactivar con la configuración actual** — requisitos de reactivación en
> `Mejoras_pendientes.md` → item 49 → "REACTIVACIÓN". Motivo: credenciales
> sobreprivilegiadas y aislamiento insuficiente del contenedor (no fallos de la
> migración a Docker, que quedó técnicamente correcta). Detalle completo en
> `Mejoras_realizadas.md` → sesión 2026-07-01 (cont.).
>
> La tabla siguiente queda como **referencia histórica** de la configuración
> operativa previa a la pausa.

Instalado en pciq22, independiente del pipeline RAG. Gestiona agenda, correo,
Notion y búsqueda de noticias.

| Componente | Detalle |
|---|---|
| Instalación | `~/.hermes/` (persistente, montado como `/opt/data` en el contenedor) — migrado de LaunchAgent nativo (install.sh) a **Docker Compose** el 2026-07-01 (imagen oficial `nousresearch/hermes-agent`, definido en `~/hermes-docker`, fuera de este repo) |
| Provider default | **OpenRouter** (`google/gemini-3.5-flash`) — 1M ctx, barato, datos Gmail ya en Google; Gmail funcional vía OpenRouter (validado en Discord) |
| Provider alternativos | Anthropic (puntual), Nous Portal (dormido), DeepSeek V4 Flash (disponible vía OpenRouter), `ollama-local` (`http://host.docker.internal:11434/v1`, accesible en red desde el contenedor Docker desde 2026-07-01) |
| Compresión auxiliar | OpenRouter + `google/gemini-2.5-flash` (1M ctx, ~10x más barato que Haiku) |
| `context_length` / `num_ctx` | 64000 (mínimo duro de Hermes; 32000 lanza `ValueError`) |
| MCP Notion | 20 tools (HTTP OAuth, toolset `mcp-notion`) |
| MCP Google Calendar | 17 tools (stdio, toolset `mcp-google-calendar`). Token persistente fijado a `/opt/data/google-calendar-tokens.json` vía `GOOGLE_CALENDAR_MCP_TOKEN_PATH` (2026-07-01; antes no persistía entre reinicios del contenedor). Re-auth OAuth vía Docker no funciona (`ERR_EMPTY_RESPONSE`, el callback solo escucha en el loopback interno del contenedor) — auth real con `npx @cocal/google-calendar-mcp auth` nativo en el host (pciq22, escritorio remoto) |
| MCP Gmail | 64 tools (stdio, toolset `mcp-gmail`); whitelist `tools.include` = 7 tools solo lectura + draft (`get_label`, `list_labels`, `list_messages`, `get_message`, `list_threads`, `get_thread`, `create_draft`) — sin send/delete/trash/config. Wrapper `gmail-mcp-wrapper.sh` (dependía de `lsof`/`pkill`/binario Homebrew, no portable a Docker) sustituido el 2026-07-01 por `npx -y @shinzolabs/gmail-mcp` directo (mismo patrón que google-calendar) |
| SOUL.md | `~/.hermes/SOUL.md` (auto-inyectado) con "Reglas de Gmail" (contar con `get_label` y argumento `id: "UNREAD"` OBLIGATORIO; maxResults siempre; nunca includeBodyHtml) |
| Web search | Tavily (`TAVILY_API_KEY` en `.env`) |
| Keep-warm local | ~~Eliminado~~ — modelo local descartado para Hermes (qwen3:8b no viable con MCPs) |
| Seguridad | `code_execution`/`browser`/`computer_use` desactivados; **`terminal` activado desde 2026-07-01** con `backend: docker` (sandbox vía contenedor hermano, `/var/run/docker.sock` montado) — `docker_volumes` restringido a `~/hermes_workspace:/workspace` (rw) + `~/.hermes/cache/documents:/output`; verificado que no ve nada fuera de `/workspace` (probado explícitamente contra `/Users/martinramirez/proyectos/research_agent`); aprobación manual para acciones destructivas |
| Gateway 24/7 | **Docker Compose** (`~/hermes-docker`, imagen `nousresearch/hermes-agent`) desde 2026-07-01, reemplaza el LaunchAgent nativo; `ai.hermes.gateway` y `com.hermes.gateway.plist` (LaunchAgents nativos) ahora inertes — pendiente archivar tras verificar con `launchctl list \| grep hermes` que no sigan activos (riesgo de doble-gateway) |
| Logs | `~/.hermes/logs/{gateway,agent,errors}.log` |
| Estado | 🔴 PAUSADO 2026-07-01 (auditoría de seguridad) — hasta esa fecha: ✅ operativo desde Discord 24/7 — agenda, correo, Notion, noticias |
| Control | Discord gateway 24/7 vía LaunchAgent `ai.hermes.gateway`; se gestiona con `launchctl bootout/bootstrap`. |
| Acceso restringido | `DISCORD_ALLOWED_USERS` = solo el User ID propio (en `~/.hermes/config.yaml` y `~/.hermes/.env`). |
| Home channel | Fijado con `/sethome` a un Channel ID válido (entrega de crons y mensajes proactivos). |
| Conversaciones separadas | Tres canales temáticos en el servidor Hermes — `docencia`, `investigacion`, `noticias` — en `discord.free_response_channels` (responden sin @mención; contexto independiente por canal). Resto de canales siguen `require_mention: true`. |

**Migración a Docker (2026-07-01):** infraestructura de Hermes vive fuera de este
repo (`~/.hermes` + `~/hermes-docker`). Detalle completo en `Mejoras_realizadas.md`
→ sesión 2026-07-01.

- **Bugs de config arreglados** en `~/.hermes/config.yaml`: YAML roto (falta `:` tras
  `ollama-local`, caía a defaults en silencio); `custom_providers` en dict en vez de
  lista (schema real: lista con clave `name:`); rutas de credenciales Gmail/Calendar
  movidas de rutas absolutas del host a `/opt/data` (persistente).
- **Docker Desktop:** `docker compose pull` fallaba por SSH (keychain, hooks de
  Docker Scout — no `credsStore`). Resuelto con pull inicial vía escritorio remoto
  (sesión interactiva con acceso al keychain).
- **Verificado:** Gmail, Notion, Calendar operativos desde Discord; sandbox de
  terminal aislado confirmado (no ve nada fuera de `/workspace`); Ollama accesible
  en red vía `host.docker.internal`.
- **Incidencia sin cerrar:** con `qwen3:14b-hermes` (fine-tune Nous, item 49) y
  `context_length` 64000 confirmado, una pregunta que dispara tool
  (`get_current_time`, "qué día es hoy") se queda colgada sin error visible ni
  timeout — patrón distinto al bloqueo con error explícito ya documentado en el
  item 49 (`tool_call requires a name argument`). Sin diagnosticar si es la misma
  causa raíz manifestándose distinto en Docker o un problema nuevo de red (conexión
  Docker↔`host.docker.internal` muerta en silencio). Próximo paso: reproducir con
  `docker compose logs -f` en vivo + doble curl consecutivo directo a Ollama desde
  dentro del contenedor para descartar la capa de red.

**Nota RAM:** con la eliminación del modelo local de Hermes, Ollama solo gestiona
`qwen2.5:14b-instruct` (~9 GB) para síntesis RAG y `bge-m3` (~1.2 GB) para
embeddings. Sin competencia de RAM entre Hermes y el RAG. `OLLAMA_KEEP_ALIVE=5m`
en el plist de Ollama se mantiene como buena práctica.

**Limitación conocida:** el tool-calling local de Gmail queda **en espera del fix de
Rapid-MLX** (issues `#197`/`#344`, bug de streaming). Plan B probado (2026-06-28):
Rapid-MLX 0.9.7 + `Qwen3.5-9B-4bit` resuelve el tool-calling en no-streaming (curl OK,
exonera al modelo), pero en streaming NO promociona la tool-call a estructurado y
Hermes —que fuerza streaming sin opción de desactivarlo— recibe respuesta vacía.
Rapid-MLX instalado como LaunchAgent (`com.martin.rapidmlx`), parado o activo según
RAM, listo para reactivar el día del fix upstream. Mientras tanto Hermes usa OpenRouter
(Gmail funcional). Detalle en `Mejoras_realizadas.md` → sesión 2026-06-28 (cont.) y
backlog item 49.

> **Ollama 0.30.7 — NO actualizar** (su `/v1` funciona y v0.30.8 arrastra una fuga de
> KV-cache MLX conocida, issue #16698). Diagnóstico previo (ruta Hermes→`/v1` de Ollama,
> con modelo y Ollama exonerados por curl): `Mejoras_realizadas.md` → sesión 2026-06-27/28.

**Aprendizajes operativos Hermes:**
1. **Config:** editar `config.yaml` SOLO con `hermes config set` / `hermes setup`,
   NUNCA a mano (`sed`/edición manual erosiona y corrompe el fichero; una sesión llegó
   a perder el bloque `mcp_servers` entero). Backup explícito antes de cualquier sesión
   de cambios.
2. **Toolsets:** mantener los toolsets internos de Hermes ACTIVOS — desactivarlos en
   masa rompe el agente (son andamiaje del bucle de razonamiento, no opcionales). El
   control fino de tools se hace por MCP con `tools.include` (p.ej. Gmail 7 tools), no
   desactivando toolsets nativos.
3. **Higiene de pruebas:** tras cualquier cambio de config → `gateway restart`; antes
   de cada prueba limpia → `/reset` en Discord. Sin esto, los "funciona una vez y luego
   no" (contexto contaminado / config vieja en memoria) hacen los resultados no fiables.

**Pendiente residual:**
- Aplicar plist ingesta 04:00 en pciq22 (commit en repo hecho; falta
  `git pull` + `cp` + `launchctl bootout/bootstrap` en pciq22).
- Gmail MCP: si aparece error `EADDRINUSE` en `~/.hermes/logs/mcp-stderr.log`,
  ejecutar `pkill -9 -f "gmail-mcp" && hermes gateway restart`.
- Archivar `ai.hermes.gateway.plist` y `com.hermes.gateway.plist` (LaunchAgents
  nativos, inertes tras la migración a Docker) — verificar primero con
  `launchctl list | grep hermes` que no sigan activos (riesgo de doble-gateway
  compitiendo por `~/.hermes`).
- Diagnosticar cuelgue silencioso de `qwen3:14b-hermes` con tool-calling en Docker
  (`get_current_time`) — ver "Migración a Docker" arriba.

## Modelos Ollama disponibles

- `qwen2.5:14b-instruct` — síntesis RAG (modelo de producción, ~9 GB)
- `bge-m3` — embeddings FAISS (8192 ctx, 1024 dims, multilingüe) — **modelo de producción**

**`options` en las llamadas a `client.generate` (item 52/53, fix 2026-07-20):** sin `options`,
Ollama usa `num_ctx=4096` por defecto y trunca el prompt en silencio (system prompt + primeros
chunks descartados) — con top_k=8 y chunks de hasta 8000 chars se supera 4096 en consultas
normales; `apply_citations` post-procesa las `[N]` que el modelo sí menciona, así que la respuesta
truncada parecía correctamente citada. Las 5 llamadas del pipeline llevan ahora `num_ctx=16384`:
- `rag_core.py::stream_ollama`, `run_rag_batch.py::synthesize` y `pages/7_Revision.py:369`
  (`_stream_ollama`) — las tres rutas de síntesis con citas — `temperature=0.0` (determinismo;
  antes sin fijar → default 0.8 de Ollama).
- `3b_summarize.py::summarize_paper` — `temperature=0.3` (deliberada, prosa más natural en
  resumen; se preserva, solo se añadió `num_ctx`).
- `2_screen_pdfs.py` (clasificación JSON) — `temperature=0.1` (deliberada, casi determinista; se
  preserva, solo se añadió `num_ctx`).

Borrados en sesión 2026-06-26 (item 46 cerrado):
~~`qwen3:8b-hermes`~~ · ~~`qwen3:8b`~~ · ~~`qwen3:14b`~~ · ~~`gemma3:4b`~~ ·
~~`nomic-embed-text`~~ · ~~`mxbai-embed-large`~~ (si aplica)

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

> **Documentación del proyecto:**
> - **ESTADO.md** (este fichero) — estado y arquitectura actuales del proyecto.
> - **Mejoras_pendientes.md** — backlog vivo + orden de prioridad.
> - **Mejoras_realizadas.md** — histórico de trabajo completado (append-only, lo más nuevo arriba).
> - **Mejoras_copia20260612.md** — copia congelada del backlog original (referencia histórica).

```
research_agent/
├── config/
│   ├── .env                          ← claves API, hosts (NO subir a git)
│   ├── .env.example                  ← plantilla de variables (sí subir a git)
│   ├── keywords.yml                  ← palabras clave para cribado (8 categorías)
│   ├── scopus_queries.yml            ← queries Scopus por categoría
│   └── active_categories.yml         ← lista de categorías activas (excluye inactivas de Scopus/RAG)
├── scripts/
│   ├── pipeline.py                   ← orquestador (módulo importable)
│   ├── run_pipeline.py               ← CLI del orquestador (scopus/inbox/adhoc)
│   ├── run_weekly_scopus.py          ← ingesta semanal autónoma + email resumen
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
│   ├── agent_chat.py                 ← chat CLI con tool-calling (Obsidian, escritura solo en 00_Inbox)
│   ├── run_eval.py                   ← evaluación Hit@k / MRR contra golden sets (item 37)
│   ├── pool_candidates.py            ← pooling de candidatos → golden sets (item 37)
│   ├── utils/
│   │   ├── pdf_utils.py
│   │   ├── constants.py              ← Constantes compartidas (OLLAMA_MODEL_EMBED, CANONICAL_CATEGORIES,
│   │   │                               CANONICAL_SECTIONS, year_from_paper_id, MAX_EMBED_CHARS)
│   │   ├── retrieval.py              ← Funciones de recuperación: BM25 + RRF + filtros (item 33)
│   │   ├── citations.py              ← Citas: build_cite_map, apply_citations, attachment_citation_key()
│   │   │                               (campo _cite en metadata de chunks de adjunto → clave "Etiqueta; adjunto")
│   │   ├── attachments.py            ← Documentos efímeros (item 47): extracción pymupdf/txt/md,
│   │   │                               troceado simple en memoria, embedding al vuelo con bge-m3,
│   │   │                               búsqueda L2 en memoria, fusión "híbrido sensato" (cupo mínimo adjunto)
│   │   └── corpus_manifest.py        ← Genera/lee corpus_manifest.json por categoría
│   └── streamlit_app/                ← Interfaz web (Streamlit)
│       ├── app.py                    ← portada: health checks + tabla categorías
│       ├── app_utils.py              ← helpers compartidos (renombrado para no
│       │                               colisionar con scripts/utils/).
│       │                               Incluye check_password(), is_public_app()
│       ├── README.md                 ← instrucciones despliegue + launchd
│       └── pages/
│           ├── 1_Ingestar.py         ← scopus / inbox / adhoc con progreso live
│           ├── 2_RAG.py              ← retrieval FAISS + síntesis LLM opcional
│           ├── 3_Keywords.py         ← editor estructurado de keywords.yml
│           ├── 4_Scopus_queries.py   ← editor de scopus_queries.yml
│           ├── 5_DOI_manual.py       ← visor filtrable de doi_manual.xlsx
│           ├── 6_Mantenimiento.py    ← mantenimiento corpus (6 secciones)
│           ├── 7_Revision.py         ← revisión bibliográfica (5 prompts)
│           ├── 8_Exportar.py         ← exportar BibTeX/RIS/CSV por categoría
│           ├── 9_Actividad.py        ← actividad sistema (solo app privada)
│           ├── 10_Duplicados.py      ← revisión de duplicados + cuarentena reversible (privada)
│           ├── 11_Articulos.py       ← catálogo bibliográfico filtrable; editor DOI/Año/Autores/Revista + borrado reversible (solo privada)
│           └── 15_Pendientes.py      ← posponer 2 años DOIs pendientes sin interés/acceso (solo privada)
├── tools/                            ← tools de tool-calling, independientes de scripts/utils/
│   └── obsidian.py                   ← 4 tools Obsidian (lectura libre, escritura solo en 00_Inbox)
├── deployment/
│   ├── com.research_agent.streamlit.plist        ← LaunchAgent Streamlit privado (8501)
│   ├── com.research_agent.streamlit_public.plist ← LaunchAgent Streamlit público (8502)
│   ├── com.research_agent.scopus_weekly.plist    ← LaunchAgent ingesta semanal (lunes 06:00)
│   └── com.research_agent.daily_question.plist   ← LaunchDaemon pregunta diaria tiempo/mareas (06:00 todos los días) — excepción, ver abajo
├── logs/                             ← logs antiguos de scripts numerados
├── tests/                            ← suite pytest (item 39)
│   ├── conftest.py                   ← añade scripts/ a sys.path
│   ├── test_pdf_utils.py             ← DOI_REGEX, _clean_doi, slugify, strip_accents, normalize_stem
│   ├── test_rename.py                ← shorten_title, sanitize_filename (importlib desde 1_rename)
│   └── test_obsidian_tools.py        ← _validar_ruta_escritura / _sanitizar_nombre (24 tests, item Obsidian)
├── pytest.ini
├── .gitignore
└── requirements.txt
```

## Scripts (orden de ejecución)

| Script | Función | Estado |
|---|---|---|
| `0_scopus_api.py` | Consulta Scopus Search API por categoría. Queries en `config/scopus_queries.yml` | ✅ |
| `1_rename_papers_by_doi.py` | Renombra PDFs via DOI + Crossref. Gestiona `doi_manual.xlsx`. **2026-06-09**: nueva fuente DOI `--doi-csv`. **2026-06-13 (item 44):** lookup robusto en `doi_manual`: además de clave exacta, indexa por `normalize_stem(stem)` y `normalize_title(título_extraído)`; normaliza DOI antes de llamar a Crossref (`normalize_doi` — barra final → no más 404 para `10.1002/bit.26092/`); handler HTTPError conserva el fichero si hay DOI válido (no mueve a fallidos). | ✅ |
- Eliminada `DOI_REGEX` duplicada y funciones `clean_doi`, `extract_doi_from_text`, `extract_doi_from_pdf` — ahora importa desde `utils.pdf_utils` (commit d1ea84d)
| `2_screen_pdfs.py` | Clasifica PDFs en 8 categorías via keywords + Ollama | ✅ |
| `3_process_corpus.py` | PDF → TEI (GROBID) → MD clean → chunks JSONL. **2026-06-10 (item 32)**: campo `section_canonical` en cada chunk con herencia jerárquica de heading — `split_by_headings()` devuelve nivel del heading; `build_chunk_records()` mantiene mapa ancestros `nivel→canonical` y sube niveles hasta encontrar una etiqueta que no sea "other". 7 etiquetas: `abstract \| introduction \| methods \| results \| discussion \| conclusion \| other`. Chunks de tabla: `section_canonical="table"`. El campo `section` (título hoja crudo) queda intacto. Commit b097744. **2026-06-11**: chunks capados a `MAX_EMBED_CHARS` vía `_split_to_max_chars` (texto y TABLAS, que antes se emitían enteras); `section_part` añadido a registros de tabla. | ✅ |
| `3a_download_pdfs.py` | Descarga PDFs desde CSV Scopus via Unpaywall + Elsevier API. **Bug fix 2026-06-09**: doi_registry check corregido (`_line.strip().split("\t")[0].lower()` — el fichero tiene formato `doi\tcategory/filename`; antes el split tab faltaba y nunca detectaba duplicados ya en corpus). **Fix 2026-06-14**: el skip por doi_registry añade resultado con status `SKIPPED_CORPUS` (fuera de `pending_mask`) → las filas ya-en-corpus dejan de filtrarse a pendientes y no descuadran `save_results` (antes el `continue` sin append rompía la alineación posicional). | ✅ |
| `3b_summarize.py` | Genera resúmenes con qwen3:14b | ✅ |
| `4_extract_metadata.py` | Extrae metadatos de TEI XML (título, DOI, autores, refs). Añade `stable_id`, `processed_date`, `source_type`, `download_source`, `download_url`, `access_type`, `download_date`. Arg `--source-type`. Verificado en producción 2026-05-27. **2026-06-11**: extrae **revista** del TEI (`monogr/title[@level='j']` + fallback) al campo `journal`; **fallback de DOI** a `doi_manual.xlsx` cuando el TEI no lo trae (por nombre de archivo y título normalizado); **preserva** `doi`/`journal` previos no vacíos al reextraer (no los machaca con vacío del TEI, backup `.bak`); **salta TEI huérfanos** sin `md_clean` correspondiente (imprime la lista) para no generar papers fantasma. **2026-06-13**: preservación generalizada a `title`/`doi`/`journal`/`year`/`authors` (`PRESERVE_FIELDS`) para que las correcciones manuales desde el editor de Artículos sobrevivan a una re-extracción; un campo vacío/ausente previo fuerza refresco desde el TEI. **2026-06-13**: fallback de `journal` vía Crossref por DOI cuando ni el TEI ni el registro previo traen revista. Ver `Mejoras_realizadas.md`, sesión de hoy. | ✅ |
| `5_build_embeddings.py` | Genera índice FAISS con bge-m3 via Ollama. **Modo incremental por defecto**: solo embeddea papers nuevos (no en `indexed_papers.json`); `--force` para re-indexar todo desde cero. **2026-06-11**: escribe `year` en metadata.jsonl (denormalizado desde `papers_metadata.jsonl` + fallback regex); `embed_texts` con truncado reactivo ante exceso de contexto. | ✅ |
| `6_make_packages.py` | Crea paquetes NotebookLM (FULLTEXT, REFERENCES, INDEX) | ✅ |
| `7_make_master_index.py` | Genera MASTER_INDEX.md por categoría | ✅ |
| `8_query_rag.py` | Consultas RAG sobre índice FAISS (CLI). **2026-06-11**: nuevos flags `--sections`, `--year-start`/`--year-end`, `--hybrid`. | ✅ |
| `run_rag_batch.py` (NUEVO, **2026-07-09**) | Batería de consultas RAG desatendida (headless, sin Streamlit). Lee un YAML (`--config`) con `category`/`phase`/`top_k`/`hybrid`/`sections`/`model` (síntesis Ollama) y una lista de `questions` (override opcional de `sections` por pregunta). Reutiliza VERBATIM `load_metadata`/`embed_query` y el ensamblado de recuperación (denso + BM25/RRF + filtros) de `8_query_rag.py`, y la plantilla `system_content` de `synthesize_answer` (`2_RAG.py`) — sin importar de ninguno de los dos, para no arrastrar `streamlit`. Por pregunta: recupera chunks, sintetiza con `ollama.generate` (modelo del YAML), aplica `apply_citations`/`build_cite_map` de `utils/citations.py`, serializa los chunks con `utils/export_refs.build_chunks_markdown`, y escribe `NN_<slug>.md` (respuesta + chunks) en `/Volumes/research/exports/rag_batch_<category>_<YYYYMMDD_HHMM>/`. Un fallo por pregunta escribe `NN_<slug>.ERROR.md` con el traceback y continúa con la siguiente (no aborta la batería). No registra en `rag_usage_*.jsonl`. Ejemplo en `scripts/ejemplos/rag_batch_ejemplo.yml`. **2026-07-09 (cont.)**: la lógica de carga + bucle se extrajo a `run_batch(cfg, base=DEFAULT_BASE, progress_cb=None) -> {"out_dir","results","n_ok","n_err"}` (comportamiento y salida por consola idénticos; `main()` = argparse→YAML→`run_batch`); `progress_cb(i,n,question,status,out_path)` opcional se llama tras cada pregunta. Lo reutiliza la página `13_RAG_multiple.py` sin duplicar lógica. Sigue headless (sin `streamlit`/`app_utils`). **2026-07-10**: `synth_timeout` configurable en el YAML (`cfg.setdefault("synth_timeout", 600)`) — sustituye el `timeout=300` fijo del cliente Ollama; como embed y síntesis comparten el mismo `ollama.Client`, el timeout se aplica a ambos (el embed es rápido y no se ve afectado en la práctica). Formato de cabecera del .md sin cambios (byte-compatible con lo validado el 2026-07-09). | ✅ |
| `agent_chat.py` (NUEVO, **2026-07-09**) | Chat CLI con tool-calling nativo (`ollama.chat(tools=[...], think=False)`) contra Ollama local. Lee todo el vault de Obsidian y escribe SOLO en `00_Inbox/` a través de las 4 tools de `tools/obsidian.py` (importadas sin modificar) vía el plugin Local REST API de Obsidian. Flujo independiente del RAG/embeddings del proyecto: no toca FAISS ni `8_query_rag.py`; para contexto usa solo las tools de lectura (`leer_nota`, `buscar_en_vault`). Modelo por defecto `qwen3:8b` sin thinking; comando `/model <nombre>` cambia el modelo activo en caliente (p. ej. a `qwen3:14b`) sin reiniciar el historial. Confirmación humana `[s/N]` con vista previa completa (ruta + frontmatter + contenido) antes de cada escritura, flag `--yes`/`--no-confirm` para desactivarla en pruebas; límite de 8 rondas de tools por turno; comandos `/salir`, `/multi`, `/nuevo`, `/model`. | ✅ |
| `tools/obsidian.py` (NUEVO, **2026-07-09**) | Cliente HTTPS mínimo contra el plugin Local REST API (with MCP) de Obsidian (`https://127.0.0.1:27124`, autofirmado, Bearer token en `config/.env.obsidian`, aislado del `.env` general igual que `config/.env.caddy_ollama`). 4 tools: `leer_nota`/`buscar_en_vault` (lectura sin restricción de carpeta) y `crear_nota_inbox`/`anexar_a_nota_inbox` (escritura SOLO en `00_Inbox/`). La garantía real es a nivel de código: `_validar_ruta_escritura` rechaza rutas fuera de `00_Inbox/`, con `..`, absolutas, o con extensión distinta de `.md`; el saneado de nombre rechaza explícitamente `/`, `\`, `..` en vez de neutralizarlos en silencio. Sin tools de borrado ni de movimiento. `crear_nota_inbox` no sobrescribe (sufijo de fecha/hora si el nombre ya existe) y añade siempre el tag `origen-agente` al frontmatter de la convención del vault (`type`, `titulo`, `creado`, `actualizado`, `estado`, `tags`, `fuente`). | ✅ |
| `tests/test_obsidian_tools.py` (NUEVO, **2026-07-09**) | 24 tests de `_validar_ruta_escritura`/`_sanitizar_nombre` (rutas válidas/rechazadas, saneado de nombre) y de las tools de escritura reales lanzando `PermissionError` antes de tocar la red. Verificado también contra Obsidian real (lectura, búsqueda, creación con frontmatter, no-sobrescritura, rechazo humano, adversarial vía modelo) y con Obsidian cerrado (error claro, sin traceback ni cuelgue). Suite total del repo: 168/168 en verde. | ✅ |
| `9_cleanup_duplicates.py` | Detecta y elimina PDFs duplicados por DOI. Detección avanzada por título normalizado (solo grupos donde todos los papers comparten DOI o carecen de él — grupos con ≥2 DOIs distintos se ignoran como artículos diferentes) y hash SHA-256 con informe `metadatos/duplicate_report.xlsx` (3 hojas: DOI/Titulo/Hash). **2026-06-09**: nueva función `apply_hash_cleanup()` — `--apply` ahora elimina también duplicados por hash PDF (no solo DOI); desempate por nombre limpio Crossref. **2026-06-11**: nueva función `quarantine_paper()` — cuarentena REVERSIBLE que mueve PDF + artefactos a `/Volumes/research/quarantine/duplicates/<ts>/` con `_manifest` y quita la línea del paper de `papers_metadata.jsonl` (backup `.bak`). Usada por la página Duplicados (`10_Duplicados.py`). Commit fb320a9. **2026-06-12 (item 42):** copy2→copy en `rewrite_metadata`. **2026-06-17**: `quarantine_paper()` añade `"meta_lines"` al manifiesto; nueva `restore_from_quarantine(manifest_path, base)` — invierte la cuarentena (shutil.move, sin sobrescribir), reinerta `meta_lines` en `papers_metadata.jsonl` con dedup por `file_key` y backup `.bak`, warning si manifiesto legacy sin `meta_lines`. | ✅ |
| `utils/corpus_manifest.py` | Genera `corpus_manifest.json` por categoría: n_pdfs, n_chunks, quality_score, faiss_indexes, faiss_stale, keywords_hash, git_commit. CLI + API pública `read_manifest()` | ✅ |
| `utils/retrieval.py` (NUEVO, item 33, 2026-06-11) | Funciones de recuperación: `dense_rank`, `bm25_rank`, `rrf_fuse` (RRF_K=60), `passes_filters` (centraliza filtros items 32/34), `pool_size`, `build_bm25`, `tokenize`. BM25 al vuelo desde metadata.jsonl, alineado con FAISS por orden. | ✅ |
| `utils/constants.py` | Constantes compartidas. **2026-06-11**: añadidas `CANONICAL_SECTIONS`, `year_from_paper_id`, `MAX_EMBED_CHARS` (junto a `OLLAMA_MODEL_EMBED`, `CANONICAL_CATEGORIES`). | ✅ |
| `pipeline.py` | Orquestador: cinco flujos (`run_scopus`, `run_inbox`, `run_adhoc`, `integrate_adhoc`, `promote_adhoc_to_category`). Helpers: `_copy_files_skip_existing()`. `_CANONICAL_CATEGORIES` importado de `utils/constants.py`. Importable por Streamlit. **Fixes 2026-06-09**: (1) `run_scopus()` llama a `build_doi_registry_from_nas()` antes del bucle de categorías; (2) `run_scopus()` pasa `--doi-csv` al paso de renombrado; (3) `run_inbox_process()` añade paso de renombrado antes de `detect_affected_categories()`. **2026-06-12 (item 42):** copy2→copy en `_copy_files_skip_existing`; eliminado el fallback inline de `_CANONICAL_CATEGORIES`; regex de `promote_adhoc_to_category` alineado a `[a-z0-9_-]+`. **2026-06-13:** puerta de dedup por DOI — `screen_new_pdfs_against_corpus()` + `build_doi_registry_from_nas()` reescrito + `detect_affected_categories()` con `normalize_stem`. **2026-06-13 (poda metadata):** `_META_STEM_FIELDS`, `_META_STEM_SUFFIXES`, `_record_stem()` y `prune_orphan_metadata()` — detecta/elimina registros de `papers_metadata.jsonl` sin `md_clean` (papers fantasma); reversible con `.bak` + `_orphans_<ts>.jsonl` + `_orphans_per_paper_<ts>/`. **2026-06-13 (poda TEI):** `prune_orphan_tei()` — detecta/mueve a cuarentena ficheros `tei/*.tei.xml` sin `md_clean` correspondiente; reversible en `quarantine/orphan_tei/<ts>/<cat>/`. Ver `Mejoras_realizadas.md`, sesión de hoy. | ✅ |
| `run_pipeline.py` | CLI del orquestador con subcomandos | ✅ |
| `streamlit_app/` | Interfaz web sobre el pipeline (ver sección dedicada) | ✅ |
| `utils/pdf_utils.py` | Funciones comunes (DOI, slugify, texto). **2026-06-13 (item 39):** `normalize_stem()`. **2026-06-13 (item 44):** `normalize_doi(doi)` — strip/prefijo/barra final; `_clean_doi` conservador: ya no recorta sufijos de 3+ letras salvo que sigan directamente a un dígito (`(?<=\d)[a-zA-Z]{3,}$`); el DOI `10.1000/xyz` y similares quedan intactos; `10.1023/B:HYDR.0000008620.87704.3b` soportado por `DOI_REGEX` y `_clean_doi`. | ✅ |
- `DOI_REGEX` ampliado para capturar `<`, `>` en DOIs Wiley/ACS SICI antiguos (commit 95c119f)
- `_clean_doi` ampliado con dos pasos: paso Wiley/ACS `(-[a-zA-Z])[a-zA-Z]{2,}$` para anclar sufijo legítimo + paso general `[a-zA-Z]{3,}$` para eliminar texto alfabético pegado al final del DOI (commit 2483494)
| `utils/crossref.py` (NUEVO, Nivel 2, 2026-07-04) | Fetcher canónico `fetch_work(doi) -> dict\|None` del endpoint `works/<doi>` de Crossref. Normaliza salida `{title, authors:[{family,given}], journal, journal_short, year}`; `year` (**2026-07-04**, helper `_pick_year`) con preferencia **published-print → published-online → issued → published** (print = año de publicación citable; `issued` es el mínimo de fechas Crossref/online temprano, y published-online puede ser digitalización tardía — caso Wise print=1978/online=2004); ignora entradas de organización (sin `family`); 404/DataCite/no-JSON → None; caché en memoria por DOI + `sleep(0.1)`; `mailto=UNPAYWALL_EMAIL`. `_crossref_journal` de `4_extract_metadata.py` ahora DELEGA en este fetcher (contrato str preservado). NO confundir con `crossref_suggest` de `11_Articulos.py` (endpoint search por título). | ✅ |
| `utils/download_registry.py` | Registro persistente de DOIs pendientes de descarga (pendientes_descarga.csv). **2026-07-12**: columna `snooze_until` (migración automática vía `load()` — CSVs antiguos sin la columna la rellenan a `""`) + `pending_active(df, today=None)` (fuente única de "qué es un pendiente activo": `status=="pending"` y snooze vacío o vencido, usada por `run_weekly_scopus.py` y por `15_Pendientes.py` para que no diverjan) + `snooze(dois, years=2, note="")` / `unsnooze(dois)`. `upsert()` no toca `snooze_until` en filas existentes (snooze-safe: la ingesta Scopus no des-pospone). **2026-07-12 (cont.):** `reconcile_with_corpus(categorias_dir=None)` — `mark_downloaded()` solo la llama `3a_download_pdfs.py`, así que un DOI ingestado por otra vía (PDF subido a mano) se quedaba `pending` para siempre aunque el paper ya existiera; esta función cruza los DOI `pending` contra `papers_metadata.jsonl` de todas las categorías y los marca `downloaded`. Corre automática en `15_Pendientes.py` y en `run_weekly_scopus.py`. Ejecutada contra el NAS real: 37 reconciliados (34 de 35 "pendientes activos" ya estaban en el corpus). | ✅ |
| `utils/export_refs.py` | BibTeX/RIS/CSV + ZIP papers (`build_papers_zip` con fallback año+autor: paper_id exacto → stable_id desde jsonl → glob prefijo 20 chars) + `build_chunks_markdown` (serializa los chunks recuperados a un único .md con referencia bibliográfica completa por chunk, para citar desde un LLM externo) | ✅ |
| `streamlit_app/pages/7_Revision.py` | Revisión bibliográfica: 5 prompts especializados, streaming 3 providers, ZIP+BibTeX papers usados, guardar nota NAS | ✅ |
| `streamlit_app/pages/8_Exportar.py` | Exportar bibliografía por categoría: filtros año/DOI/quality, BibTeX/RIS/CSV descargables | ✅ |
| `streamlit_app/app_public.py` (portada pública, puerto 8502) | `st.navigation` con 3 páginas: RAG + Revisión bibliográfica + **Artículos** (catálogo bibliográfico filtrable; en la app pública sin la gestión de DOIs, que es privada). Autenticación con `check_password("PUBLIC_APP_PASSWORD")`. Solo Ollama disponible (filtrado en `2_RAG.py` con `is_public_app()`). | ✅ |
| `validate_metadata.py` + `utils/metadata_validation.py` | QA de metadata **Nivel 1** (heurísticas locales, sin red). Detecta registros de `papers_metadata.jsonl` con metadata degradada (título==revista o prefijo de revista, autores pegados camelCase o contaminados con afiliación/dígitos, año/DOI implausibles). Escribe sidecar `metadata/validation_<cat>.jsonl` (solo los flagged; sobrescribe). **SOLO LECTURA** sobre `papers_metadata.jsonl` — nunca lo modifica. CLI `--category <cat>` (repetible) / `--all`; resumen por categoría con desglose por code y cuántos flagged tienen DOI (arreglables con Crossref en Nivel 2). Constante TUNABLE `AFFILIATION_TOKENS`. **2026-07-04 (ajuste tras datos reales):** `authors_glued` reclasificado a severidad `"info"` — `forename`/`surname` vienen vacíos en TODO el corpus (solo `full` pegado), así que marcaba ~99% de papers, verdadero pero inútil como triaje; su reparación es sistémica vía Crossref (Nivel 2). El sidecar solo admite issues de severidad `medium`/`high` (`SIDECAR_MIN_SEVERITY`); los `info` se listan si el paper ya entró por otro motivo pero no lo flaggean solos. El desglose del CLI muestra el volumen de `authors_glued` etiquetado `[info, no cuenta]`. **Nivel 2 (Crossref por DOI) 2026-07-04:** `compare_with_crossref(rec, fetch)` contrasta título/revista/año/autores contra `works/<doi>` y SUGIERE (no sobreescribe); codes `title_recover`/`title_mismatch`/`journal_mismatch`/`journal_fill`/`year_mismatch`/`authors_mismatch`/`crossref_miss` con `kind ∈ {mismatch,recover,fill,miss}`. `validate_category_crossref(...)` enriquece el sidecar con bloque `crossref:{fetched,issues}`; un paper entra si Nivel 1 medium/high O crossref con kind mismatch/recover/fill. CLI: flags `--crossref` (default OFF) y `--limit N`. Año (**fix 2026-07-04**): Crossref es la fuente CANÓNICA — con `cr.year` presente y distinto del local se emite `year_mismatch` `suggested_source="crossref"` (severity `low` si |delta|==1, desfase print/online; `medium` si >=2); `year_from_paper_id` queda como FALLBACK solo cuando Crossref no resuelve (miss) o no trae año (antes el orden invertido + un corte `cr_year != pid_year` hacían que el 100% de los mismatches saliera etiquetado paper_id y nunca se comparara contra Crossref). **2026-07-12 (item 51, "mantener campo"):** `validate_category()`/`validate_category_crossref()` aceptan `dismissed: set[(paper_id, field)]` (de `utils/validation_overrides.py`) y descartan esos issues ANTES de decidir si el paper entra al sidecar; `validate_metadata.py` carga `dismissed_set(category)` por categoría y lo pasa a ambas. Así los campos que el usuario ya revisó y marcó "verificado" desde `11_Articulos.py` no vuelven a entrar al sidecar en el origen. **2026-07-12 (cont.):** `validate_category_crossref` ahora también flaggea un paper cuyo ÚNICO issue es `crossref_miss` (antes solo `kind ∈ {mismatch,recover,fill}` — un DOI correcto no resuelto en Crossref sin ningún otro problema era invisible en el sidecar y en el resumen CLI). Round-trip verificado contra el NAS real (ver `Mejoras_realizadas.md`). | ✅ |
| `utils/validation_overrides.py` (NUEVO, **2026-07-12**) | Registro persistente de campos "verificados, no volver a sugerir" para la validación de metadata: `/Volumes/research/metadatos/validation_overrides.csv`, columnas `category, paper_id, field, date, note`. `field ∈ {title, journal, year, authors, doi}` (**`doi` añadido 2026-07-12**: cubre `crossref_miss` — DOI correcto no resuelto en Crossref; mantenerlo no cambia el valor del DOI, solo silencia el aviso). `dismiss()`/`undismiss()` (upsert idempotente), `dismissed_set(cat) -> {(paper_id, field)}` (lookup O(1) usado por el validador y por `11_Articulos.py`), `list_dismissed(cat)` para auditar/revertir. Deliberadamente NO se guarda dentro de `papers_metadata.jsonl` (un flag ahí se podría perder en la próxima re-extracción TEI, que solo protege `PRESERVE_FIELDS`). | ✅ |
| `run_weekly_scopus.py` | Ingesta Scopus semanal autónoma. Ejecuta `run_scopus(WEEKLY_CATEGORIES, recent_days=7, year_start=año_actual-1)` con `WEEKLY_CATEGORIES = ["biogas_upgrading_biomethanation", "anoxic_biogas_biodesulfurization", "bioplastics_microplastics"]` (3 categorías). **Envía un email HTML independiente por cada categoría** (subject: `[research_agent] {cat} — {fecha} — N nuevos / M pendientes`; DOIs pendientes filtrados por categoría). `build_html()` deprecated; reemplazada por `build_html_single_cat()` + `send_category_emails()`. Fallback: si falla el envío de una categoría, loguea y continúa con las demás; los HTML fallidos se concatenan en `/tmp/`. Timeout 90 min via `ThreadPoolExecutor` + `future.result(timeout=5400)`. Logging a fichero + stdout. `--dry-run` imprime HTML por categoría. Config SMTP desde `.env`. **2026-07-12:** `_load_pending_dois()` llama primero a `download_registry.reconcile_with_corpus()` para que el email no arrastre DOIs ya ingestados por vías fuera de `3a_download_pdfs.py`. | ✅ |

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

## Pipeline de libros de docencia (item 31)

Pipeline **paralelo** al de artículos para libros de texto docentes, reutilizando
bge-m3 + FAISS + Streamlit. NO usa GROBID (solo PDF de texto extraíble).

**Layout NAS** — bajo `/Volumes/research/libros_docencia/` (fuera de `categorias/`):
`pdfs/ md_clean/ chunks/ embeddings/ metadata/ logs/`.

**Scripts** (`scripts/books/`):
- `process.py` — PDF → texto por página con **PyMuPDF**; TOC vía `doc.get_toc()`
  (fallback a detección de encabezados por tamaño de fuente, marcado
  `toc_source="heuristic"`). Limpieza: une guiones de fin de línea, elimina
  cabeceras/pies recurrentes (detección posicional en bordes) y números de página
  sueltos, re-fluye párrafos. **Ordena las entradas del TOC por página** antes de
  segmentar (evita rangos corruptos por bookmarks desordenados). **Salta el
  front/back matter** (índice, prefacio, etc.) para no trocear ruido. Si el PDF no
  tiene texto → `text_extractable=false` (candidato a OCR, no se procesa).
  Idempotente por sha256 del fichero de chunks; `--force` reprocesa.
- `embed.py` — índice bge-m3/FAISS **propio** en `embeddings/all/`, reutilizando el
  núcleo de embedding compartido (`utils/embeddings.py`, mismo que artículos).
  Incremental por hash de libro (`indexed_books.json` + caché `_vectors/*.npy`) con
  **borrado**: un libro que cambia re-embebe y sus vectores viejos desaparecen; uno
  eliminado sale del índice. **Preserva el `year`** del chunk (no lo recalcula).
- `query.py` — wrapper fino sobre `8_query_rag.py` (`--project libros_docencia`),
  retrieval puro sin LLM.

**Esquema de chunk de libro**: `paper_id=book_id`, `doc_type="book"`,
`heading_path` (ruta de capítulo), `page_start`/`page_end` (página **física** del
PDF), `section_canonical="chapter"` (centinela, NO en `CANONICAL_SECTIONS` → los
libros no se filtran por IMRaD), `year` **denormalizado** desde
`libros_metadata.jsonl`, `chunk_hash`. Metadata de libro en
`metadata/libros_metadata.jsonl` (título/autor/año/isbn/sha256/quality_score/toc);
título/autores se derivan del nombre de archivo (`AÑO_Autor_Título`) cuando el PDF
no es fiable. Se deriva `papers_metadata.jsonl` para que citas y año funcionen sin
tocar el código de artículos.

**Citas de libro**: `citation_for_chunk()` (en `utils/citations.py`) despacha por
`doc_type`: libro → `Autor (Año), <Libro>, cap. <N>, p. <inicio-fin>`; artículo →
`(Apellido, Año; DOI)` como siempre. `passes_filters` admite filtrar por `doc_type`.

**Página "Preparar clase"** (`streamlit_app/pages/14_Preparar_clase.py`, solo app
privada): recupera de libros + categorías de papers y **fusiona con cupo mínimo
garantizado para libros** (mismo patrón que los adjuntos, `fuse_results`); sintetiza
**contrastando manual↔papers** ("según el manual …; los papers recientes matizan …")
con citas en su formato, y distingue 📘 libro vs 📄 paper en el panel. El núcleo RAG
(índices, proveedores, síntesis, export) se extrajo a `streamlit_app/rag_core.py`,
compartido con `2_RAG.py` (cero duplicación).

**Estado**: MVP funcional con **2 libros indexados** (Najafpour 2007,
*Biochemical Engineering and Biotechnology*, 439 pág → **153 chunks**; Burstein
2011, *MATLAB in Bioscience and Biotechnology*, 248 pág → **56 chunks**; dim 1024;
209 vectores). **Evaluación formal Hit@k/MRR pendiente** (falta golden manual).

**Nota TOC tipo fichero (fix 2026-07-11)**: libros ensamblados de PDFs sueltos
traen el TOC con los nombres de fichero como etiquetas (`"Chapter 1.pdf"`,
`"Prelims.pdf"`…). `normalize_toc_title()` retira el sufijo `.pdf` al leer el TOC,
así que `heading_path`/`section`/`toc` quedan con el título real; `prelims`/`index`
se saltan como front/back matter; apéndices se conservan como contenido pero no
cuentan en `n_chapters` (`count_chapters()`). Los libros de código (MATLAB) disparan
el **truncado reactivo** de `embed_texts` (chunks muy densos en tokens): es
esperado y NO afecta al texto guardado en `metadata.jsonl`/`md_clean`.

## Interfaz web (Streamlit)

Todos los flujos del pipeline son accesibles desde la web, además de
herramientas adicionales (RAG, editores de configuración, visor de DOIs).

| Página | Función |
|---|---|
| `app.py` (portada) | Health checks en 2 filas: NAS / Ollama (+ latencia) / GROBID (+ latencia) + espacio libre NAS / bge-m3 disponible / permisos escritura NAS. Tabla de categorías con conteos (PDFs, pendientes, MD, resúmenes, chunks, metadata, FAISS, paquetes). Filas de categorías inactivas en gris (`df.style.apply`). **Banner de backup** (solo app privada): aviso si `last_backup.json` no existe o la última copia tiene >15 días. |
| `1_Ingestar` | 4 tabs: **Scopus** / **Inbox** / **Pendientes** / **Ad-hoc**. Progreso en directo vía `on_output`. Pendientes: tabla de brechas por categoría con reprocesado selectivo. Ad-hoc: formulario + sección **🔗 Integrar ad-hoc en categoría** (selectbox origen/destino, checkbox borrar fuente, llama a `integrate_adhoc()`). Auto-recuperación de estado Inbox al inicio: si `cribado_pendiente.csv` existe en disco (p.ej. tras reinicio launchd), restaura `session_state` y muestra toast. Tab Pendientes: botón 📝 Renombrar PDFs por DOI por categoría (ejecuta `1_rename_papers_by_doi.py --folder categorias/<cat>/pdfs --apply`; PDFs sin DOI se registran en `doi_manual.xlsx`). Usar antes de Reprocesar cuando se copian PDFs con nombres sucios directamente a `pdfs/`. Botón 📝 Renombrar PDFs por DOI protegido: salta PDFs que ya tienen md_clean correspondiente, procesando solo PDFs realmente nuevos. Log persistente en NAS (`ingesta_en_curso.log` → `ingesta_history/`) con recuperación automática al reconectar. |
| `2_RAG` | Búsqueda FAISS sobre cualquier proyecto+fase. Filtros por tipo y paper_id. Selector de provider (Ollama / Anthropic / OpenAI / OpenRouter) y modelo. Toggle síntesis LLM con streaming. Pre-estimación de coste pre-query. Coste real post-query (OpenRouter registra el coste real devuelto por la API, sin precios estáticos en `LLM_PRICING`). Contador acumulado mensual en sidebar. Log completo de consultas en `metadatos/rag_queries/rag_queries_YYYY-MM.jsonl` (11 campos: pregunta, papers recuperados, respuesta, costes, `mode`). Botón "💾 Guardar como nota" → `notas_rag/<proyecto>/YYYY-MM-DD_<proyecto>_<slug>.md`. Patrón flag+`st.rerun()` para persistencia entre reruns de Streamlit. Expander "📦 Exportar papers recuperados": ZIP en memoria con PDFs y/o md_clean de los papers recuperados (fallback año+autor para PDFs renombrados por Crossref). Botón guardar nota movido al bloque de síntesis (fix rerun). **2026-07-04**: botón nuevo e independiente "⬇️ Descargar chunks (Markdown)" (`_render_chunks_export`, junto al ZIP en el flujo principal y en el bloque premium): descarga TODOS los chunks recuperados en un único .md con la referencia bibliográfica completa por chunk (título, autores, año, revista, DOI, paper_id, sección, tipo, score) vía `build_chunks_markdown` en `utils/export_refs.py`, pensado para alimentar un LLM externo que deba citar. **2026-06-11**: multiselect de Secciones (item 34), filtro de año opt-in, toggle "Recuperación híbrida (denso+BM25)" OFF por defecto (`load_bm25` cacheado por mtime), etiqueta rrf/dist en resultados. **2026-06-16 (item 47)**: uploader de documentos efímeros (PDF/txt/md) + text_area para pegar texto; etiqueta de cita configurable + cupo mínimo de chunks del adjunto (default 3); caché por hash SHA-256 en `st.session_state` (re-preguntar sobre el mismo adjunto no re-embebe); cita sintética `(Etiqueta; adjunto)` vía `utils/attachments.py` + `utils/citations.py`. **2026-06-23**: bloque "🔎 Profundizar (modelo de pago)" — solo app privada (`is_public_app()`), visible solo si hay consulta previa con artículos rescatados. Lanza una segunda consulta con provider de pago (Anthropic/OpenAI/OpenRouter) sobre lo ya rescatado por el modelo local: Modo A "mismos fragmentos" (no toca FAISS, coste mínimo) o Modo B "profundizar en estos papers" (re-consulta FAISS filtrando por los `paper_id` rescatados con top_k ampliado 8–30). Respuesta premium mostrada junto a la gratuita (no la sobrescribe), con modelo/modo/nº fragmentos/coste real; registrada con campo `mode` (`premium_same_chunks`/`premium_deepen`). Reutiliza la función única `synthesize_answer()` y el filtro `paper_id` de `passes_filters` (acepta colección de ids). Persistencia solo en `st.session_state` (`_last_results`). **2026-06-23 (Fase 1)**: chat con memoria sobre los papers rescatados — historial de turnos en `_premium_chat_history`, coste acumulado en `_premium_chat_cost`; en cada turno se reenvían todos los chunks + historial + nueva pregunta; reutiliza `synthesize_answer()` extendida con `history=None`; aviso de contexto largo por chars/4 contra `LLM_CONTEXT_WINDOWS`; modo de registro `premium_chat`; botón "🗑 Nuevo hilo" limpia el historial sin tocar el conjunto de papers. **2026-06-23**: bloque "🔎 Profundizar (modelo de pago)" — solo app privada, visible
  si hay consulta previa con artículos. Dos modos: A "mismos fragmentos" (cero FAISS) y
  B "profundizar en estos papers" (re-consulta FAISS por `paper_id`, top_k 8–30).
  Respuesta premium junto a la gratuita; registrada con campo `mode`. **Chat con memoria
  (Fase 1)**: historial multi-turno sobre los papers rescatados, modo A/B por sesión
  (fragmentos vs papers completos), coste acumulado visible, aviso de contexto al 80%
  de ventana, botón "🗑 Nuevo hilo". Expander "📄 Papers del conjunto actual" con lista
  compacta y exportar ZIP dentro del bloque premium (persiste durante los reruns del
  chat). `synthesize_answer()` como función única; `_render_papers_export()` reutilizable.
  Fase 2 pendiente: dossier editable / acumulación multi-búsqueda (item 48). **2026-07-01**: app pública añade provider **Google AI Studio** (gratis). API key personal por sesión (`st.text_input` type=password, solo si se selecciona el provider). Endpoint OpenAI-compatible (`generativelanguage.googleapis.com/v1beta/openai/`). Modelos: `gemini-2.5-flash`, `gemini-2.0-flash`. Coste registrado como 0. Validación en vivo con `models.list()`. No aparece en la app privada. |
| `3_Keywords` | Editor por textarea de `config/keywords.yml` (una keyword por línea, backup .bak automático) |
| `4_Scopus_queries` | Editor por categoría de `config/scopus_queries.yml` (multilínea, añadir/duplicar/borrar queries) |
| `5_DOI_manual` | Visor con filtros de `doi_manual.xlsx`, descarga CSV de vista filtrada. Filtros: búsqueda libre, status, **Solo sin DOI** (checkbox), **Fecha desde** (date_input). |
| `6_Mantenimiento` | 6 secciones expandibles: **Categorías activas** (multiselect sobre CANONICAL_CATEGORIES, guarda `active_categories.yml`) / **Backfill metadata** (detecta papers sin `stable_id`, re-ejecuta `4_extract_metadata.py` por categoría) / **Re-indexar FAISS** (multiselect categorías, todas por defecto, `--force bge-m3`) / **Limpieza de duplicados** (preview → apply condicional, con aviso de re-indexado) / **Reconstruir doi_registry** (llama a `build_doi_registry_from_nas()` directamente) / **Coherencia PDF/MD** (4 casos: PDF↔MD — detecta huérfanos y PDFs sin MD con corrección automática + reprocesado; MD↔PDF — MDs sin PDF; **Metadata↔MD** — detecta y elimina registros de `papers_metadata.jsonl` sin `md_clean` vía `prune_orphan_metadata()`, reversible con `.bak` + `_orphans_<ts>.jsonl`; **TEI↔md_clean** — detecta y mueve a cuarentena ficheros `tei/*.tei.xml` sin `md_clean` vía `prune_orphan_tei()`, reversible en `quarantine/orphan_tei/<ts>/<cat>/`). Ver `Mejoras_realizadas.md`, sesión de hoy. |
| `7_Revision` | Revisión bibliográfica con 5 prompts especializados (estado del arte, tabla de artículos clave, lagunas, comparativa, introducción). RAG sobre categoría+fase, streaming en 3 providers. Descarga Markdown + guardar en NAS (`notas_rag/`). Patrón flag+`st.rerun()`. Expander "📦 Exportar papers usados": ZIP (PDF+MD) + BibTeX generado desde `papers_metadata.jsonl`. Fragmentos usados en expander colapsado. **2026-06-11**: toggle "Recuperación híbrida (denso+BM25)" OFF por defecto, multiselect de Secciones (item 34) y filtro de año opt-in. |
| `8_Exportar` | Exporta bibliografía de una categoría a BibTeX / RIS / CSV. Filtros: rango de años, solo-DOI, quality score mínimo. Vista previa de papers seleccionados + 3 botones de descarga. |
| `9_Actividad` | Solo app privada. 4 secciones: uso RAG mes actual (métricas + tabla modelos de pago), últimas 20 consultas RAG, corpus por método de ingesta (`source_type`), errores recientes en `research_agent/logs/`. |
| `10_Duplicados` | Solo app privada. Detección en vivo de duplicados por título normalizado y hash SHA-256 (vía `9_cleanup_duplicates.py` cargado con `importlib`, registrado en `sys.modules` antes de `exec_module` por la dataclass de Python 3.13). Cuarentena REVERSIBLE: mueve PDF + artefactos a `/Volumes/research/quarantine/duplicates/<ts>/` con `_manifest` y quita la línea de `papers_metadata.jsonl` (`.bak`). Guard de falsos positivos en grupos por título (≥2 PDFs o ≥2 DOIs distintos → "No es duplicado" por defecto + aviso). **2026-06-17**: sección "♻️ Restaurar de cuarentena" — selectbox de timestamp, multiselect de manifiestos (con flag `✓/✗ meta`), preview + confirmación + botón; llama `restore_from_quarantine()`; reutiliza el bloque de re-index vía `dup_affected`. |
| `11_Articulos` | Privada + pública. Catálogo bibliográfico: resumen por categoría (`get_categories_summary`/`category_summary_row` en `app_utils.py`, columna "Metadata" cuenta líneas del `papers_metadata.jsonl`) + listado con filtros (texto título/DOI/autor, año, revista, radio Con/Sin DOI), DOI como `LinkColumn`, autores legibles y export CSV. **Editor (solo privada):** `st.data_editor` con todas las filas de la categoría — edita DOI, Año, Autores (sep. `;`, heurística último-token=apellido) y Revista; checkboxes `_sel` para marcar borrado. "Sugerir DOIs" llama a Crossref para los sin-DOI. "Guardar cambios" llama a `update_metadata_fields()` (escribe `papers_metadata.jsonl` + upsert `doi_manual.xlsx`, backup `.bak`). "Eliminar seleccionados" llama a `delete_papers()` (cuarentena reversible → `quarantine/deleted/<ts>/` + re-index FAISS vía `pipeline.run_step`). **Validación de metadata (Crossref, Nivel 2, solo privada, 2026-07-04):** sección que lee `validation_<cat>.jsonl`; checkbox "⚠ Solo con discrepancias" (ON: solo papers del sidecar; OFF: listado completo de la categoría); **fix 2026-07-04:** ahora SÍ se renderiza el listado por-campo — un expander por CADA paper del sidecar (antes se saltaban los que no tenían sugerencias Crossref y con sidecar sin `--crossref` no se pintaba nada): adopción POR CAMPO título/año/revista (valor actual vs sugerido Crossref/paper_id, botón "Adoptar" que llama a `update_metadata_fields` con solo ese campo; para `year` ofrece las dos fuentes cuando difieren, un botón por fuente), `authors_mismatch` solo informativo (remite a la adopción masiva), issues locales Nivel 1 como diagnóstico de solo lectura, y degradación elegante si el sidecar no trae bloque `crossref` (aviso "re-ejecuta con --crossref"); contador "N paper(s) marcados para revisar en esta categoría"; **botón de adopción MASIVA de autores por categoría** con preview (paper_id · autores actuales · autores Crossref, marca los que cambian, cuenta "N se actualizarán") → checkbox de confirmación → `update_metadata_fields(pid, authors=...)` por paper (formato `{full,forename,surname}` derivado de Crossref); papers sin DOI o sin fuente se saltan. **Adopción MASIVA de año (2026-07-04, acotada mismo día):** mismo patrón preview→confirmar para los papers con DOI de la categoría cuyo año local ≠ `cr.year` (canónico published-print vía `_pick_year`), pero el LOTE masivo se limita a severity `low` ≡ |Δ|==1 (criterio compartido `year_delta_severity` de `utils/metadata_validation.py`): tabla paper_id · año actual · año Crossref · delta + checkbox → `update_metadata_fields(pid, year=...)` (hereda `.bak` + `PRESERVE_FIELDS`) + invalidación de caché + rerun; los |Δ|≥2 van a una sección aparte "Revisar individualmente" SIN botón en bloque (corrupción probable o caso editorial dudoso — passalacqua local 2023/online 2024/print 2025) y se adoptan uno a uno IN SITU (**UX 2026-07-04**: botón "Adoptar año" por fila, misma escritura `update_metadata_fields`); saltados listados (sin DOI/miss/sin año). **UX 2026-07-04 — desaparición en vivo:** helper puro `issue_is_stale` (`utils/metadata_validation.py`) compara el registro VIGENTE contra la foto del sidecar (sugerencia adoptada → issue omitido; diagnóstico local con campo cambiado → omitido) en el listado por-campo y en "Revisar individualmente"; papers sin issues visibles se muestran como "✓ resuelto en esta sesión" + caption "N issue(s) resueltos…re-ejecuta el validador". Solo filtro de visualización: el sidecar en disco NO se reescribe. **Botón de re-validación desde la web (2026-07-04):** "🔄 Re-validar esta categoría" + checkbox "Incluir Crossref (más lento)" (default ON) junto al contador — invoca `pipeline.run_step("validate_metadata.py", build_validate_cmd(cat, crossref))` (mismo patrón que `execute_script_live` de `6_Mantenimiento.py`: `st.status` + salida incremental en vivo), y al terminar OK hace `st.rerun()` (el sidecar se lee sin caché, así que el contador y los listados quedan al día sin salir a terminal); en fallo, `st.error` con las últimas líneas de salida, sin romper la página. NO reimplementa el validador. Reutiliza `utils.crossref.fetch_work` (caché). **"Mantener campo" (2026-07-12, item 51):** botón "✋ Mantener {campo}" junto a cada "Adoptar" del listado por-campo (y para el aviso informativo de autores) que llama a `utils.validation_overrides.dismiss(cat, paper_id, campo)` y oculta la sugerencia al instante (sin esperar a re-validar). Misma lógica en las 3 zonas de adopción masiva: autores (la preview salta ya-verificados al generarse, sin gastar llamada Crossref; fila con cambio → botón retira de la preview en vivo), año lote ±1 `ymass` (antes tabla de solo lectura, ahora fila a fila con botón hermano) y año "Revisar individualmente" `yreview` (ya era fila a fila). "Saltados" `yskip` (sin DOI/miss/sin año) pasa de tabla estática a fila a fila con botón "🚫 No reintentar año". Panel final "🔓 Campos marcados como verificados" con nota y "↩ Revertir" por fila. **2026-07-12 (cont., fixes derivados de la verificación):** helper `_cell(row, field)` en el editor normaliza `pd.NA`/`None` a `""` (antes `str(pd.NA)` → cadena literal `"<NA>"` se escribía tal cual al guardar); `journal`/`doi` se pueden vaciar explícitamente (`CLEARABLE_FIELDS` en `update_metadata_fields`), `title`/`year`/`authors` siguen protegidos contra vaciado accidental. Botón "✋ Mantener DOI" junto al aviso `crossref_miss`. Diagnósticos LOCALES (Nivel 1) dejan de ser solo lectura: cada uno con `field` en `validation_overrides.FIELDS` tiene su propio botón "✋ Mantener". **Adopción masiva de autores/año — candidatos desde el sidecar:** "Previsualizar" ya no barre en vivo todos los DOI de la categoría; los candidatos salen de `crossref.issues` (`authors_mismatch` / `year_mismatch` con `suggested_source=="crossref"`) del sidecar, y solo se consulta Crossref en vivo para autores (necesario para conservar el `given`/`family` estructurado; año no lo necesita, el sidecar ya trae `int`). Ver `Mejoras_realizadas.md`. |
| `15_Pendientes` (NUEVO, **2026-07-12**) | Solo app privada. Posponer 2 años los DOIs pendientes sin interés/acceso, para que dejen de salir en el email semanal. Toggle "Mostrar pospuestos" (OFF por defecto → solo `download_registry.pending_active()`). `st.data_editor` con checkbox `Sel`, DOI como `LinkColumn` ("🔗 abrir") y título/año/categoría/motivo/última revisión/`snooze_until` en solo-lectura. Botones "😴 Posponer 2 años seleccionados" → `download_registry.snooze()` y "🔄 Reactivar seleccionados" → `unsnooze()`. El snooze sobrevive a la re-ejecución de Scopus (`upsert()` no toca `snooze_until`). **2026-07-12 (cont.):** al abrir la página se llama automáticamente a `download_registry.reconcile_with_corpus()` (aviso "🔄 N reconciliado(s) automáticamente" si hay cambios) — cierra el hueco por el que DOIs ingestados fuera de `3a_download_pdfs.py` (p. ej. PDF manual) se quedaban `pending` para siempre. |
| `12_Backup` | Solo app privada. Backup manual del corpus (`categorias/` + `metadatos/`) a `research_bk` vía `rsync --size-only`. Detección de montaje SMB (`os.path.ismount`), fecha/antigüedad de la última copia (`last_backup.json`), botones "Ver qué cambiaría" (dry-run con conteo legible) y "Copiar ahora". |
| `13_RAG_multiple` (NUEVO, **2026-07-09**) | Solo app privada (`is_public_app()` → `st.stop()`; luego `check_password("PRIVATE_APP_PASSWORD")`). Front-end de la batería de consultas RAG: formulario (categoría vía `list_existing_categories`, phase, top_k, hybrid, año desde/hasta opcionales, secciones vía `CANONICAL_SECTIONS`, modelo de síntesis vía `OLLAMA_MODELS_LLM`, preguntas una-por-línea) → construye el `cfg` y llama a `run_rag_batch.run_batch(cfg, progress_cb=...)` (mismo motor que el CLI, sin duplicar lógica; añade `scripts/` a `sys.path` para el import). Barra de progreso + expander por pregunta OK mostrando el .md generado y `st.error` por pregunta ERROR (vía `progress_cb`). Al terminar: `st.success` con `out_dir` y `n_ok`/`n_err`, y `st.download_button` con un zip en memoria de los .md (persistido en `st.session_state["rag_batch_last"]` para sobrevivir al rerun del botón). Los .md quedan además en `/Volumes/research/exports/`. El override de secciones por pregunta queda solo para el YAML+CLI (anotado en `st.caption`). **La página MANTIENE la pestaña ocupada mientras corre la batería** (ejecución síncrona, sin background job); para tandas largas o desatendidas, usar el CLI (`run_rag_batch.py`) directamente en pciq22. **2026-07-10**: `st.number_input` "Timeout de síntesis (s)" (min 60, default 600, paso 30) junto al selector de modelo → `cfg["synth_timeout"]`; caption "sube si el 14B corta respuestas largas". | ✅ |

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
**Instancia privada (puerto 8501 — `app.py`)**

| Aspecto | Valor |
|---|---|
| Plist en repo | `deployment/com.research_agent.streamlit.plist` |
| Instalado en | `~/Library/LaunchAgents/com.research_agent.streamlit.plist` |
| Etiqueta | `com.research_agent.streamlit` |
| Comando | `/Users/martinramirez/venvs/rag_papers/bin/python3 -m streamlit run app.py` |
| WorkingDirectory | `/Users/martinramirez/proyectos/research_agent/scripts/streamlit_app` |
| Logs | `~/Library/Logs/research_agent/streamlit.{log,err.log}` |
| KeepAlive | true (reinicia automáticamente si se cae) |
| RunAtLoad | true (arranca al login) |

**Instancia pública (puerto 8502 — `app_public.py`)**

| Aspecto | Valor |
|---|---|
| Plist en repo | `deployment/com.research_agent.streamlit_public.plist` |
| Instalado en | `~/Library/LaunchAgents/com.research_agent.streamlit_public.plist` |
| Etiqueta | `com.research_agent.streamlit_public` |
| Comando | `PUBLIC_APP=true /Users/martinramirez/venvs/rag_papers/bin/python3 -m streamlit run app_public.py --server.port 8502` |
| WorkingDirectory | `/Users/martinramirez/proyectos/research_agent/scripts/streamlit_app` |
| Logs | `~/Library/Logs/research_agent/streamlit_public.{log,err.log}` |
| KeepAlive | true |
| RunAtLoad | true |

**Ingesta Scopus semanal (`run_weekly_scopus.py`)**

| Aspecto | Valor |
|---|---|
| Plist en repo | `deployment/com.research_agent.scopus_weekly.plist` |
| Instalado en | `~/Library/LaunchAgents/com.research_agent.scopus_weekly.plist` |
| Etiqueta | `com.research_agent.scopus_weekly` |
| Comando | `python3.13 run_weekly_scopus.py` (venv) |
| WorkingDirectory | `/Users/martinramirez/proyectos/research_agent/scripts` |
| Logs | `~/Library/Logs/research_agent/scopus_weekly.{log,err.log}` |
| Schedule | Lunes a las **04:00** (`StartCalendarInterval`) — plist del repo actualizado; pendiente aplicar en pciq22 |
| RunAtLoad | false |
| KeepAlive | false |

**Pregunta diaria tiempo/mareas (`~/claude-scheduled/scheduled-claude.sh`, fuera del repo)**

> ⚠️ **Único LaunchDaemon del proyecto — no LaunchAgent.** Un LaunchAgent
> normal está atado a la sesión gráfica (Aqua) del usuario
> (`monitor = com.apple.UserEventAgent-Aqua`); si el Mac se reinicia (crash,
> corte...) y nadie inicia sesión gráfica antes de las 06:00, el disparador
> de `StartCalendarInterval` se pierde sin más — launchd no lo reintenta.
> Pasó de verdad dos veces (16 y 18 de julio de 2026, ver
> `Mejoras_realizadas.md` → sesión 2026-07-18). Instalado como LaunchDaemon
> en `/Library/LaunchDaemons/` (dominio `system`) con `UserName` =
> `martinramirez` para correr con permisos de usuario sin sesión gráfica
> activa. `WakeOnLaunchDate` solo tiene efecto real en LaunchDaemons —
> en el LaunchAgent anterior (desde 2026-07-09) era una clave inerte.

| Aspecto | Valor |
|---|---|
| Plist en repo | `deployment/com.research_agent.daily_question.plist` |
| Instalado en | `/Library/LaunchDaemons/com.research_agent.daily_question.plist` (root:wheel, 644) |
| Etiqueta | `com.research_agent.daily_question` |
| Dominio launchd | `system` (no `gui/<uid>`) |
| UserName | `martinramirez` — el daemon corre como este usuario, no como root |
| EnvironmentVariables | `HOME=/Users/martinramirez` — **obligatorio**: un LaunchDaemon con `UserName` no hereda `$HOME` automáticamente; sin esto el script no encuentra `~/claude-scheduled/question.md` ni el resto de rutas |
| Comando | `/bin/bash /Users/martinramirez/claude-scheduled/scheduled-claude.sh` |
| Logs | `~/Library/Logs/research_agent/daily_question.{log,err.log}` |
| Schedule | Todos los días **06:00** (`StartCalendarInterval`, un dict por weekday 1-7) |
| WakeOnLaunchDate | true — efectivo ahora que es LaunchDaemon |
| RunAtLoad | false |
| LaunchAgent viejo | Desactivado, no borrado: `~/Library/LaunchAgents/com.research_agent.daily_question.plist.disabled` |

Credenciales de `claude` CLI (llavero de inicio de sesión `Claude Code-credentials`
+ `~/.claude/.credentials.json`) verificadas empíricamente accesibles sin sesión
gráfica activa (`launchctl kickstart` en frío generó respuesta real y envió el
email — sin error de autenticación).

Reinstalar tras editar el plist (requiere `sudo`, dominio `system` — ver
`deployment/README.md` para el bloque completo):

```bash
sudo cp deployment/com.research_agent.daily_question.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.research_agent.daily_question.plist
sudo chmod 644 /Library/LaunchDaemons/com.research_agent.daily_question.plist
sudo launchctl bootout system/com.research_agent.daily_question 2>/dev/null
sudo launchctl bootstrap system /Library/LaunchDaemons/com.research_agent.daily_question.plist
```

Comandos día a día:

```bash
# Estado
launchctl list | grep streamlit

# Log en vivo
tail -f ~/Library/Logs/research_agent/streamlit.log

# Parar / arrancar / recargar
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit.plist

# Publico
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit_public.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.streamlit_public.plist

```

### Acceso

- Red UCA (local): `http://10.142.6.107:8501`
- Fuera (con VPN UCA activa): `http://10.142.6.107:8501`
- Mac mini de casa: acceso solo para edición de código vía git
- **NO** expuesto a internet (URL pública del router NO funciona — y bien que está)

## Configuración (config/.env)

```
OLLAMA_HOST=http://127.0.0.1:11435
OLLAMA_API_KEY=<clave — también token Bearer del proxy Caddy, ver más abajo>
GROBID_URL=http://127.0.0.1:8070
GROBID_TIMEOUT=600
UNPAYWALL_EMAIL=martin.ramirez@uca.es
ELSEVIER_API_KEY=<clave>
PRIVATE_APP_PASSWORD=<contraseña instancia privada>
PUBLIC_APP_PASSWORD=<contraseña instancia pública>
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

El backlog vivo y el orden de prioridad están en `Mejoras_pendientes.md`. El histórico de lo realizado, en `Mejoras_realizadas.md`. Este documento (ESTADO.md) describe el estado y la arquitectura actuales del proyecto.

## Notas importantes

- **Ollama y GROBID securizados (2026-07-08):** Ollama ya no escucha en red — solo `127.0.0.1:11435`. El puerto público `11434` lo sirve un proxy Caddy (`deployment/Caddyfile.ollama` + `deployment/com.research_agent.caddy_ollama.plist`) que exige `Authorization: Bearer <OLLAMA_API_KEY>` y devuelve 401 sin él. GROBID pasó a `127.0.0.1:8070` (sin proxy — nada remoto lo usa). Ver detalle y diagrama en [Ollama — instalación en pciq22](#ollama--instalación-en-pciq22) y `deployment/README.md`.
- Ollama en `pciq22.uca.es` solo accesible desde red UCA o VPN **y** con el token Bearer correcto (antes solo dependía de la red). Las consultas RAG con Anthropic/OpenAI NO requieren VPN UCA (útil cuando la VPN cae)
- `mxbai-embed-large` NO es compatible con los chunks actuales (512 ctx vs ~1500 chars por chunk). Usar `bge-m3` (8192 ctx) como alternativa a nomic
- Los registros de coste RAG se guardan en `/Volumes/research/metadatos/rag_usage/rag_usage_YYYY-MM.jsonl`
- Descargas Elsevier requieren VPN activa (autenticación por IP institucional)
- GROBID puede necesitar warm-up tras inactividad (primera llamada lenta)
- El cribado (`2_screen`) usa keywords primero (rápido) y Ollama como fallback
- El cribado NO es necesario para el flujo Scopus (la query ya define la categoría)
- `doi_manual.xlsx` en `/Volumes/research/metadatos/` acumula todos los DOIs procesados
- Skip automático en todos los scripts: no reprocesa lo ya existente
- FAISS para embeddings (no ChromaDB), manteniendo scripts originales
- Convención de ficheros de eval en `metadatos/eval/`: `questions_<cat>.json` → `review_<cat>.md` → `golden_<cat>.jsonl` (+ `results_<cat>_<ts>.csv`)
- Argumentos inconsistentes entre scripts: `--phase` (3_process, 3b_summarize) vs `--project` (4–8). El orquestador absorbe la diferencia.
- `CANONICAL_CATEGORIES` y `OLLAMA_MODEL_EMBED` centralizadas en `utils/constants.py` — fuente de verdad única. `pipeline.py` importa `_CANONICAL_CATEGORIES` desde ahí con fallback inline (`except ImportError`); `app_utils.py` usa import fusionado. **Si se añade una categoría, solo actualizar `utils/constants.py`.**
- `stable_id` en metadata: slug del DOI si existe, `paper_id` original si no. Campo estable independiente del nombre de fichero (item 16). Papers procesados antes del item 16 carecen de este campo — rellenar con página **6_Mantenimiento** → sección Backfill metadata.
- Procedencia en metadata: `source_type` (scopus/inbox/adhoc/manual), `download_source`, `access_type`, `download_url`, `download_date`, `processed_date`. Leído automáticamente de `descarga_cache.json` por DOI; arg `--source-type` para forzarlo (item 14). Verificado en producción 2026-05-27.
- `_copy_files_skip_existing(src, dst)` en `pipeline.py`: copia recursiva con `rglob`, skip por existencia de fichero, preserva subdirectorios. Usada por `integrate_adhoc()` y `promote_adhoc_to_category()`.
- `run_adhoc()` en `pipeline.py`: valida el nombre del proyecto con `re.fullmatch(r'^[a-z0-9_-]+$', name)` antes de crear directorios. Lanza `ValueError` si el nombre contiene espacios, mayúsculas o caracteres no permitidos.
- `pendientes_descarga.csv` en `/Volumes/research/metadatos/`: registro persistente acumulado de DOIs fallidos entre lotes. Actualizado automáticamente por `3a_download_pdfs.py --category <cat>`. Helper en `utils/download_registry.py` (`upsert`, `mark_downloaded`, `load`, y **2026-07-12** `pending_active`, `snooze`, `unsnooze`, `reconcile_with_corpus`). Prerequisito del item 28. **2026-07-12**: página `15_Pendientes.py` permite posponer 2 años (columna `snooze_until`) los DOIs sin interés/acceso para que dejen de salir en el email semanal (`run_weekly_scopus.py` usa `pending_active()` en vez del filtro `status=="pending"` suelto). **2026-07-12 (cont.):** `reconcile_with_corpus()` cruza pendientes contra el corpus real y marca `downloaded` los ya ingestados por vías fuera de `3a_download_pdfs.py` — corre automática en `15_Pendientes.py` y `run_weekly_scopus.py`; 37 reconciliados en la primera ejecución real.
- **`update_doi_registry()`**: claves normalizadas con `_norm_doi_key` (fix 2026-06-14), alineado con `build_doi_registry_from_nas()`.
- `integrate_adhoc(adhoc, target, delete_source)` en `pipeline.py`: copia pdfs/, md_clean/, summaries/, chunks/, metadata/ de un proyecto ad-hoc a una categoría canónica existente y re-indexa FAISS del destino. Los ficheros ya existentes se saltan.
- `promote_adhoc_to_category(adhoc, new_name, keywords, delete_source)` en `pipeline.py`: crea una nueva categoría canónica desde un ad-hoc copiando también embeddings/ y registrando keywords en `config/keywords.yml`. Valida nombre (`^[a-z0-9_]+$`) y que la categoría no exista previamente.
- `quality_score` (0–1) y `warnings` añadidos a cada registro de `papers_metadata.jsonl` por `4_extract_metadata.py`. 7 criterios: título, DOI, abstract, año, autores, refs<5, md_clean corto. Papers procesados antes del item 17 no tienen el campo — rellenar con **Mantenimiento → Backfill metadata**. Panel "📊 Calidad del corpus" en portada Streamlit (expander, solo categorías con metadata existente).
- `active_categories.yml` en `config/`: lista YAML `active:` con las categorías habilitadas. Editado desde la web (Mantenimiento → Sección 1). Las inactivas se muestran en gris en portada y se excluyen de `run_scopus()`. Fallback a `CANONICAL_CATEGORIES` si el fichero no existe o está vacío.
- `corpus_manifest.json` en `categorias/<cat>/`: generado con `utils/corpus_manifest.py`; contiene métricas de estado del corpus (n_pdfs, n_chunks, quality_score, faiss_indexes, faiss_stale, keywords_hash, git_commit). Actualizar tras ingestas o re-indexados. `app_utils.get_corpus_manifest()` lo lee para la portada.
- `1_rename_papers_by_doi.py` genera nombres con solo guiones bajos desde 2026-05-28 (fix guiones/espacios en `shorten_title` y `sanitize_filename`). PDFs renombrados antes pueden tener guiones en el stem — usar **Mantenimiento → Coherencia PDF/MD** para detectar y corregir los artefactos con nombre viejo.
- ZIP export en RAG (`2_RAG.py`) y Revisión (`7_Revision.py`) usa `build_papers_zip` con fallback: paper_id exacto → stable_id desde `papers_metadata.jsonl` → glob por prefijo. Resuelve PDFs cuyo paper_id (nombre viejo) ya no coincide con el stem del PDF renombrado por Crossref.
- `section_canonical` en chunks JSONL (item 32, 2026-06-10): herencia jerárquica del heading más cercano que clasifique (abstract/introduction/methods/results/discussion/conclusion); subsecciones descriptivas sin patrón IMRaD heredan del padre. Chunks de tabla → `"table"`. El campo `section` (título hoja crudo) queda intacto. **No es retroactivo**: categorías procesadas antes del item 32 no tienen el campo — re-trocear con `--force` para poblarlo.
- `metadata.jsonl` por chunk incluye ahora `section_canonical` (item 32) y `year` (item 34, denormalizado desde `papers_metadata.jsonl` + fallback regex sobre paper_id).
- `utils/retrieval.py` centraliza la recuperación: BM25 al vuelo (sin artefacto, alineado con FAISS por orden), fusión RRF (k=60) y filtros (`passes_filters`). Toggle híbrido OFF por defecto en CLI (`--hybrid`) y web.
- `MAX_EMBED_CHARS=8000` (`utils/constants.py`): tope de chunk + truncado reactivo en el embed para no exceder el contexto de bge-m3 con texto denso en fórmulas/subíndices.
- `requirements.txt`: dependencias `rank-bm25`, `pytest>=8.0` y `pymupdf` (item 47 — extracción de texto de adjuntos efímeros).
- **Tests (item 39):** `tests/` con `pytest` (`conftest.py` añade `scripts/` a sys.path; `pytest.ini` en raíz). `normalize_stem` en `utils/pdf_utils.py` unifica el antiguo `_norm` de los 3 ficheros. Regresión de DOI/título/stem: 56 passed, 1 xfailed (xfail strict = bug `_clean_doi`, item 44). Hallazgos abiertos: items 44 (`_clean_doi` recorta sufijos DOI de 3+ letras) y 45 (utilidades de texto duplicadas y divergentes `pdf_utils`↔`1_rename`).
- **Rollout item 32 completado (2026-06-11):** las 8 categorías re-troceadas + re-indexadas (`3_process_corpus.py --force-md` + `5_build_embeddings.py --force`); `section_canonical` y `year` poblados en `metadata.jsonl` de todas. Ya no queda el "pendiente: re-trocear el resto".
- **Cuarentena de índices viejos all__bge-m3 (item 41, 2026-06-16):** las fases `all__bge-m3` divergentes (sin `section_canonical`/`year`) de 6 categorías movidas a `/Volumes/research/quarantine/old_indexes/20260616_011551/<cat>/all__bge-m3/`. Índice canónico vivo de cada categoría: `embeddings/all/index.faiss`.
- **Revista desde TEI:** `4_extract_metadata.py` extrae `journal` del `monogr/title[@level='j']` del TEI (con fallback). Filtro y columna de revista disponibles en la página Artículos. Se descartó en su día y ahora sí se incorpora.
- **`4_extract_metadata.py` salta TEI huérfanos:** solo emite metadata para TEI con `md_clean` correspondiente (comparación por stem normalizado `_norm`), evitando papers fantasma en `papers_metadata.jsonl` por restos de dedup/renombrados; imprime la lista de saltados. Además: fallback de DOI a `doi_manual.xlsx` y preservación de `title`/`doi`/`journal`/`year`/`authors` no vacíos al reextraer (las correcciones manuales del editor de Artículos sobreviven).
- **Cuarentena reversible de duplicados:** página Duplicados (`10_Duplicados.py`, privada) + `quarantine_paper()` en `9_cleanup_duplicates.py` mueven PDF + artefactos a `/Volumes/research/quarantine/duplicates/<ts>/` (con `_manifest`) y quitan la línea de `papers_metadata.jsonl` con `.bak` — operación deshacible, no borra ficheros. **2026-06-17:** restauración real vía `restore_from_quarantine()` + sección UI "♻️ Restaurar de cuarentena"; manifiesto incluye `meta_lines` para reinserción automática de metadata.
- **Backup a research_bk (item 40, completado 2026-06-12):** manual (NAS de casa por VPN + montaje SMB; no automático). `/opt/homebrew/bin/rsync -rv --size-only --no-perms --no-owner --no-group` + excludes de dirs de sistema macOS, de `/Volumes/research/` a la RAÍZ de `/Volumes/research_bk/`. `--size-only` porque el SMB del Synology no conserva el mtime (comparar por tiempo re-copia en bucle). rsync clásico de Homebrew, NO el openrsync nativo. `#recycle` con auto-vaciado 15–30 días. No `--inplace`. UI: página `12_Backup.py` (privada) + banner de antigüedad en portada (>15 días). Verificado: dry-run convergente (0 ficheros); primera copia por botón OK.

### Streamlit / launchd — gotchas aprendidos durante el despliegue

- **No usar el shim `~/venvs/.../bin/streamlit`** desde launchd: macOS 15+ le pone `com.apple.provenance` y bloquea el spawn con `EX_CONFIG` (78). Solución: invocar el intérprete Python directamente con `-m streamlit`.
- **Logs NO en `/Volumes/Disco/` ni `/Volumes/research/`**: TCC bloquea a los launchd user agents la escritura en volúmenes externos. Los logs van a `~/Library/Logs/research_agent/`.
- **No usar emojis en nombres de fichero de `pages/`**: macOS los guarda en Unicode NFD y Streamlit no descubre las páginas en sidebar. Los iconos visuales se ponen con `st.set_page_config(page_icon="📥", ...)` dentro del fichero.
- **Módulo de helpers de la web se llama `app_utils.py`, NO `utils.py`**: hay colisión con el paquete `scripts/utils/` (que contiene `pdf_utils.py`) cuando `scripts/` está en `sys.path`. Python resuelve al paquete viejo en lugar de al módulo de la app. **2026-06-13:** `get_category_stats` cuenta "Metadata" desde líneas de `papers_metadata.jsonl` (no desde `per_paper/*.metadata.json` obsoletos). Ver `Mejoras_realizadas.md`, sesión de hoy.
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
- GROBID corre en Docker ARM64 nativo (`grobid/grobid:0.9.0-crf`) en pciq22. Compose en `~/grobid-compose.yml`. Docker Desktop configurado para arrancar al login.
- Mac mini de casa ya no ejecuta Streamlit ni pipeline. Servicio launchd eliminado. Modo hibernación restaurado (pmset). Repo conservado en `/Volumes/Disco/proyectos/research_agent/` para edición.
- Datos migrados del NAS Synology (casa) al SSD Crucial X9 4TB montado en `/Volumes/research/` en pciq22. NAS pasa a backup.

### Ollama — instalación en pciq22

- **Método:** tarball oficial de GitHub (NO Homebrew, NO install.sh — ambos dan versiones corruptas en ARM64)
- **Binario:** `/usr/local/bin/ollama`
- **Libs:** `/usr/local/lib/ollama/` (llama-server, llama-quantize, libggml-*.dylib)
- **Modelos:** `~/.ollama/models/`
- **Servicio:** LaunchAgent `~/Library/LaunchAgents/com.martin.ollama.plist` (`OLLAMA_HOST=127.0.0.1:11435`, `OLLAMA_ORIGINS=app://obsidian.md*` para CORS del plugin Obsidian)
- **Logs:** `~/ollama.launchd.log` / `~/ollama.launchd.err`
- Existen también los servicios `com.ollama.ollama` / `homebrew.mxcl.ollama` cargados en el sistema pero **inactivos** (status 78, no arrancan binario) — no se han tocado, no interfieren.

**Para actualizar:**
1. Descargar `https://github.com/ollama/ollama/releases/download/vX.Y.Z/ollama-darwin.tgz`
2. `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.martin.ollama.plist`
3. Extraer y copiar binarios a `/usr/local/bin/` y `/usr/local/lib/ollama/`
4. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.martin.ollama.plist`

⚠️ Los modelos en `~/.ollama/models/` no se tocan al actualizar.
⚠️ Evitar abrir Ollama.app — interfiere con el servicio headless.

**Nota operativa para el grupo — uso concurrente (2026-07-10):** una batería de
`run_rag_batch.py` / página `13_RAG_multiple` ocupa slot(s) de Ollama durante
TODO el run (recuperación + síntesis por pregunta, secuencial). Si coincidís
varios usando RAG a la vez: preferid recuperación local + síntesis con Gemini
(app pública, gratis, no consume Ollama) mientras corre una batería. Si las
consultas se solapan a menudo, subir `OLLAMA_NUM_PARALLEL=2` en
`com.martin.ollama.plist` (hoy sin definir → default de Ollama).

#### Securización (2026-07-08) — autenticación real, no solo perímetro de red

Antes, Ollama (`0.0.0.0:11434`) y GROBID (`0.0.0.0:8070`) estaban expuestos a
toda la red UCA sin ninguna autenticación. Arquitectura actual:

```
Cliente remoto ──Bearer token──▶ Caddy :11434 (0.0.0.0) ──▶ Ollama 127.0.0.1:11435
                                  (401 si falta/no coincide el token)

Cliente local (pipeline, Streamlit 8501/8502) ────────────▶ Ollama 127.0.0.1:11435 (directo, sin token)

GROBID: 127.0.0.1:8070 únicamente — sin proxy, nada remoto lo usa
```

- **Ollama**: solo loopback (`127.0.0.1:11435`, ver plist arriba). Ya no acepta
  conexiones de red directas.
- **GROBID**: bind cambiado en `~/grobid-compose.yml` a `127.0.0.1:8070:8070`.
- **Caddy** (`brew install caddy`, ya instalado — v2.11.4): escucha en
  `0.0.0.0:11434` (mismo puerto público de siempre, los clientes remotos no
  cambian URL) y hace `reverse_proxy` a `127.0.0.1:11435` solo si la petición
  trae `Authorization: Bearer <OLLAMA_API_KEY>`; si no, `401`. Reenvía la
  cabecera `Origin` intacta (comportamiento por defecto de Caddy), así que
  `OLLAMA_ORIGINS` sigue gestionando CORS para Obsidian sin cambios.
  - **Fix preflight CORS (2026-07-08):** el plugin Ollama de Obsidian dejó de
    funcionar tras el despliegue inicial porque el preflight `OPTIONS` del
    navegador/Electron nunca lleva `Authorization` (no forma parte del
    estándar CORS) — Caddy lo bloqueaba con `401` antes de que Ollama pudiera
    responder con las cabeceras CORS (`OLLAMA_ORIGINS`). Se añadió un matcher
    `@preflight method OPTIONS` que reenvía esas peticiones a Ollama **sin
    exigir token** (no ejecuta nada ni devuelve datos, solo permite completar
    el handshake CORS); el resto de métodos siguen exigiendo Bearer igual que
    antes. Verificado con el plugin funcionando. Commit `b281961`.
  - Config versionada: `deployment/Caddyfile.ollama` (sin secretos).
  - Servicio: `deployment/com.research_agent.caddy_ollama.plist` (patrón
    Streamlit — `PATH` fijado a mano, logs en `~/Library/Logs/research_agent/`).
  - El token vive en `config/.env` (`OLLAMA_API_KEY`) **y** en
    `config/.env.caddy_ollama` (fichero mínimo aparte, no versionado, que es
    el que realmente carga el proceso Caddy vía `--envfile` — así Caddy no ve
    el resto de secretos del proyecto).
  - **Nota**: en esta máquina ya corría otro Caddy manual (proyecto
    `word-pdf-to-md`, puerto 8503, admin API en `127.0.0.1:2019`). El Caddyfile
    de Ollama usa `admin off` para no chocar con él.
- **Clientes locales** (scripts del pipeline, Streamlit): usan
  `OLLAMA_HOST=http://127.0.0.1:11435` / `GROBID_URL=http://127.0.0.1:8070` en
  `config/.env`, sin token — nunca pasan por Caddy.
- **Cliente remoto** (p.ej. plugin Ollama de Obsidian): URL sin cambios
  (`http://pciq22.uca.es:11434`) + cabecera `Authorization: Bearer <token>`.

**Rotar el token:**
```bash
NEW_TOKEN=$(openssl rand -hex 32)
# Actualizar OLLAMA_API_KEY=$NEW_TOKEN en config/.env Y en config/.env.caddy_ollama
launchctl kickstart -k gui/$(id -u)/com.research_agent.caddy_ollama
# Actualizar el token en los clientes remotos (Obsidian, etc.)
```

Detalle completo de instalación/rotación en `deployment/README.md`.

**Pendiente — Hermes (pausado por auditoría, NO reactivar sin más contexto):**
si `~/hermes-docker` apuntaba a Ollama por `http://host.docker.internal:11434`
(o similar), al reactivarse deberá añadir la cabecera `Authorization: Bearer
<token>`, porque ese endpoint ahora exige autenticación (ya no es acceso
directo sin auth). Un contenedor Docker no alcanza el loopback del host en
`127.0.0.1:11435` — por eso debe seguir pasando por Caddy (`:11434`) con el
token, y no se le puede simplemente apuntar al puerto interno. No se ha
tocado `~/.hermes` ni `~/hermes-docker` en este cambio.

- **Identidad git:** `user.email = martinconil@gmail.com` / `user.name = Martín Ramírez` configurada globalmente en ambas máquinas (2026-06-23). El NAS (`/Volumes/Disco/`) hereda la identidad del entorno desde el que se ejecuta git — usar siempre desde pciq22 o con la global correcta.
