import { Card, Button, Badge } from '@/components/primitives';
import { ScoreRing } from '@/components/domain';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { DEEP_EVAL_PASS_SCORE } from '@/kernel/constants';
import { titleCase } from '@/utils/format';
import { Play, Lock, ArrowRight, ArrowLeft, Loader2, CheckCircle2 } from 'lucide-react';
import { cn } from '@/utils/cn';

export function Phase6Evaluate({ draft, goPhase }: PhaseProps) {
  const agent = useWorkspace((s) => s.agents.find((a) => a.config.identity.agent_id.value === draft.agent_id));
  const pack = useWorkspace((s) => s.evalPacks.find((p) => p.agent_id === draft.agent_id));
  const approvals = useWorkspace((s) => s.approvals.filter((a) => a.agent_id === draft.agent_id));
  const jobs = useWorkspace((s) => s.jobs);

  if (!agent || !pack) {
    return <Card><div className="text-[13px] text-text-mid">Register the agent (Phase 3) first.</div><Button className="mt-3" variant="ghost" onClick={() => goPhase(3)}>← Back to Phase 3</Button></Card>;
  }

  const running = jobs.some((j) => j.kind === 'evaluation_run' && j.entity_id === pack.id && (j.status === 'processing' || j.status === 'queued'));
  const score = pack.last_run?.score ?? null;
  const deepPath = agent.governance_path === 'deep' || agent.governance_path === 'critical';
  const fastPath = agent.governance_path === 'fast';
  const pendingApprovals = approvals.filter((a) => a.status === 'pending');
  const approvalsGranted = pendingApprovals.length === 0;
  const scoreOk = score !== null && score >= DEEP_EVAL_PASS_SCORE;
  const promotable = approvalsGranted && (!deepPath || scoreOk);

  return (
    <div>
      <div className="mb-3 text-[13px] font-semibold text-text-hi">Phase 6 · Evaluate &amp; Approve</div>
      <div className="grid grid-cols-3 gap-4">
      <div className="space-y-4">
        <Card className="flex flex-col items-center">
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Evaluation</div>
          {score !== null ? <ScoreRing score={score} /> : <div className="py-4 text-[12px] text-text-low">not run yet</div>}
          <Button className="mt-3" variant="primary" icon={running ? <Loader2 size={14} className="animate-spin-slow" /> : <Play size={14} />} onClick={() => api.runEvaluation(pack.id)} disabled={running}>
            {running ? 'Running…' : 'Run evaluation'}
          </Button>
        </Card>

        <Card className={cn(promotable ? 'border-ok/40' : 'border-err/40')}>
          <div className="flex items-center gap-2">
            {promotable ? <CheckCircle2 size={15} className="text-ok" /> : <Lock size={15} className="text-err" />}
            <div className="text-[12px]">
              <div className="font-medium text-text-hi">Promote to Production</div>
              <div className={promotable ? 'text-ok' : 'text-err'}>
                {promotable ? 'Eligible' : deepPath && !scoreOk ? `Locked — score must be ≥ ${DEEP_EVAL_PASS_SCORE}` : 'Locked — approvals pending'}
              </div>
            </div>
          </div>
          <Button className="mt-3 w-full" variant={promotable ? 'primary' : 'subtle'} disabled={!promotable} onClick={() => goPhase(7)}>Promote → Deploy</Button>
        </Card>

        {fastPath && (
          <Card className="text-[12px] text-text-mid">
            Fast path: {approvalsGranted ? 'auto-approved.' : 'auto-approval SLA ~10s after registration (simulated)…'}
          </Card>
        )}
        {!fastPath && (
          <Card>
            <div className="mb-1 text-[12px] font-semibold text-text-hi">Approvals</div>
            {approvals.map((a) => (
              <div key={a.id} className="flex items-center justify-between py-0.5 text-[11px]">
                <span className="text-text-mid">{titleCase(a.step)}</span>
                <Badge tone={a.status === 'approved' ? 'ok' : a.status === 'rejected' ? 'err' : 'warn'}>{a.status}</Badge>
              </div>
            ))}
            {!approvalsGranted && <div className="mt-1 text-[11px] text-text-low">Grant remaining approvals in Governance → Approvals Queue (Governance Officer).</div>}
          </Card>
        )}
      </div>

      <div className="col-span-2">
        <Card pad={false}>
          <div className="border-b border-border px-3 py-2.5 text-[13px] font-semibold text-text-hi">Auto-generated eval pack ({pack.cases.length} cases)</div>
          <div className="divide-y divide-border/50">
            {pack.cases.map((c) => (
              <div key={c.test_id} className={cn('flex items-start gap-2 px-3 py-2', c.category === 'safety_boundary' && c.last_result === 'fail' && 'bg-err/10')}>
                <Badge tone={c.last_result === 'pass' ? 'ok' : c.last_result === 'fail' ? 'err' : 'muted'}>{c.last_result ?? 'not run'}</Badge>
                <div className="min-w-0 flex-1 text-[12px]">
                  <div className="text-text-hi">{c.input}</div>
                  <div className="text-[11px] text-text-low">{titleCase(c.category)} → {c.expected_output}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
        <div className="mt-4 flex items-center gap-2">
          <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => goPhase(5)}>Back</Button>
          <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => goPhase(7)}>Next: Deploy</Button>
        </div>
      </div>
      </div>
    </div>
  );
}
