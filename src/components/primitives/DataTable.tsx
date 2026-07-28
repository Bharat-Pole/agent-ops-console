import React, { useMemo, useState } from 'react';
import { ArrowUp, ArrowDown, Search } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number;
  width?: string;
  align?: 'left' | 'right' | 'center';
  className?: string;
}

export interface FilterDef<T> {
  key: string;
  label: string;
  options: { value: string; label: string }[];
  predicate: (row: T, value: string) => boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  searchText?: (row: T) => string;
  searchPlaceholder?: string;
  filters?: FilterDef<T>[];
  toolbarRight?: React.ReactNode;
  empty?: React.ReactNode;
  loading?: boolean;
  initialSort?: { key: string; dir: 'asc' | 'desc' };
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  searchText,
  searchPlaceholder = 'Search…',
  filters = [],
  toolbarRight,
  empty,
  loading,
  initialSort,
}: DataTableProps<T>) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(initialSort ?? null);
  const [filterVals, setFilterVals] = useState<Record<string, string>>({});

  const filtered = useMemo(() => {
    let out = rows;
    if (query && searchText) {
      const q = query.toLowerCase();
      out = out.filter((r) => searchText(r).toLowerCase().includes(q));
    }
    for (const f of filters) {
      const v = filterVals[f.key];
      if (v) out = out.filter((r) => f.predicate(r, v));
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col?.sortValue) {
        const sv = col.sortValue;
        out = [...out].sort((a, b) => {
          const av = sv(a);
          const bv = sv(b);
          const cmp = av < bv ? -1 : av > bv ? 1 : 0;
          return sort.dir === 'asc' ? cmp : -cmp;
        });
      }
    }
    return out;
  }, [rows, query, searchText, filters, filterVals, sort, columns]);

  const toggleSort = (key: string) => {
    setSort((s) => {
      if (!s || s.key !== key) return { key, dir: 'asc' };
      if (s.dir === 'asc') return { key, dir: 'desc' };
      return null;
    });
  };

  const hasToolbar = !!searchText || filters.length > 0 || !!toolbarRight;

  return (
    <div className="rounded-card border border-border bg-surface">
      {hasToolbar && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          {searchText && (
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-low" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                className="h-8 w-64 rounded-control border border-border bg-canvas pl-7 pr-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring"
              />
            </div>
          )}
          {filters.map((f) => (
            <select
              key={f.key}
              value={filterVals[f.key] ?? ''}
              onChange={(e) => setFilterVals((v) => ({ ...v, [f.key]: e.target.value }))}
              className="h-8 rounded-control border border-border bg-canvas px-2 text-[13px] text-text-mid focus-ring"
            >
              <option value="">{f.label}: all</option>
              {f.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {f.label}: {o.label}
                </option>
              ))}
            </select>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <span className="text-[11px] text-text-low">{filtered.length} rows</span>
            {toolbarRight}
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-border text-left">
              {columns.map((c) => (
                <th
                  key={c.key}
                  style={{ width: c.width }}
                  className={cn(
                    'px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-text-low',
                    c.align === 'right' && 'text-right',
                    c.align === 'center' && 'text-center',
                  )}
                >
                  {c.sortValue ? (
                    <button
                      onClick={() => toggleSort(c.key)}
                      className="inline-flex items-center gap-1 hover:text-text-mid"
                    >
                      {c.header}
                      {sort?.key === c.key &&
                        (sort.dir === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="border-b border-border/60">
                  {columns.map((c) => (
                    <td key={c.key} className="px-3 py-2.5">
                      <div className="skeleton h-3.5 w-full max-w-[140px]" />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading &&
              filtered.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    'border-b border-border/60 last:border-0 transition',
                    onRowClick && 'cursor-pointer hover:bg-raised',
                  )}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cn(
                        'px-3 py-2.5 text-text-mid align-middle',
                        c.align === 'right' && 'text-right',
                        c.align === 'center' && 'text-center',
                        c.className,
                      )}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {!loading && filtered.length === 0 && (
        <div className="p-4">
          {empty ?? <div className="py-8 text-center text-[13px] text-text-low">No matching rows.</div>}
        </div>
      )}
    </div>
  );
}
