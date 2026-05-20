# research_agent — Interfaz Streamlit

Panel web para gestionar los flujos del pipeline y hacer consultas RAG.

## Estructura

```
scripts/streamlit_app/
├── app.py                          ← portada con health checks y estado de categorías
├── utils.py                        ← helpers compartidos
├── README.md                       ← este fichero
└── pages/
    ├── 1_📥_Ingestar.py            ← Scopus / Inbox / Ad-hoc
    ├── 2_🔍_RAG.py                 ← consultas con retrieval y síntesis LLM opcional
    ├── 3_🔑_Keywords.py            ← editor estructurado de keywords.yml
    ├── 4_📚_Scopus_queries.py      ← editor de scopus_queries.yml
    └── 5_📄_DOI_manual.py          ← visor de doi_manual.xlsx
```

## Instalación

Desde el Mac mini de casa (donde están los scripts y el NAS montado):

```bash
cd /Volumes/Disco/proyectos/research_agent
source ~/venvs/rag_papers/bin/activate
pip install streamlit
```

Streamlit ya trae todo lo que necesita; el resto de dependencias (pandas, pyyaml, faiss-cpu, ollama, openpyxl, python-dotenv, requests) ya las usa el pipeline.

Añade `streamlit` a `requirements.txt`:

```bash
echo "streamlit>=1.32" >> requirements.txt
```

## Copiar la carpeta `streamlit_app/` al proyecto

Copia la carpeta `streamlit_app/` dentro de `scripts/`:

```
scripts/
├── streamlit_app/          ← NUEVO
├── pipeline.py
├── run_pipeline.py
├── 0_scopus_api.py
└── ...
```

## Arranque manual (para pruebas)

```bash
cd /Volumes/Disco/proyectos/research_agent/scripts/streamlit_app
~/venvs/rag_papers/bin/streamlit run app.py \
    --server.address 0.0.0.0 \
    --server.port 8501
```

Acceso desde el portátil:
- **En casa (LAN)**: `http://<ip-del-mac-mini>:8501`
- **Fuera (VPN casa activa)**: misma URL
- **En el propio Mac mini**: `http://localhost:8501`

Para conocer la IP del Mac mini:
```bash
ipconfig getifaddr en0   # o en1 si va por WiFi
```

## Arranque automático con `launchd` (recomendado)

Crea `~/Library/LaunchAgents/com.research_agent.streamlit.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.research_agent.streamlit</string>

    <key>WorkingDirectory</key>
    <string>/Volumes/Disco/proyectos/research_agent/scripts/streamlit_app</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/martinramirez/venvs/rag_papers/bin/streamlit</string>
        <string>run</string>
        <string>app.py</string>
        <string>--server.address</string>
        <string>0.0.0.0</string>
        <string>--server.port</string>
        <string>8501</string>
        <string>--server.headless</string>
        <string>true</string>
        <string>--browser.gatherUsageStats</string>
        <string>false</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Volumes/Disco/proyectos/research_agent/logs/streamlit.log</string>

    <key>StandardErrorPath</key>
    <string>/Volumes/Disco/proyectos/research_agent/logs/streamlit.err.log</string>
</dict>
</plist>
```

Cargar / descargar:

```bash
# Cargar (arranca y se queda corriendo al reiniciar)
launchctl load ~/Library/LaunchAgents/com.research_agent.streamlit.plist

# Ver estado
launchctl list | grep streamlit

# Descargar
launchctl unload ~/Library/LaunchAgents/com.research_agent.streamlit.plist

# Logs en vivo
tail -f /Volumes/Disco/proyectos/research_agent/logs/streamlit.log
```

## Notas

- **Sin auth**: la VPN casa actúa de barrera. Si en algún momento abres el puerto al exterior, mete autenticación básica delante (caddy / nginx).
- **NAS no montado**: la app detecta esto y bloquea acciones con un aviso. Si el Mac mini se reinicia, asegúrate de que el NAS se monta antes que el `launchd` (típicamente con Finder → Login Items, o un script de montaje).
- **Cache FAISS**: la página RAG cachea cada índice cargado en memoria. Si reconstruyes embeddings, pulsa "🔄 Re-comprobar estado" en la portada y vuelve a entrar en RAG (`@st.cache_resource.clear()` también vale, vía menú).
- **on_output callback**: las páginas de ingesta capturan stdout línea a línea sin polling. Si una etapa es muy verbosa, solo se muestran las últimas 200 líneas (el log completo se sigue guardando en `logs/` por los scripts subyacentes).
- **Backup YAML**: los editores de keywords/scopus_queries hacen un `.bak` antes de sobrescribir. Si algo sale mal: `mv keywords.yml.bak keywords.yml`.

## Cosas pendientes (futuro)

- Página de logs (tail de `logs/*.log` en vivo)
- Editor de `doi_manual.xlsx` (st.data_editor) — actualmente solo lectura
- Búsqueda de papers por título/DOI desde la página RAG
- Métricas de uso de Ollama (latencia media por modelo)
