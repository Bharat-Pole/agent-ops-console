import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { MessagesSquare, Rocket, PauseCircle, PlayCircle, Archive, Network } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Breadcrumbs } from '@/components/shell/Breadcrumbs';
import { Button, EmptyState, Tabs, TierBadge, RiskBadge, Badge, type TabItem } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, isLive } from '@/types';
import { titleCase } from '@/utils/format';
import { OverviewTab } from './tabs/OverviewTab';
import { ConfigurationTab } from './tabs/ConfigurationTab';
import { GovernanceTab } from './tabs/GovernanceTab';
import { EvaluationsTab } from './tabs/EvaluationsTab';
import { DeploymentTab } from './tabs/DeploymentTab';
import { TelemetryTab } from './tabs/TelemetryTab';
import { JsonTab } from './tabs/JsonTab';

const TABS: TabItem[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'configuration', label: 'Configuration' },
  { key: 'governance', label: 'Governance' },
  { key: 'evaluations', label: 'Evaluations' },
  { key: 'deployment', label: 'Deployment' },
  { key: 'telemetry', label: 'Telemetry' },
  { key: 'json', label: 'JSON' },
];

export default function AgentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const agent = useWorkspace((s) => s.agents.find((a) => agentId(a) === id));

  const tab = params.get('tab') ?? 'overview';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; }, { replace: false });

  if (!agent) {
    return (
      <div>
        <Breadcrumbs items={[{ label: 'Agent Registry', to: '/agents' }, { label: id ?? 'agent' }]} />
        <EmptyState title="Agent not found" message="No agent with that id in the workspace." action={<Button variant="primary" onClick={() => navigate('/agents')}>Back to registry</Button>} />
      </div>
    );
  }

  const c = agent.config;
  const live = isLive(agent);
  const lifecycle = c.lifecycle.lifecycle_status.value;
  const canProvision = (lifecycle === 'approved' || lifecycle === 'registered') && agent.tracks.registry.status === 'ready' && !live;

  const headerAction = (
    <div className="flex gap-2">
      <Button variant="outline" icon={<Network size={15} />} onClick={() => navigate(`/builder/${agentId(agent)}`)}>Open in Builder</Button>
      {live && (
        <Button variant="primary" icon={<MessagesSquare size={15} />} onClick={() => navigate(`/playground/${agentId(agent)}`)}>Open in Playground</Button>
      )}
      {!live && canProvision && (
        <Button variant="primary" icon={<Rocket size={15} />} onClick={() => { api.provision(agentId(agent)); setParams((p) => { p.set('tab', 'deployment'); return p; }); }}>Provision</Button>
      )}
      <PersonaGatedActions agentId={agentId(agent)} lifecycle={lifecycle} />
    </div>
  );

  return (
    <div>
      <Breadcrumbs items={[{ label: 'Agent Registry', to: '/agents' }, { label: c.identity.agent_name.value }]} />
      <PageHeader
        title={c.identity.agent_name.value}
        description={c.identity.description.value}
        badges={
          <span className="flex items-center gap-1.5">
            <TierBadge tier={agent.capability_tier} />
            <RiskBadge risk={c.lifecycle.risk_tier.value} />
            <Badge tone={lifecycle === 'live' ? 'ok' : lifecycle === 'suspended' ? 'warn' : lifecycle === 'retired' ? 'muted' : 'neutral'}>{titleCase(lifecycle)}</Badge>
          </span>
        }
        action={headerAction}
      />
      <div className="mb-3 flex items-center gap-2 text-[12px] text-text-low">
        <span className="mono">{agentId(agent)}</span>
        <span>·</span>
        <span>owner {c.identity.business_owner.value}</span>
      </div>

      <Tabs items={TABS} active={tab} onChange={setTab} className="mb-4" />

      {tab === 'overview' && <OverviewTab agent={agent} />}
      {tab === 'configuration' && <ConfigurationTab agent={agent} />}
      {tab === 'governance' && <GovernanceTab agent={agent} />}
      {tab === 'evaluations' && <EvaluationsTab agent={agent} />}
      {tab === 'deployment' && <DeploymentTab agent={agent} />}
      {tab === 'telemetry' && <TelemetryTab agent={agent} />}
      {tab === 'json' && <JsonTab agent={agent} />}
    </div>
  );
}

// Suspend / Reactivate / Retire are Governance-Officer-gated (Section 9.2).
// Suspend and retire now actually block chat/eval server-side (routes/chat.py,
// evaluations/service.py) — this is real enforcement, not just a status label.
// Retire is a one-way door by design: no reactivate path back from it,
// matching real decommissioning semantics (register a new agent instead).
function PersonaGatedActions({ agentId: id, lifecycle }: { agentId: string; lifecycle: string }) {
  const persona = useWorkspace((s) => s.ui.persona);
  if (persona !== 'governance_officer' || lifecycle === 'retired') return null;
  return (
    <>
      {lifecycle === 'suspended' ? (
        <Button variant="primary" icon={<PlayCircle size={15} />} onClick={() => api.setLifecycle(id, 'live')}>Reactivate</Button>
      ) : (
        <Button variant="outline" icon={<PauseCircle size={15} />} onClick={() => api.setLifecycle(id, 'suspended')}>Suspend</Button>
      )}
      <Button variant="ghost" icon={<Archive size={15} />} onClick={() => api.setLifecycle(id, 'retired')}>Retire</Button>
    </>
  );
}
