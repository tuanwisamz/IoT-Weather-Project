import type { Theme } from '../app/theme';
import { ACTUAL_COLOR, FROZEN_WINDOW, LEAD_BUCKETS, ML_MODEL, modelInfo, modelLabel, type VariableInfo } from '../lib/constants';
import { fmtMYT, fmtNum, fmtSigned, fromAxisTime, toAxisTime } from '../lib/fmt';
import type { ForecastActualRow, LeadMetricRow, Next24Row, UptimeRow } from '../lib/types';
import { nightShading } from './nightShading';
import { baseOption, PALETTES, timeAxis, tooltipRow, valueAxis } from './themes';

interface TipParam {
  seriesName: string;
  seriesId?: string;
  value: [number, number | null] | number;
  color: string;
  dataIndex: number;
  axisValue: number | string;
}

// Forecast vs actual: the actual line on top, one line per model. Rain uses bars for the actual.
export function forecastVsActual(rows: { model: string; data: ForecastActualRow[] }[], variable: VariableInfo, theme: Theme) {
  const p = PALETTES[theme];
  const rain = variable.code === 'precipitation_mm';
  const actualByHour = new Map<string, number>();
  for (const { data } of rows) {
    for (const r of data) if (r.actual != null) actualByHour.set(r.target_time, r.actual);
  }
  const notes = new Map(rows.map(({ model, data }) => [model, new Map(data.map((r) => [toAxisTime(r.target_time), r]))]));

  const forecasts = rows.map(({ model, data }) => {
    const info = modelInfo(model)!;
    return {
      name: info.label,
      id: model,
      type: 'line',
      step: rain ? 'end' : undefined,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { color: info[theme], width: 1.5, type: info.dashed ? 'dashed' : 'solid' },
      itemStyle: { color: info[theme] },
      data: data.map((r) => [toAxisTime(r.target_time), r.forecast]),
    };
  });
  const actualData = [...actualByHour].map(([t, v]) => [toAxisTime(t), v]).sort((a, b) => a[0] - b[0]);
  const actual = rain
    ? { name: 'Actual', type: 'bar', barMaxWidth: 6, itemStyle: { color: ACTUAL_COLOR[theme], borderRadius: [4, 4, 0, 0] }, data: actualData }
    : { name: 'Actual', type: 'line', showSymbol: false, z: 5, lineStyle: { color: ACTUAL_COLOR[theme], width: 2 }, itemStyle: { color: ACTUAL_COLOR[theme] }, data: actualData };

  return {
    ...baseOption(p),
    grid: { left: 48, right: 16, top: 28, bottom: 64 },
    xAxis: timeAxis(p, { min: toAxisTime(FROZEN_WINDOW.from), max: toAxisTime(FROZEN_WINDOW.to) }),
    yAxis: valueAxis(p, variable.unit, rain ? { min: 0, scale: false } : {}),
    dataZoom: [
      { type: 'inside' },
      { type: 'slider', height: 18, bottom: 8, borderColor: p.border, fillerColor: 'rgba(212,175,55,0.12)', moveHandleSize: 0, showDetail: false },
    ],
    tooltip: {
      ...baseOption(p).tooltip,
      axisPointer: { type: 'line', lineStyle: { color: p.muted } },
      formatter: (params: TipParam[]) => {
        const time = (params[0].value as [number, number])[0];
        const head = `<div style="font-family:'IBM Plex Mono';font-size:11px;margin-bottom:2px">${fmtMYT(fromAxisTime(time))}</div>`;
        return head + params.map((s) => {
          const value = (s.value as [number, number])[1];
          const text = `${fmtNum(value, variable.digits)} ${variable.unit}`;
          const row = s.seriesId ? notes.get(s.seriesId)?.get(time) : undefined;
          const note = row ? `error ${fmtSigned(row.error, variable.digits)} · issued ${fmtMYT(row.issued_at, 'EEE HH:mm')} · lead ${row.lead_hours} h` : '';
          return tooltipRow(s.color, s.seriesName, text, note);
        }).join('');
      },
    },
    series: [
      ...forecasts,
      { ...actual, markArea: nightShading(FROZEN_WINDOW.from, FROZEN_WINDOW.to, p) },
    ],
  };
}

export type LeadMetric = 'mae' | 'bias' | 'rmse';

// ECharts doesn't separate end labels, so labels that would touch are pushed apart by hand.
function endLabelOffsets(rows: LeadMetricRow[], models: string[], last: string | undefined, metric: LeadMetric) {
  const LINE_PX = 14;
  const ends = models.flatMap((code) => {
    const r = rows.find((x) => x.model === code && x.lead_bucket === last);
    return r ? [{ code, value: r[metric] }] : [];
  }).sort((a, b) => b.value - a.value);
  const values = rows.map((r) => r[metric]);
  const span = Math.max(...values, 0) - Math.min(...values, 0) || 1;
  const pxPerUnit = 240 / span;
  const offsets = new Map<string, number>();
  let previous = -Infinity;
  for (const { code, value } of ends) {
    const y = Math.max(-value * pxPerUnit, previous + LINE_PX);
    offsets.set(code, y + value * pxPerUnit);
    previous = y;
  }
  return offsets;
}

// Error vs lead: one line per model, labelled at its end, with symbols sized by sample count.
export function errorVsLead(rows: LeadMetricRow[], models: string[], metric: LeadMetric, variable: VariableInfo, theme: Theme) {
  const p = PALETTES[theme];
  const buckets = [...new Set(rows.map((r) => r.lead_bucket))].sort();
  const offsets = endLabelOffsets(rows, models, buckets.at(-1), metric);
  const series = models.flatMap((code) => {
    const info = modelInfo(code)!;
    const own = rows.filter((r) => r.model === code);
    if (!own.length) return [];
    return [{
      name: info.label,
      type: 'line',
      symbol: 'circle',
      lineStyle: { color: info[theme], width: 2, type: info.dashed ? 'dashed' : 'solid' },
      itemStyle: { color: info[theme], borderColor: p.surface, borderWidth: 2 },
      endLabel: { show: true, formatter: info.label, color: p.muted, fontSize: 11, offset: [4, offsets.get(code) ?? 0] },
      data: buckets.map((b) => {
        const r = own.find((x) => x.lead_bucket === b);
        return r ? {
          value: r[metric],
          n: r.n,
          symbolSize: Math.max(8, Math.min(16, Math.sqrt(r.n) * 0.8)),
          itemStyle: { opacity: r.n < 20 ? 0.4 : 1 },
        } : null;
      }),
    }];
  });
  return {
    ...baseOption(p),
    grid: { left: 44, right: 112, top: 28, bottom: 28 },
    xAxis: {
      type: 'category',
      data: buckets.map((b) => LEAD_BUCKETS[b] ?? b),
      axisLine: { lineStyle: { color: p.border } },
      axisTick: { show: false },
      axisLabel: { color: p.muted },
    },
    yAxis: valueAxis(p, `${metric.toUpperCase()} (${variable.unit})`, metric === 'bias' ? {} : { min: 0, scale: false }),
    tooltip: {
      ...baseOption(p).tooltip,
      axisPointer: { type: 'line', lineStyle: { color: p.muted } },
      formatter: (params: (TipParam & { data: { value: number; n: number } | null })[]) =>
        `<div style="margin-bottom:2px">${params[0].axisValue}</div>` + params.filter((s) => s.data).map((s) =>
          tooltipRow(s.color, s.seriesName, `${fmtNum(s.data!.value, 2)} ${variable.unit} · n ${s.data!.n}`)).join(''),
    },
    series,
  };
}

// Next 24 h: two panels sharing one time axis, because temperature and probability have different scales.
export function next24h(rows: Next24Row[], theme: Theme) {
  const p = PALETTES[theme];
  const sky = theme === 'dark' ? '#5AA9E6' : '#2F7FC1';
  const gold = modelInfo('best_match')![theme];
  const mlColor = modelInfo(ML_MODEL)![theme];
  const times = rows.map((r) => toAxisTime(r.target_time));
  const min = Math.min(...times) - 1800e3;
  const max = Math.max(...times) + 1800e3;
  return {
    ...baseOption(p),
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 44, right: 16, top: 24, height: 150 },
      { left: 44, right: 16, top: 208, height: 76 },
    ],
    xAxis: [
      timeAxis(p, { min, max, gridIndex: 0, axisLabel: { show: false } }),
      timeAxis(p, { min, max, gridIndex: 1 }),
    ],
    yAxis: [
      valueAxis(p, '°C', { gridIndex: 0 }),
      valueAxis(p, 'Rain chance (%)', { gridIndex: 1, min: 0, max: 100, scale: false, splitNumber: 2 }),
    ],
    tooltip: {
      ...baseOption(p).tooltip,
      axisPointer: { type: 'line', lineStyle: { color: p.muted } },
      formatter: (params: TipParam[]) => {
        const time = (params[0].value as [number, number])[0];
        const r = rows[times.indexOf(time)];
        if (!r) return '';
        return `<div style="font-family:'IBM Plex Mono';font-size:11px;margin-bottom:2px">${fmtMYT(fromAxisTime(time))}</div>`
          + tooltipRow(gold, 'Temperature', `${fmtNum(r.temperature_c)} °C`)
          + (r.temperature_c_ml == null ? '' : tooltipRow(mlColor, 'Corrected by ML', `${fmtNum(r.temperature_c_ml)} °C`))
          + tooltipRow(sky, 'Rain chance', `${fmtNum(r.precip_probability_pct, 0)} %`)
          + tooltipRow(p.muted, 'Rain', `${fmtNum(r.precipitation_mm)} mm`);
      },
    },
    series: [
      {
        name: 'Temperature', type: 'line', showSymbol: false, xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { color: gold, width: 2 }, itemStyle: { color: gold },
        data: rows.map((r, i) => [times[i], r.temperature_c]),
      },
      // Leads under 24 h are outside the ML model's training range, so the line is dashed and labelled.
      ...(rows.some((r) => r.temperature_c_ml != null) ? [{
        name: 'Corrected by ML', type: 'line', showSymbol: false, xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { color: mlColor, width: 2, type: 'dashed' }, itemStyle: { color: mlColor },
        data: rows.map((r, i) => [times[i], r.temperature_c_ml]),
      }] : []),
      {
        name: 'Rain chance', type: 'bar', barMaxWidth: 14, xAxisIndex: 1, yAxisIndex: 1,
        itemStyle: { color: sky, borderRadius: [4, 4, 0, 0] },
        data: rows.map((r, i) => [times[i], r.precip_probability_pct]),
      },
    ],
  };
}

// Daily uptime: stacked run outcomes per day, for one job. Status colours always sit beside a legend.
export function uptime(rows: UptimeRow[], theme: Theme) {
  const p = PALETTES[theme];
  const days = rows.map((r) => fmtMYT(`${r.local_date}T12:00:00+08:00`, 'EEE d MMM'));
  const stack = (name: string, color: string, key: keyof UptimeRow) => ({
    name, type: 'bar', stack: 'runs', barMaxWidth: 28,
    itemStyle: { color, borderColor: p.surface, borderWidth: 2, borderRadius: 2 },
    data: rows.map((r) => r[key]),
  });
  return {
    ...baseOption(p),
    grid: { left: 44, right: 16, top: 28, bottom: 28 },
    xAxis: { type: 'category', data: days, axisLine: { lineStyle: { color: p.border } }, axisTick: { show: false }, axisLabel: { color: p.muted } },
    yAxis: valueAxis(p, 'Runs', { min: 0, scale: false }),
    tooltip: { ...baseOption(p).tooltip, axisPointer: { type: 'shadow', shadowStyle: { color: p.grid } } },
    series: [
      stack('Success', p.ok, 'success_runs'),
      stack('Partial', p.watch, 'partial_runs'),
      stack('Failed', p.alert, 'failed_runs'),
      stack('Missing', p.missing, 'missing_runs'),
    ],
  };
}

export const describeLead = (rows: LeadMetricRow[], metric: LeadMetric) =>
  rows.map((r) => `${modelLabel(r.model)} ${LEAD_BUCKETS[r.lead_bucket]}: ${fmtNum(r[metric], 2)}`).join('; ');
