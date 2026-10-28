# Runbook de recuperación de pciq22 (item 60d)

Objetivo: reconstruir la máquina de producción desde cero. **Nada de esto requiere pánico por el índice:**
los índices FAISS (`categorias/<cat>/embeddings/`) son **regenerables desde `chunks/`**
(`python3 scripts/5_build_embeddings.py --project <cat> --force`), y `chunks/` desde `md_clean/`. Lo
irremplazable son los PDFs, `metadata/papers_metadata.jsonl`, `metadatos/` (p. ej. `doi_manual.xlsx`,
`pendientes_descarga.csv`, `validation_overrides.csv`) y `config/.env`.

1. **Datos.** Montar `/Volumes/research` (copia de seguridad: `research_bk` en el NAS de casa) y, si se
   trabaja el código desde aquí, `/Volumes/Disco`.
2. **Código.** `git clone https://github.com/maramu/research_agent ~/proyectos/research_agent`.
3. **Secretos.** Re-emitir `config/.env` desde el gestor de contraseñas (no está en git ni en el rsync).
4. **Python.** `/opt/homebrew/bin/python3.13 -m venv ~/venvs/rag_papers` y
   `~/venvs/rag_papers/bin/pip install -r requirements-lock.txt` (versiones exactas de producción a
   2026-10-28; `requirements.txt` es la versión no fijada). Si se toca una dependencia, replicar también
   en `.venv/` del repo.
5. **Ollama.** Tarball oficial de GitHub (no Homebrew ni `install.sh`) → `/usr/local/bin/ollama` y
   `/usr/local/lib/ollama/`; recrear `~/Library/LaunchAgents/com.martin.ollama.plist` (ver "Ollama — instalación en
   pciq22" en `ESTADO.md`: `OLLAMA_HOST=127.0.0.1:11435`, `OLLAMA_ORIGINS`, `KeepAlive`) y `ollama pull bge-m3` + `ollama pull qwen2.5:14b-instruct`.
6. **GROBID.** `docker compose -f ~/grobid-compose.yml up -d` (imagen `grobid/grobid:0.9.0-crf`, plataforma
   `linux/arm64`, solo en `127.0.0.1:8070`; ver `ESTADO.md`).
7. **Caddy (acceso remoto con Bearer).** `deployment/Caddyfile.ollama` +
   `deployment/com.research_agent.caddy_ollama.plist`; ver `deployment/README.md`.
8. **Servicios.** Copiar los plist de `deployment/` a `~/Library/LaunchAgents/` y cargarlos:
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<plist>` (streamlit, streamlit_public,
   scopus_weekly, daily_question).
9. **Servidor 24/7.** `sudo pmset -c sleep 0 disksleep 0 displaysleep 0 hibernatemode 0 womp 1 autorestart 1`.
10. **Comprobar.** `curl -s http://127.0.0.1:11435/api/version`, `curl -s http://127.0.0.1:8070/api/isalive`,
    abrir `http://<ip>:8501`, y `python3 -m pytest tests -q` desde la raíz del repo.
11. **Reindexar si hace falta.** Para cada categoría: `python3 scripts/5_build_embeddings.py --project <cat> --force`
    y después regenerar `notebooklm_packages/` (`6_make_packages.py --repack-all` + `7_make_master_index.py`).

> **Pendiente (item 60b):** versionar `~/grobid-compose.yml` y `~/Library/LaunchAgents/com.martin.ollama.plist`
> en `deployment/`. Se revisaron el 2026-10-28 y no contienen secretos, pero la copia automática desde el
> directorio personal fue bloqueada por el clasificador de permisos; hacerla a mano:
> `cp ~/grobid-compose.yml ~/Library/LaunchAgents/com.martin.ollama.plist /Volumes/Disco/proyectos/research_agent/deployment/`.
