# Auditoría técnica externa — research_agent

> **Procedencia.** Revisión generada por un modelo frontera externo (**Kimi K2**, familia K2.x, vía OpenRouter en VS Code / Continue en modo Chat), **2026-07-20**.
> **Base documental declarada por el revisor:** `ESTADO.md`, `Mejoras_pendientes.md`, `Mejoras_realizadas.md` + código de `pipeline.py`, `run_pipeline.py`, `run_eval.py`, `pool_candidates.py`, `run_rag_batch.py`, `run_weekly_scopus.py`, `8_query_rag.py`, `5_build_embeddings.py`, `utils/retrieval.py`, `utils/embeddings.py`, `utils/download_registry.py`, `utils/attachments.py`, `utils/constants.py`, `streamlit_app/rag_core.py`, `streamlit_app/pages/2_RAG.py`. No vistos por el revisor: `app_utils.py`, `utils/citations.py`, `utils/export_refs.py`, `3_process_corpus.py`, `3a_download_pdfs.py`, `2_screen_pdfs.py`, `books/*`, tests.
> **Naturaleza.** La mayoría de los hallazgos son inferencias de lectura de código. Los que en el backlog aparecen como **VERIFICAR (pciq22)** requieren confirmación en la máquina de ejecución antes de aplicar el fix. Documento **inmutable de referencia** — las acciones derivadas viven en `Mejoras_pendientes.md` (items **52–61** y anotaciones fechadas en items **27, 28, 30, 31, 33, 37, 39**).
> **Entrada al backlog:** ver `Mejoras_pendientes.md` → sección "Orden de prioridad (revisión 2026-07-20 — auditoría externa Kimi K2)".

---

# Auditoría técnica `research_agent` — versión final (2026-07-20)

**Base documental:** ESTADO.md, Mejoras_pendientes.md, Mejoras_realizadas.md + código de: `pipeline.py`, `run_pipeline.py`, `run_eval.py`, `pool_candidates.py`, `run_rag_batch.py`, `run_weekly_scopus.py`, `8_query_rag.py`, `5_build_embeddings.py`, `utils/retrieval.py`, `utils/embeddings.py`, `utils/download_registry.py`, `utils/attachments.py`, `utils/constants.py`, `streamlit_app/rag_core.py`, `streamlit_app/pages/2_RAG.py`. No he visto: `app_utils.py`, `utils/citations.py`, `utils/export_refs.py`, `3_process_corpus.py`, `3a_download_pdfs.py`, `2_screen_pdfs.py`, `books/*`, tests.

**Corrección a mi primera versión, en honestidad:** retiro el hallazgo "RRF k=60 sobre pools de 8+8" — `pool_size` devuelve `max(k*10, 200)`, pools de 200 por brazo, régimen para el que RRF k=60 es defendible. El problema del híbrido no es la fusión: es el tokenizer. Lo señalo explícitamente porque una auditoría que no corrige sus errores no es de fiar.

**Veredicto global:** el proyecto está mejor construido que la media de pipelines de investigación, con una disciplina documental y de reversibilidad ejemplar. Pero hay un hallazgo que considero **P0 funcional** (síntesis con contexto truncado en silencio, confirmado en las dos rutas de síntesis), y otro P0-adherido: la comparación denso-vs-híbrido que sustenta una decisión de arquitectura se hizo con un BM25 incapaz de ver los términos donde BM25 aporta.

---

## 1. Arquitectura y separación de responsabilidades

### P0 — La síntesis trunca el contexto en silencio en las DOS rutas de síntesis (app + batería)
- **Qué (confirmado en código):** `rag_core.py::stream_ollama` llama `client.generate(model=model, prompt=ollama_prompt, stream=True)` **sin `options`**: ni `num_ctx` ni `temperature`. `run_rag_batch.py::synthesize` llama `client.generate(...)` igualmente sin `options`. En Ollama 0.30.x, sin `num_ctx` explícito el contexto efectivo es **4096 tokens** (el default del servidor). El contexto típico: system (~250 tok) + 8 chunks × hasta 8000 chars (~hasta 2000 tok c/u, media quizá 300–500) + pregunta ≈ **3.000–17.000 tokens**. Cuando supera 4096, Ollama descarta los tokens más antiguos del prompt **sin error ni aviso**: la respuesta se genera sin parte de los fragmentos y sin el system prompt.
- **Por qué importa:** No es teórico. Con top_k=8 y chunks de ~1500 chars ya estáis en ~3.500–4.500 tokens — el truncado dispara **en consultas normales**, no en casos extremos. La respuesta se sintetiza sin los fragmentos [1]-[5] y sin las reglas de cita, pero `apply_citations` post-procesa las claves [N] que sí menciona → el resultado **parece** una respuesta RAG correcta con citas. Es la forma más perversa de degradación: invisible. Todo el valor científico del sistema (dimensión 3) descansa sobre este punto. Además: temperatura sin fijar (default 0.8 en Ollama) para síntesis con citas — inaceptable para producción.
- **Recomendación (hoy, 30 minutos):** en `rag_core.py::stream_ollama` y `run_rag_batch.py::synthesize`, pasar `options={"num_ctx": 16384, "temperature": 0.0}` (qwen2.5:14b aguanta 32k; 16k deja margen y es barato en M4). Verificación inmediata: `ollama ps` durante una consulta (columna CONTEXT) o log del prompt recibido. Documentar ambos valores en ESTADO.md junto a los modelos. Si queréis confirmar el daño histórico: comparad `usage_capture["input_tokens"]` estimado (chars//4) contra 4096 en los `rag_usage_*.jsonl` — todo lo que supere ~4000 tokens estimados fue truncado.

### P1 — `scopus_weekly`: LaunchAgent frágil + plist de las 04:00 sin aplicar + "timeout" que no termina el proceso
- **Qué (confirmado):** Tres grietas apiladas en la función central del sistema. (1) Sigue siendo LaunchAgent con `WakeOnLaunchDate` inerte — el mismo defecto que causó los fallos del 16 y 18 de julio en `daily_question`, diagnosticados por vosotros. (2) El plist con la hora 04:00 lleva un mes commiteado sin aplicar en pciq22. (3) En `run_weekly_scopus.py`: `ThreadPoolExecutor` + `future.result(timeout=5400)` + `executor.shutdown(wait=False)` — los threads del executor no son daemon, así que tras el "timeout" el email sale pero **el proceso no termina** hasta que `run_scopus` acabe de verdad (potencialmente horas, launchd viendo el job vivo, Ollama ocupado). El mensaje *"El subproceso sigue en background"* miente: es un thread, no un subproceso. Y `pdf_after` se cuenta en el momento del timeout mientras el thread sigue descargando → números del email incoherentes con el estado final.
- **Por qué importa:** Si el Mac se reinicia un viernes y nadie abre sesión gráfica antes del lunes 06:00, la ingesta se pierde en silencio — el patrón exacto que ya os pasó dos veces. Y el "timeout" da una falsa sensación de cota de duración que no existe.
- **Recomendación:** (a) Aplicar el plist hoy (5 min). (b) Migrar a LaunchDaemon con el patrón ya probado (`UserName` + `HOME`), verificando SMTP en frío como hicisteis con `claude`. (c) Sustituir el thread por `subprocess.Popen(["python3", "run_pipeline.py", "scopus", ...], start_new_session=True)` + `wait(timeout=5400)` + `os.killpg(os.getpgid(p.pid), SIGKILL)` al expirar — kill real del árbol de procesos, no espera infinita. Es ~30 líneas y convierte el timeout en verdadero.

### P1 — Infraestructura crítica no versionada: compose de GROBID y plist de Ollama
- **Qué:** `~/grobid-compose.yml` (bind a `127.0.0.1:8070:8070`, fruto del trabajo de securización) y `~/Library/LaunchAgents/com.martin.ollama.plist` (`OLLAMA_HOST`, `OLLAMA_ORIGINS`, `OLLAMA_KEEP_ALIVE`) viven solo en pciq22. El Caddyfile y los plists de Streamlit/Caddy sí están en `deployment/`.
- **Por qué importa:** Si el disco de pciq22 muere, esa configuración se pierde y la reconstrucción depende de la memoria. Asimetría sin justificación.
- **Recomendación:** Copiar ambos a `deployment/` (sin secretos — no los llevan) + una línea en `deployment/README.md`. No requiere tocar producción.

### P1 — Dos venvs con sincronización manual y sin lockfile
- **Qué:** `~/venvs/rag_papers` (producción, LaunchAgents) y `.venv/` del repo, regla manual "replica en el otro". No hay `requirements` pinneado del venv de producción. La regla ya falló una vez (`.venv` apuntando a un Python 3.14 desinstalado).
- **Recomendación:** `pip freeze > requirements-lock.txt` desde `rag_papers` en pciq22, versionado. Añadir a `corpus_manifest.py` (o al health check de portada) un aviso si los dos venvs divergen. Considerar `python@3.13` con auto-upgrade desactivado — Homebrew ya os movió el intérprete bajo los pies una vez.

### P2 — Leak de FileHandlers en el proceso Streamlit (confirmado en `pipeline.py::_setup_pipeline_log`)
- **Qué:** Cada `run_scopus`/`run_inbox_*` hace `log.addHandler(fh)` sin removerlo. Como Streamlit importa `pipeline` in-process y vive semanas arriba: cada ingesta web añade un handler permanente → la ejecución N escribe también en los ficheros de log de las N−1 anteriores (logs cruzados) + leak de file descriptors. `run_weekly_scopus.py` sí tiene guard (`if not log.handlers`); `pipeline.py` no.
- **Recomendación:** try/finally con `log.removeHandler(fh)` al final de cada flujo, o un `_setup_pipeline_log` idempotente con guard. 15 minutos.

### P2 — `pipeline.py::run_step` sin timeout (confirmado)
- **Qué:** Lectura bloqueante de `process.stdout` línea a línea sin timeout ni watchdog. Un hijo colgado sin salida (GROBID muerto a mitad de PDF, cuelgue de red) deja el pipeline bloqueado indefinidamente. La única cota es el (falso) timeout del wrapper semanal.
- **Recomendación:** Añadir watchdog por inactividad (p.ej. `selectors`/thread lector con timeout de N min sin línea nueva → `process.kill()`), con valor generoso (GROBID warm-up es lento). Al menos en los pasos de red (`0_scopus_api`, `3a_download`, `3_process`).

### P2 — `integrate_adhoc` pasa `--force` a `5_build_embeddings.py`: vestigio obsoleto
- **Qué (confirmado):** El `--force` data del 2026-05-27, anterior al indexado incremental (2026-06-04). Hoy re-indexa **toda** la categoría tras cada integración aunque solo entren 2 papers.
- **Recomendación:** Quitar el `--force` de `integrate_adhoc` (el incremental por `paper_id` ya cubre los nuevos). Mantenerlo solo como opción manual.

### P2 — Resto de P2 de arquitectura (ya cubiertos en la v1, sigo suscribiéndolos)
- Ejecución síncrona en `13_RAG_multiple.py` (muere al cerrar pestaña): reutilizar el patrón detached+log de `1_Ingestar.py`. ESTADO.md con contradicción ("Streamlit corre en el Mac mini de casa" vs "ya no ejecuta") y Hermes ocupando ~30% → extraer a HERMES.md. Dos Caddy/documentar el runbook mínimo de recuperación.

---

## 2. Metodología de recuperación/RAG y evaluación

### P0-adherido — La comparación denso-vs-híbrido se hizo con un BM25 que no ve los términos donde BM25 aporta (confirmado en `retrieval.py::tokenize`)
- **Qué (confirmado):** `tokenize(text) = re.findall(r"[a-z0-9]+", text.lower())`. Consecuencias verificables: `NR-SOB` → `["nr", "sob"]` (destruido); `Fe(II)`, `S-SO4 2-`, cargas, paréntesis → destruidos; letras griegas (α, β, μ) eliminadas; tildes parten palabras españolas (`desulfurización` → `desulfurizaci` + `n`). Sobreviven `H2S`→`h2s` y `TiO2`→`tio2`. Además el mismo problema existe en el **texto indexado** (BM25 se construye sobre `text` con el mismo tokenizer).
- **Por qué importa:** El caso de uso teórico del híbrido es cobertura en queries de acrónimo/sigla/fórmula/especie química — exactamente lo que este tokenizer destruye en ambos lados (query e índice). La conclusión "dense gana consistentemente" (anoxic 0.50→0.25, biogas 0.889→0.857) se obtuvo con un BM25 lisiado. Es una decisión de arquitectura (híbrido OFF por defecto) tomada sobre un instrumento mal calibrado. La decisión operativa puede ser correcta por parsimonia; la evidencia no la sostiene.
- **Recomendación (secuenciada, antes de cualquier otra cosa de esta dimensión):** (1) Arreglar `tokenize`: preservar tokens alfanuméricos con guiones internos (`[a-z0-9]+(?:-[a-z0-9]+)*`), letras griegas y tildes (usar `utils/pdf_utils.strip_accents`, que ya existe, o normalizar NFKD). Añadir tests con H2S, TiO2, NR-SOB, Fe(II), kLa. (2) Re-correr la eval existente (denso vs híbrido, mismas preguntas) — 10 minutos — para ver si la conclusión cambia. (3) Solo entonces decidir si el híbrido merece más inversión (fusión ponderada, rerank). El tokenizer es la raíz; todo lo demás es consecuencia.

### P1 — El índice es L2 sin normalización explícita: la similitud podría no ser coseno (confirmado; falta un dato de 3 líneas)
- **Qué (confirmado):** `5_build_embeddings.py` usa `faiss.IndexFlatL2(dim)` y ni `utils/embeddings.py` ni `5_build_embeddings.py` llaman a `faiss.normalize_L2`. `attachments.py` incluso lo documenta: *"NO normaliza: el índice del corpus usa IndexFlatL2 sobre vectores crudos"*.
- **Por qué importa:** Si Ollama devuelve los embeddings de bge-m3 ya normalizados (probable pero no garantizado — depende de la versión y del servidor), L2 equivale a coseno y no pasa nada. Si no, la similitud no es coseno y penaliza chunks por norma. **Todo el corpus indexado hereda esta decisión.**
- **Recomendación:** Verificar en 3 líneas contra el Ollama de producción: embebe cualquier texto y calcula `np.linalg.norm(v)`. Si ‖v‖≈1.0 → documentar "Ollama normaliza, L2≈coseno" y cerrar. Si no → normalizar incondicionalmente en `embed_texts` (idempotente si ya vienen normalizados, convierte el comportamiento en explícito) y re-indexar. Es la decisión correcta en ambos casos: no depender del comportamiento implícito del servidor.

### P1 — Invariante metadata.jsonl ↔ index.faiss sin protección (tolerancia silenciosa)
- **Qué (confirmado en `run_eval.py`, `pool_candidates.py`, `run_rag_batch.py`, `8_query_rag.py`, `2_RAG.py`):** BM25 se construye sobre los textos de `metadata.jsonl` asumiendo orden == vectores. Si se desalinean (append incremental interrumpido, reescritura), todos los `retrieve` hacen `if idx >= len(meta): continue` — **toleran en silencio** una desalineación parcial. Ninguno comprueba `index.ntotal == len(meta)`.
- **Recomendación:** Añadir `assert index.ntotal == len(meta), f"desalineado: {index.ntotal} vs {len(meta)}"` al cargar en los 5 puntos (mejor: en un loader compartido, ver dimensión 4). Y en `5_build_embeddings.py`, escribir `indexed_papers.json` **antes** de `write_index` (hoy es lo último: un kill entre ambos deja vectores sin registrar → duplicados en el siguiente run).

### P1 — Preguntas con 0 relevantes entran al golden y deprimen las métricas artificialmente (confirmado)
- **Qué (confirmado):** `pool_candidates.py::cmd_build` escribe la pregunta al golden aunque tenga `relevant_paper_ids: []` (solo imprime "⚠️ SIN RELEVANTES"). En `run_eval.py::eval_question`, una pregunta sin relevantes da `hit=0` y `rr=0` **siempre** — cuenta como fallo garantizado e infla el fracaso aparente del retriever.
- **Recomendación:** `cmd_build` debe abortar si alguna pregunta tiene 0 relevantes (mismo patrón que el guard anti-guion que ya tiene), o `run_eval` debe excluirlas con aviso. No escribir al golden preguntas sin relevantes.

### P1 — La decisión "denso gana" sigue sin soporte estadístico (y el harness no reporta incertidumbre)
- **Qué (confirmado en `run_eval.py`):** n=4 y n=6. El IC de Wilson para Hit@8=0.50 con n=4 es [0.0, 1.0] — no discrimina. La diferencia anoxic (0.50 vs 0.25) es **una pregunta**; la de biogas en MRR es ruido de una posición. `run_eval.py` no reporta ningún intervalo ni test.
- **Recomendación:** (a) Reformular en los docs: "sin evidencia de beneficio del híbrido a n=10; OFF por parsimonia", no "dense gana". (b) En `run_eval.py`: IC de Wilson para Hit@k, bootstrap por pregunta para MRR, y test de **McNemar** (emparejado) para denso-vs-híbrido — es el test correcto para dos sistemas sobre el mismo golden. ~40 líneas. (c) Con ~25 preguntas solo detectáis efectos groseros (IC ±16 puntos): aceptadlo explícitamente.

### P1 — El híbrido se evalúa con la métrica equivocada (global, no en su nicho)
- **Qué:** Hit@8/MRR agregado global. Si el híbrido gana 2 preguntas de acrónimos y empata el resto, el agregado lo diluye hasta la invisibilidad con n=10. Vuestra propia verificación A/B con NR-SOB mostró que el híbrido subía matches léxicos que el denso no traía.
- **Recomendación:** Campo obligatorio `"archetype": "acronym|conceptual|numeric|multihop"` en el golden; `run_eval.py` reporta métricas **por arquetipo** además del global. Decisión del híbrido: mirar solo el subconjunto acronym/numeric. Y añadir un diagnóstico gratuito: **overlap Jaccard entre top-k denso y top-k BM25 por pregunta** — si es ~1, el híbrido no puede aportar y la fusión es decorativa; si es bajo y aun así no gana, entonces sí cerráis el híbrido con datos.

### P1 — Métricas insuficientes: falta cobertura (Recall@k) y pureza (Precision@k)
- **Qué:** Anoxic tiene ~4 relevantes/pregunta. Hit@8 mide si cayó *alguno*; MRR, la posición del primero. Ninguna mide cuántos relevantes se recuperan ni cuánto ruido entra al contexto del LLM (precisión = menos citas espurias).
- **Recomendación:** Añadir Recall@k, Precision@k y, si queréis una métrica de ranking con juicios binarios, MAP. Trivial con los datos que ya tenéis. Para la decisión de reranking, las métricas relevantes serán Precision@3-5 y MRR.

### P1 — Sin control de deriva del corpus entre evaluaciones (confirmado)
- **Qué (confirmado):** El CSV de `run_eval.py` tiene fieldnames fijos: sin `ntotal`, sin git commit, sin hash del golden, sin fecha del último paper. Dos runs separados por una ingesta pueden diferir por el corpus, no por el sistema.
- **Recomendación:** Escribir en el CSV/encabezado: `index.ntotal`, max `processed_date`, git commit, hash del golden. `corpus_manifest.py` ya genera casi todo — consumidlo.

### P1 — Reranking planeado sobre una vía inexistente (Ollama no sirve rerankers)
- Confirmo lo que sospechabais: `bge-reranker-v2-m3` no está disponible en Ollama. Opciones realistas en vuestro hardware: (a) `sentence-transformers` + CrossEncoder `bge-reranker-v2-m3` en el venv (añade torch; reranquear top-20 <1s en M4); (b) LLM-as-reranker pointwise con qwen2.5 (cero dependencias, offline, suficiente para evaluar si el rerank ayuda). Consejo: (b) para la evaluación inicial, (a) si justifica producción. Ninguna viola la restricción de Ollama 0.30.7.

### P2 — Sesgo de pooling: bien gestionado, falta cerrar el protocolo
- `pool_candidates.py` construye desde los retrievers evaluados (pooling TREC estándar, aceptable **para comparar esos sistemas entre sí**). Falta: (a) `PROTOCOLO.md` registrando qué retriever/versión generó cada pool; (b) que el experto pueda añadir relevantes de memoria fuera del pool (campo `source: pool|expert`) — son los más valiosos; (c) regla de re-pool al introducir un método nuevo (reranker); (d) versionar los golden en git (son artefactos de investigación y hoy viven solo en el NAS). El Hit@8=1.0 de biogas es casi seguro artefacto de pooling (el experto solo vio lo que el sistema ya recuperaba) — no comparable con anoxic (anotado sin pooling), cosa que ya documentáis bien.

### P2 — Truncado reactivo de embeddings sin auditoría + divergencia vector↔texto
- `embed_texts` trunca al 2/3 solo con `print`, sin flag persistido. El `text` de metadata queda completo (lo que ve BM25/LLM/usuario) pero el vector representa ~66% del chunk. Añadir `embed_truncated: true` (+ longitud original) a `metadata.jsonl` cuando actúa. Si afecta a <1% de chunks, cerrar; si es sistemático en categorías con fórmulas, re-trocear esos papers con `MAX_EMBED_CHARS` menor en vez de truncar.

### P2 — Indexado incremental por `paper_id` frágil ante re-troceos parciales
- `indexed_papers.json` decide por `paper_id`; un paper re-troceado con el mismo id no se re-embebe salvo `--force` global. El pipeline de libros lo hace mejor (hash + borrado). Alinear `5_build_embeddings.py` con ese patrón, o documentar la invariante "re-troceo ⇒ siempre `--force`".

### P2 — 38.5% de `section_canonical="other"` limita el filtro por sección
- Medir antes de promocionar el filtro: muestrear 50 chunks `other` y estimar cuántos son methods/results no-IMRaD. Si es alto, afinar `_CANON_PATTERNS` con los títulos reales más frecuentes del `other`.

### P2 — Evaluación de síntesis: inexistente, con el material a medio hacer
- El golden de anoxic ya incluye `answer` del experto, sin usar. Cuando llegue a ~25: (a) faithfulness determinista gratis (todo [N] citado existe entre los chunks enviados — hacerlo ya en `synthesize_answer` y marcar citas huérfanas en la UI); (b) juicio del experto sobre 5 respuestas/categoría contra su `answer` (rúbrica de 3 puntos). No montéis LLM-juez todavía: el juicio manual es más barato y fiable a vuestro volumen.

---

## 3. Fiabilidad científica de la síntesis

**Respuesta directa:** con provenance por chunk, export de chunks citables y log completo, el sistema es defendible **como herramienta de descubrimiento y primer borrador con verificación humana**. No es defendible hoy como fuente citable sin verificación, y el P0 de la dimensión 1 (truncado de contexto) lo agrava: podéis estar generando respuestas sin parte de los fragmentos y con apariencia de cita correcta.

### P0 — (arrastrado de dimensión 1) Síntesis con contexto truncado + temperatura sin fijar
- Ver arriba. Es el hallazgo que más afecta a esta dimensión: toda la cadena de provenance (chunks → contexto → [N] → `apply_citations`) se rompe en el eslabón del prompt si el contexto se trunca. `apply_citations` post-procesa las claves [N] que el modelo sí menciona → la respuesta truncada **parece** correctamente citada.

### P1 — Ninguna verificación de que las citas [N] sustentan las afirmaciones
- `apply_citations` resuelve la referencia del [N], pero nada comprueba que el chunk N sustente la frase. Un 14B local generará citas decorativas (chunk topically cercano que no dice lo afirmado). Salvaguardas escalonadas sin infraestructura nueva: (a) temperatura 0 (ver P0); (b) chequeo determinista post-síntesis (todo [N] existe entre los chunks enviados) — gratis, hacedlo ya; (c) aviso permanente en UI "verifica cada afirmación contra el fragmento citado"; (d) más adelante, verificación de entailment solo para notas guardadas en `notas_rag/`.

### P1 — Item 30 (guía + política de uso) abierto mientras la app pública ya existe
- La app `:8502` está desplegada con password compartida y Gemini BYOK, sin guía ni política. Riesgo institucional: un alumno que cite una alucinación os salpica; y las consultas quedan registradas (`rag_queries_*.jsonl`) sin aviso de transparencia. Cerrar item 30 antes de cualquier difusión amplia: aviso de verificación en la propia UI (`st.caption` permanente), nota de registro de consultas, normas de licencias. Medio día — el quick-win con mayor ratio protección/esfuerzo del backlog.

### P2 — PDFs escaneados entran al índice vacíos (item 35)
- La parte barata ya puede hacerse: detectar `md_clean` ≈ 0 tras `3_process_corpus.py` y enviar a cuarentena (encaja con item 18) en vez de dejarlo. El OCR con `ocrmypdf` es fase 2.

### P2 — Para docencia, la página física del PDF no es la página impresa
- Los chunks de libros citan páginas físicas. Subir "mapear page labels" dentro del item 31 **antes** de escalar de 2 a 30 libros — re-procesar 30 libros después es evitable.

**Lo que está muy bien aquí:** la jerarquía de año de Crossref con el caso Wise documentado, `PRESERVE_FIELDS`, `validation_overrides` fuera del jsonl, la reconciliación registro↔corpus descubierta por vuestra propia verificación round-trip. Eso es cómo se opera un corpus.

---

## 4. Calidad de código y deuda técnica

### P1 — La duplicación es peor de lo estimado y ya ha divergido en un default (confirmado)
- **Qué (confirmado):** `load_metadata` y `embed_query` existen copiadas en **4 sitios**: `8_query_rag.py`, `run_eval.py`, `pool_candidates.py`, `run_rag_batch.py` (los comentarios literales dicen "Copiado VERBATIM de 8_query_rag.py"). La plantilla de síntesis existe en `rag_core.py::build_default_system` y copiada en `run_rag_batch.py::synthesize`. Y `2_RAG.py` importa **otro** `embed_texts` de `utils/attachments.py` (distinto del de `utils/embeddings.py`) — sería la tercera función de embedding.
- **El default ya divergió:** `run_rag_batch.py` tiene `cfg.setdefault("hybrid", True)` — la batería usa híbrido **ON** por defecto mientras la política del proyecto es OFF ("dense gana"). Es la demostración empírica del riesgo de duplicar: la copia ya se desalineó en un parámetro de comportamiento. La batería **no reproduce la configuración de producción** salvo que el YAML lo fije.
- **Recomendación:** (a) Corregir el default `hybrid` a `False` en `run_rag_batch.py` **hoy**. (b) Extraer a `utils/`: un loader compartido (`load_index_and_meta` con el `assert ntotal==len(meta)` de la dimensión 2), `embed_query`, y la plantilla de sistema (`utils/synthesis.py`, módulo puro sin streamlit). `8_query_rag.py` es un CLI importable — no hay excusa para copiarlo. Subir de "BAJA" a antes del primer uso serio de la batería para investigación. 2–3 horas.

### P1 — El núcleo de recuperación no tiene tests
- 210 tests de utilidades, cero de `utils/retrieval.py` (`dense_rank`, `bm25_rank`, `rrf_fuse`, `passes_filters`, `pool_size`), `run_eval.py` ni `pipeline.py`. Son funciones que se rompen **sin lanzar errores** — devuelven resultados distintos y nadie se entera. Suite sobre fixtures: RRF determinista; `passes_filters` con year=None + filtro activo (congelar la decisión ya documentada), secciones, `doc_type`, colección de `paper_id`; tokenizer con H2S/TiO2/NR-SOB (cuando lo arregléis). Sin Ollama ni FAISS real. 2–3 h.

### P2 — Escrituras de registros críticos no atómicas
- `download_registry.py::save` (`to_csv` directo), `pipeline.py` (`doi_registry.txt` con `open("w")`), `5_build_embeddings.py` (`indexed_papers.json`, `config.json`). Un kill a mitad deja el fichero corrupto. Patrón tmp+rename (3 líneas) en todos. Especialmente `pendientes_descarga.csv` y `doi_registry.txt`, que alimentan dedup y emails.

### P2 — Inconsistencias menores confirmadas
- `download_registry.py`: `upsert`/`mark_downloaded`/`snooze` comparan DOI sin normalizar case; `reconcile_with_corpus` sí → un DOI con mayúsculas se reconcilia pero no se marca por las otras vías. Normalizar con `_norm_doi_key` en todas. `run_adhoc` docstring dice "No hace cribado ni renombrado" pero sí renombra. `run_books` es `raise NotImplementedError` mientras ESTADO.md describe el flujo como funcional (código muerto contradictorio). Docstring de `8_query_rag.py` obsoleto ("nomic-embed-text", "k*5"). `iter_chunks` en `5_build_embeddings.py` revienta con `KeyError` si un chunk no tiene `text` (usar `.get`). Deuda bien catalogada: `_fmt_authors` (item 50), `--phase` vs `--project`.

---

## 5. Seguridad y aislamiento

### P1 — El Bearer viaja en HTTP plano (confirmado)
- Caddy en `http://pciq22.uca.es:11434` exige Bearer, pero el tráfico es HTTP sin TLS. El token (que es `OLLAMA_API_KEY`) circula en claro por la red UCA en cada llamada remota. Interceptable por cualquiera con posición en el segmento (red de campus con cientos de estudiantes). Habéis hecho bien lo difícil (autenticación real) y habéis dejado lo fácil (cifrar el canal).
- **Recomendación:** TLS en el Caddy de Ollama. (a) `tls internal` de Caddy + distribuir el cert raíz a los pocos clientes (Obsidian); (b) cert UCA si `pciq22.uca.es` puede obtenerlo; (c) si el único cliente remoto sois vosotros por VPN, cerrar `:11434` a la red y usar túnel SSH (`ssh -L 11434:127.0.0.1:11435`) — elimina la superficie. (a) es la menos friccionante a medio plazo.

### P2 — `PasswordAuthentication` sigue activo en pciq22
- Ya identificado en la auditoría de Hermes, sigue abierto. Con exposición en red universitaria, cerrarlo (claves solo) es higiene de 15 minutos.

### P2 — Superficie de la app pública `:8502`
- Password compartida única, sin rate limiting, con acceso a síntesis Ollama (recurso compartido), catálogo completo visible, uploader de PDFs arbitrarios (pymupdf parsea ficheros no confiables). Aceptable para el contexto, con dos mitigaciones baratas: rate limit por sesión en la pública, y validación de tamaño/tipo en el uploader (VERIFICAR si existe límite). El aviso de "tus consultas se registran" del item 30 también aquí.

### Hermes (pausado): valido la decisión y el checklist
- La auditoría del 2026-07-01 es correcta (token OAuth sobreprivilegiado que excede la whitelist, `docker.sock` = root de facto, `tools.include: []`). Añadiría solo: al re-autenticar Google, hacerlo con un proyecto GCP dedicado y verificación de scopes en el consent screen. No reactivar sin completarlo. Y sacar Hermes de ESTADO.md (ver dimensión 1).

---

## 6. Robustez operativa

### P1 — `config/.env` no está en git (correcto) ni en ningún backup (incorrecto)
- El backup rsync cubre `/Volumes/research/`. El `.env` vive en el repo local de pciq22, que no se rsynca, y está excluido de git. Existe una única copia de todas las API keys y passwords de las apps.
- **Recomendación:** (a) Copia cifrada del `.env` (age/gpg, passphrase en gestor fuera de la máquina) como paso de `12_Backup.py`, o (b) secretos en un gestor de contraseñas del grupo y `.env` regenerable desde ahí, documentado. (a) es 1–2 h reutilizando la página existente.

### P2 — Observabilidad: sin alerta de servicio caído ni rotación de logs
- Los logs de Streamlit/Caddy/scopus crecen sin rotación. Si un LaunchAgent muere y KeepAlive no lo rescata, nadie se entera hasta que un usuario entra y falla. Recomendación: (a) rotación vía `newsyslog` (`/etc/newsyslog.d/research_agent.conf`) — 10 min; (b) healthcheck barato: cron/launchd con `curl -fsS` a `:8501`, `:8502`, `:11434` (con token) y GROBID `/api/isalive`, email solo si falla (reutilizando el SMTP de `run_weekly_scopus.py`). ~50 líneas, cierra el hueco "me entero por el usuario".

### P2 — Backup: bien diseñado, dos refuerzos baratos
- El `--size-only` por SMB sin mtime, dry-run previo, banner de >15 días y `#recycle` con auto-vaciado están bien pensados. Refuerzos: (a) el email semanal incluye una línea "último backup: hace N días" (ya tenéis el canal y el dato); (b) item 27 (backup de configs) junto al `.env` de arriba.

### P2 — SPOF y bus factor
- pciq22 es single point of failure y el conocimiento está concentrado. Runbook mínimo explícito: "si pciq22 muere: (1) montar research_bk, (2) `pip install -r requirements-lock.txt`, (3) re-aplicar `deployment/`, (4) re-emitir `.env` desde el gestor". Los índices FAISS son regenerables desde chunks — decidlo explícitamente para que nadie entre en pánico por el índice.

**Bien:** cuarentenas reversibles con manifiesto y restauración real, `.bak` generalizado, recuperación de ingesta tras reinicio, verificación round-trip contra datos reales (la sesión 2026-07-12 destapó el bug de reconciliación 34/35 — ejemplar).

---

## 7. Roadmap

**Bien secuenciado, no tocar:** item 37 como prerrequisito del reranking; libros bloqueados por su eval; decisión de no generar golden con modelos.

**Re-priorización propuesta (orden de ejecución):**

| # | Acción | Esfuerzo | Prioridad | Por qué ahora |
|---|---|---|---|---|
| 1 | **`num_ctx` + temperatura en las dos rutas de síntesis** (rag_core + run_rag_batch) | 30 min | **P0** | Degradación silenciosa activa hoy |
| 2 | **Default `hybrid` a False en run_rag_batch** | 2 min | P1 | Batería no reproduce producción |
| 3 | **Tokenizer BM25** (acrónimos/fórmulas/tildes) + tests | ½ día | P1 | Raíz de la conclusión denso/híbrido |
| 4 | Aplicar plist 04:00 + migrar scopus_weekly a LaunchDaemon + subprocess con kill real | 1 h | P1 | Fallo silencioso ya demostrado; timeout falso |
| 5 | Verificar norma de embeddings (3 líneas) + normalizar si procede | 15 min | P1 | Cierra la decisión de métrica del índice |
| 6 | `assert ntotal==len(meta)` + `indexed_papers.json` antes de `write_index` | 1 h | P1 | Invariante crítica sin protección |
| 7 | `run_eval`: excluir preguntas sin relevantes + IC Wilson + Recall@k/P@k + arquetipo + manifest en CSV | ½ día | P1 | Una iteración, antes de generar golden nuevos |
| 8 | `requirements-lock.txt` + versionar compose GROBID/plist Ollama | 1 h | P1 | Reproducibilidad real |
| 9 | Backup cifrado de `.env` + item 27 | 2 h | P1 | Única copia de todos los secretos |
| 10 | Item 30 (guía + política + avisos en UI) | ½ día | P1 | Prerrequisito de difundir `:8502` |
| 11 | Desduplicar (utils/synthesis + loader + embed_query compartidos) | 3 h | P1 | Antes de usar la batería para investigación |
| 12 | Tests de `utils/retrieval.py` | 3 h | P1 | Congela el núcleo antes de los experimentos |
| 13 | TLS en Caddy o túnel SSH | ½ día | P1 | Cierra el Bearer en claro |
| 14 | Re-correr eval denso/híbrido con tokenizer arreglado | 1 h | P1 | Verifica si la conclusión cambia |
| 15 | Ampliar golden a ~25 × 3 categorías (con arquetipo) | días experto | Inversión | Tras 3, 7, 14 — en ese orden |
| 16 | Eval libros (8–12 preguntas manuales) | ½ día experto | Quick-win | Desbloquea item 31 y escalado a 30 libros |
| 17 | Reranking (LLM-as-reranker primero) | 1–2 días | Inversión | Solo post-golden; fuera de Ollama |
| 18 | OCR (item 35): detección + cuarentena ya | ½ día | Media | Barato; OCR cuando haya volumen |
| 19 | **Item 28 (OpenClaw): congelar** | — | De-scoping | Tras reconcile (34/35 ya estaban), pendientes reales ~1; ROI desplomado |

**Dependencias explícitas:** tokenizer (3) → re-eval (14) → golden ampliado (15) → fusión/rerank (17). Hacerlos en otro orden contamina la atribución. `num_ctx`/temperatura (1) → cualquier evaluación de síntesis futura. Item 30 (10) → difusión de `:8502`. Desduplicación (11) → uso investigativo de la batería.

---

## Los 5 problemas más importantes

1. **Síntesis con contexto truncado en silencio en las dos rutas (app + batería), más temperatura sin fijar.** `stream_ollama` y `run_rag_batch.py::synthesize` llaman a Ollama sin `num_ctx` ni `temperature`. Con top_k=8 y chunks de ~1500 chars ya se supera el default de 4096 tokens: el sistema genera respuestas sin parte de los fragmentos y sin las reglas de cita, pero `apply_citations` post-procesa las claves [N] mencionadas → parecen correctamente citadas. Es la degradación más perversa posible: invisible y con apariencia de provenance. Fix de 30 minutos, hoy.
2. **La decisión denso-vs-híbrido (híbrido OFF por defecto) se tomó con un BM25 que destruye exactamente los términos donde BM25 aporta** (`tokenize` rompe `NR-SOB`, `Fe(II)`, tildes, griegas, en query e índice). La conclusión puede ser correcta por parsimonia, pero la evidencia no la sostiene. Arreglar el tokenizer y re-correr la eval antes de cualquier otra decisión de esta dimensión.
3. **La ingesta semanal tiene tres grietas apiladas**: LaunchAgent con trigger que se pierde sin sesión gráfica (mismo fallo ya sufrido dos veces), el plist de las 04:00 sin aplicar desde hace un mes, y un "timeout de 90 min" que no termina el proceso (thread no-daemon: el proceso se queda colgado en el cierre del intérprete). Todo con fix barato y patrón ya probado en casa.
4. **Duplicación de la lógica crítica en 4 sitios, ya divergida en un default** (`run_rag_batch` usa híbrido ON). Dos fuentes de verdad para lo más sensible (qué se recupera, con qué prompt) que ya se han desalineado — la demostración empírica del riesgo. Más: índice L2 sin normalización explícita y sin `assert` de alineación metadata↔vectores.
5. **Brechas de recuperación ante desastre y de transporte**: `config/.env` sin ninguna copia (fuera de git y del rsync), infraestructura crítica no versionada (compose GROBID, plist Ollama), sin lockfile del venv de producción, y el Bearer circulando en HTTP plano por la red del campus.

## 3 cosas que el proyecto YA hace bien (no "arreglar")

1. **La ingeniería de reversibilidad y provenance del corpus.** Cuarentenas con manifiesto y restauración real, `.bak` sistemático, `PRESERVE_FIELDS`, `validation_overrides` deliberadamente fuera del jsonl, y la reconciliación registro↔corpus (37 DOI) descubierta por vuestra propia verificación round-trip. Es el patrón correcto; extenderlo, no tocarlo.
2. **La validación de metadatos Nivel 1 + Nivel 2 con Crossref como sugerencia y nunca como sobreescritura.** La jerarquía de año con el caso Wise resuelto y documentado, severidades calibradas contra datos reales, adopción masiva acotada a |Δ|=1. Diseño data-driven maduro. No cambiéis la política print-first.
3. **La honestidad metodológica de la documentación.** "Sin potencia estadística" escrito en el propio backlog, decisiones con racional, gotchas de launchd registrados con la evidencia que los produjo. Esa disciplina es la que permite auditorías como esta. Mantenedla incluso cuando duela.

---

## Suposiciones: estado tras esta revisión

**Confirmadas por el código:**
- (2) num_ctx/temperatura no fijados → **CONFIRMADA en ambas rutas** (P0).
- (3) Índice L2 sin normalización explícita → **CONFIRMADA** (IndexFlatL2, sin normalize_L2; falta solo el dato de la norma real de Ollama).
- (5) "Timeout" de run_weekly_scopus no termina el proceso → **CONFIRMADA y agravada** (thread no-daemon).
- (7) Tokenizer BM25 genérico → **CONFIRMADA** (`[a-z0-9]+`, rompe acrónimos/fórmulas).
- (8) Golden sin campo `archetype` → confirmada (la estratificación es tarea pendiente).

**Descartadas:**
- "RRF k=60 sobre pools de 8+8" → **FALSA** (pool_size = max(k*10, 200)). Retirada.
- (6) run_eval registra estado del corpus → confirmado que **no** lo hace (fieldnames fijos).
- (10) 8_query_rag importable sin streamlit → **confirmado** (no importa streamlit; refuerza el hallazgo de duplicación).
- (4) requirements sin pins → no lo he verificado directamente; mantener como VERIFICAR.
- (9) app pública sin rate limiting / límite en uploader → no lo he verificado; VERIFICAR.
- (11) top_k default 8 en app → confirmado.
- (12) password compartida única → confirmado por `check_password`.

**Siguen abiertas (menores):** si Ollama normaliza los embeddings de bge-m3 (punto 2, verificable en 3 líneas); si `utils/attachments.py::embed_texts` duplica funcionalidad con `utils/embeddings.py` (parece que sí, comportamiento distinto); comportamiento exacto de `app_utils.estimate_cost_usd` (la pre-estimación de coste en `2_RAG.py` asume 1200 chars/chunk cuando el tope real es 8000 → subestima ~6x el input en providers de pago — P2 nuevo, VERIFICAR).
