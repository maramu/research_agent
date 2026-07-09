# -*- coding: utf-8 -*-
"""tools/obsidian.py — Tools de lectura/escritura sobre el vault de Obsidian.

Cliente mínimo sobre `requests` contra el plugin "Local REST API with MCP"
(coddingtonbear) de Obsidian, expuesto como 4 tools de tool-calling:

    leer_nota(ruta)                          — lectura, todo el vault
    buscar_en_vault(query)                   — búsqueda de texto, todo el vault
    crear_nota_inbox(nombre, contenido, tags) — SOLO 00_Inbox/
    anexar_a_nota_inbox(ruta, contenido)      — SOLO 00_Inbox/

GARANTÍA DE ESCRITURA: crear_nota_inbox y anexar_a_nota_inbox pasan siempre
por `_validar_ruta_escritura`, que lanza `PermissionError` ante cualquier
ruta fuera de `00_Inbox/` (absolutas, con `..`, u otras carpetas) o que no
termine en `.md`. Esa función es la garantía real — un refuerzo en el system
prompt del agente ayuda, pero NO sustituye este control a nivel de código.
No existen tools de borrado ni de movimiento de ficheros.

Config (config/.env.obsidian — NO config/.env general, mismo principio que
config/.env.caddy_ollama: aislar el secreto por proceso consumidor):
    OBSIDIAN_API_KEY   API key del plugin (Settings → Local REST API with MCP)
    OBSIDIAN_BASE_URL  Por defecto https://127.0.0.1:27124
    OBSIDIAN_CA_CERT   Opcional; ruta a un cert CA para verificar TLS en vez
                       de desactivar la verificación (ver _verify_arg).
"""
from __future__ import annotations

import logging
import os
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from urllib3.exceptions import InsecureRequestWarning

log = logging.getLogger("obsidian")

# ── Config aislada: config/.env.obsidian ────────────────────────────────────
_ENV_FILE = Path(__file__).resolve().parent.parent / "config" / ".env.obsidian"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)

OBSIDIAN_BASE_URL = os.getenv("OBSIDIAN_BASE_URL", "https://127.0.0.1:27124").rstrip("/")
# Tolerante a que alguien pegue el valor completo de la cabecera ("Bearer xxx")
# en vez de solo el token — evita un "Authorization: Bearer Bearer xxx" roto.
OBSIDIAN_API_KEY = re.sub(r"(?i)^bearer\s+", "", os.getenv("OBSIDIAN_API_KEY", "").strip())
OBSIDIAN_CA_CERT = os.getenv("OBSIDIAN_CA_CERT", "")

_TIMEOUT = 5  # segundos — nunca dejar colgado el bucle del agente

VAULT_WRITE_ROOT = "00_Inbox/"


# ---------------------------------------------------------------------------
# Validación de ruta de escritura — única garantía real de que el modelo no
# puede escribir fuera de 00_Inbox/. Todo lo demás (system prompt) es refuerzo.
# ---------------------------------------------------------------------------

def _validar_ruta_escritura(ruta: str) -> str:
    """Normaliza y valida que ``ruta`` quede dentro de ``00_Inbox/`` y sea un
    fichero ``.md``. Lanza ``PermissionError`` en cualquier otro caso
    (rutas absolutas, con ``..``, fuera de 00_Inbox/, u otra extensión).

    Devuelve la ruta normalizada (barras ``/``, sin barra inicial) lista para
    usar contra la API del plugin.
    """
    original = ruta
    ruta = (ruta or "").strip()

    if not ruta:
        raise PermissionError("Ruta vacía")

    ruta = ruta.replace("\\", "/")

    if ruta.startswith("/") or os.path.isabs(ruta):
        raise PermissionError(f"Ruta absoluta no permitida (recibido: {original!r})")

    if ".." in ruta.split("/"):
        raise PermissionError(f"Ruta con '..' no permitida (recibido: {original!r})")

    ruta_norm = os.path.normpath(ruta).replace("\\", "/")

    if ruta_norm == "." or ruta_norm == ".." or ruta_norm.startswith("../"):
        raise PermissionError(f"Ruta fuera del vault (recibido: {original!r})")

    if not (ruta_norm + "/").startswith(VAULT_WRITE_ROOT):
        raise PermissionError(
            f"Escritura permitida solo bajo {VAULT_WRITE_ROOT} (recibido: {original!r})"
        )

    if not ruta_norm.endswith(".md"):
        raise PermissionError(f"Solo se permite escribir ficheros .md (recibido: {original!r})")

    return ruta_norm


def _sanitizar_nombre(nombre: str) -> str:
    """Limpia ``nombre`` para usarlo como nombre de fichero en macOS/Syncthing:
    sin separadores de ruta ni caracteres problemáticos."""
    nombre = (nombre or "").strip()
    nombre = nombre.replace("/", "_").replace("\\", "_")
    nombre = re.sub(r'[<>:"|?*\x00-\x1f]', "_", nombre)
    nombre = re.sub(r"\s+", "_", nombre)
    nombre = re.sub(r"_+", "_", nombre).strip("._ ")
    return nombre or "nota"


# ---------------------------------------------------------------------------
# Cliente HTTP mínimo
# ---------------------------------------------------------------------------

def _encode_path(ruta: str) -> str:
    return quote(ruta, safe="/")


def _verify_arg():
    """https autofirmado del plugin: verify=False por defecto (con el warning
    de urllib3 suprimido SOLO en las llamadas de este módulo), o la ruta de
    OBSIDIAN_CA_CERT si en el futuro se confía en el certificado."""
    return OBSIDIAN_CA_CERT if OBSIDIAN_CA_CERT else False


def _headers(extra: Optional[dict] = None) -> dict:
    h = {"Authorization": f"Bearer {OBSIDIAN_API_KEY}"}
    if extra:
        h.update(extra)
    return h


def _call(method: str, path: str, **kwargs) -> Tuple[Optional[requests.Response], Optional[str]]:
    """Ejecuta una petición HTTP contra el plugin. Devuelve ``(response, None)``
    si hubo respuesta (incluidos 4xx/5xx: el caller decide), o
    ``(None, mensaje_error)`` si Obsidian no está accesible. Nunca lanza una
    excepción de red — así ninguna tool puede dejar colgado el bucle del agente.
    """
    url = f"{OBSIDIAN_BASE_URL}/{path.lstrip('/')}"
    headers = _headers(kwargs.pop("headers", None))
    try:
        with warnings.catch_warnings():
            if not OBSIDIAN_CA_CERT:
                warnings.simplefilter("ignore", InsecureRequestWarning)
            resp = requests.request(
                method, url, headers=headers,
                timeout=_TIMEOUT, verify=_verify_arg(), **kwargs,
            )
        return resp, None
    except requests.exceptions.ConnectionError:
        msg = (
            "Obsidian no está corriendo en pciq22 (o el plugin \"Local REST "
            "API with MCP\" está desactivado) — abre la app y reintenta."
        )
        log.warning("Obsidian inaccesible en %s: connection refused", OBSIDIAN_BASE_URL)
        return None, msg
    except requests.exceptions.Timeout:
        msg = "Obsidian no respondió a tiempo (>5 s) — comprueba la app y reintenta."
        log.warning("Timeout contactando Obsidian en %s", OBSIDIAN_BASE_URL)
        return None, msg
    except requests.exceptions.RequestException as e:
        log.warning("Error de conexión con Obsidian: %s", e)
        return None, f"Error de conexión con Obsidian: {e}"


# ---------------------------------------------------------------------------
# Tools expuestas al modelo
# ---------------------------------------------------------------------------

def leer_nota(ruta: str) -> str:
    """Devuelve el contenido en Markdown de cualquier nota del vault (lectura
    sin restricción de carpeta). ``ruta`` es relativa a la raíz del vault,
    p. ej. ``"20_Trabajo/Proyectos/X.md"``."""
    ruta = (ruta or "").strip().lstrip("/")
    if not ruta:
        return "Ruta vacía: indica la ruta de la nota relativa a la raíz del vault."

    resp, err = _call("GET", f"vault/{_encode_path(ruta)}", headers={"Accept": "text/markdown"})
    if err:
        return err
    if resp.status_code == 404:
        return f"No existe ninguna nota en la ruta {ruta!r}."
    if not resp.ok:
        return f"Error al leer {ruta!r}: HTTP {resp.status_code} — {resp.text[:300]}"
    return resp.text


def buscar_en_vault(query: str, context_length: int = 100) -> str:
    """Búsqueda de texto simple sobre todo el vault. Devuelve una lista de
    rutas con un fragmento de contexto de cada coincidencia."""
    query = (query or "").strip()
    if not query:
        return "Consulta de búsqueda vacía."

    resp, err = _call(
        "POST", "search/simple/",
        params={"query": query, "contextLength": context_length},
    )
    if err:
        return err
    if not resp.ok:
        return f"Error al buscar {query!r}: HTTP {resp.status_code} — {resp.text[:300]}"

    try:
        data = resp.json()
    except ValueError:
        return f"Respuesta inesperada del plugin al buscar {query!r}."

    if not data:
        return f"Sin resultados para: {query!r}"

    lineas = []
    for item in data[:20]:
        filename = item.get("filename", "?")
        score = item.get("score", 0)
        matches = item.get("matches") or []
        snippet = matches[0].get("context", "").strip() if matches else ""
        snippet = " ".join(snippet.split())[:200]
        lineas.append(f"- {filename} (score={score:.2f}): {snippet}")
    return "\n".join(lineas)


def crear_nota_inbox(nombre: str, contenido: str, tags: Optional[List[str]] = None) -> str:
    """Crea ``00_Inbox/{nombre}.md`` con frontmatter de la convención del
    vault (type/titulo/creado/actualizado/estado/tags/fuente). NO sobrescribe:
    si el nombre ya existe, añade un sufijo de timestamp. Solo puede escribir
    dentro de 00_Inbox/ — cualquier intento de escapar de esa carpeta lanza
    ``PermissionError`` (ver ``_validar_ruta_escritura``).

    ``nombre`` debe ser un nombre de fichero simple: si contiene separadores
    de ruta (``/`` o ``\\``) o ``..``, se rechaza explícitamente en vez de
    sanearlo en silencio (evita que un intento de escape quede enmascarado
    como un nombre de fichero inocuo dentro de 00_Inbox/)."""
    nombre_raw = (nombre or "").strip()
    if "/" in nombre_raw or "\\" in nombre_raw or ".." in nombre_raw:
        raise PermissionError(
            f"'nombre' debe ser un nombre de fichero simple, sin rutas (recibido: {nombre_raw!r})"
        )
    nombre_limpio = _sanitizar_nombre(nombre_raw)
    ruta = _validar_ruta_escritura(f"{VAULT_WRITE_ROOT}{nombre_limpio}.md")

    resp, err = _call("GET", f"vault/{_encode_path(ruta)}")
    if err:
        return err
    if resp.status_code == 200:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = _validar_ruta_escritura(f"{VAULT_WRITE_ROOT}{nombre_limpio}_{ts}.md")

    hoy = datetime.now().strftime("%Y-%m-%d")
    tags_final = sorted(set((tags or []) + ["origen-agente"]))
    tags_yaml = "\n".join(f"  - {t}" for t in tags_final)
    frontmatter = (
        "---\n"
        "type: referencia\n"
        f'titulo: "{nombre_limpio}"\n'
        f"creado: {hoy}\n"
        f"actualizado: {hoy}\n"
        "estado: borrador\n"
        f"tags:\n{tags_yaml}\n"
        "fuente: research_agent\n"
        "---\n\n"
    )
    cuerpo = frontmatter + (contenido or "")

    resp, err = _call(
        "PUT", f"vault/{_encode_path(ruta)}",
        data=cuerpo.encode("utf-8"),
        headers={"Content-Type": "text/markdown; charset=utf-8"},
    )
    if err:
        return err
    if not resp.ok:
        return f"Error al crear la nota: HTTP {resp.status_code} — {resp.text[:300]}"
    return f"Nota creada: {ruta}"


def anexar_a_nota_inbox(ruta: str, contenido: str) -> str:
    """Añade ``contenido`` al final de una nota ya existente en 00_Inbox/.
    Solo funciona dentro de 00_Inbox/ — cualquier intento de escapar de esa
    carpeta lanza ``PermissionError`` (ver ``_validar_ruta_escritura``)."""
    ruta_val = _validar_ruta_escritura(ruta)

    resp, err = _call("GET", f"vault/{_encode_path(ruta_val)}")
    if err:
        return err
    if resp.status_code == 404:
        return f"No existe la nota {ruta_val!r} en Inbox. Usa crear_nota_inbox para crearla."
    if not resp.ok:
        return f"Error al comprobar la nota {ruta_val!r}: HTTP {resp.status_code} — {resp.text[:300]}"

    resp, err = _call(
        "POST", f"vault/{_encode_path(ruta_val)}",
        data=("\n" + (contenido or "")).encode("utf-8"),
        headers={"Content-Type": "text/markdown; charset=utf-8"},
    )
    if err:
        return err
    if not resp.ok:
        return f"Error al añadir contenido a {ruta_val!r}: HTTP {resp.status_code} — {resp.text[:300]}"
    return f"Contenido añadido a {ruta_val}"
