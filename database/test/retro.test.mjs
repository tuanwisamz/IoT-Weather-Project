// T3.4′: 0006_retro_window.sql against a small retrieved window, with no live snapshots in it.
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { freshDb, asAnon } from './db.mjs';

const FROM = '2026-11-03T16:00:00Z';         // Wed 4 Nov 00:00 MYT
const TO = '2026-11-03T20:00:00Z';
const HOURS = ['2026-11-03T16:00:00Z', '2026-11-03T17:00:00Z', '2026-11-03T18:00:00Z', '2026-11-03T19:00:00Z'];

const hour = (iso, temp, mm, backfill = true) => `
  insert into observations (location_id, source, observed_at, temperature_c, humidity_pct, wind_speed_kmh,
                            precipitation_mm, is_backfill)
  select 1, 'openmeteo_current', timestamptz '${iso}' - make_interval(mins => 15 * k), ${temp}, 80, 10, ${mm}, ${backfill}
  from generate_series(0, 3) k;`;

const retrieved = (model, n, iso, temp, mm) => `
  insert into forecasts (location_id, model, origin, issued_at, target_time, temperature_c, humidity_pct,
                         wind_speed_kmh, precipitation_mm)
  values (1, '${model}', 'previous_runs', timestamptz '${iso}' - interval '${n} days', '${iso}', ${temp}, 82, 12, ${mm});`;

let db;
before(async () => {
  db = await freshDb();
  // Observed 30 °C every hour; the first hour rains (0.1 mm × 4 samples).
  await db.exec(HOURS.map((h, i) => hour(h, 30, i === 0 ? 0.1 : 0)).join(''));
  // best_match at day 1 is +1 °C and catches the rain; ICON at day 1 is +2 °C and misses it.
  // best_match also has day 7, which ICON doesn't, and it's deliberately terrible (+9 °C).
  await db.exec(HOURS.map((h, i) => retrieved('best_match', 1, h, 31, i === 0 ? 0.5 : 0)).join(''));
  await db.exec(HOURS.map((h) => retrieved('best_match', 7, h, 39, 0)).join(''));
  await db.exec(HOURS.map((h) => retrieved('icon_seamless', 1, h, 32, 0)).join(''));
});

const rpc = async (call) => (await asAnon(db, () => db.query(`select * from ${call}`))).rows;

test('accuracy RPCs read a window of retrieved forecasts only', async () => {
  const series = await rpc(`rpc_forecast_vs_actual('best_match', 'temperature_c', 24, '${FROM}', '${TO}')`);
  assert.equal(series.length, 4);
  assert.deepEqual([series[0].forecast, series[0].actual, series[0].lead_hours], [31, 30, 24]);

  const lead = await rpc(`rpc_metrics_by_lead('${FROM}', '${TO}') where model = 'best_match'
                          and variable = 'temperature_c' and lead_bucket = '024-048'`);
  assert.equal(lead[0].n, 4);
  assert.equal(lead[0].mae, 1);

  const rain = await rpc(`rpc_rain_contingency('${FROM}', '${TO}') where model = 'best_match'
                          and lead_bucket = '024-048'`);
  assert.deepEqual([rain[0].hits, rain[0].false_alarms, rain[0].misses, rain[0].correct_negatives], [1, 0, 0, 3]);
});

test('rpc_metrics_by_lead can still be limited to one origin', async () => {
  const snapshots = await rpc(`rpc_metrics_by_lead('${FROM}', '${TO}', 'openmeteo_current', 'snapshot')`);
  assert.equal(snapshots.length, 0);
});

test('leaderboard compares models at 24–144 h only, so day 7 can\'t hurt best_match', async () => {
  const rows = await rpc(`rpc_leaderboard('${FROM}', '${TO}')`);
  const best = rows.find((r) => r.model === 'best_match');
  assert.equal(best.n, 4);
  assert.equal(best.temp_mae, 1);
  assert.equal(rows.find((r) => r.model === 'icon_seamless').temp_mae, 2);
  assert.equal(rows[0].model, 'best_match');
});

test('a model scored on temperature alone gets no overall rank', async () => {
  await db.exec(`
    insert into ml_models (id, name, version, algorithm, features, is_active)
    values (50, 'bias_temperature', 'test', 'lightgbm', array['x'], true);
    insert into predictions (location_id, model_id, issued_at, target_time, variable, value, base_model, lead_hours)
    select 1, 50, t - interval '1 day', t, 'temperature_c', 30, 'best_match', 24
    from unnest(array['${HOURS.join("','")}']::timestamptz[]) t;`);
  const rows = await rpc(`rpc_leaderboard('${FROM}', '${TO}')`);
  const ml = rows.find((r) => r.model === 'best_match+ml');
  assert.equal(ml.temp_mae, 0);
  assert.equal(ml.rank_overall, null);
  await db.exec(`delete from predictions where model_id = 50; delete from ml_models where id = 50;`);
});

test('rpc_kpis uses day-1 leads and has no Brier without live rain probabilities', async () => {
  const [{ rpc_kpis: k }] = await rpc(`rpc_kpis('${FROM}', '${TO}')`);
  assert.equal(k.temperature.lead_bucket, '024-048');
  assert.equal(k.temperature.mae, 1);
  assert.equal(k.rain.lead_bucket, '024-048');
  assert.equal(k.rain.csi, 1);
  assert.equal(k.brier, null);
  assert.equal(k.best_model.temperature, null, 'n = 4 is below the 20 needed to name a best model');
});

test('live_since ignores retrieved rows', async () => {
  const before = (await asAnon(db, () => db.query('select * from v_collection_window'))).rows[0];
  assert.equal(before.live_since, null);
  assert.equal(before.backfilled_samples, 16);

  await db.exec(`insert into observations (location_id, source, observed_at, temperature_c, is_backfill) values
    (1, 'openmeteo_current', '2026-11-03T20:15:00Z', 30, false),
    (1, 'openmeteo_current', '2026-11-03T20:30:00Z', 30, true);`);
  const after = (await asAnon(db, () => db.query('select * from v_collection_window'))).rows[0];
  assert.equal(after.live_since.toISOString(), '2026-11-03T20:15:00.000Z');
  assert.equal(after.live_samples, 2);
  assert.equal(after.live_expected_samples, 2);
  await db.exec(`delete from observations where observed_at > '2026-11-03T20:00:00Z'`);
});

test('v_coverage_daily starts at the retrieved data and marks it as backfilled', async () => {
  const rows = (await asAnon(db, () => db.query(`select * from v_coverage_daily where local_date = '2026-11-04'`))).rows;
  const om = rows.find((r) => r.stream === 'openmeteo_current');
  const fc = rows.find((r) => r.stream === 'forecast_best_match');
  assert.equal(om.received, 12);                         // 16 samples, minus the first hour's four
  assert.equal(om.backfilled, 12);
  assert.equal(fc.received, 4);
  assert.equal(fc.backfilled, 4);
  assert.deepEqual(rows.map((r) => r.stream).sort(), ['forecast_best_match', 'metar_wmki', 'openmeteo_current']);
});

test('v_rain_status maps the next hour\'s Open-Meteo probability to a level', async () => {
  const seed = (prob, issuedAgo) => db.exec(`
    delete from forecasts where origin = 'snapshot';
    insert into forecasts (location_id, model, issued_at, target_time, precip_probability_pct)
    select 1, 'best_match', date_trunc('hour', now(), 'UTC') - interval '${issuedAgo}',
           date_trunc('hour', now(), 'UTC') + make_interval(hours => k), ${prob} - 5 * (k - 1)
    from generate_series(1, 4) k;`);
  const level = async () => (await asAnon(db, () => db.query('select * from v_rain_status'))).rows[0];

  await seed(20, '0 hours');
  assert.equal((await level()).level, 'CLEAR');
  await seed(30, '0 hours');
  assert.equal((await level()).level, 'WATCH');
  await seed(60, '0 hours');
  const likely = await level();
  assert.equal(likely.level, 'RAIN_LIKELY');
  assert.equal(likely.model_version, 'open-meteo');
  assert.ok(Math.abs(likely.prob_1h - 0.6) < 1e-6);
  assert.ok(Math.abs(likely.prob_3h - 0.6) < 1e-6);
  await seed(60, '3 hours');
  assert.equal((await level()).level, 'UNKNOWN');
  await db.exec(`delete from forecasts where origin = 'snapshot'`);
});

test('anon can read the replaced views', async () => {
  for (const v of ['v_rain_status', 'v_collection_window', 'v_coverage_daily']) {
    await asAnon(db, () => db.query(`select * from ${v}`));
  }
});
