import { useCallback, useEffect, useState } from 'react';
import type { AccessGrant, AccessScope, AgentRecord, DeploymentRecord, Environment } from '@/types';
import { agentId, isLive } from '@/types';
import { Card, Button, Badge } from '@/components/primitives';
import { ThreeTrackSwimlanes, AssetRefLink } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { Rocket, ArrowUpCircle, ArrowDownCircle, UserPlus, X, Loader2 } from 'lucide-react';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 last:border-0">
      <span className="text-[12px] text-text-low">{label}</span>
      <span className="text-[12px] text-text-hi">{children}</span>
    </div>
  );
}

const inputCls = 'rounded-control border border-border bg-canvas px-2 py-1.5 text-[12px] text-text-hi';

export function DeploymentTab({ agent }: { agent: AgentRecord }) {
  const c = agent.config;
  const aid = agentId(agent);
  const jobs = useWorkspace((s) => s.jobs);
  const live = isLive(agent);
  const provisioning = jobs.some((j) => (j.kind === 'runtime_provision' || j.kind === 'content_index') && j.entity_id === aid && (j.status === 'processing' || j.status === 'queued'));
  const canProvision = agent.tracks.runtime.status === 'not_started' && !live;

  const [history, setHistory] = useState<{ current_environment: Environment; records: DeploymentRecord[] } | null>(null);
  const [grants, setGrants] = useState<AccessGrant[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [addingGrant, setAddingGrant] = useState(false);
  const [grantForm, setGrantForm] = useState<{ grantee: string; role_label: string; scope: AccessScope }>({ grantee: '', role_label: '', scope: 'viewer' });

  const refetch = useCallback(async () => {
    const [hRes, gRes] = await Promise.all([
      fetch(`/v1/agents/${encodeURIComponent(aid)}/deployment/history`),
      fetch(`/v1/agents/${encodeURIComponent(aid)}/access-grants`),
    ]);
    if (hRes.ok) setHistory(await hRes.json());
    if (gRes.ok) setGrants((await gRes.json()).grants);
  }, [aid]);

  useEffect(() => { void refetch(); }, [refetch]);

  const doPromote = async () => { setBusy(true); await api.promoteDeployment(aid); await refetch(); setBusy(false); };
  const doRollback = async () => { setBusy(true); await api.rollbackDeployment(aid); await refetch(); setBusy(false); };
  const doGrant = async () => {
    if (!grantForm.grantee.trim() || !grantForm.role_label.trim()) return;
    const ok = await api.grantAccess({ agent_id: aid, ...grantForm });
    if (ok) { setGrantForm({ grantee: '', role_label: '', scope: 'viewer' }); setAddingGrant(false); await refetch(); }
  };
  const doRevoke = async (grantId: string) => { await api.revokeAccess(grantId); await refetch(); };

  const currentEnv = history?.current_environment;

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="primary" icon={<Rocket size={14} />} disabled={!canProvision || provisioning} onClick={() => api.provision(aid)}>
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
        </Card>
      </div>

      <Card>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-text-hi">Environment</span>
            {currentEnv && <Badge tone={currentEnv === 'production' ? 'ok' : 'neutral'}>{currentEnv}</Badge>}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" icon={<ArrowUpCircle size={13} />} disabled={busy || currentEnv !== 'staging'} onClick={() => void doPromote()}>Promote to production</Button>
            <Button size="sm" variant="ghost" icon={<ArrowDownCircle size={13} />} disabled={busy || currentEnv !== 'production'} onClick={() => void doRollback()}>Rollback to staging</Button>
          </div>
        </div>
        {!history ? (
          <div className="flex items-center gap-1.5 py-2 text-[12px] text-text-low"><Loader2 size={12} className="animate-spin" /> Loading history…</div>
        ) : (
          <div className="divide-y divide-border/50">
            {history.records.map((r) => (
              <div key={r.id} className="flex items-center justify-between py-1.5 text-[12px]">
                <div>
                  <span className="font-medium text-text-hi">{r.action}</span>{' '}
                  <span className="text-text-low">{r.from_environment ? `${r.from_environment} → ${r.to_environment}` : r.to_environment}</span>
                  {r.reason && <span className="text-text-low"> · {r.reason}</span>}
                </div>
                <div className="text-[11px] text-text-low">{r.actor_persona} · {new Date(r.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[13px] font-semibold text-text-hi">Access grants</span>
          <Button size="sm" variant="subtle" icon={<UserPlus size={13} />} onClick={() => setAddingGrant((v) => !v)}>Grant access</Button>
        </div>
        {addingGrant && (
          <div className="mb-2 flex flex-wrap items-center gap-2 border-b border-border pb-2">
            <input value={grantForm.grantee} onChange={(e) => setGrantForm({ ...grantForm, grantee: e.target.value })} placeholder="email / grantee" className={`${inputCls} flex-1`} />
            <input value={grantForm.role_label} onChange={(e) => setGrantForm({ ...grantForm, role_label: e.target.value })} placeholder="role label" className={`${inputCls} w-36`} />
            <select value={grantForm.scope} onChange={(e) => setGrantForm({ ...grantForm, scope: e.target.value as AccessScope })} className={inputCls}>
              <option value="viewer">viewer</option>
              <option value="owner">owner</option>
              <option value="admin">admin</option>
            </select>
            <Button size="sm" variant="primary" onClick={() => void doGrant()}>Add</Button>
          </div>
        )}
        {!grants ? (
          <div className="flex items-center gap-1.5 py-2 text-[12px] text-text-low"><Loader2 size={12} className="animate-spin" /> Loading grants…</div>
        ) : (
          <div className="divide-y divide-border/50">
            {grants.map((g) => (
              <div key={g.id} className="flex items-center justify-between py-1.5 text-[12px]">
                <div>
                  <span className="text-text-hi">{g.grantee}</span>{' '}
                  <span className="text-text-low">{g.role_label} · {g.scope}{g.agent_id === null ? ' · platform-wide' : ''}</span>
                </div>
                {g.agent_id !== null && (
                  <Button variant="ghost" size="tiny" icon={<X size={11} />} onClick={() => void doRevoke(g.id)}>Revoke</Button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
