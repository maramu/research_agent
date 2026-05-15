# research_agent — Estado del proyecto

## Infraestructura

| Componente | Detalle |
|---|---|
| Mac mini M4 Pro | 32GB RAM, procesa todo |
| NAS | `/Volumes/research/` — almacenamiento |
| Scripts | `/Volumes/Disco/proyectos/research_agent/` |
| Venv | `~/venvs/rag_papers` |
| GROBID | Docker, `http://pciq22.uca.es:8070` |
| Ollama | `http://pciq22.uca.es:11434` |
| GitHub | `https://github.com/maramu/research_agent` |

## Modelos Ollama disponibles

- `qwen3:14b` — resúmenes detallados
- `gemma3:4b` — cribado rápido de abstracts
- `qwen3:8b` — uso general
- `nomic-embed-text` — embeddings FAISS

## Estructura NAS

```
/Volumes/research/
├── inbox/              ← PDFs nuevos sin procesar
├── inbox_csv/          ← CSVs exportados de Scopus
├── fallidos/           ← PDFs no clasificables
├── metadatos/          ← CSVs globales, doi_manual.xlsx, cache
└── categorias/
    ├── biogas_upgrading_biomethanation/
    ├── bioplastics_microplastics/
    ├── biological_gas_odor_treatment/
    ├── anoxic_biogas_biodesulfurization/
    ├── microalgae/
    ├── single_cell_protein/
    ├── advanced_oxidation_processes/
    └── bioleaching_critical_materials/
        ├── pdfs/
        ├── md_clean/
        ├── summaries/
        ├── chunks/
        ├── embeddings/
        ├── metadata/
        ├── notebooklm_packages/
        ├── tei/
        └── logs/
```

## Scripts (orden de ejecución)

| Script | Función | Estado |
|---|---|---|
| `0_scopus_api.py` | Consulta Scopus Search API por categoría y genera CSVs para inbox_csv/ | ✅ |
| `1_rename_papers_by_doi.py` | Renombra PDFs via DOI + Crossref. Gestiona `doi_manual.xlsx` | ✅ |
| `2_screen_pdfs.py` | Clasifica PDFs en 8 categorías via keywords + Ollama | ✅ |
| `3_process_corpus.py` | PDF → TEI (GROBID) → MD clean → chunks JSONL | ✅ |
| `3a_download_pdfs.py` | Descarga PDFs desde CSV Scopus via Unpaywall + Elsevier API | ✅ |
| `3b_summarize.py` | Genera resúmenes 800-1000 palabras con qwen3:14b | ✅ |
| `4_extract_metadata.py` | Extrae metadatos de TEI XML (título, DOI, autores, refs) | ✅ |
| `5_build_embeddings.py` | Genera índice FAISS con nomic-embed-text via Ollama | ✅ |
| `6_make_packages.py` | Crea paquetes NotebookLM (FULLTEXT, REFERENCES, INDEX) | ✅ |
| `7_make_master_index.py` | Genera MASTER_INDEX.md por categoría | ✅ |
| `8_query_rag.py` | Consultas RAG sobre índice FAISS | ✅ |
| `scripts/utils/pdf_utils.py` | Funciones comunes (DOI, slugify, texto) | ✅ |

## Flujo completo

```
inbox_csv/ → 3a_download  → inbox/ (PDFs descargados)
inbox/     → 1_rename     → inbox/ (renombrados) + doi_manual.xlsx
inbox/     → 2_screen     → categorias/<categoria>/pdfs/
                          → fallidos/ (irrelevantes o baja confianza)

categorias/<categoria>/pdfs/
           → 3_process    → tei/ + md_clean/ + chunks/
           → 3b_summarize → summaries/
           → 4_extract    → metadata/
           → 5_embeddings → embeddings/
           → 6_packages   → notebooklm_packages/
           → 7_index      → MASTER_INDEX.md
           → 8_query      → respuestas RAG
```

## Configuración (.env)

```
OLLAMA_HOST=http://pciq22.uca.es:11434
OLLAMA_API_KEY=<clave>
GROBID_URL=http://pciq22.uca.es:8070
GROBID_TIMEOUT=600
UNPAYWALL_EMAIL=martin.ramirez@uca.es
ELSEVIER_API_KEY=<clave>
```

## Categorías de investigación (keywords.yml)

1. `biological_gas_odor_treatment`
2. `anoxic_biogas_biodesulfurization`
3. `bioplastics_microplastics`
4. `biogas_upgrading_biomethanation` ← validado con pipeline completo
5. `microalgae`
6. `single_cell_protein`
7. `advanced_oxidation_processes`
8. `bioleaching_critical_materials`

## Plan pendiente (por orden)

1. **Ingesta continua** — cron/launchd en Mac mini para ejecutar pipeline automáticamente
2. **`9_adhoc_project.py`** — RAG para búsquedas específicas sin clasificación (ej. 30 artículos ad-hoc)
3. **Interfaz web Streamlit** — panel de estado, ejecución de scripts, RAG integrado, editor de doi_manual.xlsx
4. **README.md y docstrings** — documentación final de todos los scripts

## Notas importantes

- Ollama en `pciq22.uca.es` solo accesible desde red UCA o VPN
- Descargas Elsevier requieren VPN activa (autenticación por IP institucional)
- El cribado usa keywords primero (rápido) y Ollama como fallback
- `doi_manual.xlsx` en `/Volumes/research/metadatos/` acumula todos los DOIs procesados
- Skip automático en todos los scripts: no reprocesa lo ya existente
- FAISS para embeddings (no ChromaDB), manteniendo scripts originales
