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

Todos siguen el mismo patrón: `PATH` fijado a mano en el plist (launchd no
carga `.zprofile`) con `/opt/homebrew/bin` incluido, y logs en
`~/Library/Logs/research_agent/` (**nunca** en `/Volumes/*`: TCC bloquea la
escritura de logs de launchd ahí).

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

## Notas

- Ollama en sí (`com.martin.ollama.plist`, fuera del repo en
  `~/Library/LaunchAgents/`) escucha solo en `127.0.0.1:11435` — no acepta
  conexiones de red directas, ni siquiera sin el proxy.
- GROBID (`~/grobid-compose.yml`, fuera del repo) publica el puerto como
  `127.0.0.1:8070:8070` — tampoco alcanzable desde la red.
