-- 0006_retro_window.sql: adapts the analytics to retrieved data (Implementation-plan §5.1).
-- The report window's forecasts are origin = 'previous_runs', so the RPCs stop reading snapshots only.
-- The two can't double count: the import stops at 7 Nov 00:00 MYT and live snapshots start after it.

update ml_models set is_active = false where name = 'rain_nowcast';   -- Himawari and the 235 K rule are dropped

drop view v_rain_status;
drop view v_collection_window;
drop view v_coverage_daily;

-- The rain lamp: Open-Meteo's own probability for the coming hour, from the newest best_match snapshot.
-- Columns match the original view, so `prob_1h_smoothed` simply equals `prob_1h`.
create view v_rain_status with (security_invoker = true) as
with latest as (
  select max(issued_at) as issued_at from forecasts
  where location_id = 1 and model = 'best_match' and origin = 'snapshot'
),
h as (
  select f.target_time, f.precip_probability_pct / 100.0 as p
  from forecasts f join latest l on f.issued_at = l.issued_at
  where f.location_id = 1 and f.model = 'best_match' and f.origin = 'snapshot'
    and f.target_time > now() and f.target_time <= now() + interval '3 hours'
),
s as (
  select (select issued_at from latest) as issued_at,
         (select p from h order by target_time limit 1)::real as prob_1h,
         (select max(p) from h)::real as prob_3h
)
select s.issued_at, 'open-meteo'::text as model_version, s.prob_1h, s.prob_1h as prob_1h_smoothed, s.prob_3h,
       case when s.prob_1h is null or s.issued_at < now() - interval '2 hours' then 'UNKNOWN'
            when s.prob_1h >= 0.6 then 'RAIN_LIKELY'
            when s.prob_1h >= 0.3 then 'WATCH'
            else 'CLEAR' end as level,
       0.3::real as watch_threshold, 0.6::real as likely_threshold,
       (s.prob_1h * 100)::real as om_prob_next_hour, null::jsonb as explain
from s
where s.issued_at is not null;

-- Data coverage. The streak includes retrieved rows, so it isn't proof of live collection on its own:
-- `live_since` is when live collection really began.
create view v_collection_window with (security_invoker = true) as
with t as (select observed_at, is_backfill,
                  observed_at - lag(observed_at) over (order by observed_at) as gap
           from observations where source = 'openmeteo_current' and location_id = 1),
g as (select observed_at, is_backfill,
             sum(case when gap > interval '1 hour' then 1 else 0 end) over (order by observed_at) as grp from t),
streaks as (select min(observed_at) s, max(observed_at) e, count(*) n,
                   count(*) filter (where is_backfill) b from g group by grp),
live as (select min(observed_at) as since from t where not is_backfill)
select (select min(observed_at) from t) as first_obs_at, (select max(observed_at) from t) as last_obs_at,
       s as streak_start, e as streak_end,
       (extract(epoch from e - s) / 3600)::real as streak_hours, n::int as samples,
       (extract(epoch from e - s) / 900)::int + 1 as expected_samples,
       extract(epoch from e - s) / 3600 >= 72 as meets_3_days,
       (select since from live) as live_since,
       b::int as backfilled_samples,
       (select count(*)::int from t, live where t.observed_at >= live.since) as live_samples,
       (select (extract(epoch from max(t.observed_at) - live.since) / 900)::int + 1
        from t, live where t.observed_at >= live.since group by live.since) as live_expected_samples
from streaks order by e - s desc limit 1;

-- Coverage per local day and stream, from the first retrieved sample. The first day is found an hour
-- later, because an import's first samples only fill the hour before --since.
create view v_coverage_daily with (security_invoker = true) as
with bounds as (
  select min(observed_at) as first_at
  from observations where location_id = 1 and source = 'openmeteo_current'
),
days as (
  select d::date as local_date,
         greatest(d::timestamp at time zone 'Asia/Kuala_Lumpur', b.first_at - interval '15 minutes') as win_start,
         least((d::date + 1)::timestamp at time zone 'Asia/Kuala_Lumpur', now()) as win_end
  from bounds b,
       generate_series(((b.first_at + interval '1 hour') at time zone 'Asia/Kuala_Lumpur')::date,
                       (now() at time zone 'Asia/Kuala_Lumpur')::date, interval '1 day') d
  where b.first_at is not null
),
streams(stream, per_day) as (values ('openmeteo_current', 96), ('metar_wmki', 24), ('forecast_best_match', 24)),
recv as (
  -- interval-end stamps: a sample at local 24:00 covers 23:45–24:00 of the day before
  select ((observed_at - interval '1 second') at time zone 'Asia/Kuala_Lumpur')::date as local_date, source as stream,
         count(*) as received, count(*) filter (where is_backfill) as backfilled
  from observations where location_id = 1 group by 1, 2
  union all
  select (target_time at time zone 'Asia/Kuala_Lumpur')::date, 'forecast_best_match', count(distinct target_time),
         count(distinct target_time) filter (where origin = 'previous_runs')
  from forecasts where location_id = 1 and model = 'best_match' and lead_hours = 24 group by 1
)
select d.local_date, s.stream, coalesce(r.received, 0)::int as received, e.expected::int as expected,
       least(100, 100.0 * coalesce(r.received, 0) / nullif(e.expected, 0))::real as coverage_pct,
       coalesce(r.backfilled, 0)::int as backfilled
from days d
cross join streams s
cross join lateral (select greatest(1, floor(s.per_day * extract(epoch from d.win_end - d.win_start) / 86400)) as expected) e
left join recv r on r.local_date = d.local_date and r.stream = s.stream;

grant select on v_rain_status, v_collection_window, v_coverage_daily to anon, authenticated;

-- Main time series: for each target hour, the freshest forecast that was at least p_lead_min hours old.
create or replace function rpc_forecast_vs_actual(p_model text, p_variable text, p_lead_min int,
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
    where model = p_model and lead_hours >= p_lead_min
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
    order by target_time, issued_at desc)
  select f.target_time, f.forecast, a.actual, (f.forecast - a.actual)::real, f.issued_at, f.lead_hours
  from f left join lateral (
    select case p_variable when 'temperature_c' then h.temperature_c when 'humidity_pct' then h.humidity_pct
                           when 'wind_speed_kmh' then h.wind_speed_kmh when 'pressure_hpa' then h.pressure_hpa
                           when 'precipitation_mm' then h.precipitation_mm end as actual
    from v_actual_hourly h
    where h.source = p_truth and h.hour = f.target_time
      and (h.source <> 'openmeteo_current' or h.samples = 4)) a on true
  where f.forecast is not null
  order by f.target_time $$;

create or replace function rpc_metrics_by_lead(p_from timestamptz, p_to timestamptz,
    p_truth text default 'openmeteo_current', p_origin text default 'any')
returns table (model text, variable text, lead_bucket text, n int, bias real, mae real, rmse real, r real)
language sql stable security invoker set search_path = public as $$
  select model, variable, lead_bucket, count(*)::int,
         avg(error)::real, avg(abs(error))::real, sqrt(avg(error * error))::real,
         case when count(*) >= 3 then corr(forecast, actual)::real end
  from v_pairs
  where truth_source = p_truth and (p_origin = 'any' or origin = p_origin)
    and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
  group by model, variable, lead_bucket
  order by model, variable, lead_bucket $$;

create or replace function rpc_rain_contingency(p_from timestamptz, p_to timestamptz,
    p_truth text default 'openmeteo_current', p_threshold_mm real default 0.1)
returns table (model text, lead_bucket text, hits int, false_alarms int, misses int, correct_negatives int,
               n int, pod real, far real, csi real, freq_bias real, hss real)
language sql stable security invoker set search_path = public as $$
  with c as (
    select model, lead_bucket,
           count(*) filter (where fc_mm >= p_threshold_mm and obs_rain)         as a,
           count(*) filter (where fc_mm >= p_threshold_mm and not obs_rain)     as b,
           count(*) filter (where fc_mm <  p_threshold_mm and obs_rain)         as c,
           count(*) filter (where fc_mm <  p_threshold_mm and not obs_rain)     as d
    from v_rain_pairs
    where truth_source = p_truth and fc_mm is not null
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
    group by model, lead_bucket)
  select model, lead_bucket, a::int, b::int, c::int, d::int, (a + b + c + d)::int,
         (a::float8 / nullif(a + c, 0))::real,
         (b::float8 / nullif(a + b, 0))::real,
         (a::float8 / nullif(a + b + c, 0))::real,
         ((a + b)::float8 / nullif(a + c, 0))::real,
         (2.0 * (a::float8 * d - b::float8 * c)
            / nullif((a + c)::float8 * (c + d) + (a + b)::float8 * (b + d), 0))::real
  from c order by model, lead_bucket $$;

-- Models are only compared at leads of 24–144 h, the range all four share in the archive
-- (ICON has no day 7). A model scored on a single metric, like best_match+ml, gets no overall rank.
create or replace function rpc_leaderboard(p_from timestamptz, p_to timestamptz, p_lead_max int default 144,
    p_truth text default 'openmeteo_current')
returns table (model text, n int, temp_mae real, rh_mae real, wind_mae real, rain_csi real, brier real,
               rank_overall real)
language sql stable security invoker set search_path = public as $$
  with e as (
    select model,
           count(*) filter (where variable = 'temperature_c')                    as n,
           avg(abs(error)) filter (where variable = 'temperature_c')             as temp_mae,
           avg(abs(error)) filter (where variable = 'humidity_pct')              as rh_mae,
           avg(abs(error)) filter (where variable = 'wind_speed_kmh')            as wind_mae
    from v_pairs
    where truth_source = p_truth and lead_hours >= 24 and lead_hours <= p_lead_max
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
    group by model),
  r as (
    select model,
           count(*) filter (where fc_mm >= 0.1 and obs_rain)::float8
             / nullif(count(*) filter (where fc_mm >= 0.1 or obs_rain), 0)        as rain_csi,
           avg(power(fc_prob_pct / 100.0 - obs_rain::int, 2))                    as brier
    from v_rain_pairs
    where truth_source = p_truth and lead_hours >= 24 and lead_hours <= p_lead_max and fc_mm is not null
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
    group by model),
  m as (
    select e.model, e.n, e.temp_mae, e.rh_mae, e.wind_mae, r.rain_csi, r.brier
    from e left join r using (model)),
  ranked as (
    select m.*,
           case when temp_mae is not null then rank() over (order by temp_mae asc nulls last) end as r1,
           case when rh_mae   is not null then rank() over (order by rh_mae   asc nulls last) end as r2,
           case when wind_mae is not null then rank() over (order by wind_mae asc nulls last) end as r3,
           case when rain_csi is not null then rank() over (order by rain_csi desc nulls last) end as r4,
           case when brier    is not null then rank() over (order by brier    asc nulls last) end as r5
    from m)
  select model, n::int, temp_mae::real, rh_mae::real, wind_mae::real, rain_csi::real, brier::real,
         (select case when count(x) >= 2 then avg(x) end from unnest(array[r1, r2, r3, r4, r5]) x)::real
  from ranked order by 8 nulls last, model $$;

-- Overview KPI row. Temperature and rain use day-1 forecasts, the shortest lead in the report window.
-- Brier needs rain probability, which only live snapshots have, so it's null until those are verified.
create or replace function rpc_kpis(p_from timestamptz, p_to timestamptz)
returns jsonb
language sql stable security invoker set search_path = public as $$
  with lb as materialized (select * from rpc_leaderboard(p_from, p_to)),
  temp as (
    select count(*) as n, avg(abs(error)) as mae, avg(error) as bias
    from v_pairs
    where truth_source = 'openmeteo_current' and model = 'best_match'
      and variable = 'temperature_c' and lead_hours >= 24 and lead_hours < 48
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')),
  rp as (
    select lead_hours, fc_mm, fc_prob_pct, obs_rain
    from v_rain_pairs
    where truth_source = 'openmeteo_current' and model = 'best_match' and lead_hours < 48
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')),
  rain as (
    select count(*) filter (where fc_mm >= 0.1 and obs_rain)     as a,
           count(*) filter (where fc_mm >= 0.1 and not obs_rain) as b,
           count(*) filter (where fc_mm <  0.1 and obs_rain)     as c,
           count(*) as n
    from rp where lead_hours >= 24 and fc_mm is not null),
  brier as (
    select count(*) as n, avg(power(fc_prob_pct / 100.0 - obs_rain::int, 2)) as brier,
           avg(obs_rain::int) as base_rate
    from rp where lead_hours <= 24 and fc_prob_pct is not null)
  select jsonb_build_object(
    'collection', (select jsonb_build_object(
        'streak_hours', w.streak_hours, 'meets_3_days', w.meets_3_days, 'live_since', w.live_since,
        'uptime_pct', (select round((100.0 * sum(u.success_runs + u.partial_runs) / nullif(sum(u.expected_runs), 0))::numeric, 1)
                       from rpc_uptime_daily(p_from, p_to) u where u.job = 'observe'))
      from (select null) dummy left join v_collection_window w on true),
    'temperature', (select jsonb_build_object('model', 'best_match', 'lead_bucket', '024-048',
                                              'mae', mae, 'bias', bias, 'n', n) from temp where n > 0),
    'rain', (select jsonb_build_object('model', 'best_match', 'lead_bucket', '024-048',
                                       'csi', a::float8 / nullif(a + b + c, 0), 'pod', a::float8 / nullif(a + c, 0),
                                       'far', b::float8 / nullif(a + b, 0), 'n', n) from rain where n > 0),
    'brier', (select jsonb_build_object('model', 'best_match', 'brier', brier,
                                        'bss', 1 - brier / nullif(base_rate * (1 - base_rate), 0), 'n', n)
              from brier where n > 0),
    'best_model', jsonb_build_object(
        'temperature', (select model from lb where n >= 20 and temp_mae is not null order by temp_mae limit 1),
        'rain', (select model from lb where n >= 20 and rain_csi is not null order by rain_csi desc limit 1)),
    'last_obs_at', (select max(observed_at) from observations where source = 'openmeteo_current'))
$$;
