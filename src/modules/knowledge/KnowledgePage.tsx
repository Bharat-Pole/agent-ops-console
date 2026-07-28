import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Tabs, Card, Button, Badge, DataTable, Drawer, EmptyState, type Column, type TabItem } from '@/components/primitives';
import { SchemaFieldRow } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, type KnowledgeSource, type PipelineRun, type Prov } from '@/types';
import { titleCase } from '@/utils/format';
import { RefreshCw, Database, Loader2, CheckCircle2, Circle } from 'lucide-react';
import { cn } from '@/utils/cn';

const G512_FIELDS = ['source_uri', 'parser', 'source_chunking', 'embedding_model', 'index_target', 'sensitivity', 'source_approval', 'refresh_cadence', 'source_version'];

export default function KnowledgePage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'sources';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });
  const sources = useWorkspace((s) => s.sources);
  const runs = useWorkspace((s) => s.pipelineRuns);

  const tabs: TabItem[] = [
    { key: 'sources', label: 'Sources', count: sources.length },
    { key: 'pipelines', label: 'Pipelines', count: runs.length },
    { key: 'indexes', label: 'Indexes' },
  ];

  return (
    <div>
      <PageHeader title="Knowledge & RAG" description="Sources (the 5.12 ingestion config), pipeline runs, and vector indexes that feed grounded agents." />
      <Tabs items={tabs} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'sources' && <SourcesTab />}
      {tab === 'pipelines' && <PipelinesTab />}
      {tab === 'indexes' && <IndexesTab />}
    </div>
  );
}

function SourcesTab() {
  const sources = useWorkspace((s) => s.sources);
  const runs = useWorkspace((s) => s.pipelineRuns);
  const jobs = useWorkspace((s) => s.jobs);
  const [selected, setSelected] = useState<KnowledgeSource | null>(null);
  const sel = useWorkspace((s) => s.sources.find((x) => x.id === selected?.id)) ?? null;

  const columns: Column<KnowledgeSource>[] = [
    { key: 'name', header: 'Name', sortValue: (s) => s.name, render: (s) => <div><div className="font-medium text-text-hi">{s.name}</div><div className="mono text-[10px] text-text-low">{s.source_uri.value}</div></div> },
    { key: 'parser', header: 'Parser', render: (s) => <span className="text-text-mid">{s.parser.value}</span> },
    { key: 'sensitivity', header: 'Sensitivity', sortValue: (s) => s.sensitivity.value, render: (s) => <Badge tone={s.sensitivity.value === 'restricted' ? 'err' : s.sensitivity.value === 'confidential' ? 'warn' : 'neutral'}>{s.sensitivity.value}</Badge> },
    { key: 'approval', header: 'Approval', render: (s) => <Badge tone={s.source_approval.value === 'approved' ? 'ok' : 'warn'}>{s.source_approval.value}</Badge> },
    { key: 'cadence', header: 'Refresh', render: (s) => <span className="text-text-mid">{s.refresh_cadence.value}</span> },
    { key: 'docs', header: 'Docs', align: 'right', sortValue: (s) => s.document_count, render: (s) => <span className="text-text-mid">{s.document_count.toLocaleString()}</span> },
  ];

  if (sources.length === 0) {
    return <EmptyState icon={<Database size={26} />} title="No knowledge sources" message="Add a knowledge source to feed grounded agents." />;
  }
  return (
    <div>
      <DataTable columns={columns} rows={sources} rowKey={(s) => s.id} onRowClick={(s) => setSelected(s)} searchText={(s) => `${s.name} ${s.source_uri.value}`} searchPlaceholder="Search sources…" initialSort={{ key: 'name', dir: 'asc' }} />
      <Drawer open={!!sel} onClose={() => setSelected(null)} title={sel?.name} subtitle={`${sel?.document_count.toLocaleString()} docs · ${sel?.index_size_mb} MB`}>
        {sel && (
          <div className="space-y-4">
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[12px] font-semibold text-text-hi">5.12 Knowledge Source config</span>
                <Button variant="subtle" size="sm" icon={jobs.some((j) => j.entity_id === sel.id && j.status !== 'completed') ? <Loader2 size={12} className="animate-spin-slow" /> : <RefreshCw size={12} />} onClick={() => api.triggerPipeline(sel.id)}>Trigger refresh</Button>
              </div>
              <div className="rounded-card border border-border bg-surface px-3 py-1">
                {G512_FIELDS.map((f) => <SchemaFieldRow key={f} field={f} prov={(sel as unknown as Record<string, Prov<unknown>>)[f]} />)}
              </div>
            </div>
            <div>
              <div className="mb-1 text-[12px] font-semibold text-text-hi">Pipeline runs</div>
              {runs.filter((r) => r.source_id === sel.id).map((r) => <PipelineRunRow key={r.id} run={r} compact />)}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function StageDot({ status }: { status: PipelineRun['stages'][number]['status'] }) {
  if (status === 'ready') return <CheckCircle2 size={14} className="text-ok" />;
  if (status === 'in_progress') return <Loader2 size={14} className="animate-spin-slow text-warn" />;
  return <Circle size={12} className="text-border-strong" />;
}

function PipelineRunRow({ run, compact }: { run: PipelineRun; compact?: boolean }) {
  const sources = useWorkspace((s) => s.sources);
  const src = sources.find((s) => s.id === run.source_id);
  return (
    <div className={cn('rounded-card border border-border bg-surface p-3', !compact && 'mb-2')}>
      <div className="mb-2 flex items-center justify-between text-[12px]">
        <span className="font-medium text-text-hi">{src?.name ?? run.source_id} <span className="mono text-[10px] text-text-low">· {run.trigger}</span></span>
        <Badge tone={run.overall === 'ready' ? 'ok' : run.overall === 'in_progress' ? 'warn' : 'neutral'}>{titleCase(run.overall)}</Badge>
      </div>
      <div className="flex items-center gap-1 overflow-x-auto">
        {run.stages.map((st, i) => (
          <div key={st.name} className="flex items-center">
            <div className="flex min-w-[74px] flex-col items-center rounded border border-border/60 px-1.5 py-1">
              <StageDot status={st.status} />
              <span className="mt-0.5 text-[10px] text-text-mid">{st.name}</span>
              {st.items != null && <span className="text-[9px] text-text-low">{st.items.toLocaleString()}</span>}
            </div>
            {i < run.stages.length - 1 && <span className="mx-0.5 text-text-low">›</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function PipelinesTab() {
  const runs = useWorkspace((s) => s.pipelineRuns);
  if (runs.length === 0) {
    return <EmptyState icon={<Database size={26} />} title="No pipeline runs" message="Trigger a refresh from the Sources tab to index a knowledge source." />;
  }
  return <div>{runs.map((r) => <PipelineRunRow key={r.id} run={r} />)}</div>;
}

function IndexesTab() {
  const navigate = useNavigate();
  const sources = useWorkspace((s) => s.sources);
  const agents = useWorkspace((s) => s.agents);

  const indexes = new Map<string, { sizeMb: number; sources: KnowledgeSource[]; embedding: string }>();
  for (const s of sources) {
    const idx = s.index_target.value;
    if (!indexes.has(idx)) indexes.set(idx, { sizeMb: 0, sources: [], embedding: s.embedding_model.value });
    const e = indexes.get(idx)!;
    e.sizeMb += s.index_size_mb;
    e.sources.push(s);
  }
  // DEMO index (Section 6.5)
  indexes.set('vector://alloydb-demo', { sizeMb: 0, sources: [], embedding: 'vertex://text-embedding-004' });

  return (
    <div className="grid grid-cols-3 gap-4">
      {[...indexes.entries()].map(([idx, e]) => {
        const isDemo = idx === 'vector://alloydb-demo';
        const consumers = agents.filter((a) => a.config.data.knowledge_source_refs.value.some((r) => e.sources.some((s) => r.includes(s.id))));
        return (
          <Card key={idx} className={isDemo ? 'border-info/40' : ''}>
            <div className="mb-2 flex items-center gap-2">
              <Database size={15} className="text-accent" />
              <span className="mono text-[12px] text-text-hi">{idx}</span>
              {isDemo && <Badge tone="info">DEMO</Badge>}
            </div>
            {isDemo ? (
              <p className="text-[12px] text-text-low">Synthetic index used by Demo Mode. Purged when a real content job completes for the agent.</p>
            ) : (
              <div className="space-y-1 text-[12px]">
                <div className="flex justify-between"><span className="text-text-low">size</span><span className="text-text-hi">{e.sizeMb} MB</span></div>
                <div className="flex justify-between"><span className="text-text-low">embedding</span><span className="mono text-[10px] text-text-mid">{e.embedding}</span></div>
                <div className="mt-1 text-text-low">sources: {e.sources.map((s) => s.name).join(', ')}</div>
                <div className="text-text-low">consumers: {consumers.length ? consumers.map((a) => <button key={agentId(a)} onClick={() => navigate(`/agents/${agentId(a)}`)} className="text-accent hover:underline mr-1">{a.config.identity.agent_name.value}</button>) : 'none'}</div>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
