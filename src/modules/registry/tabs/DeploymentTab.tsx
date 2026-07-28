import type { AgentRecord } from '@/types';
import { agentId, isLive } from '@/types';
import { Card, Button } from '@/components/primitives';
import { ThreeTrackSwimlanes, AssetRefLink } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { Rocket } from 'lucide-react';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 last:border-0">
      <span className="text-[12px] text-text-low">{label}</span>
      <span className="text-[12px] text-text-hi">{children}</span>
    </div>
  );
}

export function DeploymentTab({ agent }: { agent: AgentRecord }) {
  const c = agent.config;
  const jobs = useWorkspace((s) => s.jobs);
  const live = isLive(agent);
  const provisioning = jobs.some((j) => (j.kind === 'runtime_provision' || j.kind === 'content_index') && j.entity_id === agentId(agent) && (j.status === 'processing' || j.status === 'queued'));
  const canProvision = agent.tracks.runtime.status === 'not_started' && !live;
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="primary" icon={<Rocket size={14} />} disabled={!canProvision || provisioning} onClick={() => api.provision(agentId(agent))}>
          {live ? 'Provisioned' : provisioning ? 'Provisioning…' : 'Provision'}
        </Button>
      </div>
      <ThreeTrackSwimlanes agent={agent} />

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Runtime mapping</div>
          <Row label="runtime_host">{c.runtime.runtime_host.value}</Row>
          <Row label="model_gateway_ref"><AssetRefLink refUri={c.runtime.model_gateway_ref.value} /></Row>
          <Row label="resolver_profile"><span className="mono text-[11px]">{c.runtime.resolver_profile.value}</span></Row>
          <Row label="concurrency">{c.runtime.concurrency.value}</Row>
          <Row label="timeout">{c.runtime.timeout.value}s</Row>
          <Row label="scaling_policy"><span className="mono text-[11px]">{c.runtime.scaling_policy.value}</span></Row>
        </Card>

        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Content mapping</div>
          <Row label="rag_enabled">{String(c.data.rag_enabled.value)}</Row>
          <Row label="index_target">{c.knowledge_sources.index_target.value ? <AssetRefLink refUri={c.knowledge_sources.index_target.value} /> : '—'}</Row>
          <Row label="knowledge sources">
            <span className="flex flex-wrap justify-end gap-1">
              {c.data.knowledge_source_refs.value.length ? c.data.knowledge_source_refs.value.map((r, i) => <AssetRefLink key={i} refUri={r} />) : '—'}
            </span>
          </Row>
          <Row label="mcp_connectors">
            <span className="flex flex-wrap justify-end gap-1">
              {c.tooling.mcp_connectors.value.length ? c.tooling.mcp_connectors.value.map((r, i) => <span key={i} className="mono text-[11px] text-text-mid">{r}</span>) : '—'}
            </span>
          </Row>
          <Row label="environment">{c.deployment.environment.value}</Row>
          <Row label="promotion_rollback">{c.deployment.promotion_rollback.value}</Row>
        </Card>
      </div>
    </div>
  );
}
