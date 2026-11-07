// T3.2 / T3.3: RPC functions against a 4-hour dataset whose metrics are worked out by hand.
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { freshDb, asAnon } from './db.mjs';

const close = (actual, expected, msg) => assert.ok(Math.abs(actual - expected) < 1e-4, `${msg}: ${actual} ≠ ${expected}`);
const FROM = '2026-10-20T00:00:00Z';
const TO = '2026-10-21T00:00:00Z';

// Hours H1..H4 (06–09 UTC on 20 Oct), each complete (4 samples), actual temperature 30.
//            precip/sample  observed   best_match temp (lead 24)  fc mm  fc prob   ecmwf temp
// H1 06:00   0.1 (0.4 mm)   rain       31 (+1)                    0.5    80        30
// H2 07:00   0              dry        29 (−1)                    0.3    60        30
// H3 08:00   0              dry        30 ( 0)                    0.0    10        30
// H4 09:00   0.05 (0.2 mm)  rain       32 (+2)                    0.0    30        30
// ⇒ temp MAE 1.0, bias 0.5, RMSE √1.5 · a=b=c=d=1: POD ½, FAR ½, CSI ⅓, HSS 0 · Brier 0.225, BSS 0.1
const SEED = `
  insert into observations (location_id, source, observed_at, temperature_c, precipitation_mm)
  select 1, 'openmeteo_current', h.t - make_interval(mins => 15 * k), 30, h.p
  from (values (timestamptz '2026-10-20T06:00:00Z', 0.1), ('2026-10-20T07:00:00Z', 0), ('2026-10-20T08:00:00Z', 0),
               ('2026-10-20T09:00:00Z', 0.05)) h(t, p), generate_series(0, 3) k;
  insert into forecasts (location_id, model, issued_at, target_time, temperature_c, precipitation_mm, precip_probability_pct)
  select 1, 'best_match', t - interval '24 hours', t, temp, mm, prob
  from (values (timestamptz '2026-10-20T06:00:00Z', 31, 0.5, 80), ('2026-10-20T07:00:00Z', 29, 0.3, 60),
               ('2026-10-20T08:00:00Z', 30, 0.0, 10), ('2026-10-20T09:00:00Z', 32, 0.0, 30)) f(t, temp, mm, prob);
  insert into forecasts (location_id, model, issued_at, target_time, temperature_c, precipitation_mm)
  select 1, 'ecmwf_ifs025', t - interval '30 hours', t, 30, mm
  from (values (timestamptz '2026-10-20T06:00:00Z', 1.0), ('2026-10-20T07:00:00Z', 0.0), ('2026-10-20T08:00:00Z', 0.0),
               ('2026-10-20T09:00:00Z', 0.4)) f(t, mm);
  -- A fresher (6 h) best_match forecast for H1, which the lead slider must skip at ≥ 24 h.
  insert into forecasts (location_id, model, issued_at, target_time, temperature_c)
  values (1, 'best_match', '2026-10-20T00:00:00Z', '2026-10-20T06:00:00Z', 35);`;

let db;
before(async () => {
  db = await freshDb();
  await db.exec(SEED);
});

const rpc = async (call) => (await asAnon(db, () => db.query(`select * from ${call}`))).rows;

test('rpc_forecast_vs_actual picks the freshest forecast at least p_lead_min old', async () => {
  const at24 = await rpc(`rpc_forecast_vs_actual('best_match', 'temperature_c', 24, '${FROM}', '${TO}')`);
  assert.deepEqual(at24.map((r) => [r.forecast, r.actual, r.error, r.lead_hours]),
    [[31, 30, 1, 24], [29, 30, -1, 24], [30, 30, 0, 24], [32, 30, 2, 24]]);
  const at1 = await rpc(`rpc_forecast_vs_actual('best_match', 'temperature_c', 1, '${FROM}', '${TO}')`);
  assert.equal(at1[0].forecast, 35);
  assert.equal(at1[0].lead_hours, 6);
});

test('rpc_metrics_by_lead: MAE, bias, RMSE and n', async () => {
  const rows = await rpc(`rpc_metrics_by_lead('${FROM}', '${TO}') where model = 'best_match'
                          and variable = 'temperature_c' and lead_bucket = '024-048'`);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].n, 4);
  close(rows[0].mae, 1.0, 'mae');
  close(rows[0].bias, 0.5, 'bias');
  close(rows[0].rmse, Math.sqrt(1.5), 'rmse');
});

test('rpc_rain_contingency: a = b = c = d = 1', async () => {
  const [r] = await rpc(`rpc_rain_contingency('${FROM}', '${TO}') where model = 'best_match' and lead_bucket = '024-048'`);
  assert.deepEqual([r.hits, r.false_alarms, r.misses, r.correct_negatives, r.n], [1, 1, 1, 1, 4]);
  close(r.pod, 0.5, 'pod');
  close(r.far, 0.5, 'far');
  close(r.csi, 1 / 3, 'csi');
  close(r.freq_bias, 1, 'freq_bias');
  close(r.hss, 0, 'hss');
  const [e] = await rpc(`rpc_rain_contingency('${FROM}', '${TO}') where model = 'ecmwf_ifs025'`);
  assert.deepEqual([e.hits, e.false_alarms, e.misses, e.correct_negatives], [2, 0, 0, 2]);
  close(e.csi, 1, 'perfect csi');
});

test('rpc_brier and rpc_reliability', async () => {
  const [b] = await rpc(`rpc_brier('${FROM}', '${TO}') where model = 'best_match'`);
  assert.equal(b.n, 4);
  close(b.brier, 0.225, 'brier');
  close(b.base_rate, 0.5, 'base rate');
  close(b.bss, 0.1, 'bss');
  assert.equal((await rpc(`rpc_brier('${FROM}', '${TO}') where model = 'ecmwf_ifs025'`)).length, 0,
    'models without probabilities are excluded');

  const bins = await rpc(`rpc_reliability('${FROM}', '${TO}', 'best_match', 48)`);
  assert.equal(bins.length, 10);
  assert.deepEqual(bins.filter((x) => x.n > 0).map((x) => [x.bin_lower, x.n, x.observed_freq]),
    [[10, 1, 0], [30, 1, 1], [60, 1, 0], [80, 1, 1]]);
});

test('rpc_leaderboard ranks the perfect model first', async () => {
  const rows = await rpc(`rpc_leaderboard('${FROM}', '${TO}')`);
  assert.deepEqual(rows.map((r) => r.model), ['ecmwf_ifs025', 'best_match']);
  close(rows[0].temp_mae, 0, 'ecmwf mae');
  close(rows[0].rain_csi, 1, 'ecmwf csi');
  assert.equal(rows[0].brier, null);
  // best_match: temp MAE over its 24–144 h pairs, so the 6 h forecast for H1 is left out: (1+1+0+2)/4
  close(rows[1].temp_mae, 1.0, 'best_match mae');
  assert.equal(rows[1].n, 4);
});

test('rpc_daily_pairs uses the earliest snapshot and blanks partial days', async () => {
  const day = await freshDb();
  // Local day 20 Oct (MYT) = 19 Oct 16:00 → 20 Oct 16:00 UTC: 24 complete hours, max 33 at 06:00 UTC, 1.2 mm total.
  await day.exec(`
    insert into observations (location_id, source, observed_at, temperature_c, precipitation_mm)
    select 1, 'openmeteo_current', timestamptz '2026-10-19T16:15:00Z' + make_interval(mins => 15 * k),
           case when k between 52 and 55 then 33 else 26 end, case when k < 12 then 0.1 else 0 end
    from generate_series(0, 95) k;
    -- 21 Oct has only 10 complete hours
    insert into observations (location_id, source, observed_at, temperature_c, precipitation_mm)
    select 1, 'openmeteo_current', timestamptz '2026-10-20T16:15:00Z' + make_interval(mins => 15 * k), 27, 0
    from generate_series(0, 39) k;
    insert into forecasts_daily (location_id, model, issued_at, target_date, lead_days, temp_max_c, temp_min_c, precipitation_sum_mm)
    values (1, 'best_match', '2026-10-19T01:00:00Z', '2026-10-20', 1, 32, 25, 3.0),
           (1, 'best_match', '2026-10-19T09:00:00Z', '2026-10-20', 1, 34, 24, 0.5),
           (1, 'best_match', '2026-10-20T01:00:00Z', '2026-10-21', 1, 31, 25, 0.0);`);
  const { rows } = await asAnon(day, () => day.query(`select * from rpc_daily_pairs('2026-10-20', '2026-10-22')`));
  assert.equal(rows.length, 2);
  const [d20, d21] = rows;
  assert.deepEqual([d20.temp_max_fc, d20.temp_max_obs, d20.temp_min_obs, d20.hours_complete], [32, 33, 26, 24]);
  close(d20.rain_obs_mm, 1.2, 'daily rain');
  assert.equal(d20.rain_day_fc, true);
  assert.equal(d20.rain_day_obs, true);
  assert.equal(d21.hours_complete, 10);
  assert.equal(d21.temp_max_obs, null);
  assert.equal(d21.rain_day_obs, null);
});

test('rpc_uptime_daily: proration, missing runs and start delay', async () => {
  const up = await freshDb();
  // Local 20 Oct: observe slots 00:07 … 23:57 MYT (144). Slots 10–13 missing, 20–21 failed, all 60 s late.
  await up.exec(`
    insert into ingestion_runs (job, trigger, started_at, finished_at, status)
    select 'observe', 'schedule', s + interval '60 seconds', s + interval '120 seconds',
           case when k in (20, 21) then 'failed' else 'success' end
    from (select k, timestamptz '2026-10-19T16:07:00Z' + make_interval(mins => 10 * k) as s
          from generate_series(0, 143) k) x
    where k not between 10 and 13;
    insert into ingestion_runs (job, trigger, started_at, status)
    values ('observe', 'dispatch', '2026-10-20T03:00:00Z', 'success');   -- manual runs don't count`);
  const { rows } = await asAnon(up, () => up.query(
    `select * from rpc_uptime_daily('2026-10-19T16:00:00Z', '2026-10-20T16:00:00Z')`));
  assert.equal(rows.length, 1);
  const r = rows[0];
  assert.deepEqual([r.local_date.toISOString().slice(0, 10), r.job, r.expected_runs, r.success_runs, r.failed_runs,
    r.missing_runs], ['2026-10-20', 'observe', 144, 138, 2, 4]);
  close(r.uptime_pct, (100 * 138) / 144, 'uptime');
  close(r.median_start_delay_s, 60, 'delay');

  const timeline = await asAnon(up, () => up.query(
    `select job, start_delay_s from rpc_runs_timeline('2026-10-19T16:00:00Z', '2026-10-20T16:00:00Z') limit 1`));
  close(timeline.rows[0].start_delay_s, 60, 'timeline delay');
});

test('rpc_runs_timeline lists failed steps', async () => {
  const t = await freshDb();
  await t.exec(`insert into ingestion_runs (job, trigger, started_at, finished_at, status, steps) values
    ('observe', 'local', now() - interval '1 minute', now(), 'partial',
     '[{"step":"om_current","ok":true},{"step":"metar","ok":false,"error":"x"}]')`);
  const { rows } = await asAnon(t, () => t.query(`select * from rpc_runs_timeline(now() - interval '1 hour', now() + interval '1 hour')`));
  assert.deepEqual(rows[0].failed_steps, ['metar']);
  assert.equal(rows[0].start_delay_s, null, 'only scheduled runs have a delay');
});

test('rpc_next_24h returns the newest snapshot for the coming hours', async () => {
  const n = await freshDb();
  await n.exec(`
    insert into forecasts (location_id, model, issued_at, target_time, temperature_c)
    select 1, 'best_match', date_trunc('hour', now()) - interval '1 hour', date_trunc('hour', now()) + make_interval(hours => k), 20
    from generate_series(-1, 30) k;
    insert into forecasts (location_id, model, issued_at, target_time, temperature_c)
    select 1, 'best_match', date_trunc('hour', now()), date_trunc('hour', now()) + make_interval(hours => k), 25
    from generate_series(0, 30) k;`);
  const { rows } = await asAnon(n, () => n.query(`select * from rpc_next_24h()`));
  assert.equal(rows.length, 24);
  assert.ok(rows.every((r) => r.temperature_c === 25 && r.temperature_c_ml === null));
});

test('rpc_kpis returns every section and names a best model only with n ≥ 20', async () => {
  const [{ rpc_kpis: k }] = await rpc(`rpc_kpis('${FROM}', '${TO}')`);
  assert.deepEqual(Object.keys(k).sort(), ['best_model', 'brier', 'collection', 'last_obs_at', 'rain', 'temperature']);
  assert.equal(k.best_model.temperature, null);
  assert.equal(k.temperature.lead_bucket, '024-048');
  assert.equal(k.temperature.n, 4);
  assert.equal(k.brier.n, 4);
  close(k.brier.brier, 0.225, 'kpi brier');
});
