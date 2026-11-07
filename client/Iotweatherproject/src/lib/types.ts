// Row types, hand-written from api-spec §3 and migrations 0006–0007.

export interface NowRow {
  source: string;
  observed_at: string;
  age_s: number;
  temperature_c: number | null;
  humidity_pct: number | null;
  dew_point_c: number | null;
  precipitation_mm: number | null;
  wind_speed_kmh: number | null;
  wind_dir_deg: number | null;
  pressure_hpa: number | null;
  cloud_cover_pct: number | null;
  weather_code: number | null;
  is_raining: boolean | null;
  is_thunder: boolean | null;
}

export type RainLevel = 'CLEAR' | 'WATCH' | 'RAIN_LIKELY' | 'UNKNOWN';

export interface RainStatus {
  issued_at: string;
  model_version: string;
  prob_1h: number | null;
  prob_3h: number | null;
  level: RainLevel;
}

export interface CollectionWindow {
  first_obs_at: string;
  last_obs_at: string;
  streak_start: string;
  streak_end: string;
  streak_hours: number;
  samples: number;
  expected_samples: number;
  meets_3_days: boolean;
  live_since: string | null;
  backfilled_samples: number;
  live_samples: number;
  live_expected_samples: number | null;
}

export interface Kpis {
  temperature: { model: string; lead_bucket: string; mae: number; bias: number; n: number } | null;
  rain: { model: string; lead_bucket: string; csi: number; pod: number; far: number; n: number } | null;
  brier: { brier: number; bss: number; n: number } | null;
  best_model: { temperature: string | null; rain: string | null };
  last_obs_at: string | null;
}

export interface Next24Row {
  target_time: string;
  temperature_c: number | null;
  temperature_c_ml: number | null;
  precipitation_mm: number | null;
  precip_probability_pct: number | null;
  weather_code: number | null;
  wind_speed_kmh: number | null;
}

export interface ForecastActualRow {
  target_time: string;
  forecast: number;
  actual: number | null;
  error: number | null;
  issued_at: string;
  lead_hours: number;
}

export interface LeadMetricRow {
  model: string;
  variable: string;
  lead_bucket: string;
  n: number;
  bias: number;
  mae: number;
  rmse: number;
  r: number | null;
}

export interface LeaderboardRow {
  model: string;
  n: number;
  temp_mae: number | null;
  rh_mae: number | null;
  wind_mae: number | null;
  pres_mae: number | null;
  rain_csi: number | null;
  brier: number | null;
  rank_overall: number | null;
}

export interface NextDayRow {
  target_date: string;
  temp_max_fc: number | null;
  temp_max_obs: number | null;
  temp_min_fc: number | null;
  temp_min_obs: number | null;
  rain_fc_mm: number | null;
  rain_obs_mm: number | null;
  rain_day_fc: boolean | null;
  rain_day_obs: boolean | null;
  hours_fc: number;
  hours_complete: number;
}

export interface UptimeRow {
  local_date: string;
  job: string;
  expected_runs: number;
  success_runs: number;
  partial_runs: number;
  failed_runs: number;
  missing_runs: number;
  uptime_pct: number | null;
  median_start_delay_s: number | null;
}

export interface CoverageRow {
  local_date: string;
  stream: string;
  received: number;
  expected: number;
  coverage_pct: number;
  backfilled: number;
}

export interface RunRow {
  id: number;
  job: string;
  trigger: string;
  status: 'running' | 'success' | 'partial' | 'failed';
  started_at: string;
  finished_at: string | null;
  rows_written: Record<string, number>;
  gh_run_id: number | null;
  error: string | null;
}
