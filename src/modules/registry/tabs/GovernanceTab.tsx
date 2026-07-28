import type { AgentRecord } from '@/types';
import { agentId } from '@/types';
import { Card, Badge } from '@/components/primitives';
import { GovernanceMatrix } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { fmtDateTime, titleCase } from '@/utils/format';
import { CheckCircle2, Clock, XCircle, ShieldAlert } from 'lucide-react';

export function GovernanceTab({ agent }: { agent: AgentRecord }) {
  const id = agentId(agent);
  const approvals = useWorkspace((s) => s.approvals.filter((a) => a.agent_id === id));
  const audit = useWorkspace((s) =>
    s.auditLog.filter((e) => e.entity_id === id || agent.approval_ids.includes(e.entity_id)),
  );
  const gates = agent.config.orchestration.hitl_gate_placement.value;

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <div className="mb-3 text-[13px] font-semibold text-text-hi">Governance matrix</div>
        <GovernanceMatrix activeTier={agent.capability_tier} activeRisk={agent.config.lifecycle.risk_tier.value} />
        <p className="mt-3 text-[12px] text-text-low">
          Path = f(capability, risk). Active cell: <span className="capitalize text-text-mid">{agent.capability_tier}</span> ×{' '}
          <span className="capitalize text-text-mid">{agent.config.lifecycle.risk_tier.value}</span>.
        </p>
      </Card>

      <Card>
        <div className="mb-3 text-[13px] font-semibold text-text-hi">Approval history</div>
        {approvals.length === 0 ? (
          <div className="text-[12px] text-text-low">No approval items (fast-path auto-approved).</div>
        ) : (
          <div className="space-y-2">
            {approvals.map((a) => (
              <div key={a.id} className="flex items-start gap-2 border-b border-border/50 pb-2 last:border-0">
                {a.status === 'approved' ? <CheckCircle2 size={15} className="mt-0.5 text-ok" /> : a.status === 'rejected' ? <XCircle size={15} className="mt-0.5 text-err" /> : <Clock size={15} className="mt-0.5 text-warn" />}
                <div className="flex-1">
                  <div className="flex items-center gap-2 text-[12px] text-text-hi">
                    {titleCase(a.step)}
                    <Badge tone={a.status === 'approved' ? 'ok' : a.status === 'rejected' ? 'err' : 'warn'}>{a.status}</Badge>
                  </div>
                  <div className="text-[11px] text-text-low">
                    {a.decided_at ? `${fmtDateTime(a.decided_at)} · ${a.actor_persona}` : `requested ${fmtDateTime(a.requested_at)}`}
                  </div>
                  {a.note && <div className="text-[11px] text-text-mid">{a.note}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-text-hi">
          <ShieldAlert size={15} className="text-info" /> HITL gate placements
        </div>
        {gates.length === 0 ? (
          <div className="text-[12px] text-text-low">No HITL gates configured.</div>
        ) : (
          <ul className="space-y-1.5">
            {gates.map((g, i) => (
              <li key={i} className="rounded border border-border bg-raised/40 px-2.5 py-1.5 text-[12px]">
                <span className="font-medium text-text-hi">{g.placement}</span>
                <span className="text-text-low"> — {g.trigger}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <div className="mb-3 text-[13px] font-semibold text-text-hi">Audit events (this agent)</div>
        <div className="max-h-72 space-y-1.5 overflow-auto">
          {audit.length === 0 ? (
            <div className="text-[12px] text-text-low">No audit events.</div>
          ) : (
            audit
              .slice()
              .sort((a, b) => (a.at < b.at ? 1 : -1))
              .map((e) => (
                <div key={e.id} className="border-b border-border/50 pb-1.5 text-[12px] last:border-0">
                  <div className="flex items-center justify-between">
                    <span className="mono text-[11px] text-accent">{e.action}</span>
                    <span className="text-[10px] text-text-low">{fmtDateTime(e.at)}</span>
                  </div>
                  <div className="text-text-mid">{e.detail}</div>
                </div>
              ))
          )}
        </div>
      </Card>
    </div>
  );
}
