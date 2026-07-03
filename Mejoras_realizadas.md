# Mejoras realizadas — research_agent
> Histórico append-only (lo más nuevo arriba). Backlog: Mejoras_pendientes.md · Estado/arquitectura: ESTADO.md

---

### ✅ pool_candidates.py — BM25 puro en la unión + preservación de anotaciones (2026-07-03)

Dos endurecimientos de `scripts/pool_candidates.py`, ligados a la nota del item 33/37
sobre sesgo de pooling (ver Mejoras_pendientes.md):

- **Fix A · BM25 puro en la unión:** además de `dense_rank` y el híbrido
  `rrf_fuse(dense, bm25)`, ahora se calcula también `bm25_rank` puro y su resultado
  entra en la unión de candidatos (`candidates = dense_pos | hybrid_pos | bm25_pos`).
  Antes, un documento que solo destacaba en BM25 podía quedar fuera si el RRF lo
  diluía por debajo del corte, infravalorando al híbrido en el golden set. Se añade
  una columna `b{pos}` (o `b—`) junto a `d{pos}`/`h{pos}` en cada línea de checkbox
  para que el experto vea también el ranking BM25 puro. Reutiliza el mismo cálculo
  de BM25 que ya alimentaba el híbrido — sin coste adicional. Backward-safe: si
  `rank-bm25` no está instalado, `bm25_rank` devuelve `[]` y todo queda `b—`.
- **Fix B · Preservar anotaciones al regenerar el review:** al reejecutar `pool`,
  si `review_<categoria>.md` ya existe, se parsea con `parse_review` y las marcas
  `[x]` previas por `qid` se conservan en la regeneración (antes, cualquier
  reejecución de `pool` perdía todo el trabajo de anotación manual del experto).
  Nota añadida a la cabecera del review advirtiendo de no reordenar preguntas entre
  pooladas (la preservación es por `qid`, no por posición/texto).

---

## Sesión 2026-07-01 (cont.) — Hermes Agent: auditoría de seguridad y pausa

**Nota:** este trabajo vive fuera de este repo (`~/.hermes` + `~/hermes-docker`), no
en `research_agent`. Continuación directa de la migración a Docker documentada
justo debajo (misma sesión). Ver `ESTADO.md` → "Hermes Agent" (ahora marcado
PAUSADO) y `Mejoras_pendientes.md` → item 49 → "REACTIVACIÓN".

**Acciones de pausa aplicadas:**
- `docker compose down` — contenedor parado y eliminado; config/estado
  conservados en `~/.hermes` y `~/hermes-docker`.
- Token OAuth de Google revocado en `myaccount.google.com/permissions` —
  credencial invalidada; `credentials.json` sigue en disco pero ya no es válido.
- Autorización Notion revocada (o confirmado que no había grant activo que
  revocar).
- LaunchAgents nativos archivados a `.disabled` para que no arranquen al login.
- Tavily (API key de búsqueda web, no da acceso a datos propios): activa, sin
  urgencia de rotar.

**Hallazgos de la auditoría (motivo de la pausa):**

1. **Token OAuth de Google sobreprivilegiado:** un único token compartido por
   los MCP de Gmail y Calendar (`/opt/data/gmail-mcp/credentials.json`) con
   scopes `gmail.modify`, `gmail.send`, calendar (completo r/w/delete), drive,
   documents, spreadsheets, `contacts.readonly`. La whitelist de 7 tools de
   Gmail limita lo que el LLM VE, no lo que el token PUEDE. Drive/Docs/Sheets
   ni se usan funcionalmente: los arrastra el cliente OAuth del MCP de
   Calendar (`@cocal/google-calendar-mcp`); el array `AUTH_SCOPES` de
   `@shinzolabs/gmail-mcp` (`dist/oauth2.js`) solo pide scopes de Gmail
   (`gmail.modify`, `gmail.compose`, `gmail.send`, `gmail.settings.basic`,
   `gmail.settings.sharing`).
2. **`/var/run/docker.sock` montado en el contenedor padre** (necesario para
   `terminal.backend: docker`) = root de facto en el host. El padre corre como
   root, sin `cap_drop`/`security_opt`/`read_only`, con `~/.hermes` montado rw,
   y es quien ingiere contenido no confiable (emails, eventos, resultados
   Tavily). Regresión neta de seguridad frente al setup nativo. Cadenas de
   ataque: supply-chain vía `npx -y`, o inyección de prompt → reescritura de
   config vía toolset file.
3. **`tools.include: []`** en Calendar (17 tools, incl. `delete_event`) y
   Notion (20 tools) = todas expuestas. Canal de exfiltración vía
   `create_event` con invitado externo.

**Nota:** la migración a Docker en sí (contenedor funcional, MCPs operativos,
terminal sandbox aislado verificado, fix de persistencia del token de
Calendar, fixes de config YAML) quedó **COMPLETADA y correcta**. La pausa es
por credenciales/aislamiento, no por la migración.

---

## Sesión 2026-07-01 — Hermes Agent: migración a Docker

**Nota:** este trabajo vive fuera de este repo (`~/.hermes` + `~/hermes-docker`), no
en `research_agent`. Se documenta aquí siguiendo la convención de sesiones de
Hermes ya usada en este fichero (ver sesiones 2026-06-24 a 2026-06-28). Detalle en
`ESTADO.md` → "Hermes Agent" y `Mejoras_pendientes.md` → item 49.

**Migración de LaunchAgent nativo a Docker Compose:**
- Imagen oficial `nousresearch/hermes-agent`. `~/.hermes` montado como `/opt/data`
  (persistente).

**Terminal reactivado (antes desactivado):**
- Ahora `backend: docker` — sandbox vía contenedor hermano, usando
  `/var/run/docker.sock` montado.
- `docker_volumes` restringido a `~/hermes_workspace:/workspace` (rw) +
  `~/.hermes/cache/documents:/output`.
- Verificado: escribe dentro del scope; confirmado que NO ve nada fuera de
  `/workspace` (probado explícitamente contra
  `/Users/martinramirez/proyectos/research_agent`).

**Bugs de config arreglados (todos en `~/.hermes/config.yaml`):**
- YAML roto (faltaba `:` tras `ollama-local`) que tiraba toda la config a defaults
  en silencio.
- `custom_providers` en formato dict en vez de lista (schema real: lista con clave
  `name:`).
- Gmail MCP: el wrapper `gmail-mcp-wrapper.sh` dependía de `lsof`/`pkill`/binario
  Homebrew, no portable a Docker. Sustituido por `npx -y @shinzolabs/gmail-mcp`
  directo (mismo patrón que google-calendar).
- Rutas de credenciales Gmail/Calendar cambiadas de rutas absolutas del host a
  rutas dentro de `/opt/data` (persistente).

**Google Calendar — token no persistía entre reinicios:**
- Causa: `GOOGLE_CALENDAR_MCP_TOKEN_PATH` no estaba fijado. Fix: apuntarlo a
  `/opt/data/google-calendar-tokens.json`.
- La re-autenticación OAuth vía Docker (mapear puerto del callback) NO funcionó
  (`ERR_EMPTY_RESPONSE`, el servidor de callback solo escucha en el loopback
  interno del contenedor).
- Solución real: correr `npx @cocal/google-calendar-mcp auth` nativamente en el
  host (pciq22, escritorio remoto), apuntando al mismo path.

**Ollama en red:**
- `ollama-local` añadido a `custom_providers` apuntando a
  `http://host.docker.internal:11434/v1` — Ollama accesible en red desde el
  contenedor.

**Docker Desktop:**
- `docker compose pull` fallaba por SSH (error de keychain por hooks de Docker
  Scout, no por `credsStore`). Resuelto haciendo el pull inicial vía escritorio
  remoto (sesión interactiva con acceso al keychain).

**Verificación final:** Gmail, Notion, Calendar operativos desde Discord. Terminal
sandbox aislado y confirmado. Ollama accesible en red.

**INCIDENCIA SIN CERRAR:** con `qwen3:14b-hermes` (fine-tune Nous para
tool-calling, ya probado antes en item 49) y contexto correcto (64.000, confirmado
en config), una pregunta que dispara una tool (`get_current_time`, "qué día es
hoy") se quedó colgada sin error visible ni timeout — patrón DISTINTO al bloqueo
con error explícito ya documentado en el item 49 (`tool_call requires a name
argument`). Sin diagnosticar si es la misma causa raíz manifestándose distinto en
Docker, o un problema nuevo de red (conexión mantenida Docker↔
`host.docker.internal` muerta en silencio). Próximo paso pendiente: reproducir con
`docker compose logs -f` en vivo + doble curl consecutivo directo a Ollama desde
dentro del contenedor para descartar la capa de red.

**Pendiente residual nuevo:** archivar `ai.hermes.gateway.plist` y
`com.hermes.gateway.plist` (LaunchAgents nativos, ahora inertes tras la migración a
Docker) — verificar primero con `launchctl list | grep hermes` si sigue activo,
porque de estarlo hay riesgo real de doble-gateway compitiendo por `~/.hermes`
otra vez.

---

## Hecho hoy (2026-07-01)

### Emails independientes por categoría en ingesta semanal

`scripts/run_weekly_scopus.py` — antes enviaba un único email consolidado con todas las categorías; ahora envía **un email por categoría**:
- `build_html_single_cat()`: genera HTML para una sola categoría (tabla de 1 fila + DOIs pendientes filtrados por esa categoría).
- `send_category_emails()`: itera sobre `WEEKLY_CATEGORIES`, construye subject individual (`[research_agent] {cat} — {fecha} — N nuevos / M pendientes`), envía cada email. Si falla alguno, loguea y continúa; HTMLs fallidos concatenados en `/tmp/research_agent_weekly_report.html`.
- `main()` ya no llama a `send_email` directamente; delega a `send_category_emails()`.
- `build_html()` marcada como `# DEPRECATED — se usa build_html_single_cat() desde 2026-07-01`.

### Google AI Studio como provider gratuito en app pública

Nuevo provider en `2_RAG.py` (solo app pública, 8502) para que los compañeros del grupo usen modelos Gemini gratuitos con su propia API key de Google AI Studio:
- `app_utils.py`: `GOOGLE_AISTUDIO_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]`, `check_google_aistudio_api(api_key)` (valida formato + `models.list()`, sin caché), ventanas de contexto 1M en `LLM_CONTEXT_WINDOWS`.
- `2_RAG.py`: `get_google_aistudio_client(api_key)` — cliente OpenAI con `base_url` de Google AI Studio (sin `@st.cache_resource`, key por sesión). `stream_google_aistudio()` sigue el patrón de `stream_openrouter()` sin `extra_body`. Coste = 0.
- UX: el campo de API key (`st.text_input`, type=password) solo aparece al seleccionar "Google AI Studio" como provider. Con "Ollama (local)" no pide nada. Enlace a `https://aistudio.google.com/apikey` en el help.
- No aparece en la app privada (8501), que conserva Ollama/Anthropic/OpenAI/OpenRouter.
- Sin persistencia de key entre sesiones (requeriría sistema de usuarios — posible iteración futura).
- Fix 2026-06-30 (`0ebfa96`): `check_google_aistudio_api` solo aceptaba prefijo `AIza`; algunas API keys de Google AI Studio usan prefijo `AQ.` — ampliado el check a `api_key.startswith("AIza") or api_key.startswith("AQ.")`.

---

## Sesión 2026-06-28 (cont.) — Hermes: Plan B Rapid-MLX probado; bug de streaming; vuelta a OpenRouter

**PLAN B EJECUTADO (Rapid-MLX como backend de tool-calling local):**
- Instalado **Rapid-MLX 0.9.7** vía `uv tool install rapid-mlx` (entorno aislado, sin
  tocar Ollama/RAG ni el venv del RAG). Modelo: `mlx-community/Qwen3.5-9B-4bit`
  (~5-6 GB en disco, ~20 GB working set), servido en puerto 8000.
- **VALIDADO tool-calling en NO-streaming:** `curl` a `/v1/chat/completions` devuelve
  `tool_calls` estructurado perfecto (name + arguments). Confirma que el problema era
  el parser de la capa `/v1` de Ollama, NO el modelo; Rapid-MLX lo resuelve en
  no-streaming.
- **Integración con Hermes:** provider custom "Rapid-MLX (Qwen3.5-9B)" creado vía
  `hermes setup model` (`api_mode chat_completions`, `base_url localhost:8000/v1`,
  `context_length 64000`). En esta versión de Hermes, `provider: custom` + `base_url`
  en el bloque `model:` es válido (la regla previa "base_url nunca en `model:`" NO
  aplica aquí).
- **Funcionó UNA vez end-to-end** con whitelist mínima (solo Gmail; Notion + Calendar
  desactivados para bajar del umbral de deferred-tools ~13.107 tokens): el 9B llamó
  `get_label` y devolvió el conteo correcto.
- **LaunchAgent creado:** `~/Library/LaunchAgents/com.martin.rapidmlx.plist`
  (RunAtLoad, KeepAlive, host 127.0.0.1, puerto 8000, logs en
  `~/rapidmlx.launchd.log`/`.err`).

**BLOQUEANTE FINAL (bug de Rapid-MLX, no de la config):**
- En modo **STREAMING**, Rapid-MLX 0.9.7 NO promociona las tool-calls a estructurado:
  emite el XML `<tool_call><function=...><parameter=...>` como texto en `content`, con
  `finish_reason=stop` y sin `tool_calls`. Confirmado idéntico con 3 parsers (`hermes`,
  `qwen3_coder_xml`, `qwen3_xml`) — no es elección de parser.
- Hermes SIEMPRE usa streaming (`chat_completion_stream_request`) y NO es configurable:
  `extra_body: {stream: false}` en el provider es IGNORADO por el orquestador.
- Resultado: Hermes recibe respuesta vacía (`Empty response no content or reasoning`)
  y agota reintentos. Gmail no funciona vía Hermes + Rapid-MLX hoy.
- Causa raíz = bugs **ABIERTOS** del repo `raullenchai/Rapid-MLX`: **#197** (OutputRouter
  drops partial tool calls when stream ends mid-tool-call) y **#344** (port tool_call
  promotion to think_parser). No está en nuestra mano; esperar fix upstream.

**DECISIÓN:** volver a **OpenRouter** como provider de Hermes (modelo
`google/gemini-3.5-flash`). El tool-calling de Gmail vía OpenRouter funciona
end-to-end (validado en Discord). El servicio Rapid-MLX (LaunchAgent) queda instalado;
puede pararse para liberar RAM, reactivable con un `bootstrap` el día del fix.

**INCIDENTE de config (importante):**
- Múltiples ediciones manuales con `sed` durante la sesión erosionaron `config.yaml`
  hasta perder el bloque `mcp_servers` ENTERO (Gmail/Notion/Calendar) — `hermes mcp
  test gmail` → "Server not found". El fichero pasó de ~19 KB a ~14 KB.
- **RESTAURADO** desde backup `config.yaml.PRERAPIDMLX.20260628_150437` (19 KB, íntegro,
  con todos los MCP) y reaplicado OpenRouter con `hermes config set` (no edición
  manual).
- Tras restaurar, conflicto de puerto 3000 del MCP Gmail (`ClosedResourceError`)
  resuelto con `pkill -9 -f gmail-mcp` + kill puertos 3000-3002 (uno a uno: la sintaxis
  `lsof -ti :3000 :3001 :3002` no funciona en lsof 4.91) + `gateway restart`. Sistema
  operativo de nuevo.

**LECCIONES OPERATIVAS (importantes, corrigen supuestos previos):**
1. **CONFIG:** para cambios en `config.yaml` de Hermes usar SIEMPRE `hermes config set`
   / `hermes setup`, NUNCA `sed`/edición manual (corrompe/erosiona el fichero; ya van
   varios `.corrupt` + esta pérdida de `mcp_servers`). Backup explícito antes de
   cualquier sesión de cambios.
2. **TOOLSETS:** CORRECCIÓN sobre "adelgazar toolsets". Desactivar toolsets internos de
   Hermes en masa (`web`/`skills`/`todo`/`memory`/`clarify`/`session_search`...) ROMPE
   el funcionamiento del agente con OpenRouter (da error; se solucionó al
   REACTIVARLOS). Algunos toolsets internos son andamiaje del bucle de razonamiento, no
   opcionales como un MCP. Para uso normal: toolsets internos ACTIVOS; el control fino
   de tools se hace con `tools.include` por MCP (p.ej. Gmail 7 tools), NO desactivando
   toolsets nativos. El adelgazado en masa solo tuvo sentido como experimento puntual
   para medir el umbral de deferred-tools, no como estado permanente.
3. **ESTADOS TRANSITORIOS** ("funciona una vez y luego no"): patrón recurrente toda la
   sesión. Causas: (a) contexto de Discord contaminado (el modelo arrastra mensajes
   viejos y alucina — p.ej. "10 correos" reciclados de una sesión previa cuando los
   reales eran 19/24); (b) gateway con config vieja en memoria (un cambio en el fichero
   no surte efecto sin `gateway restart`, y a veces el restart no mataba el proceso
   viejo por el LaunchAgent con KeepAlive); (c) estados intermedios durante edición.
   REGLA: tras cambiar config → `gateway restart` siempre; antes de cada prueba limpia
   → `/reset` en Discord. Sin esa higiene, una prueba puede pillar un estado bueno
   transitorio y la siguiente fallar — los resultados no son fiables.

---

## Sesión 2026-06-27/28 — Hermes: depuración tool-calling local de Gmail (diagnóstico cerrado, fix pendiente)

**Resuelto:**
- **Causa del "modelo sin thinking":** el Modelfile `qwen3:14b-hermes` se había
  creado con `FROM <blob sha256>` en vez de `FROM qwen3:14b`, perdiendo la
  capability thinking. Recreado con `FROM qwen3:14b` + `num_ctx 64000` +
  `temperature 0.6`; verificado por API nativa que razona y emite tool-call correcta.
- **`context_length` corregido:** estaba en 1000000 (Hermes nunca comprimía); fijado
  a 64000. Nota: 32000 lanza `ValueError` (mínimo duro de Hermes = 64000). `num_ctx`
  del modelo igualado a 64000.
- **Doble-gateway resuelto:** `gateway restart` no mataba el viejo porque el
  LaunchAgent (KeepAlive) lo resucitaba. Fix: `launchctl bootout` → matar →
  `bootstrap` para gateway único supervisado. Detectado plist duplicado
  `com.hermes.gateway` (inerte, pendiente archivar).
- **MCP Gmail identificado:** `@shinzolabs/gmail-mcp` (Homebrew, 64 tools). Whitelist
  `tools.include` corregida (3 typos que no cargaban: `list_label`→`list_labels`,
  `get_messages`→`get_message`, `create_draf`→`create_draft`); 7 tools solo lectura +
  draft.
- **SOUL.md:** regla Gmail afinada (`get_label` con `id: "UNREAD"` obligatorio;
  `maxResults` siempre; nunca `includeBodyHtml`).
- **Seguridad verificada:** terminal/code_execution/browser/computer_use desactivados
  en CLI y Discord (gestión por plataforma, no por `disabled_toolsets` global).
- **Conteo de no leídos:** el valor "10" de las primeras pruebas era alucinación por
  contexto contaminado (history=28); el real es 19 (confirmado en Gmail). Lección:
  `/reset` entre tareas en sesiones locales largas.

**Diagnóstico cerrado (fix pendiente — plan B):**
- El tool-calling local de Gmail falla en la ruta Hermes→`/v1` de Ollama (envoltorio
  deferred-tools; error `tool_call requires a 'name' argument`, intermitente; una vez
  asomó `get_label` real con error de args `-32602`). Descartado por eliminación:
  modelo (curl `/api/chat` OK), `/v1` con tool mínima (curl OK), volumen de prompt
  (3.400 vs 14.300, falla igual), `tool_use_enforcement: none`. → **Plan B: Rapid-MLX
  como backend alternativo** (ver `Mejoras_pendientes.md` item 49).

**Decisión de arquitectura (modelo único RAG+Hermes): DESCARTADO.** Qwen3.6-35B-A3B
4-bit (~20 GB) no deja RAM para `bge-m3` en los 24 GB → rompería la convivencia con
el RAG; además piensa por defecto (malo para el pipeline de citas, ya validado con
`qwen2.5:14b`). El RAG mantiene `qwen2.5:14b-instruct` + `bge-m3` sin cambios. Un
modelo mayor para Hermes, si hace falta tras Rapid-MLX, iría cargado bajo demanda
(`KEEP_ALIVE` corto), nunca coresidente con el RAG. "Uno para todo" requeriría
48-64 GB de RAM.

## Sesión 2026-06-26 — Hermes: descarte modelo local, Gemini 2.5 Flash como default, limpieza Ollama

**Decisión final sobre modelo de Hermes:** `qwen3:8b` descartado definitivamente
para uso con MCPs en Hermes. Con 101 tools activas (Gmail 64, Calendar 17, Notion 20),
el modelo inventa herramientas inexistentes incluso filtrando Gmail a 4-5 tools.
No es un problema de configuración — es una limitación de capacidad del modelo 8B
para tool-calling complejo con esquemas MCP.

**Nuevo provider default: `google/gemini-2.5-flash` vía OpenRouter.**
- 1M tokens de contexto — las 101 tools no afectan al rendimiento.
- $0.30/M input, $2.50/M output — barato para uso cotidiano.
- Datos de Gmail ya están en Google → sin exposición adicional.
- Buen tool-calling con MCPs validado en sesión.
- `model.default: google/gemini-2.5-flash`, `provider: openrouter`,
  `context_length: 1000000` en `~/.hermes/config.yaml`.

**Simplificación de Hermes (modelo local eliminado):**
- `ollama rm qwen3:8b-hermes` — modelo derivado borrado.
- Crontab vaciado — keep-warm cron eliminado (ya no hay modelo local que calentar).
- Bloque `custom_providers` eliminado de `config.yaml` — `ollama-local` ya no
  aparece en el selector de `/model`.
- `~/hermes_keepwarm.sh` obsoleto (cron vacío).

**Limpieza Ollama — item 46 cerrado:**
Modelos borrados: `gemma3:4b`, `qwen3:14b`, `qwen3:8b-hermes`, `qwen3:8b`,
`nomic-embed-text` (y `mxbai-embed-large` si aplica).
Modelos activos en pciq22: `qwen2.5:14b-instruct` (~9 GB, RAG síntesis) +
`bge-m3` (~1.2 GB, embeddings FAISS). RAM unificada liberada: ~19+ GB.

**Problema recurrente documentado (Gmail MCP):**
`@shinzolabs/gmail-mcp` tiene el puerto 3000 hardcodeado en Express. Cuando una
instancia zombie queda en ese puerto, el siguiente arranque del gateway falla en
bucle (`EADDRINUSE`). Solución permanente: wrapper script
`~/.hermes/scripts/gmail-mcp-wrapper.sh` que mata el proceso en el puerto antes de
arrancar. Puerto cambiado a 3001 vía `PORT: '3001'` en env; `restartPolicy: 'never'`
para evitar reinicios en bucle. Fix rápido si vuelve a pasar:
`pkill -9 -f "gmail-mcp" && hermes gateway restart`.

## Sesión 2026-06-25 — Hermes Agent: infraestructura completa (Discord 24/7, MCPs, providers limpios)

**Cierre de la infraestructura de Hermes en pciq22** (item 49 prácticamente
completo, salvo dos sub-tareas residuales).

**LaunchAgent 24/7:**
- Plist `com.hermes.gateway.plist` creado y cargado. Hermes sobrevive a reinicios y
  se relanza si cae.
- Comando 24/7: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.hermes.gateway.plist`.
- Logs reales: `~/.hermes/logs/gateway.log` (Hermes los gestiona internamente; el
  plist apunta a `~/Library/Logs/hermes/` pero esa ruta queda vacía — informativo).

**MCPs instalados y validados (vía Discord):**
- **Notion** (HTTP): 20 tools, OAuth completado **desde el navegador de pciq22**
  (callback OAuth a `127.0.0.1:<puerto>` no funciona vía SSH/remoto). Toolset
  `mcp-notion` en `config.yaml`.
- **Google Calendar** (stdio): 17 tools, toolset `mcp-google-calendar`.
- **Gmail** (stdio): 64 tools, toolset `mcp-gmail`.

**Providers limpios (4 sin duplicados):**
- **OpenRouter (builtin, default)**: provider principal con
  `deepseek/deepseek-v4-flash` por coste/calidad. `OPENROUTER_API_KEY` en `.env`.
  Anthropic Sonnet 4.6 resultó caro (~20 USD en una sesión por sesiones largas que
  disparaban compresión cara) — descartado como default.
- **Anthropic**: API key en `.env`; disponible para consultas puntuales potentes,
  no como default.
- **Nous Portal**: logueado pero dormido.
- **ollama-local**: `qwen3:8b-hermes` para tareas locales/privadas.

**Compresión auxiliar barata:** `auxiliary.compression` con OpenRouter +
`google/gemini-2.5-flash` (~10x más barato que Haiku), `context_length: 1000000`.
Decisivo para no quemar crédito en sesiones largas.

**Otros:**
- Tavily web search activo (`TAVILY_API_KEY` en `.env`).
- Keep-warm cron `*/8 8-19 * * 1-5` (adelantado a las 8:00 para cubrir arranque
  mañanero).
- Seguridad: `terminal`, `code_execution`, `browser`, `computer_use` desactivados
  vía `hermes tools`. Activos solo los necesarios para productividad
  (web/memory/file/cronjob/skills/todo/etc.).

**Fixes durante la sesión (no van al repo, solo memoria):**
- `model.base_url` provocaba que TODAS las llamadas fueran a `localhost:11434/v1`
  ignorando el provider. Eliminado del bloque `model:`.
- `auxiliary.compression` se reseteaba a `provider: auto` disparando errores de
  context window <64K. Fijado a OpenRouter+Gemini.
- OpenRouter aparecía duplicado en `/model`. Borrado el custom; se usa el builtin
  que sí lee `OPENROUTER_API_KEY` correctamente.
- Reset desde Discord (`/reset`) revierte al default del config, no al modelo
  manual seleccionado — comportamiento conocido.

**Pendiente residual (no urgente):**
- Modelo local para Gmail vía override por MCP (privacidad correo UCA): por ahora,
  cambio manual con `/model` antes de consultas sensibles.
- Aplicar plist 04:00 en pciq22 (`launchctl bootout/bootstrap` tras `git pull`).

---

## Sesión 2026-06-24 — Hermes Agent: Discord, Anthropic, Tavily, keep-warm

- **Discord** operativo: bot "Hermes Bot" online, responde por DM y en canal `#general`.
  `DISCORD_BOT_TOKEN` + `DISCORD_ALLOWED_USERS` en `~/.hermes/.env`.
- **Anthropic** como provider de pago: `ANTHROPIC_API_KEY` en `.env`; actualmente
  default de facto por velocidad frente al modelo local.
- **Tavily** web search: `TAVILY_API_KEY` en `.env`; Hermes puede buscar noticias.
- **Keep-warm cron** activo: `~/hermes_keepwarm.sh` (curl a `/api/chat` con
  `keep_alive=10m`, `num_predict=1`) programado `*/8 9-18 * * 1-5` en crontab de
  martinramirez en pciq22. Mantiene `qwen3:8b-hermes` caliente en horario laboral sin
  tocar el keep_alive global (que protege la RAM del RAG).
- **Fix compresión**: `auxiliary.compression` en `~/.hermes/config.yaml` fijado a
  `provider: custom:ollama-local` + `context_length: 64000` para evitar el ValueError
  de "context window 40,960 < 64,000 mínimo".
- **Pendiente:** MCPs (Notion, Calendar, Gmail), LaunchAgent 24/7, seguridad.

---

## Sesión 2026-06-23

### Hermes Agent: Discord operativo + canales temáticos (sin commits de pipeline)

Hermes validado de punta a punta en `pciq22` a través de Discord (modelo
`qwen3:8b-hermes`, respuesta en español sin thinking, web search con Tavily verificado):

- **Bot conectado y validado** por DM y en canales. Intents **Message Content** y
  **Server Members** activados en el portal de Discord.
- **Gateway 24/7** vía LaunchAgent `ai.hermes.gateway` (del instalador), gestionado con
  `hermes gateway start|stop|restart`.
- **Acceso restringido:** `DISCORD_ALLOWED_USERS` = solo el User ID propio. Home channel
  fijado con `/sethome` a un Channel ID válido (entrega de crons y mensajes proactivos).
- **Tres canales temáticos** en el servidor (`docencia`, `investigacion`, `noticias`, `general`) en
  `discord.free_response_channels`: responden sin @mención y mantienen **contexto
  independiente por canal**. El resto sigue `require_mention: true`.
- **Web search Tavily** operativo, verificado con una búsqueda de noticias real.

**Learnings de la sesión:**

- El LaunchAgent es `ai.hermes.gateway` (creado por el instalador) y se gestiona con
  `hermes gateway`. El `launchctl bootout/bootstrap` manual por ruta dio **Input/output
  error** con el servicio en estado zombi (`LastExitStatus -15`); se desatascó con
  `hermes gateway stop` + arranque limpio.
- Causa del "silencio" inicial: se probaba en `#general` (que exige @mención real
  seleccionada del desplegable) en vez de por DM; y `DISCORD_HOME_CHANNEL` /
  `DISCORD_ALLOWED_USERS` tenían por error el **Application ID** del bot (provoca
  `404 Unknown Channel` al responder).
- La "calculadora de permisos del bot" del portal **no persiste estado al recargar por
  diseño** (genera el entero `274878286912` para la URL); los permisos reales viajan en
  la invitación. Es distinta de los **Privileged Gateway Intents**, que sí persisten.
- `free_response_channels` da **contexto separado por canal** = patrón para
  conversaciones temáticas; `/reset` reinicia la sesión del DM, no crea sesiones paralelas.

### RAG: chat premium con modo A/B y contexto de papers visible (commits 0e2bc3f → e5a41da)

Añadidas tres funcionalidades nuevas a `2_RAG.py` como extensión del bloque premium
(solo app privada):

**1. Consulta premium de un disparo (commit 0e2bc3f):**

- Bloque "🔎 Profundizar (modelo de pago)" visible solo si hay consulta previa con
  artículos rescatados. Lanza una segunda consulta con provider de pago
  (Anthropic/OpenAI/OpenRouter) sobre lo ya rescatado por el modelo local, sin re-recuperar.
- Modo A "mismos fragmentos" (cero FAISS, coste mínimo) o Modo B "profundizar en estos
  papers" (re-consulta FAISS filtrando por los `paper_id` rescatados, top_k 8–30).
- Respuesta premium junto a la gratuita (no la sobrescribe); registrada con campo `mode`
  (`premium_same_chunks` / `premium_deepen`).
- Refactor: `synthesize_answer()` como función única (ruta gratuita + premium + chat);
  `passes_filters()` en `utils/retrieval.py` ampliado para aceptar colección de `paper_id`
  exactos (Modo B). Campo `mode` añadido a `record_rag_query` / `record_rag_query_full`
  en `app_utils.py`.

**2. Chat con memoria — Fase 1 (commits 2ec6a6b, dffa3ed, 1e323bf, 7dccb18, e5a41da):**

- Bloque "💬 Chat con memoria sobre estos papers": historial de turnos en
  `_premium_chat_history`, coste acumulado en `_premium_chat_cost`.
- En cada turno se reenvían todos los chunks + historial + nueva pregunta (fidelidad
  máxima; el coste visible refleja la acumulación).
- Selector de modo por sesión: "Fragmentos recuperados" (usa `_last_results`, Modo A) o
  "Papers completos" (re-consulta FAISS filtrando por `paper_id` con top_k ampliado,
  Modo B). Helper reutilizable `_retrieve_paper_deepen_results()` compartido con la
  consulta de un disparo.
- Aviso de contexto largo cuando la estimación por caracteres/4 supera el 80 % de
  `LLM_CONTEXT_WINDOWS` (dict en `app_utils.py`).
- Botón "🗑 Nuevo hilo" limpia historial sin tocar el conjunto de papers.
- Expander "📄 Papers del conjunto actual (N papers)" al inicio del bloque premium:
  lista compacta (título, autores truncados a 3 + et al., año, DOI) + exportar ZIP;
  función reutilizable `_render_papers_export(papers, project, key_prefix)` usada
  también en los resultados de la búsqueda gratuita.
- Registro con `mode="premium_chat"`.
- **Fase 2 pendiente:** dossier editable / acumulación multi-búsqueda (item 48).

**3. Fixes de Streamlit aplicados durante la iteración:**

- `fix(rag): resetear input del chat premium sin violar regla de widget` (commit dffa3ed):
  asignación directa `st.session_state["premium_chat_input"] = ""` movida a callback
  `_submit_premium_chat` (corre antes de reinstanciar el widget).
- `fix(rag): inicializar prev_project antes de usarlo en render_premium_block`
  (commit e5a41da): `prev_project` inicializado junto a `prev_query` y `prev_papers`
  al inicio de `render_premium_block()` con `session_state.get(…, "")`.

### Infraestructura Hermes Agent en pciq22 (instalación manual, sin commits en este repo)

Instalado y validado Hermes Agent (Nous Research) en `pciq22.uca.es` como asistente
personal de productividad, independiente del RAG. Estado actual:

- **Modelo:** `qwen3:8b-hermes` (Modelfile derivado de `qwen3:8b`, `num_ctx 64000`,
  temperatura 0.6). Footprint 8.7 GB GPU, 100 % Metal, thinking desactivado vía
  `enable_thinking: false` en `extra_body` del provider.
- **Ollama** actualizado con `OLLAMA_FLASH_ATTENTION=1` y `OLLAMA_KV_CACHE_TYPE=q8_0`
  en el plist `com.martin.ollama.plist`. KV-cache `q8_0` reduce el footprint de 11 GB
  a 8.7 GB. Keep-alive global 5m (RAG y Hermes no coexisten residentes en 24 GB).
- **Config:** `~/.hermes/config.yaml` — provider `custom:ollama-local` apuntando a
  `http://localhost:11434/v1`; `context_length: 64000`; Nous Portal logueado pero
  dormido (no seleccionado como provider).
- **OpenRouter** añadido como provider opcional en `custom_providers` (para consultas
  puntuales potentes; selección manual, nunca automática).
- **Validado en CLI:** responde en español, sin thinking, 100 % GPU.
- **Pendiente:** Discord (bot, token, intents), MCPs (Notion OAuth, Google Calendar +
  Gmail vía cliente OAuth en GCP proyecto `hermes-pciq22`), web search (Tavily),
  keep-warm cron (9:00–18:00), seguridad (desactivar terminal/code_execution),
  LaunchAgent 24/7, actualizar `ESTADO.md` sección Hermes cuando esté completo.

### Ingesta semanal Scopus: hora cambiada de 06:00 a 04:00 (lunes)

- Plist `deployment/com.research_agent.scopus_weekly.plist` actualizado con `Hour=4`.
- Commit `chore:` mover ingesta semanal Scopus a las 04:00 (hash 0e2bc3f aprox).
- **Pendiente en pciq22:** `git pull` + `cp deployment/... ~/Library/LaunchAgents/` +
  `launchctl bootout/bootstrap` para que el launchd instalado recoja la nueva hora.
  Hasta que se aplique, la ingesta sigue a las 06:00.

---

### ✅ Contexto visible durante el chat premium: lista de papers + exportar ZIP (2026-06-23)
- Nuevo expander colapsado "📄 Papers del conjunto actual (N papers)" al inicio del bloque
  premium de `2_RAG.py` (antes de selectores de modo/provider e historial del chat), visible
  solo en la app privada.
- Muestra una línea compacta por paper con título, autores (truncados a 3 + et al.), año y DOI,
  obtenidos de `papers_metadata.jsonl` vía `load_papers_meta()`.
- Incluye el botón de exportar ZIP (PDFs y/o MD limpio) reutilizando la **misma** lógica que el
  expander de resultados gratuitos. Se extrajo la lógica a `_render_papers_export(papers, project,
  key_prefix)`; recibe un prefijo de clave para evitar duplicados de widgets de Streamlit cuando se
  usa en dos sitios de la misma página.
- Esto evita que los `st.rerun()` del chat hagan desaparecer el contexto del conjunto de papers:
  el usuario siempre puede desplegar el expander y ver/qué papers están en juego.
- **Fix**: inicialización de `prev_project` al inicio de `render_premium_block()` para evitar
  `UnboundLocalError` al construir la ruta a `papers_metadata.jsonl` cuando el usuario entra al
  bloque premium sin haber disparado previamente el handler del chat.

---

### ✅ Chat con memoria sobre papers rescatados en RAG — Fase 1 (2026-06-23)
- Nuevo bloque "💬 Chat con memoria sobre estos papers" dentro del área premium de
  `2_RAG.py`, solo app privada (`is_public_app()` guard). No aparece en la app pública.
- Mantiene un historial de turnos en `st.session_state["_premium_chat_history"]` y un coste
  acumulado de la sesión en `st.session_state["_premium_chat_cost"]`.
- En cada turno se reenvían al modelo de pago **todos los chunks** de la última búsqueda más
  el historial completo y la nueva pregunta (máxima fidelidad, decisión documentada).
- Reutiliza el mismo selector de provider/modelo de pago (Anthropic / OpenAI / OpenRouter) y
  la **misma** función `synthesize_answer()`, extendida aditivamente con un parámetro opcional
  `history=None`. Cuando `history` es `None` el comportamiento es idéntico al anterior (rutas
  gratuita y premium de un disparo intactas).
- El historial se pasa como mensajes `system` (reglas + fragmentos) + mensajes previos
  `user`/`assistant` + nueva pregunta. Ollama recibe un prompt plano equivalente.
- Botón "🗑 Nuevo hilo" que limpia el historial y el coste acumulado pero conserva el conjunto
  de papers (`_last_results`). Una nueva búsqueda gratuita también resetea el hilo.
- Coste acumulado visible en la UI (`Coste acumulado del hilo` + `Último turno`), actualizado
  en cada turno sumando al acumulado previo.
- Aviso de contexto largo: estimación por caracteres/4 del payload (chunks + historial +
  pregunta + tokens de salida); si supera el 80 % de la ventana del modelo seleccionado se
  muestra `st.warning` sugiriendo nuevo hilo o reducir el conjunto.
- Cada turno se registra en `rag_usage_*.jsonl` y `rag_queries_*.jsonl` con `mode="premium_chat"`.
- Hereda el post-procesado de citas (`apply_citations`, que incluye `strip_reference_section`)
  de `synthesize_answer()`; las respuestas del chat usan `[N]` como el resto de rutas.
- Mapa de ventanas de contexto añadido a `app_utils.py` (`LLM_CONTEXT_WINDOWS`) para los
  modelos de pago y Ollama.

---

### ✅ Consulta premium (modelo de pago) sobre artículos rescatados en RAG (2026-06-23)
- Nuevo bloque "🔎 Profundizar (modelo de pago)" en `2_RAG.py`, visible SOLO cuando ya hay
  una consulta previa con artículos rescatados y SOLO en la app privada (guard
  `is_public_app()` → no aparece en la pública, para que el grupo no dispare gasto).
- Dos modos en un selector:
  - **A "Mismos fragmentos"**: el modelo de pago razona sobre exactamente los chunks que
    recuperó la consulta gratuita (local). No toca FAISS → coste mínimo.
  - **B "Profundizar en estos papers"**: re-consulta FAISS restringido a los `paper_id`
    rescatados con un top_k ampliado (slider 8–30, default 15) para dar más contexto.
- Valor económico: la recuperación (lo caro en cómputo) la hace el modelo local gratis; al
  de pago solo se le pasa un contexto pequeño y ya filtrado → céntimos por consulta.
- Reutiliza el mecanismo de provider existente (Anthropic / OpenAI / OpenRouter, sin Ollama
  aquí) y la **misma** función de síntesis: se refactorizó la síntesis inline a
  `synthesize_answer()`, usada por la ruta gratuita y la premium (sin implementación LLM
  paralela). El post-proceso de citas (`apply_citations` / `strip_reference_section`) se
  aplica igual a la respuesta premium.
- La respuesta premium se muestra **junto a** la gratuita (no la sobrescribe), etiquetada con
  modelo, modo, nº de fragmentos y coste real. Pre-estimación de coste antes de lanzar.
- Registro de coste en `rag_usage_*.jsonl` y `rag_queries_*.jsonl` con campo
  `mode` ("premium_same_chunks" | "premium_deepen"; "standard" en las normales).
- Persistencia: solo `st.session_state` (chunks de la consulta previa en `_last_results`);
  basta para el flujo "consulta gratis → Profundizar a continuación". No se creó cache en
  disco (menos es más). Patrón flag (`_do_premium`) + `st.rerun()`.
- `passes_filters()` (utils/retrieval.py) admite ahora `paper` como colección de `paper_id`
  exactos además de substring, para el filtro del Modo B (reutilizado, no reimplementado).

---

### ✅ OpenRouter como provider de síntesis en RAG (2026-06-21)
- Cuarto provider en `2_RAG.py` (solo app privada): deepseek-v4-flash/pro, kimi-k2.6, glm-5.2.
- OpenAI-compatible: `get_openrouter_client()` = SDK `openai` con base_url de OpenRouter +
  `OPENROUTER_API_KEY`. `check_openrouter_api()` valida key vía /credits.
- Coste REAL leído de la respuesta (`extra_body={"usage":{"include":True}}`), con fallback a
  `usage.model_extra["cost"]`; override sobre `estimate_cost_usd`. Sin precios estáticos en
  `LLM_PRICING` para estos modelos. Pre-estimado muestra "se calcula tras la consulta".
- `OPENROUTER_API_KEY` se añade a mano en `config/.env` (no va a git) en casa y en pciq22.

---

### ✅ Ingesta semanal: +bioplastics_microplastics + filtro de año rodante (2026-06-21)
- `scripts/run_weekly_scopus.py`: `WEEKLY_CATEGORIES` añade `"bioplastics_microplastics"`
  (3 categorías ahora).
- Suelo de año rodante en la descarga semanal: `run_scopus(..., year_start=año_actual-1)`.
  Motivo: `recent_days=7` filtra por fecha de indexación en Scopus, no por año de
  publicación, así que papers antiguos reindexados entraban en la ventana. Floor rodante
  (vigente + anterior) sin `year_end` para no perder online-first con cover date adelantada.
- Solo reduce ruido temporal (reindexados viejos), no topical (falsos positivos de query
  de anoxic siguen igual). Backfill histórico aparte si se quiere recuperar lo descartado.

---

### ✅ pool_candidates.py — construcción de golden sets por pooling (2026-06-20)

**`scripts/pool_candidates.py`** (nuevo, CLI con subcomandos `pool` y `build`). Reutiliza las mismas funciones de retrieval que `run_eval.py`/`2_RAG.py` (`embed_query`, `dense_rank`, `bm25_rank`, `rrf_fuse`, `pool_size`, `build_bm25`) → cero divergencia con producción.

- `pool`: por pregunta de `questions_<cat>.json`, recupera candidatos (unión denso + híbrido, `--pool-k`) y escribe `review_<cat>.md` con checkboxes ordenados por `min(rank_denso, rank_híbrido)`.
- `build`: lee las líneas `[x]` del review → `golden_<cat>.jsonl`. Valida cada `paper_id` contra `embeddings/<phase>/metadata.jsonl` y aborta si hay fantasmas (guard anti guion/underscore).
- Flujo en `metadatos/eval/`: `questions_<cat>.json` (entrada) → `review_<cat>.md` (se marca) → `golden_<cat>.jsonl` (salida, la consume `run_eval.py`). Nunca renombrar uno sobre otro.

---

### ✅ 37 (parcial). Golden Q&A — biogas_upgrading_biomethanation (2026-06-20)

2ª categoría, construida con `pool_candidates.py`. 6 preguntas: trickle-bed/biotrickling termófilo, transferencia de H2 (kLa) ex-situ, arqueas hidrogenotróficas termófilas, ratio H2:CO2, biometano→proteína (SCP), inhibidores.

| Modo    | Hit@8 | MRR   |
|---------|-------|-------|
| Denso   | 1.000 | 0.889 |
| Híbrido | 1.000 | 0.857 |

- Híbrido neutro-a-negativo: arregla Q2 (kLa, pos3→pos1), rompe Q1 (trickle-bed, pos1→pos7).
- Patrón en 2 categorías: híbrido ≤ denso (anoxic 0.50→0.25 Hit@8; biogas 0.889→0.857 MRR). BM25+RRF no ayuda de forma fiable → mantener OFF; revisar fusión antes del reranking (item 33 fase 2).
- Nota metodológica: ground truth por pooling → Hit@8 absoluto optimista (MRR es el dato fino); denso-vs-híbrido sí es justo (pool de ambos modos). NO comparable en absoluto con anoxic (golden de autoría independiente).

---

### ✅ run_eval.py — flujo de evaluación Hit@k / MRR (completado 2026-06-20)

**`scripts/run_eval.py`** (nuevo, CLI):

- Lee `metadatos/eval/golden_<categoria>.jsonl`, ejecuta retrieval puro reusando `utils/retrieval.py` (mismo flujo que `2_RAG.py`: `embed_query` → `dense_rank` [+ `bm25_rank` + `rrf_fuse` si `--hybrid`]), sin filtros ni síntesis LLM.
- Calcula Hit@k y MRR por pregunta y agregado; exporta CSV a `metadatos/eval/results_<categoria>_<timestamp>.csv`.
- Flags: `--category`, `--phase` (default `all`), `--k` (default 8), `--hybrid`.

**Fix crítico de datos:** 3 `relevant_paper_ids` en `golden_anoxic_biogas_biodesulfurization.jsonl` tenían guion (`-`) en vez de guion bajo (`_`) — Claude Code los había "corregido" verificando contra nombres de fichero PDF en vez de contra el `paper_id` real indexado en FAISS (`embeddings/all/metadata.jsonl`, generado por `safe_slug()` en `3_process_corpus.py`, que usa siempre `_`). Revertido a `_` en los 3 IDs; verificado contra el índice real tras el fix.

**Primeros resultados** (`anoxic_biogas_biodesulfurization`, k=8):

| Modo    | Hit@8 | MRR   |
|---------|-------|-------|
| Denso   | 0.50  | 0.098 |
| Híbrido | 0.25  | 0.062 |

Denso supera a híbrido en esta categoría/golden set — contraintuitivo, a vigilar al añadir más categorías antes de sacar conclusiones generales.

**Pendiente anotado:** integrar `run_eval.py` en Streamlit (botón + tabla de resultados) cuando haya más categorías con golden set — de momento queda como CLI por comodidad de desarrollo.

---

### ✅ 37 (parcial). Golden Q&A set — anoxic_biogas_biodesulfurization (completado 2026-06-20)

`/Volumes/research/metadatos/eval/golden_anoxic_biogas_biodesulfurization.jsonl` — primera categoría del golden eval set, validada manualmente por dominio experto:

- 4 preguntas: pH óptimo, ratio molar N/S → azufre elemental, especies bacterianas predominantes, fuentes de amonio nitrificadas.
- Cada pregunta con `answer` de referencia y `relevant_paper_ids` (16 paper_ids en total, varios por pregunta).
- 3 IDs requirieron corrección de normalización (guion vs guion bajo: `open-pore`, `pcr-dgge`, `start-up_long-term`) — los nombres de PDF con guion no siempre coinciden con el slug esperado; verificado contra el corpus real antes de cerrar el fichero.
- Pendiente: resto de categorías (sugeridas: `biogas_upgrading_biomethanation` a continuación). Bloquea item 33 fase 2 (reranking) hasta tener cobertura suficiente.

---

### ✅ 36-A. Detalle de estado por paper en pestaña Pendientes (completado 2026-06-20)

**`scripts/streamlit_app/app_utils.py`:**

- Nueva función `get_paper_status(category)` — lee PDFs de `pdfs/`, cruza contra `tei/`, `md_clean/`, `chunks/`, `summaries/`, `metadata/papers_metadata.jsonl` e `embeddings/all/indexed_papers.json`. Devuelve solo papers con al menos un artefacto ausente.
- Fix: ruta del índice FAISS corregida a `embeddings/all/` (el directorio real del índice bge-m3 por defecto).

**`scripts/streamlit_app/pages/1_Ingestar.py` — pestaña Pendientes:**

- Bloque "🔍 Detalle por paper" tras el `st.metric` de categorías incompletas.
- Un expander por categoría incompleta con `st.dataframe` columnas: `paper_id / PDF / TEI / MD / Chunks / Resumen / Metadata / FAISS` (`✓`/`✗`). Solo muestra papers con al menos un artefacto ausente.

---

### ✅ Log persistente de ingesta (completado 2026-06-20)

**`scripts/streamlit_app/pages/1_Ingestar.py`:**

- Constantes `_LOG_ACTIVE` y `_LOG_HIST_DIR` apuntando a `/Volumes/research/logs/`.
- `_archive_log(label)` — mueve `ingesta_en_curso.log` a `ingesta_history/ingesta_<label>_<ts>.log` al terminar.
- `execute_with_live_output` escribe cada línea de `on_output` al fichero con `buffering=1` (line-buffered).
- `try/finally` garantiza `_log_file.close()` + `_archive_log()` aunque el navegador esté cerrado al terminar.
- Expander "📋 Ingesta en curso o reciente" aparece automáticamente al reconectar si el fichero existe; botón "Descartar" para archivarlo manualmente.

---

### ✅ Restauración reversible desde la UI de cuarentena de duplicados (2026-06-17)

- **`quarantine_paper()` ampliada:** captura las líneas JSONL retiradas de `papers_metadata.jsonl` en el manifiesto como `"meta_lines"`; el manifiesto se escribe si `moved or removed_lines` (antes solo si `moved`).
- **Nueva `restore_from_quarantine(manifest_path, base)`** en `9_cleanup_duplicates.py`: mueve los ficheros de vuelta con `shutil.move` (nunca sobrescribe — warning si orig ya existe o target falta); reinserta `meta_lines` en `papers_metadata.jsonl` con dedup por `file_key` y backup `.bak`; warning si el manifiesto es legacy sin `meta_lines` → sugiere regenerar con `4_extract_metadata.py --project <cat>`.
- **UI en `10_Duplicados.py`:** nueva sección "♻️ Restaurar de cuarentena" — selectbox de timestamp (orden desc), multiselect de manifiestos con flag `✓/✗ meta`, preview de lo que se restaurará, checkbox de confirmación, botón "Restaurar"; reutiliza el bloque de re-index vía `dup_affected`; warnings y resumen de éxito sobreviven al `st.rerun()`.
- **VERIFICADO en pciq22 (2026-06-17):** ruta legacy (manifiesto del 13/06 sin `meta_lines`) → 7 ficheros restaurados + warning correcto (`"manifiesto antiguo sin meta_lines: regenera con 4_extract_metadata.py --project <cat>"`) + regeneración manual con `4_extract_metadata.py` + re-index OK. Captura de `meta_lines` activa para cuarentenas nuevas.
- **PENDIENTE:** validar el round-trip de la ruta `✓ meta` (reinserción automática de la línea de metadata al restaurar) con un paper de juguete.

---

### ✅ 41. Cuarentena de índices viejos all__bge-m3 (ejecutado 2026-06-16, documentado 2026-06-17)

Fases `all__bge-m3` divergentes (sin `section_canonical`/`year` en sus chunks) movidas fuera de `categorias/` para que no compitan con el índice canónico. 6 categorías afectadas:
`microalgae`, `advanced_oxidation_processes`, `anoxic_biogas_biodesulfurization`,
`biogas_upgrading_biomethanation`, `bioleaching_critical_materials`, `bioplastics_microplastics`.

Ruta de cuarentena: `/Volumes/research/quarantine/old_indexes/20260616_011551/<cat>/all__bge-m3/` (~8,2 MB en total). Operación reversible — los índices se conservan, no se borran. Índice canónico vivo de cada categoría: `embeddings/all/index.faiss` (fase "all", items 32/34).

---

### ✅ 45. Consolidar utilidades de texto — fuente única en pdf_utils (2026-06-17)

`strip_accents`, `slugify`, `shorten_title`, `sanitize_filename` y `STOPWORDS` estaban duplicadas y divergentes entre `utils/pdf_utils.py` y `1_rename_papers_by_doi.py`. Consolidadas en `pdf_utils` portando las versiones correctas de `1_rename`:
- `shorten_title`: eliminado `\-` del `re.sub` de limpieza (guiones ya se convierten a `_` vía split).
- `sanitize_filename`: añadido `re.sub(r"\s+", "_", name)` tras el paso de chars inválidos.

`1_rename` ahora importa los cinco símbolos desde `pdf_utils`; defs locales y banner eliminados. `unicodedata` conservado (uso independiente en línea 200). `test_rename.py` repuntado de importlib a `from utils.pdf_utils import …`. Sin cambio de comportamiento en el renombrador. Suite: 99/99 passed.

---

### Cierre de hallazgos pendientes (2026-06-17)

- **sort_keys=True en `promote_adhoc_to_category`** — corregido a `sort_keys=False` en `scripts/pipeline.py` (línea 1253); keywords.yml ya no se reordena alfabéticamente en cada promoción, la categoría nueva se añade al final.
- **Filtro de año descarta papers con `year=None` en silencio** — documentado como decisión aceptada. Función `passes_filters()` en `scripts/utils/retrieval.py` líneas 76-80: si `year` no está en metadata ni es derivable de `paper_id`, el chunk se excluye cuando hay filtro de año activo. Comportamiento correcto, no requiere cambio.
- **`run_scopus` filtraba activas también con categorías explícitas** — corregido en `scripts/pipeline.py` (~línea 734): bloque `if not categories:` envuelve el filtro de `active_categories.yml`; una petición explícita (CLI/web) ya no puede ser descartada en silencio.
- **`section_canonical` vs `CANONICAL_SECTIONS`: riesgo de drift** — verificado que no habían divergido (6 patrones + `"other"` + `"table"` de `build_chunk_records` = 8 etiquetas del constant). Blindado con `tests/test_canonical_sections.py` (7 tests, guard de cobertura + 6 ejemplos paramétricos).

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
