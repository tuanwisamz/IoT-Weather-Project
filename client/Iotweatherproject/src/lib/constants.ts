// The report window, frozen by the data check (Implementation-plan §5.3). Every report figure uses it.
export const FROZEN_WINDOW = {
  from: '2026-11-03T16:00:00Z',     // Wed 4 Nov 00:00 MYT
  to: '2026-11-06T16:00:00Z',       // Sat 7 Nov 00:00 MYT
  fromDate: '2026-11-04',
  toDate: '2026-11-07',
  label: '4 – 7 Nov',
};

export interface ModelInfo {
  code: string;
  label: string;
  dark: string;
  light: string;
  dashed?: boolean;
}

// Fixed order, and each colour stays with its model however the selection changes (spec §2.4).
export const MODELS: ModelInfo[] = [
  { code: 'best_match', label: 'Best Match', dark: '#D4AF37', light: '#A8841A' },
  { code: 'ecmwf_ifs025', label: 'ECMWF IFS', dark: '#5AA9E6', light: '#2F7FC1' },
  { code: 'gfs_seamless', label: 'NOAA GFS', dark: '#E8775A', light: '#C4553A' },
  { code: 'icon_seamless', label: 'DWD ICON', dark: '#4FC1A6', light: '#1F9480' },
  { code: 'best_match+ml', label: 'Best Match + ML', dark: '#F0DC9A', light: '#6E5410', dashed: true },
];
export const ML_MODEL = 'best_match+ml';
export const modelInfo = (code: string) => MODELS.find((m) => m.code === code);
export const modelLabel = (code: string) => modelInfo(code)?.label ?? code;

export const ACTUAL_COLOR = { dark: '#F3EFE6', light: '#17150F' };

export interface VariableInfo {
  code: string;
  label: string;
  unit: string;
  digits: number;
}

export const VARIABLES: VariableInfo[] = [
  { code: 'temperature_c', label: 'Temperature', unit: '°C', digits: 1 },
  { code: 'humidity_pct', label: 'Humidity', unit: '%', digits: 0 },
  { code: 'wind_speed_kmh', label: 'Wind', unit: 'km/h', digits: 1 },
  { code: 'pressure_hpa', label: 'Pressure', unit: 'hPa', digits: 1 },
  { code: 'precipitation_mm', label: 'Rain', unit: 'mm', digits: 1 },
];
export const variableInfo = (code: string) => VARIABLES.find((v) => v.code === code) ?? VARIABLES[0];

export const TRUTHS = [
  { code: 'openmeteo_current', label: 'Open-Meteo analysis', note: 'Model analysis for the town, every 15 min' },
  { code: 'metar_wmki', label: 'Ipoh airport (METAR)', note: 'Real instruments 26 km away, hourly, no rain amounts' },
];

// The archive holds forecasts at whole days, so the slider moves in days (Implementation-plan §1).
export const LEAD_STOPS = [24, 48, 72, 96, 120, 144];

export const LEAD_BUCKETS: Record<string, string> = {
  '000-006': '0–6 h',
  '006-012': '6–12 h',
  '012-024': '12–24 h',
  '024-048': '24–48 h',
  '048-072': '48–72 h',
  '072-120': '72–120 h',
  '120-168': '120–168 h',
};

export const STREAMS: Record<string, string> = {
  openmeteo_current: 'Open-Meteo samples',
  metar_wmki: 'METAR reports',
  forecast_best_match: 'Best Match forecasts',
};
