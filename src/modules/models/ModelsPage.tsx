import { useState } from 'react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Badge, Button, DataTable, Drawer, Modal, type Column, type FilterDef } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, type AgentRecord, type ModelAsset, type ModelRole, type ModelDeployStatus, type CapabilityTier } from '@/types';
import { Layers, Plus } from 'lucide-react';
import { cn } from '@/utils/cn';

const SELECT_CLS = 'h-8 rounded-control border border-border bg-canvas px-2 text-[13px] text-text-mid focus-ring';
const INPUT_CLS = 'w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring';
const ALL_ROLES: ModelRole[] = ['llm', 'embedding', 'eval'];

// Mirrors backend/app/services/claude_service.py MODEL_BY_TIER — the real,
// server-side truth for which model executes a given agent's requests, since
// the agent config's own model_primary field doesn't (yet) point at it.
const TIER_TO_RUNTIME_MODEL: Record<CapabilityTier, string> = {
  minimal: 'claude-haiku-4-5-20251001',
  standardized: 'claude-sonnet-5',
  advanced: 'claude-opus-5',
};

function usedByAgents(model: ModelAsset, agents: AgentRecord[]): AgentRecord[] {
  return agents.filter((a) => {
    const declared = a.config.model.model_primary.value === model.id || a.config.model.model_fallback.value === model.id;
    const runtime = TIER_TO_RUNTIME_MODEL[a.capability_tier] === model.id;
    const embeds = model.id === 'text-embedding-3-small' && a.config.data.rag_enabled.value === true;
    return declared || runtime || embeds;
  });
}

function fmtCost(n: number): string {
  return n === 0 ? '—' : `$${n.toFixed(3)}`;
}

export default function ModelsPage() {
  const models = useWorkspace((s) => s.models);
  const agents = useWorkspace((s) => s.agents);
  const [selected, setSelected] = useState<ModelAsset | null>(null);
  const [registerOpen, setRegisterOpen] = useState(false);

  const columns: Column<ModelAsset>[] = [
    { key: 'name', header: 'Model', width: '22%', sortValue: (m) => m.name, render: (m) => (
      <div>
        <div className="text-text-hi">{m.name}</div>
        <div className="mono text-[11px] text-text-low">{m.id}</div>
      </div>
    ) },
    { key: 'provider', header: 'Provider', sortValue: (m) => m.provider, render: (m) => <span className="text-text-mid">{m.provider}</span> },
    { key: 'roles', header: 'Roles', render: (m) => <div className="flex gap-1">{m.roles.map((r) => <Badge key={r} tone="info">{r}</Badge>)}</div> },
    { key: 'context', header: 'Context', align: 'right', sortValue: (m) => m.context_window, render: (m) => <span className="mono text-text-mid">{m.context_window.toLocaleString()}</span> },
    { key: 'cost', header: 'Cost /Mtok (in / out)', align: 'right', render: (m) => <span className="mono text-[12px] text-text-mid">{fmtCost(m.cost_input_per_mtok)} / {fmtCost(m.cost_output_per_mtok)}</span> },
    { key: 'latency', header: 'p50 latency', align: 'right', sortValue: (m) => m.latency_p50_ms, render: (m) => <span className="text-text-mid">{m.latency_p50_ms}ms</span> },
    { key: 'risk', header: 'Risk tiers', render: (m) => <div className="flex gap-1">{m.risk_tier_mapping.map((r) => <Badge key={r} tone={r === 'critical' || r === 'high' ? 'warn' : 'ok'}>{r}</Badge>)}</div> },
    { key: 'status', header: 'Status', sortValue: (m) => m.deployment_status, render: (m) => <Badge tone={m.deployment_status === 'approved' ? 'ok' : m.deployment_status === 'candidate' ? 'info' : 'err'}>{m.deployment_status}</Badge> },
    { key: 'used', header: 'Used by', align: 'right', render: (m) => <span className="text-text-mid">{usedByAgents(m, agents).length}</span> },
  ];

  const filters: FilterDef<ModelAsset>[] = [
    { key: 'roles', label: 'Role', options: [{ value: 'llm', label: 'LLM' }, { value: 'embedding', label: 'Embedding' }, { value: 'eval', label: 'Eval' }], predicate: (m, v) => m.roles.includes(v as ModelAsset['roles'][number]) },
    { key: 'status', label: 'Status', options: [{ value: 'approved', label: 'approved' }, { value: 'candidate', label: 'candidate' }, { value: 'deprecated', label: 'deprecated' }], predicate: (m, v) => m.deployment_status === v },
  ];

  return (
    <div>
      <PageHeader
        title="Model Repository"
        description="Approved catalog for LLM, embedding, and evaluation models — the backstop that agent config model refs should validate against."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => setRegisterOpen(true)}>Register Model</Button>}
      />
      <Card className="mb-3 flex items-start gap-2.5 border-info/30 bg-info/5 px-3 py-2.5">
        <Layers size={15} className="mt-0.5 shrink-0 text-info" />
        <div className="text-[12px] text-text-mid">
          Two families are catalogued on purpose. The <span className="mono">vertex://</span> rows are what agent configs currently
          declare as <span className="mono">model_primary</span> / <span className="mono">model_fallback</span>. The{' '}
          <span className="mono">claude-*</span> / <span className="mono">text-embedding-3-small</span> rows are the models the
          Playground/chat backend and RAG retrieval actually call at runtime, keyed off capability tier. Those two are not yet the
          same model per agent — closing that gap is exactly what routing through this repository will fix.
        </div>
      </Card>
      <DataTable
        columns={columns}
        rows={models}
        rowKey={(m) => m.id}
        onRowClick={(m) => setSelected(m)}
        searchText={(m) => `${m.name} ${m.id} ${m.provider}`}
        searchPlaceholder="Search models…"
        filters={filters}
        initialSort={{ key: 'name', dir: 'asc' }}
      />

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.name} subtitle={selected?.id}>
        {selected && (
          <div className="space-y-4">
            <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Approved use case</div><p className="text-[12px] text-text-mid">{selected.approved_use_case}</p></div>
            <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Access policy</div><p className="text-[12px] text-text-mid">{selected.access_policy}</p></div>
            <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Routing note</div><p className="text-[12px] text-text-mid">{selected.routing_note}</p></div>
            {selected.fallback_of && (
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Fallback for</div><span className="mono text-[12px] text-accent">{selected.fallback_of}</span></div>
            )}
            <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Owner</div><span className="text-[12px] text-text-mid">{selected.owner}</span></div>
            <div>
              <div className="mb-1 text-[12px] font-semibold text-text-hi">Used by</div>
              {usedByAgents(selected, agents).length ? (
                usedByAgents(selected, agents).map((a) => (
                  <div key={agentId(a)} className="text-[12px] text-text-mid">{a.config.identity.agent_name.value}</div>
                ))
              ) : (
                <span className="text-[12px] text-text-low">Not currently matched to any agent.</span>
              )}
            </div>
          </div>
        )}
      </Drawer>

      <RegisterModelModal open={registerOpen} onClose={() => setRegisterOpen(false)} />
    </div>
  );
}

function RegisterModelModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [provider, setProvider] = useState('');
  const [roles, setRoles] = useState<ModelRole[]>(['llm']);
  const [deploymentStatus, setDeploymentStatus] = useState<ModelDeployStatus>('candidate');
  const [approvedUseCase, setApprovedUseCase] = useState('');

  const reset = () => { setId(''); setName(''); setProvider(''); setRoles(['llm']); setDeploymentStatus('candidate'); setApprovedUseCase(''); };
  const canSubmit = id.trim().length > 0 && name.trim().length > 0 && provider.trim().length > 0 && roles.length > 0;

  const toggleRole = (r: ModelRole) => setRoles((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));

  const submit = () => {
    if (!canSubmit) return;
    void api.registerModel({ id: id.trim(), name: name.trim(), provider: provider.trim(), roles, deployment_status: deploymentStatus, approved_use_case: approvedUseCase.trim() });
    reset();
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose(); }}
      title="Register model"
      footer={<><Button variant="ghost" onClick={() => { reset(); onClose(); }}>Cancel</Button><Button variant="primary" disabled={!canSubmit} onClick={submit}>Register</Button></>}
    >
      <div className="space-y-3">
        <div>
          <div className="mb-1 text-[12px] text-text-low">Model ID</div>
          <input autoFocus value={id} onChange={(e) => setId(e.target.value)} placeholder="e.g. claude-opus-6 or vertex://gemini-2.0" className={cn(INPUT_CLS, 'mono')} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className="mb-1 text-[12px] text-text-low">Display name</div>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Claude Opus 6" className={INPUT_CLS} />
          </div>
          <div>
            <div className="mb-1 text-[12px] text-text-low">Provider</div>
            <input value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="e.g. Anthropic" className={INPUT_CLS} />
          </div>
        </div>
        <div>
          <div className="mb-1 text-[12px] text-text-low">Roles</div>
          <div className="flex gap-3">
            {ALL_ROLES.map((r) => (
              <label key={r} className="flex items-center gap-1.5 text-[12px] text-text-mid">
                <input type="checkbox" checked={roles.includes(r)} onChange={() => toggleRole(r)} />
                {r}
              </label>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-1 text-[12px] text-text-low">Deployment status</div>
          <select value={deploymentStatus} onChange={(e) => setDeploymentStatus(e.target.value as ModelDeployStatus)} className={cn(SELECT_CLS, 'w-full')}>
            <option value="candidate">candidate</option>
            <option value="approved">approved</option>
            <option value="deprecated">deprecated</option>
          </select>
        </div>
        <div>
          <div className="mb-1 text-[12px] text-text-low">Approved use case</div>
          <input value={approvedUseCase} onChange={(e) => setApprovedUseCase(e.target.value)} placeholder="What this model is cleared for" className={INPUT_CLS} />
        </div>
      </div>
    </Modal>
  );
}
