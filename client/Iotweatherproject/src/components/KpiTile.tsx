import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface Props {
  label: string;
  value: ReactNode;
  unit?: string;
  context?: ReactNode;
  to?: string;
  gold?: boolean;
}

export function KpiTile({ label, value, unit, context, to, gold }: Props) {
  const body = (
    <>
      <p className="eyebrow">{label}</p>
      <p className={`tnum mt-1 text-[28px] leading-tight ${gold ? 'text-gold-text' : ''}`}>
        {value}{unit && <span className="ml-1 text-sm text-muted">{unit}</span>}
      </p>
      {context && <p className="mt-1 text-xs text-muted">{context}</p>}
    </>
  );
  const style = 'block min-w-0 rounded-xl border border-border bg-surface-1 p-4';
  return to ? <Link to={to} className={`${style} hover:border-gold`}>{body}</Link> : <div className={style}>{body}</div>;
}
