# Informe de rollout — commit 6093f35 (items 62, 63, 55a, 55b, embed_truncated, 33)

**Máquina:** pciq22 · **Repo:** `/Users/martinramirez/proyectos/research_agent`
**Fecha:** 2026-07-25 · **HEAD:** `6093f351926c5efd793fda1869419a82c226511a` (rama `main`)
**Python:** `/Users/martinramirez/venvs/rag_papers/bin/python3`
**Salida de esta sesión:** `/Volumes/research/metadatos/eval/rollout_6093f35/`

No se ha hecho commit ni push en pciq22 en ningún momento (disciplina de dos máquinas respetada). El único cambio en el árbol de trabajo al cierre de la sesión es `tests/test_bm25_tokenizer.py` (fix del test descrito en PASO 0.4), sin commitear, a la espera de que se lleve a casa.

---

## PASO 0 — Diagnóstico y estado "antes"

### 0.1 — Confirmación del commit
`origin/main` en `6093f35` ✅. El HEAD local ya estaba en `6093f35` al empezar la sesión (de trabajo previo), así que no faltaba ningún push desde casa.

### 0.2 — Caché de vectores de libros (`books/embed.py`)
Analizado el código: la caché `_vectors/<book_id>.npy` se invalida por **sha256 del fichero `chunks/<book_id>.jsonl` completo** (no por flags), así que un re-chunk que cambie el texto la invalida automáticamente, con o sin `--force`. Más importante: la normalización L2 (`l2_normalize`) se aplica **siempre, incondicionalmente, al ensamblar el índice** (línea 214), después de decidir si cada libro viene de caché (vectores crudos) o de reembeber — nunca hay un camino donde vectores sin normalizar lleguen al índice final. Además el script **nunca hace `faiss.read_index`**: reconstruye el índice completo en memoria en cada ejecución. Conclusión: sin riesgo, no hizo falta borrar nada a mano.

### 0.3 — Estado del pipeline de libros
3 PDFs en `pdfs/`, pero solo 2 con chunks/vectores: `1996-Blanch_Clark_Biochemical_Engineering.pdf` nunca se había procesado (a medio ingerir, no a medio re-trocear). Por indicación tuya, se dejó **fuera** de este rollout — excluido explícitamente vía `--input-dir` con symlinks solo a Najafpour y Burstein, sin tocar el PDF de Blanch & Clark.

### 0.4 — Suite de tests
Primera pasada: **293 passed, 1 failed** (no 294/0 esperado). El fallo (`test_accented_query_retrieves_unaccented_document`) se investigó y se confirmó que **no era una regresión del tokenizer (item 33)**: con el corpus de juguete original (2 documentos, el término en 1 de ellos), la IDF clásica de Okapi de `rank_bm25` da `log((2-1+.5)/(1+.5)) = log(1) = 0` exacto — el score sale 0 pase lo que pase con el tokenizer. Confirmado añadiendo un 3er documento distractor: la búsqueda funciona correctamente. Por tu indicación, se arregló el test (añadido un 3er documento al corpus del test, `tests/test_bm25_tokenizer.py`, sin tocar `scripts/`) y la suite completa quedó en **294 passed, 0 failed, 0 skipped**.

### 0.5 — Estado "antes" (capturado antes del rollout)

| categoría | n_chunks | ntotal FAISS | n_papers | n_table | `normalized`? | norma L2 media |
|---|---:|---:|---:|---:|---|---:|
| biological_gas_odor_treatment | 166 | 166 | 8 | 23 | False | 25.73 |
| anoxic_biogas_biodesulfurization | 1741 | 1741 | 87 | 165 | False | 25.88 |
| bioplastics_microplastics | 9454 | 9454 | 373 | 746 | False | 25.84 |
| biogas_upgrading_biomethanation | 8276 | 8276 | 342 | 919 | False | 25.86 |
| microalgae | 76 | 76 | 4 | 6 | False | 25.95 |
| single_cell_protein | 30 | 30 | 1 | 3 | False | 25.78 |
| advanced_oxidation_processes | 27 | 27 | 2 | 4 | False | 25.74 |
| bioleaching_critical_materials | 160 | 160 | 6 | 11 | False | 25.92 |
| libros_docencia | 209 | 209 | 2 | 0 | False | 25.73 |

`ntotal == n_chunks` en las 9. Ningún `config.json` tenía `normalized` todavía. Detalle completo (incluida distribución de `section_canonical` por categoría) en `antes.md`/`antes.json`.

**⚠️ Incidente operativo durante el PASO 3:** reutilicé por descuido el mismo script de captura para medir el estado "después", con el mismo nombre de fichero de salida, y sobreescribí `antes.json`/`antes.md` con datos posteriores al rollout. Lo detecté al comparar cifras (anoxic mostraba 1636 chunks en lo que debía ser el "antes"). Reconstruí ambos ficheros a partir de los números exactos que ya habían quedado transcritos en la conversación antes del incidente (no es una nueva medición — es la misma medición original recuperada de la transcripción; el único detalle no recuperable es la muestra individual de 50 vectores para la norma L2, se preserva la media agregada, que es lo único que se usa en cualquier conclusión). Para el estado "después" escribí un script nuevo, con nombres de fichero distintos (`despues.json`/`despues.md`), para no repetir el error. Ambos ficheros están verificados como correctos y distintos tras la reconstrucción.

---

## PASO 1 — Quiesce

- **1.1** Ambas instancias de Streamlit paradas con `launchctl bootout` (privada 8501 y pública 8502). Confirmado con `launchctl list` (sin entrada) y `lsof -i :8501 -i :8502` (sin nada escuchando).
- **1.2** `com.research_agent.scopus_weekly.plist` desactivado con `launchctl bootout`. Comando de reactivación: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.research_agent.scopus_weekly.plist` (ejecutado al final, PASO 4.2).
- **1.3** `git pull` → "Already up to date." HEAD confirmado en `6093f35`.

---

## PASO 2 — Rollout (atómico)

### 2.1 — Re-troceado de las 8 categorías (`3_process_corpus.py --phase <cat> --force-md`)

Las 8, sin errores, sin TEI ausente, todas rc=0, todas en segundos (no invoca GROBID):

| categoría | duración |
|---|---:|
| biological_gas_odor_treatment | 0s |
| anoxic_biogas_biodesulfurization | 1s |
| bioplastics_microplastics | 6s |
| biogas_upgrading_biomethanation | 4s |
| microalgae | 1s |
| single_cell_protein | 0s |
| advanced_oxidation_processes | 0s |
| bioleaching_critical_materials | 1s |

### 2.2 — Re-embebido de las 8 categorías (`5_build_embeddings.py --project <cat> --phase all --force`)

Ejecutado en segundo plano, monitorizado periódicamente (logs vacíos hasta el final por buffering de stdout al redirigir a fichero — verificado que no era cuelgue comprobando actividad en tiempo real de Ollama, `~/ollama.launchd.log`/`.err`, en cada chequeo). Todas rc=0:

| categoría | duración | chunks antes→después | truncados |
|---|---:|---|---:|
| biological_gas_odor_treatment | 35s | 166→158 | 0 |
| anoxic_biogas_biodesulfurization | 646s (~11 min) | 1741→1636 | 3 |
| bioplastics_microplastics | 8155s (~2h16min) | 9454→9078 | 58 |
| biogas_upgrading_biomethanation | 7246s (~2h1min) | 8276→7934 | 28 |
| microalgae | 81s | 76→72 | 1 |
| single_cell_protein | 27s | 30→29 | 0 |
| advanced_oxidation_processes | 29s | 27→25 | 0 |
| bioleaching_critical_materials | 154s | 160→154 | 0 |

Duración total del bloque de embebido de papers: ~5h20min (13:47–18:20 aprox.).

### 2.3 — Libros

`books/process.py --force --input-dir <symlinks a Najafpour y Burstein, excluyendo Blanch&Clark>`: 2/2 OK, 0 errores, **209 chunks** (153 Najafpour + 56 Burstein — coincide exacto con el total pre-rollout, buena señal de consistencia).

`books/embed.py --force`: 209 vectores, 2/2 libros embebidos (0 reutilizados, `--force` ignoró la caché como se esperaba), 4 truncados por contexto (avisos normales del truncado reactivo). `config.json` resultante: `"normalized": true`.

---

## PASO 3 — Verificación

### 3.1 / 3.2 — Invariante 55b y flag `normalized` en los 9 índices

| categoría | ntotal==n_chunks | `normalized` | norma L2 media |
|---|---|---|---:|
| biological_gas_odor_treatment | ✅ (158=158) | true | 1.000 |
| anoxic_biogas_biodesulfurization | ✅ (1636=1636) | true | 1.000 |
| bioplastics_microplastics | ✅ (9078=9078) | true | 1.000 |
| biogas_upgrading_biomethanation | ✅ (7934=7934) | true | 1.000 |
| microalgae | ✅ (72=72) | true | 1.000 |
| single_cell_protein | ✅ (29=29) | true | 1.000 |
| advanced_oxidation_processes | ✅ (25=25) | true | 1.000 |
| bioleaching_critical_materials | ✅ (154=154) | true | 1.000 |
| libros_docencia | ✅ (209=209) | true | 1.000 |

**Las 9/9 pasan limpiamente.** Ningún rollout parcial.

### 3.3 — Distribución de `section_canonical`: antes vs después

**⚠️ Actualizado 2026-07-25 (Encargo 2a): esta tabla usaba `antes.json` RECONSTRUIDO de la
transcripción. Sustituida por datos RE-DERIVADOS de verdad — worktree en `6093f35^` +
`3_process_corpus.py --force-md` contra el TEI real, sin tocar `/Volumes/research/categorias/`
(detalle del método en "Encargo 2" más abajo). Coincide exactamente con la reconstrucción en 7/8
categorías; difiere en `anoxic` (ver nota bajo la tabla) y añade, por petición expresa, las columnas
`methods`% junto a `other`% porque en `bioleaching_critical_materials` ambas EMPATAN exactas a
37,50% (60/160) — mostrar solo `other` sin el contexto de `methods` inducía a leerlo como una
posible errata de mi reconstrucción; no lo era, es una coincidencia real, confirmada ahora con datos
re-derivados, no reconstruidos.**

| categoría | `other`% antes | `methods`% antes | `other`% después | Δ pp (other) | n_chunks antes | n_chunks después |
|---|---:|---:|---:|---:|---:|---:|
| biological_gas_odor_treatment | 44.58 | 9.04 | 51.27 | +6.69 | 166 | 158 |
| anoxic_biogas_biodesulfurization | 35.33 | 14.58 | 50.18 | +14.85 | 1721 | 1636 |
| bioplastics_microplastics | 44.01 | 11.03 | 61.29 | +17.28 | 9454 | 9078 |
| biogas_upgrading_biomethanation | 43.03 | 12.16 | 54.21 | +11.18 | 8276 | 7934 |
| microalgae | 28.95 | 25.00 | 50.00 | +21.05 | 76 | 72 |
| single_cell_protein | 66.67 | 13.33 | 65.52 | −1.15 | 30 | 29 |
| advanced_oxidation_processes | 48.15 | 3.70 | 44.00 | −4.15 | 27 | 25 |
| **bioleaching_critical_materials** | **37.50** | **37.50** | 61.04 | +23.54 | 160 | 154 |

**`other` crece en 6/8 categorías, tal como predecía el ítem 62** (subsecciones que antes heredaban falsamente methods/results del título dejan de hacerlo). Las 2 excepciones (single_cell_protein, advanced_oxidation_processes) son las **2 categorías más pequeñas** (30 y 27 chunks antes) — coherente con el mecanismo real: el ítem 62.1 (reclasificación) *añade* registros "other", pero el 62.2 (fusión de portadas) *elimina* uno "other" por cada portada fusionada (la portada vacía en sí estaba etiquetada "other" antes de fusionarse). En categorías con muy pocos papers, si casi ninguna subsección venía mal etiquetada por el título, el efecto de resta del 62.2 puede superar al de suma del 62.1 y el porcentaje baja. No es una regresión, es el mismo mecanismo documentado con varianza de muestra pequeña.

**Nota `anoxic` — n_chunks antes corregido de 1741 a 1721 (real):** la re-derivación desde el TEI actual (86 papers reales) da 1721 chunks, no los 1741 que reportaba el índice FAISS viejo. Los 20 chunks de diferencia son el "paper fantasma" `2019_santos_clotas_..._sewage_biogas_2`, cuarentenado el 2026-06-14 pero cuyos vectores seguían vivos en el índice hasta este rollout (ver Encargo 2 y "QUÉ MIRAR CON LUPA" #3). El 1741 de la línea base original no era erróneo como medición del índice de entonces — era fiel a un índice que ya arrastraba 6 semanas de desincronización antes de que empezara esta sesión.

**Desglose por paper — `bioleaching_critical_materials` (Encargo 2b, los 6 papers, antes → después):**

| paper_id | n antes | n después | other antes | methods antes | other después | methods después |
|---|---:|---:|---:|---:|---:|---:|
| 2023_compagnone_sustainable_recovery_platinum_group_metals... | 30 | 29 | 13 | 10 | 12 | 10 |
| 2025_vitale_biotechnological_valorisation_spent_automotive... | 20 | 19 | 12 | 2 | 11 | 2 |
| 2026_cao_bioleaching_enhanced_milliampere_level_direct_current... | 17 | 16 | 11 | 2 | 10 | 2 |
| 2026_damodaran_recovery_precious_metals_industrial_spent... | 33 | 32 | 24 | 2 | 23 | 2 |
| 2026_kelly_hydrometallurgical_recovery_high_purity_copper... | 33 | 32 | 0 | 22 | 18 | 3 |
| 2026_santomartino_microbial_biomining_asteroidal_material... | 27 | 26 | 0 | 22 | 20 | 1 |

**La hipótesis del "contagio del título por ascenso de ancestros" se confirma con precisión de paper:** en 4 de los 6 papers (compagnone, vitale, cao, damodaran) `methods` ya era bajo antes (2-10) y apenas cambia — sus títulos no contenían keywords de sección, así que el 62.1 no tenía nada que corregir en ellos. Los otros 2 (**kelly**, **santomartino**) tenían `methods` en **22/33 y 22/27** — más de dos tercios del paper entero etiquetado "methods" — y se desploman a **3 y 1** tras el fix, con "other" pasando de **0 a 18** y de **0 a 20** respectivamente. Es decir: en kelly y santomartino, prácticamente ninguna subsección del cuerpo tenía clasificación propia — TODAS heredaban la etiqueta falsa del título vía ascenso de ancestros, exactamente el mecanismo que describe el ítem 62. Estos 2 papers por sí solos explican el grueso del salto de +23,54pp en `other` de toda la categoría — con solo 6 papers, 2 casos extremos bastan para mover la media de la categoría entera.

### 3.4 — Fusión de chunks de portada

| | antes (2026-07-25) | después |
|---|---:|---:|
| SOLO_METADATA | 809 | **2** |
| MIXTO | 9 | 815 |
| OTROS | 5 | 5 |
| Total chunk_index=1 | 823 | 822 (−1 por el paper fantasma de anoxic, ver nota bajo la tabla de 3.3) |

**809 → 2 (99,75% fusionados).** Los 4 MIXTO conocidos del 2026-07-25 (`carnevale_miino`, `wang_understanding`, `jusoh`, `liu_anchoring`) **siguen existiendo y siguen bien etiquetados** (4/4 confirmados). Los 2 SOLO_METADATA residuales (`2020_iyare...`, `2026_tang...`) se inspeccionaron a mano: **sí se fusionaron** (el texto contiene el abstract real tras la línea de autores/DOI), simplemente el abstract combinado es genuinamente corto (164-180 caracteres) y cae bajo el umbral de 200 caracteres que usé como criterio — no es un fallo de fusión, es un caso límite del umbral.

**Encargo 2d — reconciliación exacta de la aritmética de chunks (caída total = SOLO_METADATA fusionados + Δ nº de piezas de tabla), re-derivada, residuo=0 en las 8 categorías:**

| categoría | caída total | SOLO_METADATA fusionados | Δ piezas de tabla | suma | residuo |
|---|---:|---:|---:|---:|---:|
| biological_gas_odor_treatment | 8 | 8 | 0 | 8 | **0** |
| anoxic_biogas_biodesulfurization | 85 (sobre 1721 real, no 1741) | 84 | 1 | 85 | **0** |
| bioplastics_microplastics | 376 | 366 | 10 | 376 | **0** |
| biogas_upgrading_biomethanation | 342 | 337 | 5 | 342 | **0** |
| microalgae | 4 | 4 | 0 | 4 | **0** |
| single_cell_protein | 1 | 1 | 0 | 1 | **0** |
| advanced_oxidation_processes | 2 | 2 | 0 | 2 | **0** |
| bioleaching_critical_materials | 6 | 6 | 0 | 6 | **0** |

Los "10 extra" en bioplastics y "5 extra" en upgrading que no cuadraban en la primera versión de este informe **no eran un error de conteo — eran chunks de tabla que cambiaron de número de piezas** por el fix 63.3 (cada parte de una tabla troceada ahora reserva presupuesto para repetir `### Table N` + caption, así que el empaquetado de una tabla grande en N piezas puede dar un N distinto al de antes). Bioplastics y upgrading son, no por casualidad, las 2 categorías con más y mayores tablas del corpus — coincide exactamente con dónde aparecía el "extra" sin explicar. anoxic cuadra con el paper fantasma (**re-derivado sin fantasma**: 84 SOLO_METADATA, no 85 — la cifra de 85 de la primera versión de este informe venía de un índice que todavía incluía el fantasma) más 1 pieza de tabla de menos.

### 3.5 — Tablas de `2023_almenglo`

Antes: 2 chunks para Table 1 (`#33` caption-huérfano de 107 chars, `#34` con todas las filas fusionadas, 7993 chars, sin caption). Después: **4 chunks de tabla** (2 para Table 1 tab_0: 7768+804 chars; 1 para una segunda figura Table 1 tab_1, 2380 chars; 1 para Table 3, 4982 chars). Verificado con evidencia:

- **Las 2 partes de Table 1 (tab_0) empiezan ambas con `### Table 1` + el caption completo** (fix 63.3 confirmado).
- **Verificación a nivel de corpus completo**: 0 de 1859 chunks de tabla (8 categorías) sin el heading `### Table N` al inicio (antes había 2/165 solo en anoxic). 25 chunks de tabla con longitud <150 chars, todos inspeccionados — ninguno es un caption huérfano, todos contienen al menos una fila de datos real; son simplemente tablas/fragmentos pequeños de por sí.
- **⚠️ Corregido 2026-07-25 (Encargo 2c) — mi "0 filas fusionadas" original medía solo el patrón `" - Type:"` en el único paper de almenglo, no el corpus.** Con un patrón general (cualquier `"- Campo:"` pegado sin salto de línea previo, no atado a un nombre de columna) sobre las 8 categorías del corpus **re-derivado antes del rollout**: **29 de 1875 chunks de tabla (1,5%)** tenían filas fusionadas por nuestro fallback — 28 tablas ≥7500 chars en total, la mayoría en `bioplastics_microplastics` (18 chunks afectados: `wu_effects`, `zhang_environmental`, `nguyen_microplastic`, `fatima_phycoremediation` ×4, `kallon_uptake` ×2, `puteri_technologies` ×2, `singh_biochar` ×2, `wang_tetracycline`, `kaya_nanoplastics` ×2, `patil_advances` ×2) y `biogas_upgrading_biomethanation` (8 chunks: `tian_life_cycle` ×2, `ghorbani_multi_objective` ×2, `lin_review` ×2, `cesar_biogas_refining` ×2), más el caso original de almenglo en anoxic. **No era un caso aislado de un solo paper — era sistemático en cualquier tabla grande sin columna "Exp.", en cualquier categoría.** Repetí la misma búsqueda general contra el corpus **DESPUÉS** del rollout (las 8 categorías, 1859 chunks de tabla reales): **0 casos**. El fix cierra el 100% de los 29, no solo el ejemplo de almenglo que verifiqué a mano la primera vez. Corregido también en `Mejoras_pendientes.md` item 63.
- **Matización que SÍ se sostiene (verificada solo para el caso de almenglo, no generalizada a los otros 28):** inspeccioné el TEI de almenglo directamente y confirmé que su fila "Type: BTF b BTF HFBR Other c..." (el ejemplo citado en el ítem 63 como prueba del bug) **ya viene así, con múltiples valores en una sola celda, DIRECTAMENTE del TEI de GROBID** — GROBID unió 4-5 filas visuales del PDF (sin líneas horizontales entre ellas) en un único `<row>` con celdas multi-valor, antes de que nuestro código la tocara. Ese ejemplo concreto seguirá mostrando valores agrupados aunque el fix sea perfecto, porque es techo de GROBID, no de nuestra capa. **No he verificado si los otros 27 casos tienen la misma causa mixta** (GROBID + nuestro fallback) o si son 100% atribuibles a nuestro fallback — con el fix ya cerrando los 29/29, no cambia la acción a tomar, pero sí matiza cuánto del "antes" era estrictamente nuestro.

### 3.6 — `embed_truncated`

Presente en el 100% de los 19.086 chunks de las 8 categorías (0 registros sin el campo). 90 chunks con `embed_truncated=true` (0,47% del corpus): 3 en anoxic, 58 en bioplastics_microplastics, 28 en biogas_upgrading_biomethanation, 1 en microalgae, 0 en el resto.

### 3.7 — Eval: los 4 comandos exactos del baseline

Comandos idénticos, literal, a `baseline_2026-07-25/baseline.md` (carpeta renombrada 2026-07-25, ver Encargo 6 al final — se llamaba `baseline_2026-07-26` por error, un día por delante de la fecha real). Salida cruda en `logs_paso3/`.

| categoría | modo | Hit@8 antes | MRR antes | Hit@8 después | MRR después | Δ Hit@8 |
|---|---|---|---:|---|---:|---:|
| anoxic | denso | 0.500 (2/4) | 0.098 | 0.500 (2/4) | 0.086 | 0 |
| anoxic | híbrido | 0.250 (1/4) | 0.062 | 0.250 (1/4) | 0.042 | 0 |
| upgrading | denso | 1.000 (6/6) | 0.708 | 1.000 (6/6) | 0.792 | 0 |
| upgrading | **híbrido** | **0.833 (5/6)** | 0.722 | **0.667 (4/6)** | 0.583 | **−1 hit** |

**Recordatorio de la interpretación obligatoria: n=4 y n=6, esto detecta regresiones, no demuestra mejoras.** No leo el +0.084 de MRR en upgrading-denso como "el fix mejora la recuperación" — es ruido de reordenamiento con esa n. Lo que SÍ es una señal real es la caída de Hit@8 en upgrading-híbrido, investigada en detalle (ver "QUÉ MIRAR CON LUPA").

### 3.8 — `corpus_manifest.json`

Regenerado para las 8 categorías (`utils/corpus_manifest.py --project <cat>`). Verificado uno (anoxic): `n_pdfs=86, n_papers_metadata=86, n_chunks=1636, faiss_indexes[0].chunks=1636, git_commit="6093f35", faiss_stale=false` — todo consistente.

---

## PASO 4 — Reactivación

- **4.1** `launchctl bootstrap` para las dos instancias de Streamlit. `launchctl list` confirma PID + status 0 en ambas; `curl` confirma HTTP 200 en `:8501` y `:8502`.
- **4.2** `com.research_agent.scopus_weekly.plist` reactivado, confirmado en `launchctl list` (cargado, en espera de su próxima ejecución programada — lunes 06:00 según `ESTADO.md`).
- **4.3** Prueba de humo de la fusión de `14_Preparar_clase.py` (sin levantar la UI: reproduje la misma lógica — `dense_rank` sobre el índice de `anoxic_biogas_biodesulfurization` + `dense_rank` sobre `libros_docencia` + `fuse_results(..., hybrid=False)`, las mismas funciones que importa la página — contra los índices reales ya reindexados). Query: *"biotrickling filter removal of hydrogen sulfide from biogas"*.
  - Distancias RAW de la categoría: 0.50–0.58. Distancias RAW de libros: 0.90–0.99. **Mismo rango pequeño y comparable** (nada en decenas/cientos, que sería la señal de un rollout parcial).
  - Cupo mínimo de libro (n_min=2) respetado: 2/2 chunks de libro en el top-8 final.
  - Resultado topicalmente coherente (papers sobre desulfurización de biogás + capítulo del libro de Ingeniería Bioquímica).

---

## QUÉ MIRAR CON LUPA

1. **Regresión real en `biogas_upgrading_biomethanation` híbrido (Hit@8 5/6→4/6).** Investigado a fondo: la pregunta 3 (*"¿Qué arqueas hidrogenotróficas dominan en reactores ex-situ termófilos de biometanación?"*) tenía como acierto en la línea base el paper `2020_logrono_microbial_resource_management_ex_situ_biomethanation_hydrogen_alkaline` en la posición 1. Tras el rollout, ese paper **desaparece por completo del top-8 en modo híbrido**. Aislé la causa: en modo **denso puro** ese mismo paper SÍ sigue siendo recuperable (aparece en posición 7 post-rollout, no estaba ni en el top-8 antes — el denso mejoró para este paper), y el Hit@8 denso de esa pregunta no cambia (sigue en pos 2 vía otro paper relevante). El problema está específicamente en la **fusión RRF con BM25**: con el tokenizer nuevo (item 33) y el corpus re-trocheado, el ranking BM25 de ese paper para esta query cambió lo suficiente como para que la fusión RRF ya no lo incluya en el top-8, pese a que el denso solo sí lo encuentra. Como híbrido está OFF por defecto en producción (ítem 53), esto no afecta a ningún usuario hoy — pero es exactamente el tipo de evidencia que el ítem 33 (fase 2, reranking) necesita antes de plantearse activar híbrido: el efecto neto del tokenizer sobre la fusión no es uniformemente positivo. Recomiendo anotarlo en `Mejoras_pendientes.md` item 33/37 con este caso concreto como ejemplo, no solo el agregado n=4/n=6.
2. **Corrección al diagnóstico del ítem 63, dos capas (actualizado tras Encargo 2c):** (a) a nivel de PATRÓN, el bug de fusión de filas era real y **sistemático — 29/1875 chunks de tabla (1,5%), 28 tablas grandes, en 3 categorías distintas —, no un caso aislado** como sugería mi primera comprobación (que solo miró 1 paper). El fix lo cierra al 100% (0/1859 después). (b) a nivel del EJEMPLO concreto citado en el ítem ("Soreanu 2010/Baspinar 2011/Chinalia 2012/Montebello fusionados" en almenglo), ese caso específico viene YA fusionado en el TEI de GROBID — no verificado si los otros 27 casos comparten esa causa mixta. Las dos cosas son ciertas a la vez: el ítem 63 estaba bien clasificado como CRÍTICO y de prevalencia real (no "mal atribuido entero" — la hipótesis condicional de que 0 casos invalidaría el ítem no se cumplió, salió 29), y a la vez su ejemplo ilustrativo tenía una causa parcialmente distinta a la que documentaba. Corregido en `Mejoras_pendientes.md` item 63.
3. **Anomalía de `n_papers` en anoxic (87→86), investigada y resuelta, y ahora cuantificada con precisión** (Encargo 2, re-derivación desde TEI real): el PDF/TEI/md_clean/chunks de `2019_santos_clotas_..._sewage_biogas_2` (un duplicado del paper `..._sewage_biogas` sin sufijo) ya habían sido eliminados de los ficheros de trabajo de la categoría el **2026-06-14** (verificado: `quarantine/orphan_tei/20260614_010931/` contiene el TEI huérfano correspondiente, y `papers_metadata.jsonl` no tiene esa entrada desde entonces) — pero como `5_build_embeddings.py` en modo incremental **nunca elimina vectores de papers que ya no están en `chunks/`**, ese paper fantasma llevaba **6 semanas exactas** viviendo silenciosamente en el índice FAISS de anoxic, aportando **20 chunks fantasma** (1741 del índice viejo vs 1721 reales re-derivados desde el TEI actual), invisible hasta que este rollout hizo el primer `--force` completo desde entonces. Verificado que es un caso **aislado**: las otras 7 categorías tienen `pdfs == chunks_files == n_papers antes == n_papers después`, sin ninguna diferencia. Es un efecto colateral positivo del rollout (corrige una desincronización de 6 semanas), pero expone que el modo incremental de `5_build_embeddings.py` puede acumular "vectores fantasma" indefinidamente sin ningún aviso. **Elevado a ítem propio del backlog — item 65, PRERREQUISITO del item 64** (cuarentenar un paper fuera de dominio no lo saca del RAG sin un `--force` posterior), no solo una nota aquí. Ver Encargo 4 más abajo.
4. **Incidente operativo propio, ya reparado**: sobreescritura accidental de `antes.json`/`antes.md` durante el PASO 3 (ver nota en 0.5). Reconstruido entonces con datos exactos de la transcripción, y **verificado 2026-07-25 contra una re-derivación real desde el TEI** (Encargo 2): la reconstrucción coincidía en 7/8 categorías; en `anoxic` la reconstrucción reproducía fielmente el índice viejo (1741, con fantasma) mientras que la re-derivación da la cifra real del corpus (1721, sin fantasma) — ambas correctas para lo que miden, ya no queda ambigüedad. Lo documento explícitamente para que quede constancia y no se repita el patrón (reutilizar un script de captura con el mismo nombre de salida en dos momentos distintos del mismo rollout).
5. **Regresión híbrida de upgrading, causa aislada (Encargo 3):** revertir SOLO el tokenizer (item 33) en `retrieval.py`, dejando el corpus re-trocheado (items 62/63) y la normalización L2 (item 55a) intactos, y re-correr el híbrido de `biogas_upgrading_biomethanation` contra el corpus YA reindexado — el hit de la pregunta 3 vuelve exactamente a la posición 1 (Hit@8 5/6, MRR 0,833, incluso mejor que el 0,722 original). Confirma sin ambigüedad que la regresión es 100% atribuible al tokenizer, no al re-chunking. Detalle completo en "Encargo 3" más abajo.

---

## ENCARGOS DE SEGUIMIENTO (revisión del informe, 2026-07-25)

Seis encargos sobre este mismo informe, sin repetir el rollout. Nada de lo de abajo modifica `/Volumes/research/categorias/` ni hace commit/push.

### Encargo 1 — ¿Hay algún LaunchAgent/LaunchDaemon capaz de re-disparar un prompt viejo con bypass contra datos vivos?

**Sí existe `~/claude-scheduled/`, con un LaunchDaemon cargado — pero NO representa el riesgo que preguntas.**

- `launchctl list | grep -i "claude\|scheduled"` → solo aparecen procesos de la app Claude Desktop (`com.anthropic.claudefordesktop.*`, sin relación) y **`com.research_agent.daily_question`** (system LaunchDaemon, `active count=0`, cargado, corre a diario 06:00, `runs=5`).
- El plist (`/Library/LaunchDaemons/com.research_agent.daily_question.plist`) invoca `/bin/bash ~/claude-scheduled/scheduled-claude.sh`.
- Leí el script completo. Construye un prompt autocontenido (pregunta del usuario + datos de tiempo/mareas ya resueltos por `curl`, sin que el modelo tenga que buscar nada) y lo pasa a:
  ```
  claude --print --model claude-haiku-4-5-20251001 --allowedTools "WebSearch,WebFetch"
  ```
- **`--allowedTools` es una lista BLANCA explícita — no hay bypass de ningún tipo.** Sin Bash, sin Read, sin Write, sin Edit: no puede tocar `/Volumes/research/`, el repo, ni ningún fichero del sistema. Cada ejecución es un proceso `claude --print` aislado que no reanuda ninguna sesión anterior — no hay memoria ni contexto persistente entre ejecuciones.
- `question.md` (la única "instrucción persistente" real) dice hoy, literal: *"¿qué tiempo va hacer hoy en Chiclana y cuáles son los horarios de mareas en Cádiz?"* — sin ninguna relación con el proyecto ni con datos del NAS.
- No hay ningún otro plist en `/Library/LaunchDaemons/` ni `~/Library/LaunchAgents/` que invoque `claude`. `crontab -l` del usuario vacío (no pude comprobar el de root sin contraseña interactiva, pero el mecanismo real activo es el LaunchDaemon, no cron — `ayuda.md` dentro de la carpeta documenta cron mientras que el plist real es un LaunchDaemon, un desfase menor de documentación, no de comportamiento).
- Los últimos 15 registros del log (`~/Library/Logs/research_agent/daily_question.log`) son "Email enviado correctamente", sin errores.

**Conclusión: no hay ningún mecanismo capaz de re-disparar un prompt de esta sesión, ni de ninguna sesión de trabajo del repo, contra datos vivos. El único cron/daemon de Claude en el sistema es de bajo riesgo por diseño (lista blanca de solo lectura web, sin FS).**

### Encargo 2 — Re-derivación real del estado "antes" (sin reconstruir de la transcripción)

**Método:** `git worktree add <tmp> 6093f35^` (código de ANTES del fix, commit `afa7b60`). Para cada categoría, un directorio aislado en `/tmp` con `pdfs/` y `tei/` como symlinks de solo lectura a los reales (el TEI no se tocó nunca en todo este proceso, ni en el rollout ni aquí) y `md_clean/`/`chunks/`/`logs/` nuevos y vacíos. Ejecuté `3_process_corpus.py --phase <cat> --base <tmp> --force-md` (código viejo, TEI real, salida en `/tmp`) para las 8 categorías. Cero escritura en `/Volumes/research/`. Esto reproduce EXACTAMENTE lo que habría contenido el corpus si se hubiera reindexado justo antes del fix — no una reconstrucción de memoria, código real ejecutado contra datos reales.

Resultados de a), b), c), d) ya incorporados en el cuerpo del informe (secciones 3.3, 3.4 y 3.5 actualizadas arriba). Resumen de lo más importante:

- **a)** 7/8 categorías: la distribución re-derivada coincide EXACTA con la reconstrucción de la transcripción (confirma que la reconstrucción de emergencia del PASO 0 era fiel). La única diferencia es `anoxic`, por el paper fantasma (ver abajo).
- **b)** Desglose por paper de bioleaching: la coincidencia 37,50%/37,50% (other/methods) es real, no un error — verificado con datos re-derivados, no reconstruidos. 2 de los 6 papers (`kelly`, `santomartino`) explican por sí solos el grueso del salto de la categoría: tenían el 100% de sus subsecciones contagiadas por el título antes del fix.
- **c)** Búsqueda generalizada (no solo `"- Type:"`): el patrón de fusión de filas era **29/1875 chunks de tabla (1,5%) antes**, **0/1859 después**. Sistemático, no aislado — mi primera comprobación (solo el ejemplo de almenglo) infravaloraba mucho el alcance real.
- **d)** Reconciliación exacta con residuo=0 en las 8 categorías: caída de chunks = portadas fusionadas + cambio en el número de piezas de tabla (el fix 63.3 cambia cómo se empaquetan las tablas grandes en piezas, no solo cómo se separan las filas dentro de cada pieza).

### Encargo 3 — Aislar la regresión híbrida: ¿tokenizer o re-chunking?

**Método:** backup de `scripts/utils/retrieval.py`, sustitución quirúrgica de **solo** la función `tokenize()` por la versión pre-item-33 (`re.findall(r"[a-z0-9]+", text.lower())`), dejando intactas `dense_rank` (con la normalización L2 del item 55a) y el resto del fichero. `run_eval.py --category biogas_upgrading_biomethanation --hybrid` contra el corpus YA re-trocheado (items 62/63) — BM25 se construye al vuelo desde `metadata.jsonl`, no hace falta reindexar nada.

**Resultado:**
```
[3/6] ¿Qué arqueas hidrogenotróficas dominan en reactores ex-situ termófilos...
    Hit@8: 1  ·  RR: 1.000  ·  primera coincidencia: pos 1

Hit@8 promedio : 0.833  (5/6)
MRR              : 0.833
```
El hit vuelve exactamente a la posición 1 (mejor incluso que el 0,722 de MRR original). **La regresión es 100% atribuible al tokenizer del ítem 33, no al re-chunking de los ítems 62/63** — con el corpus nuevo pero el tokenizer viejo, el resultado es igual o mejor que la línea base completa (corpus viejo + tokenizer viejo).

`retrieval.py` restaurado desde el backup inmediatamente después de la prueba y verificado con `git diff` (sin diferencias contra HEAD). No se commiteó el revert en ningún momento — quedó solo como comprobación de un instante.

**Ampliación (misma sesión de revisión, 2026-07-25): dos medidas más con el mismo método.**

**(a) Duplicar la evidencia en `anoxic_biogas_biodesulfurization` híbrido:** mismo revert quirúrgico, `run_eval.py --hybrid` contra el corpus ya re-trocheado:
```
Hit@8 promedio : 0.250 (1/4)
MRR              : 0.062
```
Coincide EXACTO con la línea base original (Hit@8 1/4, MRR 0,062, hit en pos 4) — con el tokenizer viejo y el corpus nuevo, anoxic-híbrido reproduce bit a bit el resultado pre-rollout. Segunda confirmación independiente de que el tokenizer, no el re-chunking, gobierna el comportamiento híbrido.

**(b) Qué token concreto mueve el ranking en upgrading-pregunta-3:** tokenicé la query con ambas versiones y crucé contra el vocabulario de los 25 chunks del paper de Logroño:

| | tokenize VIEJO | tokenize NUEVO |
|---|---|---|
| Query completa | `qu, arqueas, hidrogenotr, ficas, dominan, en, reactores, ex, situ, term, filos, de, biometanaci, n` | `que, arqueas, hidrogenotroficas, dominan, en, reactores, ex-situ, ex, situ, termofilos, de, biometanacion` |
| Intersección con el documento | `ex, n, situ, term` | `ex, situ` |

El viejo tokenizer, al no plegar tildes, parte `hidrogenotróficas`→`hidrogenotr`+`ficas`, `termófilos`→`term`+`filos`, `biometanación`→`biometanaci`+`n`. Dos de esos fragmentos-basura, **`term`** y **`n`**, casan por pura casualidad de substring con palabras inglesas normales del documento de Logroño — verificado el contexto literal:
```
chunk 2: "...has some drawbacks concerning the long-term storage..."
chunk 2: "...is important for comparisons in terms of efficiency..."
chunk 3: "...as the inoculum source for the long-term enrichment..."
chunks 6,7,9,13,24: 'n' aparece suelto (fragmentos de una letra, ~1-2 por chunk)
```
Ninguna relación semántica con "termófilos" ni "biometanación" — es una colisión de substring entre el inglés "term"/"long-term" y el resto roto del español. El tokenizer nuevo elimina esos dos falsos positivos (tokens limpios `termofilos`/`biometanacion` que no aparecen en absoluto en el vocabulario del documento — intersección NUEVO vs documento: solo `ex, situ`, sin ganancia neta de tokens limpios). **La "regresión" es el tokenizer nuevo dejando de premiar por accidente a Logroño, no perdiendo una coincidencia real que antes tenía.** El denso (ajeno al tokenizer) ya lo confirmaba: encuentra a Logroño en pos 7 sin ayuda de BM25.

### Encargo 4 — Item nuevo: vectores fantasma

Añadido **item 65** a `Mejoras_pendientes.md`, marcado explícitamente como **prerrequisito del item 64**, con la evidencia del caso `2019_santos_clotas_..._sewage_biogas_2` (6 semanas, 20 chunks fantasma, cuantificado con precisión gracias al Encargo 2). También añadida una nota de advertencia al principio del propio item 64 apuntando al 65. Texto completo en `Mejoras_pendientes.md`.

### Encargo 5 — Puntos del addendum

**Diff literal de `tests/test_bm25_tokenizer.py`** (sin commitear — working tree de pciq22, no versionado; el 294/294 de la suite corresponde a este estado local, no a lo que hay en `origin/main`):
```diff
diff --git a/tests/test_bm25_tokenizer.py b/tests/test_bm25_tokenizer.py
index a8549c0..5e2a7fb 100644
--- a/tests/test_bm25_tokenizer.py
+++ b/tests/test_bm25_tokenizer.py
@@ -140,8 +140,16 @@ class TestEndToEndBM25:
         assert top and top[0] == 0
 
     def test_accented_query_retrieves_unaccented_document(self):
-        bm25 = build_bm25(["desulfurizacion anoxica del biogas", "otro tema"])
+        # Corpus de 3 docs, no 2: con exactamente 2 docs y el término en 1 de
+        # ellos, la IDF clásica de Okapi (rank_bm25) da log((2-1+.5)/(1+.5))=0
+        # exacto y el score sale 0 pase lo que pase con el tokenizer — no es
+        # un caso del tokenizer, es un artefacto del tamaño del corpus.
+        bm25 = build_bm25([
+            "desulfurizacion anoxica del biogas",
+            "otro tema",
+            "un tercer documento cualquiera sin relacion",
+        ])
         if bm25 is None:
             pytest.skip("rank_bm25 no instalado")
-        top = bm25_rank(bm25, "desulfurización", 2)
+        top = bm25_rank(bm25, "desulfurización", 3)
         assert top and top[0] == 0
```

**Norma L2 real vs la citada por el item 55a:** medida directamente sobre muestras de 27-50 vectores por índice en los 9 índices reales durante este rollout: **‖v‖≈25,8 de media** (25,73–25,95 según categoría), no 27,1. El 27,11 original (2026-07-20) salió de un único vector suelto, no de una media — corregido en `Mejoras_pendientes.md` (líneas del item 55a) y en `ESTADO.md`. No cambia ninguna conclusión (bge-m3 sigue sin normalizar en cualquier caso), solo la cifra citada.

**Aprendizaje metodológico sobre tests de BM25:** con exactamente 2 documentos en el corpus y un término presente en 1 de ellos, la IDF clásica de Okapi (la que usa `rank_bm25.BM25Okapi` por defecto) da:
```
idf = log((N - n + 0.5) / (n + 0.5)) = log((2 - 1 + 0.5) / (1 + 0.5)) = log(1) = 0
```
exactamente cero, así que el score BM25 sale 0 **independientemente de si el tokenizer funciona bien o mal**. Cualquier test end-to-end de BM25 necesita **≥3 documentos** en el corpus de prueba para no caer en este caso degenerado. Ya aplicado en el fix del test (Encargo 5, diff arriba) y documentado como comentario en el propio test.

**Item 35 — Blanch & Clark:** el PDF `1996-Blanch_Clark_Biochemical_Engineering.pdf` en `libros_docencia/pdfs/` sin `chunks/`/vectores es el estado **correcto** mientras no exista la pasada de OCR del item 35 (no confirmado aún si es un PDF escaneado o simplemente nunca se lanzó `books/process.py` sobre él) — no un bug ni un olvido de este rollout. El rollout de items 62/63 lo excluyó **a propósito** vía `--input-dir` con symlinks solo a los 2 libros ya procesados, precisamente para no mezclar "primera ingesta de un libro nuevo" con "re-proceso de un fix existente". Nota añadida a `Mejoras_pendientes.md` item 35.

### Encargo 6 — Corrección de la etiqueta de fecha de la línea base

`/Volumes/research/metadatos/eval/baseline_2026-07-26/` renombrada a **`baseline_2026-07-25/`** (los CSV que contiene están sellados `20260725`, y la sesión que la generó fue el 25, no el 26). Cabecera de `baseline.md` corregida (`Fecha captura: 2026-07-25`, con nota explicando el error original). Verificado que ningún fichero del repo referenciaba la ruta vieja; solo este mismo informe la citaba (ya corregido en la sección 3.7 arriba).
