# IoT Weather Project

Weather monitoring + forecast-accuracy dashboard for Seri Iskandar. Read [docs/Implementation-plan.md](docs/Implementation-plan.md) first (local only, git-ignored like the other design docs and the report): it records scope (v2.0: data retrieved from 4 Nov, no Himawari; Phase 5b added humidity, wind, pressure and rain models with live scoring), the folder mapping from the docs' paths, decisions, and progress.

## Layout

- `database/migrations/`: SQL, applied in phased order `0001 → 0004 → 0005 → 0002 → 0003 → 0006 → 0007 → 0008`. Each file grants its own objects. Once a file is applied to the live DB, fixes go in a new numbered file.
- `database/test/`: PGlite (Postgres in WASM) tests. `npm test`; `npm run serve` exposes a migrated DB on port 5544 (`EMPTY=1` for an empty one).
- `server/ingest/`: Python 3.11 package `iww_ingest` (jobs `observe`, `forecast`, `backfill`, `score`; tools `check`, `migrate`). Model inputs live in `iww_ingest/features/bias.py` and `iww_ingest/ml/models.py`, shared by training and live scoring; `score` needs `requirements-score.txt` (LightGBM).
- `server/ml/`: training, with its own `.venv`. `best_match` changed around Q3 2025, so training starts on 1 Oct 2025. `train_bias.py` + `score_window.py` made temperature v1.0 (the report's); `train_models.py` + `score_models.py` made the Phase 5b models; `retrain.py` runs monthly from `retrain.yml`. Live models load from `ml_models.artifact`, not the repo.
- `client/Iotweatherproject/`: React dashboard (Phase 4), deployed on Vercel (`vercel.json`; set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` there).

## Commands

```sh
cd server/ingest
.venv/Scripts/python -m pytest -q                                   # unit tests (DB tests skip without IWW_TEST_DB_URL)
.venv/Scripts/python -m iww_ingest.jobs.observe --dry-run           # live fetch + parse, no writes
IWW_TEST_DB_URL=postgresql://postgres@127.0.0.1:5544/postgres .venv/Scripts/python -m pytest -q   # with `npm run serve`
cd database/test && npm test
cd client/Iotweatherproject && npm run build
cd server/ml && .venv/Scripts/python -m pytest -q tests
cd server/ml && .venv/Scripts/python retrain.py --month 2026-11 --dry-run   # compare only
```

## Conventions

- Store UTC; group local days with explicit `at time zone 'Asia/Kuala_Lumpur'`; hour H covers (H−1h, H].
- Jobs are idempotent (`db.upsert` with ON CONFLICT) and log every run to `ingestion_runs`.
- Retrieved data stays marked (`is_backfill`, `origin = 'previous_runs'`), and data before `live_since` is never described as live or continuous collection.
- The report window is frozen by the data check in plan §5.3, using counts only. Don't change it after seeing accuracy scores.
- Report versions (`ml_models.is_report`) own the 4–7 Nov figures; `v_forecasts_all` prefers them, so never rescore the window with a newer version.
- Don't add `set search_path` to small inlinable SQL helpers like `lead_bucket()`: it blocks inlining and made `v_pairs` ~4× slower.
