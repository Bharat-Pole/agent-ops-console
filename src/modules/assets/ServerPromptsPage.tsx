// Prompt Repository (server-backed): packs + immutable versions. Rollback is
// a NEW version copying older content — history never mutates.
import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, DataTable, EmptyState, Modal, type Column } from '@/components/primitives';
import { apiErrorMessage, promptsApi, type ServerPromptPack, type ServerPromptVersion } from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

const STATUS_TONE: Record<string, 'ok' | 'warn' | 'muted' | 'err' | 'neutral'> = {
  draft: 'muted', pending_approval: 'warn', approved: 'ok', rejected: 'err', deprecated: 'muted',
};
const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';
const AREA = 'min-h-[140px] w-full rounded-control border border-border bg-canvas px-2.5 py-2 mono text-[12px] text-text-hi outline-none focus:border-border-strong';

export default function ServerPromptsPage() {
  const [packs, setPacks] = useState<ServerPromptPack[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [openPack, setOpenPack] = useState<ServerPromptPack | null>(null);

  const load = useCallback(() => {
    promptsApi.list().then(setPacks).catch((e) => setError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const columns: Column<ServerPromptPack>[] = [
    { key: 'name', header: 'Pack', width: '30%', sortValue: (p) => p.name.toLowerCase(),
      render: (p) => <div className="flex flex-col"><span className="font-medium text-text-hi">{p.name}</span><span className="mono text-[10px] text-text-low">{p.slug}</span></div> },
    { key: 'type', header: 'Type', sortValue: (p) => p.prompt_type, render: (p) => <span className="text-text-mid">{titleCase(p.prompt_type)}</span> },
    { key: 'latest', header: 'Latest', render: (p) => <span className="mono text-text-mid">v{p.latest_version ?? 0}</span> },
    { key: 'status', header: 'Latest status', render: (p) => p.latest_status ? <Badge tone={STATUS_TONE[p.latest_status]}>{titleCase(p.latest_status)}</Badge> : <span className="text-text-low">—</span> },
    { key: 'approved', header: 'Approved', render: (p) => <span className="text-text-mid">{p.approved_version ? `v${p.approved_version}` : 'none'}</span> },
    { key: 'created', header: 'Created', align: 'right', sortValue: (p) => p.created_at, render: (p) => <span className="text-text-low">{fmtDate(p.created_at)}</span> },
  ];

  return (
    <div>
      <PageHeader title="Prompt Repository" description="Immutable versions with approval workflow; rollback creates a new version."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>New Pack</Button>} />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}
      {packs === null ? <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
        : packs.length === 0 ? <EmptyState title="No prompt packs" message="Create one, or accept a recommendation's prompt component." action={<Button variant="primary" onClick={() => setCreateOpen(true)}>New Pack</Button>} />
        : <DataTable columns={columns} rows={packs} rowKey={(p) => p.id} onRowClick={setOpenPack} searchText={(p) => `${p.name} ${p.slug} ${p.prompt_type}`} searchPlaceholder="Search packs…" />}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New prompt pack" footer={null} width="max-w-2xl">
        <CreatePackForm onDone={() => { setCreateOpen(false); load(); }} />
      </Modal>
      {openPack && <PackDetailModal packId={openPack.id} onClose={() => { setOpenPack(null); load(); }} />}
    </div>
  );
}

function CreatePackForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState('task');
  const [content, setContent] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setError(null);
    try { await promptsApi.create({ name, prompt_type: type, content }); onDone(); }
    catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
        <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Type</span>
        <select className={INPUT} value={type} onChange={(e) => setType(e.target.value)}>
          {['system', 'persona', 'task', 'chain_of_thought', 'few_shot', 'guardrail', 'citation', 'refusal', 'output_format', 'evaluation_rubric'].map((t) => <option key={t} value={t}>{t}</option>)}
        </select></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Content (v1)</span>
        <textarea className={AREA} value={content} onChange={(e) => setContent(e.target.value)} /></label>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end"><Button variant="primary" disabled={busy || !name || !content} onClick={submit}>{busy ? 'Creating…' : 'Create'}</Button></div>
    </div>
  );
}

function PackDetailModal({ packId, onClose }: { packId: string; onClose: () => void }) {
  const [pack, setPack] = useState<ServerPromptPack | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState('');

  const load = useCallback(() => {
    promptsApi.get(packId).then((p) => setPack(p)).catch((e) => setError(apiErrorMessage(e)));
  }, [packId]);
  useEffect(load, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); load(); } catch (e) { setError(apiErrorMessage(e)); }
  };

  const versions: ServerPromptVersion[] = pack?.versions ?? [];
  return (
    <Modal open onClose={onClose} title={pack ? `${pack.name}` : 'Loading…'} width="max-w-3xl" footer={null}>
      {error && <div className="mb-2 text-[12px] text-red-400">{error}</div>}
      {pack && (
        <div className="flex flex-col gap-3">
          <div className="flex justify-end">
            <Button size="tiny" variant="new" onClick={() => { setDraft(versions[0]?.content ?? ''); setEditorOpen(true); }}>New version</Button>
          </div>
          {editorOpen && (
            <Card>
              <CardHeader title="New version content" />
              <textarea className={AREA} value={draft} onChange={(e) => setDraft(e.target.value)} />
              <div className="mt-2 flex justify-end gap-2">
                <Button size="tiny" variant="ghost" onClick={() => setEditorOpen(false)}>Cancel</Button>
                <Button size="tiny" variant="primary" disabled={!draft.trim()}
                  onClick={() => act(async () => { await promptsApi.newVersion(pack.id, draft); setEditorOpen(false); })}>Save as new version</Button>
              </div>
            </Card>
          )}
          {versions.map((v) => (
            <Card key={v.id}>
              <CardHeader
                title={<span className="flex items-center gap-2">v{v.version} <Badge tone={STATUS_TONE[v.status]}>{titleCase(v.status)}</Badge>
                  {v.rolled_back_from && <span className="text-[11px] text-text-low">rollback of v{v.rolled_back_from}</span>}</span>}
                subtitle={fmtDate(v.created_at)}
                action={<div className="flex gap-1">
                  {v.status === 'draft' && <Button size="tiny" variant="primary" onClick={() => act(() => promptsApi.submit(pack.id, v.version))}>Submit</Button>}
                  <Button size="tiny" variant="ghost" onClick={() => act(() => promptsApi.rollback(pack.id, v.version))}>Rollback to this</Button>
                </div>}
              />
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-control border border-border bg-canvas p-2 text-[11px] text-text-mid">{v.content}</pre>
            </Card>
          ))}
        </div>
      )}
    </Modal>
  );
}
