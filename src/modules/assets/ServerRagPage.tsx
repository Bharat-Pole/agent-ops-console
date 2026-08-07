// RAG pipelines (server-backed) + retrieval preview. The mode banner is the
// server's honest answer: hybrid, or keyword_only with the reason.
import { useCallback, useEffect, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, EmptyState, Modal } from '@/components/primitives';
import {
  apiErrorMessage, knowledgeApi, ragApi,
  type RetrievalPreview, type ServerKnowledgeSource, type ServerRagPipeline,
} from '@/api/client';

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function ServerRagPage() {
  const [pipelines, setPipelines] = useState<ServerRagPipeline[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [preview, setPreview] = useState<{ pipeline: ServerRagPipeline; query: string; result: RetrievalPreview } | null>(null);
  const [queries, setQueries] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    ragApi.list().then(setPipelines).catch((e) => setError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const run = async (p: ServerRagPipeline) => {
    const q = queries[p.id]?.trim();
    if (!q) return;
    setError(null);
    try { setPreview({ pipeline: p, query: q, result: await ragApi.preview(p.id, q) }); }
    catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <div>
      <PageHeader title="RAG Pipelines" description="Retrieval configs over knowledge sources; score thresholds are enforced, not decorative."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>New Pipeline</Button>} />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}
      {pipelines === null ? <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
        : pipelines.length === 0 ? <EmptyState title="No pipelines" message="Create one over your uploaded knowledge sources." action={<Button variant="primary" onClick={() => setCreateOpen(true)}>New Pipeline</Button>} />
        : (
          <div className="flex flex-col gap-3">
            {pipelines.map((p) => (
              <Card key={p.id}>
                <CardHeader title={p.name}
                  subtitle={`${p.source_ids.length} sources · top_k ${p.top_k} · threshold ${p.score_threshold} · α ${p.hybrid_alpha}`} />
                <div className="flex gap-2">
                  <input className={INPUT} placeholder="Test a retrieval query…" value={queries[p.id] ?? ''}
                    onChange={(e) => setQueries((s) => ({ ...s, [p.id]: e.target.value }))}
                    onKeyDown={(e) => e.key === 'Enter' && run(p)} />
                  <Button variant="subtle" icon={<Search size={14} />} onClick={() => run(p)}>Preview</Button>
                </div>
                {preview?.pipeline.id === p.id && (
                  <div className="mt-3">
                    <div className="mb-2 flex items-center gap-2 text-[12px]">
                      <Badge tone={preview.result.mode === 'hybrid' ? 'ok' : 'warn'}>{preview.result.mode}</Badge>
                      {preview.result.mode_notes.map((n, i) => <span key={i} className="text-amber-400">{n}</span>)}
                    </div>
                    {preview.result.results.length === 0 ? (
                      <div className="text-[12px] text-text-low">No chunks above threshold for "{preview.query}".</div>
                    ) : preview.result.results.map((r) => (
                      <div key={r.chunk_id} className="mb-2 rounded-control border border-border bg-canvas p-2">
                        <div className="mb-1 flex justify-between text-[10px] text-text-low">
                          <span>{r.source} · {r.location}</span>
                          <span className="mono">score {r.score} (vec {r.vector_score} / kw {r.keyword_score})</span>
                        </div>
                        <div className="text-[12px] text-text-mid">{r.text}</div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New RAG pipeline" footer={null}>
        <CreatePipelineForm onDone={() => { setCreateOpen(false); load(); }} />
      </Modal>
    </div>
  );
}

function CreatePipelineForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('');
  const [sources, setSources] = useState<ServerKnowledgeSource[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    knowledgeApi.list().then(setSources).catch(() => setSources([]));
  }, []);

  const submit = async () => {
    setBusy(true); setError(null);
    try { await ragApi.create({ name, source_ids: [...selected] }); onDone(); }
    catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
        <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <div>
        <span className="mb-1 block text-[12px] text-text-mid">Knowledge sources</span>
        {sources.length === 0 && <div className="text-[12px] text-text-low">No sources uploaded yet.</div>}
        {sources.map((s) => (
          <label key={s.id} className="flex items-center gap-2 py-0.5 text-[13px] text-text-mid">
            <input type="checkbox" checked={selected.has(s.id)}
              onChange={(e) => setSelected((prev) => { const n = new Set(prev); e.target.checked ? n.add(s.id) : n.delete(s.id); return n; })} />
            {s.name} <span className="text-[11px] text-text-low">({s.embedded ? 'embedded' : 'keyword-only'})</span>
          </label>
        ))}
      </div>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end"><Button variant="primary" disabled={busy || !name || selected.size === 0} onClick={submit}>{busy ? 'Creating…' : 'Create'}</Button></div>
    </div>
  );
}
