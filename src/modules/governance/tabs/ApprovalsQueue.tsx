import { useNavigate } from 'react-router-dom';
import { Card, Button, Badge, EmptyState } from '@/components/primitives';
import { Tooltip } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId } from '@/types';
import { PATH_DEFS } from '@/kernel/constants';
import { titleCase, fmtDate } from '@/utils/format';
import { Check, X, ShieldCheck, CheckCircle2 } from 'lucide-react';

export function ApprovalsQueue() {
  const navigate = useNavigate();
  const persona = useWorkspace((s) => s.ui.persona);
  const approvals = useWorkspace((s) => s.approvals);
  const agents = useWorkspace((s) => s.agents);
  const canDecide = persona === 'governance_officer';

  const pending = approvals.filter((a) => a.status === 'pending');
  const byAgent = new Map<string, typeof pending>();
  for (const p of pending) {
    if (!byAgent.has(p.agent_id)) byAgent.set(p.agent_id, []);
    byAgent.get(p.agent_id)!.push(p);
  }

  const agentName = (id: string) => agents.find((a) => agentId(a) === id)?.config.identity.agent_name.value ?? id;

  if (pending.length === 0) {
    return <EmptyState icon={<CheckCircle2 size={26} />} title="Queue clear" message="No pending approval items. Register a Standard/Deep agent to populate the queue." />;
  }

  return (
    <div className="space-y-4">
      {!canDecide && (
        <div className="rounded-card border border-warn/40 bg-warn/10 px-3 py-2 text-[12px] text-warn">
          You are viewing as <b>{titleCase(persona)}</b>. Only the <b>Governance Officer</b> can approve or reject.
        </div>
      )}
      {[...byAgent.entries()].map(([aid, items]) => (
        <Card key={aid} pad={false}>
          <button onClick={() => navigate(`/agents/${aid}?tab=governance`)} className="flex w-full items-center gap-2 border-b border-border px-4 py-2.5 text-left">
            <ShieldCheck size={15} className="text-accent" />
            <span className="text-[13px] font-semibold text-text-hi">{agentName(aid)}</span>
            <span className="mono text-[10px] text-text-low">{aid}</span>
            <Badge tone="warn" className="ml-auto">{items.length} pending</Badge>
          </button>
          <div className="divide-y divide-border/50">
            {items.map((it) => (
              <div key={it.id} className="flex items-center gap-3 px-4 py-2.5">
                <div className="flex-1">
                  <div className="text-[13px] text-text-hi">{titleCase(it.step)}</div>
                  <div className="text-[11px] text-text-low">required by {PATH_DEFS[it.required_by_path].label} path · requested {fmtDate(it.requested_at)}</div>
                </div>
                <Tooltip content={canDecide ? '' : 'Switch to Governance Officer persona'}>
                  <span className="flex gap-1.5">
                    <Button variant="primary" size="sm" icon={<Check size={13} />} disabled={!canDecide} onClick={() => api.decideApproval(it.id, 'approved', 'Approved — schema valid, advisory scope confirmed.')}>Approve</Button>
                    <Button variant="danger" size="sm" icon={<X size={13} />} disabled={!canDecide} onClick={() => api.decideApproval(it.id, 'rejected', 'Rejected — returned for revision.')}>Reject</Button>
                  </span>
                </Tooltip>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
