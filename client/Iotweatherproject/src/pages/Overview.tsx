import { useMemo } from 'react';
import { Chart } from '../charts/Chart';
import { next24h } from '../charts/options';
import { useTheme } from '../app/theme';
import { ChartCard } from '../components/ChartCard';
import { KpiTile } from '../components/KpiTile';
import { RainLamp } from '../components/RainLamp';
import { FROZEN_WINDOW, modelLabel } from '../lib/constants';
import { fmtAge, fmtCompass, fmtMYT, fmtNum, fmtPct, fmtSigned } from '../lib/fmt';
import { GLOSSARY } from '../lib/glossary';
import { useCollection, useKpis, useNext24, useNow, useRainStatus } from '../lib/queries';
import { wmo } from '../lib/wmo';

function NowCard() {
  const { data, isLoading, error, refetch } = useNow();
  const om = data?.find((r) => r.source === 'openmeteo_current');
  const metar = data?.find((r) => r.source === 'metar_wmki');
  const { label, Icon } = wmo(om?.weather_code ?? null);
  return (
    <ChartCard overline="Now · Seri Iskandar" title={label} info={GLOSSARY.actual} loading={isLoading} error={error}
      onRetry={refetch} empty={!om && 'No observations yet.'} height={170} className="lg:col-span-7">
      {om && (
        <>
          <div className="flex items-center gap-4">
            <p className="tnum text-[56px] leading-none font-light">{fmtNum(om.temperature_c)}°</p>
            <Icon size={36} className="text-muted" aria-hidden />
          </div>
          <dl className="tnum mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[13px] sm:grid-cols-4">
            {[
              ['Humidity', fmtPct(om.humidity_pct)],
              ['Wind', `${fmtNum(om.wind_speed_kmh)} km/h ${fmtCompass(om.wind_dir_deg)}`],
              ['Pressure', `${fmtNum(om.pressure_hpa, 0)} hPa`],
              ['Rain (15 min)', `${fmtNum(om.precipitation_mm)} mm`],
            ].map(([term, value]) => (
              <div key={term}>
                <dt className="text-xs text-muted">{term}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 border-t border-border pt-2 text-xs text-muted">
            {metar && <>Station check · METAR WMKI {fmtNum(metar.temperature_c, 0)}° {metar.is_raining ? 'rain' : 'no rain'} · </>}
            Updated {fmtMYT(om.observed_at, 'HH:mm')} MYT ({fmtAge(om.age_s)})
          </p>
        </>
      )}
    </ChartCard>
  );
}

function RainCard() {
  const { data, isLoading, error, refetch } = useRainStatus();
  return (
    <ChartCard overline="Rain indicator" title="Open-Meteo rain probability" info={GLOSSARY.rain} loading={isLoading}
      error={error} onRetry={refetch} height={170} className="lg:col-span-5">
      <RainLamp level={data?.level ?? 'UNKNOWN'} />
      <dl className="tnum mt-4 grid grid-cols-2 gap-2 text-[13px]">
        <div>
          <dt className="text-xs text-muted">Next hour</dt>
          <dd className="text-xl">{fmtPct(data?.prob_1h == null ? null : data.prob_1h * 100)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Next 3 hours (peak)</dt>
          <dd className="text-xl">{fmtPct(data?.prob_3h == null ? null : data.prob_3h * 100)}</dd>
        </div>
      </dl>
      {data && <p className="mt-3 text-xs text-muted">Forecast issued {fmtMYT(data.issued_at, 'EEE HH:mm')} MYT</p>}
    </ChartCard>
  );
}

function KpiRow() {
  const { data: k } = useKpis();
  const { data: w } = useCollection();
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      <KpiTile label="Report window" value="3" unit="days" to="/health" context={`Retrieved · ${FROZEN_WINDOW.label}`} />
      <KpiTile label="Live since" value={w?.live_since ? fmtMYT(w.live_since, 'EEE HH:mm') : '—'} to="/health"
        context={w?.live_samples != null ? `${w.live_samples} live sample${w.live_samples === 1 ? '' : 's'}` : undefined} />
      <KpiTile label="Temp MAE · 1 day ahead" value={fmtNum(k?.temperature?.mae, 2)} unit="°C" to="/accuracy" gold
        context={k?.temperature ? `Bias ${fmtSigned(k.temperature.bias)} · n = ${k.temperature.n}` : undefined} />
      <KpiTile label="Rain CSI · 1 day ahead" value={fmtNum(k?.rain?.csi, 2)} to="/accuracy?var=precipitation_mm"
        context={k?.rain ? `n = ${k.rain.n}` : undefined} />
      <KpiTile label="Best model (temp)" value={<span className="text-xl">{k?.best_model.temperature ? modelLabel(k.best_model.temperature) : '—'}</span>}
        to="/accuracy" context="Lowest MAE at 24–144 h" />
    </div>
  );
}

function Next24() {
  const { data, isLoading, error, refetch } = useNext24();
  const { theme } = useTheme();
  const option = useMemo(() => next24h(data ?? [], theme), [data, theme]);
  return (
    <ChartCard overline="Next 24 hours" title="Temperature and chance of rain" subtitle="Newest Best Match forecast · dashed: corrected by ML, still being checked at leads under 24 h"
      loading={isLoading} error={error} onRetry={refetch} height={310}
      empty={!data?.length && 'Waiting for a current forecast.'}>
      <Chart option={option} height={310} label={`Forecast for the next ${data?.length ?? 0} hours`} />
    </ChartCard>
  );
}

export default function Overview() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-[28px] leading-tight font-semibold">What's happening now, and how good is the forecast?</h1>
        <p className="text-muted">Live weather for Seri Iskandar, Perak, with forecast accuracy from the report window.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-12">
        <RainCard />
        <NowCard />
      </div>
      <KpiRow />
      <Next24 />
    </div>
  );
}
