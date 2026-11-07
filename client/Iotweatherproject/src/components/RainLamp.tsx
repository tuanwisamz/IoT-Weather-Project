import { CloudDrizzle, CloudOff, CloudRainWind, Sun, type LucideIcon } from 'lucide-react';
import type { RainLevel } from '../lib/types';

const LEVELS: Record<RainLevel, { word: string; color: string; Icon: LucideIcon }> = {
  CLEAR: { word: 'Clear', color: 'var(--ok)', Icon: Sun },
  WATCH: { word: 'Watch: rain possible', color: 'var(--watch)', Icon: CloudDrizzle },
  RAIN_LIKELY: { word: 'Rain likely within 1 h', color: 'var(--alert)', Icon: CloudRainWind },
  UNKNOWN: { word: 'No recent forecast', color: 'var(--unknown)', Icon: CloudOff },
};

export function RainLamp({ level }: { level: RainLevel }) {
  const { word, color, Icon } = LEVELS[level];
  return (
    <div className="flex items-center gap-4" aria-live="polite">
      <span className="grid size-[72px] shrink-0 place-items-center rounded-full border-2"
        style={{ borderColor: color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
        <Icon size={30} style={{ color }} aria-hidden />
      </span>
      <span className="text-xl font-medium">{word}</span>
    </div>
  );
}

export function RainBadge({ level }: { level: RainLevel }) {
  const { word, color } = LEVELS[level];
  return (
    <span className="flex items-center gap-1.5 text-[13px] text-muted" title={word}>
      <span className="size-3 rounded-full border-2" style={{ borderColor: color }} aria-hidden />
      <span className="hidden sm:inline">{word.split(':')[0]}</span>
    </span>
  );
}
