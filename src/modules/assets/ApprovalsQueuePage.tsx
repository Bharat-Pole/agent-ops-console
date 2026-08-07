// Approval queue (server-backed): only steps MY roles can decide, one at a
// time — bulk approval does not exist, by design.
import { useCallback, useEffect, useState } from 'react';
import { Check, ShieldAlert, X } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, EmptyState } from '@/components/primitives';
import { useAuth } from '@/api/auth';
import {
  agentsApi, apiErrorMessage, approvalsApi, governanceApi,
  type ApprovalStep, type GovernanceExceptionRow, type ServerAgent,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

export default function ApprovalsQueuePage() {
  const { me } = useAuth();
  const [steps, setSteps] = useState<ApprovalStep[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    approvalsApi.queue().then(setSteps).catch((e) => setError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const decide = async (step: ApprovalStep, approve: boolean) => {
    setError(null);
    try { await approvalsApi.decide(step.id, approve, notes[step.id]); load(); }
    catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <div>
      <PageHeader
        title="Approval Queue"
        description={`Pending steps your roles (${me?.roles.join(', ') || 'none'}) can decide. Decisions are individual — there is no bulk approval.`}
      />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}
      {steps === null ? <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
        : steps.length === 0 ? <EmptyState title="Queue is empty" message="No pending approvals for your roles." />
        : (
          <div className="flex flex-col gap-3">
            {steps.map((s) => (
              <Card key={s.id}>
                <CardHeader
                  title={<span className="flex items-center gap-2">
                    {titleCase(s.resource_type)} · {titleCase(s.step)}
                    <Badge tone="warn">requires {s.required_role}</Badge></span>}
                  subtitle={<span className="mono text-[11px]">{s.resource_id} · requested {fmtDate(s.requested_at)}</span>}
                  action={<div className="flex gap-1">
                    <Button size="tiny" variant="primary" icon={<Check size={12} />} onClick={() => decide(s, true)}>Approve</Button>
                    <Button size="tiny" variant="danger" icon={<X size={12} />} onClick={() => decide(s, false)}>Reject</Button>
                  </div>}
                />
                <input
                  className="h-8 w-full rounded-control border border-border bg-canvas px-2.5 text-[12px] text-text-hi outline-none focus:border-border-strong"
                  placeholder="Decision note (recorded on the approval)"
                  value={notes[s.id] ?? ''}
                  onChange={(e) => setNotes((n) => ({ ...n, [s.id]: e.target.value }))}
                />
              </Card>
            ))}
          </div>
        )}

      <ExceptionsCard canCreate={(me?.roles ?? []).includes('governance_reviewer')} />
    </div>
  );
}

function ExceptionsCard({ canCreate }: { canCreate: boolean }) {
  const [rows, setRows] = useState<GovernanceExceptionRow[]>([]);
  const [agents, setAgents] = useState<ServerAgent[]>([]);
  const [agentId, setAgentId] = useState('');
  const [reason, setReason] = useState('');
  const [days, setDays] = useState(30);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    governanceApi.exceptions().then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(() => {
    load();
    agentsApi.list().then((a) => { setAgents(a); if (a.length) setAgentId(a[0].id); }).catch(() => undefined);
  }, [load]);

  const create = async () => {
    setError(null);
    try { await governanceApi.createException(agentId, reason, days); setReason(''); load(); }
    catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <Card className="mt-4">
      <CardHeader
        title={<span className="flex items-center gap-2"><ShieldAlert size={14} className="text-amber-400" /> Exception register</span>}
        subtitle="Logged eval-gate overrides — Low/Medium risk only, expiry hard-capped at 180 days."
      />
      {rows.length === 0 ? <div className="mb-2 text-[12px] text-text-low">No exceptions on record.</div>
        : rows.map((e) => (
          <div key={e.id} className="flex items-center justify-between border-t border-border py-1.5 text-[12px]">
            <span className="text-text-mid">
              <Badge tone={e.status === 'active' ? 'warn' : 'muted'}>{e.status}</Badge>{' '}
              <span className="mono text-[10px]">{e.agent_id.slice(0, 8)}</span> — {e.reason}
            </span>
            <span className="flex items-center gap-2 text-[11px] text-text-low">
              expires {fmtDate(e.expires_at)}
              {e.status === 'active' && (
                <button className="text-text-mid hover:text-red-400"
                  onClick={() => governanceApi.revokeException(e.id).then(load)}>revoke</button>
              )}
            </span>
          </div>
        ))}
      {canCreate && (
        <div className="mt-2 flex flex-wrap gap-2 border-t border-border pt-2">
          <select className="h-8 rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
            value={agentId} onChange={(e) => setAgentId(e.target.value)}>
            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <input className="h-8 flex-1 rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi outline-none focus:border-border-strong"
            placeholder="Reason (min 10 chars — recorded on the decision)"
            value={reason} onChange={(e) => setReason(e.target.value)} />
          <input className="h-8 w-20 rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi outline-none"
            type="number" min={1} max={180} value={days} onChange={(e) => setDays(Number(e.target.value))} />
          <Button size="tiny" variant="subtle" disabled={reason.trim().length < 10 || !agentId} onClick={create}>
            Grant exception
          </Button>
        </div>
      )}
      {error && <div className="mt-1 text-[12px] text-red-400">{error}</div>}
    </Card>
  );
}
