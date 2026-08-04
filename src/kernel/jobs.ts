// Section 6.2 — the async job queue simulation. All long operations create a Job
// and advance via setTimeout chains, emitting store updates on each transition so
// status pills animate live. A tiny job tray in the TopBar reflects active jobs.

import { ws } from './store';
import type { Job, JobKind } from '@/types';
import { latency } from './rng';

export interface JobStep {
  label: string;
  ms: number;
  onStep?: () => void; // mutate store as this step completes (e.g., advance a track sub-step)
}

// Start a multi-step job. Returns the job id; resolves the returned promise when
// the job completes (or is left running — caller may ignore).
export function startJob(
  kind: JobKind,
  label: string,
  entityId: string,
  steps: JobStep[],
  onComplete?: () => void,
): { id: string; done: Promise<void> } {
  const store = ws();
  const id = store.nextId('job');
  const job: Job = {
    id,
    kind,
    label,
    entity_id: entityId,
    status: 'queued',
    progress: 0,
    step_label: steps[0]?.label ?? null,
    result: null,
    created_at: new Date().toISOString(),
  };
  store.upsertJob(job);

  const done = new Promise<void>((resolve) => {
    let i = 0;
    const runNext = () => {
      if (i >= steps.length) {
        ws().updateJob(id, { status: 'completed', progress: 1, step_label: 'done' });
        onComplete?.();
        // auto-clear finished jobs from the tray after a moment
        window.setTimeout(() => ws().removeJob(id), 2500);
        resolve();
        return;
      }
      const step = steps[i];
      ws().updateJob(id, { status: 'processing', step_label: step.label, progress: i / steps.length });
      window.setTimeout(() => {
        try {
          step.onStep?.();
        } catch {
          /* ignore step errors in the simulation */
        }
        ws().updateJob(id, { progress: (i + 1) / steps.length });
        i += 1;
        runNext();
      }, step.ms);
    };
    // small initial queue delay
    window.setTimeout(runNext, latency(150, 400));
  });

  return { id, done };
}

// Convenience: a single-shot job (one processing phase then complete).
export function startSimpleJob(kind: JobKind, label: string, entityId: string, ms: number, onComplete?: () => void) {
  return startJob(kind, label, entityId, [{ label: 'processing', ms }], onComplete);
}
