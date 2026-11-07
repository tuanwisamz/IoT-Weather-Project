// ML3: 0008_ml_live.sql. New ML variables, the report-version pin, and the score/retrain run log.
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { freshDb, asAnon } from './db.mjs';

const FROM = '2026-11-03T16:00:00Z';         // Wed 4 Nov 00:00 MYT
const TO = '2026-11-03T20:00:00Z';
const HOURS = ['2026-11-03T16:00:00Z', '2026-11-03T17:00:00Z', '2026-11-03T18:00:00Z', '2026-11-03T19:00:00Z'];
const hours = `unnest(array['${HOURS.join("','")}']::timestamptz[])`;

let db;
before(async () => {
  db = await freshDb();
  // Observed: 30 °C, 80 %, 10 km/h, 1010 hPa every hour; only the first hour rains.
  await db.exec(`
    insert into observations (location_id, source, observed_at, temperature_c, humidity_pct, wind_speed_kmh,
                              pressure_hpa, precipitation_mm, is_backfill)
    select 1, 'openmeteo_current', t - make_interval(mins => 15 * k), 30, 80, 10, 1010,
           case when t = '${HOURS[0]}' then 0.1 else 0 end, true
    from ${hours} t, generate_series(0, 3) k;
    insert into forecasts (location_id, model, origin, issued_at, target_time, temperature_c, humidity_pct,
                           wind_speed_kmh, pressure_hpa, precipitation_mm)
    select 1, 'best_match', 'previous_runs', t - interval '1 day', t, 31, 84, 12, 1011, 0 from ${hours} t;
    insert into ml_models (id, name, version, algorithm, features, is_active, is_report, trained_at) values
      (60, 'bias_temperature', 'v1.0', 'lightgbm', array['x'], false, true,  '2026-11-07'),
      (61, 'bias_temperature', 'v1.1', 'lightgbm', array['x'], true,  false, '2026-11-08'),
      (62, 'bias_pressure',    'v1.0', 'lightgbm', array['x'], true,  true,  '2026-11-08'),
      (63, 'rain_occurrence',  'v1.0', 'lightgbm', array['x'], true,  true,  '2026-11-08');`);
  const pred = (model, variable, value) => `
    insert into predictions (location_id, model_id, issued_at, target_time, variable, value, base_model, lead_hours)
    select 1, ${model}, t - interval '1 day', t, '${variable}', ${value}, 'best_match', 24 from ${hours} t;`;
  await db.exec([
    pred(60, 'temperature_c', 30),             // the report version: perfect
    pred(61, 'temperature_c', 35),             // a newer version for the same hours: 5 °C off
    pred(62, 'pressure_hpa', 1010.5),
    // Rain: a 90 % chance and "yes" for the rainy hour, 20 % and "no" for the rest.
    `insert into predictions (location_id, model_id, issued_at, target_time, variable, value, base_model, lead_hours)
     select 1, 63, t - interval '1 day', t, v.variable,
            case when t = '${HOURS[0]}' then v.wet else v.dry end, 'best_match', 24
     from ${hours} t, (values ('rain_prob', 0.9, 0.2), ('rain_yes', 1, 0)) v(variable, wet, dry);`,
  ].join(''));
});

const rpc = async (call) => (await asAnon(db, () => db.query(`select * from ${call}`))).rows;
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-4, `${a} ≠ ${b}`);

test('the report version wins over a newer version for the same forecast hour', async () => {
  const ml = (await rpc(`rpc_leaderboard('${FROM}', '${TO}')`)).find((r) => r.model === 'best_match+ml');
  assert.equal(ml.temp_mae, 0);
  assert.equal(ml.n, 4);
});

test('a forecast hour scored only by the newer version shows it', async () => {
  await db.exec(`
    insert into predictions (location_id, model_id, issued_at, target_time, variable, value, base_model, lead_hours)
    values (1, 61, '2026-11-08T00:00:00Z', '2026-11-08T06:00:00Z', 'temperature_c', 33.5, 'best_match', 6);`);
  const { rows } = await db.query(`select temperature_c from v_forecasts_all
                                   where model = 'best_match+ml' and target_time = '2026-11-08T06:00:00Z'`);
  assert.equal(rows[0].temperature_c, 33.5);
});

test('pressure is on the leaderboard for raw and ML models', async () => {
  const rows = await rpc(`rpc_leaderboard('${FROM}', '${TO}')`);
  assert.equal(rows.find((r) => r.model === 'best_match').pres_mae, 1);
  close(rows.find((r) => r.model === 'best_match+ml').pres_mae, 0.5);
});

test('ML rain is scored from its yes/no and its probability gives a Brier score', async () => {
  const ml = (await rpc(`rpc_leaderboard('${FROM}', '${TO}')`)).find((r) => r.model === 'best_match+ml');
  assert.equal(ml.rain_csi, 1);
  close(ml.brier, (0.1 ** 2 + 3 * 0.2 ** 2) / 4);
  assert.notEqual(ml.rank_overall, null);
});

test('ML rows carry no rain amount, so they stay out of millimetre errors', async () => {
  const { rows } = await db.query(`select count(*)::int as n from v_pairs
                                   where model = 'best_match+ml' and variable = 'precipitation_mm'`);
  assert.equal(rows[0].n, 0);
});

test('the run log accepts the score and retrain jobs', async () => {
  await db.exec(`insert into ingestion_runs (job, trigger) values ('score', 'schedule'), ('retrain', 'dispatch');`);
  await assert.rejects(db.exec(`insert into ingestion_runs (job) values ('nope');`));
});
