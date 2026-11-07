import { formatInTimeZone } from 'date-fns-tz';

const TZ = 'Asia/Kuala_Lumpur';

// Every time on screen goes through here, so nothing depends on the viewer's own time zone.
export const fmtMYT = (ts: string | number | Date, pattern = 'EEE d MMM, HH:mm') => formatInTimeZone(ts, TZ, pattern);

export const fmtNum = (value: number | null | undefined, digits = 1) =>
  value == null ? '—' : value.toFixed(digits);

export const fmtSigned = (value: number | null | undefined, digits = 2) =>
  value == null ? '—' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(digits)}`;

export const fmtPct = (value: number | null | undefined) => (value == null ? '—' : `${Math.round(value)} %`);

export function fmtAge(seconds: number) {
  if (seconds < 90) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 36 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`;
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
export const fmtCompass = (deg: number | null) => (deg == null ? '' : COMPASS[Math.round(deg / 45) % 8]);

// ECharts draws in UTC mode, so shifting by +8 h makes its axis read as MYT in any browser.
const MYT_MS = 8 * 3600e3;
export const toAxisTime = (iso: string) => Date.parse(iso) + MYT_MS;
export const fromAxisTime = (value: number) => value - MYT_MS;
