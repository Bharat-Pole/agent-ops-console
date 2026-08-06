import { useNavigate } from 'react-router-dom';
import { Card, Button, Badge, EmptyState } from '@/components/primitives';
import { Tooltip } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId } from '@/types';
import { PATH_DEFS } from '@/kernel/constants';
import { titleCase, fmtDate } from '@/utils/format';
import { Check, X, ShieldCheck, CheckCircle2, Wrench } from 'lucide-react';

export function ApprovalsQueue() {
  const navigate = useNavigate();
  const persona = useWorkspace((s) => s.ui.persona);
  const approvals = useWorkspace((s) => s.approvals);
  const agents = useWorkspace((s) => s.agents);
  const tools = useWorkspace((s) => s.tools);
  const canDecide = persona === 'governance_officer';

  const pending = approvals.filter((a) => a.status === 'pending');
  // Phase 3.2 — the queue is shared across entity kinds (Blueprint §11), so it
  // groups by entity, not by agent. A tool item has no agent_id and no
  // governance path; both are NULL rather than a stand-in value.
  const agentItems = pending.filter((a) => a.entity_type === 'agent');
  const toolItems = pending.filter((a) => a.entity_type === 'tool');

  const byAgent = new Map<string, typeof pending>();
  for (const p of agentItems) {
    const aid = p.agent_id ?? p.entity_id;
    if (!byAgent.has(aid)) byAgent.set(aid, []);
    byAgent.get(aid)!.push(p);
  }

  const agentName = (id: string) => agents.find((a) => agentId(a) === id)?.config.identity.agent_name.value ?? id;
  const toolName = (id: string) => tools.find((t) => t.id === id)?.name ?? id;

  if (pending.length === 0) {
    return <EmptyState icon={<CheckCircle2 size={26} />} title="Queue clear" message="No pending approval items. Register a Standard/Deep agent, or catalogue a tool, to populate the queue." />;
  }

  return (
    <div className="space-y-4">
      {!canDecide && (
        <div className="rounded-card border border-warn/40 bg-warn/10 px-3 py-2 text-[12px] text-warn">
          You are viewing as <b>{titleCase(persona)}</b>. Only the <b>Governance Officer</b> can approve or reject.
        </div>
      )}
      {toolItems.length > 0 && (
        <Card pad={false}>
          <button onClick={() => navigate('/tools?tab=catalog')} className="flex w-full items-center gap-2 border-b border-border px-4 py-2.5 text-left">
            <Wrench size={15} className="text-accent" />
            <span className="text-[13px] font-semibold text-text-hi">Tool Catalog</span>
            <span className="text-[11px] text-text-low">cataloguing is not consent — a pending tool cannot be bound</span>
            <Badge tone="warn" className="ml-auto">{toolItems.length} pending</Badge>
          </button>
          <div className="divide-y divide-border/50">
            {toolItems.map((it) => (
              <div key={it.id} className="flex items-center gap-3 px-4 py-2.5">
                <div className="flex-1">
                  <div className="text-[13px] text-text-hi">{toolName(it.entity_id)}</div>
                  <div className="text-[11px] text-text-low">
                    <span className="mono">{it.entity_id}</span> · {titleCase(it.step)} · requested {fmtDate(it.requested_at)}
                  </div>
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
                  <div className="text-[11px] text-text-low">
                    {it.required_by_path ? `required by ${PATH_DEFS[it.required_by_path].label} path · ` : ''}requested {fmtDate(it.requested_at)}
                  </div>
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
