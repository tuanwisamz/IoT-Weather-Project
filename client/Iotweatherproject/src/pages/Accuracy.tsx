import { useMemo, useState } from 'react';
import { useTheme } from '../app/theme';
import { Chart } from '../charts/Chart';
import { describeLead, errorVsLead, forecastVsActual, type LeadMetric } from '../charts/options';
import { ChartCard } from '../components/ChartCard';
import { FilterBar, LeadSlider, ModelChips, Segmented, TruthSelect, VariableTabs } from '../components/Filters';
import { MetricTable, type Column } from '../components/MetricTable';
import { FROZEN_WINDOW, ML_MODEL, modelLabel, TRUTHS, variableInfo } from '../lib/constants';
import { fmtMYT, fmtNum } from '../lib/fmt';
import { GLOSSARY } from '../lib/glossary';
import { useForecastActual, useLeaderboard, useLeadMetrics, useNextDay } from '../lib/queries';
import type { LeaderboardRow, NextDayRow } from '../lib/types';
import { useAccuracyFilters } from '../lib/urlState';

const truthLabel = (code: string) => TRUTHS.find((t) => t.code === code)?.label ?? code;

const LEADERBOARD: Column<LeaderboardRow>[] = [
  {
    key: 'model', label: 'Model', align: 'left', value: (r) => modelLabel(r.model),
    render: (r) => (
      <>
        {modelLabel(r.model)}
        {r.model === ML_MODEL && <span className="ml-1.5 rounded-full bg-gold-tint px-1.5 py-0.5 text-[11px] text-gold-text">ML</span>}
      </>
    ),
  },
  { key: 'temp_mae', label: 'Temp MAE (°C)', value: (r) => r.temp_mae, render: (r) => fmtNum(r.temp_mae, 2), best: 'low' },
  { key: 'rh_mae', label: 'Humidity MAE (%)', value: (r) => r.rh_mae, render: (r) => fmtNum(r.rh_mae, 1), best: 'low' },
  { key: 'wind_mae', label: 'Wind MAE (km/h)', value: (r) => r.wind_mae, render: (r) => fmtNum(r.wind_mae, 2), best: 'low' },
  { key: 'pres_mae', label: 'Pressure MAE (hPa)', value: (r) => r.pres_mae, render: (r) => fmtNum(r.pres_mae, 2), best: 'low' },
  { key: 'rain_csi', label: 'Rain CSI', value: (r) => r.rain_csi, render: (r) => fmtNum(r.rain_csi, 2), best: 'high' },
  { key: 'n', label: 'n', value: (r) => r.n },
];

const NEXT_DAY: Column<NextDayRow>[] = [
  { key: 'date', label: 'Date', align: 'left', value: (r) => r.target_date, render: (r) => fmtMYT(`${r.target_date}T12:00:00+08:00`, 'EEE d MMM') },
  { key: 'max', label: 'Max fc / obs (°C)', value: () => null, render: (r) => `${fmtNum(r.temp_max_fc)} / ${fmtNum(r.temp_max_obs)}` },
  { key: 'min', label: 'Min fc / obs (°C)', value: () => null, render: (r) => `${fmtNum(r.temp_min_fc)} / ${fmtNum(r.temp_min_obs)}` },
  { key: 'rain', label: 'Rain fc / obs (mm)', value: () => null, render: (r) => `${fmtNum(r.rain_fc_mm)} / ${fmtNum(r.rain_obs_mm)}` },
  {
    key: 'day', label: 'Rain day correct', value: () => null,
    render: (r) => (r.rain_day_fc == null || r.rain_day_obs == null ? '—' : r.rain_day_fc === r.rain_day_obs ? 'Yes' : 'No'),
  },
  { key: 'hours', label: 'Hours fc / obs', value: () => null, render: (r) => `${r.hours_fc} / ${r.hours_complete}` },
];

function ForecastVsActual({ models, variable, lead, truth }: { models: string[]; variable: string; lead: number; truth: string }) {
  const { theme } = useTheme();
  const info = variableInfo(variable);
  const results = useForecastActual(models, variable, lead, truth);
  const loading = results.some((r) => r.isLoading);
  const error = results.find((r) => r.error)?.error;
  const stamp = results.map((r) => r.dataUpdatedAt).join();
  const rows = useMemo(() => models.map((model, i) => ({ model, data: results[i]?.data ?? [] })).filter((r) => r.data.length),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stamp, models.join()]);
  const option = useMemo(() => forecastVsActual(rows, info, theme), [rows, info, theme]);
  const n = rows[0]?.data.filter((r) => r.actual != null).length ?? 0;
  return (
    <ChartCard overline="Forecast vs actual" title={`${info.label} (${info.unit})`} info={GLOSSARY.lead}
      subtitle={`Forecasts issued at least ${lead} h before each hour · truth: ${truthLabel(truth)} · n = ${n} hours per model`}
      loading={loading} error={error} empty={!rows.length && `No pairs for this choice in ${FROZEN_WINDOW.label}. Try another truth or variable.`}
      height={360} onRetry={() => results.forEach((r) => r.refetch())}>
      <Chart option={option} height={360} label={`${info.label} forecast against actual for ${rows.map((r) => modelLabel(r.model)).join(', ')}`} />
    </ChartCard>
  );
}

function ErrorVsLead({ models, variable, truth }: { models: string[]; variable: string; truth: string }) {
  const { theme } = useTheme();
  const info = variableInfo(variable);
  const [metric, setMetric] = useState<LeadMetric>('mae');
  const { data, isLoading, error, refetch } = useLeadMetrics(truth);
  const rows = useMemo(() => (data ?? []).filter((r) => r.variable === variable && models.includes(r.model)), [data, variable, models]);
  const option = useMemo(() => errorVsLead(rows, models, metric, info, theme), [rows, models, metric, info, theme]);
  return (
    <ChartCard overline="Error vs lead time" title={`${metric.toUpperCase()} by lead`} info={GLOSSARY[metric]} className="lg:col-span-6"
      subtitle="Larger markers mean more hours" loading={isLoading} error={error} onRetry={refetch}
      empty={!rows.length && (variable === 'precipitation_mm' && truth === 'metar_wmki'
        ? "METAR reports rain as yes or no, not millimetres, so there's no rain error to show. Choose the Open-Meteo analysis instead."
        : 'No pairs for this choice.')}
      actions={<Segmented label="Metric" value={metric} onChange={setMetric}
        options={[{ value: 'mae', label: 'MAE' }, { value: 'bias', label: 'Bias' }, { value: 'rmse', label: 'RMSE' }]} />}>
      <Chart option={option} label={describeLead(rows, metric)} />
    </ChartCard>
  );
}

function Leaderboard({ truth }: { truth: string }) {
  const { data, isLoading, error, refetch } = useLeaderboard(truth);
  return (
    <ChartCard overline="Model leaderboard" title="Who wins for Seri Iskandar?" info={GLOSSARY.ml} className="lg:col-span-6"
      subtitle={`Leads of 24–144 h · truth: ${truthLabel(truth)}`} loading={isLoading} error={error} onRetry={refetch}
      empty={!data?.length && 'No pairs yet.'}>
      <MetricTable rows={data ?? []} columns={LEADERBOARD} rowKey={(r) => r.model} defaultSort="temp_mae" caption="Model leaderboard" />
      <p className="mt-2 text-xs text-muted">
        The ML model corrects Best Match's temperature, humidity, wind and pressure, and forecasts rain as yes or no.
        Its wind is flatter than real wind, so strong winds come out too weak.
      </p>
    </ChartCard>
  );
}

function NextDay() {
  const [lead, setLead] = useState(1);
  const { data, isLoading, error, refetch } = useNextDay(lead);
  return (
    <ChartCard overline="Next-day forecast" title="Daily temperature and rainfall" info={GLOSSARY.nextDay}
      subtitle="Best Match · truth: Open-Meteo analysis" loading={isLoading} error={error} onRetry={refetch} height={140}
      empty={!data?.length && 'No forecast days in this window.'}
      actions={<Segmented label="Days ahead" value={lead} onChange={setLead}
        options={[1, 2, 3].map((d) => ({ value: d, label: `${d} day${d > 1 ? 's' : ''} ahead` }))} />}>
      <MetricTable rows={data ?? []} columns={NEXT_DAY} rowKey={(r) => r.target_date} sortable={false} caption="Next-day forecast against observed" />
    </ChartCard>
  );
}

export default function Accuracy() {
  const { variable, truth, lead, models, update } = useAccuracyFilters();
  const shown = useMemo(() => models.filter((m) => m !== ML_MODEL || variable !== 'precipitation_mm'), [models, variable]);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-[28px] leading-tight font-semibold">Forecast accuracy</h1>
        <p className="text-muted">Retrieved forecasts against what happened, {FROZEN_WINDOW.label} 2026. Every chart uses this window.</p>
      </div>
      <FilterBar>
        <VariableTabs value={variable} onChange={(v) => update('var', v)} />
        <TruthSelect value={truth} onChange={(v) => update('truth', v)} />
        <LeadSlider value={lead} onChange={(v) => update('lead', String(v))} />
        <div className="w-full"><ModelChips selected={models} variable={variable} onChange={(m) => update('models', m.join(','))} /></div>
      </FilterBar>
      <ForecastVsActual models={shown} variable={variable} lead={lead} truth={truth} />
      <div className="grid gap-4 lg:grid-cols-12">
        <ErrorVsLead models={shown} variable={variable} truth={truth} />
        <Leaderboard truth={truth} />
      </div>
      <NextDay />
    </div>
  );
}
