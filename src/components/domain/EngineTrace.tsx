import { useState } from 'react';
import type { EngineTrace as EngineTraceT } from '@/kernel/engine';
import { JsonViewer } from '@/components/primitives';
import { ChevronDown, ChevronRight, Cpu } from 'lucide-react';

// Section 9.3 — "Engine trace" expander shows all 7 stages' raw outputs
// (acceptance #2: the engine trace shows raw scores).
const STAGES: { key: keyof EngineTraceT; label: string }[] = [
  { key: 'stage1_nlu', label: 'Stage 1 — Intake & Normalize' },
  { key: 'stage2_classification', label: 'Stage 2 — Archetype classification (raw scores)' },
  { key: 'stage3_synthesis', label: 'Stage 3 — Architecture synthesis' },
  { key: 'stage3b_writeDetect', label: 'Stage 3b — Write-action detection' },
  { key: 'stage4_confidence', label: 'Stage 4 — Confidence & provenance' },
  { key: 'stage5_elicitation', label: 'Stage 5 — Targeted elicitation' },
  { key: 'stage6_reviewCard', label: 'Stage 6 — Review card' },
  { key: 'stage7_evalGen', label: 'Stage 7 — Validation & certification' },
];

export function EngineTrace({ trace }: { trace: EngineTraceT }) {
  const [open, setOpen] = useState(false);
  const [openStage, setOpenStage] = useState<string | null>('stage2_classification');

  return (
    <div className="rounded-card border border-border bg-surface">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2 px-3 py-2.5 text-left">
        {open ? <ChevronDown size={14} className="text-text-low" /> : <ChevronRight size={14} className="text-text-low" />}
        <Cpu size={14} className="text-info" />
        <span className="text-[13px] font-semibold text-text-hi">Engine trace</span>
        <span className="text-[11px] text-text-low">all 7 stages, raw output</span>
      </button>
      {open && (
        <div className="border-t border-border p-2">
          {STAGES.map((s) => {
            const isOpen = openStage === s.key;
            return (
              <div key={s.key} className="mb-1">
                <button onClick={() => setOpenStage(isOpen ? null : s.key)} className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-[12px] text-text-mid hover:bg-raised">
                  {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  {s.label}
                </button>
                {isOpen && <div className="px-2 pb-2"><JsonViewer data={trace[s.key]} maxHeight={280} /></div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
