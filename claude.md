# Iskandar Weather Watch

Weather monitoring + forecast-accuracy dashboard for Seri Iskandar. Read [docs/Implementation-plan.md](docs/Implementation-plan.md) first: it records scope (v2.0: due Sun 8 Nov 2026, data retrieved from 4 Nov, one temperature model, no Himawari), the folder mapping from the docs' paths, decisions, and progress.

## Layout

- `database/migrations/`: SQL, applied in phased order `0001 → 0004 → 0005 → 0002 → 0003 → 0006 → 0007`. Each file grants its own objects. Once a file is applied to the live DB, fixes go in a new numbered file.
- `database/test/`: PGlite (Postgres in WASM) tests. `npm test`; `npm run serve` exposes a migrated DB on port 5544 (`EMPTY=1` for an empty one).
- `server/ingest/`: Python 3.11 package `iww_ingest` (jobs `observe`, `forecast`, `backfill`; tools `check`, `migrate`).
- `server/ml/`: temperature bias-correction training and scoring, run on the laptop only, with its own `.venv`. `best_match` changed around Q3 2025, so training starts on 1 Oct 2025.
- `client/Iotweatherproject/`: React dashboard (Phase 4).

## Commands

```sh
cd server/ingest
.venv/Scripts/python -m pytest -q                                   # unit tests (DB tests skip without IWW_TEST_DB_URL)
.venv/Scripts/python -m iww_ingest.jobs.observe --dry-run           # live fetch + parse, no writes
IWW_TEST_DB_URL=postgresql://postgres@127.0.0.1:5544/postgres .venv/Scripts/python -m pytest -q   # with `npm run serve`
cd database/test && npm test
cd client/Iotweatherproject && npm run build
cd server/ml && .venv/Scripts/python -m pytest -q tests
```

## Conventions

- Store UTC; group local days with explicit `at time zone 'Asia/Kuala_Lumpur'`; hour H covers (H−1h, H].
- Jobs are idempotent (`db.upsert` with ON CONFLICT) and log every run to `ingestion_runs`.
- Retrieved data stays marked (`is_backfill`, `origin = 'previous_runs'`), and data before `live_since` is never described as live or continuous collection.
- The report window is frozen by the data check in plan §5.3, using counts only. Don't change it after seeing accuracy scores.
- Don't add `set search_path` to small inlinable SQL helpers like `lead_bucket()`: it blocks inlining and made `v_pairs` ~4× slower.
