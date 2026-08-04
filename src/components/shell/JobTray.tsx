import { useState, useRef, useEffect } from 'react';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { useWorkspace } from '@/kernel/store';
import { cn } from '@/utils/cn';

// Section 6.2 — a tiny job tray in the TopBar (spinner + count) listing active jobs.
export function JobTray() {
  const jobs = useWorkspace((s) => s.jobs);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'processing');
  const recent = jobs.slice(-8).reverse();

  if (jobs.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-control border px-2.5 py-1.5 text-[12px]',
          active.length > 0
            ? 'border-accent/40 bg-accent/10 text-accent'
            : 'border-border text-text-mid hover:bg-raised',
        )}
      >
        {active.length > 0 ? (
          <Loader2 size={14} className="animate-spin-slow" />
        ) : (
          <CheckCircle2 size={14} className="text-ok" />
        )}
        {active.length > 0 ? `${active.length} running` : 'jobs'}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-1 w-80 overflow-hidden rounded-card border border-border-strong bg-raised shadow-2xl animate-fade-in">
          <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-text-low">
            Job queue
          </div>
          <div className="max-h-80 overflow-auto">
            {recent.map((j) => (
              <div key={j.id} className="flex items-center gap-2 border-t border-border px-3 py-2">
                {j.status === 'processing' || j.status === 'queued' ? (
                  <Loader2 size={14} className="animate-spin-slow text-accent shrink-0" />
                ) : j.status === 'completed' ? (
                  <CheckCircle2 size={14} className="text-ok shrink-0" />
                ) : (
                  <XCircle size={14} className="text-err shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px] text-text-hi">{j.label}</div>
                  <div className="truncate text-[11px] text-text-low">
                    {j.step_label ?? j.status}
                  </div>
                </div>
                {(j.status === 'processing' || j.status === 'queued') && (
                  <div className="h-1 w-14 shrink-0 overflow-hidden rounded-full bg-canvas">
                    <div
                      className="h-full rounded-full bg-accent transition-all"
                      style={{ width: `${Math.round(j.progress * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
