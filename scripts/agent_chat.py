#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_chat.py — Chat de terminal con tool-calling contra Ollama (qwen3:14b)

Agente conversacional que puede leer todo el vault de Obsidian y crear/anexar
notas SOLO dentro de 00_Inbox/ (garantía a nivel de código en
tools/obsidian.py::_validar_ruta_escritura — el system prompt de este script
es un refuerzo, no la garantía).

Flujo independiente del pipeline de RAG/embeddings del proyecto: no toca
FAISS ni scripts/8_query_rag.py. Para contexto usa únicamente las tools de
lectura de Obsidian (leer_nota, buscar_en_vault).

Uso:
    python3 scripts/agent_chat.py
    python3 scripts/agent_chat.py --model qwen3:14b --host http://127.0.0.1:11435
    python3 scripts/agent_chat.py --no-confirm   # sin confirmación humana (pruebas)

Dentro del chat:
    /salir            — termina la sesión (o Ctrl-D)
    /multi            — inicia un mensaje multilínea, termina con /fin
    /nuevo            — borra el historial de la conversación actual
    /model <nombre>   — cambia el modelo activo a partir del siguiente turno
                        (no borra el historial); p. ej. /model qwen3:14b
    /model            — muestra el modelo activo actual, sin cambiarlo

Variables de entorno:
    config/.env             OLLAMA_HOST (por defecto http://127.0.0.1:11435)
    config/.env.obsidian     OBSIDIAN_API_KEY (la carga tools/obsidian.py)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import ollama
from dotenv import load_dotenv

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPTS_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.obsidian import (  # noqa: E402
    anexar_a_nota_inbox,
    buscar_en_vault,
    crear_nota_inbox,
    leer_nota,
)

# ── Config general (config/.env) — solo para OLLAMA_HOST; la key de Obsidian
# la carga tools/obsidian.py desde config/.env.obsidian, aislada. ───────────
_ENV_FILE = ROOT_DIR / "config" / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

log = logging.getLogger("agent_chat")

DEFAULT_HOST = "http://127.0.0.1:11435"
DEFAULT_MODEL = "qwen3:8b"
MAX_TOOL_ITERS_POR_TURNO = 8
CHAT_TIMEOUT = 600  # segundos — qwen3:14b en este hardware es lento (turnos con tool-calling
# y contexto largo pueden superar los 5 min); mejor esperar de más que cortar una respuesta válida

DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _dim(texto: str) -> str:
    return f"{DIM}{texto}{RESET}"


# ---------------------------------------------------------------------------
# Registro de tools — formato ollama.chat(tools=[...])
# ---------------------------------------------------------------------------

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "leer_nota",
            "description": (
                "Devuelve el contenido en Markdown de una nota del vault de Obsidian. "
                "Lectura SIN restricción de carpeta: puede leer cualquier nota del vault, "
                "no solo las de 00_Inbox."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {
                        "type": "string",
                        "description": (
                            "Ruta de la nota relativa a la raíz del vault, "
                            "p. ej. '20_Trabajo/Proyectos/X.md'."
                        ),
                    },
                },
                "required": ["ruta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_vault",
            "description": (
                "Busca un texto en todas las notas del vault de Obsidian (todas las "
                "carpetas, sin restricción) y devuelve las rutas coincidentes con un "
                "fragmento de contexto de cada una."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto a buscar."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_nota_inbox",
            "description": (
                "Crea una nota NUEVA con el frontmatter estándar del vault (type, "
                "titulo, creado, actualizado, estado, tags, fuente). SOLO puede escribir "
                "dentro de 00_Inbox/ — cualquier otra carpeta es imposible a nivel de "
                "código, no lo intentes con otra ruta. No sobrescribe: si el nombre ya "
                "existe, se añade un sufijo de fecha/hora."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": (
                            "Nombre de fichero simple, sin carpetas y sin extensión "
                            "(la extensión .md se añade automáticamente)."
                        ),
                    },
                    "contenido": {
                        "type": "string",
                        "description": "Cuerpo de la nota en Markdown, sin frontmatter.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags adicionales (se añade siempre 'origen-agente').",
                    },
                },
                "required": ["nombre", "contenido"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "anexar_a_nota_inbox",
            "description": (
                "Añade contenido al final de una nota que YA EXISTE dentro de 00_Inbox/. "
                "SOLO puede escribir dentro de 00_Inbox/ — cualquier otra carpeta es "
                "imposible a nivel de código, no lo intentes con otra ruta. No crea la "
                "nota si no existe (usa crear_nota_inbox para eso)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {
                        "type": "string",
                        "description": "Ruta de la nota dentro de 00_Inbox/, p. ej. '00_Inbox/mi_nota.md'.",
                    },
                    "contenido": {
                        "type": "string",
                        "description": "Texto a añadir al final de la nota.",
                    },
                },
                "required": ["ruta", "contenido"],
            },
        },
    },
]

TOOL_FUNCS = {
    "leer_nota": leer_nota,
    "buscar_en_vault": buscar_en_vault,
    "crear_nota_inbox": crear_nota_inbox,
    "anexar_a_nota_inbox": anexar_a_nota_inbox,
}

# Tools de escritura: pasan por confirmación humana antes de ejecutarse.
WRITE_TOOLS = {"crear_nota_inbox", "anexar_a_nota_inbox"}

SYSTEM_PROMPT = """Eres un asistente que ayuda a consultar y organizar el vault de Obsidian del usuario.

Puedes:
- Leer cualquier nota del vault y buscar texto en todo el vault (tools leer_nota, buscar_en_vault).
- Crear notas nuevas o añadir contenido a notas existentes, pero SOLO dentro de la carpeta 00_Inbox/ (tools crear_nota_inbox, anexar_a_nota_inbox).

Convención de frontmatter del vault (las tools de escritura la aplican automáticamente):
type, titulo, creado, actualizado, estado, tags, fuente.

Puedes leer todo el vault, pero solo puedes crear o modificar notas dentro de 00_Inbox. No puedes borrar ni mover archivos.

Si te piden borrar una nota, moverla, o escribir fuera de 00_Inbox, explica que no tienes esa capacidad — no existen tools para ello, así que no lo intentes forzando una ruta distinta con crear_nota_inbox o anexar_a_nota_inbox.

Responde siempre en español, de forma clara y concisa."""


# ---------------------------------------------------------------------------
# Vista previa + confirmación humana de las tools de escritura
# ---------------------------------------------------------------------------

def _vista_previa_crear_nota(args: Dict[str, Any]) -> str:
    nombre = str(args.get("nombre", ""))
    contenido = str(args.get("contenido", ""))
    tags = args.get("tags") or []
    hoy = datetime.now().strftime("%Y-%m-%d")
    tags_final = sorted(set(list(tags) + ["origen-agente"]))
    tags_yaml = "\n".join(f"  - {t}" for t in tags_final)
    frontmatter = (
        "---\n"
        "type: referencia\n"
        f'titulo: "{nombre}"\n'
        f"creado: {hoy}\n"
        f"actualizado: {hoy}\n"
        "estado: borrador\n"
        f"tags:\n{tags_yaml}\n"
        "fuente: research_agent\n"
        "---"
    )
    return (
        f"CREAR NOTA en 00_Inbox/{nombre}.md\n"
        "(si ya existe una nota con ese nombre, se creará con sufijo de fecha/hora)\n\n"
        f"{frontmatter}\n\n{contenido}"
    )


def _vista_previa_anexar_nota(args: Dict[str, Any]) -> str:
    ruta = str(args.get("ruta", ""))
    contenido = str(args.get("contenido", ""))
    return f"AÑADIR AL FINAL de {ruta}\n\n{contenido}"


def confirmar_escritura(nombre_tool: str, args: Dict[str, Any]) -> bool:
    """Muestra la nota/contenido exactos que se van a escribir y pide
    confirmación [s/N] antes de tocar el vault."""
    preview = (
        _vista_previa_crear_nota(args)
        if nombre_tool == "crear_nota_inbox"
        else _vista_previa_anexar_nota(args)
    )
    linea = "─" * 70
    print(f"\n{linea}")
    print(f"{BOLD}🖊  El agente quiere escribir en el vault:{RESET}")
    print(linea)
    print(preview)
    print(linea)
    try:
        resp = input("¿Confirmas esta escritura? [s/N]: ").strip().lower()
    except EOFError:
        resp = "n"
    return resp in ("s", "si", "sí", "y", "yes")


# ---------------------------------------------------------------------------
# Ejecución de tools
# ---------------------------------------------------------------------------

def ejecutar_tool(nombre_tool: str, args: Dict[str, Any], auto_confirm: bool) -> str:
    print(_dim(f"  ↳ tool: {nombre_tool}({args})"))

    if nombre_tool not in TOOL_FUNCS:
        return f"Tool desconocida: {nombre_tool!r}"

    if nombre_tool in WRITE_TOOLS and not auto_confirm:
        if not confirmar_escritura(nombre_tool, args):
            print(_dim("  ↳ escritura rechazada por el usuario"))
            return "El usuario rechazó la escritura. No se ha modificado el vault."

    fn = TOOL_FUNCS[nombre_tool]
    try:
        resultado = fn(**args)
    except PermissionError as e:
        log.warning("PermissionError en tool %s: %s", nombre_tool, e)
        resultado = f"PermissionError: {e}"
    except TypeError as e:
        resultado = f"Argumentos inválidos para {nombre_tool}: {e}"

    print(_dim(f"  ↳ resultado: {resultado[:200]}"))
    return resultado


# ---------------------------------------------------------------------------
# Entrada de usuario — multilínea razonable
# ---------------------------------------------------------------------------

def leer_entrada_usuario() -> Optional[str]:
    """Lee un mensaje del usuario. Una línea normal se envía al pulsar Enter.
    '/multi' inicia un mensaje de varias líneas, terminado con '/fin' en su
    propia línea. '/salir' o Ctrl-D terminan la sesión (devuelve None)."""
    try:
        primera = input(f"\n{BOLD}Tú>{RESET} ")
    except EOFError:
        print()
        return None

    if primera.strip() in ("/salir", "/exit", "/quit"):
        return None

    if primera.strip() == "/multi":
        print(_dim("  (modo multilínea — termina con /fin en una línea sola)"))
        lineas: List[str] = []
        while True:
            try:
                linea = input()
            except EOFError:
                print()
                break
            if linea.strip() == "/fin":
                break
            lineas.append(linea)
        return "\n".join(lineas)

    return primera


# ---------------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------------

def chat_loop(client: ollama.Client, model: str, auto_confirm: bool) -> None:
    historia: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    model_activo = model

    print(
        f"Agente listo (modelo {model_activo}). /salir para terminar, /multi para varias líneas, "
        "/nuevo para reiniciar, /model para cambiar de modelo."
    )

    while True:
        mensaje = leer_entrada_usuario()
        if mensaje is None:
            print("Hasta luego.")
            return

        mensaje = mensaje.strip()
        if not mensaje:
            continue
        if mensaje == "/nuevo":
            historia = [{"role": "system", "content": SYSTEM_PROMPT}]
            print(_dim("  (historial reiniciado)"))
            continue
        if mensaje == "/model" or mensaje.startswith("/model "):
            nuevo_modelo = mensaje[len("/model"):].strip()
            if nuevo_modelo:
                model_activo = nuevo_modelo
            print(_dim(f"  (modelo activo: {model_activo})"))
            continue

        historia.append({"role": "user", "content": mensaje})

        iteraciones = 0
        while True:
            try:
                resp = client.chat(model=model_activo, messages=historia, tools=TOOLS_SCHEMA, think=False)
            except Exception as e:
                print(f"\n[error] No se pudo contactar con Ollama ({model_activo} en el host configurado): {e}")
                historia.pop()  # no dejar el turno del usuario sin respuesta en el historial
                break

            msg = resp["message"]
            historia.append(msg)

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                print(f"\n{BOLD}Agente>{RESET} {msg.get('content') or ''}")
                break

            iteraciones += 1
            if iteraciones > MAX_TOOL_ITERS_POR_TURNO:
                aviso = (
                    f"Límite de {MAX_TOOL_ITERS_POR_TURNO} llamadas a tools alcanzado "
                    "en este turno; se detiene para evitar un bucle infinito."
                )
                print(f"\n[aviso] {aviso}")
                historia.append({
                    "role": "tool",
                    "tool_name": tool_calls[0]["function"]["name"],
                    "content": aviso,
                })
                break

            for tc in tool_calls:
                nombre_tool = tc["function"]["name"]
                args = dict(tc["function"]["arguments"])
                resultado = ejecutar_tool(nombre_tool, args, auto_confirm)
                historia.append({
                    "role": "tool",
                    "tool_name": nombre_tool,
                    "content": resultado,
                })


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat con tool-calling sobre el vault de Obsidian")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Modelo Ollama (por defecto {DEFAULT_MODEL})")
    parser.add_argument("--host", default=None, help="Host de Ollama (por defecto OLLAMA_HOST del .env)")
    parser.add_argument(
        "--yes", "--no-confirm", dest="auto_confirm", action="store_true",
        help="No pedir confirmación antes de escribir en el vault (solo para pruebas)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    host = args.host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)
    client = ollama.Client(host=host, timeout=CHAT_TIMEOUT)

    if args.auto_confirm:
        print(_dim("  (--no-confirm activo: las escrituras en el vault NO pedirán confirmación)"))

    try:
        chat_loop(client, args.model, args.auto_confirm)
    except KeyboardInterrupt:
        print("\nInterrumpido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
