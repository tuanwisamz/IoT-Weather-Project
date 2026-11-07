// T3.1 / T3.3: the analytics views on small synthetic datasets with hand-computed answers.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { freshDb, asAnon } from './db.mjs';

// Four 15-min samples ending at `hourIso` (a complete hour), all with temperature `temp`.
const completeHour = (hourIso, temp, precip = 0) => `
  insert into observations (location_id, source, observed_at, temperature_c, precipitation_mm)
  select 1, 'openmeteo_current', timestamptz '${hourIso}' - make_interval(mins => 15 * k), ${temp}, ${precip}
  from generate_series(0, 3) k;`;

const forecast = (model, issued, target, temp) => `
  insert into forecasts (location_id, model, issued_at, target_time, temperature_c)
  values (1, '${model}', '${issued}', '${target}', ${temp});`;

test('lead_bucket edges', async () => {
  const db = await freshDb();
  const { rows } = await db.query(`select h, lead_bucket(h) as b from unnest(array[0,5,6,11,12,23,24,47,48,71,72,119,120,167]) h`);
  assert.deepEqual(rows.map((r) => r.b), ['000-006', '000-006', '006-012', '006-012', '012-024', '012-024', '024-048',
    '024-048', '048-072', '048-072', '072-120', '072-120', '120-168', '120-168']);
});

test('v_pairs keeps complete hours only and signs the error forecast − actual', async () => {
  const db = await freshDb();
  await db.exec(completeHour('2026-11-02T06:00:00Z', 30));
  // 07:00 has only 3 samples, so it must not be verified.
  await db.exec(`insert into observations (location_id, source, observed_at, temperature_c)
                 select 1, 'openmeteo_current', timestamptz '2026-11-02T07:00:00Z' - make_interval(mins => 15 * k), 31
                 from generate_series(0, 2) k;`);
  await db.exec(forecast('best_match', '2026-11-01T06:00:00Z', '2026-11-02T06:00:00Z', 32.5));
  await db.exec(forecast('best_match', '2026-11-01T06:00:00Z', '2026-11-02T07:00:00Z', 30));
  const { rows } = await db.query(`select target_time, lead_hours, lead_bucket, error from v_pairs
                                   where variable = 'temperature_c' and truth_source = 'openmeteo_current'`);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].target_time.toISOString(), '2026-11-02T06:00:00.000Z');
  assert.equal(rows[0].lead_hours, 24);
  assert.equal(rows[0].lead_bucket, '024-048');
  assert.ok(Math.abs(rows[0].error - 2.5) < 1e-6);
});

test('METAR hours pair without the 4-sample rule and give rain_hour from wxString', async () => {
  const db = await freshDb();
  await db.exec(`insert into observations (location_id, source, observed_at, temperature_c, is_raining) values
                 (1, 'metar_wmki', '2026-11-02T06:00:00Z', 29, true)`);
  await db.exec(forecast('best_match', '2026-11-02T00:00:00Z', '2026-11-02T06:00:00Z', 30));
  const { rows } = await db.query(`select a.rain_hour, p.error from v_actual_hourly a
      join v_pairs p on p.truth_source = a.source and p.target_time = a.hour
      where a.source = 'metar_wmki' and p.variable = 'temperature_c'`);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].rain_hour, true);
  assert.ok(Math.abs(rows[0].error - 1) < 1e-6);
});

test('v_now returns the newest row per source with an age', async () => {
  const db = await freshDb();
  await db.exec(`insert into observations (location_id, source, observed_at, temperature_c) values
    (1, 'openmeteo_current', now() - interval '20 minutes', 27),
    (1, 'openmeteo_current', now() - interval '5 minutes', 28),
    (1, 'metar_wmki', now() - interval '1 hour', 26)`);
  const { rows } = await db.query(`select source, temperature_c, age_s from v_now order by source`);
  assert.deepEqual(rows.map((r) => [r.source, r.temperature_c]), [['metar_wmki', 26], ['openmeteo_current', 28]]);
  assert.ok(rows[1].age_s >= 299 && rows[1].age_s < 320);
});

test('v_collection_window picks the longest streak; a gap > 1 h breaks it', async () => {
  const db = await freshDb();
  // Streak A: 2 h of samples. Gap of 2 h. Streak B: 5 h of samples (with one 45-min hole, still continuous).
  await db.exec(`insert into observations (location_id, source, observed_at)
    select 1, 'openmeteo_current', timestamptz '2026-11-01T00:00:00Z' + make_interval(mins => 15 * k) from generate_series(0, 8) k;
    insert into observations (location_id, source, observed_at)
    select 1, 'openmeteo_current', timestamptz '2026-11-01T04:00:00Z' + make_interval(mins => 15 * k)
    from generate_series(0, 20) k where k not in (5, 6);`);
  const { rows } = await db.query(`select * from v_collection_window`);
  assert.equal(rows[0].streak_start.toISOString(), '2026-11-01T04:00:00.000Z');
  assert.equal(rows[0].streak_hours, 5);
  assert.equal(rows[0].samples, 19);
  assert.equal(rows[0].expected_samples, 21);
  assert.equal(rows[0].meets_3_days, false);
  assert.equal(rows[0].first_obs_at.toISOString(), '2026-11-01T00:00:00.000Z');
});

test('v_rain_status smooths the last 3 slots and maps thresholds to levels', async () => {
  const db = await freshDb();
  const insert = (ago, p) => `insert into predictions (location_id, model_id, issued_at, target_time, variable, value)
    select 1, id, now() - interval '${ago} minutes', now() - interval '${ago} minutes' + interval '1 hour', 'rain_1h_prob', ${p}
    from ml_models where name = 'rain_nowcast' and is_active;`;
  await db.exec(insert(25, 0.1) + insert(15, 0.4) + insert(5, 0.7));
  let { rows } = await db.query(`select level, prob_1h, prob_1h_smoothed, model_version, watch_threshold from v_rain_status`);
  assert.equal(rows.length, 1);
  assert.ok(Math.abs(rows[0].prob_1h - 0.7) < 1e-6);
  assert.ok(Math.abs(rows[0].prob_1h_smoothed - 0.4) < 1e-6);       // (0.1 + 0.4 + 0.7) / 3
  assert.equal(rows[0].level, 'WATCH');
  assert.equal(rows[0].model_version, 'v0-rule');

  await db.exec(`update predictions set issued_at = issued_at - interval '1 hour'`);
  ({ rows } = await db.query(`select level from v_rain_status`));
  assert.equal(rows[0].level, 'UNKNOWN');
});

test('v_coverage_daily counts per stream and never exceeds 100 %', async () => {
  const db = await freshDb();
  // A full local (MYT) day three days ago: 96 samples from 00:15 to 24:00, one of them backfilled,
  // plus one sample on the next day so the first day isn't also the last.
  const day = `((now() at time zone 'Asia/Kuala_Lumpur')::date - 3)`;
  await db.exec(`insert into observations (location_id, source, observed_at, is_backfill)
    select 1, 'openmeteo_current', (${day}::timestamp at time zone 'Asia/Kuala_Lumpur') + make_interval(mins => 15 * (k + 1)), k = 3
    from generate_series(0, 96) k;`);
  const { rows } = await db.query(`select stream, received, expected, coverage_pct, backfilled from v_coverage_daily
                                   where local_date = ${day} order by stream`);
  const om = rows.find((r) => r.stream === 'openmeteo_current');
  assert.equal(om.received, 96);                         // 00:15 … 24:00 (interval-end stamps)
  assert.equal(om.expected, 96);
  assert.equal(om.coverage_pct, 100);
  assert.equal(om.backfilled, 1);
  assert.equal(rows.find((r) => r.stream === 'metar_wmki').received, 0);
  const { rows: today } = await db.query(`select expected from v_coverage_daily
      where stream = 'openmeteo_current' and local_date = (now() at time zone 'Asia/Kuala_Lumpur')::date`);
  assert.ok(today[0].expected <= 96, 'today is prorated up to now');
});

test('anon can read every view', async () => {
  const db = await freshDb();
  await asAnon(db, async () => {
    for (const v of ['v_actual_hourly', 'v_forecasts_all', 'v_pairs', 'v_now', 'v_rain_status', 'v_collection_window', 'v_coverage_daily']) {
      await db.query(`select * from ${v} limit 1`);
    }
  });
});
