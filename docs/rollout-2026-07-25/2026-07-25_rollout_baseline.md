# Línea base pre-reindexado — items 62/63

**Fecha captura:** 2026-07-25 (corregido 2026-07-25: la carpeta y esta cabecera decían "2026-07-26" por error — los CSV que genera este mismo documento están sellados `20260725`, y coinciden con la fecha real de la sesión) · **Repo:** `/Users/martinramirez/proyectos/research_agent`
**Git HEAD:** `afa7b60162e0a51a1bc413be9f198bd828c77d20` (rama `main`, `git status --short` limpio, sin cambios sin commitear)
**Python:** `/Users/martinramirez/venvs/rag_papers/bin/python3`
**Tarea:** verificación de solo lectura. Nada modificado en el repo ni en `categorias/`.

---

## a) P1 — ¿El golden referencia `chunk_id`?

**Respuesta: NO. Los dos golden sets existentes solo referencian `paper_id` (a través de `relevant_paper_ids`), nunca un identificador de chunk. Un re-chunk NO invalida el golden.**

Evidencia ejecutada:

```
$ ls /Volumes/research/metadatos/eval/golden_*.jsonl
golden_anoxic_biogas_biodesulfurization.jsonl       (4 registros)
golden_biogas_upgrading_biomethanation.jsonl        (6 registros)
```
Solo existen estos 2 golden sets — confirma el supuesto del encargo (no hay golden para las otras 6 categorías).

Esquema real (unión de claves sobre TODOS los registros de ambos ficheros):
```
{'answer', 'question', 'relevant_paper_ids'}
```
Ningún registro contiene `chunk_id`, `chunk_index`, `section_part`, ni ningún otro campo con "chunk" en el nombre (grep programático sobre las claves, 0 coincidencias en los 10 registros totales).

Ejemplo real (primer registro, anoxic):
```json
{
  "question": "¿Cuál es el rango de pH óptimo para la biodesulfuración anóxica de biogás?",
  "answer": "El rango de pH óptimo se sitúa entre 6.5 y 8.0...",
  "relevant_paper_ids": ["2015_almenglo_modeling_control_strategies_anoxic_biotrickling_filtration_biogas_purification", "2019_khanongnuch_h2s_removal_microbial_community_composition_anoxic_biotrickling_filter", "2014_fernandez_biogas_biodesulfurization_anoxic_biotrickling_filter_packed_open_por..."]
}
```

`paper_id` se deriva del nombre de fichero (vía `safe_slug`), no del contenido trocedado — sobrevive intacto a un re-chunk. `run_eval.py::retrieve_paper_ids` (líneas 92-116) también trabaja exclusivamente a nivel de `paper_id` (deduplica por `pid`, nunca compara `chunk_id`). **No hace falta re-anclar nada del golden antes de reindexar.**

Matiz para más adelante (ya anotado en `Mejoras_pendientes.md` item 35, sección "Auditoría de chunks 2026-07-25"): si en el futuro se anota el golden a nivel de chunk (en vez de paper), eso SÍ habría que hacerlo **después** del reindexado, no antes, para no repetir el mismo problema. Hoy no aplica.

---

## b) P2 — ¿El filtro por sección se come las tablas?

**Respuesta: Escenario (i) — sin selección no se filtra nada (pasan todos los chunks, incluidos los `table`); "table" es siempre seleccionable en las 4 vías. La pérdida solo puede ocurrir si el usuario filtra activamente y no marca "table". No hay pérdida sistemática.**

Evidencia ejecutada (`passes_filters` real, importado desde `utils.retrieval`, con dos dicts de chunk construidos a mano):

```
--- sin seleccion (sections=None, como hacen los 4 callers via "sections=allowed_sections or None") ---
chunk results, sections=None : True
chunk table,   sections=None : True

--- sin seleccion, pasando literalmente el set vacio (sin el "or None" de los callers) ---
chunk results, sections=set() : True
chunk table,   sections=set() : True

--- usuario selecciona ["results"] (table NO incluida) ---
chunk results, sections={"results"} : True
chunk table,   sections={"results"} : False

--- usuario selecciona ["results","table"] (table SI incluida) ---
chunk results, sections={"results","table"} : True
chunk table,   sections={"results","table"} : True
```

Confirma la lectura de código del PASO 0 (`retrieval.py:90`, `if sections and m.get("section_canonical") not in sections: return False` — el `and` hace que una lista/set vacío nunca entre en la rama de exclusión).

Cableado en los 4 sitios (confirmado en PASO 0, no repetido aquí): `2_RAG.py:696-701` y `7_Revision.py:190-195` ofrecen `st.multiselect(options=CANONICAL_SECTIONS, default=[])` — `CANONICAL_SECTIONS` incluye `"table"` explícitamente y el `default=[]` es justamente el caso "no-filtro". `8_query_rag.py --sections` y el YAML de `run_rag_batch.py` son texto libre, sin restricción ni siquiera implícita.

**Conclusión:** el ítem 43 ("¿el filtro por sección de la UI descarta todos los chunks de tabla?") queda **cerrado con evidencia ejecutada: NO**. La única forma de perder chunks de tabla vía este filtro es que el usuario los excluya activamente — comportamiento esperado de un filtro, no un bug.

---

## c) P3 — ¿Cuántos chunks de portada están realmente vacíos de contenido?

**Criterio reproducible** (script `p3_classify_portadas.py`, detalle completo en `p3_portadas_detalle.json` en esta carpeta):
1. Si el chunk NO contiene una línea `**Authors:**...` → **OTROS** (no encaja en el patrón de portada esperado).
2. Si la contiene: se eliminan las líneas `**Authors:**...` y `**Year...**`/`**DOI...**` (regex multilínea), se colapsan saltos de línea sobrantes y se mide la longitud del texto restante.
3. `< 200 caracteres` de prosa restante → **SOLO_METADATA**. `>= 200` → **MIXTO**.

### Tabla por categoría (chunk_index=1, las 8 categorías)

| categoría | SOLO_METADATA | MIXTO | OTROS | total |
|---|---:|---:|---:|---:|
| biological_gas_odor_treatment | 8 | 0 | 0 | 8 |
| anoxic_biogas_biodesulfurization | 85 | 1 | 1 | 87 |
| bioplastics_microplastics | 366 | 4 | 3 | 373 |
| biogas_upgrading_biomethanation | 337 | 4 | 1 | 342 |
| microalgae | 4 | 0 | 0 | 4 |
| single_cell_protein | 1 | 0 | 0 | 1 |
| advanced_oxidation_processes | 2 | 0 | 0 | 2 |
| bioleaching_critical_materials | 6 | 0 | 0 | 6 |
| **TOTAL** | **809** | **9** | **5** | **823** |

### Cruce SOLO_METADATA/MIXTO/OTROS × `section_canonical` (agregado, 8 categorías)

| bucket | section_canonical | n |
|---|---|---:|
| SOLO_METADATA | other | 598 |
| SOLO_METADATA | results | 133 |
| SOLO_METADATA | methods | 65 |
| SOLO_METADATA | conclusion | 13 |
| MIXTO | other | 5 |
| MIXTO | results | 3 |
| MIXTO | methods | 1 |
| OTROS | other | 3 |
| OTROS | abstract | 2 |

### El número que decide el ítem 62 — "cota superior" convertida en número real

De los **215** chunks `chunk_index=1` cuya `section_canonical` NO es `other`/`abstract` (el proxy original del informe de auditoría, "31 de 87" pero ahora medido en las 8 categorías):

| bucket | n | % |
|---|---:|---:|
| SOLO_METADATA | 211 | 98,1% |
| MIXTO | 4 | 1,9% |
| OTROS | 0 | 0% |

Por categoría (solo las que tienen algún caso):
```
biological_gas_odor_treatment                 {SOLO_METADATA: 2}
anoxic_biogas_biodesulfurization              {SOLO_METADATA: 31}   ← el "31/87" del informe: los 31 SON, sin excepción, SOLO_METADATA
bioplastics_microplastics                     {SOLO_METADATA: 101, MIXTO: 2}
biogas_upgrading_biomethanation               {SOLO_METADATA: 73, MIXTO: 2}
microalgae                                     {SOLO_METADATA: 2}
bioleaching_critical_materials                 {SOLO_METADATA: 2}
```

Los 4 MIXTO que escapan a la regla (contienen prosa real pese a estar mal clasificados):
- `bioplastics_microplastics / 2024_carnevale_miino_...` (methods, 1778 chars de prosa)
- `bioplastics_microplastics / 2025_wang_understanding_removal_microplastics...` (results, 993 chars)
- `biogas_upgrading_biomethanation / 2025_jusoh_hydrogen_sulfide_removal_biogas...` (results, 1750 chars)
- `biogas_upgrading_biomethanation / 2025_liu_anchoring_fe_cu_bimetallic_oxides...` (results, 3985 chars)

**Conclusión para el ítem 62:** la cota superior del informe original (31/87 en anoxic) **se confirma exacta y además se generaliza**: en las 8 categorías, 211 de 215 chunks "mal clasificados" (98,1%) son de verdad portadas vacías de contenido (solo autores+año+DOI), no un artefacto de medición. Los 4 casos MIXTO son candidatos a **reetiquetar** en vez de excluir (tienen contenido real, solo la etiqueta de sección está mal); los 211 restantes son candidatos a **excluir del índice** o fusionar con el chunk siguiente — decisión que corresponde al diseño del fix del ítem 62, no a esta verificación.

También aparece el contraejemplo ya anotado en el propio `Mejoras_pendientes.md` (item 62): `2018_zheng` (chunk_index=1, `section_canonical="other"` — NO cuenta en los 215 — pero con 4660 chars de prosa real, MIXTO). Confirma que "other" en sí no es garantía de vacío ni "methods/results" garantía de contenido; el criterio de 3 cubos es el que hay que mirar, no solo `section_canonical`.

### Ejemplos por cubo (3 de cada, primeros 200 chars del texto ORIGINAL)

**SOLO_METADATA:**
```
[biological_gas_odor_treatment] 1999_acu_a_microbiological_kinetic_aspects_biofilter_removal_toluene_waste_gases
  section_canonical=results  prose_len_tras_strip=0
  '**Authors:** Maria Elena; Acun ˜a; Fermin Pe ´rez; Richard Auria; Sergio Revah\n\n**DOI: 10.1002/(SICI)1097-0290(19990420)63:2<175::AID-BIT6>3.0.CO;2-G**'

[biological_gas_odor_treatment] 2003_kan_development_foamed_emulsion_bioreactor_air_pollution_control
  section_canonical=other  prose_len_tras_strip=0
  '**Authors:** Eunsung Kan; Marc A Deshusses\n\n**Year: 2003 | DOI: 10.1002/bit.10767**'

[biological_gas_odor_treatment] 2004_kanagawa_biological_treatment_ammonia_gas_high_loading
  section_canonical=other  prose_len_tras_strip=0
  '**Authors:** T Kanagawa; H W Qi; T Okubo; N Tokura'
```

**MIXTO:**
```
[anoxic_biogas_biodesulfurization] 2018_zheng_mercury_isotope_signatures_record_photic_zone_euxinia_mesoproterozoic
  section_canonical=other  prose_len_tras_strip=4660
  '**Authors:** Wang Zheng; Geoffrey J Gilleaudeau; Linda C Kah; Ariel D Anbar\n\n**Year: 2018 | DOI: 10.1073/pnas.1721733115**\n\nPhotic zone euxinia (PZE) is a condition where anoxic, H 2 S-rich waters occ'

[bioplastics_microplastics] 2020_masia_bioremediation_promising_strategy_microplastics_removal_wastewater_treatment_plants
  section_canonical=other  prose_len_tras_strip=1005
  '**Authors:** Paula Masiá; Daniel Sol; Alba Ardura; Amanda Laca; Yaisel J Borrell; Eduardo Dopico; Adriana Laca; Gonzalo Machado-Schiaffino; Mario Díaz; Eva Garcia-Vazquez\n\n**Year: 2020 | DOI: 10.1016/'

[bioplastics_microplastics] 2024_carnevale_miino_microplastics_removal_wastewater_treatment_plants_review_different_approaches
  section_canonical=methods  prose_len_tras_strip=1778
  '**Authors:** Marco Carnevale Miino; Silvia Galafassi; Rosa Zullo; Vincenzo Torretta; Cristina Rada\n\n**Year: 2024 | DOI: 10.1016/j.scitotenv.2024.172675**\n\n• More than 65 % of microplastics (MPs) are a'
```

**OTROS:**
```
[anoxic_biogas_biodesulfurization] 2004_shikano_volcanic_heat_flux_short_term_holomixis_summer_stratification
  section_canonical=other  prose_len_tras_strip=4340
  '**DOI: 10.4319/lo.2004.49.6.2287**\n\nVolcanic heat flux and short-term holomixis during the summer stratification period in a crater lake Abstract-We sampled Lake Katanuma from 1998 to 2002 at weekly o'
  (sin línea "**Authors:**" — el DOI aparece pero no autores; entra en OTROS por la regla 1)

[bioplastics_microplastics] 2024_oecd_policy_scenarios_eliminating_plastic_pollution_2040
  section_canonical=abstract  prose_len_tras_strip=1133
  'Translations -you must cite the original work, identify changes to the original and add the following text: In the event of any discrepancy between the original work and the translation, only the text'
  (informe/policy paper sin bloque de autores extraído por GROBID)

[bioplastics_microplastics] 2024_zhang_advances_environmental_degradation_impact_degradable_plastics
  section_canonical=other  prose_len_tras_strip=1480
  '**DOI: 10.1360/TB-2024-0824**\n\nPHA和聚乳酸(polylactic acid, PLA)等...' (texto en chino, revista china)
```

Detalle completo (823 registros, uno por chunk_index=1 de las 8 categorías) en `p3_portadas_detalle.json`, en esta misma carpeta.

---

## PASO 2 — Línea base de evaluación

### Comandos ejecutados (literales)

```bash
cd /Users/martinramirez/proyectos/research_agent/scripts
/Users/martinramirez/venvs/rag_papers/bin/python3 run_eval.py --category anoxic_biogas_biodesulfurization
/Users/martinramirez/venvs/rag_papers/bin/python3 run_eval.py --category anoxic_biogas_biodesulfurization --hybrid
/Users/martinramirez/venvs/rag_papers/bin/python3 run_eval.py --category biogas_upgrading_biomethanation
/Users/martinramirez/venvs/rag_papers/bin/python3 run_eval.py --category biogas_upgrading_biomethanation --hybrid
```

Ningún flag adicional — `--base`, `--phase`, `--k`, `--eval-dir` quedan en sus defaults de código (`/Volumes/research/categorias`, `all`, `8`, `<base>/../metadatos/eval`). `--hybrid` es el único flag variado entre pasadas, tal como pide el encargo.

Salida cruda de cada ejecución (stdout+stderr, vía `tee`) en esta carpeta:
- `run_denso_anoxic_biogas_biodesulfurization.txt`
- `run_hibrido_anoxic_biogas_biodesulfurization.txt`
- `run_denso_biogas_upgrading_biomethanation.txt`
- `run_hibrido_biogas_upgrading_biomethanation.txt`

El propio `run_eval.py` escribe además su CSV de detalle por pregunta en la ruta por defecto (`/Volumes/research/metadatos/eval/`, NO en esta carpeta — es el comportamiento estándar del script sin `--eval-dir`, no lo he sobreescrito):
- `results_anoxic_biogas_biodesulfurization_20260725_124511.csv` (denso)
- `results_anoxic_biogas_biodesulfurization_20260725_124524.csv` (híbrido)
- `results_biogas_upgrading_biomethanation_20260725_124528.csv` (denso)
- `results_biogas_upgrading_biomethanation_20260725_124537.csv` (híbrido)

### Git / entorno

```
git rev-parse HEAD        : afa7b60162e0a51a1bc413be9f198bd828c77d20
git status --short         : (vacío — working tree limpio)
rama                        : main
```

### Estadísticas de corpus por categoría

| Categoría | n_chunks metadata.jsonl | ntotal FAISS | n_chunks table | n_papers | dim FAISS | modelo |
|---|---:|---:|---:|---:|---:|---|
| anoxic_biogas_biodesulfurization | 1741 | 1741 | 165 | 87 | 1024 | bge-m3 |
| biogas_upgrading_biomethanation | 8276 | 8276 | 919 | 342 | 1024 | bge-m3 |

`ntotal == n_chunks` se cumple en ambas categorías hoy (invariante del ítem 55b, verificado antes del reindexado).

`config.json` de cada índice (tal cual, sin interpretar):
```json
anoxic:   {"project": "anoxic_biogas_biodesulfurization", "phase": "all", "model": "bge-m3", "chunks": 1741, "dimension": 1024}
upgrading:{"project": "biogas_upgrading_biomethanation", "phase": "all", "model": "bge-m3", "chunks": 8276, "dimension": 1024}
```

### Métricas (tal cual las reporta `run_eval.py`)

| Categoría | Modo | Hit@8 | MRR | n preguntas |
|---|---|---:|---:|---:|
| anoxic_biogas_biodesulfurization | denso (default) | 0.500 (2/4) | 0.098 | 4 |
| anoxic_biogas_biodesulfurization | híbrido | 0.250 (1/4) | 0.062 | 4 |
| biogas_upgrading_biomethanation | denso (default) | 1.000 (6/6) | 0.708 | 6 |
| biogas_upgrading_biomethanation | híbrido | 0.833 (5/6) | 0.722 | 6 |

Detalle por pregunta (posición del primer hit) en los `.txt`/`.csv` de esta carpeta.

**Nota de contexto (no verificación, solo lectura del backlog):** `Mejoras_pendientes.md` item 37 registraba el 2026-06-20 "Hit@8 denso 0.50, híbrido 0.25" para anoxic y "denso 1.0/MRR 0.889, híbrido 1.0/0.857" para upgrading. Hit@8 coincide en ambas categorías; el MRR de upgrading difiere (0.708/0.722 hoy vs 0.889/0.857 entonces) — el corpus ha crecido desde entonces (ingesta semanal activa sobre esta categoría, ver `run_weekly_scopus.py` en `WEEKLY_CATEGORIES`), así que un mismo Hit@8=1.0 puede moverse de posición dentro del top-8 sin cambiar el hit. Esto es exactamente el tipo de deriva de corpus que esta línea base debe permitir distinguir de un cambio causado por el reindexado del ítem 62/63.

---

## RIESGOS DEL REINDEXADO

1. **CRÍTICO — modo incremental de `5_build_embeddings.py` deja el índice desincronizado si no se usa `--force`.** Confirmado en el propio docstring del script (líneas 66-68): *"El modo incremental detecta papers nuevos por paper_id. Si se regeneraron [chunks de papers ya indexados], usa --force para que queden incluidos correctamente."* El flujo del fix es: `3_process_corpus.py --force` (regenera `chunks/*.jsonl` con las filas unidas por `\n\n` y sin el leak de `canonical_section()` sobre el título) → `5_build_embeddings.py`. Si este segundo paso se ejecuta **sin** `--force`, el `paper_id` de cada paper ya existe en `indexed_papers.json` y el script los salta silenciosamente — el índice FAISS y `metadata.jsonl` seguirían representando el chunking VIEJO (con el bug), mientras `chunks/*.jsonl` en disco ya tendría el chunking NUEVO. Es exactamente el tipo de divergencia vector↔texto que preocupa al ítem 55b, pero autoinducida por el propio procedimiento de reindexado si se olvida el flag. **Acción: `--force` obligatorio en ambos pasos, para las 8 categorías.**

2. **Verificar `ntotal == len(metadata.jsonl)` después del reindexado**, para las 8 categorías (hoy se cumple en las 2 medidas, ver tabla arriba). Es barato de comprobar y es justo el invariante que el ítem 55b pide blindar; esta línea base dejó registrado el valor "antes" para las 2 categorías con golden, pero conviene medirlo en las 8 tras el reindexado, no solo en las 2 evaluadas.

3. **`corpus_manifest.json` por categoría quedará desactualizado** (n_chunks, `faiss_stale`, `git_commit`) hasta que se regenere explícitamente — no es una pérdida de datos, pero cualquier vista de salud del corpus (portada Streamlit) mostrará cifras viejas si no se relanza `utils/corpus_manifest.py` tras el reindexado.

4. **Los golden sets, `indexed_papers.json`, las notas guardadas en `notas_rag/*.md` y los logs `rag_usage_*.jsonl`/`rag_queries_*.jsonl` NO referencian identificadores de chunk** (verificado: `indexed_papers.json` solo tiene `{"paper_ids": [...], "model": ...}`; las notas citan `paper_id`; `rag_queries_*.jsonl` guarda `retrieved_papers`, no chunks; `rag_usage_*.jsonl` es solo coste/tokens). **Nada de esto se rompe estructuralmente por el reindexado.** El único identificador de chunk persistente en todo el repo es `chunk_hash` — pero es exclusivo del pipeline de **libros** (`scripts/books/process.py`), no del pipeline de artículos que se va a reindexar; no aplica a las 8 categorías de este encargo.

5. **Los CSV de resultados históricos en `/Volumes/research/metadatos/eval/results_*_20260620_*.csv` dejan de ser comparables directamente** contra una nueva corrida tras el reindexado — no porque se rompan, sino porque miden un corpus con menos papers (la ingesta semanal ha seguido añadiendo papers a `anoxic`/`upgrading` desde junio) y el chunking viejo. Cualquier comparación "antes/después" del ítem 62/63 debe usar como "antes" los 4 ficheros `.txt`/`.csv` de ESTA línea base (2026-07-25), no los de junio, para no mezclar dos variables (deriva de corpus + fix de chunking) en la misma comparación.

6. **El reindexado NO toca la pureza del corpus (ítem 64).** Los papers fuera de dominio detectados en la auditoría de chunks (`1989_anderson`, `1997_gervais`, `2018_zheng`, discutiblemente `1998_searcy`) seguirán en el corpus después de re-trocear y re-indexar — el fix de los ítems 62/63 opera sobre CÓMO se trocea/clasifica el texto, no sobre QUÉ PDFs están incluidos. Si se quiere resolver el ítem 64 antes de anotar el golden a nivel de chunk (como recomienda el propio backlog), es una acción de cuarentena aparte, no incluida en este reindexado.

7. **Riesgo bajo, mencionado por completitud:** el "truncado reactivo" de `embed_texts` (P2 de la auditoría Kimi, anclado en el ítem 63) podría seguir afectando a otras tablas grandes del corpus que no sean `2023_almenglo #34` — el fix de unir filas con `\n\n` reduce la probabilidad de que una tabla entera se trate como un solo párrafo gigante, pero no la elimina para tablas que de verdad superen `MAX_EMBED_CHARS` con filas ya bien delimitadas. No es un riesgo del reindexado en sí, pero conviene tenerlo presente al revisar los resultados post-reindexado si aparecen truncados nuevos.
