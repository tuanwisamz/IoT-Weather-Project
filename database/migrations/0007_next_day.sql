-- 0007_next_day.sql: the brief's next-day forecast, for data with no daily archive.
-- rpc_daily_pairs reads forecasts_daily, which Previous Runs can't fill, so this builds the same table
-- from hourly forecasts at a lead of exactly N days. A local day covers hours 01:00–24:00 ((H-1h, H] rule).
-- Values are null unless at least 22 of the day's hours are present, as in rpc_daily_pairs.
create function rpc_next_day(p_from_date date, p_to_date date, p_model text default 'best_match',
    p_lead_days int default 1, p_truth text default 'openmeteo_current')
returns table (target_date date, temp_max_fc real, temp_max_obs real, temp_min_fc real, temp_min_obs real,
               rain_fc_mm real, rain_obs_mm real, rain_day_fc boolean, rain_day_obs boolean,
               hours_fc int, hours_complete int)
language sql stable security invoker set search_path = public as $$
  with bounds as (
    select p_from_date::timestamp at time zone 'Asia/Kuala_Lumpur' as s,
           least(p_to_date, p_from_date + 31)::timestamp at time zone 'Asia/Kuala_Lumpur' as e),
  fc as (
    select ((f.target_time - interval '1 hour') at time zone 'Asia/Kuala_Lumpur')::date as local_date,
           count(*) as hours, max(f.temperature_c) as tmax, min(f.temperature_c) as tmin,
           sum(f.precipitation_mm) as rain
    from v_forecasts_all f, bounds b
    where f.model = p_model and f.lead_hours = 24 * p_lead_days
      and f.target_time > b.s and f.target_time <= b.e
    group by 1),
  obs as (
    select ((h.hour - interval '1 hour') at time zone 'Asia/Kuala_Lumpur')::date as local_date,
           count(*) as hours, max(h.temperature_c) as tmax, min(h.temperature_c) as tmin,
           sum(h.precipitation_mm) as rain
    from v_actual_hourly h, bounds b
    where h.source = p_truth and (h.source <> 'openmeteo_current' or h.samples = 4)
      and h.hour > b.s and h.hour <= b.e
    group by 1)
  select fc.local_date,
         case when fc.hours >= 22 then fc.tmax end::real,
         case when o.hours >= 22 then o.tmax end::real,
         case when fc.hours >= 22 then fc.tmin end::real,
         case when o.hours >= 22 then o.tmin end::real,
         case when fc.hours >= 22 then fc.rain end::real,
         case when o.hours >= 22 then o.rain end::real,
         case when fc.hours >= 22 then fc.rain >= 1.0 end,
         case when o.hours >= 22 then o.rain >= 1.0 end,
         fc.hours::int, coalesce(o.hours, 0)::int
  from fc left join obs o using (local_date)
  order by fc.local_date $$;

grant execute on function rpc_next_day(date, date, text, int, text) to anon, authenticated;
