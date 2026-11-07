-- 0001_core.sql: tables (architecture §7.1–7.6). All times are UTC timestamptz.

-- §7.1 Reference tables ---------------------------------------------------------------------------

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

-- §7.2 Run log and raw payloads -------------------------------------------------------------------

create table ingestion_runs (                   -- proof of continuous operation
  id           bigserial primary key,
  job          text not null check (job in ('observe','forecast','backfill','manual')),
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

-- §7.3 Observations (the "actual" weather, many sources) ------------------------------------------

create table observations (
  id               bigserial primary key,
  location_id      smallint not null references locations,
  source           text not null references sources(code),
  observed_at      timestamptz not null,        -- UTC, END of the interval (architecture §5)
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

-- §7.4 Forecast vault -----------------------------------------------------------------------------

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

-- §7.5 Satellite features -------------------------------------------------------------------------

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

-- §7.6 ML registry and predictions ----------------------------------------------------------------

create table ml_models (
  id              serial primary key,
  name            text not null,                -- rain_nowcast | bias_temperature | bias_humidity | bias_wind
  version         text not null,                -- v0-rule, v1.0, v1.1 …
  algorithm       text not null check (algorithm in ('rule','logreg','lightgbm','cnn')),
  features        text[] not null,
  train_window    tstzrange,
  test_window     tstzrange,
  metrics         jsonb not null default '{}'::jsonb,  -- offline test metrics + baselines + thresholds
  importance      jsonb,                               -- [{"feature":"frac_lt_235_r25","gain":0.31}, …]
  artifact_path   text,                                -- models/rain_nowcast/v1.0/model.txt
  artifact_sha256 text,
  is_active       boolean not null default false,
  trained_at      timestamptz not null default now(),
  unique (name, version)
);
create unique index ml_models_one_active on ml_models (name) where is_active;

create table predictions (
  id          bigserial primary key,
  location_id smallint not null references locations,
  model_id    int not null references ml_models,
  issued_at   timestamptz not null,             -- nowcast: satellite slot time · bias: forecast issued_at
  target_time timestamptz not null,             -- nowcast: window END · bias: forecast hour
  variable    text not null,                    -- rain_1h_prob | rain_3h_prob | temperature_c | humidity_pct | wind_speed_kmh
  value       real not null,
  base_model  text,                             -- bias: the raw model corrected (best_match)
  base_value  real,                             -- bias: the raw forecast value
  lead_hours  smallint,
  explain     jsonb,                            -- nowcast: top-5 contributions [{"feature","value","contrib"}]
  run_id      bigint references ingestion_runs,
  unique (location_id, model_id, variable, issued_at, target_time)
);
create index on predictions (variable, issued_at desc);
