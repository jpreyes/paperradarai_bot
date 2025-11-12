# PaperRadar (bot + API)

Modular refactor listo para escalar a web: separa fetching, ranking y LLM del “delivery” (Telegram) y expone una API (FastAPI).

## Requisitos

- Python 3.10–3.12
- `pip install -r requirements.txt`

## Variables de entorno

Cree un archivo `.env` basado en `.env.example`:

```
TELEGRAM_BOT_TOKEN=
DATA_ROOT=data
POLL_INTERVAL_MIN=2
SIM_THRESHOLD=0.55
TOP_N=12
MAX_AGE_HOURS=0

OPENAI_API_KEY=           # (opcional)
LLM_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
LLM_THRESHOLD=0.70
LLM_MAX_PER_TICK=2
LLM_ONDEMAND_MAX_PER_HOUR=5
JOURNAL_TOP_N=9
JOURNAL_LLM_TOP=4
```

## Ejecutar el bot de Telegram

```bash
python -m paperradar.bot.main
```

## Ejecutar la API web

```bash
python -m paperradar.web.main
# GET http://localhost:8000/health
# GET http://localhost:8000/sample/<chat_id>?top=5
# GET http://localhost:8000/users/<chat_id>/journals
```

### Nuevos endpoints de journals

- `GET /journals/catalog` lista el catalogo actual (se inicializa con 3 ejemplos).
- `POST /journals/catalog` permite upsert masivo de revistas (`{"items": [...]}`).
- `DELETE /journals/catalog/{journal_id}` elimina registros por `id`/ISSN.
- `POST /journals/catalog/dedupe` limpia duplicados (mismo ISSN o titulo normalizado).
- `POST /users/{chat_id}/journals/ingest` baja revistas desde Crossref usando los topics del perfil activo (usa las credenciales definidas en `.env` para `CROSSREF_MAILTO`).
- `GET /users/{chat_id}/journals?limit=9&llm_top=4` genera recomendaciones basadas en embeddings de OpenAI + analisis LLM.

La vista web ahora incluye una pestana **Revistas** con tarjetas que combinan la similitud vectorial, solapamiento tematico y un resumen (LLM/heuristico) sobre pros y riesgos de publicacion. El boton “Actualizar catalogo” ejecuta la ingesta de Crossref y refresca la lista automaticamente.

### Embeddings de papers

Cada vez que se envian nuevos papers en modo live se genera (y cachea en `data/paper_embeddings.json`) un embedding usando `OPENAI_EMBEDDING_MODEL`. Solo se calcula para los items que efectivamente se muestran, asi se reutilizan los vectores entre perfiles sin recalcular en cada consulta.

### Magic links (acceso web sin Telegram)

- `POST /auth/magic/request` recibe `{ "email": "investigador@dominio" }` y devuelve un `login_url` (se muestra tambi&eacute;n en la UI).
- `GET /auth/magic/consume?token=...` consume el enlace, guarda el `chat_id` en `localStorage` y redirige al panel.
- Cada usuario tiene un PIN (`web_passcode`) que se genera al crear el enlace; debe ingresarse en la interfaz para habilitar los datos en ese navegador.
- `POST /auth/pin/verify` valida `{chat_id, pin}`. El front almacena la sesi&oacute;n localmente y permite cerrar sesi&oacute;n desde el panel.

Los usuarios se persisten en `data/<chat_id>` exactamente igual que los provenientes de Telegram, por lo que todas las funciones (perfiles, likes, ingest) quedan disponibles inmediatamente.

## Estructura

```
paperradar/
  config.py, logging_setup.py
  storage/ (users, history, cache)
  fetchers/ (arxiv, crossref, merge)
  core/ (filters, ranking, llm, model)
  services/ (pipeline)
  bot/ (handlers, scheduler, main)
  web/ (api, main)
```

---

> Migración: se preservan formatos `data/<chat_id>/meta.json`, `sent_ids.json`, `history.json/csv`.
