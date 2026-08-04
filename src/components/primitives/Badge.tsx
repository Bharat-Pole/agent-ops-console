import React from 'react';
import { cn } from '@/utils/cn';

type Tone = 'neutral' | 'accent' | 'ok' | 'warn' | 'err' | 'info' | 'muted';

const TONES: Record<Tone, string> = {
  neutral: 'bg-raised text-text-mid border-border',
  accent: 'bg-accent/15 text-accent border-accent/30',
  ok: 'bg-ok/15 text-ok border-ok/30',
  warn: 'bg-warn/15 text-warn border-warn/30',
  err: 'bg-err/15 text-err border-err/30',
  info: 'bg-info/15 text-info border-info/30',
  muted: 'bg-transparent text-text-low border-border',
};

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  mono?: boolean;
}

export function Badge({ tone = 'neutral', mono, className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium border whitespace-nowrap',
        TONES[tone],
        mono && 'mono',
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
