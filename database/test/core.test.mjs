// T1.1 and T1.8: schema, seeds, RLS, and the (H-1h, H] hour bucketing.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { freshDb, asAnon, migrationFiles, hasMigration } from './db.mjs';

const NUMERIC_ORDER = ['0001_core', '0002_views', '0003_rpc', '0004_rls', '0005_seed'];

test('migrations apply in phased order and in numeric order', async () => {
  await freshDb();
  await freshDb({ order: NUMERIC_ORDER });
  assert.ok(migrationFiles().length >= 3);
});

test('seeds are present', async () => {
  const db = await freshDb();
  const { rows } = await db.query(`select
      (select count(*) from locations)::int as locations,
      (select count(*) from sources)::int as sources,
      (select count(*) from forecast_models where is_active)::int as active_models,
      (select count(*) from ml_models where is_active)::int as active_ml`);
  assert.deepEqual(rows[0], { locations: 1, sources: 4, active_models: 4, active_ml: 0 });
});

test('anon can read observations but cannot write them', async () => {
  const db = await freshDb();
  await db.exec(`insert into observations (location_id, source, observed_at, temperature_c)
                 values (1, 'openmeteo_current', '2026-11-01T00:15:00Z', 27.1)`);
  await asAnon(db, async () => {
    const { rows } = await db.query('select temperature_c from observations');
    assert.equal(rows.length, 1);
    await assert.rejects(
      db.query(`insert into observations (location_id, source, observed_at) values (1, 'openmeteo_current', now())`),
      /permission denied|row-level security/,
    );
    await assert.rejects(db.query('delete from observations'), /permission denied/);
  });
});

test('anon cannot read raw_responses', async () => {
  const db = await freshDb();
  await db.exec(`insert into raw_responses (source, url, payload) values ('openmeteo_forecast', 'https://x', '{}')`);
  await asAnon(db, async () => {
    await assert.rejects(db.query('select * from raw_responses'), /permission denied/);
  });
});

test('lead_hours is generated from target_time - issued_at', async () => {
  const db = await freshDb();
  const { rows } = await db.query(`insert into forecasts (location_id, model, issued_at, target_time, temperature_c)
      values (1, 'best_match', '2026-11-01T06:00:00Z', '2026-11-02T08:00:00Z', 30) returning lead_hours`);
  assert.equal(rows[0].lead_hours, 26);
});

test('only one active version per ML model name', async () => {
  const db = await freshDb();
  const insert = (version) => `insert into ml_models (name, version, algorithm, features, is_active)
                               values ('bias_temperature', '${version}', 'lightgbm', array['x'], true)`;
  await db.exec(insert('v1.0'));
  await assert.rejects(db.exec(insert('v1.1')), /duplicate key/);
});

test('T1.8: four 15-min samples make one complete hour, bucketed as (H-1h, H]', { skip: !hasMigration('0002_views') }, async () => {
  const db = await freshDb();
  // Samples at 12:15, 12:30, 12:45, 13:00 belong to hour 13:00; 13:15 starts hour 14:00.
  await db.exec(`insert into observations (location_id, source, observed_at, temperature_c, precipitation_mm) values
    (1, 'openmeteo_current', '2026-11-01T12:15:00Z', 27.0, 0.0),
    (1, 'openmeteo_current', '2026-11-01T12:30:00Z', 27.5, 0.2),
    (1, 'openmeteo_current', '2026-11-01T12:45:00Z', 28.0, 0.3),
    (1, 'openmeteo_current', '2026-11-01T13:00:00Z', 28.4, 0.1),
    (1, 'openmeteo_current', '2026-11-01T13:15:00Z', 28.6, 0.0)`);
  const { rows } = await db.query(`select hour, samples, temperature_c, round(precipitation_mm::numeric, 3)::float as precip, rain_hour
      from v_actual_hourly where source = 'openmeteo_current' order by hour`);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].hour.toISOString(), '2026-11-01T13:00:00.000Z');
  assert.equal(rows[0].samples, 4);
  assert.ok(Math.abs(rows[0].temperature_c - 28.4) < 1e-5, 'instantaneous value uses the sample stamped at H');
  assert.equal(rows[0].precip, 0.6);
  assert.equal(rows[0].rain_hour, true);
  assert.equal(rows[1].hour.toISOString(), '2026-11-01T14:00:00.000Z');
  assert.equal(rows[1].samples, 1);
});
