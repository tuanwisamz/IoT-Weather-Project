-- 0008: more correction models, live scoring and monthly retraining (Implementation-plan §5.8).
-- Applied after 0007. Earlier files are frozen, so the views and functions they own are replaced here.

-- The live scorer and the monthly retrain log their runs like every other job.
alter table ingestion_runs drop constraint ingestion_runs_job_check;
alter table ingestion_runs add constraint ingestion_runs_job_check
  check (job in ('observe', 'forecast', 'backfill', 'manual', 'score', 'retrain'));

-- `artifact` holds the LightGBM model text, so the live scorer and the retrain never need the repo.
-- `is_report` marks the versions whose predictions are the report's 4–7 Nov figures; they always win
-- over a newer version for the same forecast hour, so activating v1.1 can't change the report.
alter table ml_models add column artifact text;
alter table ml_models add column is_report boolean not null default false;
update ml_models set is_report = true where name = 'bias_temperature' and version = 'v1.0';

-- Raw forecasts + the ML-corrected pseudo-model, one shape. `rain_yes` is new and only set for ML rows.
-- One prediction per forecast hour and variable: a report version first, then the newest version.
-- The ML model forecasts rain as yes/no, not millimetres, so its precipitation_mm stays null.
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
from (
  select p.*, row_number() over (
           partition by p.location_id, p.base_model, p.variable, p.issued_at, p.target_time
           order by m.is_report desc, m.trained_at desc, m.id desc) as pick
  from predictions p
  join ml_models m on m.id = p.model_id
  where m.name like 'bias\_%' or m.name = 'rain_occurrence'
) p
where p.pick = 1
group by p.location_id, p.base_model, p.issued_at, p.target_time, p.lead_hours;

-- Rain pairs: an ML yes/no counts as a forecast of 0.1 mm or 0 mm, so the CSI and contingency at the
-- default 0.1 mm threshold score it as its own yes/no. Higher thresholds aren't meaningful for ML rows.
create or replace view v_rain_pairs with (security_invoker = true) as
select f.location_id, f.model, f.origin, f.issued_at, f.target_time, f.lead_hours,
       lead_bucket(f.lead_hours) as lead_bucket, a.source as truth_source,
       case when f.rain_yes is null then f.precipitation_mm
            when f.rain_yes then 0.1::real else 0::real end as fc_mm,
       f.precip_probability_pct as fc_prob_pct, a.rain_hour as obs_rain
from v_forecasts_all f
join v_actual_hourly a on a.location_id = f.location_id and a.hour = f.target_time
where a.rain_hour is not null
  and (a.source <> 'openmeteo_current' or a.samples = 4);

-- Leaderboard: adds pressure, which every model has, and ranks on it too.
drop function rpc_leaderboard(timestamptz, timestamptz, int, text);
create function rpc_leaderboard(p_from timestamptz, p_to timestamptz, p_lead_max int default 144,
    p_truth text default 'openmeteo_current')
returns table (model text, n int, temp_mae real, rh_mae real, wind_mae real, pres_mae real, rain_csi real,
               brier real, rank_overall real)
language sql stable security invoker set search_path = public as $$
  with e as (
    select model,
           count(*) filter (where variable = 'temperature_c')                    as n,
           avg(abs(error)) filter (where variable = 'temperature_c')             as temp_mae,
           avg(abs(error)) filter (where variable = 'humidity_pct')              as rh_mae,
           avg(abs(error)) filter (where variable = 'wind_speed_kmh')            as wind_mae,
           avg(abs(error)) filter (where variable = 'pressure_hpa')              as pres_mae
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
    select e.model, e.n, e.temp_mae, e.rh_mae, e.wind_mae, e.pres_mae, r.rain_csi, r.brier
    from e left join r using (model)),
  ranked as (
    select m.*,
           case when temp_mae is not null then rank() over (order by temp_mae asc nulls last) end as r1,
           case when rh_mae   is not null then rank() over (order by rh_mae   asc nulls last) end as r2,
           case when wind_mae is not null then rank() over (order by wind_mae asc nulls last) end as r3,
           case when rain_csi is not null then rank() over (order by rain_csi desc nulls last) end as r4,
           case when brier    is not null then rank() over (order by brier    asc nulls last) end as r5,
           case when pres_mae is not null then rank() over (order by pres_mae asc nulls last) end as r6
    from m)
  select model, n::int, temp_mae::real, rh_mae::real, wind_mae::real, pres_mae::real, rain_csi::real, brier::real,
         (select case when count(x) >= 2 then avg(x) end from unnest(array[r1, r2, r3, r4, r5, r6]) x)::real
  from ranked order by 9 nulls last, model $$;

grant execute on function rpc_leaderboard(timestamptz, timestamptz, int, text) to anon, authenticated;
