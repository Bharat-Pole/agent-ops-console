import { useMemo, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Tabs, Card, Badge, Button, type TabItem } from '@/components/primitives';
import { GovernanceMatrix } from '@/components/domain';
import { useWorkspace, type FeatureFlags } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, type CapabilityTier, type RiskTier, type GovernancePath } from '@/types';
import { PERSONA_LIST, PERSONAS, P95_TARGET_MS, buildMatrixFromRules, buildPathDefsMap } from '@/kernel/constants';
import { compactNum, latestP95, errorRate30d, fmtDateTime } from '@/utils/format';
import { Download, ExternalLink } from 'lucide-react';
import { cn } from '@/utils/cn';

const ALL_PATHS: GovernancePath[] = ['fast', 'standard', 'deep', 'critical'];

// Blueprint §4 recommended role set — kept verbatim as reference. This console
// implements 4 demo personas today (kernel/constants.ts PERSONAS); this table
// is the honest map of what's covered vs. what Phase 2 still needs to split out.
const BLUEPRINT_ROLES: { role: string; blurb: string; coveredBy: string | null }[] = [
  { role: 'Business User', blurb: 'Uses approved agents, gives feedback, views outputs.', coveredBy: 'Team Lead / Consumer' },
  { role: 'Agent Creator', blurb: 'Creates new agent requests, fills intent forms, configures drafts.', coveredBy: 'Business Owner' },
  { role: 'Agent Owner', blurb: 'Owns agent purpose, use case, lifecycle, business acceptance.', coveredBy: 'Business Owner' },
  { role: 'AI Engineer', blurb: 'Configures prompts, RAG, tools, workflows, model settings, testing.', coveredBy: 'Platform Engineer' },
  { role: 'Governance Reviewer', blurb: 'Approves risk tier, prompts, data access, tools, deployment, exceptions.', coveredBy: 'Governance Officer' },
  { role: 'Evaluator / QA Reviewer', blurb: 'Creates test cases, reviews scorecards, validates evidence packs.', coveredBy: null },
  { role: 'Platform Admin', blurb: 'Manages users, roles, policies, connectors, model catalog, system settings.', coveredBy: null },
  { role: 'FinOps Admin', blurb: 'Reviews token usage, cost, budget, model usage, cost-center allocation.', coveredBy: null },
  { role: 'Security / Data Owner', blurb: 'Approves sensitive data access, tool access, high-risk patterns.', coveredBy: null },
];

const FLAG_META: { key: keyof FeatureFlags; label: string; blurb: string }[] = [
  { key: 'model_repository', label: 'Model Repository', blurb: 'Show the Model Repository nav item and let it resolve in search / asset links.' },
  { key: 'workflow_builder', label: 'Workflow Builder', blurb: 'Show the Workflow & Agent Builder nav item.' },
];

export default function AdminPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'roles';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });

  const tabs: TabItem[] = [
    { key: 'roles', label: 'Users & Roles' },
    { key: 'models', label: 'Models & Cost Centers' },
    { key: 'governance', label: 'Governance Config' },
    { key: 'connectors', label: 'Connectors & Health' },
    { key: 'audit', label: 'Audit & Retention' },
    { key: 'flags', label: 'Feature Flags' },
  ];

  return (
    <div>
      <PageHeader title="Admin Console" description="Platform-wide configuration — roles, model pricing, cost centers, governance rules, connector health, audit retention, and feature flags." />
      <Tabs items={tabs} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'roles' && <RolesTab />}
      {tab === 'models' && <ModelsTab />}
      {tab === 'governance' && <GovernanceTab />}
      {tab === 'connectors' && <ConnectorsTab />}
      {tab === 'audit' && <AuditTab />}
      {tab === 'flags' && <FlagsTab />}
    </div>
  );
}

function RolesTab() {
  const persona = useWorkspace((s) => s.ui.persona);
  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <div className="mb-2 text-[13px] font-semibold text-text-hi">Implemented personas</div>
        <div className="space-y-2">
          {PERSONA_LIST.map((p) => {
            const m = PERSONAS[p];
            const active = p === persona;
            return (
              <div key={p} className={cn('rounded-control border px-2.5 py-2', active ? 'border-accent bg-accent/10' : 'border-border')}>
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-semibold text-text-hi">{m.label}</span>
                  <span className="mono text-[10px] text-text-low">{m.short}</span>
                  {active && <Badge tone="accent">current</Badge>}
                </div>
                <div className="text-[11px] text-text-low">{m.blurb}</div>
              </div>
            );
          })}
        </div>
        <div className="mt-2 text-[11px] text-text-low">Switch personas from the top bar — permissions throughout the console are gated on this value.</div>
      </Card>

      <Card>
        <div className="mb-2 text-[13px] font-semibold text-text-hi">Blueprint's recommended role set</div>
        <div className="mb-2 text-[11px] text-text-low">Reference from the platform blueprint. 4 of 9 roles map onto an implemented persona today — the rest are Phase 2 scope.</div>
        <div className="space-y-1.5">
          {BLUEPRINT_ROLES.map((r) => (
            <div key={r.role} className="flex items-start justify-between gap-2 border-b border-border/50 py-1.5 last:border-0">
              <div>
                <div className="text-[12px] font-medium text-text-hi">{r.role}</div>
                <div className="text-[11px] text-text-low">{r.blurb}</div>
              </div>
              {r.coveredBy ? <Badge tone="ok">{r.coveredBy}</Badge> : <Badge tone="neutral">not yet split out</Badge>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function ModelsTab() {
  const navigate = useNavigate();
  const models = useWorkspace((s) => s.models);
  const agents = useWorkspace((s) => s.agents);

  const byOutputCost = [...models].sort((a, b) => b.cost_output_per_mtok - a.cost_output_per_mtok);

  const costCenters = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const a of agents) {
      const label = a.config.observability.cost_label.value;
      map.set(label, [...(map.get(label) ?? []), agentId(a)]);
    }
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [agents]);

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[13px] font-semibold text-text-hi">Model price table</div>
          <Button variant="subtle" size="tiny" icon={<ExternalLink size={11} />} onClick={() => navigate('/models')}>Full repository</Button>
        </div>
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-border text-left text-[10px] uppercase text-text-low">
              <th className="py-1.5">Model</th><th className="py-1.5 text-right">In /Mtok</th><th className="py-1.5 text-right">Out /Mtok</th><th className="py-1.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {byOutputCost.map((m) => (
              <tr key={m.id} className="border-b border-border/50 last:border-0">
                <td className="py-1.5 text-text-hi">{m.name}</td>
                <td className="py-1.5 text-right mono text-text-mid">${m.cost_input_per_mtok.toFixed(3)}</td>
                <td className="py-1.5 text-right mono text-text-mid">{m.cost_output_per_mtok === 0 ? '—' : `$${m.cost_output_per_mtok.toFixed(3)}`}</td>
                <td className="py-1.5"><Badge tone={m.deployment_status === 'approved' ? 'ok' : m.deployment_status === 'candidate' ? 'info' : 'err'}>{m.deployment_status}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card>
        <div className="mb-2 text-[13px] font-semibold text-text-hi">Cost centers</div>
        <div className="mb-2 text-[11px] text-text-low">Derived from each agent's <span className="mono">observability.cost_label</span> field.</div>
        <div className="space-y-1.5">
          {costCenters.map(([label, ids]) => (
            <div key={label} className="rounded-control border border-border px-2.5 py-2">
              <div className="mb-1 flex items-center justify-between">
                <span className="mono text-[12px] text-text-hi">{label}</span>
                <Badge tone="info">{ids.length} agent{ids.length === 1 ? '' : 's'}</Badge>
              </div>
              <div className="flex flex-wrap gap-1">
                {ids.map((id) => {
                  const a = agents.find((x) => agentId(x) === id)!;
                  return <button key={id} onClick={() => navigate(`/agents/${id}`)} className="text-[11px] text-accent hover:underline">{a.config.identity.agent_name.value}</button>;
                })}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function GovernanceTab() {
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const policyRules = useWorkspace((s) => s.policyRules);
  const pathDefinitions = useWorkspace((s) => s.pathDefinitions);
  const [editingCell, setEditingCell] = useState<{ tier: CapabilityTier; risk: RiskTier } | null>(null);

  const matrix = buildMatrixFromRules(policyRules);
  const pathDefs = buildPathDefsMap(pathDefinitions);

  const counts: Record<string, number> = {};
  for (const a of agents) {
    const k = `${a.capability_tier}:${a.config.lifecycle.risk_tier.value}`;
    counts[k] = (counts[k] ?? 0) + 1;
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[13px] font-semibold text-text-hi">Approval matrix — configuration source</div>
          <Button variant="subtle" size="tiny" icon={<ExternalLink size={11} />} onClick={() => navigate('/governance')}>Approvals & Gates</Button>
        </div>
        <div className="mb-2 text-[11px] text-text-low">
          Real, DB-backed policy (<span className="mono">policy_rules</span> table) — <span className="mono">services/registration.py</span> reads
          this exact table, so editing a cell here changes real registration behavior immediately. Click a cell to change it.
        </div>
        <GovernanceMatrix counts={counts} matrix={matrix} pathDefs={pathDefs} activeTier={editingCell?.tier} activeRisk={editingCell?.risk} onCell={(tier, risk) => setEditingCell({ tier, risk })} />
        {editingCell && (
          <div className="mt-3 flex items-center gap-2 rounded-control border border-border bg-raised/40 px-2.5 py-2">
            <span className="text-[12px] text-text-mid">
              <span className="capitalize">{editingCell.tier}</span> × <span className="capitalize">{editingCell.risk}</span> →
            </span>
            <select
              value={matrix[editingCell.tier][editingCell.risk]}
              onChange={(e) => void api.updatePolicyRule(editingCell.tier, editingCell.risk, e.target.value as GovernancePath)}
              className="h-7 rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi focus-ring"
            >
              {ALL_PATHS.map((p) => <option key={p} value={p}>{pathDefs[p]?.label ?? p}</option>)}
            </select>
            <Button variant="ghost" size="tiny" onClick={() => setEditingCell(null)}>Done</Button>
          </div>
        )}
      </Card>

      <Card>
        <div className="mb-2 text-[13px] font-semibold text-text-hi">Path definitions</div>
        <div className="space-y-2">
          {ALL_PATHS.map((p) => {
            const d = pathDefs[p];
            if (!d) return null;
            return (
              <div key={p} className="rounded-control border border-border px-2.5 py-2">
                <div className="mb-1 flex items-center gap-2">
                  <Badge tone={p === 'fast' ? 'ok' : p === 'standard' ? 'accent' : p === 'deep' ? 'warn' : 'err'}>{d.label}</Badge>
                  <span className="text-[11px] text-text-low">{d.hitl_gates} HITL gate{d.hitl_gates === 1 ? '' : 's'}</span>
                </div>
                <div className="text-[11px] text-text-mid">{d.desc}</div>
                {d.approvals.length > 0 && <div className="mt-1 text-[11px] text-text-low">Approvers: {d.approvals.join(', ')}</div>}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

function ConnectorsTab() {
  const navigate = useNavigate();
  const connectors = useWorkspace((s) => s.connectors);
  const tools = useWorkspace((s) => s.tools);
  const agents = useWorkspace((s) => s.agents);
  const telemetry = useWorkspace((s) => s.telemetry);

  const toolCounts = { available: 0, degraded: 0, offline: 0 };
  for (const t of tools) toolCounts[t.status]++;

  const degradedAgents = useMemo(() => agents
    .map((a) => {
      const t = telemetry.find((x) => x.agent_id === agentId(a));
      const target = P95_TARGET_MS[a.capability_tier];
      const p95 = latestP95(t);
      const err = errorRate30d(t);
      return { a, p95, err, target, degraded: p95 > target || err > 0.02 };
    })
    .filter((r) => r.degraded), [agents, telemetry]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-text-hi">MCP connectors</div>
            <Button variant="subtle" size="tiny" icon={<ExternalLink size={11} />} onClick={() => navigate('/tools?tab=mcp')}>Manage</Button>
          </div>
          <div className="space-y-1.5">
            {connectors.map((c) => (
              <div key={c.id} className="flex items-center justify-between rounded-control border border-border px-2.5 py-1.5">
                <div className="flex items-center gap-2">
                  <span className={cn('h-2 w-2 rounded-full', c.status === 'connected' ? 'bg-ok' : c.status === 'degraded' ? 'bg-warn' : 'bg-err')} />
                  <span className="text-[12px] text-text-hi">{c.name}</span>
                  <span className="mono text-[10px] text-text-low">{c.transport} · {c.auth_mode}</span>
                </div>
                <Badge tone={c.status === 'connected' ? 'ok' : c.status === 'degraded' ? 'warn' : 'err'}>{c.status}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Tool catalog health</div>
          <div className="flex gap-3">
            <div className="flex-1 rounded-control border border-ok/30 bg-ok/5 px-3 py-2 text-center">
              <div className="text-[18px] font-semibold text-ok">{toolCounts.available}</div>
              <div className="text-[10px] uppercase text-text-low">available</div>
            </div>
            <div className="flex-1 rounded-control border border-warn/30 bg-warn/5 px-3 py-2 text-center">
              <div className="text-[18px] font-semibold text-warn">{toolCounts.degraded}</div>
              <div className="text-[10px] uppercase text-text-low">degraded</div>
            </div>
            <div className="flex-1 rounded-control border border-err/30 bg-err/5 px-3 py-2 text-center">
              <div className="text-[18px] font-semibold text-err">{toolCounts.offline}</div>
              <div className="text-[10px] uppercase text-text-low">offline</div>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <div className="mb-2 text-[13px] font-semibold text-text-hi">Degraded agents ({degradedAgents.length})</div>
        {degradedAgents.length === 0 ? (
          <div className="text-[12px] text-text-low">No agents currently exceed their p95 target or 2% error-rate threshold.</div>
        ) : (
          <div className="space-y-1">
            {degradedAgents.map((r) => (
              <button key={agentId(r.a)} onClick={() => navigate(`/agents/${agentId(r.a)}?tab=telemetry`)} className="flex w-full items-center justify-between rounded-control border border-err/20 bg-err/5 px-2.5 py-1.5 text-left hover:border-err/40">
                <span className="text-[12px] text-text-hi">{r.a.config.identity.agent_name.value}</span>
                <span className="mono text-[11px] text-err">{(r.p95 / 1000).toFixed(1)}s p95 / {(r.err * 100).toFixed(1)}% err</span>
              </button>
            ))}
          </div>
        )}
      </Card>

      <Card className="border-border/60 bg-raised/30">
        <div className="mb-1 text-[13px] font-semibold text-text-hi">Backup &amp; retention</div>
        <p className="text-[12px] text-text-low">Not yet implemented. The agents/approvals/audit_log/prompts/knowledge_chunks tables live in a single Postgres instance with no automated backup or retention policy configured yet — this is real Phase-2 platform work, not a UI gap.</p>
      </Card>
    </div>
  );
}

function AuditTab() {
  const navigate = useNavigate();
  const auditLog = useWorkspace((s) => s.auditLog);

  const byAction = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of auditLog) map.set(e.action, (map.get(e.action) ?? 0) + 1);
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [auditLog]);

  const oldest = auditLog.length ? auditLog.reduce((o, e) => (e.at < o ? e.at : o), auditLog[0].at) : null;
  const newest = auditLog.length ? auditLog.reduce((n, e) => (e.at > n ? e.at : n), auditLog[0].at) : null;

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(auditLog, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'audit-log-export.json'; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[13px] font-semibold text-text-hi">Audit log summary</div>
          <Button variant="subtle" size="tiny" icon={<ExternalLink size={11} />} onClick={() => navigate('/governance?tab=audit')}>Full log</Button>
        </div>
        <div className="mb-3 flex gap-3">
          <div className="flex-1 rounded-control border border-border px-3 py-2 text-center">
            <div className="text-[18px] font-semibold text-text-hi">{compactNum(auditLog.length)}</div>
            <div className="text-[10px] uppercase text-text-low">events</div>
          </div>
          <div className="flex-1 rounded-control border border-border px-3 py-2 text-center">
            <div className="text-[11px] font-medium text-text-hi">{oldest ? fmtDateTime(oldest) : '—'}</div>
            <div className="text-[10px] uppercase text-text-low">oldest</div>
          </div>
          <div className="flex-1 rounded-control border border-border px-3 py-2 text-center">
            <div className="text-[11px] font-medium text-text-hi">{newest ? fmtDateTime(newest) : '—'}</div>
            <div className="text-[10px] uppercase text-text-low">newest</div>
          </div>
        </div>
        <Button variant="outline" size="sm" icon={<Download size={13} />} onClick={exportJson}>Export full log (JSON)</Button>
      </Card>

      <Card>
        <div className="mb-2 text-[13px] font-semibold text-text-hi">By action</div>
        <div className="space-y-1">
          {byAction.map(([action, n]) => (
            <div key={action} className="flex items-center justify-between border-b border-border/50 py-1 last:border-0">
              <span className="mono text-[12px] text-accent">{action}</span>
              <span className="text-[12px] text-text-mid">{n}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function FlagsTab() {
  const flags = useWorkspace((s) => s.ui.featureFlags);

  return (
    <Card className="max-w-lg">
      <div className="mb-1 text-[13px] font-semibold text-text-hi">Feature flags</div>
      <div className="mb-3 text-[11px] text-text-low">Nav-level gates: turning one off hides it from the left nav and global search. Direct navigation to the route still works — same scope as most feature-flag systems' UI-visibility gates.</div>
      <div className="space-y-2">
        {FLAG_META.map((f) => (
          <div key={f.key} className="flex items-center justify-between rounded-control border border-border px-3 py-2">
            <div>
              <div className="text-[12px] font-medium text-text-hi">{f.label}</div>
              <div className="text-[11px] text-text-low">{f.blurb}</div>
            </div>
            <button
              onClick={() => void api.setFeatureFlag(f.key, !flags[f.key])}
              className={cn('relative h-5 w-9 shrink-0 rounded-full transition', flags[f.key] ? 'bg-accent' : 'bg-border-strong')}
              role="switch"
              aria-checked={flags[f.key]}
            >
              <span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all', flags[f.key] ? 'left-[18px]' : 'left-0.5')} />
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}
