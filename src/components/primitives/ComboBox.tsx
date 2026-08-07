import { useId } from 'react';
import { cn } from '@/utils/cn';

export interface ComboOption {
  value: string;
  label?: string;
  hint?: string;
}

/**
 * Type-to-search picker over a known set, backed by a native <datalist>: you
 * get filtering, keyboard nav, and mobile support for free, and — unlike a
 * hard <select> — a value the list doesn't know can still be typed, which
 * matters when an asset was created outside the current page's cache.
 */
export function ComboBox({
  value,
  onChange,
  options,
  placeholder,
  disabled,
  emptyHint,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  options: ComboOption[];
  placeholder?: string;
  disabled?: boolean;
  emptyHint?: string;
  className?: string;
}) {
  const listId = useId();
  const known = options.some((o) => o.value === value);

  return (
    <div className={className}>
      <input
        className={cn(
          'h-8 w-full rounded-control border bg-canvas px-2 text-[12px] text-text-hi outline-none',
          value && !known ? 'border-amber-700' : 'border-border',
          'focus:border-border-strong disabled:opacity-50',
        )}
        list={listId}
        value={value}
        disabled={disabled}
        placeholder={placeholder ?? (options.length ? 'type to search…' : emptyHint)}
        onChange={(e) => onChange(e.target.value)}
      />
      <datalist id={listId}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.hint ? `${o.label ?? o.value} — ${o.hint}` : o.label ?? o.value}
          </option>
        ))}
      </datalist>
      {options.length === 0 && emptyHint && (
        <div className="mt-0.5 text-[10px] text-text-low">{emptyHint}</div>
      )}
      {value && !known && options.length > 0 && (
        <div className="mt-0.5 text-[10px] text-amber-400">
          not in the approved list — validation will reject it
        </div>
      )}
    </div>
  );
}
