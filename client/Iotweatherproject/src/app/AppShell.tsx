import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { CalendarRange, Moon, Sun } from 'lucide-react';
import { FROZEN_WINDOW } from '../lib/constants';
import { useNow, useRainStatus } from '../lib/queries';
import { fmtAge } from '../lib/fmt';
import { RainBadge } from '../components/RainLamp';
import { useTheme } from './theme';

const TABS = [
  { to: '/', label: 'Overview' },
  { to: '/accuracy', label: 'Accuracy' },
  { to: '/health', label: 'Data Health' },
];

function Freshness() {
  const { data } = useNow();
  const row = data?.find((r) => r.source === 'openmeteo_current');
  if (!row) return null;
  const tone = row.age_s < 1800 ? 'bg-ok' : row.age_s < 3600 ? 'bg-watch' : 'bg-alert';
  return (
    <span className="flex items-center gap-1.5 text-[13px] text-muted" title="Age of the latest observation">
      <span className={`size-2 rounded-full ${tone}`} aria-hidden />
      {fmtAge(row.age_s)}
    </span>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme();
  const { data: rain } = useRainStatus();

  return (
    <div className="flex min-h-dvh flex-col bg-bg text-text">
      <header className="sticky top-0 z-20 border-b border-border bg-surface-1">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-1 px-4 py-2 md:px-6">
          <span className="font-display text-lg font-semibold tracking-tight">IoT Weather Project</span>
          <nav className="flex gap-1" aria-label="Pages">
            {TABS.map((tab) => (
              <NavLink key={tab.to} to={tab.to} end={tab.to === '/'}
                className={({ isActive }) => `border-b-2 px-3 py-2 text-[13px] font-medium ${
                  isActive ? 'border-gold text-text' : 'border-transparent text-muted hover:text-text'}`}>
                {tab.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4">
            <span className="hidden items-center gap-1.5 text-[13px] text-muted md:flex">
              <CalendarRange size={14} aria-hidden /> {FROZEN_WINDOW.label} · report window
            </span>
            <Freshness />
            <RainBadge level={rain?.level ?? 'UNKNOWN'} />
            <button type="button" onClick={toggle} className="rounded-lg p-1.5 text-muted hover:bg-surface-3 hover:text-text"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 md:px-6">{children}</main>

      <footer className="border-t border-border px-4 py-4 text-center text-xs text-muted">
        Weather data by Open-Meteo.com (CC BY 4.0) · METAR NOAA AWC · Times in MYT (UTC+8) ·{' '}
        <a className="underline hover:text-text" href="https://github.com/tuanwisamz/IoT-Weather-Project">GitHub</a>
      </footer>
    </div>
  );
}
