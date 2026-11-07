# Iskandar Weather Watch

Iskandar Weather Watch monitors the weather in Seri Iskandar, Perak, and measures how good the forecasts really are. The project uses no hardware: data from 4 Nov 2026 is retrieved from public weather archives, and GitHub Actions jobs then keep collecting Open-Meteo's 15-minute analysis, the METAR report from Ipoh airport (WMKI) and new forecasts into Supabase Postgres every 10 minutes to every hour. Accuracy metrics are computed in SQL, a temperature bias-correction model is trained on past forecasts, and a React dashboard shows forecast versus actual, error by lead time, a model leaderboard, a rain indicator based on Open-Meteo's probability, and data coverage. Everything runs on free tiers (RM0).

| Folder | Contents |
|---|---|
| [docs/](docs/) | Architecture, API contract, UI spec, task list, the [implementation plan](docs/Implementation-plan.md) and the report |
| [database/migrations/](database/migrations/) | Postgres schema, views, RPC functions, RLS and seed data |
| [database/test/](database/test/) | PGlite harness that applies the migrations and checks the SQL |
| [server/ingest/](server/ingest/) | Python package `iww_ingest`: the `observe`, `forecast` and `backfill` jobs |
| [server/ml/](server/ml/) | Temperature bias-correction model, scoring and the sanity notebook |
| [client/Iotweatherproject/](client/Iotweatherproject/) | React dashboard |
| [.github/workflows/](.github/workflows/) | Scheduled jobs and CI |

## Quick start (ingestion)

```sh
cd server/ingest
uv venv --python 3.11 .venv && . .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate elsewhere
uv pip install -r requirements.txt -e .
pytest
python -m iww_ingest.jobs.observe --dry-run                 # fetches and parses, writes nothing
```

Set `SUPABASE_DB_URL` (see [.env.example](.env.example)) to write to the database.

Weather data by Open-Meteo.com (CC BY 4.0) · METAR from NOAA Aviation Weather Center.
