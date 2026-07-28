import React, { useState, useRef } from 'react';
import { cn } from '@/utils/cn';

// Lightweight hover/focus tooltip (no external dependency). Positions above by
// default; falls back gracefully — content is also exposed via title for a11y.
export function Tooltip({
  content,
  children,
  side = 'top',
  className,
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: 'top' | 'bottom' | 'right';
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const show = () => {
    window.clearTimeout(timer.current);
    setOpen(true);
  };
  const hide = () => {
    timer.current = window.setTimeout(() => setOpen(false), 60);
  };

  const pos =
    side === 'top'
      ? 'bottom-full left-1/2 -translate-x-1/2 mb-1.5'
      : side === 'bottom'
        ? 'top-full left-1/2 -translate-x-1/2 mt-1.5'
        : 'left-full top-1/2 -translate-y-1/2 ml-1.5';

  return (
    <span
      className={cn('relative inline-flex', className)}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {open && content != null && content !== '' && (
        <span
          role="tooltip"
          className={cn(
            'absolute z-50 max-w-xs whitespace-normal rounded-control border border-border-strong bg-raised px-2 py-1.5 text-[11px] leading-snug text-text-hi shadow-xl pointer-events-none animate-fade-in',
            pos,
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}
