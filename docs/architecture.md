# IoT Weather Project — Architecture

**v1.0 · RM0 free-tier stack · Solo build · Written 31 Oct 2026 from [plan.md](plan.md) and [suggestion.md](suggestion.md)**

> Companion docs: [api-spec.md](api-spec.md) (data contracts and endpoints) · [spec.md](spec.md) (dashboard UI) · [tasks.md](tasks.md) (build checklist).
> The project is called "IoT Weather Project". It was renamed on 9 Nov 2026 from the working name "Iskandar Weather Watch", which is where the `iww` prefix on internal names (`iww_ingest`, `IWW_*`) comes from.
> Facts marked ✔ were tested live on 30–31 Oct 2026. Items marked ⚠ still need checking during the build (see §15).

> **As built, 9 Nov 2026.** The build is smaller than the original design in this document. [Implementation-plan.md](Implementation-plan.md) records what was built and where. Sections and rows marked **Not built** describe the original design only. In short:
> - Data is **retrieved retrospectively from Wed 4 Nov**, then collected live. The project uses no hardware, and every source keeps its own history. Retrieved rows stay marked (`is_backfill`, `origin = 'previous_runs'`).
> - The report's frozen window is 4–7 Nov. The pre-set data check passed, so it was not extended to 1–7 Nov.
> - **Not built:** Himawari, IMERG, the reanalysis source, the rain nowcast, FastAPI, the ML Lab, and the Rain & Satellite and About pages. The rain lamp shows Open-Meteo's rain probability.
> - **Models:** temperature bias correction v1.0 gives the report's figure. Phase 5b added humidity, wind, pressure and rain-occurrence models plus temperature v1.1; a `score` job applies them to every new forecast and `retrain.yml` retrains them monthly (§6.6, §6.7, §9.2).
> - Paths are remapped: `server/ingest/`, `server/ml/`, `database/migrations/`, `client/Iotweatherproject/` (§14). The dashboard is hosted on **Vercel**, not Render (§13).

---

## 1. Goals and non-goals

**Goals**

1. Collect weather for Seri Iskandar **continuously for 3+ days**, aiming for 7–14, with an uptime record that *proves* continuity.
2. Store **forecasts as issued** (the forecast vault) next to **actuals from several sources**, so accuracy can be measured by variable, lead time, model and hour of day.
3. Compute accuracy metrics **inside the database** (views and RPC functions), so the dashboard and the report read the same numbers.
4. Show it all on an **interactive dashboard** at a public URL, including a satellite-driven "about to rain" indicator. *(Built as Open-Meteo's rain probability.)*
5. Two ML models: a **satellite + weather rain nowcast** and **forecast bias correction**. *(Built: bias correction for temperature, humidity, wind and pressure, and a rain-occurrence model. The nowcast is not built.)*
6. **RM0.** Every component runs on a free tier, with no card on file.

**Non-goals (for now):** an AI chat agent, a daily AI report, Telegram alerts, physical hardware, user accounts or login.

**Design rule:** every rubric-critical feature (ingestion, storage, accuracy, dashboard) must work **without FastAPI**. FastAPI sleeps on Render's free tier, so it serves only extras. *(FastAPI was not built.)*

---

## 2. Stack (all free)

| Layer | Choice | Why |
|---|---|---|
| Scheduler + jobs | **GitHub Actions** cron on a **public** repo, Python 3.11 | Free, unlimited minutes on public repos, 5-min minimum interval |
| Database | **Supabase Postgres** (free: 500 MB, PostgREST Data API) | SQL views for the metrics, an instant REST API for the browser, RLS |
| DB driver (jobs) | `psycopg` 3 through the Supabase **session pooler** | ✔ GitHub runners have no IPv6, and Supabase's direct connection is IPv6-only, so jobs **must** use the pooler URL |
| Satellite processing | **Not built.** `satpy` (`ahi_hsd` reader), `numpy`, `bz2` | Standard reader for Himawari HSD files |
| ML training | Python scripts in `server/ml/` on the laptop, and the monthly `retrain.yml` job: `lightgbm`, `pandas`, `numpy` | No GPU needed; LightGBM gives small, fast, explainable models |
| ML inference | The `score` job in GitHub Actions (`lightgbm`, `numpy`) | No always-on server needed |
| Frontend | React + Vite + TypeScript, Tailwind CSS, Radix primitives (popover, slider), React Router, TanStack Query, `supabase-js` | The user's usual stack |
| Charts | **Apache ECharts** (tree-shaken `echarts/core`) | Zoom, brush, heatmaps, large data, theming |
| Maps | **Not built.** Leaflet + `react-leaflet`, CARTO/OSM dark and light base tiles, **NASA GIBS** WMTS overlays | Free, and GIBS serves Himawari IR tiles with no key |
| Frontend hosting | **Vercel** (Hobby plan, static site) | The owner's choice (Implementation-plan decision 13) |
| Extras API | **Not built.** **FastAPI** on a free **Render Web Service** (512 MB, sleeps after 15 min) | ML explanations, live ROC/AUC, onset analysis, CSV export |
| Secrets | GitHub Actions Secrets, Vercel environment variables | Nothing secret in the repo |

---

## 3. System diagram

```mermaid
flowchart LR
  subgraph PER["Perception: virtual and remote sensors"]
    OMC["Open-Meteo current<br/>15-min analysis"]
    OMF["Open-Meteo forecast<br/>4 models, hourly + daily"]
    OMP["Open-Meteo Previous Runs<br/>past forecasts"]
    MT["METAR WMKI<br/>Ipoh airport station"]
  end

  subgraph GA["Processing: GitHub Actions (public repo)"]
    OBS["observe · every 10 min<br/>current + METAR"]
    FC["forecast · hourly<br/>forecast vault, then score (ML)"]
    BF["backfill · daily<br/>gap fill + retention"]
    RT["retrain · monthly<br/>challenger vs champion"]
  end

  subgraph DB["Application: Supabase Postgres"]
    T[("tables<br/>observations · forecasts · predictions<br/>ml_models · ingestion_runs")]
    V["views + RPC functions<br/>pairs · metrics · contingency · rain status · health"]
  end

  subgraph BIZ["Business: dashboard"]
    FE["React + ECharts<br/>Vercel static site"]
  end

  OMC & MT --> OBS
  OMF --> FC
  OMC --> BF
  OMP --> RT
  OBS & FC & BF -->|"idempotent upserts (pooler)"| T
  RT -->|"new model version, only if better"| T
  T --> V
  V -->|"PostgREST, anon key, read-only RLS"| FE
  ML["server/ml on the laptop<br/>training + one-off window scoring"] -.->|"ml_models row + artifact"| T
  OMP -.-> ML
```

### 3.1 Mapping to the 5-layer IoT model (report §3)

| Layer | Component | Notes |
|---|---|---|
| Perception | Open-Meteo "virtual sensors" (current analysis, forecasts, Previous Runs), METAR WMKI (real instruments) | Himawari and IMERG were designed as remote-sensing sensors but **not built** |
| Transport | HTTPS REST **pull** from every source (none offer webhooks); HTTPS + TLS to Supabase through the session pooler | Polling interval is justified by each source's update rate (§4) |
| Processing | GitHub Actions jobs: parse, convert units, run ML inference (`score`), upsert, log, retrain monthly ("collect *and* process", Week 3 Method B) | Stateless and idempotent, so a job can be re-run safely |
| Application | Postgres tables, views and RPC functions | Analytics live next to the data |
| Business | Dashboard: accuracy, leaderboard, rain indicator, data health, live ML check | The rain indicator is the virtual "actuator" |

### 3.2 Data flow in one sentence per path (report "Data Flow Description")

1. **Observation path:** every 10 min, `observe` pulls Open-Meteo `current` and METAR and upserts them into `observations`.
2. **Forecast path:** every hour, `forecast` stores the full 7-day hourly and daily forecast for each model run it has not stored yet in `forecasts` / `forecasts_daily`. Straight after, `score` corrects the new `best_match` forecast with each active model and writes `predictions`.
3. **Repair path:** once a day, `backfill` refills missed 15-min samples (only after the first live sample, marked `is_backfill`) and trims old raw payloads. The one-off import of 1–7 Nov used the same job with `--since`/`--until` to add METAR history and Previous Runs forecasts.
4. **Model path:** once a month, `retrain` trains a challenger on Previous Runs history and activates it only if it beats the current model on last month.
5. **Read path:** the browser calls Supabase views and RPC functions with the public anon key (read-only by RLS).

---

## 4. Data sources and sampling

| Source code | Endpoint | Cadence / latency | Poll | Gives | Role |
|---|---|---|---|---|---|
| `openmeteo_current` | `api.open-meteo.com/v1/forecast?current=…` | ✔ `interval: 900` (15 min); precipitation is the **15-min sum** | every 10 min | temp, RH, dew point, precip, wind, MSL pressure, cloud, weather code | **Primary actual** (the brief's "observed") |
| (gap fill of the above) | same endpoint, `minutely_15=…&past_days=2` | ✔ past 15-min values available | daily | same 15-min values | Refills samples missed by late cron runs |
| `openmeteo_reanalysis` (**Not built.**) | `archive-api.open-meteo.com/v1/archive` | hourly, ~1–2 day delay | daily | hourly reanalysis | Second actual + ML history |
| `metar_wmki` | `aviationweather.gov/api/data/metar?ids=WMKI&format=json&hours=3` | ✔ hourly at :00, received ~8 min later | every 10 min | temp, dew point, wind (kt), QNH, `wxString` (RA/TS) | **Real instrument** truth, 26 km NE |
| `imerg_early` (**Not built.**) | NASA GES DISC (Earthdata login) | half-hourly, ~4–6 h latency | hourly + daily | 0.1° rain rate | Satellite rain truth + nowcast labels |
| Forecast vault | `api.open-meteo.com/v1/forecast?models=…&hourly=…&daily=…` | ECMWF/GFS/ICON update every 6 h (✔ `meta.json`); `best_match` blends hourly | hourly | 7-day hourly + daily | The forecasts being verified |
| Model run times | `api.open-meteo.com/data/{meta_key}/static/meta.json` | ✔ `last_run_initialisation_time`, `last_run_availability_time` | hourly | run timestamps | Store each model run **once** (§6.2) |
| Previous Runs | `previous-runs-api.open-meteo.com/v1/forecast` | ✔ data from about **Mar 2024** (Jan 2024 is null) | one-off import + training | `*_previous_day1..7` | The 1–7 Nov import + model training and retraining |
| Himawari-9 B13 (**Not built.**) | `https://noaa-himawari9.s3.amazonaws.com/AHI-L1b-FLDK/YYYY/MM/DD/HHMM/HS_H09_YYYYMMDD_HHMM_B13_FLDK_R20_S0510.DAT.bz2` | ✔ every 10 min, on AWS ~10–20 min after scan start | every 10 min | 2 km IR brightness temperature | ML features |
| GIBS tiles (**Not built.**) | `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{Layer}/default/{Time}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png` | ✔ Himawari layer ~50 min behind real time; IMERG ~6 h | browser | PNG tiles, max native zoom **6** | Dashboard imagery only |

**Fixed location:** Seri Iskandar, **4.35993 N, 100.98491 E**, 25 m. ✔ Open-Meteo snaps it to the grid cell at 4.3937 N, 100.9738 E (elevation 21 m).

**Why poll `current` every 10 min when it updates every 15:** the satellite step needed a 10-min cadence (it wasn't built, but the cadence stayed). Polling at minutes 7, 17, 27, … sees every 15-min value at least once. Duplicates are absorbed by the unique key, and missed values are refilled daily.

**Attribution (required):** "Weather data by Open-Meteo.com (CC BY 4.0)" and NOAA AWC METAR. Shown in the dashboard footer and cited in the report.

---

## 5. Time and measurement conventions

These rules prevent most off-by-one-hour bugs. Every module follows them.

| Rule | Detail |
|---|---|
| Storage time zone | **UTC everywhere** (`timestamptz`). Request Open-Meteo hourly data with `timezone=GMT`. Display in **Asia/Kuala_Lumpur (MYT, UTC+8)** |
| Daily aggregation | Daily forecasts are requested with `timezone=Asia/Kuala_Lumpur`, so daily max/min follow **local** days. `target_date` is a local date |
| Interval-end stamping | For accumulated quantities, `observed_at` is the **end** of the interval: a 15-min sample at 12:15 covers 12:00–12:15, and an IMERG half-hour 12:00–12:30 is stored at 12:30 |
| Hourly bucket | Hour `H` aggregates samples in **(H−1h, H]**, matching Open-Meteo's hourly precipitation ("sum of the preceding hour") |
| Instantaneous variables | Temperature, RH, wind and pressure at hour `H` use the sample stamped exactly `H`, or the mean of the bucket if that sample is missing |
| Pressure | Compare **MSL pressure** everywhere (`pressure_msl`, METAR QNH). Never mix it with surface pressure |
| Units | °C, %, mm, km/h (METAR knots × 1.852), hPa, K for brightness temperature |
| Rain hour | Hourly precipitation **≥ 0.1 mm**, or the station reports RA/DZ/SH/TS precipitation |
| Rain day | Daily total **≥ 1.0 mm** |
| `issued_at` | When **we first obtained** that forecast (fetch time truncated to the hour). This is the lead time a Seri Iskandar resident would have experienced |
| `model_run_at` | The model's initialisation time from `meta.json`, when known (null for `best_match`) |
| Lead time | `lead_hours = target_time − issued_at`, in whole hours, stored as a generated column |
| Lead buckets | `000-006`, `006-012`, `012-024`, `024-048`, `048-072`, `072-120`, `120-168` (zero-padded so they sort as text) |

---

## 6. Scheduled jobs

The four jobs (`observe`, `forecast`, `backfill`, `score`) are Python modules in `server/ingest/iww_ingest/jobs/`, run as `python -m iww_ingest.jobs.<job>`. Each one:

1. inserts an `ingestion_runs` row (`status='running'`),
2. runs its steps **independently**, so one failing source doesn't stop the others, recording per-step status and timing in `steps`,
3. upserts with `ON CONFLICT` on natural keys (**idempotent**: re-running never duplicates rows),
4. finishes the run as `success`, `partial` (some steps failed) or `failed`, with `rows_written` per table.

HTTP calls use a shared client: 15 s timeout and 3 retries with exponential backoff (1, 3 and 9 s) on 5xx and timeouts, but not on 4xx. Calls go out with a descriptive `User-Agent` (`iww-ingest/1.0 (student project; contact email)`).

### 6.1 `observe` — every 10 min (`7-59/10 * * * *`)

Minutes 7, 17, 27, … avoid GitHub's crowded top-of-hour slot, and Himawari slot HH:M0 is usually on AWS by then.

| Step | Action | Writes |
|---|---|---|
| 1 `om_current` | GET `current=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,rain,weather_code,wind_speed_10m,wind_direction_10m,pressure_msl,cloud_cover` with `timezone=GMT`. `observed_at = current.time`, `interval_min = 15` | `observations` (1 row) |
| 2 `metar` | GET the last 3 h for WMKI. Per report: `observed_at = obsTime`, wind kt → km/h, RH from temp/dew point (Magnus), `is_raining = wxString ~ (RA\|DZ\|SH)`, `is_thunder = wxString ~ TS` | `observations` (0–3 rows) |
| 3 `himawari` | List `AHI-L1b-FLDK/…/` prefixes for the last 2 h. For every slot **newer than the last stored `slot_time`** (oldest first, max 12 per run): download `…B13_FLDK_R20_S0510.DAT.bz2` (~2.9 MB), decompress, load with satpy, crop with cached masks (§8.1), compute features, upsert | `satellite_features` (3 rows per slot) |
| 4 `nowcast` | Build the feature vector for the newest slot (§9.1), score with the active `rain_nowcast` model (or the `rule_235k` fallback), add the top-5 feature contributions | `predictions` (2 rows: `rain_1h_prob`, `rain_3h_prob`) |

Catch-up: if GitHub skipped runs, step 3 processes up to 12 missed slots in one go. Older gaps are left to `backfill`, which is real **store-and-forward**.

**As built:** steps 1–2 only. Steps 3–4 (Himawari and the nowcast) are not built, so `observe` writes `observations` only.

### 6.2 `forecast` — hourly (`17 * * * *`)

| Step | Action | Writes |
|---|---|---|
| 1 `model_runs` | For each model with a `meta_key`, GET `meta.json`. A model is **due** if `last_run_initialisation_time` is newer than the latest `model_run_at` stored for it. `best_match` is always due | — |
| 2 `vault` | One GET for all due models: `models=<due>&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,precipitation_probability,wind_speed_10m,wind_direction_10m,pressure_msl,cloud_cover,cape,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,precipitation_hours,wind_speed_10m_max&forecast_days=7&timezone=Asia/Kuala_Lumpur`. Convert hourly times to UTC with `utc_offset_seconds`. Keep only `target_time ≥ issued_at`. Unpack the `<var>_<model>` keys ✔ | `forecasts` (~168 rows per model), `forecasts_daily` (~7 per model), `raw_responses` (1) |
| 3 `bias` | For the `best_match` snapshot just stored, apply each active `bias_*` model to leads 0–72 h | `predictions` (73 × 3 rows) |
| 4 `imerg` | Fetch IMERG Early half-hours for the window now−8 h to now−4 h that aren't stored yet (§6.4) | `observations` (`imerg_early`) |

**As built:** steps 1–2. Step 3 became the separate `score` job (§6.6), run after `forecast` in the same workflow. Step 4 is not built.

Storing each 6-hourly model run **once**, instead of hourly copies of the same run, cuts storage about 6× for ECMWF/GFS/ICON. It also stops the same forecast being counted six times in `n`. ⚠ If a `meta.json` mapping fails, the job falls back to storing that model every hour and logs a warning.

### 6.3 `backfill` — daily (`40 19 * * *` = 03:40 MYT)

| Step | Action | Writes |
|---|---|---|
| 1 `om_gapfill` | `minutely_15=…&past_days=2`. Insert only **missing** 15-min samples (`ON CONFLICT DO NOTHING`, `is_backfill = true`) | `observations` |
| 2 `reanalysis` | Historical Weather API for the last 5 days (hourly) | `observations` (`openmeteo_reanalysis`) |
| 3 `imerg_catchup` | IMERG Early for the last 48 h, any missing half-hours | `observations` |
| 4 `himawari_gaps` | Find missing 10-min slots in the last 48 h and re-download them from the AWS archive. Recompute `d_bt_*` for neighbouring slots | `satellite_features` |
| 5 `previous_runs` | For `target_time` hours in the last 7 days where a model has **no** snapshot at a given day-lead, insert `origin='previous_runs'` rows from `*_previous_dayN` (`issued_at = target_time − N days`, approximate) | `forecasts` |
| 6 `retention` | Delete `raw_responses` older than 30 days; `VACUUM (ANALYZE)` the hot tables | — |

**As built:** the daily run does steps 1 and 6 only. Step 1 fills only samples after the first live one, so retrieved data can't pass as live. Steps 2–4 are not built. `previous_runs` and a `metar_history` step run only in the one-off import (`--since`/`--until`, Implementation-plan §5.3), not daily.

### 6.4 IMERG access (not built)

Use the free NASA Earthdata login (`EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` secrets) with the `earthaccess` library. Open each half-hourly IMERG Early V07 granule (`GPM_3IMERGHHE`) through OPeNDAP and read only the 0.1° cells within 10 km of Seri Iskandar. Store the mean rate (mm/h), `precipitation_mm = rate × 0.5`, and `is_raining = max rate ≥ 0.5 mm/h`. ⚠ Confirm the collection short name and OPeNDAP subsetting during setup. Fallback: download the full HDF5 granule (~several MB) and slice it locally.

### 6.5 Workflow template

```yaml
# .github/workflows/observe.yml
name: observe
on:
  schedule: [{ cron: "7-59/10 * * * *" }]
  workflow_dispatch: {}
concurrency: { group: observe, cancel-in-progress: false }   # never overlap two runs
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 8
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: server/ingest/requirements*.txt
      - run: pip install -r server/ingest/requirements.txt && pip install -e server/ingest
      - run: python -m iww_ingest.jobs.observe
        env:
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}   # session pooler URI
          CONTACT_EMAIL: ${{ secrets.CONTACT_EMAIL }}
          GH_RUN_ID: ${{ github.run_id }}
```

`forecast.yml` and `backfill.yml` follow the same pattern with their own cron and `timeout-minutes` (10 and 20). `forecast.yml` adds the `score` step (§6.6). `retrain.yml` is described in §6.7. A `ci.yml` runs the unit tests, the PGlite SQL tests and `npm run build` on every push. The secrets must be **repository** secrets named exactly `SUPABASE_DB_URL` and `CONTACT_EMAIL`; otherwise every run stops with "SUPABASE_DB_URL is not set".

**GitHub cron caveats:** runs can start 5–30 min late under load, and scheduled workflows are disabled after 60 days without a commit, which is not a risk inside this project's timeline. The data-health page measures the real start delay (§11).

### 6.6 `score` — hourly, after `forecast`

| Step | Action | Writes |
|---|---|---|
| 1 `score` | Load each active model from `ml_models.artifact`. For every `best_match` snapshot issue from the last 6 h that the model hasn't scored, build the 13 inputs (`features/bias.py`) and write corrected values (humidity clipped to 0–100 %, wind ≥ 0) or, for rain, a probability and a yes/no | `predictions` |
| 2 `thin` | Delete live predictions older than 3 h unless their issue is at 00/06/12/18 UTC. Retrieved forecasts (the report window) are never touched | — |

It runs in `forecast.yml` with `if: !cancelled()`, so it still scores if the forecast step failed. `lightgbm` comes from `requirements-score.txt`.

### 6.7 `retrain` — monthly (`0 20 1 * *` = 04:00 MYT on the 2nd)

`server/ml/retrain.py` fetches Previous Runs history and, for each model, trains a challenger on everything before last month (MYT) and scores it on that month next to the active champion. Only a challenger that scores better is refit on all the data and activated as the next version; otherwise nothing changes. The comparison is appended to the champion's `metrics.retrain_checks` either way. A champion trained on the month being judged is never replaced. The manual button defaults to a dry run.

---

## 7. Database schema (Supabase Postgres)

Migration files live in `database/migrations/`, applied in the phased order `0001 → 0004 → 0005 → 0002 → 0003 → 0006 → 0007 → 0008` with `python -m iww_ingest.tools.migrate`. The tables below are `0001`'s; later changes are noted in comments.

### 7.1 Reference tables

```sql
-- 0001_core.sql
create table locations (
  id          smallint primary key,
  name        text not null,
  lat         double precision not null,
  lon         double precision not null,
  grid_lat    double precision,               -- Open-Meteo grid cell actually used
  grid_lon    double precision,
  elevation_m real,
  tz          text not null default 'Asia/Kuala_Lumpur'
);

create table sources (                          -- every "actual" source, described once
  code        text primary key,                 -- openmeteo_current | openmeteo_reanalysis | metar_wmki | imerg_early
  kind        text not null check (kind in ('model_analysis','reanalysis','station','satellite')),
  name        text not null,
  lat         double precision,
  lon         double precision,
  distance_km real,                             -- from Seri Iskandar
  cadence_min smallint not null,
  notes       text
);

create table forecast_models (
  code        text primary key,                 -- the Open-Meteo `models=` value
  name        text not null,
  provider    text not null,
  meta_key    text,                             -- meta.json key; null = no single run (best_match)
  update_h    smallint,                         -- nominal update interval
  is_active   boolean not null default true
);
```

### 7.2 Run log and raw payloads

```sql
create table ingestion_runs (                   -- proof of continuous operation
  id           bigserial primary key,
  job          text not null check (job in ('observe','forecast','backfill','manual')),  -- 0008 adds 'score', 'retrain'
  trigger      text not null default 'schedule' check (trigger in ('schedule','dispatch','local')),
  gh_run_id    bigint,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  status       text not null default 'running'
               check (status in ('running','success','partial','failed')),
  rows_written jsonb not null default '{}'::jsonb,   -- {"observations":2,"satellite_features":3}
  steps        jsonb not null default '[]'::jsonb,   -- [{"step":"metar","ok":true,"ms":412,"error":null}]
  error        text
);
create index on ingestion_runs (job, started_at desc);

create table raw_responses (                    -- reprocessing safety net, 30-day retention
  id          bigserial primary key,
  run_id      bigint references ingestion_runs on delete cascade,
  source      text not null,
  url         text not null,                    -- with no secrets in it
  http_status smallint,
  fetched_at  timestamptz not null default now(),
  payload     jsonb
);
create index on raw_responses (fetched_at);
```

### 7.3 Observations (the "actual" weather, many sources)

```sql
create table observations (
  id               bigserial primary key,
  location_id      smallint not null references locations,
  source           text not null references sources(code),
  observed_at      timestamptz not null,        -- UTC, END of the interval (§5)
  interval_min     smallint,                    -- 15 current · 60 reanalysis · 30 imerg · null metar
  temperature_c    real,
  dew_point_c      real,
  humidity_pct     real,
  precipitation_mm real,                        -- accumulated over interval_min
  rain_rate_mmh    real,                        -- imerg only
  wind_speed_kmh   real,
  wind_dir_deg     real,
  pressure_hpa     real,                        -- MSL / QNH
  cloud_cover_pct  real,
  weather_code     smallint,                    -- WMO code (Open-Meteo)
  is_raining       boolean,                     -- station/satellite flag; null for model sources
  is_thunder       boolean,
  is_backfill      boolean not null default false,
  raw              jsonb,                       -- the source record as received
  run_id           bigint references ingestion_runs,
  inserted_at      timestamptz not null default now(),
  unique (location_id, source, observed_at)
);
create index on observations (source, observed_at desc);
```

### 7.4 Forecast vault

```sql
create table forecasts (                        -- hourly, one row per (model run, target hour)
  id                     bigserial primary key,
  location_id            smallint not null references locations,
  model                  text not null references forecast_models(code),
  origin                 text not null default 'snapshot' check (origin in ('snapshot','previous_runs')),
  issued_at              timestamptz not null,  -- when we obtained it (hour)
  model_run_at           timestamptz,           -- model initialisation time, if known
  target_time            timestamptz not null,  -- hour being predicted (instant vars at H, precip over (H-1h,H])
  lead_hours             smallint generated always as
                           ((extract(epoch from (target_time - issued_at)) / 3600)::smallint) stored,
  temperature_c          real,
  humidity_pct           real,
  dew_point_c            real,
  precipitation_mm       real,
  precip_probability_pct real,
  wind_speed_kmh         real,
  wind_dir_deg           real,
  pressure_hpa           real,                  -- MSL
  cloud_cover_pct        real,
  cape_jkg               real,
  weather_code           smallint,
  run_id                 bigint references ingestion_runs,
  unique (location_id, model, origin, issued_at, target_time)
);
create index on forecasts (location_id, target_time);
create index on forecasts (model, lead_hours);

create table forecasts_daily (                  -- next-day max/min and rain total (brief requirement)
  id                         bigserial primary key,
  location_id                smallint not null references locations,
  model                      text not null references forecast_models(code),
  issued_at                  timestamptz not null,
  target_date                date not null,     -- local MYT date
  lead_days                  smallint not null, -- target_date - local date of issued_at
  temp_max_c                 real,
  temp_min_c                 real,
  precipitation_sum_mm       real,
  precip_probability_max_pct real,
  precipitation_hours        real,
  wind_speed_max_kmh         real,
  run_id                     bigint references ingestion_runs,
  unique (location_id, model, issued_at, target_date)
);
```

### 7.5 Satellite features (table created, never filled: Himawari not built)

```sql
create table satellite_features (
  id                 bigserial primary key,
  location_id        smallint not null references locations,
  slot_time          timestamptz not null,      -- Himawari scan start, 10-min slot (UTC)
  radius_km          smallint not null check (radius_km in (10, 25, 50)),
  pixel_count        int not null,
  bt_min_k           real,                      -- coldest cloud top
  bt_mean_k          real,
  bt_p10_k           real,                      -- 10th percentile (robust "coldest")
  frac_lt_235        real,                      -- share of pixels < 235 K (rain cloud)
  frac_lt_221        real,                      -- share < 221 K (deep convection)
  d_bt_mean_10m      real,                      -- change vs 10/30/60 min earlier (K); negative = cooling
  d_bt_mean_30m      real,
  d_bt_mean_60m      real,
  d_bt_p10_30m       real,
  upwind_frac_lt_235 real,                      -- 25–75 km upwind sector (50 km row only)
  source_file        text,
  run_id             bigint references ingestion_runs,
  unique (location_id, slot_time, radius_km)
);
create index on satellite_features (slot_time desc);
```

### 7.6 ML registry and predictions

```sql
create table ml_models (
  id             serial primary key,
  name           text not null,                 -- rain_nowcast | bias_temperature | bias_humidity | bias_wind
  version        text not null,                 -- v0-rule, v1.0, v1.1 …
  algorithm      text not null check (algorithm in ('rule','logreg','lightgbm','cnn')),
  features       text[] not null,
  train_window   tstzrange,
  test_window    tstzrange,
  metrics        jsonb not null default '{}'::jsonb,  -- offline test metrics + baselines + thresholds
  importance     jsonb,                               -- [{"feature":"frac_lt_235_r25","gain":0.31}, …]
  artifact_path  text,                                -- models/rain_nowcast/v1.0/model.txt
  artifact_sha256 text,
  is_active      boolean not null default false,
  trained_at     timestamptz not null default now(),
  -- 0008: artifact text (the LightGBM model text the jobs load), is_report boolean (owns the 4–7 Nov figures)
  unique (name, version)
);
create unique index ml_models_one_active on ml_models (name) where is_active;

create table predictions (
  id          bigserial primary key,
  location_id smallint not null references locations,
  model_id    int not null references ml_models,
  issued_at   timestamptz not null,             -- nowcast: satellite slot time · bias: forecast issued_at
  target_time timestamptz not null,             -- nowcast: window END · bias: forecast hour
  variable    text not null,                    -- built: temperature_c | humidity_pct | wind_speed_kmh | pressure_hpa | rain_prob | rain_yes
  value       real not null,
  base_model  text,                             -- bias: the raw model corrected (best_match)
  base_value  real,                             -- bias: the raw forecast value
  lead_hours  smallint,
  explain     jsonb,                            -- nowcast: top-5 contributions [{"feature","value","contrib"}]
  run_id      bigint references ingestion_runs,
  unique (location_id, model_id, variable, issued_at, target_time)
);
create index on predictions (variable, issued_at desc);
```

### 7.7 Seed data

```sql
-- 0005_seed.sql
insert into locations values
  (1, 'Seri Iskandar', 4.35993, 100.98491, 4.3937, 100.9738, 25, 'Asia/Kuala_Lumpur');

insert into sources values
  ('openmeteo_current',    'model_analysis', 'Open-Meteo current (15-min)',        4.3937, 100.9738, 4,  15, 'Primary actual. Model-based, not a gauge'),
  ('openmeteo_reanalysis', 'reanalysis',     'Open-Meteo Historical Weather',      4.3937, 100.9738, 4,  60, 'Retrospective best estimate, 1–2 day delay'),
  ('metar_wmki',           'station',        'METAR WMKI Ipoh Sultan Azlan Shah',  4.568,  101.092,  26, 60, 'Real instruments; rain yes/no only'),
  ('imerg_early',          'satellite',      'GPM IMERG Early V07 (0.1°)',          4.35,   100.95,   4,  30, 'Satellite rain estimate, ~4–6 h latency');

insert into forecast_models values
  ('best_match',    'Open-Meteo Best Match', 'Open-Meteo', null,          1, true),
  ('ecmwf_ifs025',  'ECMWF IFS 0.25°',       'ECMWF',      'ecmwf_ifs025', 6, true),
  ('gfs_seamless',  'NOAA GFS',              'NOAA',       'ncep_gfs025',  6, true),
  ('icon_seamless', 'DWD ICON',              'DWD',        'dwd_icon',     6, true),
  -- optional bonus: an AI weather model and the regional JMA model (✔ both return data)
  ('ecmwf_aifs025_single', 'ECMWF AIFS (AI model)', 'ECMWF', 'ecmwf_aifs025_single', 6, false),
  ('jma_seamless',  'JMA GSM',               'JMA',        'jma_gsm',      6, false);

insert into ml_models (name, version, algorithm, features, metrics, is_active) values
  ('rain_nowcast', 'v0-rule', 'rule', array['frac_lt_235_r25','d_bt_mean_30m_r25'],
   '{"thresholds":{"watch":0.3,"likely":0.6}}', true);   -- works from day 1, before ML training
```

The `rain_nowcast` `v0-rule` row is seeded but never used, because the nowcast wasn't built. Phase 5b models are registered by `server/ml/score_models.py`.

`gfs_seamless` and `icon_seamless` are "seamless" blends. Over Malaysia only the global members apply, so their run time follows `ncep_gfs025` and `dwd_icon` (⚠ confirm the run times line up).

### 7.8 Entity relationships (for the report's ER diagram)

```mermaid
erDiagram
  locations ||--o{ observations : has
  locations ||--o{ forecasts : has
  locations ||--o{ forecasts_daily : has
  locations ||--o{ satellite_features : has
  locations ||--o{ predictions : has
  sources ||--o{ observations : provides
  forecast_models ||--o{ forecasts : issues
  forecast_models ||--o{ forecasts_daily : issues
  ml_models ||--o{ predictions : produces
  ingestion_runs ||--o{ observations : wrote
  ingestion_runs ||--o{ forecasts : wrote
  ingestion_runs ||--o{ satellite_features : wrote
  ingestion_runs ||--o{ predictions : wrote
  ingestion_runs ||--o{ raw_responses : logged
```

### 7.9 Security (RLS)

```sql
-- 0004_rls.sql: weather data is public, writes come only from jobs
do $$ declare t text; begin
  foreach t in array array['locations','sources','forecast_models','ingestion_runs','observations',
                           'forecasts','forecasts_daily','satellite_features','ml_models','predictions'] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy %I on %I for select to anon, authenticated using (true)', t || '_read', t);
  end loop;
end $$;
alter table raw_responses enable row level security;           -- no policy = no anon access

-- read-only role for FastAPI (least privilege): commented out in 0004, because FastAPI wasn't built
-- create role api_reader login password '<set-in-dashboard>' noinherit;
-- grant usage on schema public to api_reader;
-- grant select on all tables in schema public to api_reader;
-- grant execute on all functions in schema public to api_reader;
```

- The jobs connect as the `postgres` user through the pooler. That bypasses RLS, so the URL lives only in GitHub Secrets.
- The browser uses the **anon / publishable key**. RLS allows `SELECT` only, so a leaked key cannot write anything.
- All views are `with (security_invoker = true)`, which keeps Supabase's security linter quiet. All functions are `stable` and `security invoker`, with `set search_path = public`.

---

## 8. Satellite feature extraction (not built)

Himawari was dropped (Implementation-plan decision 7). This section is the original design.

### 8.1 Crop masks (computed once, cached)

The geostationary grid never moves. So the first run loads segment S05's lat/lon arrays with `pyresample` (`area.get_lonlats()`), computes the haversine distance from Seri Iskandar, and saves the pixel indices for:

- **r10, r25, r50:** discs with radius 10, 25 and 50 km
- **upwind sector:** an annulus 25–75 km from the town, ±45° around the upwind bearing, stored as an 8-sector lookup (N, NE, … NW)

The result goes to `ingest/.cache/masks_S05_R20.npz`, cached by `actions/cache`. Later runs index the array directly.

⚠ **Segment check:** by geometry, 4.36 N at 101 E falls at roughly line 2,520 of the 5,500-line 2 km full disk. That is inside S05 (lines 2,201–2,750), and the 50 km disc spans about ±25 lines, so it shouldn't cross into S06. Confirm on the first file by printing the lat/lon at the crop centre.

### 8.2 Per-slot computation

```python
scn = Scene(reader="ahi_hsd", filenames=[dat_path])          # decompressed .DAT
scn.load(["B13"], calibration="brightness_temperature")
bt = scn["B13"].values                                         # Kelvin, NaN outside the disk
for r, idx in masks.discs.items():                             # 10, 25, 50
    v = bt.flat[idx]; v = v[np.isfinite(v)]
    row = dict(radius_km=r, pixel_count=v.size, bt_min_k=v.min(), bt_mean_k=v.mean(),
               bt_p10_k=np.percentile(v, 10), frac_lt_235=(v < 235).mean(), frac_lt_221=(v < 221).mean())
```

- **Trends** (`d_bt_mean_10m/30m/60m`, `d_bt_p10_30m`): the difference from the stored row for the same radius 10/30/60 min earlier. Null if that slot is missing; `backfill` recomputes it once the gap is filled.
- **Upwind sector:** the bearing comes from the hourly forecast's `wind_direction_700hPa` for the current hour (✔ the variable exists). The 700 hPa wind is the usual steering wind for convective cells.
- **Runtime target:** < 15 s per slot on a GitHub runner (download ~2.9 MB, decompress, calibrate, crop).

### 8.3 Display imagery (no processing)

The browser loads GIBS `Himawari_AHI_Band13_Clean_Infrared` tiles for a timestamp list (§10.4). Nothing is stored. `IMERG_Precipitation_Rate_30min` is an optional second overlay.

---

## 9. ML design

> **Since 7 Nov 2026, ML 2 (§9.2) is built.** Temperature v1.0 is tested on the frozen window, which is retrieved data rather than live data, but it's still unseen by the model. §9.1 is not built. **Also built 7 Nov (Phase 5b):** humidity, wind, pressure and rain-occurrence models, live scoring and monthly retraining. The design is in [Implementation-plan.md](Implementation-plan.md) §5.8, the research in [ML-research.md](ML-research.md), and it replaces the "No live scoring" line in §9.2.

The bias-correction models are **trained offline on about a year of Previous Runs history** (from 1 Oct 2025) and **tested once on the frozen window**, which they never saw: a true out-of-sample test. The Phase 5b inputs live in `server/ingest/iww_ingest/features/bias.py` and are used by training, window scoring and the live `score` job, so training and serving compute them the same way (**no train/serve skew**). Temperature v1.0 keeps its own copy in `server/ml/bias_features.py`.

### 9.1 ML 1 — Rain nowcast ("rain at Seri Iskandar in the next 1 h / 3 h?") (not built)

The Phase 5b `rain_occurrence` model (§9.2) forecasts "rain this hour?" from the forecast instead. This section is the original design.

| Item | Specification |
|---|---|
| Unit of prediction | One Himawari slot `t` (every 10 min) |
| Labels | `rain_1h = 1` if IMERG rain over the cells within 10 km is ≥ 0.5 mm/h in any half-hour of (t, t+1h]; `rain_3h` the same for (t, t+3h]. **History** uses IMERG **Final** (gauge-calibrated); **live** evaluation uses IMERG **Early**, with `openmeteo_current` and METAR as cross-check labels |
| Satellite features (×3 radii) | `bt_min_k`, `bt_mean_k`, `bt_p10_k`, `frac_lt_235`, `frac_lt_221`, `d_bt_mean_10m/30m/60m`, `d_bt_p10_30m`, `upwind_frac_lt_235` |
| Weather features | RH, dew-point depression, 3 h MSL pressure tendency, CAPE and `precipitation_probability` for the next hour (best_match), 700 hPa wind speed, rain in the last hour |
| Calendar features | hour of day (sin/cos, local), day of year (sin/cos) |
| Models | v0 = **235 K rule** (in production from day 1) · v1 = logistic regression · v2 = **LightGBM** (binary, `is_unbalance` or class weights, early stopping) · stretch = small CNN on 64 × 64 IR patches |
| Split | **Time-blocked**, no shuffling: train Oct–Nov 2025 (+ Oct–Dec 2024 if time allows), validate Dec 2025, test = live window |
| Baselines to beat | Open-Meteo `precipitation_probability`, persistence ("raining now → raining next hour"), the 235 K rule |
| Metrics | ROC-AUC, Brier score and Brier skill score vs climatology, POD/FAR/CSI at the chosen threshold, **median warning lead** (minutes between the first `WATCH`/`RAIN_LIKELY` and rain onset) |
| Thresholds | `watch` and `likely` chosen on the validation set (max CSI for `likely`, POD ≥ 0.8 for `watch`) and stored in `ml_models.metrics.thresholds` |
| Output | `rain_1h_prob`, `rain_3h_prob` + `explain` (LightGBM `pred_contrib=True`, top 5) |

**Training data budget (Colab/Kaggle):** Oct–Dec 2025 at 10-min cadence is about 13,200 slots × 2.9 MB ≈ **38 GB streamed** (each file is downloaded, cropped and deleted). At 0.5–1 s per file that's about 2–4 h of compute, which fits one Kaggle session. Process month by month and write features to a Parquet file. Fallback if time is short: sample every 20 min, or train **v1 on weather features only** (Open-Meteo Historical Forecast + reanalysis) and add satellite features in v2.

**The v0 rule** (written so the indicator works before training):
`p_1h = clip(0.05 + 0.9 · frac_lt_235(r25) + 0.15 · [d_bt_mean_30m(r25) < −4 K], 0, 1)`, and `p_3h` the same with r50.

### 9.2 ML 2 — Forecast bias correction

| Item | Specification |
|---|---|
| Target | Residual `truth − raw_forecast`, one model per variable. v1.0 corrects temperature only; Phase 5b adds humidity, wind and pressure, and a rain-occurrence classifier (ML-research §4.1) |
| Training data | ✔ Previous Runs API, `best_match`: **Oct 2025 – Jun 2026** for v1.0, **Oct 2025 – Oct 2026** for Phase 5b, after a change in `best_match` around Q3 2025 (Implementation-plan §5.4): `<var>_previous_day1..7` as the forecast, and plain `<var>` (day 0, the newest run) as the truth |
| Why day-0 truth | Day-0 values are what `openmeteo_current` reports, so the training truth matches the live evaluation truth. METAR is a secondary check |
| Features | v1.0: raw forecast value, lead hours (≈ 24 × N in training), local hour (sin/cos), day of year (sin/cos), forecast precipitation, RH, wind speed. Phase 5b: 13 inputs (`features/bias.py`): forecast temperature, humidity, dew point, precipitation, wind speed and direction (sin/cos), pressure, cloud cover, CAPE, lead hours and local hour (sin/cos). **No day of year**: with one year of history it hurts on unseen seasons (ML-research §3.2). Precipitation probability is excluded: it's empty in Previous Runs for every model |
| Model | LightGBM regression (L1 objective, which is robust to storm outliers); `rain_occurrence` is a LightGBM binary classifier with a yes/no cut-off of 0.30 |
| Validation | v1.0: train Oct 2025 – Jun 2026, validate Jul–Oct 2026. Phase 5b: 13-fold month-by-month cross-validation with a 3-day gap. Test = the frozen window. Nothing from Nov 2026 is used, so either candidate window stays unseen |
| Output | Corrected values exposed in the views as the pseudo-model **`best_match+ml`**, so it competes on the **leaderboard**. The window (1–7 Nov, 24–168 h) was scored once locally; since Phase 5b every new `best_match` forecast is also scored live by the `score` job (§6.6) |
| Proof | MAE of raw vs corrected per lead bucket on the frozen window, with `n` |
| Known limitation | Training leads are roughly whole days (24, 48, … h). Leads in between are interpolated by the model. State this in the report |

### 9.3 Artifacts and registry

- Saved as `server/ml/models/<name>/<version>/model.txt` (LightGBM text format, a few hundred KB) plus `card.json` (features, windows, metrics, thresholds, importance), **committed to the repo**.
- `server/ml/score_window.py` (v1.0) and `server/ml/score_models.py` (Phase 5b) insert the `ml_models` row, flip `is_active` (one active per name) and record `artifact_sha256`. Phase 5b rows also hold the model text in `artifact`; `retrain.py` adds later versions the same way.
- The `score` job loads the **active** version from `ml_models.artifact`, not from the repo, so a retrain takes effect without a deploy. Versions that own the report's figures are flagged `is_report`. To roll back, flip `is_active`.

---

## 10. Frontend architecture

### 10.1 Routes (details in [spec.md](spec.md))

| Route | Page | Main data |
|---|---|---|
| `/` | Overview | `v_now`, `v_rain_status`, `rpc_kpis`, `rpc_next_24h`, `v_collection_window` |
| `/accuracy` | Forecast Accuracy | `rpc_forecast_vs_actual`, `rpc_metrics_by_lead`, `rpc_leaderboard`, `rpc_next_day` (designed: also `rpc_error_heatmap`, `rpc_daily_pairs`, `rpc_skill_vs_persistence`) |
| `/rain` | Rain & Satellite (**Not built.**) | GIBS tiles, `rpc_nowcast_timeline`, `rpc_rain_contingency`, `rpc_reliability`, `rpc_rain_heatmap` |
| `/ml` | ML Lab (**Not built.**) | `ml_models`, `rpc_bias_eval`, FastAPI `/nowcast/*`, `/models/*` |
| `/health` | Data Health | `v_collection_window`, `rpc_uptime_daily`, `v_coverage_daily`, `rpc_metrics_by_lead` (Live check), `ingestion_runs` |
| `/about` | About & Method (**Not built.**) | static content + architecture diagram |

### 10.2 Data access

- `supabase-js` with the anon key. Row types are hand-written in `lib/types.ts` (the Supabase CLI isn't set up).
- **TanStack Query** keys are `[name, …params]`. Refetch: rain status and the now card every 60 s, health every 2 min, metrics every 10 min. Stale-while-revalidate.
- **URL state:** `?var=&models=&lead=&truth=` live in the search params, so views are shareable and the video demo can deep-link to them.
- Date range: fixed to the frozen report window (`FROZEN_WINDOW` in `lib/constants.ts`), with no date picker. The Live check card uses live data instead.
- *(Designed but not built: FastAPI calls through an `apiClient` with a 75 s cold-start timeout.)*

### 10.3 Build and hosting

- Vite build → `dist/`. A Vercel static site; `vercel.json` does the **rewrite `/*` → `/index.html`** and sets `Cache-Control: public, max-age=31536000, immutable` on `/assets/*`.
- Bundle budget: < 450 KB gzipped on first load. ECharts comes from `echarts/core` with only the charts used. Pages are lazy-loaded per route.
- Env vars (build time): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

### 10.4 Satellite loop (not built)

- Frame times run from `now − 3 h` to `latest`, every 10 min (19 frames).
- `latest` is found by probing: request one tile (z=6 over Perak) for `floor10(now − 40 min)` and step back 10 min on a 404, up to 6 times. Cache the result for 10 min. This avoids downloading the 5.6 MB GetCapabilities document in the browser.
- Each frame is a Leaflet `TileLayer` with `maxNativeZoom: 6`, `maxZoom: 9` and `opacity: 0.75`. Preload all frames before autoplay; play at 2 fps.

---

## 11. Analytics layer (views and RPC functions)

Full signatures and return shapes are in [api-spec.md §3](api-spec.md). Below are the core definitions every metric builds on.

```sql
-- 0002_views.sql
create function lead_bucket(h int) returns text language sql immutable as $$
  select case when h < 6 then '000-006' when h < 12 then '006-012' when h < 24 then '012-024'
              when h < 48 then '024-048' when h < 72 then '048-072' when h < 120 then '072-120'
              else '120-168' end $$;

-- Hourly "actual" per source, using the (H-1h, H] convention
create view v_actual_hourly with (security_invoker = true) as
select location_id, source,
       date_trunc('hour', observed_at - interval '1 second') + interval '1 hour' as hour,
       count(*)                                                                as samples,
       coalesce(avg(temperature_c)  filter (where extract(minute from observed_at) = 0), avg(temperature_c))  as temperature_c,
       coalesce(avg(humidity_pct)   filter (where extract(minute from observed_at) = 0), avg(humidity_pct))   as humidity_pct,
       coalesce(avg(wind_speed_kmh) filter (where extract(minute from observed_at) = 0), avg(wind_speed_kmh)) as wind_speed_kmh,
       coalesce(avg(pressure_hpa)   filter (where extract(minute from observed_at) = 0), avg(pressure_hpa))   as pressure_hpa,
       sum(precipitation_mm)                                                   as precipitation_mm,
       coalesce(bool_or(is_raining), sum(precipitation_mm) >= 0.1)             as rain_hour
from observations
group by 1, 2, 3;
-- openmeteo_current hours count as complete only when samples = 4; RPCs filter on this

-- Raw forecasts + the ML-corrected pseudo-model, one shape (as replaced by 0008_ml_live.sql).
-- One prediction per forecast hour and variable: report versions first, then the newest version.
-- ML rain is a yes/no (rain_yes), so the +ml row's precipitation_mm stays null.
create or replace view v_forecasts_all with (security_invoker = true) as
select location_id, model, origin, issued_at, target_time, lead_hours,
       temperature_c, humidity_pct, wind_speed_kmh, pressure_hpa, precipitation_mm, precip_probability_pct,
       null::boolean as rain_yes
from forecasts
union all
select p.location_id, p.base_model || '+ml', 'snapshot', p.issued_at, p.target_time, p.lead_hours,
       max(p.value) filter (where p.variable = 'temperature_c'),
       max(p.value) filter (where p.variable = 'humidity_pct'),
       max(p.value) filter (where p.variable = 'wind_speed_kmh'),
       max(p.value) filter (where p.variable = 'pressure_hpa'),
       null::real,
       (max(p.value) filter (where p.variable = 'rain_prob') * 100)::real,
       bool_or(p.value >= 0.5) filter (where p.variable = 'rain_yes')
from (select p.*, row_number() over (
               partition by p.location_id, p.base_model, p.variable, p.issued_at, p.target_time
               order by m.is_report desc, m.trained_at desc, m.id desc) as pick
      from predictions p join ml_models m on m.id = p.model_id
      where m.name like 'bias\_%' or m.name = 'rain_occurrence') p
where p.pick = 1
group by p.location_id, p.base_model, p.issued_at, p.target_time, p.lead_hours;

-- Forecast/actual pairs in long format: one row per (forecast hour × truth source × variable)
create view v_pairs with (security_invoker = true) as
select f.location_id, f.model, f.origin, f.issued_at, f.target_time, f.lead_hours,
       lead_bucket(f.lead_hours) as lead_bucket, a.source as truth_source,
       v.variable, v.forecast, v.actual, v.forecast - v.actual as error
from v_forecasts_all f
join v_actual_hourly a on a.location_id = f.location_id and a.hour = f.target_time
cross join lateral (values
  ('temperature_c',    f.temperature_c,    a.temperature_c),
  ('humidity_pct',     f.humidity_pct,     a.humidity_pct),
  ('wind_speed_kmh',   f.wind_speed_kmh,   a.wind_speed_kmh),
  ('pressure_hpa',     f.pressure_hpa,     a.pressure_hpa),
  ('precipitation_mm', f.precipitation_mm, a.precipitation_mm)
) as v(variable, forecast, actual)
where v.forecast is not null and v.actual is not null
  and (a.source <> 'openmeteo_current' or a.samples = 4);
```

The other views and functions, specified in api-spec.md, are:

- **Built:** `v_now`, `v_rain_status`, `v_collection_window`, `v_coverage_daily`, `v_rain_pairs`, `rpc_metrics_by_lead`, `rpc_rain_contingency`, `rpc_brier`, `rpc_reliability`, `rpc_leaderboard`, `rpc_forecast_vs_actual`, `rpc_daily_pairs`, `rpc_next_day`, `rpc_uptime_daily`, `rpc_runs_timeline`, `rpc_kpis`, `rpc_next_24h`
- **Not built:** `rpc_skill_vs_persistence`, `rpc_error_heatmap`, `rpc_rain_heatmap`, `rpc_nowcast_timeline`, `rpc_bias_eval`

**Performance:** with per-run storage there are about 6,000 forecast rows per day, so a 14-day window aggregates fewer than ~500k pair rows. That is well inside Supabase's **3 s anon statement timeout**, provided RPCs filter `target_time` first (indexed). If any RPC exceeds ~1 s, convert its aggregate to a materialized view refreshed at the end of the `forecast` job. *(Measured live: every RPC answers in under 0.35 s as anon, so none was needed.)*

---

## 12. FastAPI extras service (not built)

- `api/app/main.py`, base path `/api/v1`. Full contract in [api-spec.md §4](api-spec.md).
- Connects with the **`api_reader`** role (read-only) through the pooler, using a pool of size 2 (`psycopg_pool`).
- Loads the active model artifacts at startup for SHAP-style contributions.
- Responses are cached in-process for 5 min (`cachetools.TTLCache`) and sent with `Cache-Control: public, max-age=300`.
- CORS allows only `CORS_ORIGINS` (the Render static URL and `http://localhost:5173`).
- Memory budget: **< 350 MB** on the 512 MB instance. Use pandas + lightgbm + scikit-learn; no satpy, no torch.

---

## 13. Deployment

The dashboard is a static site on **Vercel** (Implementation-plan decision 13 and §5.7). Root Directory `client/Iotweatherproject`, framework preset Vite (build `npm run build`, output `dist`), Node 24.x from `package.json`. `client/Iotweatherproject/vercel.json`:

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }],
  "headers": [
    { "source": "/assets/(.*)",
      "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }] }
  ]
}
```

### Environment variables

| Name | Where | Value |
|---|---|---|
| `SUPABASE_DB_URL` | GitHub repository secret (and the local `.env`) | `postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:5432/postgres` (**session pooler**) |
| `CONTACT_EMAIL` | GitHub repository secret (and the local `.env`) | Used in the `User-Agent` |
| `IWW_LOG_LEVEL` | Optional, local `.env` | Job log level, default `INFO` |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Vercel project (and `client/Iotweatherproject/.env`) | Project URL + anon / publishable key |

No card on Vercel's Hobby plan. The original design's Render Blueprint and FastAPI variables (`DATABASE_URL`, `CORS_ORIGINS`, `VITE_API_BASE`, `EARTHDATA_*`) were not needed.

---

## 14. Repository layout

```
IoT Weather Project/                   public GitHub repo (free Actions minutes)
├─ .github/workflows/  observe.yml · forecast.yml (+ score) · backfill.yml · retrain.yml · ci.yml
├─ database/
│  ├─ migrations/      0001_core · 0002_views · 0003_rpc · 0004_rls · 0005_seed · 0006_retro_window · 0007_next_day · 0008_ml_live
│  └─ test/            PGlite harness (npm test, npm run serve)
├─ server/
│  ├─ ingest/          Python package used by the jobs and by training
│  │  ├─ pyproject.toml · requirements.txt · requirements-score.txt · requirements-dev.txt
│  │  ├─ iww_ingest/
│  │  │  ├─ config.py · db.py · http.py · runlog.py · timeutil.py
│  │  │  ├─ sources/  openmeteo.py · metar.py
│  │  │  ├─ features/ bias.py
│  │  │  ├─ ml/       models.py
│  │  │  ├─ jobs/     observe.py · forecast.py · backfill.py · score.py
│  │  │  └─ tools/    check.py · migrate.py
│  │  └─ tests/        parsers, unit conversion, scoring, idempotency
│  └─ ml/              train_bias.py · score_window.py (v1.0) · history.py · train_models.py · score_models.py · retrain.py
│                      models/<name>/<version>/{model.txt, card.json} · notebooks/00_sanity.ipynb · tests/
├─ client/Iotweatherproject/  package.json · vercel.json · vite.config.ts · src/{app, pages, components, charts, lib, theme}
├─ docs/  Overview.md · Implementation-plan.md · ML-research.md · architecture.md · api-spec.md · spec.md · tasks.md · report/
├─ README.md · claude.md · .gitignore (node_modules, .venv, dist, .cache, *.DAT*, .env)
```

---

## 15. Reliability, capacity and cost

### 15.1 Failure modes

| Failure | Detection | Mitigation |
|---|---|---|
| GitHub cron late or skipped | `ingestion_runs` gaps; delay chart on `/health` | 15-min data polled every 10 min; daily `om_gapfill`; optional backup trigger from cron-job.org calling `workflow_dispatch` (not set up) |
| One source down (Open-Meteo, METAR) | Step-level `ok=false` → run status `partial` | Steps are independent; retries with backoff; the backfill catches up later |
| Open-Meteo parse change | Step error + `raw_responses` | Raw JSON kept 30 days, so it can be reprocessed after a fix |
| Supabase paused | — | Writes every 10 min keep it active (it pauses after ~7 days idle) |
| Job secrets missing or misnamed | Every scheduled run fails; no `ingestion_runs` rows | The run log says "SUPABASE_DB_URL is not set"; add the two repository secrets (this happened until 9 Nov) |
| Duplicate or overlapping runs | — | `concurrency` group + unique keys + `ON CONFLICT` |
| Bad model deployed | Live check card on `/health` | The monthly retrain only activates a challenger that beats the champion; flip `is_active` back to roll back |
| Secrets leak | — | Service URL only in Secrets; the anon key can only read (RLS) |

### 15.2 Capacity (14-day window)

| Table | Rows/day | 14 days | Size (incl. indexes) |
|---|---|---|---|
| `observations` | ~250 | 3.5 k | < 5 MB (raw jsonb included) |
| `forecasts` | ~4,000 best_match + ~3 × 670 per-run ≈ 6,000 | 85 k | ~20 MB |
| `forecasts_daily` | ~250 | 3.5 k | < 1 MB |
| `satellite_features` | 0 (not built) | 0 | — |
| `predictions` | ~3,500 (4 kept issues × ~870) | 49 k | ~10 MB |
| `ingestion_runs` | ~170 | 2.4 k | < 2 MB |
| `raw_responses` | ~30 | 30-day retention | ~30 MB (TOAST-compressed) |
| **Total** | | | **< 100 MB of the 500 MB free tier** |

GitHub Actions: about 170 runs/day at 1–3 min each, unlimited on a public repo. A dashboard load is about 450 KB, well inside Vercel's Hobby bandwidth; Supabase data doesn't count toward it.

### 15.3 Cost (report §6)

| Item | Free tier used | Our usage | Cost |
|---|---|---|---|
| Open-Meteo API | < 10,000 calls/day, non-commercial | ~200 calls/day | RM0 |
| GitHub Actions | Unlimited minutes on public repos | ~300 min/day | RM0 |
| Supabase | 500 MB DB, 2 projects | < 100 MB | RM0 |
| Vercel | Hobby plan (static site) | 1 site | RM0 |
| Model training | The laptop, and the monthly `retrain.yml` run in GitHub Actions | Minutes per month | RM0 |
| **Total** | | | **RM0** |

For the report, add a column showing what a paid equivalent would cost (e.g. a hosted VM or a weather API subscription). Look up current prices when writing it.

---

## 16. Open items to verify during the build

**Status (9 Nov):** V6 checked (every RPC under 0.35 s as anon). V2 relies on the hourly fallback in §6.2. V1, V3, V4, V5 and V7 no longer apply, because Himawari and IMERG weren't built.

| # | Item | How to check | Fallback |
|---|---|---|---|
| V1 | S05 contains the whole 50 km disc | Print lat/lon at the mask centre and edges from the first file | Also load S06 and concatenate |
| V2 | `meta_key` run times line up with the `gfs_seamless` / `icon_seamless` outputs | Compare values before and after a run change | Store those models every hour and dedupe by value |
| V3 | IMERG Early collection name and OPeNDAP subsetting via `earthaccess` | Fetch one granule for yesterday | Download the full granule and slice it |
| V4 | Himawari archive on AWS covers Oct–Dec 2024/2025 | List `AHI-L1b-FLDK/2025/10/01/` | Use Himawari-8 or a shorter window |
| V5 | satpy reads a single segment and the runner install time is acceptable | Time the first workflow run | Pin versions; cache the pip wheels |
| V6 | The anon key can call each RPC under the 3 s timeout | `EXPLAIN ANALYZE` with 7 days of data | Materialized aggregates |
| V7 | IMERG Final history access for training labels | Fetch one Final granule from Oct 2025 | Use Early for history too, or reanalysis precipitation |
