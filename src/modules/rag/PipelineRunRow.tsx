import { Badge } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { type PipelineRun } from '@/types';
import { titleCase } from '@/utils/format';
import { Loader2, CheckCircle2, Circle } from 'lucide-react';
import { cn } from '@/utils/cn';

export function StageDot({ status }: { status: PipelineRun['stages'][number]['status'] }) {
  if (status === 'ready') return <CheckCircle2 size={14} className="text-ok" />;
  if (status === 'in_progress') return <Loader2 size={14} className="animate-spin-slow text-warn" />;
  return <Circle size={12} className="text-border-strong" />;
}

export function PipelineRunRow({ run, compact }: { run: PipelineRun; compact?: boolean }) {
  const sources = useWorkspace((s) => s.sources);
  const src = sources.find((s) => s.id === run.source_id);
  return (
    <div className={cn('rounded-card border border-border bg-surface p-3', !compact && 'mb-2')}>
      <div className="mb-2 flex items-center justify-between text-[12px]">
        <span className="font-medium text-text-hi">{src?.name ?? run.source_id} <span className="mono text-[10px] text-text-low">· {run.trigger}</span></span>
        <Badge tone={run.overall === 'ready' ? 'ok' : run.overall === 'in_progress' ? 'warn' : 'neutral'}>{titleCase(run.overall)}</Badge>
      </div>
      <div className="flex items-center gap-1 overflow-x-auto">
        {run.stages.map((st, i) => (
          <div key={st.name} className="flex items-center">
            <div className="flex min-w-[74px] flex-col items-center rounded border border-border/60 px-1.5 py-1">
              <StageDot status={st.status} />
              <span className="mt-0.5 text-[10px] text-text-mid">{st.name}</span>
              {st.items != null && <span className="text-[9px] text-text-low">{st.items.toLocaleString()}</span>}
            </div>
            {i < run.stages.length - 1 && <span className="mx-0.5 text-text-low">›</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
