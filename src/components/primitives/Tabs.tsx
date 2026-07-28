import React from 'react';
import { cn } from '@/utils/cn';

export interface TabItem {
  key: string;
  label: React.ReactNode;
  count?: number;
}

// Presentational tab bar. Pages sync `active` to the URL for deep-linking
// (acceptance #12).
export function Tabs({
  items,
  active,
  onChange,
  className,
}: {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  return (
    <div className={cn('flex items-center gap-1 border-b border-border', className)}>
      {items.map((it) => {
        const on = it.key === active;
        return (
          <button
            key={it.key}
            onClick={() => onChange(it.key)}
            className={cn(
              'relative -mb-px px-3 py-2 text-[13px] font-medium transition',
              on ? 'text-text-hi' : 'text-text-low hover:text-text-mid',
            )}
          >
            <span className="inline-flex items-center gap-1.5">
              {it.label}
              {it.count !== undefined && (
                <span
                  className={cn(
                    'rounded px-1 text-[10px]',
                    on ? 'bg-accent/20 text-accent' : 'bg-raised text-text-low',
                  )}
                >
                  {it.count}
                </span>
              )}
            </span>
            {on && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-accent" />}
          </button>
        );
      })}
    </div>
  );
}
