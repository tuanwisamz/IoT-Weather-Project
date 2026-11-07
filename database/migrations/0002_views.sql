-- 0002_views.sql: the analytics base (architecture §11, api-spec §3.2).
-- Time zones are always explicit: UTC for hour buckets, Asia/Kuala_Lumpur for local days.

-- No `set search_path` here on purpose: a SET clause stops Postgres inlining the function, which made
-- v_pairs ~10x slower (it runs once per pair). It references no tables, so there's nothing to hijack.
create function lead_bucket(h int) returns text language sql immutable as $$
  select case when h < 6 then '000-006' when h < 12 then '006-012' when h < 24 then '012-024'
              when h < 48 then '024-048' when h < 72 then '048-072' when h < 120 then '072-120'
              else '120-168' end $$;

-- Hourly "actual" per source, using the (H-1h, H] convention.
-- openmeteo_current hours count as complete only when samples = 4; the RPCs filter on this.
create view v_actual_hourly with (security_invoker = true) as
select location_id, source,
       date_trunc('hour', observed_at - interval '1 second', 'UTC') + interval '1 hour'          as hour,
       count(*)::int                                                                               as samples,
       coalesce(avg(temperature_c)  filter (where extract(minute from observed_at at time zone 'UTC') = 0), avg(temperature_c))::real  as temperature_c,
       coalesce(avg(humidity_pct)   filter (where extract(minute from observed_at at time zone 'UTC') = 0), avg(humidity_pct))::real   as humidity_pct,
       coalesce(avg(wind_speed_kmh) filter (where extract(minute from observed_at at time zone 'UTC') = 0), avg(wind_speed_kmh))::real as wind_speed_kmh,
       coalesce(avg(pressure_hpa)   filter (where extract(minute from observed_at at time zone 'UTC') = 0), avg(pressure_hpa))::real   as pressure_hpa,
       sum(precipitation_mm)::real                                                                 as precipitation_mm,
       coalesce(bool_or(is_raining), sum(precipitation_mm) >= 0.1)                                 as rain_hour
from observations
group by 1, 2, 3;

-- Raw forecasts + the ML-corrected pseudo-model, one shape.
create view v_forecasts_all with (security_invoker = true) as
select location_id, model, origin, issued_at, target_time, lead_hours,
       temperature_c, humidity_pct, wind_speed_kmh, pressure_hpa, precipitation_mm, precip_probability_pct
from forecasts
union all
select p.location_id, p.base_model || '+ml', 'snapshot', p.issued_at, p.target_time, p.lead_hours,
       max(p.value) filter (where p.variable = 'temperature_c'),
       max(p.value) filter (where p.variable = 'humidity_pct'),
       max(p.value) filter (where p.variable = 'wind_speed_kmh'),
       null::real, null::real, null::real
from predictions p join ml_models m on m.id = p.model_id and m.name like 'bias_%' and m.is_active
group by 1, 2, 3, 4, 5, 6;

-- Forecast/actual pairs in long format: one row per (forecast hour × truth source × variable).
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

-- Latest observation per source (Overview · Now card).
create view v_now with (security_invoker = true) as
select distinct on (source) source, observed_at,
       extract(epoch from now() - observed_at)::int as age_s,
       temperature_c, humidity_pct, dew_point_c, precipitation_mm, wind_speed_kmh, wind_dir_deg,
       pressure_hpa, cloud_cover_pct, weather_code, is_raining, is_thunder
from observations where location_id = 1
order by source, observed_at desc;

-- The virtual rain indicator: one row. The 30-minute UNKNOWN cutoff is a single literal on purpose
-- (Implementation-plan §8, risk 4): raise it if Himawari latency makes the lamp flicker.
create view v_rain_status with (security_invoker = true) as
with m as (select * from ml_models where name = 'rain_nowcast' and is_active),
s as (
  select p.issued_at, p.value as prob_1h, p.explain,
         avg(p.value) over (order by p.issued_at rows between 2 preceding and current row) as prob_1h_smoothed
  from predictions p join m on m.id = p.model_id
  where p.variable = 'rain_1h_prob' and p.issued_at > now() - interval '6 hours'
)
select s.issued_at, m.version as model_version, s.prob_1h, s.prob_1h_smoothed::real as prob_1h_smoothed,
       (select value from predictions p3 where p3.model_id = m.id and p3.variable = 'rain_3h_prob'
          and p3.issued_at = s.issued_at) as prob_3h,
       case when s.issued_at < now() - interval '30 minutes' then 'UNKNOWN'
            when s.prob_1h_smoothed >= coalesce((m.metrics #>> '{thresholds,likely}')::real, 0.6) then 'RAIN_LIKELY'
            when s.prob_1h_smoothed >= coalesce((m.metrics #>> '{thresholds,watch}')::real, 0.3)  then 'WATCH'
            else 'CLEAR' end as level,
       coalesce((m.metrics #>> '{thresholds,watch}')::real, 0.3)  as watch_threshold,
       coalesce((m.metrics #>> '{thresholds,likely}')::real, 0.6) as likely_threshold,
       (select f.precip_probability_pct from forecasts f where f.model = 'best_match'
          and f.target_time = date_trunc('hour', now(), 'UTC') + interval '1 hour'
        order by f.issued_at desc limit 1) as om_prob_next_hour,
       s.explain
from s cross join m
order by s.issued_at desc limit 1;

-- Proof of "3+ days continuous": the longest run of openmeteo_current samples with no gap > 1 h.
create view v_collection_window with (security_invoker = true) as
with t as (select observed_at,
                  observed_at - lag(observed_at) over (order by observed_at) as gap
           from observations where source = 'openmeteo_current' and location_id = 1),
g as (select observed_at, sum(case when gap > interval '1 hour' then 1 else 0 end)
                             over (order by observed_at) as grp from t),
streaks as (select min(observed_at) s, max(observed_at) e, count(*) n from g group by grp)
select (select min(observed_at) from t) as first_obs_at, (select max(observed_at) from t) as last_obs_at,
       s as streak_start, e as streak_end,
       (extract(epoch from e - s) / 3600)::real as streak_hours, n::int as samples,
       (extract(epoch from e - s) / 900)::int + 1 as expected_samples,
       extract(epoch from e - s) / 3600 >= 72 as meets_3_days
from streaks order by e - s desc limit 1;

-- Coverage per local day and stream. Expected counts are prorated on the first day (from the first
-- observation) and on today (up to now), so a day in progress isn't shown as a failure.
create view v_coverage_daily with (security_invoker = true) as
with bounds as (
  -- Collection starts at the first job run, not the first observation: METAR's 3-hour lookback
  -- returns reports from before the clock started.
  select coalesce((select min(started_at) from ingestion_runs where job in ('observe', 'forecast', 'backfill')),
                  (select min(observed_at) from observations where location_id = 1)) as first_at
),
days as (
  select d::date as local_date,
         greatest(d::timestamp at time zone 'Asia/Kuala_Lumpur',
                  date_trunc('hour', b.first_at - interval '1 second', 'UTC')) as win_start,
         least((d::date + 1)::timestamp at time zone 'Asia/Kuala_Lumpur', now()) as win_end
  from bounds b,
       generate_series((b.first_at at time zone 'Asia/Kuala_Lumpur')::date,
                       (now() at time zone 'Asia/Kuala_Lumpur')::date, interval '1 day') d
  where b.first_at is not null
),
streams(stream, per_day) as (values
  ('openmeteo_current', 96), ('metar_wmki', 24), ('imerg_early', 48), ('satellite', 144), ('forecast_best_match', 24)
),
recv as (
  -- interval-end stamps: a sample at local 24:00 covers 23:45–24:00 of the day before
  select ((observed_at - interval '1 second') at time zone 'Asia/Kuala_Lumpur')::date as local_date, source as stream,
         count(*) as received, count(*) filter (where is_backfill) as backfilled
  from observations where location_id = 1 group by 1, 2
  union all
  select (slot_time at time zone 'Asia/Kuala_Lumpur')::date, 'satellite', count(distinct slot_time), 0
  from satellite_features where location_id = 1 group by 1
  union all
  select (issued_at at time zone 'Asia/Kuala_Lumpur')::date, 'forecast_best_match', count(distinct issued_at), 0
  from forecasts where location_id = 1 and model = 'best_match' and origin = 'snapshot' group by 1
)
select d.local_date, s.stream, coalesce(r.received, 0)::int as received, e.expected::int as expected,
       least(100, 100.0 * coalesce(r.received, 0) / nullif(e.expected, 0))::real as coverage_pct,
       coalesce(r.backfilled, 0)::int as backfilled
from days d
cross join streams s
cross join lateral (select greatest(1, floor(s.per_day * extract(epoch from d.win_end - d.win_start) / 86400)) as expected) e
left join recv r on r.local_date = d.local_date and r.stream = s.stream;

-- 0004_rls.sql may already have run on the live database, so this file grants its own objects.
grant execute on function lead_bucket(int) to anon, authenticated;
grant select on v_actual_hourly, v_forecasts_all, v_pairs, v_now, v_rain_status, v_collection_window,
                v_coverage_daily to anon, authenticated;
