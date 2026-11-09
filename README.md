# IoT Weather Project

IoT Weather Project monitors the weather in Seri Iskandar, Perak, and measures how good the forecasts really are. The project uses no hardware: data from 4 Nov 2026 is retrieved from public weather archives, and GitHub Actions jobs then keep collecting Open-Meteo's 15-minute analysis, the METAR report from Ipoh airport (WMKI) and new forecasts into Supabase Postgres every 10 minutes to every hour. Accuracy metrics are computed in SQL. LightGBM models trained on past forecasts correct Best Match's temperature, humidity, wind and pressure and forecast rain hours; they score every new forecast and retrain monthly. A React dashboard shows forecast versus actual, error by lead time, a model leaderboard, a rain indicator based on Open-Meteo's probability, and data coverage, hosted on Vercel. Everything runs on free tiers (RM0).

| Folder | Contents |
|---|---|
| [docs/](docs/) | A [plain-language guide](docs/Overview.md), the [implementation plan](docs/Implementation-plan.md) (what was built), the [ML research](docs/ML-research.md), the original architecture, API contract, UI spec and task list, and the report |
| [database/migrations/](database/migrations/) | Postgres schema, views, RPC functions, RLS and seed data |
| [database/test/](database/test/) | PGlite harness that applies the migrations and checks the SQL |
| [server/ingest/](server/ingest/) | Python package `iww_ingest`: the `observe`, `forecast`, `backfill` and `score` jobs |
| [server/ml/](server/ml/) | Model training, window scoring, the monthly retrain and the sanity notebook |
| [client/Iotweatherproject/](client/Iotweatherproject/) | React dashboard (deployed on Vercel) |
| [.github/workflows/](.github/workflows/) | Scheduled jobs, the monthly retrain and CI |

## Quick start (ingestion)

```sh
cd server/ingest
uv venv --python 3.11 .venv && . .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate elsewhere
uv pip install -r requirements.txt -e .
pytest
python -m iww_ingest.jobs.observe --dry-run                 # fetches and parses, writes nothing
```

To write to the database, put `SUPABASE_DB_URL` (the Supabase session pooler URI) and `CONTACT_EMAIL` in a `.env` file at the repo root. The dashboard reads `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` from `client/Iotweatherproject/.env` (on Vercel, from the project's environment variables). Both `.env` files are ignored by git.

Weather data by Open-Meteo.com (CC BY 4.0) · METAR from NOAA Aviation Weather Center.
