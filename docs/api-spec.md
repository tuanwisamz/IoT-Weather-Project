# Iskandar Weather Watch — API & Data Contract Specification v1

**v1.1 · Written 31 Oct 2026, updated 7 Nov 2026 · Companion to [architecture.md](architecture.md)**

> **Scope change, 7 Nov 2026.** Data from Wed 4 Nov is retrieved retrospectively (§5.8, §6), and `database/migrations/0006_retro_window.sql` changes several contracts below. FastAPI, Himawari and IMERG surfaces are out of scope. See [Implementation-plan.md](Implementation-plan.md) §1 and §5.1.

This document defines every interface the code depends on:

| § | Surface | Who calls it | Required for core rubric? |
|---|---|---|---|
| 3 | **Supabase Data API**: tables, views and RPC functions (PostgREST) | React dashboard, FastAPI | **Yes**: the dashboard's main data path |
| 4 | **FastAPI extras** (`/api/v1`) | React ML Lab page, CSV export | No: extras only (the service may be asleep) |
| 5 | **Upstream contracts**: Open-Meteo, METAR, Himawari, IMERG → our columns | Ingestion jobs | Yes |
| 6 | **Job CLI contract** | GitHub Actions, local runs | Yes |

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Auth | None for readers. The dashboard is public and read-only. Supabase calls carry the **anon / publishable key** (RLS allows `SELECT` and RPC `EXECUTE` only). FastAPI has no auth; it is read-only |
| Time in | ISO 8601 with an offset, e.g. `2026-11-02T00:00:00+08:00`. Date-only params (`date`) are **local MYT dates** |
| Time out | Supabase returns `timestamptz` in UTC (`…+00:00`); the frontend formats it in `Asia/Kuala_Lumpur`. FastAPI returns ISO 8601 with `+08:00` |
| Ranges | `p_from` is inclusive, `p_to` is exclusive, applied to `target_time` (forecasts) or `observed_at` / `slot_time`. Max range 31 days; longer ranges are clamped |
| Units | °C · % · mm · km/h · hPa (MSL) · K · probability 0–1 for ML, 0–100 % for Open-Meteo `precip_probability_pct` |
| Numbers | Metrics are rounded to 3 significant decimals by the frontend, not the DB. `null` means "not computable" (e.g. `n = 0`) |
| Sample size | Every metric row carries `n`. The UI must show it |
| FastAPI errors | `{"error": {"code": "VALIDATION_ERROR", "message": "…", "details": {}}}` with HTTP 400 / 404 / 422 / 503 |
| Supabase errors | PostgREST error JSON (`code`, `message`, `details`, `hint`); `57014` = statement timeout (3 s for anon) |
| Row cap | PostgREST returns ≤ 1,000 rows per request. Every RPC returns aggregated or bounded rows, and raw tables need `.range()` |

---

## 2. Enums

| Enum | Values |
|---|---|
| `variable` | `temperature_c`, `humidity_pct`, `wind_speed_kmh`, `pressure_hpa`, `precipitation_mm` |
| `truth_source` | `openmeteo_current` (default), `openmeteo_reanalysis`, `metar_wmki`, `imerg_early` |
| `model` | `best_match`, `ecmwf_ifs025`, `gfs_seamless`, `icon_seamless`, optional `ecmwf_aifs025_single`, `jma_seamless`, and the pseudo-model `best_match+ml` |
| `origin` | `snapshot` (stored live), `previous_runs` (rebuilt by backfill) |
| `lead_bucket` | `000-006`, `006-012`, `012-024`, `024-048`, `048-072`, `072-120`, `120-168` |
| `rain_level` | `CLEAR`, `WATCH`, `RAIN_LIKELY`, `UNKNOWN` (newest prediction older than 30 min) |
| `job` | `observe`, `forecast`, `backfill`, `manual` |
| `run_status` | `running`, `success`, `partial`, `failed` |
| `ml_name` | `rain_nowcast`, `bias_temperature`, `bias_humidity`, `bias_wind` |
| `pred_variable` | `rain_1h_prob`, `rain_3h_prob`, `temperature_c`, `humidity_pct`, `wind_speed_kmh` |

**Variable availability by truth source** (cells with no data are excluded from pairs automatically):

| | temperature | humidity | wind | pressure | precipitation | rain yes/no |
|---|---|---|---|---|---|---|
| `openmeteo_current` | ✓ | ✓ | ✓ | ✓ | ✓ (15-min sums) | from mm |
| `openmeteo_reanalysis` | ✓ | ✓ | ✓ | ✓ | ✓ | from mm |
| `metar_wmki` | ✓ | ✓ (derived) | ✓ | ✓ (QNH) | — | ✓ (`wxString`) |
| `imerg_early` | — | — | — | — | ✓ | ✓ |

---

## 3. Supabase Data API (primary read path)

Base: `https://<project-ref>.supabase.co/rest/v1/`, reached through `supabase-js`.

```ts
const { data, error } = await supabase.rpc('rpc_metrics_by_lead', {
  p_from: '2026-11-01T00:00:00+08:00', p_to: '2026-11-08T00:00:00+08:00', p_truth: 'openmeteo_current',
});
```

Every RPC is `language sql stable security invoker set search_path = public`, with `grant execute … to anon`.

### 3.1 Summary

| Object | Kind | Used by (design-spec panel) | Refresh |
|---|---|---|---|
| `v_now` | view | Overview · Now card | 60 s |
| `v_rain_status` | view | Overview · Rain indicator, top bar badge | 60 s |
| `v_collection_window` | view | Top bar range default, Health · banner | 10 min |
| `v_coverage_daily` | view | Health · coverage grid | 2 min |
| `rpc_kpis` | rpc | Overview · KPI row | 10 min |
| `rpc_next_24h` | rpc | Overview · 24 h strip | 10 min |
| `rpc_forecast_vs_actual` | rpc | Accuracy · main time series | on change |
| `rpc_metrics_by_lead` | rpc | Accuracy · error vs lead | 10 min |
| `rpc_skill_vs_persistence` | rpc | Accuracy · skill chart | 10 min |
| `rpc_leaderboard` | rpc | Accuracy · leaderboard | 10 min |
| `rpc_error_heatmap` | rpc | Accuracy · hour × date heatmap | on change |
| `rpc_daily_pairs` | rpc | Accuracy · next-day table | 10 min |
| `rpc_rain_contingency` | rpc | Rain · scorecard | 10 min |
| `rpc_brier` | rpc | Rain · Brier tiles | 10 min |
| `rpc_reliability` | rpc | Rain · reliability diagram | 10 min |
| `rpc_rain_heatmap` | rpc | Rain · hour × date rain map | 10 min |
| `rpc_nowcast_timeline` | rpc | Rain · nowcast timeline | 60 s |
| `rpc_bias_eval` | rpc | ML Lab · raw vs corrected | 10 min |
| `rpc_uptime_daily` | rpc | Health · uptime bars | 2 min |
| `rpc_runs_timeline` | rpc | Health · run timeline, delay chart | 2 min |
| `ml_models` | table | ML Lab · model cards (fallback when FastAPI is asleep) | 10 min |
| `ingestion_runs` | table | Health · latest runs table (`order=started_at.desc&limit=50`) | 2 min |
| `sources`, `forecast_models`, `locations` | tables | Pickers, About page | once |

### 3.2 Views

#### `v_now`: latest observation per source

| Column | Type | Notes |
|---|---|---|
| `source` | text | one row per source |
| `observed_at` | timestamptz | |
| `age_s` | int | `now() − observed_at` in seconds |
| `temperature_c`, `humidity_pct`, `dew_point_c`, `precipitation_mm`, `wind_speed_kmh`, `wind_dir_deg`, `pressure_hpa`, `cloud_cover_pct`, `weather_code` | real / smallint | null where the source lacks the variable |
| `is_raining`, `is_thunder` | boolean | |

```sql
create view v_now with (security_invoker = true) as
select distinct on (source) source, observed_at,
       extract(epoch from now() - observed_at)::int as age_s,
       temperature_c, humidity_pct, dew_point_c, precipitation_mm, wind_speed_kmh, wind_dir_deg,
       pressure_hpa, cloud_cover_pct, weather_code, is_raining, is_thunder
from observations where location_id = 1
order by source, observed_at desc;
```

#### `v_rain_status`: the virtual rain indicator (one row)

| Column | Type | Notes |
|---|---|---|
| `issued_at` | timestamptz | newest satellite slot scored |
| `model_version` | text | e.g. `v0-rule`, `v1.0` |
| `prob_1h`, `prob_3h` | real 0–1 | raw model output |
| `prob_1h_smoothed` | real 0–1 | **sliding window**: mean of the last 3 slots (30 min), so the light doesn't flicker |
| `level` | rain_level | `≥ likely` → `RAIN_LIKELY`, `≥ watch` → `WATCH`, else `CLEAR`; `UNKNOWN` if older than 30 min |
| `watch_threshold`, `likely_threshold` | real | from `ml_models.metrics.thresholds` |
| `om_prob_next_hour` | real 0–100 | Open-Meteo's own probability for comparison |
| `explain` | jsonb | top-5 contributions `[{"feature","value","contrib"}]` |

```sql
create view v_rain_status with (security_invoker = true) as
with m as (select * from ml_models where name = 'rain_nowcast' and is_active),
s as (
  select p.issued_at, p.value as prob_1h, p.explain,
         avg(p.value) over (order by p.issued_at rows between 2 preceding and current row) as prob_1h_smoothed
  from predictions p join m on m.id = p.model_id
  where p.variable = 'rain_1h_prob' and p.issued_at > now() - interval '6 hours'
)
select s.issued_at, m.version as model_version, s.prob_1h, s.prob_1h_smoothed,
       (select value from predictions p3 where p3.model_id = m.id and p3.variable = 'rain_3h_prob'
          and p3.issued_at = s.issued_at) as prob_3h,
       case when s.issued_at < now() - interval '30 minutes' then 'UNKNOWN'
            when s.prob_1h_smoothed >= coalesce((m.metrics #>> '{thresholds,likely}')::real, 0.6) then 'RAIN_LIKELY'
            when s.prob_1h_smoothed >= coalesce((m.metrics #>> '{thresholds,watch}')::real, 0.3)  then 'WATCH'
            else 'CLEAR' end as level,
       coalesce((m.metrics #>> '{thresholds,watch}')::real, 0.3)  as watch_threshold,
       coalesce((m.metrics #>> '{thresholds,likely}')::real, 0.6) as likely_threshold,
       (select f.precip_probability_pct from forecasts f where f.model = 'best_match'
          and f.target_time = date_trunc('hour', now()) + interval '1 hour'
        order by f.issued_at desc limit 1) as om_prob_next_hour,
       s.explain
from s cross join m
order by s.issued_at desc limit 1;
```

#### `v_collection_window`: data coverage, retrieved and live

The streak includes retrieved rows, so `meets_3_days` on its own does **not** prove live collection. Always show it with `live_since`. `0006` adds these two columns; the SQL below is the original `0002` version.

| Column | Type | Notes |
|---|---|---|
| `live_since` | timestamptz | first `openmeteo_current` row with `is_backfill = false`; null until live collection starts |
| `backfilled_samples` | int | samples in the streak with `is_backfill = true` |
| `first_obs_at`, `last_obs_at` | timestamptz | across all `openmeteo_current` rows |
| `streak_start`, `streak_end` | timestamptz | longest run with no gap > 1 h (gaps-and-islands) |
| `streak_hours` | real | |
| `samples` | int | 15-min samples in the streak |
| `expected_samples` | int | `streak_hours × 4` |
| `meets_3_days` | boolean | `streak_hours ≥ 72` |

```sql
create view v_collection_window with (security_invoker = true) as
with t as (select observed_at,
                  observed_at - lag(observed_at) over (order by observed_at) as gap
           from observations where source = 'openmeteo_current' and location_id = 1),
g as (select observed_at, sum(case when gap > interval '1 hour' then 1 else 0 end)
                             over (order by observed_at) as grp from t),
streaks as (select min(observed_at) s, max(observed_at) e, count(*) n from g group by grp)
select (select min(observed_at) from t) as first_obs_at, (select max(observed_at) from t) as last_obs_at,
       s as streak_start, e as streak_end,
       extract(epoch from e - s) / 3600 as streak_hours, n as samples,
       (extract(epoch from e - s) / 900)::int + 1 as expected_samples,
       extract(epoch from e - s) / 3600 >= 72 as meets_3_days
from streaks order by e - s desc limit 1;
```

#### `v_coverage_daily`

| Column | Type | Notes |
|---|---|---|
| `local_date` | date | MYT |
| `stream` | text | `openmeteo_current`, `metar_wmki`, `imerg_early`, `satellite`, `forecast_best_match` |
| `received`, `expected` | int | expected: 96 / 24 / 48 / 144 / 24 per day |
| `coverage_pct` | real | `100 × received / expected`, capped at 100 |
| `backfilled` | int | rows with `is_backfill` (observations only) |

### 3.3 RPC functions

Shared parameter defaults: `p_truth text default 'openmeteo_current'`, `p_origin text default 'snapshot'`, `p_location smallint default 1`.

#### `rpc_kpis(p_from timestamptz, p_to timestamptz) returns jsonb`

```json
{
  "collection": { "streak_hours": 171.5, "meets_3_days": true, "uptime_pct": 98.6 },
  "temperature": { "model": "best_match", "lead_bucket": "012-024", "mae": 1.12, "bias": 0.64, "n": 162 },
  "rain": { "model": "best_match", "lead_bucket": "000-006", "csi": 0.41, "pod": 0.72, "far": 0.51, "n": 168 },
  "brier": { "model": "best_match", "brier": 0.142, "bss": 0.18, "n": 168 },
  "best_model": { "temperature": "ecmwf_ifs025", "rain": "best_match+ml" },
  "last_obs_at": "2026-11-08T03:45:00+00:00"
}
```

#### `rpc_next_24h() returns table(...)`

Built from the newest `best_match` snapshot plus `best_match+ml`, for hours now+1 to now+24.
Columns: `target_time`, `temperature_c`, `temperature_c_ml`, `precipitation_mm`, `precip_probability_pct`, `weather_code`, `wind_speed_kmh`.

#### `rpc_forecast_vs_actual(p_model text, p_variable text, p_lead_min int, p_from timestamptz, p_to timestamptz, p_truth text default 'openmeteo_current') returns table(...)`

For each target hour, this picks **the freshest forecast that was at least `p_lead_min` hours old**, which is what the lead-time slider shows ("the forecast as it stood 24 h before").

| Column | Type |
|---|---|
| `target_time` | timestamptz |
| `forecast` | real |
| `actual` | real (null if no truth yet: the line ends) |
| `error` | real |
| `issued_at` | timestamptz |
| `lead_hours` | smallint (≥ `p_lead_min`) |

```sql
create function rpc_forecast_vs_actual(p_model text, p_variable text, p_lead_min int,
    p_from timestamptz, p_to timestamptz, p_truth text default 'openmeteo_current')
returns table (target_time timestamptz, forecast real, actual real, error real,
               issued_at timestamptz, lead_hours smallint)
language sql stable security invoker set search_path = public as $$
  with f as (
    select distinct on (target_time) target_time, issued_at, lead_hours,
           case p_variable when 'temperature_c' then temperature_c when 'humidity_pct' then humidity_pct
                           when 'wind_speed_kmh' then wind_speed_kmh when 'pressure_hpa' then pressure_hpa
                           when 'precipitation_mm' then precipitation_mm end as forecast
    from v_forecasts_all
    where model = p_model and origin = 'snapshot' and lead_hours >= p_lead_min
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
    order by target_time, issued_at desc)
  select f.target_time, f.forecast, a.actual, f.forecast - a.actual, f.issued_at, f.lead_hours
  from f left join lateral (
    select case p_variable when 'temperature_c' then h.temperature_c when 'humidity_pct' then h.humidity_pct
                           when 'wind_speed_kmh' then h.wind_speed_kmh when 'pressure_hpa' then h.pressure_hpa
                           when 'precipitation_mm' then h.precipitation_mm end as actual
    from v_actual_hourly h
    where h.source = p_truth and h.hour = f.target_time
      and (h.source <> 'openmeteo_current' or h.samples = 4)) a on true
  order by f.target_time $$;
```

#### `rpc_metrics_by_lead(p_from, p_to, p_truth default 'openmeteo_current', p_origin default 'snapshot') returns table(...)`

| Column | Type | Formula |
|---|---|---|
| `model`, `variable`, `lead_bucket` | text | group keys |
| `n` | int | `count(*)` |
| `bias` | real | `avg(error)` (positive = forecast too high) |
| `mae` | real | `avg(abs(error))` |
| `rmse` | real | `sqrt(avg(error²))` |
| `r` | real | `corr(forecast, actual)` (null if n < 3) |

```sql
  select model, variable, lead_bucket, count(*)::int as n,
         avg(error)::real, avg(abs(error))::real, sqrt(avg(error * error))::real,
         case when count(*) >= 3 then corr(forecast, actual)::real end
  from v_pairs
  where truth_source = p_truth and origin = p_origin
    and target_time >= p_from and target_time < p_to
  group by model, variable, lead_bucket
  order by model, variable, lead_bucket;
```

#### `rpc_skill_vs_persistence(p_from, p_to, p_variable text, p_truth default 'openmeteo_current') returns table(...)`

The reference forecast is **24 h persistence**: "same as this hour yesterday", which is a fair baseline for a strong diurnal cycle.
Columns: `model`, `lead_bucket`, `n`, `mae_model`, `mae_persistence`, `skill` (= `1 − mae_model / mae_persistence`; > 0 means the model beats persistence).

#### `rpc_rain_contingency(p_from, p_to, p_truth default 'openmeteo_current', p_threshold_mm real default 0.1) returns table(...)`

A forecast rain hour is `precipitation_mm ≥ p_threshold_mm`. An observed rain hour is `v_actual_hourly.rain_hour`.

| Column | Formula (a = hits, b = false alarms, c = misses, d = correct negatives) |
|---|---|
| `model`, `lead_bucket` | group keys |
| `hits`, `false_alarms`, `misses`, `correct_negatives`, `n` | counts |
| `pod` | a / (a + c) |
| `far` | b / (a + b) |
| `csi` | a / (a + b + c) |
| `freq_bias` | (a + b) / (a + c) |
| `hss` | 2(ad − bc) / ((a + c)(c + d) + (a + b)(b + d)) |

Every ratio is wrapped in `nullif(denominator, 0)`.

#### `rpc_brier(p_from, p_to, p_truth default 'openmeteo_current') returns table(...)`

Probability is `precip_probability_pct / 100`; the outcome is `rain_hour`.
Columns: `model`, `lead_bucket`, `n`, `brier` (= avg((p − o)²)), `base_rate`, `brier_clim` (= base_rate × (1 − base_rate)), `bss` (= 1 − brier / brier_clim).
Rows where the model has no probability (null) are excluded.

#### `rpc_reliability(p_from, p_to, p_model text default 'best_match', p_lead_max int default 24, p_truth default 'openmeteo_current') returns table(...)`

Ten bins: [0,10), [10,20) … [90,100].
Columns: `bin_lower`, `bin_upper`, `n`, `mean_forecast` (0–1), `observed_freq` (0–1).

#### `rpc_leaderboard(p_from, p_to, p_lead_max int default 72, p_truth default 'openmeteo_current') returns table(...)`

| Column | Notes |
|---|---|
| `model` | including `best_match+ml` |
| `n` | pairs at leads ≤ `p_lead_max` |
| `temp_mae`, `rh_mae`, `wind_mae` | real |
| `rain_csi` | at 0.1 mm |
| `brier` | null for models without probabilities, and for `+ml` |
| `rank_overall` | mean of the per-metric ranks (lower is better; nulls are skipped) |

#### `rpc_error_heatmap(p_from, p_to, p_model text, p_variable text, p_lead_bucket text default '012-024', p_truth default 'openmeteo_current') returns table(...)`

Columns: `local_date` (date), `local_hour` (0–23), `mean_error`, `n`. This reveals afternoon-storm misses.

#### `rpc_rain_heatmap(p_from, p_to, p_truth default 'openmeteo_current') returns table(...)`

Columns: `local_date`, `local_hour`, `precipitation_mm` (observed), `rain_hour`, `fc_prob_0_6h` (best_match probability at lead 0–6 h, 0–100).

#### `rpc_daily_pairs(p_from_date date, p_to_date date, p_model text default 'best_match', p_lead_days int default 1, p_truth default 'openmeteo_current') returns table(...)`

This uses the **earliest** snapshot issued on local day `target_date − p_lead_days`. Observed daily values come from `v_actual_hourly` grouped by `((hour − 1 h) at time zone 'Asia/Kuala_Lumpur')::date`, and only for days with ≥ 22 complete hours.

| Column | Notes |
|---|---|
| `target_date` | local |
| `temp_max_fc`, `temp_max_obs`, `temp_min_fc`, `temp_min_obs` | °C |
| `rain_fc_mm`, `rain_obs_mm` | daily totals |
| `rain_prob_max_fc` | % |
| `rain_day_fc`, `rain_day_obs` | boolean (≥ 1 mm) |
| `hours_complete` | int (24 = fully observed) |

#### `rpc_nowcast_timeline(p_from, p_to) returns table(...)`

One row per satellite slot (max 31 days × 144 = 4,464 rows, so the client asks for ≤ 3 days at a time).

| Column | Notes |
|---|---|
| `slot_time` | timestamptz |
| `prob_1h`, `prob_1h_smoothed`, `prob_3h` | 0–1 (active nowcast model) |
| `level` | rain_level at that time |
| `om_prob_next_hour` | 0–100 |
| `bt_min_r25`, `frac_lt_235_r25`, `d_bt_mean_30m_r25` | satellite context |
| `rain_obs_mm_current` | `openmeteo_current` 15-min precipitation at the slot |
| `rain_obs_mm_imerg` | IMERG half-hour precipitation covering the slot (null until it arrives) |

#### `rpc_bias_eval(p_from, p_to, p_truth default 'openmeteo_current') returns table(...)`

Columns: `variable`, `lead_bucket`, `n`, `mae_raw` (best_match), `mae_corrected` (best_match+ml), `improvement_pct` (= 100 × (1 − corrected / raw)). It compares the **same** target hours and issue times only (an inner join on both).

#### `rpc_uptime_daily(p_from, p_to) returns table(...)`

Columns: `local_date`, `job`, `expected_runs` (observe 144 · forecast 24 · backfill 1), `success_runs`, `partial_runs`, `failed_runs`, `missing_runs` (= expected − total, min 0), `uptime_pct` (= 100 × (success + partial) / expected), `median_start_delay_s`.

**Start delay** = `started_at − nominal slot`, where the nominal slot for `observe` is the most recent `HH:M7` and for `forecast` is `HH:17`.

#### `rpc_runs_timeline(p_from, p_to, p_job text default null) returns table(...)`

Columns: `id`, `job`, `status`, `started_at`, `finished_at`, `duration_s`, `start_delay_s`, `rows_written` (jsonb), `failed_steps` (text[]). Capped at 1,000 rows, newest first.

### 3.4 Raw table reads allowed from the browser

| Table | Typical query | Notes |
|---|---|---|
| `ml_models` | `select=*&is_active=eq.true` | The model card fallback when FastAPI is asleep |
| `ingestion_runs` | `select=id,job,status,started_at,finished_at,rows_written,error&order=started_at.desc&limit=50` | Health · latest runs table |
| `satellite_features` | `select=slot_time,radius_km,bt_min_k,frac_lt_235&slot_time=gte.<iso>&order=slot_time` | Rain page sparkline |
| `forecast_models`, `sources`, `locations` | `select=*` | Pickers, About page |

`raw_responses` is **not** readable by anon.

---

## 4. FastAPI extras (`/api/v1`)

- **Base URL:** `https://iww-api.onrender.com/api/v1` (Render free; cold start ~50–60 s)
- **Docs:** `/docs` (OpenAPI, generated)
- **CORS:** `CORS_ORIGINS` only
- **Caching:** in-process TTL cache of 5 min, keyed by path + query; `Cache-Control: public, max-age=300`
- **Rate limit:** 60 requests/min per IP (`slowapi`) → `429 RATE_LIMITED`
- **DB:** role `api_reader` (read-only); statement timeout 10 s

### 4.1 Endpoint summary

| Method | Path | Purpose | Dashboard use |
|---|---|---|---|
| GET | `/health` | Liveness + DB + model check | Wake-up ping on first load |
| GET | `/meta` | Location, enums, active models, data window, attribution | About page |
| GET | `/models` | Active model cards | ML Lab |
| GET | `/models/{name}` | One model card with offline metrics, baselines, importance | ML Lab |
| GET | `/nowcast/latest` | Latest nowcast with recomputed per-feature contributions | ML Lab · "why" panel |
| GET | `/nowcast/evaluation` | Live ROC curve, AUC, Brier, POD/FAR/CSI, warning lead, baselines | ML Lab · nowcast scorecard |
| GET | `/bias/evaluation` | Raw vs corrected by lead with bootstrap CI | ML Lab · bias panel |
| GET | `/analytics/onset` | Rain events and onset-timing error | Rain page (P1) |
| GET | `/analytics/agreement` | How well the truth sources agree with each other | Accuracy page ("what is actual?") |
| GET | `/events` | Detected rain events for the storm replay | Rain page · replay picker (P1) |
| GET | `/export/{dataset}.csv` | CSV download | Export buttons |
| GET | `/report/summary` | Frozen-window headline numbers for the report | Writing the report |

### 4.2 Details

#### `GET /health`

```json
{ "status": "ok", "version": "1.0.0", "db": "ok", "models_loaded": ["rain_nowcast:v1.0", "bias_temperature:v1.0"],
  "uptime_s": 42, "time": "2026-11-05T14:02:11+08:00" }
```

Returns `503 DB_UNAVAILABLE` with the same shape (`"db": "error"`) if the pool can't connect.

#### `GET /meta`

```json
{
  "location": { "name": "Seri Iskandar", "lat": 4.35993, "lon": 100.98491, "grid_lat": 4.3937, "grid_lon": 100.9738, "tz": "Asia/Kuala_Lumpur" },
  "variables": ["temperature_c", "humidity_pct", "wind_speed_kmh", "pressure_hpa", "precipitation_mm"],
  "models": [{ "code": "best_match", "name": "Open-Meteo Best Match", "update_h": 1 }, "…"],
  "truth_sources": [{ "code": "metar_wmki", "kind": "station", "distance_km": 26 }, "…"],
  "lead_buckets": ["000-006", "006-012", "012-024", "024-048", "048-072", "072-120", "120-168"],
  "thresholds": { "rain_hour_mm": 0.1, "rain_day_mm": 1.0 },
  "data_window": { "first_obs_at": "2026-11-01T09:15:00+08:00", "last_obs_at": "2026-11-08T11:45:00+08:00", "meets_3_days": true },
  "attribution": ["Weather data by Open-Meteo.com (CC BY 4.0)", "Himawari-9: JMA via NOAA Open Data", "Imagery: NASA GIBS", "IMERG: NASA GPM", "METAR: NOAA Aviation Weather Center"]
}
```

#### `GET /models` · `GET /models/{name}`

`name` ∈ `ml_name`. Returns `404 MODEL_NOT_FOUND` if there is no active version.

```json
{
  "name": "rain_nowcast", "version": "v1.0", "algorithm": "lightgbm",
  "trained_at": "2026-11-04T10:00:00+08:00",
  "train_window": ["2025-10-01", "2025-11-30"], "test_window": ["2025-12-01", "2025-12-31"],
  "features": ["frac_lt_235_r25", "bt_p10_k_r10", "d_bt_mean_30m_r25", "rh", "cape", "hour_sin", "…"],
  "metrics": {
    "test": { "roc_auc": 0.86, "brier": 0.112, "bss": 0.31, "pod": 0.78, "far": 0.39, "csi": 0.52, "median_warning_min": 40, "n": 4320, "base_rate": 0.21 },
    "baselines": {
      "openmeteo_prob": { "roc_auc": 0.71, "brier": 0.151 },
      "persistence":    { "roc_auc": 0.64, "brier": 0.188 },
      "rule_235k":      { "roc_auc": 0.77, "brier": 0.139 }
    },
    "thresholds": { "watch": 0.28, "likely": 0.55 }
  },
  "importance": [{ "feature": "frac_lt_235_r25", "gain": 0.31 }, { "feature": "d_bt_mean_30m_r25", "gain": 0.17 }]
}
```

(All numbers above are placeholders that show the shape, not results.)

#### `GET /nowcast/latest`

```json
{
  "issued_at": "2026-11-05T14:00:00+08:00", "model_version": "v1.0",
  "prob_1h": 0.64, "prob_1h_smoothed": 0.58, "prob_3h": 0.81, "level": "WATCH",
  "om_prob_next_hour": 45,
  "contributions": [
    { "feature": "frac_lt_235_r25", "value": 0.42, "contrib": 0.91, "label": "42% of cloud within 25 km colder than 235 K" },
    { "feature": "d_bt_mean_30m_r25", "value": -6.1, "contrib": 0.37, "label": "Cloud tops cooled 6.1 K in 30 min" }
  ],
  "base_value": -1.32
}
```

`contrib` is in log-odds (LightGBM `pred_contrib`). The UI shows the sign and relative size. `label` is built from a template per feature, defined in `features/explain.py`.

#### `GET /nowcast/evaluation?from=&to=&truth=imerg_early&horizon=1h`

| Param | Type | Default |
|---|---|---|
| `from`, `to` | ISO 8601 | the collection window |
| `truth` | `imerg_early` \| `openmeteo_current` \| `metar_wmki` | `imerg_early` |
| `horizon` | `1h` \| `3h` | `1h` |

```json
{
  "n": 812, "base_rate": 0.19, "label_lag_note": "IMERG Early arrives ~4–6 h late; the newest hours are excluded",
  "model":     { "roc_auc": 0.83, "brier": 0.121, "bss": 0.22, "pod": 0.74, "far": 0.41, "csi": 0.49, "median_warning_min": 35 },
  "baselines": { "openmeteo_prob": { "roc_auc": 0.70, "brier": 0.149 }, "persistence": { "roc_auc": 0.62, "brier": 0.190 }, "rule_235k": { "roc_auc": 0.75, "brier": 0.140 } },
  "roc": [{ "fpr": 0.0, "tpr": 0.0, "threshold": 1.0 }, "… ≤ 50 points"],
  "reliability": [{ "bin_lower": 0.0, "bin_upper": 0.1, "n": 402, "mean_forecast": 0.04, "observed_freq": 0.05 }, "…"]
}
```

`422 INSUFFICIENT_DATA` if `n < 30` or there are no positive labels.

#### `GET /bias/evaluation?variable=temperature_c&from=&to=&truth=openmeteo_current`

```json
{
  "variable": "temperature_c",
  "rows": [
    { "lead_bucket": "000-006", "n": 140, "mae_raw": 0.81, "mae_corrected": 0.66, "improvement_pct": 18.5, "ci95": [9.1, 26.0] },
    { "lead_bucket": "024-048", "n": 160, "mae_raw": 1.42, "mae_corrected": 1.05, "improvement_pct": 26.1, "ci95": [17.3, 33.8] }
  ]
}
```

`ci95` comes from 1,000 bootstrap resamples, done in blocks of whole days to respect autocorrelation.

#### `GET /analytics/onset?from=&to=&model=best_match&truth=openmeteo_current&lead_min=6`

A rain event is detected with a **sliding window**: 3 consecutive 15-min samples summing ≥ 0.3 mm start an event, and 4 dry samples end it. The forecast onset is the first forecast hour ≥ 0.1 mm within ±6 h of the observed onset, taken from forecasts at least `lead_min` hours old.

```json
{
  "events": [
    { "observed_onset": "2026-11-03T15:15:00+08:00", "observed_end": "2026-11-03T17:30:00+08:00", "total_mm": 18.4,
      "forecast_onset": "2026-11-03T14:00:00+08:00", "onset_error_h": -1.25, "nowcast_first_watch": "2026-11-03T14:30:00+08:00", "warning_min": 45 }
  ],
  "summary": { "n_events": 9, "detected": 7, "median_abs_onset_error_h": 1.5, "median_nowcast_warning_min": 40 }
}
```

#### `GET /analytics/agreement?from=&to=`

Pairwise agreement between truth sources on the hours where both have data:

```json
{
  "pairs": [
    { "a": "openmeteo_current", "b": "metar_wmki", "n": 150, "temp_mae": 1.3, "rain_agree_pct": 81.0, "rain_kappa": 0.48 },
    { "a": "openmeteo_current", "b": "imerg_early", "n": 160, "rain_agree_pct": 77.5, "rain_kappa": 0.41 }
  ]
}
```

#### `GET /events?from=&to=&min_mm=5`

The storm replay list. Each event carries `start`, `end`, `total_mm`, `peak_rate_mmh`, `min_bt_k`, and a `replay_window` of `[start − 2 h, end + 1 h]` that the Rain page loads into the IR loop and the nowcast timeline.

#### `GET /export/{dataset}.csv?from=&to=`

| `dataset` | Columns |
|---|---|
| `observations` | all `observations` columns except `raw` |
| `forecasts` | all `forecasts` columns |
| `pairs` | `v_pairs` filtered by `truth=` (default `openmeteo_current`) |
| `metrics_by_lead` | `rpc_metrics_by_lead` output |
| `predictions` | `predictions` without `explain` |
| `satellite_features` | all columns |
| `ingestion_runs` | all columns |

The CSV is streamed as `text/csv; charset=utf-8` with `Content-Disposition: attachment; filename="iww_<dataset>_<from>_<to>.csv"`. Times are UTC ISO 8601. The range is capped at 31 days (`400 RANGE_TOO_LARGE`).

#### `GET /report/summary?from=&to=`

This is one JSON document with every headline number the report needs, so the report and the dashboard agree:

- collection streak and uptime
- the best model per variable
- MAE at 24 h and 72 h
- rain CSI and Brier
- ML improvement
- the number of rain events
- source agreement
- the `n` behind each number

### 4.3 Error codes

| HTTP | `code` | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad enum, `from ≥ to`, malformed date |
| 400 | `RANGE_TOO_LARGE` | Range > 31 days |
| 404 | `MODEL_NOT_FOUND` / `NOT_FOUND` | Unknown model or dataset |
| 422 | `INSUFFICIENT_DATA` | Too few samples for the metric |
| 429 | `RATE_LIMITED` | > 60 requests/min per IP |
| 503 | `DB_UNAVAILABLE` | Pool can't connect or the query times out |

---

## 5. Upstream contracts (source → our columns)

### 5.1 Open-Meteo `current` → `observations` (`openmeteo_current`)

```
GET https://api.open-meteo.com/v1/forecast?latitude=4.35993&longitude=100.98491
    &current=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,rain,weather_code,
             wind_speed_10m,wind_direction_10m,pressure_msl,cloud_cover
    &timezone=GMT
```

| Response field | Column | Transform |
|---|---|---|
| `current.time` (`2026-10-30T22:00`) | `observed_at` | parse as UTC; this is the **end** of the 15-min interval |
| `current.interval` (✔ 900) | `interval_min` | ÷ 60 |
| `temperature_2m` | `temperature_c` | — |
| `relative_humidity_2m` | `humidity_pct` | — |
| `dew_point_2m` | `dew_point_c` | — |
| `precipitation` | `precipitation_mm` | 15-min sum |
| `wind_speed_10m` | `wind_speed_kmh` | — |
| `wind_direction_10m` | `wind_dir_deg` | — |
| `pressure_msl` | `pressure_hpa` | — |
| `cloud_cover` | `cloud_cover_pct` | — |
| `weather_code` | `weather_code` | — |
| whole `current` object | `raw` | — |

Gap fill: the same fields as `minutely_15=…&past_days=2&forecast_days=1`, inserted with `ON CONFLICT DO NOTHING` and `is_backfill = true`, only for times ≤ now.

### 5.2 Open-Meteo forecast → `forecasts` + `forecasts_daily`

```
GET https://api.open-meteo.com/v1/forecast?latitude=4.35993&longitude=100.98491
    &models=best_match,ecmwf_ifs025,gfs_seamless,icon_seamless           (only the models that are due)
    &hourly=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,precipitation_probability,
            wind_speed_10m,wind_direction_10m,pressure_msl,cloud_cover,cape,weather_code
    &daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,
           precipitation_hours,wind_speed_10m_max
    &forecast_days=7&timezone=Asia/Kuala_Lumpur
```

- ✔ With several models, keys come back as `<variable>_<model>` (e.g. `temperature_2m_ecmwf_ifs025`). Parse the model suffix by matching against the requested list, longest first. A single-model request returns bare keys.
- `hourly.time` is local because of `timezone=Asia/Kuala_Lumpur`. Convert with `utc_offset_seconds` (28,800). Do the same for `daily.time` → `target_date`, which stays a local date.
- `issued_at` = `date_trunc('hour', fetch time)` in UTC. `model_run_at` = `to_timestamp(meta.last_run_initialisation_time)`.
- Drop hourly rows with `target_time < issued_at`. The 700 hPa wind is **not** part of the vault; `observe` fetches it itself (§5.4).
- Mapping: `temperature_2m → temperature_c`, `relative_humidity_2m → humidity_pct`, `dew_point_2m → dew_point_c`, `precipitation → precipitation_mm`, `precipitation_probability → precip_probability_pct`, `wind_speed_10m → wind_speed_kmh`, `wind_direction_10m → wind_dir_deg`, `pressure_msl → pressure_hpa`, `cloud_cover → cloud_cover_pct`, `cape → cape_jkg`, `weather_code → weather_code`.
- Daily: `temperature_2m_max → temp_max_c`, `temperature_2m_min → temp_min_c`, `precipitation_sum → precipitation_sum_mm`, `precipitation_probability_max → precip_probability_max_pct`, `precipitation_hours → precipitation_hours`, `wind_speed_10m_max → wind_speed_max_kmh`. `lead_days = target_date − (issued_at at MYT)::date`.

### 5.3 Model run metadata

```
GET https://api.open-meteo.com/data/{meta_key}/static/meta.json
→ { "last_run_initialisation_time": 1793361600, "last_run_availability_time": 1793390263, "update_interval_seconds": 21600, … }
```

A model is **due** when `last_run_initialisation_time > max(model_run_at)` stored for it.

### 5.4 Weather context for satellite features (inside `observe`)

```
GET https://api.open-meteo.com/v1/forecast?latitude=4.35993&longitude=100.98491
    &hourly=wind_direction_700hPa,wind_speed_700hPa,cape,precipitation_probability&forecast_hours=2&timezone=GMT
```

This is used only in memory, for the upwind bearing and the nowcast weather features. It is not stored (already covered by the vault).

### 5.5 METAR → `observations` (`metar_wmki`)

```
GET https://aviationweather.gov/api/data/metar?ids=WMKI&format=json&hours=3
```

| Field (✔ example) | Column | Transform |
|---|---|---|
| `obsTime` (1793394000) | `observed_at` | unix → UTC |
| `temp` (25) | `temperature_c` | — |
| `dewp` (24) | `dew_point_c` | — |
| (derived) | `humidity_pct` | Magnus: `100·exp(17.625·Td/(243.04+Td)) / exp(17.625·T/(243.04+T))` |
| `wspd` (3, kt) | `wind_speed_kmh` | × 1.852 |
| `wdir` (30, or `"VRB"`) | `wind_dir_deg` | null if `VRB` |
| `altim` (1012, hPa QNH) | `pressure_hpa` | — |
| `wxString` (absent when no weather) | `is_raining` | regex `(^\|\s)[-+]?(VC)?(TS\|SH)?(RA\|DZ)` |
| `wxString` | `is_thunder` | contains `TS` |
| whole object (incl. `rawOb`) | `raw` | — |

### 5.6 Himawari-9 → `satellite_features`

```
LIST  https://noaa-himawari9.s3.amazonaws.com/?list-type=2&prefix=AHI-L1b-FLDK/YYYY/MM/DD/&delimiter=/
GET   https://noaa-himawari9.s3.amazonaws.com/AHI-L1b-FLDK/YYYY/MM/DD/HHMM/HS_H09_YYYYMMDD_HHMM_B13_FLDK_R20_S0510.DAT.bz2
```

`slot_time` = the `HHMM` folder (UTC scan start). Features as defined in [architecture.md §8](architecture.md). A missing file is logged as step `ok=false`, and `backfill` retries it.

### 5.7 IMERG Early → `observations` (`imerg_early`)

Collection `GPM_3IMERGHHE` (V07, ⚠ confirm), read with `earthaccess` login and an OPeNDAP subset over lat 4.26–4.46, lon 100.88–101.08 (3 × 3 cells).
Columns: `observed_at` = granule end time, `interval_min = 30`, `rain_rate_mmh` = mean `precipitation`, `precipitation_mm` = rate × 0.5, `is_raining` = max cell rate ≥ 0.5.

### 5.8 Open-Meteo Previous Runs (backfill + training)

```
GET https://previous-runs-api.open-meteo.com/v1/forecast?latitude=4.35993&longitude=100.98491
    &hourly=temperature_2m,temperature_2m_previous_day1,…,temperature_2m_previous_day7,
            relative_humidity_2m,relative_humidity_2m_previous_day1,…,
            wind_speed_10m,wind_speed_10m_previous_day1,…,precipitation_previous_day1,…
    &start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&timezone=GMT
```

✔ Day 1–7 values are present from about **Mar 2024** (null in Jan 2024). Backfill rows: `origin='previous_runs'`, `issued_at = target_time − N days`, so `lead_hours = 24 × N`.

✔ Checked 7 Nov 2026 with `models=best_match,ecmwf_ifs025,gfs_seamless,icon_seamless` for 1–6 Nov. Response keys are `<var>_previous_dayN_<model>`.

| Field | Result |
|---|---|
| Temperature, day 1–6 | Complete for all 4 models |
| Temperature, day 7 | Complete except `icon_seamless`, which is empty |
| Humidity, wind, pressure, precipitation, day 1 | Complete for all 4 models |
| `precipitation_probability_previous_dayN` | **Empty for all 4 models**, so skip this column |

### 5.9 Open-Meteo Historical Weather → `observations` (`openmeteo_reanalysis`)

```
GET https://archive-api.open-meteo.com/v1/archive?latitude=4.35993&longitude=100.98491
    &start_date=…&end_date=…&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,
    wind_speed_10m,wind_direction_10m,pressure_msl,cloud_cover,weather_code&timezone=GMT
```

`observed_at` = the hour (end of the accumulation hour), `interval_min = 60`. Upserts **overwrite** earlier values, because reanalysis can be revised.

### 5.10 NASA GIBS (browser only)

```
https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/Himawari_AHI_Band13_Clean_Infrared/default/{YYYY-MM-DDTHH:MM:00Z}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png
https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate_30min/default/{…}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png
```

✔ Tile matrix set `GoogleMapsCompatible_Level6` (max native zoom 6), PNG. Times are 10-min steps (Himawari) and 30-min steps (IMERG). Some time ranges have gaps, so the client skips frames that return 404.

---

## 6. Job CLI contract

```
python -m iww_ingest.jobs.observe   [--dry-run] [--trigger schedule|dispatch|local]
python -m iww_ingest.jobs.forecast  [--dry-run] [--models best_match,ecmwf_ifs025] [--force]
python -m iww_ingest.jobs.backfill  [--dry-run] [--days 2] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--steps om_gapfill,metar_history,previous_runs,retention]
python -m iww_ingest.tools.check    [--window FROM,TO]   # row counts, last run per job, collection streak; --window prints the data check counts
```

`rpc_next_day(p_from_date, p_to_date, p_model, p_lead_days, p_truth)` (`0007`) returns the same shape as `rpc_daily_pairs`, built from hourly forecasts, with `hours_fc` added and the rain probability removed.

`--since` and `--until` are local MYT dates for the one-off import. `--since` lifts the rule that gap fill only runs after the first live sample, and rows still get `is_backfill = true`. The `--max-slots` flag and the `reanalysis`, `imerg_catchup` and `himawari_gaps` steps are out of scope.

| Flag | Effect |
|---|---|
| `--dry-run` | Fetch and parse, print the row counts, write nothing (no `ingestion_runs` row) |
| `--force` | Ignore "model not due" and store a snapshot anyway |
| `--trigger` | Recorded in `ingestion_runs.trigger` |

| Exit code | Meaning |
|---|---|
| `0` | `success` or `partial`: the workflow stays green, and partial runs are visible on `/health` |
| `1` | `failed` (every step failed, or there's no DB connection): the workflow goes red, and GitHub emails you |

Environment: `SUPABASE_DB_URL` (required), `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` (IMERG steps), `CONTACT_EMAIL`, `GH_RUN_ID` (optional), `IWW_LOG_LEVEL` (default `INFO`).
