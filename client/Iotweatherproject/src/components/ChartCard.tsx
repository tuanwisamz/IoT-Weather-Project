import type { ReactNode } from 'react';
import { Info, RotateCw, SearchX } from 'lucide-react';
import * as Popover from '@radix-ui/react-popover';
import { ApiError } from '../lib/supabase';

export function InfoPopover({ text }: { text: string }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="rounded p-0.5 text-muted hover:text-text" aria-label="What this means">
        <Info size={14} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content sideOffset={6} collisionPadding={12}
          className="z-30 max-w-72 rounded-lg border border-border bg-surface-2 p-3 text-[13px] text-text shadow-lg">
          {text}
          <Popover.Arrow className="fill-border" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

interface Props {
  overline?: string;
  title: string;
  subtitle?: ReactNode;
  info?: string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: string | false;
  height?: number;
  actions?: ReactNode;
  className?: string;
  children?: ReactNode;
}

function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const code = error instanceof ApiError ? error.code : null;
  return (
    <div className="flex flex-col items-start gap-2 py-6 text-[13px]" role="alert">
      <p>
        Couldn't load this card{code && <span className="ml-1 font-mono text-xs text-muted">({code})</span>}.
      </p>
      {onRetry && (
        <button type="button" onClick={onRetry}
          className="flex items-center gap-1.5 rounded-lg bg-surface-3 px-3 py-1.5 hover:text-gold-text">
          <RotateCw size={13} aria-hidden /> Try again
        </button>
      )}
    </div>
  );
}

export function ChartCard({ overline, title, subtitle, info, loading, error, onRetry, empty, height = 320, actions, className = '', children }: Props) {
  return (
    <section className={`min-w-0 rounded-xl border border-border bg-surface-1 p-5 ${className}`}>
      <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          {overline && <p className="eyebrow">{overline}</p>}
          <h2 className="flex items-center gap-1.5 text-base font-semibold">
            {title}
            {info && <InfoPopover text={info} />}
          </h2>
          {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
        </div>
        {actions}
      </header>
      {error ? <ErrorState error={error} onRetry={onRetry} />
        : loading ? <div className="skeleton" style={{ height }} />
          : empty ? (
            <p className="flex items-center gap-2 py-8 text-[13px] text-muted"><SearchX size={16} aria-hidden /> {empty}</p>
          ) : children}
    </section>
  );
}
