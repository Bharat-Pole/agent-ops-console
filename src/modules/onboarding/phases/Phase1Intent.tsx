import { useState } from 'react';
import { Card, Button, Badge } from '@/components/primitives';
import { ReviewCard, EngineTrace } from '@/components/domain';
import { TagInput } from '../TagInput';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { applyTierOverride } from '@/kernel/engine';
import type { CapabilityTier } from '@/types';
import { Loader2, Sparkles, ArrowRight, Wand2, Plus } from 'lucide-react';

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 text-[12px] font-medium text-text-mid">{children}</div>;
}

export function Phase1Intent({ draft, patch, goPhase }: PhaseProps) {
  const jobs = useWorkspace((s) => s.jobs);
  const pushToast = useWorkspace((s) => s.pushToast);
  // Real, DB-backed knowledge sources (Knowledge & RAG module) — was reading
  // the old client-only demo `sources` seed array, which suggested ids that
  // don't exist for real and can't actually be bound to an agent.
  const knowledgeSources = useWorkspace((s) => s.knowledgeSources);
  const sourceSuggestions = knowledgeSources.map((src) => ({ value: src.id, label: src.name }));
  const sourceLabel = (id: string) => knowledgeSources.find((src) => src.id === id)?.name ?? id;
  const toolIds = useWorkspace((s) => s.tools.map((t) => t.id));
  const synthesizing = jobs.some((j) => j.kind === 'synthesis' && j.entity_id === draft.id && (j.status === 'processing' || j.status === 'queued'));
  const intent = draft.intent;
  const setIntent = (p: Partial<typeof intent>) => patch((d) => ({ ...d, intent: { ...d.intent, ...p }, name: p.agent_name ?? d.name }));

  const [suggesting, setSuggesting] = useState(false);
  const [suggestions, setSuggestions] = useState<{ source_id: string; name: string; relevance: string; reason: string }[]>([]);

  const suggestSources = async () => {
    if (!intent.objective.trim()) { pushToast('warn', 'Enter an objective first.'); return; }
    setSuggesting(true);
    const result = await api.suggestSources(intent.objective);
    setSuggesting(false);
    setSuggestions(result.filter((r) => !(intent.data_sources ?? []).includes(r.source_id)));
    if (result.length === 0) pushToast('info', 'No matching sources found (or the suggestion call failed — see toast above).');
  };

  const addSuggested = (sourceId: string) => {
    setIntent({ data_sources: [...(intent.data_sources ?? []), sourceId] });
    setSuggestions((s) => s.filter((x) => x.source_id !== sourceId));
  };

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
            <div className="mb-1 flex items-center justify-between">
              <Label>Data sources</Label>
              <button
                type="button"
                onClick={() => void suggestSources()}
                disabled={suggesting}
                className="flex items-center gap-1 text-[11px] text-accent hover:underline disabled:opacity-50"
              >
                {suggesting ? <Loader2 size={11} className="animate-spin-slow" /> : <Wand2 size={11} />}
                {suggesting ? 'Ranking sources…' : 'Suggest from objective'}
              </button>
            </div>
            <TagInput value={intent.data_sources ?? []} onChange={(v) => setIntent({ data_sources: v })} placeholder="add a source, Enter…" suggestions={sourceSuggestions} labelFor={sourceLabel} />
            {suggestions.length > 0 && (
              <div className="mt-1.5 space-y-1">
                {suggestions.map((s) => (
                  <button
                    key={s.source_id}
                    type="button"
                    title={s.reason}
                    onClick={() => addSuggested(s.source_id)}
                    className="flex w-full items-center gap-2 rounded-control border border-border bg-raised/40 px-2 py-1 text-left hover:border-accent/40"
                  >
                    <Plus size={11} className="shrink-0 text-accent" />
                    <span className="flex-1 truncate text-[11px] text-text-hi">{s.name}</span>
                    <Badge tone={s.relevance === 'high' ? 'accent' : 'muted'}>{s.relevance}</Badge>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div>
            <Label>Tools</Label>
            <TagInput value={intent.tools ?? []} onChange={(v) => setIntent({ tools: v })} placeholder="add a tool, Enter…" suggestions={toolIds} />
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
              onConfirm={() => goPhase(2)}
              onOverrideTier={override}
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
