import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Tabs, Card, Badge, EmptyState, type TabItem } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { agentId, type KnowledgeSource } from '@/types';
import { Database } from 'lucide-react';
import { PipelineRunRow } from './PipelineRunRow';

export default function RagPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'indexes';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });
  const runs = useWorkspace((s) => s.pipelineRuns);

  const tabs: TabItem[] = [
    { key: 'indexes', label: 'Indexes' },
    { key: 'pipelines', label: 'Pipelines', count: runs.length },
  ];

  return (
    <div>
      <PageHeader title="RAG & Indexes" description="Vector indexes derived from knowledge sources, and the content pipeline runs that build them." />
      <Tabs items={tabs} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'indexes' ? <IndexesTab /> : <PipelinesTab />}
    </div>
  );
}

function PipelinesTab() {
  const runs = useWorkspace((s) => s.pipelineRuns);
  if (runs.length === 0) {
    return <EmptyState icon={<Database size={26} />} title="No pipeline runs" message="Trigger a refresh from a knowledge source to index it." />;
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
