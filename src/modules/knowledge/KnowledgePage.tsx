import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button, Badge, DataTable, EmptyState, type Column } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { type KnowledgeSource } from '@/types';
import { Database, Plus } from 'lucide-react';

export default function KnowledgePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const sources = useWorkspace((s) => s.sources);

  useEffect(() => {
    if (params.get('new') === '1') {
      params.delete('new');
      setParams(params, { replace: true });
      navigate('/knowledge/new');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns: Column<KnowledgeSource>[] = [
    { key: 'name', header: 'Name', sortValue: (s) => s.name, render: (s) => <div><div className="font-medium text-text-hi">{s.name}</div><div className="mono text-[10px] text-text-low">{s.source_uri.value}</div></div> },
    { key: 'parser', header: 'Parser', render: (s) => <span className="text-text-mid">{s.parser.value}</span> },
    { key: 'sensitivity', header: 'Sensitivity', sortValue: (s) => s.sensitivity.value, render: (s) => <Badge tone={s.sensitivity.value === 'restricted' ? 'err' : s.sensitivity.value === 'confidential' ? 'warn' : 'neutral'}>{s.sensitivity.value}</Badge> },
    { key: 'approval', header: 'Approval', render: (s) => <Badge tone={s.source_approval.value === 'approved' ? 'ok' : 'warn'}>{s.source_approval.value}</Badge> },
    { key: 'cadence', header: 'Refresh', render: (s) => <span className="text-text-mid">{s.refresh_cadence.value}</span> },
    { key: 'docs', header: 'Docs', align: 'right', sortValue: (s) => s.document_count, render: (s) => <span className="text-text-mid">{s.document_count.toLocaleString()}</span> },
  ];

  return (
    <div>
      <PageHeader
        title="Knowledge"
        description="Knowledge sources (the 5.12 ingestion config) that feed grounded agents. Pipelines & indexes live under RAG & Indexes."
        action={<Button variant="new" icon={<Plus size={14} />} onClick={() => navigate('/knowledge/new')}>Add Knowledge Source</Button>}
      />
      {sources.length === 0 ? (
        <EmptyState icon={<Database size={26} />} title="No knowledge sources" message="Add a knowledge source to feed grounded agents." />
      ) : (
        <DataTable columns={columns} rows={sources} rowKey={(s) => s.id} onRowClick={(s) => navigate(`/knowledge/${s.id}`)} searchText={(s) => `${s.name} ${s.source_uri.value}`} searchPlaceholder="Search sources…" initialSort={{ key: 'name', dir: 'asc' }} />
      )}
    </div>
  );
}
