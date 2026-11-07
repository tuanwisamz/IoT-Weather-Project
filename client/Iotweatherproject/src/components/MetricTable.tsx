import { useMemo, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, Star } from 'lucide-react';

export interface Column<T> {
  key: string;
  label: string;
  value: (row: T) => number | string | null;
  render?: (row: T) => ReactNode;
  align?: 'left' | 'right';
  // 'low' or 'high' stars the best value in this column.
  best?: 'low' | 'high';
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  defaultSort?: string;
  sortable?: boolean;
  caption: string;
}

export function MetricTable<T>({ rows, columns, rowKey, defaultSort, sortable = true, caption }: Props<T>) {
  const [sort, setSort] = useState({ key: defaultSort ?? '', asc: true });

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    return [...rows].sort((a, b) => {
      const x = col.value(a);
      const y = col.value(b);
      if (x == null) return 1;
      if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * (sort.asc ? 1 : -1);
    });
  }, [rows, columns, sort]);

  const bests = useMemo(() => Object.fromEntries(columns.filter((c) => c.best).map((c) => {
    const values = rows.map(c.value).filter((v): v is number => typeof v === 'number');
    return [c.key, c.best === 'low' ? Math.min(...values) : Math.max(...values)];
  })), [rows, columns]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border text-xs text-muted">
            {columns.map((c) => {
              const active = sort.key === c.key;
              const align = c.align === 'left' ? 'text-left' : 'text-right';
              return (
                <th key={c.key} scope="col" className={`whitespace-nowrap px-2 py-2 font-medium ${align}`}
                  aria-sort={active ? (sort.asc ? 'ascending' : 'descending') : undefined}>
                  {sortable ? (
                    <button type="button" className="inline-flex items-center gap-1 hover:text-text"
                      onClick={() => setSort({ key: c.key, asc: active ? !sort.asc : true })}>
                      {c.label}
                      {active && (sort.asc ? <ArrowUp size={11} aria-hidden /> : <ArrowDown size={11} aria-hidden />)}
                    </button>
                  ) : c.label}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)} className="border-b border-border last:border-0 hover:bg-surface-2">
              {columns.map((c) => {
                const value = c.value(row);
                const best = c.best && value === bests[c.key];
                const align = c.align === 'left' ? 'text-left' : 'tnum text-right';
                return (
                  <td key={c.key} className={`whitespace-nowrap px-2 py-2 ${align} ${best ? 'font-medium text-gold-text' : ''}`}>
                    {best && <Star size={11} className="mr-1 inline align-[-1px]" fill="currentColor" aria-label="Best" />}
                    {c.render ? c.render(row) : value ?? '—'}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
