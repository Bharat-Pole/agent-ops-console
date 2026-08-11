import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Download, Trash2 } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button, DataTable, Badge, EmptyState, Tooltip, Modal, type Column, type FilterDef } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import type { PromptAsset, PromptCategory, PromptKind, PromptStatus, RiskTier, CapabilityTier } from '@/types';
import { titleCase } from '@/utils/format';

const KIND_OPTIONS: PromptKind[] = [
  'system', 'user_template', 'task', 'persona', 'tool_use', 'citation', 'template', 'safety', 'refusal', 'escalation', 'stop_condition',
];
const KIND_TONE: Record<PromptKind, 'accent' | 'info' | 'warn' | 'neutral' | 'err'> = {
  system: 'accent', user_template: 'neutral', task: 'info', persona: 'accent', tool_use: 'info',
  citation: 'info', template: 'neutral', safety: 'warn', refusal: 'err', escalation: 'warn', stop_condition: 'err',
};
const STATUS_TONE: Record<PromptStatus, 'ok' | 'neutral' | 'muted'> = { approved: 'ok', draft: 'neutral', deprecated: 'muted' };
const RISK_TIER_OPTIONS: RiskTier[] = ['low', 'medium', 'high', 'critical'];
const AGENT_TYPE_OPTIONS: CapabilityTier[] = ['minimal', 'standardized', 'advanced'];

export default function PromptsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const prompts = useWorkspace((s) => s.prompts);
  const persona = useWorkspace((s) => s.ui.persona);
  const canApprove = persona === 'governance_officer';
  const [pendingDelete, setPendingDelete] = useState<PromptAsset | null>(null);
  const [deleting, setDeleting] = useState(false);

  const createPrompt = async () => {
    const id = await api.createPrompt({ name: 'New Prompt', kind: 'template', category: 'agent', owner: `${persona}@brightspeed.com` });
    if (id) navigate(`/prompts/${id}`);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    const ok = await api.deletePrompt(pendingDelete.id);
    setDeleting(false);
    if (ok) setPendingDelete(null);
  };

  useEffect(() => {
    if (params.get('new') === '1') { params.delete('new'); setParams(params, { replace: true }); void createPrompt(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: Column<PromptAsset>[] = [
    { key: 'name', header: 'Name', width: '26%', sortValue: (p) => p.name.toLowerCase(), render: (p) => <div><div className="font-medium text-text-hi">{p.name}</div><div className="mono text-[10px] text-text-low">prompts://{p.id}@{p.version}</div></div> },
    { key: 'kind', header: 'Kind', sortValue: (p) => p.kind, render: (p) => <Badge tone={KIND_TONE[p.kind]}>{p.kind}</Badge> },
    { key: 'category', header: 'Type', sortValue: (p) => p.category, render: (p) => <Badge tone="neutral">{p.category}</Badge> },
    { key: 'status', header: 'Status', sortValue: (p) => p.status, render: (p) => <Badge tone={STATUS_TONE[p.status]}>{titleCase(p.status)}</Badge> },
    { key: 'used', header: 'Used by', align: 'right', sortValue: (p) => p.used_by.length, render: (p) => <span className="text-text-mid">{p.used_by.length}</span> },
    { key: 'owner', header: 'Owner', sortValue: (p) => p.owner, render: (p) => <span className="text-text-mid">{p.owner}</span> },
    {
      key: 'tags', header: 'Tags', sortValue: (p) => p.domain ?? '', render: (p) => (
        <span className="flex flex-wrap gap-1">
          {p.domain && <Badge tone="neutral">{p.domain}</Badge>}
          {p.risk_tier && <Badge tone="warn">{p.risk_tier}</Badge>}
          {!p.domain && !p.risk_tier && <span className="text-text-low">—</span>}
        </span>
      ),
    },
    {
      key: 'delete',
      header: '',
      align: 'center',
      render: (p) => {
        const inUse = p.used_by.length > 0;
        const blocked = inUse || !canApprove;
        return (
          <Tooltip content={inUse ? 'Referenced by an agent — deprecate instead of deleting.' : !canApprove ? 'Governance Officer only' : ''}>
            <button
              onClick={(e) => { e.stopPropagation(); if (!blocked) setPendingDelete(p); }}
              disabled={blocked}
              className="rounded p-1.5 text-text-low hover:bg-err/10 hover:text-err disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-text-low"
            >
              <Trash2 size={14} />
            </button>
          </Tooltip>
        );
      },
    },
  ];

  const domainOptions = useMemo(
    () => [...new Set(prompts.map((p) => p.domain).filter((d): d is string => !!d))].sort().map((d) => ({ value: d, label: d })),
    [prompts],
  );

  const filters: FilterDef<PromptAsset>[] = [
    { key: 'kind', label: 'Kind', options: KIND_OPTIONS.map((k) => ({ value: k, label: k })), predicate: (p, v) => p.kind === v },
    { key: 'category', label: 'Type', options: (['agent', 'tool', 'mcp', 'rag'] as PromptCategory[]).map((c) => ({ value: c, label: c })), predicate: (p, v) => p.category === v },
    { key: 'status', label: 'Status', options: (['draft', 'approved', 'deprecated'] as PromptStatus[]).map((s) => ({ value: s, label: s })), predicate: (p, v) => p.status === v },
    { key: 'domain', label: 'Domain', options: domainOptions, predicate: (p, v) => p.domain === v },
    { key: 'risk_tier', label: 'Risk tier', options: RISK_TIER_OPTIONS.map((r) => ({ value: r, label: r })), predicate: (p, v) => p.risk_tier === v },
    { key: 'agent_type', label: 'Agent type', options: AGENT_TYPE_OPTIONS.map((c) => ({ value: c, label: c })), predicate: (p, v) => p.agent_type === v },
  ];

  return (
    <div>
      <PageHeader
        title="Prompt Repository"
        description="Governed prompt assets with versions and used-by tracking. Referenced prompts deprecate, never delete."
        action={
          <div className="flex gap-2">
            <Button variant="subtle" icon={<Download size={14} />} onClick={() => api.exportApprovedPromptPack()}>Export approved pack</Button>
            <Button variant="new" icon={<Plus size={15} />} onClick={createPrompt}>New Prompt</Button>
          </div>
        }
      />
      {prompts.length === 0 ? (
        <EmptyState title="No prompts" message="Create a prompt asset to get started." action={<Button variant="primary" onClick={createPrompt}>New Prompt</Button>} />
      ) : (
        <DataTable columns={columns} rows={prompts} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/prompts/${p.id}`)} searchText={(p) => `${p.name} ${p.id} ${p.owner}`} searchPlaceholder="Search prompts…" filters={filters} initialSort={{ key: 'name', dir: 'asc' }} />
      )}
      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="Delete prompt?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)} disabled={deleting}>Cancel</Button>
            <Button variant="danger" icon={<Trash2 size={14} />} onClick={confirmDelete} disabled={deleting}>{deleting ? 'Deleting…' : 'Delete'}</Button>
          </>
        }
      >
        {pendingDelete && (
          <p className="text-[13px] text-text-mid">
            Are you sure you want to delete <span className="font-semibold text-text-hi">{pendingDelete.name}</span> {pendingDelete.version}? This cannot be undone.
          </p>
        )}
      </Modal>
    </div>
  );
}
