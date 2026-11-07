# Iskandar Weather Watch — Implementation Plan

**v2.0 · 7 Nov 2026 · Due Sun 8 Nov 2026, 23:59 MYT · Scope: data retrieved from Wed 4 Nov, one trained temperature model, three-page dashboard · Status: Supabase live with migrations `0001`–`0005` applied; first local ingestion done; no retrieved data yet; jobs not scheduled (A3–A4)**

This plan turns [architecture.md](architecture.md), [api-spec.md](api-spec.md), [spec.md](spec.md) and [tasks.md](tasks.md) into a build order and a concrete design for this repository. Where they disagree, this plan decides **what gets built and where**, and the other docs still decide **how it behaves**. §5.1 records every gap in the docs that this plan fills.

---

## 1. Decisions taken

Decisions 1, 3, 4, 5, 6, 7 and 8 were set or replaced on 7 Nov 2026 (v2.0). They override the earlier "≤ 7 days" scope, the 235 K rain rule and the "no ML training" rule.

| # | Decision | Consequence |
|---|---|---|
| 1 | **Deadline Sun 8 Nov 2026, 23:59 MYT** | About 34 hours from this revision (Sat 7 Nov, 13:30 MYT). Only the scope below gets built |
| 2 | **Keep the existing folders** (`client/`, `server/`, `database/`) | Doc paths are remapped (§2) |
| 3 | GitHub repo, Render account and Supabase project **exist**. The local repo has no commits and no remote | Pushing the repo is now the critical path (§3). NASA Earthdata isn't needed |
| 4 | **Data is retrieved retrospectively from Wed 4 Nov, then collected live.** The project uses no hardware: every source is a public service that keeps its own history, so past values can still be fetched | A one-off import loads the past (§5.3). `observe` and `forecast` also run live from today. Retrieved rows stay marked as such (`is_backfill`, `origin = 'previous_runs'`) and the report says so. The owner has decided this needs no lecturer sign-off (§9) |
| 5 | **Frozen report window: Wed 4 Nov 00:00 → Sat 7 Nov 00:00 MYT** (72 h, 3 full days). If the data check in §5.3 fails, it extends back to **Sun 1 Nov 00:00** (144 h) | The rule is based on data quantity only, is set before any scores are seen, and is applied once |
| 6 | **Train one model on history:** temperature bias correction on Open-Meteo Previous Runs data, up to 31 Oct 2026, tested on the frozen window | The test data stays unseen under either window. It appears as `best_match+ml` on the leaderboard (§5.4) |
| 7 | **Himawari and the 235 K rule are dropped.** The rain lamp shows Open-Meteo's own rain probability, labelled as such | Phase 2 is cancelled. No satpy, and the Rain & Satellite page stays out of scope |
| 8 | **Accuracy in the frozen window covers leads of 1–6 days only.** Previous Runs has no forecasts under 24 h, no rain probability, and no ICON values at day 7 | Short leads and Brier come only from live data after the window, and are reported separately |
| 9 | **Pulled forward from P1:** the `om_gapfill` and `retention` steps of the daily `backfill` job | Late GitHub runs drop 15-min samples, and pairs need `samples = 4` per hour. Without gap fill, many hours would never be verified |
| 10 | UI primitives (popover, chips, slider, select) are **hand-built on Radix primitives**, not generated with the shadcn/ui CLI | Less setup. They look the same, since both are styled through the spec's CSS variables |
| 11 | RPC row types are **hand-written** in `lib/types.ts` from api-spec §3 | `supabase gen types` needs the Supabase CLI and Docker, and neither is set up |

**Out of scope** (only if everything else is done early, in this order): About page → humidity and wind bias models → skill vs persistence and error heatmap → capture mode. Not at this scope: Himawari, satellite-trained nowcast, IMERG, FastAPI, the ML Lab, the Rain & Satellite page, live ML scoring, CNN training, storm replay, AIFS/JMA.

---

## 2. Repository layout

| Docs path | This repo | Status at this scope |
|---|---|---|
| `supabase/migrations/` | `database/migrations/` | `0001`–`0005` built and applied live; `0006` to do |
| — | `database/test/` (PGlite harness) | Built (new) |
| `ingest/` | `server/ingest/` | Built, except the v2.0 import steps |
| `ml/` | `server/ml/` | To do (the folder is empty) |
| `api/` | `server/api/` | Not at this scope |
| `models/` | `server/ml/models/` | To do |
| `web/` | `client/Iotweatherproject/` | To do (still the Vite vanilla starter) |
| `.github/workflows/` | `.github/workflows/` | Written; has never run |

Target layout, with files still to create marked `+`:

```
IoT Weather Project/
├─ .github/workflows/   observe.yml · forecast.yml · backfill.yml · ci.yml
├─ database/
│  ├─ migrations/       0001_core.sql · 0002_views.sql · 0003_rpc.sql · 0004_rls.sql · 0005_seed.sql · +0006_retro_window.sql
│  └─ test/             package.json · db.mjs · serve.mjs · core.test.mjs · views.test.mjs · rpc.test.mjs · perf.test.mjs
├─ server/
│  ├─ ingest/
│  │  ├─ pyproject.toml · requirements.txt · requirements-dev.txt
│  │  ├─ iww_ingest/
│  │  │  ├─ config.py · db.py · http.py · runlog.py · timeutil.py
│  │  │  ├─ sources/   openmeteo.py · metar.py
│  │  │  ├─ jobs/      _common.py · observe.py · forecast.py · backfill.py
│  │  │  └─ tools/     check.py · migrate.py
│  │  └─ tests/         fixtures/*.json · test_*.py
│  └─ ml/               +requirements-ml.txt · +train_bias.py · +score_window.py · +models/bias_temperature/v1.0/ · +notebooks/00_sanity.ipynb
├─ client/Iotweatherproject/   React dashboard (§5.6)
├─ docs/                architecture.md · api-spec.md · spec.md · tasks.md · Implementation-plan.md
├─ +render.yaml · README.md · .env.example · .gitignore · claude.md
```

---

## 3. Your actions (blockers)

The remaining actions need your login, so I can't do them. **A3–A4 are the critical path:** until they're done, the live jobs only run when started by hand.

| # | When | Action | Done when |
|---|---|---|---|
| A1 | ☑ Done 7 Nov | Supabase project in Singapore, `.env` at the repo root | The file exists |
| A2 | ☑ `0001`–`0005` applied 7 Nov | `0006` still has to be applied after T3.4′, with `python -m iww_ingest.tools.migrate` | `0006` applied |
| **A3** | **Sat afternoon, now** | GitHub repo → Settings → Secrets and variables → Actions: add `SUPABASE_DB_URL` (pooler URI) and `CONTACT_EMAIL` | Both are listed |
| **A4** | After A3 | Commit and push this repo to the GitHub repo's `main` branch (scheduled workflows only run on the default branch) and enable Actions if prompted | `observe` and `forecast` show green scheduled runs |
| A5 | Sat night | Render → New → Static Site from the repo (settings in §5.7) | The URL loads and `/accuracy` doesn't 404 |

---

## 4. Schedule and exit criteria

| Block | When (MYT) | Build | Exit criterion |
|---|---|---|---|
| B1 | Sat 7 Nov, until 16:00 | A3–A4, import steps R1–R3, the one-off import of 1–7 Nov | Rows in `observations` and `forecasts` for every day of the window; live jobs green |
| B2 | Sat, 16:00–18:00 | `0006_retro_window.sql`, the data check | Window confirmed and written in §10 **before any score is looked at** |
| B3 | Sat, 18:00–20:00 | Train and score the temperature model | `card.json` written; `best_match+ml` on the leaderboard |
| B4 | Sat, from 20:00 | Dashboard shell, shared components, **deploy**, Overview | Public URL works; Overview shows real data in both themes |
| B5 | Sun 8 Nov, morning | Accuracy, Data Health, sanity notebook | Lead slider changes the chart and the URL; pandas matches the RPCs to 3 decimals |
| B6 | Sun, afternoon | Screenshots, report | Every figure captured; report drafted |
| B7 | Sun, evening | Video, zip, **submit by 21:00** | Submitted, leaving about 3 hours spare before 23:59 |
| — | After submission | — | Jobs keep running until grading ends |

**Data window (T8.1):** **Wed 4 Nov 00:00 → Sat 7 Nov 00:00 MYT**, or **Sun 1 Nov 00:00 → Sat 7 Nov 00:00 MYT** if the data check fails (§5.3). Live data from 7 Nov onward sits outside this window. It can be reported separately, but it's never mixed into the frozen figures.

**If a block overruns:** drop these in order: the Data Health coverage grid, then the Overview "next 24 h" chart, then the sanity notebook's rain metrics (keep MAE and bias). **Hard stop for training:** if B3 isn't finished by Sat 20:00, stop and start the dashboard, because the dashboard carries more marks than the model.

---

## 5. Design

### 5.1 Database (`database/migrations/`)

| File | Contents | Applied |
|---|---|---|
| `0001_core.sql` | The 11 tables and indexes of architecture §7.1–7.6, verbatim | D1 |
| `0004_rls.sql` | RLS on every table, `select` policies for `anon` and `authenticated`, explicit grants, revokes on `raw_responses`. The `api_reader` role stays commented out | D1 |
| `0005_seed.sql` | 1 location, 4 sources, 6 forecast models (4 active), the `v0-rule` nowcast | D1 |
| `0002_views.sql` | `lead_bucket()`, `v_actual_hourly`, `v_forecasts_all`, `v_pairs`, `v_now`, `v_rain_status`, `v_collection_window`, `v_coverage_daily` | D2 |
| `0003_rpc.sql` | Helpers `v_rain_pairs` and `iww_nominal_slot()`, then `rpc_forecast_vs_actual`, `rpc_metrics_by_lead`, `rpc_rain_contingency`, `rpc_brier`, `rpc_reliability`, `rpc_leaderboard`, `rpc_daily_pairs`, `rpc_kpis`, `rpc_next_24h`, `rpc_uptime_daily`, `rpc_runs_timeline` | D2–D3 |
| `0006_retro_window.sql` | The changes below, needed for retrieved data | B2 |

**What `0006_retro_window.sql` changes**

| Object | Change | Why |
|---|---|---|
| Accuracy RPCs and `rpc_kpis` | Read `origin in ('snapshot', 'previous_runs')`, not only `snapshot` | Every forecast in the frozen window is `previous_runs`, so today these return nothing. The two can't double count: the import stops at 7 Nov 00:00 and live snapshots start after it |
| `rpc_kpis` | `temperature` and `rain` use bucket `024-048`, not `012-024` and `000-006`. `brier` uses live snapshots only, and is null until they exist | The window has no leads under 24 h and no rain probability (Decision 8) |
| `rpc_leaderboard` | Compares models at leads of 24–144 h only | ICON has no day-7 values, so all models must be scored on the same leads |
| `v_collection_window` | Adds `live_since` (first row with `is_backfill = false`) and `backfilled_samples` | The streak now includes retrieved rows, so the page must be able to show which part was live |
| `v_coverage_daily` | Starts at the first `openmeteo_current` row, not the first job run. `forecast_best_match` counts both origins | Otherwise the imported days wouldn't appear at all |
| `v_rain_status` | Rebuilt on `forecasts`: the next hour's `precip_probability_pct` from the newest `best_match` snapshot. WATCH ≥ 30 %, RAIN_LIKELY ≥ 60 %, UNKNOWN if the newest run is over 2 h old. `model_version` returns `open-meteo` | Decision 7. The output columns stay the same, except that `prob_1h_smoothed` equals `prob_1h` |

**Conventions**

- Views are `with (security_invoker = true)`. Functions are `language sql stable security invoker set search_path = public`.
- **Each file grants its own objects** (`grant select on <views>`, `grant execute on <functions> to anon, authenticated`). The live DB receives `0004` *before* `0002`/`0003`, and a grant only covers objects that already exist.
- **Time zones are always explicit.** Hour buckets use `date_trunc('hour', ts, 'UTC')`, and local days use `(ts at time zone 'Asia/Kuala_Lumpur')::date`. Nothing depends on the session `TimeZone`.
- Ranges are `target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')`, with the indexed column filtered first.
- Once a file has been applied to the live DB it's frozen; fixes go in `0006_*.sql` and later files.

**Gaps in api-spec that this plan fills**

| Object | Rule chosen |
|---|---|
| `v_coverage_daily` | One row per (local day × stream) from the first observation to today. `satellite` counts distinct `slot_time`; `forecast_best_match` counts distinct `issued_at`. **Today's `expected` is prorated** by elapsed time, so the grid doesn't show today as a failure |
| `rpc_uptime_daily` | Counts `trigger = 'schedule'` runs only (manual dispatches don't inflate uptime). `expected` is prorated on the first day (from the first run) and on today. Nominal slots: observe `epoch ≡ 420 (mod 600)` (HH:M7), forecast `≡ 1020 (mod 3600)` (HH:17), backfill `≡ 70800 (mod 86400)` (19:40 UTC). Start delay = `started_at − nominal slot at or before it` |
| `rpc_kpis` | `collection` from `v_collection_window` plus observe uptime over the range. Lead buckets as changed by `0006` above: `temperature` and `rain` = best_match, `024-048`; `brier` = best_match, live leads ≤ 24 h. `best_model` = lowest temperature MAE / highest rain CSI at leads ≤ 72 h among models with `n ≥ 20` (null if none qualify yet) |
| `rpc_rain_contingency`, `rpc_brier`, `rpc_reliability` | Join `v_forecasts_all` to `v_actual_hourly.rain_hour` directly, not through `v_pairs`. `v_pairs` has no `rain_hour`, and METAR has rain flags but no millimetres |
| `rpc_daily_pairs` | Forecast = **earliest** `forecasts_daily` row with `lead_days = p_lead_days` for each `target_date`. Observed max/min/total come from hourly actuals of local day D (hours 01:00–24:00 MYT, the `(H−1h, H]` rule). Observed columns are null when `hours_complete < 22`; `hours_complete` is always returned so the UI can show the "partial" tag |
| `rpc_leaderboard` | `rank()` per metric (ascending MAE and Brier, descending CSI), with `rank_overall` = mean of the non-null ranks |
| `lead_bucket()` | **No `set search_path`**: the clause blocks inlining, and the per-row function call made `rpc_metrics_by_lead` take 1.8 s instead of 0.4 s on 7 days of data |
| `rpc_kpis` | Queries only the rows each tile needs and computes the leaderboard once (2.3 s → 0.3 s) |

### 5.2 Ingestion package (`server/ingest/iww_ingest/`)

| Module | Responsibility | Key functions |
|---|---|---|
| `config.py` | Constants and environment. Location (4.35993 N, 100.98491 E), upstream URLs, variable lists (api-spec §5), the default model list for DB-less dry-runs, `CACHE_DIR = server/ingest/.cache`, rain thresholds. Reads `SUPABASE_DB_URL`, `CONTACT_EMAIL`, `GH_RUN_ID`, `IWW_LOG_LEVEL`, and a local `.env` when present | `settings()` |
| `db.py` | One psycopg 3 connection per job. `upsert()` sends multi-row chunks of 500 (the pooler is ~200 ms from GitHub's runners) and counts written rows with `RETURNING`. Autocommit, `application_name='iww-<job>'`, 60 s statement timeout, `prepare_threshold=None` (safe even if someone pastes the transaction-pooler URL). dicts and lists are adapted to `jsonb` | `connect()`, `upsert(conn, table, rows, key, on_conflict='nothing' \| 'update', update_cols=None) → int` |
| `http.py` | Shared `requests.Session`: 15 s timeout; 3 retries with 1/3/9 s backoff on 5xx, timeouts and connection errors, never on 4xx; `User-Agent: iww-ingest/1.0 (student project; <CONTACT_EMAIL>)` | `get_json(url, params) → (data, status, url)`, `get_bytes(url)`, `list_s3(prefix)` |
| `runlog.py` | `ingestion_runs` lifecycle. Each step runs in its own transaction, so a failure rolls back only that step | `RunLog(conn, job, trigger, gh_run_id, dry_run)`, `with log.step(name):`, `log.rows(table, n)`, `log.finish() → status`, `exit_code(status)` |
| `timeutil.py` | Open-Meteo local time → UTC via `utc_offset_seconds`; floor to hour or 10 min; MYT date of a UTC instant | `om_local_to_utc()`, `floor_to()`, `myt_date()` |
| `sources/openmeteo.py` | `current`, forecast vault, `meta.json`, `minutely_15` gap fill, 700 hPa context | `fetch_/parse_current`, `fetch_/parse_forecast`, `fetch_meta`, `fetch_/parse_minutely15`, `fetch_context` |
| `sources/metar.py` | WMKI reports → rows: kt × 1.852, Magnus RH, `VRB` → null direction, `wxString` flags | `fetch()`, `parse_report()`, `magnus_rh()`, `wx_flags()` |
| `jobs/*.py` | The three jobs (below), each with the api-spec §6 CLI | `main(argv)` |
| `tools/check.py` | Daily sanity: row counts per table, last run per job, current streak. **New:** `--window <from>,<to>` prints the data check counts (§5.3) | `main()` |
| `tools/migrate.py` | Applies named migration files in order, each in one transaction (there's no `psql` on this machine) | `main(files)` |

**Upsert policy (idempotency)**

| Table · writer | Unique key | On conflict | Reason |
|---|---|---|---|
| `observations` · `om_current` | (location, source, observed_at) | do nothing | Keep the value as first seen live |
| `observations` · `om_gapfill` | same | do nothing, `is_backfill = true` | Only fill holes. The daily run stays **after the first live sample**. The one-off import passes `--since`, which lifts that limit and keeps `is_backfill = true` |
| `observations` · `metar` | same | update | Corrected reports (`COR`) replace the original |
| `observations` · `metar_history` | same | update, `is_backfill = true` | Same parser as `metar`, with `hours=170` |
| `forecasts`, `forecasts_daily` · `vault` | (location, model, origin, issued_at, target_time / target_date) | do nothing | `issued_at` means "first obtained" |
| `forecasts` · `previous_runs` | same, `origin = 'previous_runs'` | do nothing | `issued_at = target_time − N days` is approximate, and says so in the report |
| `predictions` · `score_window` | (location, model_id, variable, issued_at, target_time) | update | Re-scoring after a fix replaces the old value |
| `raw_responses` | — | plain insert | It's a log |

**Jobs**

| Job | Steps (each independent) | Notes |
|---|---|---|
| `observe` | `om_current` → `metar` | The Himawari and nowcast steps are cancelled (Decision 7) |
| `forecast` | `model_runs` → `vault` | `model_runs`: a model is due if its `meta.json` `last_run_initialisation_time` > the newest stored `model_run_at`; `best_match` is always due; a meta failure makes that model due every hour, with a warning. `vault`: one request for all due models, unpacking `<var>_<model>` keys longest-suffix-first (bare keys when there's only one model); keeps `target_time ≥ issued_at`; writes 1 `raw_responses` row |
| `backfill` | `om_gapfill` → `retention` | `om_gapfill`: `minutely_15`, `past_days=2`, only times ≤ now. `retention`: delete `raw_responses` older than 30 days, then `VACUUM (ANALYZE)` the hot tables |
| `backfill` (one-off import) | `om_gapfill` → `metar_history` → `previous_runs` | Run once locally with `--since` and `--until` (§5.3). Logged to `ingestion_runs` with `trigger = 'local'`, so it never counts toward uptime |

**CLI and exit codes:** exactly api-spec §6. `--dry-run` fetches and parses, prints row counts plus one sample row per table, and writes nothing. It runs without `SUPABASE_DB_URL` (every model is treated as due) and uses the DB read-only when the URL is set. The `trigger` defaults to `schedule` or `dispatch` from `GITHUB_EVENT_NAME`, and `local` otherwise. Exit `0` on `success` or `partial`, `1` on `failed`.

**Dependencies:** `requirements.txt` = `psycopg[binary]`, `requests`, `python-dotenv`. `requirements-dev.txt` = `pytest`. `server/ml/requirements-ml.txt` = `lightgbm`, `pandas`, `numpy`, `scikit-learn`, used on the laptop only and never installed by the scheduled jobs.

### 5.3 Retrieving the past data

**What's available.** Checked live on 7 Nov 2026 for 1–6 Nov:

| Data | Source | Coverage | Limit |
|---|---|---|---|
| 15-min "actual" | Open-Meteo `minutely_15` with `past_days=7` | 96 samples a day back to 31 Oct | The same values `om_gapfill` uses |
| METAR WMKI | aviationweather.gov, `hours=170` | Back to 31 Oct 04:00 UTC | **This archive rolls forward, so run the import on Sat 7 Nov** |
| Forecasts | Previous Runs, `<var>_previous_day1..7`, all 4 models | Temperature, humidity, wind, pressure and precipitation complete | Leads ≈ 24 × N h only. `precipitation_probability` is empty for every model. ICON has no day 7 |

**The import.** It loads from 1 Nov so the fallback window needs no second run, and stops where the live vault starts:

```sh
python -m iww_ingest.jobs.backfill --since 2026-11-01 --until 2026-11-07 --steps om_gapfill,metar_history,previous_runs
```

`--since` and `--until` are local MYT dates. The job is idempotent, so it's safe to re-run. `forecasts_daily` has no archived source, so `rpc_daily_pairs` has no data in the window and the Next-day table is dropped (§5.6).

**The data check (T8.1).** Written on 7 Nov, before any scores exist. Run `python -m iww_ingest.tools.check --window 2026-11-04,2026-11-07`, which prints counts only. 4–7 Nov is used if **all three** pass:

| Check | Pass mark |
|---|---|
| Hours with `samples = 4` in `openmeteo_current` | ≥ 65 of 72 (90 %) |
| Hours with observed rain (`rain_hour`) | ≥ 6 |
| Paired hours at day-1 lead, for each of the 4 models | ≥ 60 |

If any fails, the window becomes **1–7 Nov**. This decision is made once and written in §10. The window doesn't change again, and accuracy scores play no part in it.

**How it's described.** The report, video and dashboard call this data **retrieved**, not continuously collected. Only rows after `live_since` are live collection.

### 5.4 Temperature model

| Item | Specification |
|---|---|
| Target | Residual `truth − raw forecast` for temperature, `best_match` |
| Data | ✔ Previous Runs, `best_match`, 1 Mar 2024 → 31 Oct 2026: 23,400 hours × 7 day-leads, about 164k rows. Forecast = `temperature_2m_previous_dayN`; truth = plain `temperature_2m` (day 0) |
| Features | Raw forecast, `lead_hours` (24 × N), local hour (sin/cos), day of year (sin/cos), forecast humidity, wind and precipitation. Forecast rain probability is excluded because Previous Runs doesn't have it |
| Model | LightGBM regression, L1 objective, early stopping on validation |
| Split | Time-blocked, no shuffling. Train 1 Mar 2024 → 30 Jun 2026, validate 1 Jul → 31 Oct 2026, test = the frozen window. Nothing from Nov 2026 is used in training, so **both** candidate windows stay unseen |
| Baselines | The raw forecast, and a constant bias per lead day taken from the training set |
| Done when | Validation MAE per lead day is recorded in `card.json`. If the model doesn't beat the raw forecast, it's still reported, with that result stated |
| Output | `models/bias_temperature/v1.0/model.txt` + `card.json`, one `ml_models` row (`bias_temperature`, active) |
| Scoring | `server/ml/score_window.py` runs once locally. It writes `predictions` for `best_match` at leads 24–168 h over 1–7 Nov. `v_forecasts_all` then exposes them as `best_match+ml`. There's no live scoring |

**Known limits, stated in the report:** day-0 truth is a model analysis, not an instrument. The model only covers leads of 1–7 days. The test window is too short to show seasonal behaviour.

### 5.5 Workflows (`.github/workflows/`)

| File | Trigger | Timeout | Installs | Secrets |
|---|---|---|---|---|
| `observe.yml` | `7-59/10 * * * *` + dispatch | 8 min | core | `SUPABASE_DB_URL`, `CONTACT_EMAIL` |
| `forecast.yml` | `17 * * * *` + dispatch | 10 min | core | same |
| `backfill.yml` | `40 19 * * *` (03:40 MYT) + dispatch | 20 min | core | same |
| `ci.yml` | push + PR | 10 min | dev requirements, Node 24 | none |

The three jobs all use `concurrency: { group: <job>, cancel-in-progress: false }`, `setup-python` 3.11 with the pip cache, and `GH_RUN_ID: ${{ github.run_id }}`. `ci.yml` runs `pytest` (unit tests only), the PGlite tests in `database/test`, and `npm ci && npm run build` in the client.

### 5.6 Dashboard (`client/Iotweatherproject/`)

**Stack** (current stable versions, pinned at install in B4): React · Vite 8 (already in the starter) · TypeScript (the starter pins `~7.0`; drop to the latest 5.x if `@vitejs/plugin-react` or the type check complains) · Tailwind v4 (`@tailwindcss/vite`) · React Router · TanStack Query · `@supabase/supabase-js` · ECharts via `echarts/core` · `lucide-react` · `date-fns` + `date-fns-tz` · Radix `popover`, `slider` and `tooltip` primitives · `@fontsource` Fraunces, IBM Plex Sans and IBM Plex Mono.

```
src/
├─ main.tsx
├─ app/        App.tsx · router.tsx · providers.tsx · AppShell.tsx · TopBar.tsx · Footer.tsx
├─ pages/      Overview.tsx · Accuracy.tsx · Health.tsx
├─ components/ ChartCard · KpiTile · RainLamp · StatusPill · FreshnessBadge · EmptyState · Skeleton
│              ModelChips · VariableTabs · TruthSelect · LeadSlider · MetricTable
│              InfoPopover · ThemeToggle
├─ charts/     echarts.ts (registrations) · useEChart.ts · themes.ts · nightShading.ts
│              options/ next24h · forecastVsActual · errorVsLead · uptime · coverage
├─ lib/        supabase.ts · rpc.ts · queries.ts · types.ts · fmt.ts · wmo.ts · urlState.ts
│              glossary.ts · constants.ts (models, series colours, lead stops, FROZEN_WINDOW)
└─ theme/      tokens.css (spec §6.5) · index.css (Tailwind + fonts)
```

**Data layer**

- `rpc<T>(name, params)` wraps `supabase.rpc` and throws the PostgREST error, which the card shows with its code (e.g. `57014`).
- Query keys are `['rpc', name, params]`. Refetch: `v_now` and `v_rain_status` every 60 s; Health every 2 min; metrics every 10 min; `rpc_forecast_vs_actual` only on filter change.
- URL state: `?var&models&lead&truth`, read and written by `useUrlState()`. The date range is the fixed `FROZEN_WINDOW` constant, with no date picker. It's set from the data check result (§5.3).
- All formatting goes through `fmtMYT()` and the number rules in spec §6.1. Raw `Date#toString()` is never shown.

**Pages and panels.** The top bar has three tabs only: Overview, Accuracy and Data Health.

| Page | Panel | Data | Component / chart | Must-have interaction |
|---|---|---|---|---|
| Overview | Now | `v_now` | Now card + METAR cross-check line | ⓘ "what actual means" |
| | Rain indicator | `v_rain_status` | `RainLamp` (lg), captioned "Open-Meteo rain probability" | `aria-live` on level change |
| | KPI row | `rpc_kpis` | 5 × `KpiTile` | Tile → source chart |
| | Next 24 h | `rpc_next_24h` | line + probability bars + WMO icons | Hover tooltip |
| Accuracy | Filter bar | `forecast_models`, `sources` | `VariableTabs`, `ModelChips` (≤ 5), `TruthSelect`, `LeadSlider` (24–144 h, steps of 24) | Every change updates the URL |
| | Forecast vs actual | `rpc_forecast_vs_actual` × selected models | line (bars for rain) + dataZoom | Lead slider moves the line |
| | Error vs lead | `rpc_metrics_by_lead`, including `best_match` vs `best_match+ml` | line + symbols ∝ √n | MAE / Bias / RMSE toggle; `n < 20` faded |
| | Leaderboard | `rpc_leaderboard` | `MetricTable`, with an "ML" chip on the `+ml` row | Sortable; best per column in gold with ★ |
| Health | Banner | `v_collection_window` | banner, worded as in spec §4.5 | — |
| | Daily uptime | `rpc_uptime_daily` | stacked bars | Job filter |
| | Coverage grid | `v_coverage_daily` | heatmap, gold scale, "B" on retrieved days | Hover counts |
| | Latest runs | `ingestion_runs` (50 newest) | `MetricTable` | GitHub run link |

Dropped at this scope: mini map, Overview "last 72 h" chart, Next-day table, run timeline.

**Every card** has loading (skeleton), empty (spec §8 copy) and error (code + retry) states, shows `n`, and has an ⓘ glossary popover. CSV download, the "view as table" toggle and fullscreen are dropped at this scope.

**Theming:** `tokens.css` holds both themes from spec §6.5 on `:root[data-theme]`. Tailwind maps the variables to utilities in `@theme`. `themes.ts` builds the ECharts dark and light themes from the same values. The first visit follows `prefers-color-scheme`, and the choice is saved in `localStorage`.

**Performance:** routes are lazy-loaded; ECharts registers only line, bar and heatmap charts. The budget is < 450 KB gzipped on first load, checked with `vite build` output.

### 5.7 Deployment (`render.yaml`, static site only)

`rootDir: client/Iotweatherproject`, build `npm ci && npm run build`, publish `dist`, rewrite `/*` → `/index.html`, `Cache-Control: public, max-age=31536000, immutable` on `/assets/*`, env `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` (`sync: false`). No card on Render.

---

## 6. Task checklist

Status: ☐ to do · ◐ drafted, not yet verified · ☑ done (with evidence in §10) · ✕ cancelled in v2.0.

### Phase 0 — Setup

| ID | Task | Done when | Status |
|---|---|---|---|
| T0.1 | `git init`, `.gitignore`, `README.md`, `.env.example`, `claude.md` | Files present; `.env` ignored | ☑ |
| T0.2 | Supabase project (A1) | `.env` holds the pooler URI | ☑ |
| T0.3 | GitHub Secrets (A3) | Both secrets listed | ☐ you |
| T0.5 | Render account | Exists | ☑ |

### Phase 1 — Ingestion

| ID | Task | Done when | Status |
|---|---|---|---|
| T1.1 | `0001_core.sql`, `0004_rls.sql`, `0005_seed.sql` | They apply in PGlite in both orders; anon can `select` but not `insert`; `raw_responses` is hidden from anon | ☑ |
| T1.2 | `config`, `db`, `http`, `runlog`, `timeutil`, packaging | `upsert()` twice → same row count (PGlite socket) | ☑ |
| T1.3 | Open-Meteo `current` + `observe` step 1 | Dry-run prints 1 row; `observed_at` = `current.time` in UTC | ☑ |
| T1.4 | METAR + `observe` step 2 | Tests for kt → km/h, Magnus, `-RA` / `TSRA` / `VCSH` / missing; live dry-run parses rows | ☑ |
| T1.5 | `forecast` job (`model_runs`, `vault`) | ~168 hourly rows per due model + 7 daily; an immediate re-run writes only `best_match` | ☑ (locally) |
| T1.6 | `observe.yml`, `forecast.yml`, `ci.yml` | 3 consecutive green scheduled runs each (after A4) | ◐ (written; needs A3–A4) |
| T1.7 | 🕐 **Live collection started** | Start time written in §10 | ◐ (first sample Sat 7 Nov 13:15 MYT, by hand; scheduled runs need A3–A4) |
| T1.8 | Hour bucketing check | PGlite: 4 samples → 1 hour with `samples = 4` and the right precipitation sum | ☑ |
| T2.5′ | `backfill` (`om_gapfill`, `retention`) + `backfill.yml` | A deleted 15-min row is restored with `is_backfill = true` | ☑ (locally) |
| T3.6 | `tools/check.py`, `tools/migrate.py` | Prints counts, last runs, streak | ☑ |

### Phase 2 — Retrieve the past data (replaces Satellite + v0 rain indicator)

| ID | Task | Done when | Status |
|---|---|---|---|
| T2.1 – T2.4 | Himawari, masks, features, v0 rule | — | ✕ |
| R1 | `backfill` flags `--since` / `--until`, `om_gapfill` limit lifted for imports | Dry-run over 1–7 Nov prints the expected row counts; tests green | ☐ |
| R2 | `metar_history` step | Rows reach back to 1 Nov | ☐ |
| R3 | `previous_runs` step (4 models, N = 1–7, `origin = 'previous_runs'`) | Re-run writes 0 duplicates | ☐ |
| R4 | Run the import against Supabase **on Sat 7 Nov** | All 3 steps logged in `ingestion_runs` | ☐ |
| R5 | `tools.check --window` and the data check (§5.3) | Result and window written in §10, before any score is viewed | ☐ |

### Phase 3 — Analytics

| ID | Task | Done when | Status |
|---|---|---|---|
| T3.1 | `0002_views.sql` base views | `views.test.mjs` green; `v_pairs` > 0 rows live | ☑ (locally) |
| T3.2 | `0003_rpc.sql` part A (accuracy RPCs + `rpc_kpis`, `rpc_next_24h`) | `rpc.test.mjs` green; < 1 s as anon live (**V6**) | ☑ (locally) |
| T3.3 | `v_rain_status`, `v_collection_window`, `v_coverage_daily`, `rpc_uptime_daily`, `rpc_runs_timeline` | Same | ☑ (locally) |
| T3.4′ | `0006_retro_window.sql` (§5.1) | New PGlite tests green; every RPC returns rows for a `previous_runs`-only window | ☐ |
| T3.5 | `00_sanity.ipynb` | pandas MAE / bias / CSI = RPC output to 3 decimals | ☐ |

### Phase 5 — Temperature model

| ID | Task | Done when | Status |
|---|---|---|---|
| M1 | `server/ml/train_bias.py`: fetch history, build features, time-blocked split | Test proves no training row is dated after 30 Jun 2026 and no validation row after 31 Oct 2026 | ☐ |
| M2 | Train, compare with both baselines, write `model.txt` + `card.json` | Validation MAE per lead day recorded | ☐ |
| M3 | Register in `ml_models`; `score_window.py` writes `predictions` | `best_match+ml` appears in `rpc_leaderboard` | ☐ |

### Phase 4 — Dashboard

| ID | Task | Done when | Status |
|---|---|---|---|
| T4.1 | Replace the starter; install the stack (§5.6) | `npm run build` passes in CI | ☐ |
| T4.2 | Tokens, theme toggle, `AppShell`, top bar, tabs, footer | Contrast spot-check passes in both themes | ☐ |
| T4.3 | `render.yaml`, Render deploy (A5) | URL recorded in §10; deep link works | ☐ |
| T4.4 | Shared components, `useEChart`, `fmtMYT`, glossary, URL state | Used by all three pages | ☐ |
| T4.5 | Overview | Live data, both themes, all card states | ☐ |
| T4.6 | Accuracy | Lead slider changes the line and the URL | ☐ |
| T4.7 | Data Health | Retrieved vs live data and per-job uptime visible | ☐ |

### Phase 8 — Freeze, report, video, submit

| ID | Task | Status |
|---|---|---|
| T8.1 | Freeze the window from R5 in `FROZEN_WINDOW` | ☐ |
| T8.2 | Screenshots: Overview · forecast vs actual + error vs lead · leaderboard with `best_match+ml` · Health banner + uptime · sanity comparison | ☐ |
| T8.3 | Report ≤ 8 pages, Arial 11, IEEE refs at 8 pt, rubric on the last page. States that the window was retrieved, and how | ☐ |
| T8.4 | Video ≤ 2 min, following the tasks.md demo script | ☐ |
| T8.5 | `git archive --format=zip -o iww-source.zip HEAD`; no `.exe`, `.dll` or secrets | ☐ |
| T8.6 | Submit; jobs keep running | ☐ |

---

## 7. Test inventory

| Suite | Cases | Runs in |
|---|---|---|
| `database/test/core.test.mjs` | Both migration orders apply; seeds; anon read-only; `raw_responses` hidden; `lead_hours` generated; one active ML model per name; T1.8 bucketing | CI + local |
| `database/test/views.test.mjs` | Lead-bucket edges (5 → `000-006`, 6 → `006-012`, 167 → `120-168`); incomplete hours excluded from `v_pairs`; `v_now` picks the newest row per source; collection streak breaks on a gap > 1 h | CI + local |
| `database/test/rpc.test.mjs` | Hand-computed MAE / bias / RMSE; a contingency table with known a/b/c/d → POD/FAR/CSI/HSS; Brier and reliability bins; leaderboard ranks; daily pairs with a partial day; uptime proration and start delay; every RPC callable as anon | CI + local |
| `database/test/perf.test.mjs` | 7 days of realistic volume (~42k forecast rows) → each RPC < 1 s (rough proxy for **V6**) | local |
| `server/ingest/tests/test_openmeteo.py` | Current → row (UTC, interval); multi-model key unpacking incl. `gfs_seamless` vs `best_match` suffixes; single-model bare keys; local → UTC; `target_time < issued_at` dropped; `lead_days` | CI |
| `server/ingest/tests/test_metar.py` | kt → km/h; Magnus; `VRB`; `-RA`, `+TSRA`, `TSRA`, `VCSH`, `TS`, missing `wxString` | CI |
| `database/test/retro.test.mjs` (new) | Every accuracy RPC returns rows for a `previous_runs`-only window; ICON's missing day 7 doesn't change the leaderboard's lead range; `live_since` ignores backfilled rows; `v_rain_status` thresholds and the 2 h `UNKNOWN` cutoff | CI + local |
| `server/ingest/tests/test_previous_runs.py` (new) | `<var>_previous_dayN_<model>` keys unpacked; `issued_at` = target − N days; null columns skipped; `--until` respected | CI |
| `server/ml/tests/test_train_bias.py` (new) | Split boundaries; features use no value from after `issued_at`; `predictions` rows have the right shape | local |
| `server/ingest/tests/test_runlog.py` | A failed step → `partial`; all failed → `failed` → exit code 1 | CI |
| `server/ingest/tests/test_db.py` | `upsert()` idempotency and conflict modes against PGlite (`npm run serve`) or `IWW_TEST_DB_URL`; skipped when neither is reachable | local |
| Live dry-runs | `observe`, `forecast`, `backfill` with `--dry-run` against the real APIs | local, before each push |

Fixtures in `tests/fixtures/` are recorded from the first live dry-runs, so the unit tests never need the network.

---

## 8. Risks and fallbacks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | The import isn't run on Sat 7 Nov | METAR history keeps rolling off | R4 runs in B1, before anything else that's optional |
| 2 | The temperature model overruns | The dashboard starts late | Hard stop on Sat evening (§4). The dashboard and report take priority |
| 3 | The model doesn't beat the raw forecast | No improvement to show | Report the result as it stands. It's still a valid out-of-sample test |
| 4 | Too little rain in the window | CSI is unreliable | Data check extends to 1–7 Nov (§5.3); `n` is always shown |
| 5 | `issued_at = target − N days` is only approximate | Lead buckets are approximate | State it in the report; leads are shown in whole days |
| 6 | GitHub cron starts late or skips | Missing 15-min samples, so live hours fail `samples = 4` | Poll every 10 min + daily `om_gapfill`; Health shows the real delay |
| 7 | Open-Meteo key format differs from the docs | Forecasts aren't stored | Longest-suffix parser + bare-key path, checked by the dry-run and fixtures |
| 8 | `meta.json` key doesn't match a seamless model (**V2**) | That model is stored hourly | Fall back to hourly with a warning (architecture §6.2); `n` is inflated for it, which the report states |
| 9 | An RPC exceeds the 3 s anon timeout (**V6**) | Card error `57014` | Filter `target_time` first; materialised view refreshed by `forecast` |
| 10 | TypeScript 7 / Vite 8 plugin incompatibility | Client build fails in B4 | Pin TypeScript 5.x and a matching plugin version |

---

## 9. Settled questions

| Question | Decision (7 Nov 2026) |
|---|---|
| Does retrieved data meet the brief? | **Yes, by the project owner's decision.** Sensors weren't affordable for the assignment, so public archives are the data source. Lecturer sign-off isn't being sought. The report still says how the data was obtained |
| Is a model analysis acceptable as "actual"? | Yes. The report explains it and METAR is the cross-check |
| Does the rubric page count toward 8 pages? | Treated as counting: the report stays within 8 pages including it |

---

## 10. Progress log

| When (MYT) | What | Evidence |
|---|---|---|
| 31 Oct | Plan v1.0 written; layout, deadline and accounts confirmed | this file |
| 31 Oct | Drafted before the pause: `git init` (no commits), `.gitignore`, `.env.example`, `README.md`, `0001_core.sql`, `0004_rls.sql`, `0005_seed.sql`, `database/test/` harness (`db.mjs`, `core.test.mjs`, PGlite installed). **The first test run was interrupted, so none of it is verified yet** | files on disk |
| 31 Oct | Plan v1.1: detailed design, gap rules, test inventory | this file |
| 31 Oct | **Phase 1 built.** Live dry-runs: `observe` 1 + 3 rows, `forecast` 616 hourly (4 models × 154 future h) + 28 daily, `backfill` 217 samples. Upstream contracts confirmed: multi-model keys are `<var>_<model>` for every model incl. `best_match`; single-model keys are bare; `meta.json` has `last_run_initialisation_time` for `ecmwf_ifs025`, `ncep_gfs025`, `dwd_icon` | `pytest`: 30 passed (25 unit + 5 DB) |
| 31 Oct | End-to-end against a PGlite server: a forecast re-run in the same hour finds only `best_match` due and writes 0 duplicates; a deleted 15-min sample is restored by gap fill; `tools.migrate` applies all 5 files to an empty DB; anon insert → `InsufficientPrivilege` | terminal output |
| 31 Oct | **Phase 3 SQL built** (`0002_views.sql`, `0003_rpc.sql`). Hand-computed metrics match (MAE 1.0, bias 0.5, RMSE √1.5, POD/FAR ½, CSI ⅓, Brier 0.225, BSS 0.1, uptime 138/144). V6 proxy on 7 days of data in PGlite: slowest calls are `rpc_metrics_by_lead` 420 ms, `rpc_kpis` 333 ms, `rpc_leaderboard` 220 ms | `npm test`: 39 passed |
| 7 Nov | **Supabase project created** (`iskandar-weather-watch`, ref `haclwpvxkkkghvpxgiai`, ap-southeast-1, Postgres 17). All 5 migrations applied in phased order, so they're now frozen (fixes go in `0006_*.sql`). As the public key: reads and RPCs return 200, `raw_responses` and inserts are refused with `42501`. `SUPABASE_DB_URL` still needed in `.env` (A1), so the data clock hasn't started | REST checks; security advisor shows only the two intentional items (`raw_responses` no policy, `lead_bucket` no `search_path`) |
| 7 Nov 13:27 | **First live ingestion, run locally** through the session pooler: `observe` 4 observations, `forecast` 620 hourly + 28 daily. First `openmeteo_current` sample 13:15 MYT. **Nothing is scheduled yet:** the repo has no commits or remote (A3–A4) | `tools.check`: runs 1–2 `success` |
| 7 Nov | Status check, taken before the Supabase work above: 13 of 35 tasks done, no live data, no commits, no remote | `npm test`: 39 passed; `pytest`: 25 passed, 5 DB tests skipped |
| 7 Nov 13:30 | **Plan v2.0.** Deadline set to Sun 8 Nov 23:59 MYT. Data retrieved from 4 Nov, then live. One trained temperature model. Himawari dropped. Window and data check set before any data from the window was loaded (the first stored sample is 13:15 today, after the window ends) | §1, §5.3, §5.4 |
| 7 Nov | Source availability checked live: `minutely_15` back to 31 Oct, METAR back to 31 Oct, Previous Runs complete for 4 models except ICON day 7, `precipitation_probability_previous_day*` empty, `best_match` history complete 1 Mar 2024 → 31 Oct 2026 | §5.3 |
| — | **Next:** A3–A4, then R1–R5 | — |
