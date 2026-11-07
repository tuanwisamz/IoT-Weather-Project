import type { ReactNode } from 'react';
import * as Slider from '@radix-ui/react-slider';
import { LEAD_STOPS, ML_MODEL, MODELS, TRUTHS, VARIABLES } from '../lib/constants';
import { useTheme } from '../app/theme';

export function Segmented<T extends string | number>({ label, value, options, onChange }: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-0.5 rounded-lg bg-surface-3 p-0.5">
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-1 text-[13px] ${
            o.value === value ? 'bg-surface-1 font-medium text-text' : 'text-muted hover:text-text'}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const VariableTabs = ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
  <Segmented label="Variable" value={value} onChange={onChange}
    options={VARIABLES.map((v) => ({ value: v.code, label: v.label }))} />
);

export function ModelChips({ selected, onChange, variable }: {
  selected: string[];
  onChange: (models: string[]) => void;
  variable: string;
}) {
  const { theme } = useTheme();
  const toggle = (code: string) => {
    const next = selected.includes(code) ? selected.filter((m) => m !== code) : [...selected, code];
    if (next.length) onChange(MODELS.map((m) => m.code).filter((c) => next.includes(c)));
  };
  return (
    <div role="group" aria-label="Models" className="flex flex-wrap gap-1.5">
      {MODELS.map((m) => {
        const on = selected.includes(m.code);
        // The ML rain model forecasts yes or no, so it has no rain amounts to chart.
        const off = m.code === ML_MODEL && variable === 'precipitation_mm';
        return (
          <button key={m.code} type="button" aria-pressed={on} disabled={off} onClick={() => toggle(m.code)}
            title={off ? 'The ML model forecasts rain as yes or no, not millimetres' : undefined}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[13px] ${
              on ? 'border-gold bg-surface-3 text-text' : 'border-border text-muted hover:text-text'} ${off ? 'opacity-40' : ''}`}>
            <span className="h-0.5 w-3.5 rounded-full" aria-hidden
              style={{ borderTop: `2px ${m.dashed ? 'dashed' : 'solid'} ${on ? m[theme] : 'var(--text-muted)'}` }} />
            {m.label}
          </button>
        );
      })}
    </div>
  );
}

export function TruthSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-2 text-[13px] text-muted">
      Truth
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-border bg-surface-3 px-2 py-1 text-text">
        {TRUTHS.map((t) => <option key={t.code} value={t.code} title={t.note}>{t.label}</option>)}
      </select>
    </label>
  );
}

export function LeadSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex min-w-60 grow items-center gap-3 text-[13px] text-muted">
      <span className="whitespace-nowrap">Issued ≥ <span className="tnum text-text">{value} h</span> before</span>
      <Slider.Root className="relative flex h-5 grow touch-none items-center select-none" min={0} max={LEAD_STOPS.length - 1}
        step={1} value={[LEAD_STOPS.indexOf(value)]} onValueChange={([i]) => onChange(LEAD_STOPS[i])}>
        <Slider.Track className="relative h-1 grow rounded-full bg-surface-3">
          <Slider.Range className="absolute h-full rounded-full bg-gold" />
        </Slider.Track>
        <Slider.Thumb aria-label="Minimum lead time" aria-valuetext={`${value} hours`}
          className="block size-4 rounded-full border-2 border-gold bg-surface-1" />
      </Slider.Root>
    </div>
  );
}

export const FilterBar = ({ children }: { children: ReactNode }) => (
  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-surface-1 p-3">{children}</div>
);
