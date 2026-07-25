# Auditoría de calidad de chunks vs PDF original
**Categoría:** anoxic_biogas_biodesulfurization · **Fecha:** 2026-07-25 · **Semilla:** 20260725
**Corpus:** 1741 chunks, 87 papers (verificado) · **Muestra auditada:** 16 chunks
**Repo scripts:** `/Users/martinramirez/proyectos/research_agent` (nota: `/Volumes/Disco` indicado originalmente no era accesible; el repo real está en disco local, los datos sí están en `/Volumes/research`)
**Salida:** `/Volumes/research/metadatos/auditoria_chunks/2026-07-25/` (`muestra.json`, `localizacion.json`, `paginas/*.png`, este informe)

Todo el proceso ha sido de solo lectura sobre el repo y sobre `categorias/`; no se ha modificado ningún fichero fuente.

---

## PASO 3 — Fichas de comparación, una por chunk

Nota general aplicable a casi todas las fichas: el pipeline **aplana sistemáticamente subíndices y superíndices** (H₂S → "H 2 S", SO₄²⁻ → "SO 4 2-", m⁻³h⁻¹ → "m -3 h -1", exponentes de página/nota → espacio+dígito). Es un patrón de GROBID en la extracción de texto de PDF, visible en prácticamente todos los chunks con fórmulas o unidades. Lo documento aquí una vez y en cada ficha solo señalo cuándo se desvía de este patrón "leve pero constante" hacia algo más grave (pérdida total del carácter, no solo de su formato).

---

### 1. `2023_almenglo_recent_advances_biological_technologies_anoxic_biogas_desulfurization#34`
**Criterio:** table_longest (7993 chars) · **Página:** 4 · **Localización:** confirmada visualmente

1. **Contenido completo:** Sí, cubre toda la Tabla 1 visible en página 4 (desde Soreanu et al. 2008a hasta la fila cortada "Other c" antes de "(continued on next page)").
2. **Números:** La PRIMERA fila coincide exacta: PDF `9.3 (100%) | 16.5 (66%) | 10.2–72 | 6–7` = chunk `9.3 (100%) | 16.5 (66%) | 10.2-72 | 6-7`. Pero a partir de la fila de Soreanu(2010)/Baspinar(2011)/Chinalia(2012)/Montebello(2012), los números se mezclan (ver punto 3).
3. **Tablas — filas/columnas:** **CRÍTICO, confirmado.** El chunk contiene: `- Type: BTF Other a HFBR BTF | Scale [Volume]: Laboratory [12 L] Pilot [2.4 m 3 ] Pilot [26.5 L] Laboratory | [H 2 S] IN [ppm V ]: 2000-4000 30000-35000 20000 426-2594 | ...`. En el PDF estas son **4 filas independientes** (Soreanu 2010, Baspinar 2011, Chinalia 2012, Montebello 2012), cada una con su propio Type/Scale/pH/REF. El chunk las concatena bajo una sola etiqueta de columna, perdiendo la asociación fila↔valor. Ejemplo peor: `[H 2 S] IN [ppm V ]: -1000-1500` en otra fila fusionada — eso es la concatenación literal de "–" (sin dato, fila Soreanu 2008c) + "1000-1500" (fila Deng 2009), que parece un único rango válido pero son dos estudios distintos.
4. **Fórmulas/subíndices:** legibles pero aplanados (patrón general).
5. **Contaminación:** ninguna (no hay cabeceras/pies de página ni texto ajeno).
6. **Guionado:** no aplica (no hay palabras partidas).
7. **Fronteras:** el chunk corta literalmente a mitad de fila al final: `... pH: 6-8 7.4 7.4-8.2` (se corta sin cerrar la última fila, coincide con el límite de `MAX_EMBED_CHARS=8000`).

**HALLAZGO NO ANTICIPADO (root cause, confirmado por código):** `_split_to_max_chars()` (`3_process_corpus.py:489-521`) solo reconoce párrafos separados por `\n\n`. `extract_tables_md()` (líneas 303-363, rama sin columna "Exp.") une las filas de una tabla con un solo `\n` — es decir, TODA la tabla es UN SOLO "párrafo" a efectos del splitter. Cuando ese párrafo supera `MAX_EMBED_CHARS` (8000), el código cae a la rama de emergencia por palabras (líneas 507-513: `para.split()` + `" ".join`), que **descarta todos los saltos de línea internos** y reconstruye el texto por palabras sueltas — destruyendo el límite entre filas. Esto es 100% reproducible: cualquier tabla sin columna "Exp." cuyo bloque de filas supere 8000 caracteres sufre esto. **Reparable en nuestra capa** (unir filas con `\n\n` en vez de `\n` en `extract_tables_md`, o hacer que `_split_to_max_chars` respete `\n` antes de caer a palabras).

**Severidad máxima: CRÍTICO**

---

### 2. `2023_almenglo_recent_advances_biological_technologies_anoxic_biogas_desulfurization#33`
**Criterio:** table_shortest (107 chars) · **Página:** 4 (misma tabla que #34) · **Localización:** confirmada

1. **Contenido:** Es literalmente `### Table 1\n\n*Main operational parameters and performance in studies for anoxic desulfurization of biogas.*` — coincide EXACTO con el título y el pie de tabla del PDF. Cero filas de datos.
2–6. No aplica (no hay datos numéricos ni prosa que comparar).
7. **Fronteras:** este chunk es exactamente "cabecera + caption" de la tabla, separado del resto por el mismo mecanismo descrito en la ficha 1 (el caption es un párrafo corto que cabe entero antes de que el bloque de filas dispare el fallback). Es la contrapartida exacta del chunk #34.

**HALLAZGO NO ANTICIPADO:** este chunk es 100% fiel al PDF pero **no aporta ninguna información recuperable por RAG** (ni una cifra, ni un valor). Es un "chunk vacío de contenido útil" que ocupa un slot de embedding. Mismo patrón que se repite en los bloques de portada (ver fichas 9 y 11).

**Severidad máxima: MEDIO** (fiel pero sin valor informativo — no es un error de exactitud, es un problema de utilidad)

---

### 3. `2023_lenis_implementation_pilot_scale_biotrickling_filtration_process_biogas_desulfurization_anoxic#25`
**Criterio:** table_median (972 chars) · **Página:** 6 · **Localización:** confirmada

1. **Contenido:** Casi completo. Las 8 filas de "Table 2. Potassium nitrate dosage regime." están todas presentes y en orden. **Falta la nota al pie "* new digestate"** que en el PDF explica el asterisco de la última fila ("Continuously *"). El chunk conserva el asterisco literal pero no su significado.
2. **Números:** Verificados fila a fila contra el PDF — **coinciden exactamente**, incluidas las listas largas de días (ej. "99, 110, 117, 120, 122, 124, 127, 131, 135, 138, 142, 144, 149") y cantidades KNO₃ ("50, 500, 50, 50, 200, 50, 700, 500, 500, 500, 500, 250, 700"). Esta tabla NO sufre el bug de la ficha 1 porque es pequeña (972 < 8000 chars) y nunca entra en la rama de emergencia.
3. **Filas/columnas:** correctas, una bullet por fila, sin mezclas.
4. **Fórmulas:** "KNO 3" aplanado (patrón general), sin pérdida de significado.
5. **Contaminación:** ninguna.
6. **Guionado:** no aplica.
7. **Fronteras:** limpias, la tabla completa cabe en un chunk.

**HALLAZGO NO ANTICIPADO:** el título del chunk es `### Table 2 .` — con un espacio espurio antes del punto. Aparece también en la ficha 4. Confirmado sistemático: **58 de 165 chunks de tabla del corpus completo (35%)** tienen este patrón `Table N .` con espacio antes del punto.

**Severidad máxima: ALTO** (pérdida de la nota al pie, que cambia la interpretabilidad de un dato de la tabla)

---

### 4. `2021_valdebenito_rolack_markers_comparison_performances_anoxic_biotrickling_filters_biogas_desulphurisation#46`
**Criterio:** table_from_paper_with_4_tables · **Página:** 7 · **Localización:** confirmada

1. **Contenido:** **Faltan 3 columnas enteras.** El PDF muestra para la fila "(18) Lab scale": BTF Scale, (H₂S), LRcrit, ECcrit, REcrit, EBRT, ECmax, REmax, EBRT, pH, T, [NO₃⁻], TLF/TLV, **Inoculum/Packing Material** ("Community of microorganisms from a sample of anaerobic sludge of a STP, selected in the BTF/strips of PVC, PET, PTFE (Teflon), OPU"), **Microbial Analysis** ("Biomass was determined as weight of protein by weight of dry support material"), **Ref.** ("[30]"). El chunk termina en "TLF/TLV at EC crit ... 0.5/11" — las tres últimas columnas están completamente ausentes.
2. **Números:** los 12 valores numéricos presentes coinciden exactamente (1537-2127, 84.4, 84.4, 95.7, 1.6, ND, ND, ND, 7, 35, 0.25-8, 0.5/11).
3. **Filas/columnas:** la única fila de datos está bien formada para las columnas que sí aparecen.
4-6. No aplica más allá de lo anterior.
7. **Fronteras:** el chunk es la tabla entera (2 filas: cabecera+dato), no hay corte a media fila.

**HALLAZGO NO ANTICIPADO (verificado en el TEI XML, no es un bug de nuestra capa):** inspeccioné `tei/2021_valdebenito....tei.xml` directamente. GROBID partió lo que en el PDF es una sola "Tabla 2" en **tres `<figure type="table">` separadas**: `tab_0` (1 fila, solo cabecera, descartada por nuestro código porque `len(rows)<2`), `tab_1` (33 filas, la tabla completa "principal"), y `tab_2` (2 filas: cabecera + exactamente la fila que aparece en este chunk). Crucialmente, **en `tab_2` los propios `<cell>` de GROBID para "Inoculum/Packing Material", "Microbial Analysis" y "Ref." ya vienen vacíos** (`''`) en el XML — no es una pérdida de nuestro pipeline, es que GROBID no logró asociar ese texto (probablemente multilínea, envuelto) con la fila. Además, la fragmentación en 3 figuras duplicadas/parciales para la misma tabla visual es en sí misma un problema: puede generar chunks redundantes o incoherentes entre sí en el corpus (no verificado si `tab_1` genera chunks que solapan con `tab_2`, pero es plausible).
**Techo de GROBID** para la pérdida de columnas y la fragmentación en sí; parcialmente reparable en nuestra capa si quisiéramos deduplicar/fusionar figuras con el mismo `head` antes de trocear.

**Severidad máxima: CRÍTICO** (pérdida silenciosa de 3 columnas completas de descripción metodológica, sin ningún indicador de truncamiento)

---

### 5. `1989_anderson_uranium_deposition_saanich_inlet_sediments_vancouver_island#12`
**Criterio:** other · **Páginas:** 7-8 · **Localización:** confirmada (cruza página)

1. **Contenido:** completo, las 3 secciones/párrafos del chunk aparecen íntegras en el PDF (párrafo 1 y 2 en columna derecha p.7, párrafo 3 en columna izquierda p.8 arriba). Correcta decisión de renderizar ambas páginas.
2. **Números — CRÍTICO, dos casos confirmados en el mismo chunk:**
   - PDF: `~0.2 dpm 238U l⁻¹ (~10⁻⁹ molar)` → chunk: `-0.2 dpm 238U 1-l (_ 10m9 molar)`. La virgulilla "~" (aproximadamente) se convirtió en "-" (podría leerse como negativo), "l⁻¹" se invirtió a "1-l", y **el exponente "10⁻⁹" se corrompió a "10m9"** — el signo menos del exponente se sustituyó por la letra "m", cambiando el valor numérico representado.
   - PDF: `100 mg l⁻¹` → chunk: `100 mg 1-l` — mismo patrón de inversión dígito/letra.
3. No aplica (no es tabla).
4. **Fórmulas/subíndices:** PDF `CO₃²⁻ ions` → chunk `CO:-ions` — la fórmula del ion carbonato queda **destrozada** (pierde el "3" y el superíndice de carga, sustituidos por un colon suelto, y sin espacio a la palabra siguiente).
5. **Contaminación:** ninguna — verificado que ni cabecera ("Uranium concentration of organic sediment / 2211"), ni pie, ni el bloque de REFERENCES de la página 8 se colaron en el chunk (el corte de sección es correcto, justo antes de "CONCLUSIONS").
6. **Guionado:** correcto — el propio PDF ya trae "LANG-MUIR, 1978" partido con guion en el original (no es un artefacto nuestro).
7. **Fronteras:** el chunk empieza a media frase ("existing solid phases. The solubility of U...") — es el comportamiento esperado del chunker por palabras en párrafos largos, no un bug.

**HALLAZGO NO ANTICIPADO:** el patrón "~" → "-" y "10⁻⁹" → "10m9" sugiere un problema de codificación de fuente/glifo específico de este PDF de 1989 (probablemente escaneado/OCR), no visto en los papers más modernos de la muestra. **No reparable en nuestra capa ni en GROBID** — es un defecto que viene del propio texto extraíble del PDF fuente.

**Severidad máxima: CRÍTICO** (el exponente corrompido cambia el valor numérico representado)

---

### 6. `2025_elboghdady_microbial_acclimation_thermophilic_anaerobic_digestate_enhances_biogas_production#17`
**Criterio:** other · **Página:** 8 · **Localización:** confirmada

1. **Contenido:** completo — los 3 párrafos coinciden exactos con la sección "3.3. PLA degradation vs. Microbial acclimatation" del PDF, incluida la última frase de la página ("...thus increasing process profitability.").
2. **Números:** verificados — "90 %", "54 and 40 days", "33-38 and 27-32 days" — todos coinciden exactamente.
3. No aplica.
4. **Subíndices:** solo el patrón general (t₉₀ → "t 90"), sin pérdida de dígitos.
5. **Contaminación:** ninguna.
6. **Guionado:** correcto ("mono-and codigestion" en el chunk reproduce fielmente un guion sin espacio que también está así en el PDF — no es un artefacto).
7. **Fronteras:** limpias — el chunk arranca en el inicio real de un párrafo y termina en el cierre de la sección, justo donde acaba la página.

**HALLAZGO NO ANTICIPADO:** ninguno más allá del patrón general.

**Severidad máxima: BAJO** (chunk correcto; único defecto es el aplanado sistemático de subíndices)

---

### 7. `2018_zheng_mercury_isotope_signatures_record_photic_zone_euxinia_mesoproterozoic#1`
**Criterio:** other (chunk_index=1, portada+abstract+inicio cuerpo) · **Página:** 1 · **Localización:** confirmada

1. **Contenido:** el abstract está completo y es una copia exacta del bloque en negrita del PDF. El inicio del cuerpo también coincide.
2. **Números:** DOI `10.1073/pnas.1721733115` coincide exacto con el pie de página del PDF.
3. No aplica.
4. **Subíndices:** patrón general (H₂S → "H 2 S").
5. **Contaminación:** ninguna — no se coló el bloque "Significance" (recuadro azul lateral) ni "Author contributions" ni el pie de página.
6. **Guionado:** no aplica.
7. **Fronteras:** correcto, el chunk corta limpiamente al final de un párrafo ("...bound to oxygen-containing", justo donde el texto sigue en la página siguiente, párrafo continuará en el siguiente chunk).

**HALLAZGO NO ANTICIPADO (dos, menores):**
- El nombre chino del autor "(郑旺)" junto a "Wang Zheng" en el PDF se pierde por completo en la lista de autores del chunk (queda solo "Wang Zheng"). Cosmético pero es una pérdida de información real del PDF.
- **"Ocean euxinia..."** en el PDF empieza con una "O" mayúscula decorativa grande (drop cap, típico de PNAS) seguida de "cean euxinia...". El chunk reproduce esto como **"O cean euxinia..."** — con un espacio espurio insertado exactamente donde el drop-cap se extrajo como un bloque de texto separado del resto de la palabra. Es un artefacto de maquetación tipográfica, no visto en los demás chunks de la muestra (los otros papers no usan drop caps), probablemente de baja prevalencia pero completamente reproducible en cualquier artículo con este estilo tipográfico.

**Severidad máxima: BAJO**

---

### 8. `2019_khanongnuch_h2s_removal_microbial_community_composition_anoxic_biotrickling_filter#9`
**Criterio:** methods · **Página:** 4 · **Localización:** confirmada

1. **Contenido:** completo — la sección "2.6. Analytical methods" está íntegra, todas las técnicas analíticas mencionadas (ion chromatography, pH-meter, espectrofotómetro, titulación, GC, detector de gases) coinciden.
2. **Números:** sin cifras experimentales en esta sección (son especificaciones de equipos), nada que verificar más allá de referencias [22]-[24] que coinciden.
3. No aplica.
4. **Fórmulas/subíndices:** PDF `SO₄²⁻ concentrations` → chunk `SO 4 2concentrations` — aquí el defecto es más grave que el patrón general: **el superíndice de carga "²⁻" desaparece por completo (no queda ni rastro) y además se pierde el espacio** antes de "concentrations", quedando "2concentrations" pegado. Es una variante más agresiva del aplanado habitual.
5. **Contaminación:** ninguna.
6. **Guionado:** correcto.
7. **Fronteras:** limpias, sección completa en un chunk.

**Severidad máxima: MEDIO**

---

### 9. `2025_brito_anoxic_desulfurization_biogas_rich_hydrogen_sulfide_feedback_control#1`
**Criterio:** methods (⚠️ ver hallazgo) · **Página:** 1 · **Localización:** confirmada

1. **Contenido:** el chunk es únicamente `**Authors:** J Brito; C Frade-González; F Almenglo; J J González-Cortés; A Valle; M C Durán-Ruiz; M Ramírez` + `**Year: 2025 | DOI: 10.1016/j.biortech.2025.132439**`. Coincide exacto con la portada del PDF (autores y DOI verificados carácter a carácter).
2. **Números:** DOI correcto.
3-6. No aplica — no hay cuerpo de texto ni datos.
7. **Fronteras:** es el chunk_index=1 completo del paper (todo el "preámbulo" antes del primer heading real).

**HALLAZGO NO ANTICIPADO — el más importante de la auditoría, cuantificado contra el corpus completo:** este chunk está etiquetado `section_canonical="methods"`, pero **no contiene absolutamente nada de metodología** — es pura metadata bibliográfica. Causa raíz confirmada en `constants.py:29-32` + `3_process_corpus.py:385-396`: `canonical_section()` compara el **título completo del paper** (que actúa como heading H1, `# {paper_title}`) contra la lista de keywords. El título de este paper contiene la palabra "**Operational**" (de "Operational limits and multi-omics analysis") → matchea la keyword "operational" de la lista de `methods` (`constants.py` / `3_process_corpus.py:376-377`) → todo el bloque de portada hereda `section_canonical="methods"`.
Comprobé la prevalencia real contra los 1741 chunks: **de los 87 chunks `chunk_index=1` (uno por paper), 31 (35.6%) tienen `section_canonical` distinto de "other"/"abstract"** — es decir, más de un tercio de los papers del corpus tienen su bloque de portada mal clasificado como methods/results/etc. porque su título contiene una keyword de sección. Esto significa que **cualquier filtro de RAG por `section_canonical=methods` o `=results` puede devolver chunks vacíos de contenido real** en más de un tercio de los papers.
**Totalmente reparable en nuestra capa**: no aplicar `canonical_section()` al título del paper (nivel 0/preámbulo), o tratar `chunk_index==1` como caso especial.

**Severidad máxima: ALTO** (no corrompe el contenido en sí, pero degrada sistemáticamente la fiabilidad del filtrado por sección en más de un tercio del corpus)

---

### 10. `2018_shihab_removal_ethanethiol_biotrickling_filter_nitrate_electron_acceptor#12`
**Criterio:** results · **Páginas:** 16 (no detectada automáticamente, añadida manualmente), 17, 18 · **Localización:** corregida manualmente durante la auditoría

1. **Contenido:** completo tras añadir la página 16 (mi localización automática solo encontró 17-18 por solapamiento de palabras; el inicio del chunk, con las ecuaciones (1) y (2), está en la página 16, que rendericé aparte tras notar la discrepancia).
2. **Números:** todos los coeficientes estequiométricos verificados exactos contra el PDF: `2.87, 0.87, 0.24, 2.58, 1.32, 0.789` (ec. 1) y `1.34, 1.34, 0.315, 2.578, 0.51, 0.418` (ec. 2), además de `4.6±0.4 a 63.4±2.7 mg/L`, `8.5±1.2 a 96±8.0 g/m³/h`, `54.5 g H2S/m³`, `0.72 y 2.89`, `2 y 4 kg S²⁻/m³.day`, `20 y 14 electrones`, `2 y 8 electrones`, `3500 kJ/C-mole`, `427 y 1157 kJ/C-mole`, `0.34 y 0.63` — **todos coinciden exactamente**, incluidos los símbolos ± que en otros chunks se pierden.
3. No aplica (no es tabla).
4. **Fórmulas — CRÍTICO, confirmado:** la ecuación (1) del PDF, `CH₃CH₂SH + 2.87NO₃⁻ + 0.87H⁺ → SO₄²⁻ + ... (1)`, aparece en el chunk como: `$$\n𝐶𝐻\n$$\n\n3 𝐶𝐻 2 𝑆𝐻 + 2.87𝑁𝑂 3 -+ 0.87𝐻 + → 𝑆𝑂 4 2-+ ...`. El bloque LaTeX `$$...$$` generado por `_extract_div_content` (línea 191-194) contiene ÚNICAMENTE "CH" — GROBID etiquetó solo un fragmento de la fórmula como `<formula>`, y el resto ("3 CH2SH + 2.87NO3-...") quedó como texto de párrafo normal, fuera del bloque matemático, con el "3" (que debería ser subíndice del primer carbono) flotando delante de "CH2SH". La ecuación (2), en el mismo chunk, NO se etiquetó como `<formula>` en absoluto (aparece como texto plano sin `$$`), pero al menos no se fragmentó — solo sufre el aplanado habitual de subíndices.
5. **Contaminación:** ninguna — confirmado que la marca de agua diagonal "ACCEPTED MANUSCRIPT" (el PDF es un manuscrito aceptado, no la maquetación final) **no se coló** en el texto extraído en ningún punto del chunk, a pesar de cruzar 3 páginas todas con la marca de agua.
6. **Guionado:** no aplica.
7. **Fronteras:** limpias, el chunk termina justo antes del heading "3.6. Metabolic products...".

**Severidad máxima: CRÍTICO** (fórmula química partida en dos fragmentos inconexos con un bloque `$$` mal formado)

---

### 11. `2014_mora_kinetic_stoichiometric_characterization_anoxic_sulfide_oxidation_so_nr#1`
**Criterio:** results (⚠️ ver hallazgo, mismo patrón que ficha 9) · **Página:** 1 · **Localización:** confirmada

1. **Contenido:** portada del paper — autores y DOI.
2. **Números:** DOI `10.1007/s00253-014-5688-5` correcto.
3-7. No aplica al ser solo metadata.

**HALLAZGO NO ANTICIPADO (dos, distintos):**
- **Mismo bug de clasificación que la ficha 9**: el título contiene "characterization" → keyword de la lista `results` → chunk_index=1 etiquetado `results` sin contener resultados. Confirma que el bug no es específico de un paper, ya lo cuantifiqué arriba (31/87).
- **Lista de autores corrupta:** el chunk dice `**Authors:** Mabel Mora; Maikel Fernández; José Manuel Gómez; Domingo Cantero; Javier Lafuente; Xavier Gamisans; David Gabriel; : D Cantero`. El PDF tiene 7 autores (Mora, Fernández, Gómez, Cantero, Lafuente, Gamisans, Gabriel); el chunk añade un **8º "autor" espurio: ": D Cantero"**, con dos puntos sueltos delante — casi con certeza GROBID capturó el bloque de afiliaciones/correspondencia al pie de la página ("M. Fernández · J. M. Gómez · D. Cantero" reaparece ahí como grupo de afiliación) como si fuera un `<author>` adicional, duplicando a Cantero con un artefacto de puntuación.

**Severidad máxima: ALTO** (clasificación de sección + lista de autores corrupta con entrada duplicada/espuria; no cambia resultados científicos pero sí la metadata bibliográfica)

---

### 12. `2010_soreanu_empirical_modelling_dual_performance_optimisation_hydrogen_sulphide_removal#2`
**Criterio:** abstract_control · **Página:** 1 · **Localización:** confirmada

1. **Contenido:** el abstract completo coincide palabra por palabra con el bloque "Abstract" del PDF.
2. **Números:** `2000-4000 ppmv`, `10-70 L/h`, `12 L` — todos exactos.
3-6. No aplica / patrón general de subíndices únicamente.
7. **Fronteras:** limpias, es el abstract completo en un solo chunk.

**Severidad máxima: BAJO** — chunk de control, sin defectos más allá del patrón general.

---

### 13. `1998_searcy_sulfur_reduction_human_erythrocytes#12`
**Criterio:** searcy_1998_control · **Página:** 5 (numeración de revista: 314) · **Localización:** confirmada

1. **Contenido:** completo, los 2 párrafos coinciden exactos con el PDF.
2. **Números:** `2.6 mM`, `0.2 mM`, `70%`, `0.5 mM S₅²⁻`, `5 times`, `5 min` — todos verificados exactos.
3. No aplica.
4. **Subíndices:** patrón general únicamente (S₂O₃²⁻ → "S 2 O 3 2-").
5. **Contaminación:** ninguna.
6. **Guionado:** el PDF usa una raya en "valid—that" (em dash); el chunk la sustituye por un guion corto "valid-that". Cambio tipográfico menor, sin pérdida de significado.
7. **Fronteras:** empieza a media frase ("they did not enter the cells." — el inicio "Other substrates were unexpectedly ineffective..." queda en el chunk anterior), comportamiento esperado del chunker.

**Severidad máxima: BAJO**

---

### 14. `1998_searcy_sulfur_reduction_human_erythrocytes#27`
**Criterio:** searcy_1998_control · **Página:** 9 (numeración revista: 318) · **Localización:** confirmada

1. **Contenido:** sección completa "Interaction of HS⁻ with hemoglobin" (3 frases), coincide exacta con el PDF de principio a fin — es la sección entera, no un fragmento.
2. **Números:** no hay cifras en esta sección; las citas "(Lemberg and Legge, '49; Arp and Childress, '83)" coinciden exactas.
3-6. Solo el patrón general de subíndices (HS⁻ → "HS -").
7. **Fronteras:** perfectas — sección corta que cabe entera en un chunk, sin cortes.

**Severidad máxima: BAJO** — el más limpio de los 16 chunks auditados.

---

### 15. `1997_gervais_diel_vertical_migration_i_cryptomonas_i_i_chromatium#8`
**Criterio:** no_table_paper_check · **Página:** 4 · **Localización:** confirmada (score de coincidencia 1.000, perfecto)

1. **Contenido:** la sección completa "Measurement of global radiation" (una sola frase) coincide.
2. **Números:** "30 km" coincide.
3. No aplica.
4. No aplica.
5. **Contaminación:** ninguna.
6. **Guionado:** no aplica.
7. **Fronteras:** sección completa, sin cortes.

**HALLAZGO NO ANTICIPADO:** el chunk dice `"...lake Miiggelsee situated..."`. El nombre real del lago es **Müggelsee** (lago en Berlín). La "ü" se convirtió en "ii". **Verifiqué que este error YA está en la capa de texto del propio PDF** (lo confirma que mi script de localización, que lee el texto nativo del PDF con PyMuPDF sin pasar por GROBID, encontró una coincidencia perfecta 1.000 contra "Miiggelsee" en la página) — es decir, **no es un defecto introducido por GROBID ni por nuestro pipeline**, sino un error heredado del propio PDF fuente (muy probablemente un OCR de mala calidad en el PDF de 1997). Lo marco igualmente porque afecta al contenido final que llega al RAG y podría confundir una búsqueda por el nombre del lago, pero la responsabilidad es 100% del PDF fuente, no reparable en ninguna capa nuestra ni de GROBID.

**Verificación adicional de la pregunta del PASO 1** ("¿el paper no tiene tablas, o se perdieron?"): escaneé el PDF completo (18 páginas) buscando cualquier mención "Table N" — **cero coincidencias**. Este paper genuinamente no tiene tablas; no es una pérdida de GROBID.

**Severidad máxima: ALTO** (nombre propio corrompido, aunque el origen es el PDF fuente y no nuestro pipeline)

---

### 16. `2018_lopez_feedforward_control_application_aerobic_anoxic_biotrickling_filters_h#12`
**Criterio:** no_table_paper_check · **Página:** 7 · **Localización:** confirmada

1. **Contenido:** completo, los 2 párrafos coinciden exactos con la columna izquierda del PDF.
2. **Números:** `99%`, `1-2%`, `10 m h⁻¹`, `6.5 y 19 m h⁻¹` — todos exactos.
3. No aplica.
4. **Subíndices:** patrón general (H₂S, m h⁻¹).
5. **Contaminación:** ninguna.
6. **Guionado:** correcto.
7. **Fronteras:** empieza a media frase (esperado), termina limpio antes del heading "Effect of N:S ratio...".

**Verificación adicional:** escaneé el PDF completo (9 páginas) buscando "Table N" — **cero coincidencias**. Este paper tampoco tiene tablas; confirma de nuevo que no es una pérdida de GROBID sino ausencia real en la fuente.

**Severidad máxima: BAJO**

---

## PASO 4 — Síntesis

### a) Tabla chunk × severidad máxima

| # | chunk_id (abreviado) | Severidad máxima | Motivo principal |
|---|---|---|---|
| 1 | almenglo...#34 (tabla larga) | **CRÍTICO** | Filas de 4 estudios distintos fusionadas en una sola entrada |
| 4 | valdebenito...#46 (tabla) | **CRÍTICO** | 3 columnas enteras ausentes (confirmado en TEI) |
| 5 | anderson...#12 (other) | **CRÍTICO** | Exponente "10⁻⁹"→"10m9", "CO₃²⁻"→"CO:-" |
| 10 | shihab...#12 (results) | **CRÍTICO** | Fórmula CH₃CH₂SH partida en fragmento `$$CH$$` + texto suelto |
| 3 | lenis...#25 (tabla) | ALTO | Nota al pie "* new digestate" perdida |
| 9 | brito...#1 (methods/portada) | ALTO | Sección mal clasificada (título con keyword) |
| 11 | mora...#1 (results/portada) | ALTO | Igual + autor duplicado espurio ": D Cantero" |
| 15 | gervais...#8 (other) | ALTO | "Müggelsee"→"Miiggelsee" (defecto del PDF fuente, no del pipeline) |
| 2 | almenglo...#33 (tabla corta) | MEDIO | Chunk fiel pero sin contenido informativo (solo caption) |
| 8 | khanongnuch...#9 (methods) | MEDIO | "SO₄²⁻" pierde carga y espacio: "SO 4 2concentrations" |
| 6 | elboghdady...#17 (other) | BAJO | Solo patrón general de subíndices |
| 7 | zheng...#1 (other/portada) | BAJO | Drop-cap "O cean", nombre chino del autor perdido |
| 12 | soreanu...#2 (abstract) | BAJO | Solo patrón general |
| 13 | searcy...#12 | BAJO | Em dash → guion corto |
| 14 | searcy...#27 | BAJO | Ninguno (el más limpio de la muestra) |
| 16 | lopez...#12 | BAJO | Solo patrón general |

**4 de 16 (25%) con al menos un defecto CRÍTICO** — pero nótese el sesgo de muestreo intencional: 3 de esos 4 son chunks de tabla o resultados con fórmulas, categorías deliberadamente sobre-representadas en el diseño de la muestra (PASO 1 pedía explícitamente el caso más largo/corto/multi-tabla). Entre los chunks de control (abstract, searcy, no_table_check) la tasa de CRÍTICO es 0/6.

### b) Defectos sistemáticos candidatos, por prevalencia estimada

| # | Defecto | Prevalencia medida/estimada | Capa | Reparable |
|---|---|---|---|---|
| 1 | Aplanado de subíndices/superíndices (H₂S→"H 2 S", exponentes) | **Muy alta** — presente en ~13/16 chunks de la muestra con química/unidades | GROBID (extracción de texto de PDF) | Parcialmente, con normalización regex post-hoc en nuestra capa (riesgo de falsos positivos) |
| 2 | `canonical_section()` matchea contra el título del paper → portada (autores/DOI) mal clasificada como methods/results | **31/87 papers (35.6%)**, medido contra el corpus completo | Nuestra capa (`3_process_corpus.py:385-396`) | **Sí, trivial** — no aplicar `canonical_section` al heading nivel-0/título, o tratar chunk_index=1 como caso especial |
| 3 | "Table N ." con espacio espurio antes del punto en cabeceras de tabla | **58/165 chunks de tabla (35%)**, medido | GROBID (tokenización del head) | Parcial — limpieza regex en `extract_tables_md` |
| 4 | Fusión de filas de tabla por el fallback de `_split_to_max_chars` (rows unidas por `\n` simple + tabla > 8000 chars) | **Baja en absoluto (1/165 tablas ≥7500 chars, 0.6%), pero CRÍTICA cuando ocurre** — y crecerá si se añaden papers con tablas grandes sin columna "Exp." | Nuestra capa (`3_process_corpus.py:499-521`, `extract_tables_md:352-358`) | **Sí** — unir filas con `\n\n` en vez de `\n`, o hacer que el fallback respete líneas antes de palabras |
| 5 | GROBID fragmenta una tabla visual en múltiples `<figure>` con columnas vacías | Vista 1 vez en la muestra (valdebenito), prevalencia real desconocida — requeriría escanear TEI de las 87 papers | GROBID (segmentación de tablas) | No en GROBID; parcialmente en nuestra capa (deduplicar/fusionar figuras con mismo `head`) |
| 6 | Fórmulas químicas partidas en fragmento `$$...$$` incompleto + texto suelto | Vista 1 vez (shihab), prevalencia desconocida sin más muestreo | GROBID (segmentación de `<formula>`) | No, techo de GROBID |
| 7 | Chunks "vacíos" de contenido útil (solo caption de tabla, o solo portada con autores/DOI) | Al menos 3/16 en la muestra (almenglo#33, brito#1, mora#1) | Nuestra capa | Parcial — se podría fusionar el remanente corto con el siguiente chunk, o excluir del índice de embeddings |
| 8 | Corrupción de caracteres/OCR heredada del PDF fuente (tilde→guion, "m" por signo menos, ü→ii) | Vista en 2 papers antiguos (1989, 1997) de la muestra | PDF fuente (pre-GROBID) | No, fuera de nuestro control |

### c) Los 3 chunks que más preocupan

1. **`valdebenito...#46`** — porque revela que GROBID puede **descartar columnas enteras de una tabla de forma completamente silenciosa**: nada en el chunk, ni en el TEI a simple vista, avisa de que faltan 3 columnas. Un usuario del RAG preguntando "¿qué inóculo usó el estudio (18) Lab scale?" recibiría una respuesta con la tabla pero sin esa columna, sin ninguna señal de que la información existe en el PDF y se perdió en la extracción.

2. **`almenglo...#34`** — porque no es un incidente aislado sino un **bug de código 100% reproducible** con una condición de disparo identificada con precisión (tabla sin columna "Exp." + bloque de filas > 8000 caracteres). Es el peor tipo de error para un RAG: fusiona silenciosamente datos de estudios distintos bajo una sola entrada, de forma que una pregunta como "¿qué pH usó Baspinar et al. 2011?" tiene una probabilidad real de responderse con el pH de otro estudio fusionado en la misma fila corrupta, con total confianza y sin ningún indicio de error.

3. **El patrón `brito#1`/`mora#1`** (portada mal clasificada) — porque afecta a **más de un tercio del corpus (31/87 papers)**, no es un caso raro. Cualquier consulta al RAG que filtre por `section_canonical="methods"` o `"results"` tiene una probabilidad de ~1/3 (por paper) de traer de vuelta un chunk vacío de contenido real (solo lista de autores y DOI) en lugar de metodología o resultados genuinos, degradando silenciosamente la precisión de cualquier búsqueda filtrada por sección.

### d) Notas previas del usuario

Aún no se me ha proporcionado ninguna nota de hallazgos previos. Si tienes una, compártela y la contrasto aquí explícitamente (en qué coincido y en qué no), como pediste — no la he leído ni buscado de antemano.
