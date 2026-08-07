import { Card, Button } from '@/components/primitives';
import { ReviewCard, EngineTrace } from '@/components/domain';
import { TagInput } from '../TagInput';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { applyTierOverride, applyArchitectureOverride } from '@/kernel/engine';
import type { CapabilityTier, Architecture } from '@/types';
import { Loader2, Sparkles, ArrowRight } from 'lucide-react';

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 text-[12px] font-medium text-text-mid">{children}</div>;
}

export function Phase1Intent({ draft, patch, goPhase }: PhaseProps) {
  const jobs = useWorkspace((s) => s.jobs);
  const pushToast = useWorkspace((s) => s.pushToast);
  const synthesizing = jobs.some((j) => j.kind === 'synthesis' && j.entity_id === draft.id && (j.status === 'processing' || j.status === 'queued'));
  const intent = draft.intent;
  const setIntent = (p: Partial<typeof intent>) => patch((d) => ({ ...d, intent: { ...d.intent, ...p }, name: p.agent_name ?? d.name }));

  const generate = () => {
    if (!intent.objective.trim()) { pushToast('warn', 'Enter an objective first.'); return; }
    patch((d) => ({ ...d, synthesis: null }));
    api.synthesize(draft.id);
  };

  const override = (tier: CapabilityTier) => {
    const res = applyTierOverride(draft.intent, tier);
    if (res.accepted && res.result) {
      patch((d) => ({ ...d, synthesis: res.result!, confirmedTier: res.result!.capability_tier, confirmedRisk: res.result!.risk_tier }));
      pushToast('ok', res.note);
    } else {
      pushToast('warn', res.note);
    }
  };

  const overrideArch = (a: Architecture) => {
    const res = applyArchitectureOverride(draft.intent, a);
    if (res.accepted && res.result) {
      patch((d) => ({ ...d, synthesis: res.result!, confirmedArchitecture: res.result!.architecture }));
      pushToast('ok', res.note);
    } else {
      pushToast('warn', res.note);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <div className="mb-3 text-[13px] font-semibold text-text-hi">Phase 1 · Capture Intent</div>
        <div className="space-y-3">
          <div>
            <Label>Agent name</Label>
            <input value={intent.agent_name ?? ''} onChange={(e) => setIntent({ agent_name: e.target.value })} placeholder="e.g. Incident Summarizer" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          </div>
          <div>
            <Label>Objective</Label>
            <textarea value={intent.objective} onChange={(e) => setIntent({ objective: e.target.value })} rows={4} placeholder="Describe what this agent should do, and from what data…" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          </div>
          <div>
            <Label>Intended audience</Label>
            <input value={intent.intended_audience ?? ''} onChange={(e) => setIntent({ intended_audience: e.target.value })} placeholder="e.g. NOC team" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          </div>
          <div>
            <Label>Data sources</Label>
            <TagInput value={intent.data_sources ?? []} onChange={(v) => setIntent({ data_sources: v })} placeholder="add a source, Enter…" />
          </div>
          <div>
            <Label>Tools</Label>
            <TagInput value={intent.tools ?? []} onChange={(v) => setIntent({ tools: v })} placeholder="add a tool, Enter…" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label>Business owner</Label>
              <input value={intent.business_owner ?? ''} onChange={(e) => setIntent({ business_owner: e.target.value })} placeholder="owner@brightspeed.com" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
            </div>
            <div>
              <Label>Technical owner</Label>
              <input value={intent.technical_owner ?? ''} onChange={(e) => setIntent({ technical_owner: e.target.value })} placeholder="eng@brightspeed.com" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
            </div>
          </div>
          <Button variant="primary" icon={synthesizing ? <Loader2 size={14} className="animate-spin-slow" /> : <Sparkles size={14} />} onClick={generate} disabled={synthesizing}>
            {synthesizing ? 'Draft generating…' : 'Generate proposal'}
          </Button>
        </div>
      </Card>

      <div className="space-y-4">
        {synthesizing && (
          <Card className="flex items-center gap-3">
            <Loader2 size={18} className="animate-spin-slow text-accent" />
            <span className="text-[13px] text-text-mid">Running the objective-to-architecture synthesis engine…</span>
          </Card>
        )}
        {!synthesizing && draft.synthesis && (
          <>
            <ReviewCard
              card={draft.synthesis.review_card}
              architecture={draft.synthesis.trace.stage2b_architecture}
              recommending={draft.archRecommending}
              onConfirm={() => goPhase(2)}
              onOverrideTier={override}
              onOverrideArchitecture={overrideArch}
              onEdit={() => patch((d) => ({ ...d, synthesis: null }))}
              confirmLabel="Confirm & continue →"
            />
            <EngineTrace trace={draft.synthesis.trace} />
          </>
        )}
        {!synthesizing && !draft.synthesis && (
          <Card className="flex h-full flex-col items-center justify-center py-12 text-center">
            <ArrowRight size={22} className="mb-2 text-text-low" />
            <div className="text-[13px] text-text-mid">Fill the intent and click <b>Generate proposal</b>.</div>
            <div className="mt-1 text-[12px] text-text-low">The engine proposes a tier, archetype, config, and governance path — all deterministic.</div>
          </Card>
        )}
      </div>
    </div>
  );
}
