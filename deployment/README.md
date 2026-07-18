# deployment/

Plists de `launchd` (patrón `~/Library/LaunchAgents/`) y configuración de
Caddy para los servicios de `research_agent` en pciq22.

## Servicios

| Plist | Qué hace |
|---|---|
| `com.research_agent.streamlit.plist` | Streamlit privada, puerto 8501 |
| `com.research_agent.streamlit_public.plist` | Streamlit pública, puerto 8502 |
| `com.research_agent.scopus_weekly.plist` | Ingesta semanal Scopus (lunes) |
| `com.research_agent.caddy_ollama.plist` | Proxy Caddy con auth Bearer delante de Ollama, puerto 11434 |
| `com.research_agent.daily_question.plist` | Pregunta diaria (tiempo/mareas) por email, 06:00 todos los días — **LaunchDaemon**, no LaunchAgent (ver abajo) |

Todos siguen el mismo patrón: `PATH` fijado a mano en el plist (launchd no
carga `.zprofile`) con `/opt/homebrew/bin` incluido, y logs en
`~/Library/Logs/research_agent/` (**nunca** en `/Volumes/*`: TCC bloquea la
escritura de logs de launchd ahí).

### Por qué `daily_question` es un LaunchDaemon y no un LaunchAgent

Un LaunchAgent normal vive en `~/Library/LaunchAgents/` y está atado a la
sesión gráfica (Aqua) del usuario (`monitor = com.apple.UserEventAgent-Aqua`
en `launchctl print`). Si el Mac se reinicia (crash, corte, lo que sea) y
nadie inicia sesión gráfica antes de las 06:00, el disparador de esa hora se
pierde sin más — launchd no reintenta triggers de `StartCalendarInterval`
perdidos. Esto pasó de verdad dos veces (16 y 18 de julio de 2026): el Mac
mini está siempre encendido y sin sesión gráfica hasta que alguien se conecta
por Screen Sharing, así que un LaunchAgent es la elección equivocada aquí.

Por eso `daily_question` está instalado como **LaunchDaemon** en
`/Library/LaunchDaemons/` (dominio `system`, no `gui/<uid>`), con `UserName`
puesto a `martinramirez` para que corra con los permisos del usuario (acceso
a `~/claude-scheduled/`, credenciales de `claude` CLI) sin necesitar sesión
gráfica activa. Verificado empíricamente que `claude --print` se autentica
bien en este contexto (no depende del desbloqueo del llavero de sesión).

Un LaunchDaemon con `UserName` **no hereda `$HOME`** — hay que fijarlo a mano
en `EnvironmentVariables`, si no el script no encuentra
`~/claude-scheduled/question.md` ni el resto de rutas.

Reinstalar tras editar el plist (requiere `sudo`, dominio `system`):

```bash
sudo cp deployment/com.research_agent.daily_question.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.research_agent.daily_question.plist
sudo chmod 644 /Library/LaunchDaemons/com.research_agent.daily_question.plist
sudo launchctl bootout system/com.research_agent.daily_question 2>/dev/null
sudo launchctl bootstrap system /Library/LaunchDaemons/com.research_agent.daily_question.plist
```

El LaunchAgent viejo (`~/Library/LaunchAgents/com.research_agent.daily_question.plist.disabled`)
se dejó renombrado en vez de borrado, por si hiciera falta revertir.

## Reinstalar / actualizar el servicio Caddy (proxy Ollama)

```bash
cp deployment/com.research_agent.caddy_ollama.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.caddy_ollama.plist 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.caddy_ollama.plist
```

Caddy lee el Caddyfile de `deployment/Caddyfile.ollama` (versionado, sin
secretos) y carga `OLLAMA_API_KEY` desde `config/.env.caddy_ollama` vía
`--envfile` (ver `ProgramArguments` del plist). Este fichero es un secreto
**mínimo** aparte de `config/.env` — así el proceso Caddy no carga en su
entorno el resto de claves (OpenAI, Anthropic, SMTP...). Debe mantenerse en
sincronía con `OLLAMA_API_KEY` en `config/.env` (mismo valor, dos ficheros).
Plantilla versionada: `config/.env.caddy_ollama.example`.

Si cambias el Caddyfile basta con recargar sin caída:

```bash
caddy fmt --overwrite deployment/Caddyfile.ollama   # opcional, formatea
launchctl kickstart -k gui/$(id -u)/com.research_agent.caddy_ollama
```

### Arquitectura

```
Cliente remoto ──Bearer──▶ Caddy :11434 (0.0.0.0) ──▶ Ollama 127.0.0.1:11435
Cliente local (pipeline, Streamlit) ─────────────────▶ Ollama 127.0.0.1:11435 (directo, sin token)
GROBID: solo 127.0.0.1:8070, sin proxy (nada remoto lo usa)
```

### Qué debe configurar un cliente remoto

- **URL**: sin cambios — `http://pciq22.uca.es:11434` (la misma de siempre).
- **Cabecera obligatoria**: `Authorization: Bearer <token>`. Sin ella, Caddy
  responde `401 Unauthorized` antes de llegar a Ollama.
- El token vigente es el valor de `OLLAMA_API_KEY` en `config/.env` (no
  versionado — pregúntalo si necesitas configurarlo en otra máquina/app, p.ej.
  el plugin Ollama de Obsidian).

### Rotar el token

```bash
NEW_TOKEN=$(openssl rand -hex 32)
# Editar OLLAMA_API_KEY=$NEW_TOKEN en AMBOS ficheros:
#   config/.env
#   config/.env.caddy_ollama
launchctl kickstart -k gui/$(id -u)/com.research_agent.caddy_ollama
```

Después, actualizar el token en todos los clientes remotos (Obsidian, etc.).
No hace falta tocar Ollama ni reiniciarlo — solo Caddy relee
`config/.env.caddy_ollama` al arrancar.

## Tools de Obsidian (`tools/obsidian.py`)

El agente puede leer todo el vault de Obsidian y crear/anexar notas
**solo** dentro de `00_Inbox/` (garantía a nivel de código en
`_validar_ruta_escritura`, no de prompt — ver docstring del módulo). Cliente
contra el plugin **Local REST API with MCP** (coddingtonbear), que debe estar
activo en Obsidian y escuchando en `https://127.0.0.1:27124` (HTTPS
autofirmado).

### Configurar la API key

1. En Obsidian: **Ajustes → Local REST API with MCP → API Key** (cópiala).
2. `cp config/.env.obsidian.example config/.env.obsidian`
3. Pega la key en `OBSIDIAN_API_KEY=` dentro de `config/.env.obsidian`.

Igual que `config/.env.caddy_ollama`, es un secreto **aparte** de
`config/.env`: aísla el token por proceso consumidor (`tools/obsidian.py` lo
carga directamente, no pasa por el `.env` general). No versionado
(`.gitignore`); plantilla versionada: `config/.env.obsidian.example`.

Variables opcionales (normalmente no hace falta tocarlas):

- `OBSIDIAN_BASE_URL` — por defecto `https://127.0.0.1:27124`.
- `OBSIDIAN_CA_CERT` — ruta a un certificado CA si en el futuro se prefiere
  verificar el TLS autofirmado del plugin en vez de desactivar la
  verificación (comportamiento por defecto, `verify=False`, con el warning
  de urllib3 suprimido solo en las llamadas de este módulo).

### Si Obsidian está cerrado

Cualquier tool devuelve un mensaje de error claro (p. ej. *"Obsidian no está
corriendo en pciq22 — abre la app y reintenta"*) en vez de lanzar una
excepción de red o colgar el bucle del agente. Timeout de 5 s por petición.

### Alcance de las 4 tools

| Tool | Alcance | Endpoint |
|---|---|---|
| `leer_nota(ruta)` | Todo el vault (solo lectura) | `GET /vault/{ruta}` |
| `buscar_en_vault(query)` | Todo el vault (solo lectura) | `POST /search/simple/` |
| `crear_nota_inbox(nombre, contenido, tags)` | Solo `00_Inbox/` | `PUT /vault/00_Inbox/{nombre}.md` |
| `anexar_a_nota_inbox(ruta, contenido)` | Solo `00_Inbox/` | `POST /vault/{ruta}` |

No hay tools de borrado ni de mover ficheros. `crear_nota_inbox` nunca
sobrescribe: si el nombre ya existe, añade un sufijo `_AAAAMMDD_HHMMSS`.

Nota: el registro de estas tools en un bucle de tool-calling (formato
`tools=[...]` de la API de chat de Ollama, con `qwen3:14b` en el Ollama de
`127.0.0.1:11435`) queda pendiente — de momento el módulo está listo para
integrarse pero no hay un bucle de agente en el repo que lo consuma.

## Notas

- Ollama en sí (`com.martin.ollama.plist`, fuera del repo en
  `~/Library/LaunchAgents/`) escucha solo en `127.0.0.1:11435` — no acepta
  conexiones de red directas, ni siquiera sin el proxy.
- GROBID (`~/grobid-compose.yml`, fuera del repo) publica el puerto como
  `127.0.0.1:8070:8070` — tampoco alcanzable desde la red.
