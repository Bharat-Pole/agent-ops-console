import { useEffect, useState, useCallback } from 'react';
import { CheckCircle2, XCircle, Loader2, Clock, ChevronRight } from 'lucide-react';
import type { RealPipelineRun, RealPipelineStage } from '@/types';
import { cn } from '@/utils/cn';

const STAGE_ORDER = ['fetch', 'parse', 'chunk', 'embed', 'store', 'finalize'] as const;

const STAGE_LABELS: Record<string, string> = {
  fetch: 'Fetch',
  parse: 'Parse',
  chunk: 'Chunk',
  embed: 'Embed',
  store: 'Store',
  finalize: 'Finalize',
};

function StageIcon({ status }: { status: RealPipelineStage['status'] }) {
  if (status === 'done') return <CheckCircle2 size={14} className="text-ok" />;
  if (status === 'error') return <XCircle size={14} className="text-err" />;
  if (status === 'running') return <Loader2 size={14} className="animate-spin text-warn" />;
  return <Clock size={13} className="text-border-strong" />;
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  if (total === 0) return null;
  const pct = Math.min(100, Math.round((done / total) * 100));
  return (
    <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-border">
      <div
        className="h-full rounded-full bg-accent transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

interface Props {
  runId: string;
  /** If true, polls every 2s until run completes */
  live?: boolean;
  onComplete?: (run: RealPipelineRun) => void;
}

export function PipelineRunDetail({ runId, live, onComplete }: Props) {
  const [run, setRun] = useState<RealPipelineRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchRun = useCallback(async () => {
    try {
      const res = await fetch(`/v1/knowledge/pipeline-runs/${encodeURIComponent(runId)}`);
      if (!res.ok) { setError('Failed to load run.'); return false; }
      const data = await res.json();
      setRun(data.run);
      return data.run.status !== 'running';
    } catch {
      setError('Network error.');
      return false;
    }
  }, [runId]);

  useEffect(() => {
    fetchRun();
  }, [fetchRun]);

  useEffect(() => {
    if (!live) return;
    const interval = setInterval(async () => {
      const done = await fetchRun();
      if (done) {
        clearInterval(interval);
        const res = await fetch(`/v1/knowledge/pipeline-runs/${encodeURIComponent(runId)}`);
        if (res.ok) {
          const data = await res.json();
          onComplete?.(data.run);
        }
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [live, runId, fetchRun, onComplete]);

  if (error) return <div className="text-[12px] text-err">{error}</div>;
  if (!run) return (
    <div className="flex items-center gap-2 text-[12px] text-text-low">
      <Loader2 size={12} className="animate-spin" /> Loading run…
    </div>
  );

  // The API doesn't guarantee row order — sort to the canonical pipeline sequence
  // so the stage boxes always read fetch -> parse -> chunk -> embed -> store -> finalize.
  const stages = [...(run.stages ?? [])].sort(
    (a, b) => STAGE_ORDER.indexOf(a.stage_name) - STAGE_ORDER.indexOf(b.stage_name),
  );

  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold text-text-hi uppercase tracking-wide">
          Pipeline Run
        </span>
        <span className={cn(
          'rounded-full px-2 py-0.5 text-[10px] font-semibold',
          run.status === 'success' ? 'bg-ok/15 text-ok' :
          run.status === 'error' ? 'bg-err/15 text-err' :
          'bg-warn/15 text-warn',
        )}>
          {run.status}
        </span>
      </div>

      {/* Stage pipeline */}
      <div className="flex items-stretch gap-0.5">
        {stages.map((stage, i) => (
          <div key={stage.id} className="flex flex-1 items-center">
            <div className={cn(
              'flex w-full flex-col rounded-md border px-2 py-1.5 transition-all',
              stage.status === 'done' ? 'border-ok/30 bg-ok/5' :
              stage.status === 'error' ? 'border-err/30 bg-err/5' :
              stage.status === 'running' ? 'border-warn/40 bg-warn/5' :
              'border-border bg-surface/40',
            )}>
              <div className="flex items-center gap-1">
                <StageIcon status={stage.status} />
                <span className="text-[11px] font-medium text-text-hi">
                  {STAGE_LABELS[stage.stage_name] ?? stage.stage_name}
                </span>
              </div>
              {stage.items_total > 0 && (
                <>
                  <span className="text-[9px] text-text-low">
                    {stage.items_done}/{stage.items_total}
                  </span>
                  <ProgressBar done={stage.items_done} total={stage.items_total} />
                </>
              )}
              {stage.error_msg && (
                <span className="mt-0.5 text-[9px] text-err line-clamp-2">{stage.error_msg}</span>
              )}
            </div>
            {i < stages.length - 1 && (
              <ChevronRight size={12} className="mx-0.5 shrink-0 text-border-strong" />
            )}
          </div>
        ))}
      </div>

      {/* Run-level error */}
      {run.status === 'error' && run.error_msg && (
        <div className="mt-2 rounded-md border border-err/30 bg-err/10 px-3 py-2 text-[11px] text-err">
          {run.error_msg}
        </div>
      )}

      {/* Timing */}
      {run.finished_at && (
        <div className="text-[10px] text-text-low">
          Finished {new Date(run.finished_at).toLocaleString()}
          {run.chunks_created > 0 && ` · ${run.chunks_created} chunks stored`}
        </div>
      )}
    </div>
  );
}
