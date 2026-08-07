import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Tabs, Card, Button, Badge, DataTable, Drawer, Modal, JsonViewer, type Column, type FilterDef, type TabItem } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, type ToolAsset, type McpConnector, type ToolPermission } from '@/types';
import { fmtDateTime } from '@/utils/format';
import { Ban, Radio, Power, Activity, Loader2, Plus } from 'lucide-react';
import { cn } from '@/utils/cn';

const SELECT_CLS = 'h-8 rounded-control border border-border bg-canvas px-2 text-[13px] text-text-mid focus-ring';
const INPUT_CLS = 'w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring';
const TOOL_PERMISSIONS: ToolPermission[] = ['read', 'summarize', 'draft', 'recommend', 'validate'];

export default function ToolsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'catalog';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });
  const tools = useWorkspace((s) => s.tools);
  const connectors = useWorkspace((s) => s.connectors);
  const [registerOpen, setRegisterOpen] = useState(false);

  useEffect(() => {
    if (params.get('new') === '1') {
      const p = new URLSearchParams(params); p.delete('new'); setParams(p, { replace: true });
      setRegisterOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tabs: TabItem[] = [
    { key: 'catalog', label: 'Tool Catalog', count: tools.length },
    { key: 'mcp', label: 'MCP Connectors', count: connectors.length },
  ];

  return (
    <div>
      <PageHeader
        title="Tools & MCP"
        description="Advisory base scope: tool_permission ∈ {read, summarize, draft, recommend, validate}. Write-capable tools are catalogued for visibility but cannot be bound."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => setRegisterOpen(true)}>Register Tool</Button>}
      />
      <Tabs items={tabs} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'catalog' ? <ToolCatalog /> : <McpConnectors />}
      <RegisterToolModal open={registerOpen} onClose={() => setRegisterOpen(false)} />
    </div>
  );
}

function RegisterToolModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const connectors = useWorkspace((s) => s.connectors);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [permission, setPermission] = useState<ToolPermission>('read');
  const [connectorId, setConnectorId] = useState('');

  const reset = () => { setName(''); setDescription(''); setCategory(''); setPermission('read'); setConnectorId(''); };
  const canSubmit = name.trim().length > 0 && description.trim().length > 0 && category.trim().length > 0;

  const submit = () => {
    if (!canSubmit) return;
    void api.registerTool({ name: name.trim(), description: description.trim(), category: category.trim(), permission_ceiling: permission, connector_id: connectorId || null });
    reset();
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose(); }}
      title="Register tool"
      footer={<><Button variant="ghost" onClick={() => { reset(); onClose(); }}>Cancel</Button><Button variant="primary" disabled={!canSubmit} onClick={submit}>Register</Button></>}
    >
      <div className="space-y-3">
        <div>
          <div className="mb-1 text-[12px] text-text-low">Name</div>
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. billing_reader" className={cn(INPUT_CLS, 'mono')} />
        </div>
        <div>
          <div className="mb-1 text-[12px] text-text-low">Description</div>
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What this tool does" className={INPUT_CLS} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className="mb-1 text-[12px] text-text-low">Category</div>
            <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. billing" className={INPUT_CLS} />
          </div>
          <div>
            <div className="mb-1 text-[12px] text-text-low">Permission ceiling</div>
            <select value={permission} onChange={(e) => setPermission(e.target.value as ToolPermission)} className={cn(SELECT_CLS, 'w-full')}>
              {TOOL_PERMISSIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>
        <div>
          <div className="mb-1 text-[12px] text-text-low">Connector (optional)</div>
          <select value={connectorId} onChange={(e) => setConnectorId(e.target.value)} className={cn(SELECT_CLS, 'w-full')}>
            <option value="">— none —</option>
            {connectors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="rounded-control border border-info/30 bg-info/5 px-2.5 py-2 text-[11px] text-text-mid">
          Only advisory permissions are offered here — this flow can never register a write-capable tool.
        </div>
      </div>
    </Modal>
  );
}

function ToolCatalog() {
  const navigate = useNavigate();
  const tools = useWorkspace((s) => s.tools);
  const agents = useWorkspace((s) => s.agents);
  const [selected, setSelected] = useState<ToolAsset | null>(null);

  const columns: Column<ToolAsset>[] = [
    { key: 'name', header: 'Name', width: '20%', sortValue: (t) => t.name, render: (t) => <span className="mono text-text-hi">{t.name}</span> },
    { key: 'category', header: 'Category', sortValue: (t) => t.category, render: (t) => <span className="text-text-mid">{t.category}</span> },
    { key: 'perm', header: 'Permission ceiling', sortValue: (t) => t.permission_ceiling, render: (t) => <Badge tone="info">{t.permission_ceiling}</Badge> },
    { key: 'write', header: 'Write', sortValue: (t) => (t.write_capable ? 1 : 0), render: (t) => t.write_capable ? <Badge tone="err"><Ban size={10} /> WRITE — advisory-block</Badge> : <span className="text-[11px] text-text-low">read-only</span> },
    { key: 'connector', header: 'Connector', render: (t) => <span className="mono text-[11px] text-text-mid">{t.connector_id ?? '—'}</span> },
    { key: 'used', header: 'Used by', align: 'right', sortValue: (t) => t.used_by.length, render: (t) => <span className="text-text-mid">{t.used_by.length}</span> },
  ];
  const filters: FilterDef<ToolAsset>[] = [
    { key: 'write', label: 'Write', options: [{ value: 'yes', label: 'write-capable' }, { value: 'no', label: 'read-only' }], predicate: (t, v) => (v === 'yes' ? t.write_capable : !t.write_capable) },
  ];

  return (
    <div>
      <div className="mb-3 rounded-card border border-info/30 bg-info/5 px-3 py-2 text-[12px] text-text-mid">
        Advisory base scope: <span className="mono">tool_permission ∈ {'{read, summarize, draft, recommend, validate}'}</span>. Write-capable tools are catalogued for visibility but cannot be bound.
      </div>
      <DataTable columns={columns} rows={tools} rowKey={(t) => t.id} onRowClick={(t) => setSelected(t)} searchText={(t) => `${t.name} ${t.category}`} searchPlaceholder="Search tools…" filters={filters} initialSort={{ key: 'name', dir: 'asc' }} />

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.name} subtitle={selected?.description}>
        {selected && (
          <div className="space-y-4">
            {selected.write_capable && <div className="rounded-card border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err">⚠️ Write-capable — advisory-block. This tool can never be bound to an agent.</div>}
            <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Permission ceiling</div><Badge tone="info">{selected.permission_ceiling}</Badge></div>
            <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Schema</div><JsonViewer data={selected.schema} maxHeight={220} /></div>
            <div>
              <div className="mb-1 text-[12px] font-semibold text-text-hi">Bound agents</div>
              {selected.used_by.length ? selected.used_by.map((aid) => { const a = agents.find((x) => agentId(x) === aid); return <button key={aid} onClick={() => navigate(`/agents/${aid}`)} className="block text-left text-[12px] text-accent hover:underline">{a?.config.identity.agent_name.value ?? aid}</button>; }) : <span className="text-[12px] text-text-low">Not bound to any agent.</span>}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function McpConnectors() {
  const connectors = useWorkspace((s) => s.connectors);
  const jobs = useWorkspace((s) => s.jobs);

  const dot = (status: McpConnector['status']) => status === 'connected' ? 'bg-ok' : status === 'degraded' ? 'bg-warn' : 'bg-err';

  return (
    <div className="grid grid-cols-2 gap-4">
      {connectors.map((c) => {
        const checking = jobs.some((j) => j.kind === 'healthcheck' && j.entity_id === c.id && (j.status === 'processing' || j.status === 'queued'));
        return (
          <Card key={c.id}>
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={cn('h-2.5 w-2.5 rounded-full', dot(c.status))} />
                <span className="text-[14px] font-semibold text-text-hi">{c.name}</span>
                <Badge tone={c.status === 'connected' ? 'ok' : c.status === 'degraded' ? 'warn' : 'err'}>{c.status}</Badge>
              </div>
              <Radio size={14} className="text-text-low" />
            </div>
            <div className="space-y-1 text-[12px]">
              <div className="flex justify-between"><span className="text-text-low">transport</span><span className="text-text-hi">{c.transport}</span></div>
              <div className="flex justify-between"><span className="text-text-low">endpoint</span><span className="mono text-[11px] text-text-mid truncate max-w-[60%]">{c.endpoint}</span></div>
              <div className="flex justify-between"><span className="text-text-low">auth_mode</span><span className="text-text-hi">{c.auth_mode}</span></div>
              <div className="flex justify-between"><span className="text-text-low">tools provided</span><span className="mono text-[11px] text-text-mid">{c.tools_provided.join(', ')}</span></div>
              <div className="flex justify-between"><span className="text-text-low">last healthcheck</span><span className="text-text-mid">{fmtDateTime(c.last_healthcheck)}</span></div>
            </div>
            <div className="mt-3 flex gap-2">
              <Button variant="subtle" size="sm" icon={checking ? <Loader2 size={13} className="animate-spin-slow" /> : <Activity size={13} />} disabled={checking} onClick={() => api.healthcheck(c.id)}>Run healthcheck</Button>
              <Button variant={c.status === 'offline' ? 'primary' : 'outline'} size="sm" icon={<Power size={13} />} onClick={() => api.toggleConnectorOffline(c.id)}>{c.status === 'offline' ? 'Bring online' : 'Toggle offline'}</Button>
            </div>
            {c.status === 'offline' && <div className="mt-2 text-[11px] text-err">Offline → Pre-Flight hard blocker #4 (MCP connectors available) is now red.</div>}
          </Card>
        );
      })}
    </div>
  );
}
