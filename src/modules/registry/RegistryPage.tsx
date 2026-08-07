import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2 } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button, DataTable, Badge, TierBadge, RiskBadge, EmptyState, Modal, Tooltip, type Column, type FilterDef } from '@/components/primitives';
import { MiniTrackPills } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, isLive, type AgentRecord, type LifecycleStatus } from '@/types';
import { TIER_ORDER, RISK_ORDER, PATH_DEFS, DEEP_EVAL_PASS_SCORE } from '@/kernel/constants';
import { cost30d, tokens30d, money, compactNum, fmtDate, titleCase } from '@/utils/format';

const LIFECYCLE_TONE: Record<LifecycleStatus, 'ok' | 'accent' | 'warn' | 'neutral' | 'muted' | 'err'> = {
  draft: 'muted',
  registered: 'neutral',
  in_review: 'warn',
  approved: 'accent',
  live: 'ok',
  suspended: 'err',
  retired: 'muted',
};

export default function RegistryPage() {
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const telemetry = useWorkspace((s) => s.telemetry);
  const approvals = useWorkspace((s) => s.approvals);
  const evalPacks = useWorkspace((s) => s.evalPacks);
  const auditLog = useWorkspace((s) => s.auditLog);
  const environments = useWorkspace((s) => s.agentEnvironments);
  const persona = useWorkspace((s) => s.ui.persona);
  const canDelete = persona === 'platform_engineer';
  const [pendingDelete, setPendingDelete] = useState<AgentRecord | null>(null);
  const [deleting, setDeleting] = useState(false);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    const ok = await api.deleteAgent(agentId(pendingDelete));
    setDeleting(false);
    if (ok) setPendingDelete(null);
  };

  // Real $ cost + real token volume (request_telemetry, module 7/8) — was $ only.
  const usageOf = useMemo(() => {
    const map: Record<string, { cost: number; tokens: number }> = {};
    for (const a of agents) {
      const t = telemetry.find((x) => x.agent_id === agentId(a));
      map[agentId(a)] = { cost: cost30d(t), tokens: tokens30d(t) };
    }
    return map;
  }, [agents, telemetry]);

  // Real pending-approval count per agent (was only visible on the agent's own Governance tab).
  const approvalsOf = useMemo(() => {
    const map: Record<string, number> = {};
    for (const item of approvals) {
      if (item.status !== 'pending') continue;
      map[item.agent_id] = (map[item.agent_id] ?? 0) + 1;
    }
    return map;
  }, [approvals]);

  // Real last eval score per agent (was only visible on the agent's own Evaluations tab).
  const evalScoreOf = useMemo(() => {
    const map: Record<string, number | null> = {};
    for (const p of evalPacks) map[p.agent_id] = p.last_run?.score ?? null;
    return map;
  }, [evalPacks]);

  // Real most-recent audit event per agent — covers both agent-entity events
  // (register, chat, config_change, promote/rollback, suspend/retire, access
  // grants...) and eval-run events (which are logged under entity_type='eval'
  // with the pack id, not the agent id, so they need this reverse lookup).
  const agentIdByPackId = useMemo(() => {
    const map: Record<string, string> = {};
    for (const p of evalPacks) map[p.id] = p.agent_id;
    return map;
  }, [evalPacks]);
  const lastActivityOf = useMemo(() => {
    const map: Record<string, (typeof auditLog)[number]> = {};
    for (const evt of auditLog) {
      const aid = evt.entity_type === 'agent' ? evt.entity_id : evt.entity_type === 'eval' ? agentIdByPackId[evt.entity_id] : undefined;
      if (!aid) continue;
      if (!map[aid] || evt.at > map[aid].at) map[aid] = evt;
    }
    return map;
  }, [auditLog, agentIdByPackId]);

  const domainOptions = useMemo(
    () => [...new Set(agents.map((a) => a.config.identity.use_case_category.value))].sort().map((d) => ({ value: d, label: d })),
    [agents],
  );
  const costCenterOptions = useMemo(
    () => [...new Set(agents.map((a) => a.config.observability.cost_label.value))].sort().map((c) => ({ value: c, label: c })),
    [agents],
  );
  const ownerOptions = useMemo(
    () => [...new Set(agents.map((a) => a.config.identity.business_owner.value))].sort().map((o) => ({ value: o, label: o })),
    [agents],
  );

  const columns: Column<AgentRecord>[] = [
    {
      key: 'name',
      header: 'Name',
      width: '20%',
      sortValue: (a) => a.config.identity.agent_name.value.toLowerCase(),
      render: (a) => (
        <div className="flex flex-col">
          <span className="font-medium text-text-hi">{a.config.identity.agent_name.value}</span>
          <span className="mono text-[10px] text-text-low">{agentId(a)}</span>
        </div>
      ),
    },
    { key: 'tier', header: 'Tier', sortValue: (a) => a.capability_tier, render: (a) => <TierBadge tier={a.capability_tier} /> },
    { key: 'risk', header: 'Risk', sortValue: (a) => a.config.lifecycle.risk_tier.value, render: (a) => <RiskBadge risk={a.config.lifecycle.risk_tier.value} /> },
    {
      key: 'path',
      header: 'Governance',
      sortValue: (a) => a.governance_path,
      render: (a) => <span className="text-text-mid">{PATH_DEFS[a.governance_path].label}</span>,
    },
    {
      key: 'lifecycle',
      header: 'Lifecycle',
      sortValue: (a) => a.config.lifecycle.lifecycle_status.value,
      render: (a) => <Badge tone={LIFECYCLE_TONE[a.config.lifecycle.lifecycle_status.value]}>{titleCase(a.config.lifecycle.lifecycle_status.value)}</Badge>,
    },
    {
      key: 'environment',
      header: 'Environment',
      sortValue: (a) => environments[agentId(a)] ?? '',
      render: (a) => {
        const env = environments[agentId(a)];
        return env ? <Badge tone={env === 'production' ? 'ok' : 'neutral'}>{env}</Badge> : <span className="text-text-low">—</span>;
      },
    },
    { key: 'tracks', header: 'R/R/C', render: (a) => <MiniTrackPills agent={a} /> },
    {
      key: 'approvals',
      header: 'Approvals',
      sortValue: (a) => approvalsOf[agentId(a)] ?? 0,
      render: (a) => {
        const pending = approvalsOf[agentId(a)] ?? 0;
        return pending > 0 ? <Badge tone="warn">{pending} pending</Badge> : <Badge tone="ok">clear</Badge>;
      },
    },
    {
      key: 'eval',
      header: 'Eval',
      sortValue: (a) => evalScoreOf[agentId(a)] ?? -1,
      render: (a) => {
        const score = evalScoreOf[agentId(a)];
        if (score == null) return <Badge tone="muted">not run</Badge>;
        return <Badge tone={score >= DEEP_EVAL_PASS_SCORE ? 'ok' : score >= 70 ? 'warn' : 'err'}>{score}/100</Badge>;
      },
    },
    { key: 'owner', header: 'Owner', sortValue: (a) => a.config.identity.business_owner.value, render: (a) => <span className="text-text-mid">{a.config.identity.business_owner.value}</span> },
    {
      key: 'cost',
      header: 'Cost / Tokens (30d)',
      align: 'right',
      sortValue: (a) => usageOf[agentId(a)]?.cost ?? 0,
      render: (a) => {
        const u = usageOf[agentId(a)];
        return (
          <div className="flex flex-col items-end">
            <span className="mono text-text-mid">{money(u?.cost ?? 0)}</span>
            <span className="text-[10px] text-text-low">{compactNum(u?.tokens ?? 0)} tok</span>
          </div>
        );
      },
    },
    {
      key: 'activity',
      header: 'Recent Activity',
      sortValue: (a) => lastActivityOf[agentId(a)]?.at ?? '',
      render: (a) => {
        const evt = lastActivityOf[agentId(a)];
        if (!evt) return <span className="text-text-low">—</span>;
        return (
          <div className="flex flex-col">
            <span className="text-[11px] text-text-mid">{titleCase(evt.action)}</span>
            <span className="text-[10px] text-text-low">{fmtDate(evt.at)}</span>
          </div>
        );
      },
    },
    {
      key: 'updated',
      header: 'Updated',
      align: 'right',
      sortValue: (a) => a.updated_at,
      render: (a) => <span className="text-text-low">{fmtDate(a.updated_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'center',
      render: (a) => (
        <Tooltip content={canDelete ? '' : 'Platform Engineer only'}>
          <button
            onClick={(e) => { e.stopPropagation(); if (canDelete) setPendingDelete(a); }}
            disabled={!canDelete}
            className="rounded p-1.5 text-text-low hover:bg-err/10 hover:text-err disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-text-low"
          >
            <Trash2 size={14} />
          </button>
        </Tooltip>
      ),
    },
  ];

  const filters: FilterDef<AgentRecord>[] = [
    { key: 'tier', label: 'Tier', options: TIER_ORDER.map((t) => ({ value: t, label: t })), predicate: (a, v) => a.capability_tier === v },
    { key: 'risk', label: 'Risk', options: RISK_ORDER.map((r) => ({ value: r, label: r })), predicate: (a, v) => a.config.lifecycle.risk_tier.value === v },
    {
      key: 'lifecycle',
      label: 'Lifecycle',
      options: (['draft', 'registered', 'in_review', 'approved', 'live', 'suspended', 'retired'] as LifecycleStatus[]).map((l) => ({ value: l, label: titleCase(l) })),
      predicate: (a, v) => a.config.lifecycle.lifecycle_status.value === v,
    },
    { key: 'live', label: 'LIVE only', options: [{ value: 'yes', label: 'yes' }], predicate: (a) => isLive(a) },
    // Domain/Cost Center are real fields (use_case_category, observability.cost_label).
    // "Team" has no real backing field anywhere in the data model — not added
    // here rather than faked; would need a real G_Identity field + backfill.
    { key: 'domain', label: 'Domain', options: domainOptions, predicate: (a, v) => a.config.identity.use_case_category.value === v },
    { key: 'costCenter', label: 'Cost Center', options: costCenterOptions, predicate: (a, v) => a.config.observability.cost_label.value === v },
    { key: 'owner', label: 'Owner', options: ownerOptions, predicate: (a, v) => a.config.identity.business_owner.value === v },
  ];

  return (
    <div>
      <PageHeader
        title="Agent Registry"
        description="The system of record. Every screen elsewhere links back here."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => navigate('/onboarding?new=1')}>New Agent</Button>}
      />
      {agents.length === 0 ? (
        <EmptyState title="No agents in the workspace" message="Reset the demo to re-seed, or start an onboarding." action={<Button variant="primary" onClick={() => navigate('/onboarding?new=1')}>Start onboarding</Button>} />
      ) : (
        <DataTable
          columns={columns}
          rows={agents}
          rowKey={(a) => agentId(a)}
          onRowClick={(a) => navigate(`/agents/${agentId(a)}`)}
          searchText={(a) => `${a.config.identity.agent_name.value} ${agentId(a)} ${a.config.identity.business_owner.value}`}
          searchPlaceholder="Search agents…"
          filters={filters}
          initialSort={{ key: 'updated', dir: 'desc' }}
        />
      )}
      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="Delete agent?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)} disabled={deleting}>Cancel</Button>
            <Button variant="danger" icon={<Trash2 size={14} />} onClick={confirmDelete} disabled={deleting}>{deleting ? 'Deleting…' : 'Delete'}</Button>
          </>
        }
      >
        {pendingDelete && (
          <p className="text-[13px] text-text-mid">
            Are you sure you want to delete <span className="font-semibold text-text-hi">{pendingDelete.config.identity.agent_name.value}</span>? This removes it from the registry along with its approvals and evaluation pack, and cannot be undone.
          </p>
        )}
      </Modal>
    </div>
  );
}
