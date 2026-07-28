import { Check, Loader2, XOctagon, Circle } from 'lucide-react';
import type { TrackStatus } from '@/types';
import { cn } from '@/utils/cn';

// Section 3.3 — StatusPill: ✔ ready | ⏳ provisioning/indexing | ✖ blocked | ○ not-started.
const MAP: Record<TrackStatus, { label: string; cls: string; icon: React.ReactNode }> = {
  ready: {
    label: 'ready',
    cls: 'text-ok bg-ok/12 border-ok/30',
    icon: <Check size={12} strokeWidth={3} />,
  },
  in_progress: {
    label: 'in progress',
    cls: 'text-warn bg-warn/12 border-warn/30',
    icon: <Loader2 size={12} className="animate-spin-slow" />,
  },
  blocked: {
    label: 'blocked',
    cls: 'text-err bg-err/12 border-err/30',
    icon: <XOctagon size={12} />,
  },
  not_started: {
    label: 'not started',
    cls: 'text-text-low bg-transparent border-border',
    icon: <Circle size={11} />,
  },
};

export function StatusPill({
  status,
  label,
  size = 'sm',
}: {
  status: TrackStatus;
  label?: string;
  size?: 'xs' | 'sm';
}) {
  const m = MAP[status];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded border font-medium whitespace-nowrap',
        m.cls,
        size === 'xs' ? 'px-1 py-0.5 text-[10px]' : 'px-1.5 py-0.5 text-[11px]',
      )}
    >
      {m.icon}
      {label ?? m.label}
    </span>
  );
}
