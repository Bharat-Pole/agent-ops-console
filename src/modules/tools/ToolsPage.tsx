import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button, Badge, DataTable, type Column, type FilterDef } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { type ToolAsset } from '@/types';
import { Ban, Plus, Globe } from 'lucide-react';

export default function ToolsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const tools = useWorkspace((s) => s.tools);

  // LeftNav "Register Tool" lands here with ?new=1 → jump to the wizard.
  useEffect(() => {
    if (params.get('new') === '1') {
      params.delete('new');
      setParams(params, { replace: true });
      navigate('/tools/new');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: Column<ToolAsset>[] = [
    { key: 'name', header: 'Name', width: '20%', sortValue: (t) => t.name, render: (t) => <span className="mono text-text-hi">{t.name}</span> },
    { key: 'kind', header: 'Kind', sortValue: (t) => t.kind ?? 'catalog', render: (t) => t.kind === 'http_api' ? <Badge tone="accent"><Globe size={10} /> http {t.http?.method}</Badge> : <span className="text-[11px] text-text-low">catalog</span> },
    { key: 'category', header: 'Category', sortValue: (t) => t.category, render: (t) => <span className="text-text-mid">{t.category}</span> },
    { key: 'perm', header: 'Permission ceiling', sortValue: (t) => t.permission_ceiling, render: (t) => <Badge tone="info">{t.permission_ceiling}</Badge> },
    { key: 'write', header: 'Write', sortValue: (t) => (t.write_capable ? 1 : 0), render: (t) => t.write_capable ? <Badge tone="err"><Ban size={10} /> WRITE — advisory-block</Badge> : <span className="text-[11px] text-text-low">read-only</span> },
    { key: 'used', header: 'Used by', align: 'right', sortValue: (t) => t.used_by.length, render: (t) => <span className="text-text-mid">{t.used_by.length}</span> },
  ];
  const filters: FilterDef<ToolAsset>[] = [
    { key: 'write', label: 'Write', options: [{ value: 'yes', label: 'write-capable' }, { value: 'no', label: 'read-only' }], predicate: (t, v) => (v === 'yes' ? t.write_capable : !t.write_capable) },
    { key: 'kind', label: 'Kind', options: [{ value: 'http_api', label: 'http_api' }, { value: 'catalog', label: 'catalog' }], predicate: (t, v) => (t.kind ?? 'catalog') === v },
  ];

  return (
    <div>
      <PageHeader
        title="Tools"
        description="Advisory base scope: tool_permission ∈ {read, summarize, draft, recommend, validate}. Write-capable tools are catalogued for visibility but cannot be bound."
        action={<Button variant="new" icon={<Plus size={14} />} onClick={() => navigate('/tools/new')}>New Tool</Button>}
      />
      <DataTable columns={columns} rows={tools} rowKey={(t) => t.id} onRowClick={(t) => navigate(`/tools/${t.id}`)} searchText={(t) => `${t.name} ${t.category}`} searchPlaceholder="Search tools…" filters={filters} initialSort={{ key: 'name', dir: 'asc' }} />
    </div>
  );
}
