# Notas pendientes — research_agent

## Verificaciones completadas

### ✅ PDFs manuales en categorías (verificado 2026-05-16)

**Caso de prueba:** PDF manual `35. 2020-07 A. Algal reseach.pdf` en `microalgae/pdfs/`

**Resultados:**
- ✅ `3_process_corpus.py` procesa PDFs con nombres no-DOI (normaliza espacios a `_`)
- ✅ Skip logic funciona: segunda ejecución salta el PDF ya procesado
- ✅ Cadena completa OK: summarize → metadata → embeddings
- ✅ RAG query recupera chunks del PDF manual correctamente

**Comportamiento confirmado:**
- PDFs añadidos manualmente a cualquier `categorias/<cat>/pdfs/` se procesan en la siguiente ejecución
- No requieren nombres DOI (aunque se normalizan)
- Scripts saltan automáticamente lo ya procesado
- Mezcla de PDFs manuales + Scopus en la misma categoría: ambos se procesan sin conflicto

---

### ✅ Interfaz Streamlit + despliegue launchd (completado 2026-05-20)

- 5 páginas funcionando: Ingestar, RAG, Keywords, Scopus queries, DOI manual
- Servicio launchd corriendo 24/7 con auto-restart
- Mac mini configurado en modo servidor (pmset)
- Acceso desde portátil por LAN y VPN casa confirmado

**Gotchas documentados en ESTADO.md** (ver sección correspondiente).

---

### ✅ RAG multi-provider + cost tracking (completado 2026-05-20)

- Anthropic (Claude) y OpenAI (GPT) añadidos como providers de síntesis
- Contador de uso mensual en `/Volumes/research/metadatos/rag_usage/`
- Pre-estimación de coste antes de cada consulta
- bge-m3 disponible como índice alternativo a nomic para `anoxic_biogas_biodesulfurization`

---

## En progreso

### 🔄 Re-embeddear todas las categorías con bge-m3

Corriendo ahora mismo en `tmux new -s embeddings` en el Mac mini.

**Comando lanzado:**
```bash
for cat in biological_gas_odor_treatment \
           bioplastics_microplastics \
           biogas_upgrading_biomethanation \
           microalgae \
           single_cell_protein \
           advanced_oxidation_processes \
           bioleaching_critical_materials; do
    python 5_build_embeddings.py --project "$cat" --phase "$cat" --model bge-m3
done
```

**Verificar progreso:**
```bash
tmux attach -t embeddings
# o
ls -d /Volumes/research/categorias/*/embeddings/*__bge-m3 2>/dev/null
```

Deben aparecer las 8 categorías cuando termine.

**Decisión pendiente tras terminar:** comparar retrieval nomic vs bge-m3 con más casos de uso real (sobre todo consultas en castellano, donde bge-m3 multilingüe debería destacar). Si la mejora es marginal, borrar los índices bge-m3 y quedarse con nomic en todas.

---

## Keywords y criterios de búsqueda

Revisar y afinar:
- `config/keywords.yml` — para cribado de PDFs sueltos (flujo inbox)
- `config/scopus_queries.yml` — para búsquedas Scopus directas (flujo scopus)

Categorías con pocas queries actuales (ampliar si hace falta):
- `anoxic_biogas_biodesulfurization` — solo 1 query (12 resultados)
- `bioleaching_critical_materials` — solo 1 query (39 resultados)

---

## Próximos pasos (orden sugerido)

### 1. Mejorar el editor de keywords en la web 🔑

La tabla actual (`st.data_editor`) es poco práctica. Tres opciones diseñadas:

**Opción A — Tags/chips por categoría** ← recomendada para uso diario
Cada categoría con sus keywords como chips individuales con botón ✕ para borrar,
y un input al final para añadir. Requiere `streamlit-tags` (pip install).

**Opción B — Textarea por categoría** ← más rápida para ediciones masivas
Cada categoría con un `text_area` donde escribes keywords una por línea.
Sin dependencias extra. Ideal para pegar 30 keywords de golpe.

**Opción C — Híbrido** (chips por defecto + botón "edición masiva" abre textarea)
Lo mejor de A y B, a costa de más código.

**Opción D — Sugerencia automática con LLM**
Dado el corpus ya clasificado de una categoría, Ollama propone keywords
que aparecen frecuentemente en los papers pero no están en la lista.
Experimento interesante para descubrir términos no considerados.

→ Decidir opción en próxima sesión y montar.

### 2. Cron/launchd para ingesta Scopus semanal automática

Pendiente. Ejemplo de LaunchAgent o cron:
```bash
0 6 * * 1  cd /Volumes/Disco/proyectos/research_agent/scripts && \
           /Users/martinramirez/venvs/rag_papers/bin/python run_pipeline.py \
           scopus --recent-days 7
```

### 3. Pequeñas mejoras UX en la web (baja prioridad)

- **Toggle síntesis OFF**: cuando el toggle de "Sintetizar respuesta con LLM"
  está desactivado, mostrar un aviso visible en el área principal
  (ej. "Síntesis desactivada — activa el toggle en la sidebar para obtener
  una respuesta con citas") en lugar de pasar silenciosamente a mostrar solo chunks.
  Evita confusión de "¿por qué no responde?".
- **Botones por fila en portada**: acción "Procesar pendientes" directa por categoría
  en la tabla principal, sin tener que ir a la tab de Ingestar.
- **Página de logs en vivo**: `tail -f` de `~/Library/Logs/research_agent/*.log`
  directamente en la web.
- **Editor doi_manual.xlsx** con `st.data_editor` — actualmente solo visor.

### 4. Actualizar precios en app_utils.py

Los precios en `LLM_PRICING` son aproximados a fecha 2026-05-20. Verificar
periódicamente en:
- Anthropic: https://docs.claude.com/en/docs/about-claude/pricing
- OpenAI: https://openai.com/api/pricing

### 5. README.md global + docstrings

Documentación final del proyecto: README de primer nivel con visión general,
y docstrings en los scripts numerados que aún no los tienen.

### 6. Decisión final nomic vs bge-m3 (tras re-indexar)

Cuando termine el barrido bge-m3:
- Comparar con casos reales de uso (especialmente consultas en castellano)
- Si bge-m3 no gana claramente → borrar los `*__bge-m3` y quedarse con nomic
- Si bge-m3 gana → actualizar DEFAULT_MODEL en app_utils.py y documentar el cambio
