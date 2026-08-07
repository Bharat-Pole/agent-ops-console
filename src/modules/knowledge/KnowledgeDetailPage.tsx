import { useParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Button, EmptyState } from '@/components/primitives';
import { SchemaFieldRow } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { type Prov } from '@/types';
import { ArrowLeft, RefreshCw, Loader2, Database } from 'lucide-react';
import { PipelineRunRow } from '@/modules/rag/PipelineRunRow';

const G512_FIELDS = ['source_uri', 'parser', 'source_chunking', 'embedding_model', 'index_target', 'sensitivity', 'source_approval', 'refresh_cadence', 'source_version'];

export default function KnowledgeDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const sel = useWorkspace((s) => s.sources.find((x) => x.id === id));
  const runs = useWorkspace((s) => s.pipelineRuns);
  const jobs = useWorkspace((s) => s.jobs);

  if (!sel) {
    return (
      <div>
        <PageHeader title="Knowledge source" description="" />
        <EmptyState icon={<Database size={26} />} title="Source not found" message="This source id doesn't exist." />
        <Button className="mt-3" variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate('/knowledge')}>Back to Knowledge</Button>
      </div>
    );
  }

  const refreshing = jobs.some((j) => j.entity_id === sel.id && j.status !== 'completed');

  return (
    <div>
      <PageHeader
        title={sel.name}
        description={`${sel.document_count.toLocaleString()} docs · ${sel.index_size_mb} MB`}
        action={
          <div className="flex gap-2">
            <Button variant="subtle" size="sm" icon={refreshing ? <Loader2 size={13} className="animate-spin-slow" /> : <RefreshCw size={13} />} onClick={() => api.triggerPipeline(sel.id)}>Trigger refresh</Button>
            <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate('/knowledge')}>Back</Button>
          </div>
        }
      />
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-1 text-[12px] font-semibold text-text-hi">5.12 Knowledge Source config</div>
          <div className="rounded-card border border-border bg-surface px-3 py-1">
            {G512_FIELDS.map((f) => <SchemaFieldRow key={f} field={f} prov={(sel as unknown as Record<string, Prov<unknown>>)[f]} />)}
          </div>
        </Card>
        <Card>
          <div className="mb-2 text-[12px] font-semibold text-text-hi">Pipeline runs</div>
          {runs.filter((r) => r.source_id === sel.id).length
            ? runs.filter((r) => r.source_id === sel.id).map((r) => <PipelineRunRow key={r.id} run={r} compact />)
            : <span className="text-[12px] text-text-low">No runs yet — trigger a refresh.</span>}
        </Card>
      </div>
    </div>
  );
}
