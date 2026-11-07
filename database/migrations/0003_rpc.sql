-- 0003_rpc.sql: RPC functions for the dashboard (api-spec §3.3), plus the helpers they share.
-- Every function: language sql stable security invoker set search_path = public.
-- Ranges: p_from inclusive, p_to exclusive, clamped to 31 days.

-- Rain hours: forecast mm / probability vs observed rain_hour, for any truth source that has one
-- (METAR has rain flags but no millimetres, so this can't come from v_pairs).
create view v_rain_pairs with (security_invoker = true) as
select f.location_id, f.model, f.origin, f.issued_at, f.target_time, f.lead_hours,
       lead_bucket(f.lead_hours) as lead_bucket, a.source as truth_source,
       f.precipitation_mm as fc_mm, f.precip_probability_pct as fc_prob_pct, a.rain_hour as obs_rain
from v_forecasts_all f
join v_actual_hourly a on a.location_id = f.location_id and a.hour = f.target_time
where a.rain_hour is not null
  and (a.source <> 'openmeteo_current' or a.samples = 4);

-- The scheduled slot a run belongs to: observe HH:M7, forecast HH:17, backfill 19:40 UTC.
create function iww_nominal_slot(p_job text, p_ts timestamptz) returns timestamptz
language sql immutable set search_path = public as $$
  select to_timestamp(floor((extract(epoch from p_ts) - o.off) / o.period) * o.period + o.off)
  from (select case p_job when 'observe' then 600 when 'forecast' then 3600 else 86400 end as period,
               case p_job when 'observe' then 420 when 'forecast' then 1020 else 70800 end as off) o $$;

-- Main time series: for each target hour, the freshest forecast that was at least p_lead_min hours old.
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

create function rpc_metrics_by_lead(p_from timestamptz, p_to timestamptz,
    p_truth text default 'openmeteo_current', p_origin text default 'snapshot')
returns table (model text, variable text, lead_bucket text, n int, bias real, mae real, rmse real, r real)
language sql stable security invoker set search_path = public as $$
  select model, variable, lead_bucket, count(*)::int,
         avg(error)::real, avg(abs(error))::real, sqrt(avg(error * error))::real,
         case when count(*) >= 3 then corr(forecast, actual)::real end
  from v_pairs
  where truth_source = p_truth and origin = p_origin
    and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
  group by model, variable, lead_bucket
  order by model, variable, lead_bucket $$;

create function rpc_rain_contingency(p_from timestamptz, p_to timestamptz,
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
    where truth_source = p_truth and origin = 'snapshot' and fc_mm is not null
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

create function rpc_brier(p_from timestamptz, p_to timestamptz, p_truth text default 'openmeteo_current')
returns table (model text, lead_bucket text, n int, brier real, base_rate real, brier_clim real, bss real)
language sql stable security invoker set search_path = public as $$
  with s as (
    select model, lead_bucket, count(*) as n,
           avg(power(fc_prob_pct / 100.0 - obs_rain::int, 2)) as brier,
           avg(obs_rain::int) as base_rate
    from v_rain_pairs
    where truth_source = p_truth and origin = 'snapshot' and fc_prob_pct is not null
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
    group by model, lead_bucket)
  select model, lead_bucket, n::int, brier::real, base_rate::real, (base_rate * (1 - base_rate))::real,
         (1 - brier / nullif(base_rate * (1 - base_rate), 0))::real
  from s order by model, lead_bucket $$;

-- Ten probability bins [0,10) … [90,100] in percent; empty bins are returned with n = 0.
create function rpc_reliability(p_from timestamptz, p_to timestamptz, p_model text default 'best_match',
    p_lead_max int default 24, p_truth text default 'openmeteo_current')
returns table (bin_lower int, bin_upper int, n int, mean_forecast real, observed_freq real)
language sql stable security invoker set search_path = public as $$
  with p as (
    select least(floor(fc_prob_pct / 10), 9)::int as bin, fc_prob_pct / 100.0 as prob, obs_rain::int as o
    from v_rain_pairs
    where truth_source = p_truth and origin = 'snapshot' and model = p_model and lead_hours <= p_lead_max
      and fc_prob_pct is not null
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days'))
  select b * 10, b * 10 + 10, count(p.bin)::int, avg(p.prob)::real, avg(p.o)::real
  from generate_series(0, 9) b left join p on p.bin = b
  group by b order by b $$;

create function rpc_leaderboard(p_from timestamptz, p_to timestamptz, p_lead_max int default 72,
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
    where truth_source = p_truth and origin = 'snapshot' and lead_hours <= p_lead_max
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')
    group by model),
  r as (
    select model,
           count(*) filter (where fc_mm >= 0.1 and obs_rain)::float8
             / nullif(count(*) filter (where fc_mm >= 0.1 or obs_rain), 0)        as rain_csi,
           avg(power(fc_prob_pct / 100.0 - obs_rain::int, 2))                    as brier
    from v_rain_pairs
    where truth_source = p_truth and origin = 'snapshot' and lead_hours <= p_lead_max and fc_mm is not null
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
         (select avg(x) from unnest(array[r1, r2, r3, r4, r5]) x)::real
  from ranked order by 8 nulls last, model $$;

-- The brief's next-day forecast: the EARLIEST daily snapshot issued p_lead_days before each local date,
-- against observed values from the local day's hours 01:00–24:00 ((H-1h, H] rule).
create function rpc_daily_pairs(p_from_date date, p_to_date date, p_model text default 'best_match',
    p_lead_days int default 1, p_truth text default 'openmeteo_current')
returns table (target_date date, temp_max_fc real, temp_max_obs real, temp_min_fc real, temp_min_obs real,
               rain_fc_mm real, rain_obs_mm real, rain_prob_max_fc real, rain_day_fc boolean,
               rain_day_obs boolean, hours_complete int)
language sql stable security invoker set search_path = public as $$
  with fc as (
    select distinct on (target_date) target_date, temp_max_c, temp_min_c, precipitation_sum_mm,
           precip_probability_max_pct
    from forecasts_daily
    where model = p_model and lead_days = p_lead_days
      and target_date >= p_from_date and target_date < least(p_to_date, p_from_date + 31)
    order by target_date, issued_at asc),
  obs as (
    select ((hour - interval '1 hour') at time zone 'Asia/Kuala_Lumpur')::date as local_date,
           count(*) as hours_complete,
           max(temperature_c) as tmax, min(temperature_c) as tmin, sum(precipitation_mm) as rain
    from v_actual_hourly
    where source = p_truth and (source <> 'openmeteo_current' or samples = 4)
      and hour >  (p_from_date::timestamp at time zone 'Asia/Kuala_Lumpur')
      and hour <= (least(p_to_date, p_from_date + 31)::timestamp at time zone 'Asia/Kuala_Lumpur')
    group by 1)
  select fc.target_date, fc.temp_max_c,
         case when o.hours_complete >= 22 then o.tmax end::real,
         fc.temp_min_c,
         case when o.hours_complete >= 22 then o.tmin end::real,
         fc.precipitation_sum_mm,
         case when o.hours_complete >= 22 then o.rain end::real,
         fc.precip_probability_max_pct,
         fc.precipitation_sum_mm >= 1.0,
         case when o.hours_complete >= 22 then o.rain >= 1.0 end,
         coalesce(o.hours_complete, 0)::int
  from fc left join obs o on o.local_date = fc.target_date
  order by fc.target_date $$;

-- Overview strip: the newest best_match snapshot (+ its ML-corrected twin) for the next 24 hours.
create function rpc_next_24h()
returns table (target_time timestamptz, temperature_c real, temperature_c_ml real, precipitation_mm real,
               precip_probability_pct real, weather_code smallint, wind_speed_kmh real)
language sql stable security invoker set search_path = public as $$
  with latest as (select max(issued_at) as issued_at from forecasts where model = 'best_match' and origin = 'snapshot')
  select f.target_time, f.temperature_c, ml.temperature_c, f.precipitation_mm, f.precip_probability_pct,
         f.weather_code, f.wind_speed_kmh
  from forecasts f
  join latest l on f.issued_at = l.issued_at
  left join v_forecasts_all ml on ml.model = 'best_match+ml' and ml.issued_at = f.issued_at
                               and ml.target_time = f.target_time
  where f.model = 'best_match' and f.origin = 'snapshot'
    and f.target_time >  date_trunc('hour', now(), 'UTC')
    and f.target_time <= date_trunc('hour', now(), 'UTC') + interval '24 hours'
  order by f.target_time $$;

-- Daily uptime per job. Only scheduled runs count. Expected runs are the nominal slots inside
-- [first run of the job, now − 15 min) for that local day, so a job's first day and today are prorated.
-- A run still 'running' after 30 min was killed (timeout) and counts as failed.
create function rpc_uptime_daily(p_from timestamptz, p_to timestamptz)
returns table (local_date date, job text, expected_runs int, success_runs int, partial_runs int,
               failed_runs int, missing_runs int, uptime_pct real, median_start_delay_s real)
language sql stable security invoker set search_path = public as $$
  with jobs as (
    select job, case job when 'observe' then 600 when 'forecast' then 3600 else 86400 end as period,
           case job when 'observe' then 420 when 'forecast' then 1020 else 70800 end as off,
           min(iww_nominal_slot(job, started_at)) as first_slot
    from ingestion_runs where trigger = 'schedule' and job in ('observe', 'forecast', 'backfill')
    group by job),
  days as (
    select d::date as local_date,
           d::timestamp at time zone 'Asia/Kuala_Lumpur' as day_start,
           (d::date + 1)::timestamp at time zone 'Asia/Kuala_Lumpur' as day_end
    from generate_series((p_from at time zone 'Asia/Kuala_Lumpur')::date,
                         (least(p_to, p_from + interval '31 days', now()) at time zone 'Asia/Kuala_Lumpur')::date,
                         interval '1 day') d),
  win as (
    select d.local_date, j.job, j.period, j.off,
           extract(epoch from greatest(d.day_start, j.first_slot, p_from)) as s,
           extract(epoch from least(d.day_end, p_to, now() - interval '15 minutes')) as e
    from days d cross join jobs j),
  expected as (
    select local_date, job,
           greatest(0, case when e <= s then 0
                            else floor((e - off - 1) / period) - ceil((s - off) / period) + 1 end)::int as n
    from win),
  runs as (
    select (iww_nominal_slot(job, started_at) at time zone 'Asia/Kuala_Lumpur')::date as local_date, job,
           count(*) filter (where status = 'success')                                            as success,
           count(*) filter (where status = 'partial')                                            as partial,
           count(*) filter (where status = 'failed'
                              or (status = 'running' and started_at < now() - interval '30 minutes')) as failed,
           percentile_cont(0.5) within group
             (order by extract(epoch from started_at - iww_nominal_slot(job, started_at)))        as delay
    from ingestion_runs
    where trigger = 'schedule' and started_at >= p_from - interval '1 day' and started_at < p_to
    group by 1, 2)
  select x.local_date, x.job, x.n, coalesce(r.success, 0)::int, coalesce(r.partial, 0)::int,
         coalesce(r.failed, 0)::int,
         greatest(x.n - coalesce(r.success + r.partial + r.failed, 0), 0)::int,
         least(100, 100.0 * coalesce(r.success + r.partial, 0) / nullif(x.n, 0))::real,
         r.delay::real
  from expected x left join runs r using (local_date, job)
  where x.n > 0 or r.job is not null
  order by x.local_date, x.job $$;

create function rpc_runs_timeline(p_from timestamptz, p_to timestamptz, p_job text default null)
returns table (id bigint, job text, status text, started_at timestamptz, finished_at timestamptz,
               duration_s real, start_delay_s real, rows_written jsonb, failed_steps text[])
language sql stable security invoker set search_path = public as $$
  select r.id, r.job, r.status, r.started_at, r.finished_at,
         extract(epoch from r.finished_at - r.started_at)::real,
         case when r.trigger = 'schedule' and r.job <> 'manual'
              then extract(epoch from r.started_at - iww_nominal_slot(r.job, r.started_at))::real end,
         r.rows_written,
         array(select s ->> 'step' from jsonb_array_elements(r.steps) s where not (s ->> 'ok')::boolean)
  from ingestion_runs r
  where r.started_at >= p_from and r.started_at < least(p_to, p_from + interval '31 days')
    and (p_job is null or r.job = p_job)
  order by r.started_at desc
  limit 1000 $$;

-- Overview KPI row: one JSON document (api-spec §3.3). best_model needs n ≥ 20 to be named.
-- Each section queries only the rows it needs; the leaderboard is computed once.
create function rpc_kpis(p_from timestamptz, p_to timestamptz)
returns jsonb
language sql stable security invoker set search_path = public as $$
  with lb as materialized (select * from rpc_leaderboard(p_from, p_to)),
  temp as (
    select count(*) as n, avg(abs(error)) as mae, avg(error) as bias
    from v_pairs
    where truth_source = 'openmeteo_current' and origin = 'snapshot' and model = 'best_match'
      and variable = 'temperature_c' and lead_hours >= 12 and lead_hours < 24
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')),
  rp as (
    select lead_hours, fc_mm, fc_prob_pct, obs_rain
    from v_rain_pairs
    where truth_source = 'openmeteo_current' and origin = 'snapshot' and model = 'best_match'
      and lead_hours <= 24          -- Brier uses leads 0–24 h
      and target_time >= p_from and target_time < least(p_to, p_from + interval '31 days')),
  rain as (
    select count(*) filter (where fc_mm >= 0.1 and obs_rain)     as a,
           count(*) filter (where fc_mm >= 0.1 and not obs_rain) as b,
           count(*) filter (where fc_mm <  0.1 and obs_rain)     as c,
           count(*) as n
    from rp where lead_hours < 6 and fc_mm is not null),
  brier as (
    select count(*) as n, avg(power(fc_prob_pct / 100.0 - obs_rain::int, 2)) as brier,
           avg(obs_rain::int) as base_rate
    from rp where fc_prob_pct is not null)
  select jsonb_build_object(
    'collection', (select jsonb_build_object(
        'streak_hours', w.streak_hours, 'meets_3_days', w.meets_3_days,
        'uptime_pct', (select round((100.0 * sum(u.success_runs + u.partial_runs) / nullif(sum(u.expected_runs), 0))::numeric, 1)
                       from rpc_uptime_daily(p_from, p_to) u where u.job = 'observe'))
      from (select null) dummy left join v_collection_window w on true),
    'temperature', (select jsonb_build_object('model', 'best_match', 'lead_bucket', '012-024',
                                              'mae', mae, 'bias', bias, 'n', n) from temp where n > 0),
    'rain', (select jsonb_build_object('model', 'best_match', 'lead_bucket', '000-006',
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

-- 0004_rls.sql may already have run on the live database, so this file grants its own objects.
grant select on v_rain_pairs to anon, authenticated;
grant execute on function
  iww_nominal_slot(text, timestamptz),
  rpc_forecast_vs_actual(text, text, int, timestamptz, timestamptz, text),
  rpc_metrics_by_lead(timestamptz, timestamptz, text, text),
  rpc_rain_contingency(timestamptz, timestamptz, text, real),
  rpc_brier(timestamptz, timestamptz, text),
  rpc_reliability(timestamptz, timestamptz, text, int, text),
  rpc_leaderboard(timestamptz, timestamptz, int, text),
  rpc_daily_pairs(date, date, text, int, text),
  rpc_next_24h(),
  rpc_uptime_daily(timestamptz, timestamptz),
  rpc_runs_timeline(timestamptz, timestamptz, text),
  rpc_kpis(timestamptz, timestamptz)
to anon, authenticated;
