# research_agent — Estado del proyecto

## Infraestructura

| Componente | Detalle |
|---|---|
| Mac mini M4 Pro | 32GB RAM, procesa todo |
| NAS | `/Volumes/research/` — almacenamiento |
| Scripts | `/Volumes/Disco/proyectos/research_agent/scripts/` |
| Config | `/Volumes/Disco/proyectos/research_agent/config/` |
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
├── inbox/              ← PDFs nuevos sin procesar (flujo inbox)
├── inbox_csv/          ← CSVs de Scopus (manual o via 0_scopus_api.py)
├── fallidos/           ← PDFs no clasificables
├── metadatos/          ← CSVs globales, doi_manual.xlsx, cache
└── categorias/
    ├── biogas_upgrading_biomethanation/
    ├── bioplastics_microplastics/
    ├── biological_gas_odor_treatment/
    ├── anoxic_biogas_biodesulfurization/   ← validado pipeline completo
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

## Estructura del proyecto

```
research_agent/
├── config/
│   ├── .env                  ← claves API, hosts
│   ├── keywords.yml          ← palabras clave para cribado (8 categorías)
│   └── scopus_queries.yml    ← queries Scopus por categoría
├── scripts/
│   ├── pipeline.py           ← orquestador (módulo importable)
│   ├── run_pipeline.py       ← CLI del orquestador (scopus/inbox/adhoc)
│   ├── 0_scopus_api.py       ← búsqueda Scopus API
│   ├── 1_rename_papers_by_doi.py
│   ├── 2_screen_pdfs.py
│   ├── 3_process_corpus.py
│   ├── 3a_download_pdfs.py
│   ├── 3b_summarize.py
│   ├── 4_extract_metadata.py
│   ├── 5_build_embeddings.py
│   ├── 6_make_packages.py
│   ├── 7_make_master_index.py
│   ├── 8_query_rag.py
│   └── utils/
│       └── pdf_utils.py
├── logs/
├── .gitignore
└── requirements.txt
```

## Scripts (orden de ejecución)

| Script | Función | Estado |
|---|---|---|
| `0_scopus_api.py` | Consulta Scopus Search API por categoría. Queries en `config/scopus_queries.yml` | ✅ |
| `1_rename_papers_by_doi.py` | Renombra PDFs via DOI + Crossref. Gestiona `doi_manual.xlsx` | ✅ |
| `2_screen_pdfs.py` | Clasifica PDFs en 8 categorías via keywords + Ollama | ✅ |
| `3_process_corpus.py` | PDF → TEI (GROBID) → MD clean → chunks JSONL | ✅ |
| `3a_download_pdfs.py` | Descarga PDFs desde CSV Scopus via Unpaywall + Elsevier API | ✅ |
| `3b_summarize.py` | Genera resúmenes con qwen3:14b | ✅ |
| `4_extract_metadata.py` | Extrae metadatos de TEI XML (título, DOI, autores, refs) | ✅ |
| `5_build_embeddings.py` | Genera índice FAISS con nomic-embed-text via Ollama | ✅ |
| `6_make_packages.py` | Crea paquetes NotebookLM (FULLTEXT, REFERENCES, INDEX) | ✅ |
| `7_make_master_index.py` | Genera MASTER_INDEX.md por categoría | ✅ |
| `8_query_rag.py` | Consultas RAG sobre índice FAISS | ✅ |
| `pipeline.py` | Orquestador: tres flujos (scopus, inbox, adhoc). Importable por Streamlit | ✅ |
| `run_pipeline.py` | CLI del orquestador con subcomandos | ✅ |
| `utils/pdf_utils.py` | Funciones comunes (DOI, slugify, texto) | ✅ |

## Tres flujos del pipeline

### Flujo A — Scopus (categorizado de origen)

No necesita cribado: la query de Scopus ya define la categoría.
Los PDFs van directamente a `categorias/<cat>/pdfs/`.

```
0_scopus_api   → inbox_csv/scopus_<cat>_<fecha>.csv
3a_download    → categorias/<cat>/pdfs/  (--out-dir directo)
3_process      → tei/ + md_clean/ + chunks/
3b_summarize   → summaries/
4_extract      → metadata/
5_embeddings   → embeddings/
6_packages     → notebooklm_packages/
7_index        → MASTER_INDEX.md
```

```bash
python run_pipeline.py scopus --recent-days 7
python run_pipeline.py scopus --category microalgae --max 500 --year-start 2020
```

### Flujo B — Inbox (PDFs sueltos sin clasificar)

Para PDFs descargados manualmente o acumulados en inbox/.

```
1_rename       → inbox/ (renombrados) + doi_manual.xlsx
2_screen       → categorias/<cat>/pdfs/ + fallidos/
3_process … 7_index  (solo categorías con PDFs nuevos)
```

```bash
python run_pipeline.py inbox
```

### Flujo C — Ad-hoc (proyecto temporal)

Lote de PDFs sin clasificación. Crea proyecto, copia PDFs, procesa y deja listo para RAG.

```
carpeta PDFs → categorias/<nombre>/pdfs/ (copia)
3_process … 7_index
8_query_rag → consultas RAG
```

```bash
python run_pipeline.py adhoc --name revision_metanol --pdfs ~/papers_metanol
python 8_query_rag.py --project revision_metanol "tu pregunta"
```

## Configuración (config/.env)

```
OLLAMA_HOST=http://pciq22.uca.es:11434
OLLAMA_API_KEY=<clave>
GROBID_URL=http://pciq22.uca.es:8070
GROBID_TIMEOUT=600
UNPAYWALL_EMAIL=martin.ramirez@uca.es
ELSEVIER_API_KEY=<clave>
```

## Queries Scopus (config/scopus_queries.yml)

Fichero YAML con queries de búsqueda por categoría en sintaxis Scopus
(`TITLE-ABS-KEY`, `AND`, `OR`, `W/N`). Las queries son independientes
de `keywords.yml` (usado solo para cribado de PDFs sueltos).

## Categorías de investigación (config/keywords.yml)

1. `biological_gas_odor_treatment`
2. `anoxic_biogas_biodesulfurization` ← validado pipeline completo (Scopus → RAG)
3. `bioplastics_microplastics`
4. `biogas_upgrading_biomethanation` ← validado pipeline completo
5. `microalgae`
6. `single_cell_protein`
7. `advanced_oxidation_processes`
8. `bioleaching_critical_materials`

## Plan pendiente (por orden)

1. ~~**`0_scopus_api.py`**~~ ✅ — consulta Scopus API con queries personalizadas por categoría
2. ~~**Orquestador + ingesta continua**~~ ✅ — `pipeline.py` + `run_pipeline.py` con tres flujos (scopus/inbox/adhoc)
3. **Cron/launchd** — configurar ejecución automática semanal en Mac mini
4. **Interfaz web Streamlit** — panel de estado, ejecución de scripts, RAG integrado, editor de doi_manual.xlsx
5. **README.md y docstrings** — documentación final de todos los scripts

## Notas importantes

- Ollama en `pciq22.uca.es` solo accesible desde red UCA o VPN
- Descargas Elsevier requieren VPN activa (autenticación por IP institucional)
- GROBID puede necesitar warm-up tras inactividad (primera llamada lenta)
- El cribado (`2_screen`) usa keywords primero (rápido) y Ollama como fallback
- El cribado NO es necesario para el flujo Scopus (la query ya define la categoría)
- `doi_manual.xlsx` en `/Volumes/research/metadatos/` acumula todos los DOIs procesados
- Skip automático en todos los scripts: no reprocesa lo ya existente
- FAISS para embeddings (no ChromaDB), manteniendo scripts originales
- Argumentos inconsistentes entre scripts: `--phase` (3_process, 3b_summarize) vs `--project` (4–8). El orquestador absorbe la diferencia.
