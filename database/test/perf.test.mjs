// Rough proxy for V6 (every RPC < 1 s as anon): 7 days at production volume, timed in PGlite.
// PGlite (WASM, single-threaded) is slower than Supabase, so passing here leaves headroom.
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { freshDb, asAnon } from './db.mjs';

const BUDGET_MS = 1000;
const FROM = "now() - interval '7 days'";
const TO = 'now()';
let db;

before(async () => {
  db = await freshDb();
  await db.exec(`
    -- 15-min analysis + hourly METAR for 7 days
    insert into observations (location_id, source, observed_at, temperature_c, humidity_pct, wind_speed_kmh, pressure_hpa, precipitation_mm)
    select 1, 'openmeteo_current', date_trunc('hour', now()) - make_interval(mins => 15 * k),
           27 + 4 * sin(k / 15.0), 80, 6, 1010, case when k % 37 < 3 then 0.4 else 0 end
    from generate_series(0, 96 * 7) k;
    insert into observations (location_id, source, observed_at, temperature_c, is_raining)
    select 1, 'metar_wmki', date_trunc('hour', now()) - make_interval(hours => k), 27, k % 9 = 0
    from generate_series(0, 24 * 7) k;
    -- best_match every hour × 168 h, and three 6-hourly models × 168 h (≈ 42k rows)
    insert into forecasts (location_id, model, issued_at, target_time, temperature_c, humidity_pct, wind_speed_kmh,
                           pressure_hpa, precipitation_mm, precip_probability_pct)
    select 1, m.model, i.issued, i.issued + make_interval(hours => h), 28, 78, 7, 1009,
           case when h % 11 = 0 then 0.5 else 0 end, (h * 7) % 100
    from (values ('best_match', 1), ('ecmwf_ifs025', 6), ('gfs_seamless', 6), ('icon_seamless', 6)) m(model, step)
    cross join lateral (select date_trunc('hour', now()) - make_interval(hours => k) as issued
                        from generate_series(0, 24 * 7, m.step) k) i
    cross join generate_series(0, 167) h;
    insert into ingestion_runs (job, trigger, started_at, finished_at, status)
    select 'observe', 'schedule', now() - make_interval(mins => 10 * k), now() - make_interval(mins => 10 * k) + interval '1 minute', 'success'
    from generate_series(0, 144 * 7) k;
    analyze;`);
});

const CALLS = {
  rpc_forecast_vs_actual: `rpc_forecast_vs_actual('best_match', 'temperature_c', 24, ${FROM}, ${TO})`,
  rpc_metrics_by_lead: `rpc_metrics_by_lead(${FROM}, ${TO})`,
  rpc_rain_contingency: `rpc_rain_contingency(${FROM}, ${TO})`,
  rpc_brier: `rpc_brier(${FROM}, ${TO})`,
  rpc_reliability: `rpc_reliability(${FROM}, ${TO})`,
  rpc_leaderboard: `rpc_leaderboard(${FROM}, ${TO})`,
  rpc_daily_pairs: `rpc_daily_pairs((now() - interval '7 days')::date, now()::date)`,
  rpc_next_24h: `rpc_next_24h()`,
  rpc_uptime_daily: `rpc_uptime_daily(${FROM}, ${TO})`,
  rpc_runs_timeline: `rpc_runs_timeline(${FROM}, ${TO})`,
  rpc_kpis: `rpc_kpis(${FROM}, ${TO})`,
  v_rain_status: 'v_rain_status',
  v_collection_window: 'v_collection_window',
  v_coverage_daily: 'v_coverage_daily',
};

for (const [name, call] of Object.entries(CALLS)) {
  test(`${name} < ${BUDGET_MS} ms on 7 days of data`, async () => {
    await asAnon(db, async () => {
      await db.query(`select * from ${call}`);                 // warm-up (plans, caches)
      const t0 = performance.now();
      await db.query(`select * from ${call}`);
      const ms = performance.now() - t0;
      console.log(`  ${name.padEnd(24)} ${ms.toFixed(0).padStart(5)} ms`);
      assert.ok(ms < BUDGET_MS, `${name} took ${ms.toFixed(0)} ms`);
    });
  });
}
