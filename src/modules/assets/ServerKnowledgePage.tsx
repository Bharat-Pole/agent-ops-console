// Knowledge Base (server-backed): file upload → real chunking → embeddings
// when a provider exists. Retrieval mode labels are the server's truth —
// "keyword_only" means exactly that, never a pretend vector search.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, EmptyState } from '@/components/primitives';
import { apiErrorMessage, knowledgeApi, type ServerKnowledgeSource } from '@/api/client';
import { fmtDate } from '@/utils/format';

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function ServerKnowledgePage() {
  const [sources, setSources] = useState<ServerKnowledgeSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ServerKnowledgeSource | null>(null);

  const load = useCallback(() => {
    knowledgeApi.list().then(setSources).catch((e) => setError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  return (
    <div>
      <PageHeader title="Knowledge Base" description="Upload PDF/MD/TXT — parsed, chunked, and embedded (when an embedding provider is configured)." />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}
          {sources === null ? <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
            : sources.length === 0 ? <EmptyState title="No knowledge sources" message="Upload the first document." />
            : (
              <div className="flex flex-col gap-3">
                {sources.map((s) => (
                  <Card key={s.id}>
                    <CardHeader
                      title={<span className="flex items-center gap-2">{s.name}
                        <Badge tone={s.status === 'ready' ? 'ok' : s.status === 'failed' ? 'err' : 'warn'}>{s.status}</Badge>
                        <Badge tone={s.embedded ? 'accent' : 'muted'}>{s.embedded ? 'embedded' : 'keyword-only'}</Badge></span>}
                      subtitle={<span className="mono text-[11px]">{s.filename} · {s.chunk_count} chunks · {(s.bytes / 1024).toFixed(1)} KB · {s.sensitivity}</span>}
                      action={<Button size="tiny" variant="ghost" onClick={() => {
                        knowledgeApi.get(s.id).then(setExpanded).catch((e) => setError(apiErrorMessage(e)));
                      }}>Chunks</Button>}
                    />
                    <div className="text-[12px] text-text-low">{s.retrieval_mode} · {fmtDate(s.created_at)}</div>
                    {s.error && <div className="mt-1 text-[12px] text-amber-400">{s.error}</div>}
                  </Card>
                ))}
              </div>
            )}
          {expanded && (
            <Card className="mt-3">
              <CardHeader title={`Chunk preview — ${expanded.name}`} action={<Button size="tiny" variant="ghost" onClick={() => setExpanded(null)}>Close</Button>} />
              {(expanded.chunk_preview ?? []).map((c) => (
                <div key={c.ord} className="mb-2 rounded-control border border-border bg-canvas p-2">
                  <div className="mb-1 text-[10px] text-text-low">#{c.ord} · {String(c.meta.location ?? '')} · {c.has_embedding ? 'embedded' : 'no embedding'}</div>
                  <div className="text-[12px] text-text-mid">{c.text}</div>
                </div>
              ))}
            </Card>
          )}
        </div>
        <UploadCard onDone={load} />
      </div>
    </div>
  );
}

function UploadCard({ onDone }: { onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [sensitivity, setSensitivity] = useState('internal');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { setError('choose a file'); return; }
    setBusy(true); setError(null);
    try {
      await knowledgeApi.upload(file, name || file.name, sensitivity);
      setName(''); if (fileRef.current) fileRef.current.value = '';
      onDone();
    } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <Card>
      <CardHeader title="Upload source" subtitle="PDF, Markdown, or plain text (≤20MB)." />
      <div className="flex flex-col gap-3">
        <input ref={fileRef} type="file" accept=".pdf,.md,.txt" className="text-[12px] text-text-mid" />
        <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Display name</span>
          <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} placeholder="defaults to filename" /></label>
        <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Sensitivity</span>
          <select className={INPUT} value={sensitivity} onChange={(e) => setSensitivity(e.target.value)}>
            {['public', 'internal', 'confidential', 'restricted'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select></label>
        {error && <div className="text-[12px] text-red-400">{error}</div>}
        <Button variant="primary" icon={<Upload size={14} />} disabled={busy} onClick={submit}>{busy ? 'Uploading…' : 'Upload & ingest'}</Button>
      </div>
    </Card>
  );
}
