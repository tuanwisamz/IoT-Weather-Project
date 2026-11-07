import { AlertTriangle, Check, Loader, X, type LucideIcon } from 'lucide-react';

const STATUS: Record<string, { color: string; Icon: LucideIcon }> = {
  success: { color: 'var(--ok)', Icon: Check },
  partial: { color: 'var(--watch)', Icon: AlertTriangle },
  failed: { color: 'var(--alert)', Icon: X },
  running: { color: 'var(--unknown)', Icon: Loader },
};

export function StatusPill({ status }: { status: string }) {
  const { color, Icon } = STATUS[status] ?? STATUS.running;
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs text-text"
      style={{ background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
      <Icon size={12} style={{ color }} aria-hidden /> {status}
    </span>
  );
}
