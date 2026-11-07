import type { Theme } from '../app/theme';
import { fmtMYT, fromAxisTime } from '../lib/fmt';

export interface Palette {
  text: string;
  muted: string;
  border: string;
  grid: string;
  surface: string;
  night: string;
  gold: string;
  ok: string;
  watch: string;
  alert: string;
  missing: string;
}

export const PALETTES: Record<Theme, Palette> = {
  dark: {
    text: '#F3EFE6', muted: '#A39E93', border: '#2A2A2F', grid: '#1F1F23', surface: '#121214', night: '#1A1A1D',
    gold: '#D4AF37', ok: '#3FB68B', watch: '#F08A24', alert: '#E5484D', missing: '#3A3A40',
  },
  light: {
    text: '#17150F', muted: '#5F5A4F', border: '#E2DCCD', grid: '#EEE9DD', surface: '#FFFFFF', night: '#F5F1E6',
    gold: '#A8841A', ok: '#1F8A63', watch: '#B85F0B', alert: '#C62A2F', missing: '#D6D0C2',
  },
};

export function baseOption(p: Palette) {
  return {
    backgroundColor: 'transparent',
    useUTC: true,
    animationDuration: 300,
    textStyle: { fontFamily: 'IBM Plex Sans', color: p.muted, fontSize: 12 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: p.surface,
      borderColor: p.border,
      textStyle: { color: p.text, fontSize: 12 },
      confine: true,
    },
  };
}

export const axisLabelTime = (value: number) => {
  const real = fromAxisTime(value);
  return fmtMYT(real, 'HH:mm') === '00:00' ? fmtMYT(real, 'EEE d MMM') : fmtMYT(real, 'HH:mm');
};

export function timeAxis(p: Palette, extra: object = {}) {
  return {
    type: 'time',
    axisLine: { lineStyle: { color: p.border } },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: { color: p.muted, formatter: axisLabelTime, hideOverlap: true },
    ...extra,
  };
}

export function valueAxis(p: Palette, name: string, extra: object = {}) {
  return {
    type: 'value',
    name,
    nameTextStyle: { color: p.muted, align: 'left' },
    scale: true,
    axisLabel: { color: p.muted },
    splitLine: { lineStyle: { color: p.grid } },
    ...extra,
  };
}

export const tooltipRow = (color: string, label: string, value: string, note = '') =>
  `<div style="display:flex;align-items:center;gap:6px;line-height:1.7">
     <span style="width:8px;height:8px;border-radius:50%;background:${color}"></span>
     <span>${label}</span>
     <span style="margin-left:auto;padding-left:16px;font-variant-numeric:tabular-nums">${value}</span>
   </div>${note ? `<div style="opacity:.7;padding-left:14px;font-size:11px">${note}</div>` : ''}`;
