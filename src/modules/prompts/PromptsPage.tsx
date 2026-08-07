import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button, DataTable, Badge, EmptyState, type Column, type FilterDef } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import type { PromptAsset, PromptCategory, PromptKind, PromptStatus } from '@/types';
import { titleCase } from '@/utils/format';

const KIND_TONE: Record<PromptKind, 'accent' | 'info' | 'warn' | 'neutral'> = { system: 'accent', safety: 'warn', citation: 'info', template: 'neutral' };
const STATUS_TONE: Record<PromptStatus, 'ok' | 'neutral' | 'muted'> = { approved: 'ok', draft: 'neutral', deprecated: 'muted' };

export default function PromptsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const prompts = useWorkspace((s) => s.prompts);
  const persona = useWorkspace((s) => s.ui.persona);

  const createPrompt = async () => {
    const id = await api.createPrompt({ name: 'New Prompt', kind: 'template', category: 'agent', owner: `${persona}@brightspeed.com` });
    if (id) navigate(`/prompts/${id}`);
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
  ];

  const filters: FilterDef<PromptAsset>[] = [
    { key: 'kind', label: 'Kind', options: (['system', 'safety', 'citation', 'template'] as PromptKind[]).map((k) => ({ value: k, label: k })), predicate: (p, v) => p.kind === v },
    { key: 'category', label: 'Type', options: (['agent', 'tool', 'mcp', 'rag'] as PromptCategory[]).map((c) => ({ value: c, label: c })), predicate: (p, v) => p.category === v },
    { key: 'status', label: 'Status', options: (['draft', 'approved', 'deprecated'] as PromptStatus[]).map((s) => ({ value: s, label: s })), predicate: (p, v) => p.status === v },
  ];

  return (
    <div>
      <PageHeader title="Prompt Repository" description="Governed prompt assets with versions and used-by tracking. Referenced prompts deprecate, never delete." action={<Button variant="new" icon={<Plus size={15} />} onClick={createPrompt}>New Prompt</Button>} />
      {prompts.length === 0 ? (
        <EmptyState title="No prompts" message="Create a prompt asset to get started." action={<Button variant="primary" onClick={createPrompt}>New Prompt</Button>} />
      ) : (
        <DataTable columns={columns} rows={prompts} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/prompts/${p.id}`)} searchText={(p) => `${p.name} ${p.id} ${p.owner}`} searchPlaceholder="Search prompts…" filters={filters} initialSort={{ key: 'name', dir: 'asc' }} />
      )}
    </div>
  );
}
