# Notas pendientes — research_agent

## Verificaciones pendientes

### PDFs manuales en categorías
Verificar el comportamiento cuando se añaden PDFs manualmente a `categorias/<cat>/pdfs/`:

```bash
# Caso de prueba
cp ~/paper_prueba.pdf /Volumes/research/categorias/microalgae/pdfs/
python scripts/3_process_corpus.py --phase microalgae
# ¿Se procesa el PDF manual? Esperado: SÍ

# Verificar skip logic
python scripts/3_process_corpus.py --phase microalgae
# ¿Se salta lo ya procesado? Esperado: SÍ
```

**Comportamiento esperado:**
- PDFs añadidos manualmente a cualquier `pdfs/` se procesan en la siguiente ejecución
- Scripts saltan automáticamente lo que ya tienen salida en `md_clean/`, `summaries/`, etc.
- Mezcla de PDFs manuales + Scopus en la misma categoría: ambos se procesan sin conflicto

## Keywords y criterios de búsqueda

Revisar y afinar:
- `config/keywords.yml` — para cribado de PDFs sueltos (flujo inbox)
- `config/scopus_queries.yml` — para búsquedas Scopus directas (flujo scopus)

Categorías con pocas queries actuales (ampliar si hace falta):
- `anoxic_biogas_biodesulfurization` — solo 1 query (12 resultados)
- `bioleaching_critical_materials` — solo 1 query (39 resultados)

## Próximos pasos (orden sugerido)

1. **Streamlit antes que cron** — interfaz para afinar queries y ver resultados
   - Panel de estado del NAS
   - Ejecutar flujos (scopus/inbox/adhoc)
   - Consultas RAG integradas
   - Editor de `scopus_queries.yml` y `keywords.yml`
   - Visor de `doi_manual.xlsx`

2. **Cron/launchd** — ingesta semanal automática
   ```bash
   0 6 * * 1  cd /Volumes/Disco/proyectos/research_agent/scripts && \
              /Users/martinramirez/venvs/rag_papers/bin/python run_pipeline.py scopus --recent-days 7
   ```

3. **README.md y docstrings** — documentación final
