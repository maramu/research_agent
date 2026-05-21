# Reprocesado de pendientes desde Streamlit

## Resumen

Se añadió una pestaña **Pendientes** dentro de `Ingestar` en la app Streamlit de `research_agent`.

La finalidad es poder reanudar una ingesta que se haya cortado a mitad de ejecución, sin tener que lanzar comandos manuales desde terminal.

## Ubicación

Archivo modificado:

```text
scripts/streamlit_app/pages/1_Ingestar.py
```

La navegación queda:

```text
Ingestar
├── Scopus
├── Inbox
├── Pendientes
└── Ad-hoc
```

## Qué problema resuelve

Antes, la portada mostraba una columna `Pendientes` basada en:

```text
PDFs - MD limpio
```

Eso solo detecta PDFs que no llegaron a generar `md_clean/*.clean.md`.

Sin embargo, si Streamlit se corta después de crear `md_clean` pero antes de terminar resúmenes, metadata, embeddings o paquetes, esa categoría puede seguir incompleta aunque `Pendientes` sea 0.

Ejemplo observado:

```text
bioplastics_microplastics
PDFs:       64
MD limpio: 64
Resúmenes: 50
Metadata:  8
Chunks:    64
```

Aquí el atasco real está en pasos posteriores, especialmente `summaries` y `metadata`, no en la generación inicial de `md_clean`.

## Lógica nueva

La pestaña **Pendientes** ahora muestra una tabla por categoría con:

```text
PDFs
MD limpio
Resúmenes
Chunks
Metadata
FAISS
Paquetes
Brechas
```

La columna `Brechas` compara los artefactos esperados por paper contra los ya generados.

Por defecto, se consideran incompletas las categorías que tengan faltantes en:

```text
MD limpio
Resúmenes
Chunks
Metadata
```

FAISS y paquetes se muestran como información de estado, pero no se usan para marcar automáticamente una categoría como incompleta por paper.

Esto evita falsos positivos como `adhoc_20260521_SpringerBrief`, que tiene los outputs principales por paper completos.

## Cómo usarlo

1. Abrir la app Streamlit.
2. Ir a **Ingestar**.
3. Entrar en la pestaña **Pendientes**.
4. Revisar la tabla de brechas.
5. Dejar seleccionadas las categorías incompletas o elegir manualmente otras.
6. Pulsar **Reprocesar pendientes**.

La acción ejecuta `process_category()` para cada categoría seleccionada.

Esto relanza la cadena:

```text
3_process_corpus.py
3b_summarize.py
4_extract_metadata.py
5_build_embeddings.py
6_make_packages.py
7_make_master_index.py
```

Los scripts ya tienen lógica de salto para artefactos existentes, por lo que la intención es reanudar lo que falte sin rehacer innecesariamente lo ya completado.

## Funciones añadidas

En `1_Ingestar.py` se añadieron:

```text
run_pending_categories()
category_resume_row()
```

`run_pending_categories()` procesa varias categorías con salida en vivo en Streamlit.

`category_resume_row()` calcula los conteos y las brechas mostradas en la tabla.

## Verificación

Se comprobó sintaxis con:

```bash
python3 -m py_compile proyectos/research_agent/scripts/streamlit_app/pages/1_Ingestar.py
```

