import { useNavigate } from 'react-router-dom';
import type { AgentRecord, EvalCategory } from '@/types';
import { agentId } from '@/types';
import { Card, Button, Badge, EmptyState } from '@/components/primitives';
import { ScoreRing } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { DEEP_EVAL_PASS_SCORE } from '@/kernel/constants';
import { titleCase, fmtDate } from '@/utils/format';
import { Lock, ExternalLink, AlertTriangle } from 'lucide-react';
import { cn } from '@/utils/cn';

const CAT_ORDER: EvalCategory[] = ['grounding', 'correctness', 'safety_boundary', 'latency_cost', 'regression'];

export function EvaluationsTab({ agent }: { agent: AgentRecord }) {
  const navigate = useNavigate();
  const pack = useWorkspace((s) => s.evalPacks.find((p) => p.agent_id === agentId(agent)));

  if (!pack) {
    return <EmptyState title="No evaluation pack" message="A pack is auto-generated during onboarding (Phase 6)." />;
  }

  const score = pack.last_run?.score ?? null;
  const deepPath = agent.governance_path === 'deep' || agent.governance_path === 'critical';
  const promotionLocked = deepPath && (score === null || score < DEEP_EVAL_PASS_SCORE);

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="space-y-4">
        <Card className="flex flex-col items-center">
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Last run</div>
          {score !== null ? <ScoreRing score={score} /> : <div className="text-[12px] text-text-low">not run yet</div>}
          {pack.last_run && <div className="mt-2 text-[11px] text-text-low">{fmtDate(pack.last_run.date)}</div>}
          <Button variant="subtle" size="sm" className="mt-3" icon={<ExternalLink size={13} />} onClick={() => navigate(`/evaluations/${pack.id}`)}>
            Open eval pack
          </Button>
        </Card>

        {deepPath && (
          <Card className={cn(promotionLocked ? 'border-err/40' : 'border-ok/40')}>
            <div className="flex items-center gap-2">
              {promotionLocked ? <Lock size={15} className="text-err" /> : <AlertTriangle size={15} className="text-ok" />}
              <div className="text-[12px]">
                <div className="font-medium text-text-hi">Promote to Production</div>
                <div className={promotionLocked ? 'text-err' : 'text-ok'}>
                  {promotionLocked ? `Locked — score must be ≥ ${DEEP_EVAL_PASS_SCORE} (${agent.governance_path} path)` : 'Eligible — score meets threshold'}
                </div>
              </div>
            </div>
          </Card>
        )}
      </div>

      <div className="col-span-2">
        <Card pad={false}>
          <div className="border-b border-border px-3 py-2.5 text-[13px] font-semibold text-text-hi">
            Cases ({pack.cases.length})
          </div>
          <div className="divide-y divide-border/50">
            {CAT_ORDER.map((cat) => {
              const cases = pack.cases.filter((c) => c.category === cat);
              if (!cases.length) return null;
              return (
                <div key={cat} className="px-3 py-2">
                  <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-low">{titleCase(cat)}</div>
                  {cases.map((c) => (
                    <div key={c.test_id} className={cn('flex items-start gap-2 py-1', cat === 'safety_boundary' && c.last_result === 'fail' && 'bg-err/10 -mx-1 px-1 rounded')}>
                      <Badge tone={c.last_result === 'pass' ? 'ok' : c.last_result === 'fail' ? 'err' : 'muted'}>{c.last_result ?? 'not run'}</Badge>
                      <div className="min-w-0 flex-1 text-[12px]">
                        <div className="text-text-hi">{c.input}</div>
                        <div className="text-[11px] text-text-low">→ {c.expected_output}</div>
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}
