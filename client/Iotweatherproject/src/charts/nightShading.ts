import { toAxisTime } from '../lib/fmt';
import type { Palette } from './themes';

const HOUR = 3600e3;

// Night bands from 19:15 to 07:15 MYT, which make the daily cycle and afternoon storms easy to see.
export function nightShading(from: string, to: string, p: Palette) {
  const start = toAxisTime(from);
  const end = toAxisTime(to);
  const firstDay = Math.floor(start / (24 * HOUR)) * 24 * HOUR;
  const bands = [];
  for (let day = firstDay - 24 * HOUR; day < end; day += 24 * HOUR) {
    const dusk = day + 19.25 * HOUR;
    const dawn = day + 31.25 * HOUR;
    if (dawn > start && dusk < end) bands.push([{ xAxis: Math.max(dusk, start) }, { xAxis: Math.min(dawn, end) }]);
  }
  return { silent: true, itemStyle: { color: p.night }, data: bands };
}
