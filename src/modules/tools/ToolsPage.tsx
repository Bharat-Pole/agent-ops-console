import { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Tabs, Card, Button, Badge, DataTable, Drawer, Modal, JsonViewer, type Column, type FilterDef, type TabItem } from '@/components/primitives';
import { TagInput } from '@/modules/onboarding/TagInput';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { PERMISSION_MATRIX } from '@/kernel/constants';
import { agentId, ADVISORY_PERMISSIONS, type ToolAsset, type ToolPermission, type ToolRiskLevel, type McpConnector, type McpTransport, type McpAuthMode, type ConnectorBacklogItem } from '@/types';
import { fmtDateTime } from '@/utils/format';
import { Ban, Radio, Power, Activity, Loader2, Plus, Sparkles, Search, RefreshCw, Pencil, ShieldCheck, Clock, XCircle, Grid3x3, ShieldHalf, Waypoints } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { ConnectorToolsResponse, ToolCallRecord, ConnectorBacklogResponse } from '@/kernel/services';

export default function ToolsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'catalog';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });
  const tools = useWorkspace((s) => s.tools);
  const connectors = useWorkspace((s) => s.connectors);

  const tabs: TabItem[] = [
    { key: 'catalog', label: 'Tool Catalog', count: tools.length },
    { key: 'mcp', label: 'MCP Connectors', count: connectors.length },
    // Server-side data, not in the store — no count here on purpose.
    { key: 'calls', label: 'Tool Calls' },
    { key: 'backlog', label: 'Connector Backlog' },
  ];

  return (
    <div>
      <PageHeader title="Tools & MCP" description="Advisory base scope: tool_permission ∈ {read, summarize, draft, recommend, validate}. Write-capable tools are catalogued for visibility but cannot be bound." />
      <Tabs items={tabs} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'catalog' && <ToolCatalog />}
      {tab === 'mcp' && <McpConnectors />}
      {tab === 'calls' && <ToolCalls />}
      {tab === 'backlog' && <ConnectorBacklog />}
    </div>
  );
}

const STATUS_TONE: Record<string, 'ok' | 'warn' | 'err'> = { available: 'ok', degraded: 'warn', offline: 'err' };

// Consent, not health — a separate axis from STATUS_TONE above (Phase 3.2).
const APPROVAL_TONE: Record<string, 'ok' | 'warn' | 'err'> = { approved: 'ok', pending: 'warn', rejected: 'err' };
const APPROVAL_ICON: Record<string, JSX.Element> = {
  approved: <ShieldCheck size={10} />,
  pending: <Clock size={10} />,
  rejected: <XCircle size={10} />,
};
const RISK_TONE: Record<string, 'ok' | 'info' | 'warn' | 'err'> = { low: 'ok', medium: 'info', high: 'warn', critical: 'err' };
const RISK_LEVELS: ToolRiskLevel[] = ['low', 'medium', 'high', 'critical'];

function ToolCatalog() {
  const navigate = useNavigate();
  const tools = useWorkspace((s) => s.tools);
  const agents = useWorkspace((s) => s.agents);
  const connectors = useWorkspace((s) => s.connectors);
  const [selected, setSelected] = useState<ToolAsset | null>(null);
  const [creating, setCreating] = useState(false);
  const [matrixOpen, setMatrixOpen] = useState(false);

  // Re-read from the store so the drawer reflects a status change cascaded
  // from the MCP Connectors tab while it is open.
  const live = selected ? tools.find((t) => t.id === selected.id) ?? selected : null;

  const columns: Column<ToolAsset>[] = [
    { key: 'name', header: 'Name', width: '20%', sortValue: (t) => t.name, render: (t) => <span className="mono text-text-hi">{t.name}</span> },
    { key: 'category', header: 'Category', sortValue: (t) => t.category, render: (t) => <span className="text-text-mid">{t.category}</span> },
    { key: 'perm', header: 'Permission ceiling', sortValue: (t) => t.permission_ceiling, render: (t) => <Badge tone="info">{t.permission_ceiling}</Badge> },
    { key: 'write', header: 'Write', sortValue: (t) => (t.write_capable ? 1 : 0), render: (t) => t.write_capable ? <Badge tone="err"><Ban size={10} /> WRITE — advisory-block</Badge> : <span className="text-[11px] text-text-low">read-only</span> },
    { key: 'connector', header: 'Connector', render: (t) => <span className="mono text-[11px] text-text-mid">{t.connector_id ?? '—'}</span> },
    { key: 'status', header: 'Status', sortValue: (t) => t.status, render: (t) => <Badge tone={STATUS_TONE[t.status] ?? 'neutral'}>{t.status}</Badge> },
    // Health and consent are different questions, so they are different
    // columns: a tool can be `available` and still `pending`.
    { key: 'approval', header: 'Approval', sortValue: (t) => t.approval_state, render: (t) => <Badge tone={APPROVAL_TONE[t.approval_state] ?? 'neutral'}>{APPROVAL_ICON[t.approval_state]} {t.approval_state}</Badge> },
    { key: 'risk', header: 'Risk', sortValue: (t) => t.risk_level ?? '', render: (t) => t.risk_level ? <Badge tone={RISK_TONE[t.risk_level] ?? 'neutral'}>{t.risk_level}</Badge> : <span className="text-[11px] text-text-low">unclassified</span> },
    { key: 'owner', header: 'Owner', sortValue: (t) => t.owner ?? '', render: (t) => t.owner ? <span className="text-text-mid">{t.owner}</span> : <span className="text-[11px] text-text-low">unassigned</span> },
    { key: 'used', header: 'Used by', align: 'right', sortValue: (t) => t.used_by.length, render: (t) => <span className="text-text-mid">{t.used_by.length}</span> },
  ];
  const filters: FilterDef<ToolAsset>[] = [
    { key: 'write', label: 'Write', options: [{ value: 'yes', label: 'write-capable' }, { value: 'no', label: 'read-only' }], predicate: (t, v) => (v === 'yes' ? t.write_capable : !t.write_capable) },
    { key: 'status', label: 'Status', options: ['available', 'degraded', 'offline'].map((s) => ({ value: s, label: s })), predicate: (t, v) => t.status === v },
    { key: 'approval', label: 'Approval', options: ['approved', 'pending', 'rejected'].map((s) => ({ value: s, label: s })), predicate: (t, v) => t.approval_state === v },
    { key: 'risk', label: 'Risk', options: [...RISK_LEVELS.map((r) => ({ value: r, label: r })), { value: 'none', label: 'unclassified' }], predicate: (t, v) => (v === 'none' ? t.risk_level === null : t.risk_level === v) },
    { key: 'connector', label: 'Connector', options: connectors.map((c) => ({ value: c.id, label: c.name })), predicate: (t, v) => t.connector_id === v },
  ];

  const pending = tools.filter((t) => t.approval_state === 'pending').length;
  const unclassified = tools.filter((t) => t.risk_level === null).length;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3 rounded-card border border-info/30 bg-info/5 px-3 py-2 text-[12px] text-text-mid">
        <span>Advisory base scope: <span className="mono">tool_permission ∈ {'{read, summarize, draft, recommend, validate}'}</span>. Write-capable tools are catalogued for visibility but cannot be bound.</span>
        <div className="flex shrink-0 gap-2">
          <Button variant="subtle" size="sm" icon={<Grid3x3 size={13} />} onClick={() => setMatrixOpen((o) => !o)}>Permission matrix</Button>
          <Button variant="primary" size="sm" icon={<Plus size={13} />} onClick={() => setCreating(true)}>New tool</Button>
        </div>
      </div>

      {matrixOpen && <PermissionMatrix tools={tools} onClose={() => setMatrixOpen(false)} />}

      {(pending > 0 || unclassified > 0) && (
        <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 rounded-card border border-warn/30 bg-warn/5 px-3 py-2 text-[12px] text-text-mid">
          {pending > 0 && <span><b className="text-warn">{pending}</b> tool(s) pending approval — catalogued but not bindable. Decide in Governance → Approvals.</span>}
          {unclassified > 0 && <span><b className="text-warn">{unclassified}</b> tool(s) with no risk classification or owner.</span>}
        </div>
      )}

      <DataTable columns={columns} rows={tools} rowKey={(t) => t.id} onRowClick={(t) => setSelected(t)} searchText={(t) => `${t.name} ${t.category} ${t.owner ?? ''}`} searchPlaceholder="Search tools…" filters={filters} initialSort={{ key: 'name', dir: 'asc' }} />

      <Drawer open={!!live} onClose={() => setSelected(null)} title={live?.name} subtitle={live?.description}>
        {live && (
          <div className="space-y-4">
            {live.write_capable && <div className="rounded-card border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err">⚠️ Write-capable — advisory-block. This tool can never be bound to an agent.</div>}
            {live.approval_state !== 'approved' && (
              <div className="rounded-card border border-warn/40 bg-warn/10 px-3 py-2 text-[12px] text-warn">
                {live.approval_state === 'pending'
                  ? 'Pending approval — catalogued and visible, but bind_tool() rejects it server-side until a Governance Officer approves. Decide it in Governance → Approvals.'
                  : 'Rejected — kept in the catalog so the decision is visible, but it cannot be bound.'}
              </div>
            )}
            <div className="flex flex-wrap gap-6">
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Permission ceiling</div><Badge tone="info">{live.permission_ceiling}</Badge></div>
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Status</div><Badge tone={STATUS_TONE[live.status] ?? 'neutral'}>{live.status}</Badge></div>
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Approval</div><Badge tone={APPROVAL_TONE[live.approval_state] ?? 'neutral'}>{APPROVAL_ICON[live.approval_state]} {live.approval_state}</Badge></div>
            </div>
            <ToolPolicyEditor tool={live} />
            {live.connector_id && (
              <div>
                <div className="mb-1 text-[12px] font-semibold text-text-hi">Served by connector</div>
                <span className="mono text-[12px] text-text-mid">{live.connector_id}</span>
                <div className="mt-1 text-[11px] text-text-low">A tool is never healthier than the connector that serves it — status is derived server-side.</div>
              </div>
            )}
            <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Schema</div><JsonViewer data={live.schema} maxHeight={220} /></div>
            <div>
              <div className="mb-1 text-[12px] font-semibold text-text-hi">Bound agents</div>
              {live.used_by.length ? live.used_by.map((aid) => { const a = agents.find((x) => agentId(x) === aid); return <button key={aid} onClick={() => navigate(`/agents/${aid}`)} className="block text-left text-[12px] text-accent hover:underline">{a?.config.identity.agent_name.value ?? aid}</button>; }) : <span className="text-[12px] text-text-low">Not bound to any agent.</span>}
            </div>
          </div>
        )}
      </Drawer>

      <NewToolModal open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}

// ---- Permission Matrix (deck slide 25 / Blueprint §3.4) -------------------
// Pure presentation over PERMISSION_MATRIX — no schema, no enforcement. It
// exists because the model was always right and never *legible*: the deck ships
// a 9-row matrix and the console could only show a 5-value enum plus a boolean.
//
// The live counts are the honest part. Allowed rows count tools that could
// actually bind under that ceiling; the four blocked rows share ONE count,
// because `write_capable` records that a tool writes and never which verb, and
// splitting 3 tools across create/update/approve/deploy would be inventing
// attribution to fill a table.
function PermissionMatrix({ tools, onClose }: { tools: ToolAsset[]; onClose: () => void }) {
  // Slide 25 title-cases its permission names; the enum is lower-case.
  const allowedCount = (p: string) => tools.filter((t) => t.permission_ceiling === p.toLowerCase() && !t.write_capable).length;
  const writeCapable = tools.filter((t) => t.write_capable).length;
  const blockedRows = PERMISSION_MATRIX.filter((r) => r.treatment === 'blocked');

  return (
    <Card className="mb-3">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-[13px] font-semibold text-text-hi">Detailed Tool Permission Matrix</div>
          <div className="text-[11px] text-text-low">Deck slide 25, quoted verbatim — the nine permission types, and how each is enforced here.</div>
        </div>
        <button onClick={onClose} className="text-[11px] text-text-low hover:text-text-hi">dismiss</button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-text-low">
              <th className="py-1.5 pr-3 font-medium">Permission</th>
              <th className="py-1.5 pr-3 font-medium">Base 90-day treatment</th>
              <th className="py-1.5 pr-3 font-medium">What it means</th>
              <th className="py-1.5 pr-3 font-medium">How it is implemented</th>
              <th className="py-1.5 text-right font-medium">Tools</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {PERMISSION_MATRIX.map((row, i) => {
              const blocked = row.treatment === 'blocked';
              const firstBlocked = blocked && row.permission === blockedRows[0].permission;
              return (
                <tr key={row.permission} className={cn(blocked && 'bg-err/[0.04]', i === 4 && 'border-b-2 border-border')}>
                  <td className="py-1.5 pr-3"><span className="mono text-text-hi">{row.permission}</span></td>
                  <td className="py-1.5 pr-3">
                    {blocked
                      ? <Badge tone="err"><Ban size={10} /> {row.treatment_text}</Badge>
                      : <Badge tone="ok">{row.treatment_text}</Badge>}
                  </td>
                  <td className="py-1.5 pr-3 text-text-mid">{row.description}</td>
                  <td className="py-1.5 pr-3 text-text-low">{row.implementation}</td>
                  <td className="py-1.5 text-right">
                    {blocked
                      ? (firstBlocked
                        ? <span className="text-text-mid" title="write_capable does not record which write verb — one count for all four rows">{writeCapable} <span className="text-text-low">(all 4)</span></span>
                        : <span className="text-text-low">↑</span>)
                      : <span className="text-text-mid">{allowedCount(row.permission)}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-2 space-y-1 border-t border-border pt-2 text-[11px] text-text-low">
        <div>
          <b className="text-text-mid">Why five values, not nine:</b> the five allowed rows are the locked{' '}
          <span className="mono">ToolPermission</span> enum, so an invalid permission is a <i>type error</i> rather than a
          policy violation. The four blocked rows have no enum member at all — they are one{' '}
          <span className="mono">write_capable</span> boolean, re-read from the server’s own table by{' '}
          <span className="mono">bind_tool()</span> and never trusted from a client.
        </div>
        <div>
          <b className="text-text-mid">Counts:</b> allowed rows count tools bindable under that ceiling. Write-capable
          tools are counted once against the blocked group regardless of their declared ceiling — they can never bind,
          so counting them as “draft” would overstate what is reachable.
        </div>
        <div>
          <b className="text-text-mid">Source:</b> permission, description and treatment are quoted from deck slide 25.
          Slide 21 and the SOW each use a slightly different vocabulary (<span className="mono">retrieve</span>,{' '}
          <span className="mono">classify</span>); slide 25 is the detailed matrix and is the one the enum follows.
        </div>
      </div>
    </Card>
  );
}

// ---- Tool policy fields (Blueprint §3.4 / ROADMAP D6) ---------------------
// The only two author-editable fields on a tool. Everything governance depends
// on — permission_ceiling, write_capable, connector_id, status, approval_state
// — is unreachable from here and rejected server-side too.
function ToolPolicyEditor({ tool }: { tool: ToolAsset }) {
  const [owner, setOwner] = useState(tool.owner ?? '');
  const [risk, setRisk] = useState<string>(tool.risk_level ?? '');
  const [saving, setSaving] = useState(false);

  // Re-seed when the drawer switches tools, or after a save returns a fresh row.
  useEffect(() => {
    setOwner(tool.owner ?? '');
    setRisk(tool.risk_level ?? '');
  }, [tool.id, tool.owner, tool.risk_level]);

  const dirty = (owner.trim() || null) !== tool.owner || (risk || null) !== tool.risk_level;

  const save = async () => {
    setSaving(true);
    await api.updateToolPolicy(tool.id, { owner: owner.trim() || null, risk_level: risk || null });
    setSaving(false);
  };

  return (
    <div className="rounded-card border border-border bg-raised/40 px-3 py-2.5">
      <div className="mb-2 text-[12px] font-semibold text-text-hi">Ownership &amp; risk</div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1 text-[11px] text-text-low">Owner</div>
          <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="unassigned" className="w-full rounded-control border border-border bg-canvas px-2.5 py-1.5 text-[12px] text-text-hi placeholder:text-text-low focus-ring" />
        </div>
        <div>
          <div className="mb-1 text-[11px] text-text-low">Risk level</div>
          <select value={risk} onChange={(e) => setRisk(e.target.value)} className="w-full rounded-control border border-border bg-canvas px-2.5 py-1.5 text-[12px] text-text-hi focus-ring">
            <option value="">unclassified</option>
            {RISK_LEVELS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <span className="text-[11px] text-text-low">
          {tool.write_capable
            ? 'Write-capable — cannot be classified below high; the server enforces the floor.'
            : 'Unclassified is a real state, not a missing value — it marks a governance gap.'}
        </span>
        <Button variant="primary" size="sm" disabled={!dirty || saving} onClick={save} icon={saving ? <Loader2 size={13} className="animate-spin-slow" /> : undefined}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}

function parsePairs(items: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const item of items) {
    const [key, ...rest] = item.split(':');
    const k = key?.trim();
    const v = rest.join(':').trim();
    if (k) out[k] = v || 'string';
  }
  return out;
}

function pairsToTags(rec: Record<string, string>): string[] {
  return Object.entries(rec).map(([k, v]) => `${k}:${v}`);
}

const EMPTY_FORM = { name: '', category: '', description: '', permission_ceiling: 'recommend' as ToolPermission, write_capable: false, owner: '', risk_level: '' as '' | ToolRiskLevel, inputs: [] as string[], outputs: [] as string[] };

function NewToolModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [prompt, setPrompt] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const reset = () => { setForm(EMPTY_FORM); setPrompt(''); };
  const close = () => { reset(); onClose(); };

  const suggest = async () => {
    if (!prompt.trim()) return;
    setSuggesting(true);
    const draft = await api.suggestTool(prompt.trim());
    setSuggesting(false);
    if (!draft) return;
    setForm((f) => ({
      ...f,
      name: draft.name ?? f.name,
      category: draft.category ?? f.category,
      description: draft.description ?? f.description,
      permission_ceiling: (draft.permission_ceiling as ToolPermission) ?? f.permission_ceiling,
      write_capable: draft.write_capable ?? f.write_capable,
      // The model may propose a risk level; the server clamps it to the
      // write-capable floor and rejects anything invalid regardless.
      risk_level: (draft.risk_level as ToolRiskLevel) ?? f.risk_level,
      inputs: draft.schema ? pairsToTags(draft.schema.inputs) : f.inputs,
      outputs: draft.schema ? pairsToTags(draft.schema.outputs) : f.outputs,
    }));
  };

  const canCreate = form.name.trim() && form.category.trim() && !creating;

  const create = async () => {
    if (!canCreate) return;
    setCreating(true);
    const tool = await api.createTool({
      name: form.name.trim(),
      category: form.category.trim(),
      description: form.description.trim(),
      permission_ceiling: form.permission_ceiling,
      write_capable: form.write_capable,
      owner: form.owner.trim() || null,
      risk_level: form.risk_level || null,
      schema: { inputs: parsePairs(form.inputs), outputs: parsePairs(form.outputs) },
    });
    setCreating(false);
    if (tool) close();
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title="New tool"
      width="max-w-2xl"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={close}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={!canCreate} onClick={create} icon={creating ? <Loader2 size={13} className="animate-spin-slow" /> : undefined}>
            {creating ? 'Creating…' : 'Create tool'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-card border border-border bg-canvas px-3 py-2.5">
          <div className="mb-1.5 text-[12px] font-medium text-text-mid">Suggest with AI</div>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            placeholder="Describe what this tool should do, e.g. “look up a customer's open support tickets by account number”…"
            className="w-full rounded-control border border-border bg-surface px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring"
          />
          <Button
            variant="subtle"
            size="sm"
            className="mt-2"
            icon={suggesting ? <Loader2 size={13} className="animate-spin-slow" /> : <Sparkles size={13} />}
            disabled={suggesting || !prompt.trim()}
            onClick={suggest}
          >
            {suggesting ? 'Drafting…' : 'Suggest'}
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Name</div>
            <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. ticket_lookup" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Category</div>
            <input value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} placeholder="e.g. network_ops" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          </div>
        </div>

        <div>
          <div className="mb-1 text-[12px] font-medium text-text-mid">Description</div>
          <textarea value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} rows={2} className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Permission ceiling</div>
            <select
              value={form.permission_ceiling}
              onChange={(e) => setForm((f) => ({ ...f, permission_ceiling: e.target.value as ToolPermission }))}
              className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring"
            >
              {ADVISORY_PERMISSIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <label className="flex items-end gap-2 pb-2 text-[12px] text-text-mid">
            <input type="checkbox" checked={form.write_capable} onChange={(e) => setForm((f) => ({ ...f, write_capable: e.target.checked }))} />
            Requires write access (advisory-block — will be catalogued but never bindable)
          </label>
        </div>

        {form.write_capable && (
          <div className="rounded-card border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err">⚠️ Write-capable — advisory-block. This tool can never be bound to an agent.</div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Owner</div>
            <input value={form.owner} onChange={(e) => setForm((f) => ({ ...f, owner: e.target.value }))} placeholder="e.g. Network Ops Platform" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Risk level</div>
            <select value={form.risk_level} onChange={(e) => setForm((f) => ({ ...f, risk_level: e.target.value as '' | ToolRiskLevel }))} className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring">
              <option value="">unclassified</option>
              {RISK_LEVELS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            {form.write_capable && <div className="mt-1 text-[11px] text-text-low">Write-capable — the server raises anything below <b>high</b>.</div>}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Inputs (field:type)</div>
            <TagInput value={form.inputs} onChange={(v) => setForm((f) => ({ ...f, inputs: v }))} placeholder="query:string, Enter…" />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Outputs (field:type)</div>
            <TagInput value={form.outputs} onChange={(v) => setForm((f) => ({ ...f, outputs: v }))} placeholder="results:Record[], Enter…" />
          </div>
        </div>

        <div className="rounded-card border border-warn/30 bg-warn/5 px-3 py-2 text-[11px] text-text-mid">
          Cataloguing a tool is not consent to use it. This registers as <b>pending approval</b> and raises an item on the
          shared approval queue — <span className="mono">bind_tool()</span> rejects it until a Governance Officer decides.
        </div>
      </div>
    </Modal>
  );
}

function McpConnectors() {
  const connectors = useWorkspace((s) => s.connectors);
  const [registering, setRegistering] = useState(false);
  const [editing, setEditing] = useState<McpConnector | null>(null);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3 rounded-card border border-info/30 bg-info/5 px-3 py-2 text-[12px] text-text-mid">
        <span>
          A tool is never healthier than the connector that serves it — connector status is authoritative and cascades
          to every tool it serves. A newly registered server advertises nothing until you run <b>Discover tools</b>.
        </span>
        <Button variant="primary" size="sm" icon={<Plus size={13} />} onClick={() => setRegistering(true)}>Register MCP server</Button>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {connectors.map((c) => <ConnectorCard key={c.id} connector={c} onEdit={() => setEditing(c)} />)}
      </div>
      <ConnectorModal
        open={registering || !!editing}
        connector={editing}
        onClose={() => { setRegistering(false); setEditing(null); }}
      />
    </div>
  );
}

// New connectors default to `streamable_http` — the spec-current remote binding,
// and the only transport the server will actually probe over the wire.
const EMPTY_CONNECTOR_FORM: { name: string; transport: McpTransport; endpoint: string; auth_mode: McpAuthMode } = {
  name: '', transport: 'streamable_http', endpoint: '', auth_mode: 'secret_manager',
};

// `stdio` has no network endpoint — it is a command line, so no scheme is enforced.
const ENDPOINT_HINT: Record<McpTransport, string> = {
  streamable_http: 'https://mcp.your-system.brightspeed.internal/mcp',
  http: 'https://mcp.your-system.brightspeed.internal/v1',
  sse: 'sse://mcp.your-system.brightspeed.internal/v1',
  stdio: 'npx -y @your-org/mcp-server',
};

// Deprecated bindings, kept selectable only because seeded connectors carry
// them (CONCERNS.md D8). Labelled in the form so nobody picks one by accident.
const DEPRECATED_TRANSPORTS: McpTransport[] = ['sse', 'http'];

// Register or edit an MCP server (Blueprint §3.5). Deliberately does NOT expose
// `status` or `tools_provided`: status belongs to the health cascade, and
// tools_provided is what the server *advertises* — discovered, never typed.
function ConnectorModal({ open, connector, onClose }: { open: boolean; connector: McpConnector | null; onClose: () => void }) {
  const [form, setForm] = useState(EMPTY_CONNECTOR_FORM);
  const [saving, setSaving] = useState(false);
  const editing = !!connector;

  // Re-seed whenever the target changes, so opening edit-then-create doesn't
  // leave the previous connector's values in the form.
  useEffect(() => {
    setForm(connector
      ? { name: connector.name, transport: connector.transport, endpoint: connector.endpoint, auth_mode: connector.auth_mode }
      : EMPTY_CONNECTOR_FORM);
  }, [connector, open]);

  const canSave = form.name.trim() && form.endpoint.trim() && !saving;

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    const payload = { name: form.name.trim(), transport: form.transport, endpoint: form.endpoint.trim(), auth_mode: form.auth_mode };
    const result = connector
      ? await api.updateConnector(connector.id, payload)
      : await api.createConnector(payload);
    setSaving(false);
    if (result) onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? `Edit ${connector!.name}` : 'Register MCP server'}
      width="max-w-xl"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={!canSave} onClick={save} icon={saving ? <Loader2 size={13} className="animate-spin-slow" /> : undefined}>
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Register'}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div>
          <div className="mb-1 text-[12px] font-medium text-text-mid">Name</div>
          <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. ServiceNow" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          {!editing && <div className="mt-1 text-[11px] text-text-low">The connector id is slugified from this and must be unique.</div>}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Transport</div>
            <select value={form.transport} onChange={(e) => setForm((f) => ({ ...f, transport: e.target.value as McpTransport }))} className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring">
              {(['streamable_http', 'stdio', 'sse', 'http'] as McpTransport[]).map((t) => (
                <option key={t} value={t}>{t}{DEPRECATED_TRANSPORTS.includes(t) ? ' (deprecated)' : ''}</option>
              ))}
            </select>
            {DEPRECATED_TRANSPORTS.includes(form.transport) && (
              <div className="mt-1 text-[11px] text-warn">
                Deprecated binding. MCP spec 2026-07-28 defines only <b>streamable_http</b> and <b>stdio</b>; only
                streamable_http connectors are contacted for real.
              </div>
            )}
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Auth mode</div>
            <select value={form.auth_mode} onChange={(e) => setForm((f) => ({ ...f, auth_mode: e.target.value as McpAuthMode }))} className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring">
              {(['secret_manager', 'oauth', 'none'] as McpAuthMode[]).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
        </div>

        <div>
          <div className="mb-1 text-[12px] font-medium text-text-mid">Endpoint</div>
          <input value={form.endpoint} onChange={(e) => setForm((f) => ({ ...f, endpoint: e.target.value }))} placeholder={ENDPOINT_HINT[form.transport]} className="mono w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[12px] text-text-hi placeholder:text-text-low focus-ring" />
          <div className="mt-1 text-[11px] text-text-low">
            {form.transport === 'stdio'
              ? 'stdio has no network endpoint — give the command that launches the server.'
              : `Must start with ${form.transport === 'sse' ? 'sse://, http:// or https://' : 'http:// or https://'} — re-validated server-side.`}
          </div>
        </div>

        <div className="rounded-card border border-border bg-raised/40 px-3 py-2 text-[11px] text-text-low">
          {editing
            ? 'Status, advertised tools and last healthcheck are not editable — status is owned by the health cascade, and advertised tools come from discovery.'
            : 'Registers as connected with no advertised tools. Run Discover tools afterwards to see the undiscovered diff against the catalog.'}
        </div>
      </div>
    </Modal>
  );
}

const dot = (status: McpConnector['status']) => status === 'connected' ? 'bg-ok' : status === 'degraded' ? 'bg-warn' : 'bg-err';

// Connector health is server-persisted, so these are real backend calls — per
// the repo convention they use local loading booleans, not kernel/jobs.ts.
function ConnectorCard({ connector: c, onEdit }: { connector: McpConnector; onEdit: () => void }) {
  const tools = useWorkspace((s) => s.tools);
  const [checking, setChecking] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [discovery, setDiscovery] = useState<ConnectorToolsResponse | null>(null);
  const [showPolicy, setShowPolicy] = useState(false);

  const busy = checking || toggling || discovering;
  const servedOffline = tools.filter((t) => t.connector_id === c.id && t.status !== 'available').length;

  const run = async (setter: (v: boolean) => void, fn: () => Promise<unknown>) => {
    setter(true);
    try { await fn(); } finally { setter(false); }
  };

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={cn('h-2.5 w-2.5 rounded-full', dot(c.status))} />
          <span className="text-[14px] font-semibold text-text-hi">{c.name}</span>
          <Badge tone={c.status === 'connected' ? 'ok' : c.status === 'degraded' ? 'warn' : 'err'}>{c.status}</Badge>
          {/* Phase 5A. A status derived from a real round trip and one derived
              from a simulated roll must never look identical — the whole point
              of storing probe evidence is that the UI can tell them apart. */}
          <Badge tone={c.last_probe ? 'ok' : 'neutral'}>{c.last_probe ? 'live MCP' : 'simulated'}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onEdit} title="Edit connector" className="text-text-low hover:text-text-hi"><Pencil size={13} /></button>
          <Radio size={14} className="text-text-low" />
        </div>
      </div>
      <div className="space-y-1 text-[12px]">
        <div className="flex justify-between"><span className="text-text-low">transport</span><span className="text-text-hi">{c.transport}</span></div>
        <div className="flex justify-between"><span className="text-text-low">endpoint</span><span className="mono text-[11px] text-text-mid truncate max-w-[60%]">{c.endpoint}</span></div>
        <div className="flex justify-between"><span className="text-text-low">auth_mode</span><span className="text-text-hi">{c.auth_mode}</span></div>
        <div className="flex justify-between"><span className="text-text-low">tools provided</span><span className="mono text-[11px] text-text-mid">{c.tools_provided.join(', ')}</span></div>
        <div className="flex justify-between"><span className="text-text-low">last healthcheck</span><span className="text-text-mid">{fmtDateTime(c.last_healthcheck)}</span></div>
        {c.last_probe && (
          <div className="flex justify-between">
            <span className="text-text-low">last probe</span>
            <span className="mono text-[11px] text-ok">
              MCP {c.last_probe.protocol_version} · {c.last_probe.latency_ms}ms · {c.last_probe.tool_count} advertised
            </span>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="subtle" size="sm" disabled={busy}
          icon={checking ? <Loader2 size={13} className="animate-spin-slow" /> : <Activity size={13} />}
          onClick={() => run(setChecking, () => api.healthcheck(c.id))}>Run healthcheck</Button>
        <Button variant={c.status === 'offline' ? 'primary' : 'outline'} size="sm" disabled={busy}
          icon={toggling ? <Loader2 size={13} className="animate-spin-slow" /> : <Power size={13} />}
          onClick={() => run(setToggling, () => api.toggleConnectorOffline(c.id))}>
          {c.status === 'offline' ? 'Bring online' : 'Toggle offline'}
        </Button>
        <Button variant="subtle" size="sm" disabled={busy}
          icon={discovering ? <Loader2 size={13} className="animate-spin-slow" /> : <Search size={13} />}
          onClick={() => run(setDiscovering, async () => setDiscovery(await api.listConnectorTools(c.id)))}>Discover tools</Button>
        <Button variant="subtle" size="sm" icon={<ShieldHalf size={13} />} onClick={() => setShowPolicy((v) => !v)}>
          {showPolicy ? 'Hide' : 'Gateway'} policy
        </Button>
      </div>

      {showPolicy && <ConnectorPolicyPanel connector={c} />}

      {c.status === 'offline' && <div className="mt-2 text-[11px] text-err">Offline → Pre-Flight hard blocker #4 (MCP connectors available) is now red.</div>}
      {servedOffline > 0 && (
        <div className="mt-2 text-[11px] text-warn">
          {servedOffline} served tool(s) not available — a tool is never healthier than its connector.
        </div>
      )}

      {discovery && (
        <div className="mt-3 rounded-card border border-border bg-raised/40 px-3 py-2">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[12px] font-semibold text-text-hi">
              MCP tools/list
              {discovery.live && discovery.protocol_version && (
                <span className="ml-1.5 font-normal text-ok">· live, spec {discovery.protocol_version}</span>
              )}
              {discovery.live === false && <span className="ml-1.5 font-normal text-text-low">· from catalog (no live endpoint)</span>}
            </span>
            <button onClick={() => setDiscovery(null)} className="text-[11px] text-text-low hover:text-text-hi">dismiss</button>
          </div>
          <div className="space-y-0.5 text-[11px]">
            {discovery.tools.map((t) => (
              <div key={t.id} className="flex items-center justify-between gap-2">
                <span className="mono truncate text-text-mid">{t.id}</span>
                <span className="flex shrink-0 items-center gap-1">
                  {t.write_capable && <Badge tone="err">write</Badge>}
                  {t.approval_state === 'pending' && <Badge tone="warn">pending</Badge>}
                  <Badge tone={STATUS_TONE[t.status] ?? 'neutral'}>{t.status}</Badge>
                </span>
              </div>
            ))}
            {/* Definitions the client refused. Reported, never silently
                dropped: a connector serving malformed tools is a fact an
                operator needs, and hiding it would make the exclusion look
                like the tool never existed. */}
            {(discovery.rejected?.length ?? 0) > 0 && (
              <div className="mt-1.5 border-t border-border pt-1.5">
                <div className="text-err">Rejected as non-conformant — excluded from discovery:</div>
                {discovery.rejected!.map((r) => (
                  <div key={r.name ?? r.detail} className="mono text-[10px] text-text-low">
                    {r.name ?? '(unnamed)'} — {r.detail}
                  </div>
                ))}
              </div>
            )}
            {(discovery.created?.length ?? 0) > 0 && (
              <div className="mt-1 text-ok">
                {discovery.created!.length} tool(s) added to the catalog, pending approval.
              </div>
            )}
            {discovery.undiscovered.length > 0 && (
              <div className="mt-1 text-warn">Advertised but not catalogued: <span className="mono">{discovery.undiscovered.join(', ')}</span></div>
            )}
            {discovery.orphaned.length > 0 && (
              <div className="mt-1 text-warn">Catalogued but no longer advertised: <span className="mono">{discovery.orphaned.join(', ')}</span></div>
            )}
            {discovery.undiscovered.length === 0 && discovery.orphaned.length === 0 && (
              <div className="mt-1 text-ok">Catalog matches what the connector advertises.</div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

// ---- Gateway policy editor (Phase 6 — slide 21 elements 4 and 5) ----------
//
// Deliberately a separate panel from `ConnectorModal`, mirroring the two
// backend routes: that form edits *how we reach* a server (name, transport,
// endpoint, auth), this one declares *what it may expose and to whom*. The
// separation is the point — an author who could widen their own data boundary
// is the hole the gateway exists to close.
//
// Empty means UNDECLARED, not deny-all, and the panel says so rather than
// showing a reassuring empty state. An undeclared boundary is a real governance
// gap; making it look like a configured one would be the worst thing this
// screen could do.

function ConnectorPolicyPanel({ connector: c }: { connector: McpConnector }) {
  const [datasets, setDatasets] = useState<string[]>(c.allowed_datasets ?? []);
  const [fields, setFields] = useState<string[]>(c.allowed_fields ?? []);
  const [identities, setIdentities] = useState<string[]>(c.approved_identities ?? []);
  const [serviceAccount, setServiceAccount] = useState(c.service_account ?? '');
  const [iamPrincipal, setIamPrincipal] = useState(c.iam_principal ?? '');
  const [rateLimit, setRateLimit] = useState(String(c.rate_limit_per_min ?? 60));
  const [timeout, setTimeoutMs] = useState(String(c.timeout_ms ?? 10000));
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.updateConnectorPolicy(c.id, {
        allowed_datasets: datasets,
        allowed_fields: fields,
        approved_identities: identities,
        service_account: serviceAccount.trim() || null,
        iam_principal: iamPrincipal.trim() || null,
        rate_limit_per_min: Number(rateLimit) || 60,
        timeout_ms: Number(timeout) || 10000,
      });
    } finally {
      setSaving(false);
    }
  };

  const gaps = [
    identities.length === 0 && 'approved identities',
    datasets.length === 0 && 'allowed datasets',
  ].filter(Boolean) as string[];

  return (
    <div className="mt-3 space-y-2.5 rounded-card border border-border bg-raised/40 px-3 py-2.5">
      <div className="text-[12px] font-semibold text-text-hi">
        Gateway policy <span className="font-normal text-text-low">· enforced on every tool call</span>
      </div>

      {gaps.length > 0 && (
        <div className="rounded-card border border-warn/30 bg-warn/5 px-2 py-1.5 text-[11px] text-warn">
          Undeclared: {gaps.join(' and ')}. An empty list means <em>nobody has written the policy</em> — not
          &ldquo;nothing allowed&rdquo;. The gateway allows the call and records the gap on every row.
        </div>
      )}

      <div>
        <label className="mb-1 block text-[11px] text-text-low">
          Allowed datasets <span className="text-text-low">— a call must name one of these once any are declared</span>
        </label>
        <TagInput value={datasets} onChange={setDatasets} placeholder="e.g. incidents_public" />
      </div>
      <div>
        <label className="mb-1 block text-[11px] text-text-low">
          Allowed fields <span className="text-text-low">— everything else is redacted from the response</span>
        </label>
        <TagInput value={fields} onChange={setFields} placeholder="e.g. key" />
      </div>
      <div>
        <label className="mb-1 block text-[11px] text-text-low">
          Approved identities <span className="text-text-low">— persona ids; enforcement is real, the principal is simulated</span>
        </label>
        <TagInput value={identities} onChange={setIdentities} placeholder="e.g. platform_engineer" />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-[11px] text-text-low">service_account</label>
          <input value={serviceAccount} onChange={(e) => setServiceAccount(e.target.value)} placeholder="unassigned"
            className="w-full rounded-input border border-border bg-base px-2 py-1 text-[12px] text-text-hi outline-none focus:border-accent" />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-text-low">iam_principal</label>
          <input value={iamPrincipal} onChange={(e) => setIamPrincipal(e.target.value)} placeholder="unassigned"
            className="w-full rounded-input border border-border bg-base px-2 py-1 text-[12px] text-text-hi outline-none focus:border-accent" />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-text-low">rate limit / min</label>
          <input value={rateLimit} onChange={(e) => setRateLimit(e.target.value)} inputMode="numeric"
            className="w-full rounded-input border border-border bg-base px-2 py-1 text-[12px] text-text-hi outline-none focus:border-accent" />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-text-low">timeout (ms)</label>
          <input value={timeout} onChange={(e) => setTimeoutMs(e.target.value)} inputMode="numeric"
            className="w-full rounded-input border border-border bg-base px-2 py-1 text-[12px] text-text-hi outline-none focus:border-accent" />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[10px] text-text-low">Slide 21 elements 4 &amp; 5 · audited as a governance action</span>
        <Button size="sm" variant="primary" disabled={saving}
          icon={saving ? <Loader2 size={13} className="animate-spin-slow" /> : undefined} onClick={save}>
          Save policy
        </Button>
      </div>
    </div>
  );
}

// ---- Connector Backlog (deck slide 21, element 7) -------------------------
// The last unbuilt element of slide 21's seven, and the contracted Week-11
// artifact: "identify which systems should be connected in the first 90 days
// versus future phases."
//
// The candidate set is the SOW's seven systems of record — not ours to extend,
// which is why there is no "add system" button. The one rule with teeth: a
// system with no existing MCP server cannot sit in the 90-day phase, because
// the SOW puts building MCP servers out of scope. That is enforced server-side;
// the UI explains it rather than hiding the control.

const PHASE_LABEL: Record<string, string> = { day_90: 'First 90 days', later: 'Later phase' };
const SERVER_TONE: Record<string, 'ok' | 'info' | 'warn' | 'err'> = {
  official: 'ok', community: 'info', none: 'err', unknown: 'warn',
};
const BACKLOG_STATUS_TONE: Record<string, 'ok' | 'info' | 'warn' | 'err' | 'neutral'> = {
  proposed: 'info', access_requested: 'info', approved: 'ok', connected: 'ok',
  deferred: 'neutral', blocked: 'err',
};
const SENSITIVITY_TONE: Record<string, 'ok' | 'info' | 'warn' | 'err'> = {
  public: 'ok', internal: 'info', confidential: 'warn', restricted: 'err',
};

function ConnectorBacklog() {
  const [data, setData] = useState<ConnectorBacklogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<ConnectorBacklogItem | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api.listConnectorBacklog().then((d) => { setData(d); setLoading(false); });
  }, []);
  useEffect(load, [load]);

  const live = open && data ? data.backlog.find((b) => b.id === open.id) ?? open : null;
  const recommended = data?.summary.recommended;

  if (!loading && !data) {
    return <Card><div className="py-6 text-center text-[13px] text-text-low">Could not reach the server — backlog unavailable.</div></Card>;
  }

  const columns: Column<ConnectorBacklogItem>[] = [
    { key: 'rank', header: '#', width: '4%', sortValue: (b) => b.rank, render: (b) => <span className="mono text-text-mid">{b.rank}</span> },
    { key: 'system', header: 'System', width: '16%', sortValue: (b) => b.system_name, render: (b) => (
      <span className="flex items-center gap-1.5">
        <span className="text-text-hi">{b.system_name}</span>
        {b.id === recommended && <Badge tone="ok">recommended</Badge>}
      </span>
    ) },
    { key: 'phase', header: 'Phase', sortValue: (b) => b.phase, render: (b) => (
      <Badge tone={b.phase === 'day_90' ? 'ok' : 'neutral'}>{PHASE_LABEL[b.phase] ?? b.phase}</Badge>
    ) },
    { key: 'server', header: 'MCP server', sortValue: (b) => b.mcp_server, render: (b) => (
      <Badge tone={SERVER_TONE[b.mcp_server] ?? 'neutral'}>{b.mcp_server}</Badge>
    ) },
    { key: 'transport', header: 'Transport', render: (b) => <span className="mono text-[11px] text-text-mid">{b.transport ?? '—'}</span> },
    { key: 'auth', header: 'Auth', render: (b) => <span className="mono text-[11px] text-text-mid">{b.auth_model ?? '—'}</span> },
    { key: 'sensitivity', header: 'Data', sortValue: (b) => b.data_sensitivity, render: (b) => (
      <Badge tone={SENSITIVITY_TONE[b.data_sensitivity] ?? 'neutral'}>{b.data_sensitivity}</Badge>
    ) },
    { key: 'owner', header: 'Access owner', render: (b) => b.access_owner
      ? <span className="text-[12px] text-text-mid">{b.access_owner}</span>
      : <span className="text-[11px] text-text-low">unidentified</span> },
    { key: 'status', header: 'Status', sortValue: (b) => b.status, render: (b) => (
      <Badge tone={BACKLOG_STATUS_TONE[b.status] ?? 'neutral'}>{b.status.replace('_', ' ')}</Badge>
    ) },
  ];

  const filters: FilterDef<ConnectorBacklogItem>[] = [
    { key: 'phase', label: 'Phase', options: [{ value: 'day_90', label: 'First 90 days' }, { value: 'later', label: 'Later phase' }], predicate: (b, v) => b.phase === v },
    { key: 'server', label: 'MCP server', options: ['official', 'community', 'none', 'unknown'].map((s) => ({ value: s, label: s })), predicate: (b, v) => b.mcp_server === v },
    { key: 'status', label: 'Status', options: ['proposed', 'access_requested', 'approved', 'connected', 'deferred', 'blocked'].map((s) => ({ value: s, label: s.replace('_', ' ') })), predicate: (b, v) => b.status === v },
  ];

  return (
    <div>
      <div className="mb-3 rounded-card border border-info/30 bg-info/5 px-3 py-2 text-[12px] text-text-mid">
        <div className="flex items-center justify-between gap-3">
          <span>
            <b className="text-text-hi">Which systems connect in the first 90 days, and which wait.</b>{' '}
            The candidate set is the SOW's seven systems of record — it is not ours to extend, so there is no
            “add system”. Slide 21 also names <i>internal applications</i> as a catch-all; that is a category,
            not an assessable system.
          </span>
          <Button variant="ghost" size="sm" icon={<RefreshCw size={13} />} onClick={load} disabled={loading}>Refresh</Button>
        </div>
        {data && (
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-border/60 pt-1.5 text-[11px]">
            <span><b className="text-ok">{data.summary.day_90}</b> in the first 90 days</span>
            <span><b className="text-text-hi">{data.summary.later}</b> deferred to a later phase</span>
            {data.summary.recommended && (
              <span>recommended reference connector: <b className="text-text-hi">{data.summary.recommended}</b></span>
            )}
            {data.summary.blocked_on_no_server.length > 0 && (
              <span className="text-warn">
                {data.summary.blocked_on_no_server.length} blocked for want of an existing MCP server
              </span>
            )}
          </div>
        )}
      </div>

      <DataTable
        columns={columns}
        rows={data?.backlog ?? []}
        rowKey={(b) => b.id}
        onRowClick={(b) => setOpen(b)}
        searchText={(b) => `${b.system_name} ${b.rationale} ${b.blockers ?? ''}`}
        searchPlaceholder="Search the backlog…"
        filters={filters}
        loading={loading}
        initialSort={{ key: 'rank', dir: 'asc' }}
      />

      <Drawer open={!!live} onClose={() => setOpen(null)} title={live?.system_name} subtitle={live ? `rank ${live.rank} · ${PHASE_LABEL[live.phase]}` : undefined}>
        {live && (
          <div className="space-y-4">
            {live.mcp_server !== 'official' && live.mcp_server !== 'community' && (
              <div className="rounded-card border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err">
                No existing MCP server, so this cannot be scheduled into the first 90 days — the SOW scopes out
                <i> building</i> MCP servers (“install and configure MCP servers only”). The server rejects the
                change rather than letting the plan claim something the contract excludes.
              </div>
            )}

            <div className="flex flex-wrap gap-6">
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">MCP server</div><Badge tone={SERVER_TONE[live.mcp_server] ?? 'neutral'}>{live.mcp_server}</Badge></div>
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Status</div><Badge tone={BACKLOG_STATUS_TONE[live.status] ?? 'neutral'}>{live.status.replace('_', ' ')}</Badge></div>
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Data sensitivity</div><Badge tone={SENSITIVITY_TONE[live.data_sensitivity] ?? 'neutral'}>{live.data_sensitivity}</Badge></div>
            </div>

            {live.mcp_server_note && (
              <div>
                <div className="mb-1 text-[12px] font-semibold text-text-hi">Server</div>
                <div className="text-[12px] text-text-mid">{live.mcp_server_note}</div>
              </div>
            )}

            <div className="flex gap-6">
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Transport</div><span className="mono text-[12px] text-text-mid">{live.transport ?? '—'}</span></div>
              <div><div className="mb-1 text-[12px] font-semibold text-text-hi">Auth model</div><span className="mono text-[12px] text-text-mid">{live.auth_model ?? '—'}</span></div>
            </div>

            <div>
              <div className="mb-1 text-[12px] font-semibold text-text-hi">Why this rank</div>
              <div className="text-[12px] leading-relaxed text-text-mid">{live.rationale}</div>
            </div>

            {live.blockers && (
              <div>
                <div className="mb-1 text-[12px] font-semibold text-text-hi">Blockers</div>
                <div className="rounded-card border border-warn/30 bg-warn/5 px-3 py-2 text-[12px] text-text-mid">{live.blockers}</div>
              </div>
            )}

            <div>
              <div className="mb-1 text-[12px] font-semibold text-text-hi">Read-only tool candidates</div>
              {live.candidate_tools.length
                ? <div className="flex flex-wrap gap-1">{live.candidate_tools.map((t) => <Badge key={t} tone="neutral"><span className="mono">{t}</span></Badge>)}</div>
                : <span className="text-[12px] text-text-low">None proposed — the system is not assessable yet.</span>}
            </div>

            <div className="flex gap-6">
              <div>
                <div className="mb-1 text-[12px] font-semibold text-text-hi">Access owner</div>
                <span className="text-[12px] text-text-mid">{live.access_owner ?? 'unidentified'}</span>
              </div>
              {live.existing_connector_id && (
                <div>
                  <div className="mb-1 text-[12px] font-semibold text-text-hi">Already registered as</div>
                  <span className="mono text-[12px] text-text-mid">{live.existing_connector_id}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}

// ---- Tool Calls (deck slide 21, element 6) --------------------------------
// The third concern on this page: not *what agents may do* (Tool Catalog) or
// *how we reach the systems* (MCP Connectors), but **what actually happened**.
//
// Server-side data with its own filters, so it uses a local loading boolean and
// refetches on filter change rather than living in the store.

const RESULT_TONE: Record<string, 'ok' | 'warn' | 'err'> = { ok: 'ok', error: 'warn', blocked: 'err' };

// Phase 6. The single most important distinction on this screen: whether a row
// is something the platform *observed* or something a client *reported*.
// Showing them as one number is the easiest way to overclaim this workstream,
// so they are labelled per row and filterable. CONCERNS R7.
function EvidenceBadge({ call }: { call: ToolCallRecord }) {
  if (!call.gateway) return <Badge tone="neutral" title="Reported by a client — result and latency are claims">reported</Badge>;
  if (call.invocation === 'live') return <Badge tone="ok" title="Real MCP round trip — latency measured, result observed">observed · live</Badge>;
  if (call.invocation === 'simulated') return <Badge tone="info" title="Policy enforced server-side; the tool body was simulated">enforced · sim</Badge>;
  return <Badge tone="err" title="Denied at a checkpoint — nothing was invoked">denied</Badge>;
}

function ToolCalls() {
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const tools = useWorkspace((s) => s.tools);
  const [calls, setCalls] = useState<ToolCallRecord[] | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api.listToolCalls({ limit: 500 }).then((rows) => {
      setCalls(rows);
      setLoading(false);
    });
  }, []);

  useEffect(load, [load]);

  const agentName = (id: string) => agents.find((a) => agentId(a) === id)?.config.identity.agent_name.value ?? id;

  const columns: Column<ToolCallRecord>[] = [
    { key: 'at', header: 'When', width: '13%', sortValue: (c) => c.at, render: (c) => <span className="text-[11px] text-text-mid">{fmtDateTime(c.at)}</span> },
    { key: 'agent', header: 'Agent', width: '17%', sortValue: (c) => c.agent_id, render: (c) => <span className="text-text-hi">{agentName(c.agent_id)}</span> },
    { key: 'request', header: 'Request', sortValue: (c) => c.request_id, render: (c) => <span className="mono text-[11px] text-text-low">{c.request_id}</span> },
    { key: 'consumer', header: 'Consumer', sortValue: (c) => c.consumer, render: (c) => <Badge tone="neutral">{c.consumer}</Badge> },
    { key: 'tool', header: 'Tool invoked', sortValue: (c) => c.tool_invoked, render: (c) => <span className="mono text-text-hi">{c.tool_invoked}</span> },
    // NULL means the tool is local and reaches no MCP server — rendered as an
    // explicit "local", never as a blank or a fabricated connector name.
    { key: 'system', header: 'System accessed', sortValue: (c) => c.system_accessed ?? '', render: (c) => c.system_accessed ? <span className="mono text-[11px] text-text-mid">{c.system_accessed}</span> : <span className="text-[11px] text-text-low">local — no MCP</span> },
    { key: 'permission', header: 'Permission', sortValue: (c) => c.permission, render: (c) => <Badge tone="info">{c.permission}</Badge> },
    { key: 'result', header: 'Result', sortValue: (c) => c.result_status, render: (c) => (
      <span className="flex items-center gap-1">
        <Badge tone={RESULT_TONE[c.result_status] ?? 'neutral'}>{c.result_status}</Badge>
        {/* The checkpoint that refused — a denial nobody can attribute is a
            denial somebody files a bug about. */}
        {c.denied_by && <span className="mono text-[10px] text-err">@{c.denied_by}</span>}
      </span>
    ) },
    { key: 'evidence', header: 'Evidence', sortValue: (c) => `${c.gateway ? 1 : 0}${c.invocation ?? ''}`, render: (c) => <EvidenceBadge call={c} /> },
    { key: 'latency', header: 'Latency', align: 'right', sortValue: (c) => c.latency_ms, render: (c) => (
      // A latency is only a system's latency when it was measured over a real
      // socket. Anything else is styled down rather than presented as equal.
      <span className={cn('mono text-[11px]', c.invocation === 'live' ? 'text-ok' : 'text-text-low')}>{c.latency_ms} ms</span>
    ) },
  ];

  const filters: FilterDef<ToolCallRecord>[] = [
    { key: 'agent', label: 'Agent', options: agents.map((a) => ({ value: agentId(a), label: a.config.identity.agent_name.value })), predicate: (c, v) => c.agent_id === v },
    { key: 'tool', label: 'Tool', options: tools.map((t) => ({ value: t.id, label: t.id })), predicate: (c, v) => c.tool_invoked === v },
    { key: 'result', label: 'Result', options: ['ok', 'error', 'blocked'].map((s) => ({ value: s, label: s })), predicate: (c, v) => c.result_status === v },
    {
      key: 'evidence',
      label: 'Evidence',
      options: [
        { value: 'observed', label: 'observed (live MCP)' },
        { value: 'enforced', label: 'gateway-enforced' },
        { value: 'reported', label: 'client-reported' },
      ],
      predicate: (c, v) =>
        v === 'observed' ? c.invocation === 'live' : v === 'enforced' ? c.gateway : !c.gateway,
    },
  ];

  const blocked = calls?.filter((c) => c.result_status === 'blocked').length ?? 0;
  const observed = calls?.filter((c) => c.invocation === 'live').length ?? 0;
  const enforced = calls?.filter((c) => c.gateway).length ?? 0;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3 rounded-card border border-info/30 bg-info/5 px-3 py-2 text-[12px] text-text-mid">
        <span>
          Every tool call, with the system it reached. <span className="mono">system_accessed</span> and{' '}
          <span className="mono">permission</span> are resolved server-side from the tool catalog — never taken from the client.
          {blocked > 0 && <> <span className="text-err">{blocked} blocked</span> — the advisory-only invariant, as evidence.</>}
        </span>
        <Button variant="ghost" size="sm" icon={<RefreshCw size={13} />} onClick={load} disabled={loading}>Refresh</Button>
      </div>

      {/* The honest claim, on the screen rather than in a doc: the gateway makes
          a call authoritative, and rows that did not pass through it are not.
          Stating the limit here is what keeps a demo from overclaiming it. */}
      <div className="mb-3 flex items-start gap-2 rounded-card border border-border bg-raised/40 px-3 py-2 text-[12px] text-text-mid">
        <Waypoints size={14} className="mt-0.5 shrink-0 text-accent" />
        <span>
          <span className="font-semibold text-text-hi">{enforced}</span> call(s) passed through the policy gateway —
          eleven checkpoints enforced server-side, the result and latency observed here rather than reported.{' '}
          <span className="font-semibold text-ok">{observed}</span> of those were real MCP round trips, and only those
          latencies measure a real system. Rows badged <span className="mono text-[11px]">reported</span> are the
          client-reported path: governed, but not runtime evidence.
        </span>
      </div>

      {!loading && calls === null ? (
        <Card><div className="py-6 text-center text-[13px] text-text-low">Could not reach the server — tool calls unavailable.</div></Card>
      ) : (
        <DataTable
          columns={columns}
          rows={calls ?? []}
          rowKey={(c) => c.id}
          onRowClick={(c) => navigate(`/agents/${c.agent_id}`)}
          searchText={(c) => `${c.tool_invoked} ${c.agent_id} ${c.request_id} ${c.system_accessed ?? ''} ${c.exception_detail ?? ''}`}
          searchPlaceholder="Search tool calls…"
          filters={filters}
          loading={loading}
          initialSort={{ key: 'at', dir: 'desc' }}
          empty={<div className="py-6 text-center text-[13px] text-text-low">No tool calls yet. Chat with a LIVE agent in the Playground and ask it to use a tool.</div>}
        />
      )}
    </div>
  );
}
