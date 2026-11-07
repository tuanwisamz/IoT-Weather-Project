import { useMemo, useState } from 'react';
import { Archive, Radio } from 'lucide-react';
import { useTheme } from '../app/theme';
import { Chart } from '../charts/Chart';
import { uptime } from '../charts/options';
import { PALETTES } from '../charts/themes';
import { ChartCard } from '../components/ChartCard';
import { Segmented } from '../components/Filters';
import { MetricTable, type Column } from '../components/MetricTable';
import { StatusPill } from '../components/StatusPill';
import { FROZEN_WINDOW, STREAMS } from '../lib/constants';
import { fmtMYT, fmtPct } from '../lib/fmt';
import { GLOSSARY } from '../lib/glossary';
import { useCollection, useCoverage, useRuns, useUptime } from '../lib/queries';
import type { RunRow } from '../lib/types';

const JOBS = [
  { value: 'observe', label: 'observe' },
  { value: 'forecast', label: 'forecast' },
  { value: 'backfill', label: 'backfill' },
];

function Banner() {
  const { data: w, isLoading } = useCollection();
  if (isLoading || !w) return <div className="skeleton h-24" />;
  return (
    <section className="grid gap-3 rounded-xl border border-gold bg-surface-1 p-5 md:grid-cols-2">
      <div className="flex gap-3">
        <Archive size={18} className="mt-0.5 shrink-0 text-gold-text" aria-hidden />
        <div>
          <p className="font-medium">Report window: 3 days of retrieved data</p>
          <p className="text-[13px] text-muted">
            Wed 4 Nov 00:00 – Sat 7 Nov 00:00 MYT, from public archives ·{' '}
            {w.backfilled_samples.toLocaleString()} retrieved 15-min samples since 1 Nov
          </p>
        </div>
      </div>
      <div className="flex gap-3">
        <Radio size={18} className="mt-0.5 shrink-0 text-gold-text" aria-hidden />
        <div>
          <p className="font-medium">
            {w.live_since ? `Collecting live since ${fmtMYT(w.live_since, 'EEE d MMM, HH:mm')} MYT` : 'Live collection has not started'}
          </p>
          {w.live_since && (
            <p className="text-[13px] text-muted">
              {w.live_samples} of {w.live_expected_samples} expected samples
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function Uptime() {
  const { theme } = useTheme();
  const [job, setJob] = useState('observe');
  const { data: w } = useCollection();
  const { data, isLoading, error, refetch } = useUptime(w?.live_since ?? undefined);
  const rows = useMemo(() => (data ?? []).filter((r) => r.job === job), [data, job]);
  const option = useMemo(() => uptime(rows, theme), [rows, theme]);
  const p = PALETTES[theme];
  const expected = rows.reduce((sum, r) => sum + r.expected_runs, 0);
  const ran = rows.reduce((sum, r) => sum + r.success_runs + r.partial_runs, 0);
  return (
    <ChartCard overline="Daily uptime" title="Scheduled runs by outcome" info={GLOSSARY.uptime} height={260}
      subtitle={expected ? `${ran} of ${expected} expected runs · ${fmtPct((100 * ran) / expected)}` : undefined}
      loading={isLoading} error={error} onRetry={refetch} empty={!rows.length && `No scheduled ${job} runs yet.`}
      actions={<Segmented label="Job" value={job} onChange={setJob} options={JOBS} />}>
      <div className="mb-1 flex flex-wrap gap-3 text-xs text-muted">
        {[['Success', p.ok], ['Partial', p.watch], ['Failed', p.alert], ['Missing', p.missing]].map(([label, color]) => (
          <span key={label} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: color }} aria-hidden /> {label}
          </span>
        ))}
      </div>
      <Chart option={option} height={260} label={`Daily scheduled runs for ${job}`} />
    </ChartCard>
  );
}

function Coverage() {
  const { data, isLoading, error, refetch } = useCoverage();
  const dates = useMemo(() => [...new Set((data ?? []).map((r) => r.local_date))].sort(), [data]);
  const cell = (date: string, stream: string) => data?.find((r) => r.local_date === date && r.stream === stream);
  const inWindow = (d: string) => d >= FROZEN_WINDOW.fromDate && d < FROZEN_WINDOW.toDate;
  return (
    <ChartCard overline="Coverage" title="Data received per day" info={GLOSSARY.coverage}
      subtitle="Dates in bold are in the report window · B = retrieved or repaired" loading={isLoading} error={error}
      onRetry={refetch} height={140} empty={!data?.length && 'No data yet.'}>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-0.5 text-xs">
          <caption className="sr-only">Coverage per day and data stream</caption>
          <thead>
            <tr>
              <th scope="col" />
              {dates.map((d) => (
                <th key={d} scope="col" className={`px-1 pb-1 whitespace-nowrap ${inWindow(d) ? 'font-semibold text-text' : 'font-normal text-muted'}`}>
                  {fmtMYT(`${d}T12:00:00+08:00`, 'EEE d')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(STREAMS).map(([stream, label]) => (
              <tr key={stream}>
                <th scope="row" className="pr-3 text-left font-normal whitespace-nowrap text-muted">{label}</th>
                {dates.map((d) => {
                  const c = cell(d, stream);
                  const pct = c?.coverage_pct ?? 0;
                  return (
                    <td key={d} className="tnum rounded px-1 py-1.5 text-center" title={c ? `${c.received} of ${c.expected} · ${c.backfilled} retrieved or repaired` : undefined}
                      style={{ background: `color-mix(in srgb, var(--gold-500) ${Math.round(pct * 0.55)}%, var(--surface-3))` }}>
                      {fmtPct(pct)}{c?.backfilled ? ' B' : ''}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}

const RUNS: Column<RunRow>[] = [
  { key: 'started', label: 'Started (MYT)', align: 'left', value: (r) => r.started_at, render: (r) => <span className="font-mono text-xs">{fmtMYT(r.started_at, 'EEE d MMM HH:mm')}</span> },
  { key: 'job', label: 'Job', align: 'left', value: (r) => r.job },
  { key: 'trigger', label: 'Trigger', align: 'left', value: (r) => r.trigger },
  { key: 'status', label: 'Status', align: 'left', value: (r) => r.status, render: (r) => <StatusPill status={r.status} /> },
  { key: 'rows', label: 'Rows written', value: (r) => Object.values(r.rows_written).reduce((a, b) => a + b, 0) },
  {
    key: 'link', label: 'GitHub', value: () => null,
    render: (r) => (r.gh_run_id ? (
      <a className="underline hover:text-text" href={`https://github.com/tuanwisamz/IoT-Weather-Project/actions/runs/${r.gh_run_id}`}>run ↗</a>
    ) : '—'),
  },
];

function LatestRuns() {
  const { data, isLoading, error, refetch } = useRuns();
  return (
    <ChartCard overline="Latest runs" title="Run log" subtitle="The 50 newest job runs" loading={isLoading} error={error}
      onRetry={refetch} empty={!data?.length && 'No runs yet.'}>
      <MetricTable rows={data ?? []} columns={RUNS} rowKey={(r) => r.id} caption="Latest job runs" sortable={false} />
    </ChartCard>
  );
}

export default function Health() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-[28px] leading-tight font-semibold">Data health</h1>
        <p className="text-muted">Where the data came from, and whether collection is still running.</p>
      </div>
      <Banner />
      <Coverage />
      <Uptime />
      <LatestRuns />
    </div>
  );
}
