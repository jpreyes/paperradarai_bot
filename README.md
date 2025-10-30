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
LLM_THRESHOLD=0.70
LLM_MAX_PER_TICK=2
LLM_ONDEMAND_MAX_PER_HOUR=5
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
```

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
