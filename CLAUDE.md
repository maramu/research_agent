# research_agent — guía para sesiones de Claude Code

Pipeline de papers científicos: Scopus → PDF → GROBID (TEI) → md_clean/chunks → índice FAISS (bge-m3 vía
Ollama) → RAG y catálogo en Streamlit. Idioma de trabajo: **español**.

## Dónde se trabaja (importante)
- **Producción = pciq22** (`hostname` pciq22.uca.es; Mac mini en la UCA). Allí corren Streamlit (launchd) y los
  jobs, con el repo en `/Users/martinramirez/proyectos/research_agent` y los datos en `/Volumes/research/`.
- **Los cambios de código se hacen en el repo de desarrollo del NAS:** `/Volumes/Disco/proyectos/research_agent`
  (montado también en pciq22). Flujo: editar + tests allí → `git commit` y `git push origin main` desde allí →
  `git pull origin main` en el repo de producción de pciq22. Si trabajas desde pciq22, edita en
  `/Volumes/Disco/...`, no en `/Users/martinramirez/proyectos/research_agent`.
- Tras cambiar código hay que **reiniciar Streamlit en pciq22** (no recarga los módulos de `scripts/` ya importados).
- Los **datos no están en git**: `/Volumes/research/` (`categorias/<cat>/{pdfs,tei,md_clean,chunks,summaries,
  metadata,embeddings,notebooklm_packages,logs}`, `metadatos/`, `quarantine/`, `inbox/`).
- Tests: `python3 -m pytest tests -q` (desde la raíz del repo; no tocan `/Volumes/research`).
- Hook de pre-commit (`.githooks/`, activar con `scripts/install_hooks.sh`): sintaxis + tests rápidos; `SKIP_TESTS=1` para saltarlo.
- Commits: terminar el mensaje con la línea `Co-Authored-By` que indique el entorno.

## Documentación (mantenerla al día en cada cambio)
- `ESTADO.md` — arquitectura y estado por script (una fila por script/página; añadir nota fechada).
- `Mejoras_realizadas.md` — histórico, entrada numerada nueva **arriba** (causa, arreglo, datos tocados).
- `Mejoras_pendientes.md` — backlog; el bloque más reciente "ACTUALIZACIÓN …" fija el orden vivo.
- `docs/` — material de referencia congelado (auditorías, rollouts, copias antiguas); índice en `docs/README.md`.
- `snippets/` — comandos de uso habitual para pegar en terminal/Termius (pciq22 y vigilante de Windows); sin secretos. Mantenerlos al día si cambian rutas, etiquetas de launchd u opciones de scripts.
- Al empezar una sesión: leer `ESTADO.md` y el último bloque de `Mejoras_pendientes.md`; **verificar con
  git/NAS antes de afirmar el estado**.

## Reglas y trampas conocidas
- **Datos destructivos:** borrar/purgar solo si Martín lo pide; antes mirar el objetivo; dejar copia `.bak`
  (convención del proyecto) salvo petición de "sin rastro".
- **`paper_id` ≠ nombre del PDF:** el `paper_id` puede estar truncado respecto al PDF ("Año - Autor - Título
  [doi].pdf"). Emparejar por prefijo ≥60 car. (`utils.pdf_utils.is_processed_stem`), **nunca por DOI**
  (rompería la detección de duplicados).
- **Borrar un paper** (`9_cleanup_duplicates.quarantine_paper`, botón de Artículos): mueve artefactos y log a
  cuarentena y limpia `papers_metadata`, `references.jsonl`, sidecar de validación e informes de `logs/`
  (todo reversible vía manifiesto). El índice FAISS se **poda** (`utils.embeddings.prune_papers_from_index`),
  no se reconstruye. Después regenerar `notebooklm_packages/` (`6_make_packages.py --repack-all` +
  `7_make_master_index.py`; ya lo hace Artículos).
- **Renombrar** (botón de Artículos / `rename_paper`) usa el primer autor de `papers_metadata`: comprobar que no
  sean editores del volumen (caso CET 10.3303) — item 78 del backlog.
- `5_build_embeddings.py`: incremental por defecto (poda papers sin chunks y añade los nuevos); `--force` solo
  si el índice está desalineado. Embeddings por lotes (`/api/embed`) y escritura atómica índice+metadata.
- `1_rename_papers_by_doi.py`: el DOI del nombre del fichero (`[10.x_y]`) tiene prioridad sobre el texto del PDF.
  `process_category()` renombra los PDFs nuevos antes de procesar (flag `--skip-processed` protege los ya procesados).
- Las páginas de Streamlit se prueban poco en pantalla (item 80): decir qué se verificó y qué no.
- Cuello de botella de calidad RAG: el golden (item 37), depende de que Martín etiquete preguntas.
