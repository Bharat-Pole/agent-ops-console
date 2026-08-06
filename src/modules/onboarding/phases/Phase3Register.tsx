import { useState } from 'react';
import { Card, Button, Badge } from '@/components/primitives';
import { ReviewCard } from '@/components/domain';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { synthesize, applyTierOverride } from '@/kernel/engine';
import type { CapabilityTier } from '@/types';
import { CheckCircle2, ArrowRight, ArrowLeft, ClipboardCheck, Loader2 } from 'lucide-react';
import { cn } from '@/utils/cn';

export function Phase3Register({ draft, patch, goPhase }: PhaseProps) {
  const pushToast = useWorkspace((s) => s.pushToast);
  const registeredAgent = useWorkspace((s) => s.agents.find((a) => a.config.identity.agent_id.value === draft.agent_id));
  const [registering, setRegistering] = useState(false);

  if (!draft.synthesis) {
    return <Card><div className="text-[13px] text-text-mid">Generate a proposal in Phase 1 first.</div><Button className="mt-3" variant="ghost" onClick={() => goPhase(1)}>← Back to Phase 1</Button></Card>;
  }

  const questions = draft.synthesis.elicitation.questions;
  const answered = questions.filter((q) => draft.elicitationAnswers[q.id]).length;

  const answer = (qid: string, value: string, affects: string) => {
    patch((d) => ({ ...d, elicitationAnswers: { ...d.elicitationAnswers, [qid]: value } }));
    // Risk-affecting answers re-run the engine so the review card updates live.
    if (affects.includes('risk_tier') || affects.includes('tool_permission')) {
      const sensitivity = /pii|personal/i.test(value) ? 'confidential' : /regulated|cross-border/i.test(value) ? 'restricted' : 'internal';
      const nextIntent = { ...draft.intent, data_sensitivity: sensitivity };
      const result = synthesize(nextIntent);
      patch((d) => ({ ...d, intent: nextIntent, synthesis: result, confirmedRisk: result.risk_tier, confirmedTier: result.capability_tier }));
    }
  };

  const override = (tier: CapabilityTier) => {
    const res = applyTierOverride(draft.intent, tier);
    if (res.accepted && res.result) { patch((d) => ({ ...d, synthesis: res.result!, confirmedTier: res.result!.capability_tier, confirmedRisk: res.result!.risk_tier })); pushToast('ok', res.note); }
    else pushToast('warn', res.note);
  };

  const register = async () => {
    setRegistering(true);
    const id = await api.register(draft.id);
    setRegistering(false);
    if (id) goPhase(4);
  };

  if (registeredAgent) {
    return (
      <Card>
        <div className="flex items-center gap-2 text-[14px] font-semibold text-ok"><CheckCircle2 size={18} /> Registered</div>
        <p className="mt-2 text-[13px] text-text-mid">
          {draft.name} is registered as <span className="mono">{registeredAgent.config.identity.agent_id.value}</span> with governance path{' '}
          <Badge tone="accent">{registeredAgent.governance_path}</Badge>. Approval items were created; the Registry track completes when approvals are granted.
        </p>
        <div className="mt-4 flex gap-2">
          <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => goPhase(4)}>Next: Configure Workflow</Button>
          <Button variant="ghost" onClick={() => goPhase(3)}>Stay</Button>
        </div>
      </Card>
    );
  }

  return (
    <div>
      <div className="mb-3 text-[13px] font-semibold text-text-hi">Phase 3 · Register</div>
      <div className="grid grid-cols-2 gap-4">
      <div className="space-y-4">
        <ReviewCard card={draft.synthesis.review_card} onOverrideTier={override} />
      </div>
      <div className="space-y-4">
        {questions.length > 0 && (
          <Card>
            <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-text-hi"><ClipboardCheck size={15} className="text-accent" /> Targeted clarifications <span className="text-[11px] font-normal text-text-low">(max 3)</span></div>
            <p className="mb-3 text-[12px] text-text-low">Only questions that change tier, risk, or a low-confidence field are asked.</p>
            <div className="space-y-3">
              {questions.map((q) => (
                <div key={q.id}>
                  <div className="mb-1 text-[12px] text-text-hi">{q.question}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {q.options.map((o) => (
                      <button key={o} onClick={() => answer(q.id, o, q.affects)} className={cn('rounded-control border px-2.5 py-1 text-[12px]', draft.elicitationAnswers[q.id] === o ? 'border-accent bg-accent/15 text-accent' : 'border-border text-text-mid hover:border-border-strong')}>
                        {o}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {draft.synthesis.elicitation.optional.length > 0 && (
              <div className="mt-3 text-[11px] text-text-low">+ {draft.synthesis.elicitation.optional.length} optional clarification(s) available later.</div>
            )}
          </Card>
        )}

        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Register agent</div>
          <p className="mb-3 text-[12px] text-text-low">
            Creates the AgentRecord, approval items per governance path, an auto-generated eval pack, and audit events.
            {questions.length > 0 && ` ${answered}/${questions.length} clarification(s) answered (optional).`}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => goPhase(2)} disabled={registering}>Back</Button>
            <Button variant="primary" icon={registering ? <Loader2 size={14} className="animate-spin-slow" /> : <CheckCircle2 size={14} />} onClick={register} disabled={registering}>
              {registering ? 'Registering…' : 'Register agent'}
            </Button>
          </div>
        </Card>
      </div>
      </div>
    </div>
  );
}
