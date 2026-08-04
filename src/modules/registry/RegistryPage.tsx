import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button, DataTable, Badge, TierBadge, RiskBadge, EmptyState, type Column, type FilterDef } from '@/components/primitives';
import { MiniTrackPills } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { agentId, isLive, type AgentRecord, type LifecycleStatus } from '@/types';
import { TIER_ORDER, RISK_ORDER, PATH_DEFS } from '@/kernel/constants';
import { cost30d, money, fmtDate, titleCase } from '@/utils/format';

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

  const costOf = useMemo(() => {
    const map: Record<string, number> = {};
    for (const a of agents) map[agentId(a)] = cost30d(telemetry.find((t) => t.agent_id === agentId(a)));
    return map;
  }, [agents, telemetry]);

  const columns: Column<AgentRecord>[] = [
    {
      key: 'name',
      header: 'Name',
      width: '24%',
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
    { key: 'tracks', header: 'R/R/C', render: (a) => <MiniTrackPills agent={a} /> },
    { key: 'owner', header: 'Owner', sortValue: (a) => a.config.identity.business_owner.value, render: (a) => <span className="text-text-mid">{a.config.identity.business_owner.value}</span> },
    {
      key: 'cost',
      header: 'Cost (30d)',
      align: 'right',
      sortValue: (a) => costOf[agentId(a)] ?? 0,
      render: (a) => <span className="mono text-text-mid">{money(costOf[agentId(a)] ?? 0)}</span>,
    },
    {
      key: 'updated',
      header: 'Updated',
      align: 'right',
      sortValue: (a) => a.updated_at,
      render: (a) => <span className="text-text-low">{fmtDate(a.updated_at)}</span>,
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
    </div>
  );
}
