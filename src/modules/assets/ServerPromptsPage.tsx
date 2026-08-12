// Prompt Repository (server-backed): packs + immutable versions. Rollback is
// a NEW version copying older content — history never mutates.
import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, DataTable, EmptyState, Modal, type Column } from '@/components/primitives';
import {
  apiErrorMessage, promptsApi,
  type PromptComparison, type PromptUsage, type PromptUsageRef,
  type ServerPromptPack, type ServerPromptVersion,
} from '@/api/client';
import { diffLines, diffStats } from '@/modules/prompts/diff';
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

/** Where this prompt is referenced — computed server-side, never stored. */
function UsagePanel({ packId }: { packId: string }) {
  const [usage, setUsage] = useState<PromptUsage | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    promptsApi.usage(packId).then(setUsage).catch(() => setUsage(null));
  }, [packId]);

  if (!usage) return null;
  const row = (r: PromptUsageRef, i: number) => (
    <div key={`${r.reference_type}-${i}`} className="flex items-center justify-between border-t border-border py-1 text-[12px]">
      <span className="text-text-mid">
        <Badge tone="neutral">{r.reference_type.replace('_', ' ')}</Badge>{' '}
        {r.agent_name ?? r.agent_slug ?? '—'}
        {r.workflow_name && <span className="text-text-low"> · {r.workflow_name} v{r.workflow_version}</span>}
        {r.channel && <span className="text-text-low"> · {r.channel}</span>}
      </span>
      <span className="text-[11px] text-text-low">
        {r.version_policy ?? r.workflow_status ?? r.deployment_status}
        {r.pinned_version ? ` · pinned v${r.pinned_version}` : ''}
      </span>
    </div>
  );

  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2">Usage
          <Badge tone={usage.totals.active ? 'ok' : 'muted'}>{usage.totals.active} active</Badge>
          {usage.totals.historical > 0 && <Badge tone="muted">{usage.totals.historical} historical</Badge>}
        </span>}
        subtitle="Computed from bindings, workflow graphs, and deployment pins."
        action={<Button size="tiny" variant="ghost" onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide' : 'Show'}</Button>}
      />
      {open && (
        <div>
          {usage.totals.active === 0 && usage.totals.historical === 0 && (
            <div className="text-[12px] text-text-low">Not referenced anywhere yet.</div>
          )}
          {[...usage.active.bindings, ...usage.active.workflow_versions, ...usage.active.deployments].map(row)}
          {usage.totals.historical > 0 && (
            <>
              <div className="mt-2 text-[10px] uppercase tracking-wide text-text-low">Historical — not live</div>
              {[...usage.historical.workflow_versions, ...usage.historical.deployments].map(row)}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

/** Side-by-side version comparison over the immutable version rows. */
function ComparePanel({ packId, versions }: { packId: string; versions: ServerPromptVersion[] }) {
  const sorted = [...versions].sort((x, y) => x.version - y.version);
  const [a, setA] = useState(sorted[sorted.length - 2]?.version ?? sorted[0].version);
  const [b, setB] = useState(sorted[sorted.length - 1].version);
  const [result, setResult] = useState<PromptComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setError(null); setResult(null);
    try { setResult(await promptsApi.compare(packId, a, b)); }
    catch (e) { setError(apiErrorMessage(e)); }
  };

  const lines = result ? diffLines(result.a.content, result.b.content) : [];
  const stats = result ? diffStats(lines) : { added: 0, removed: 0 };

  return (
    <Card>
      <CardHeader title="Compare versions" subtitle="Read-only — comparing never creates a version." />
      <div className="flex flex-wrap items-center gap-2">
        <select className="h-8 rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
          value={a} onChange={(e) => setA(Number(e.target.value))}>
          {sorted.map((v) => <option key={v.id} value={v.version}>v{v.version}</option>)}
        </select>
        <span className="text-[12px] text-text-low">→</span>
        <select className="h-8 rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
          value={b} onChange={(e) => setB(Number(e.target.value))}>
          {sorted.map((v) => <option key={v.id} value={v.version}>v{v.version}</option>)}
        </select>
        <Button size="tiny" variant="subtle" onClick={run}>Compare</Button>
        {result && (
          <span className="text-[11px] text-text-low">
            <span className="text-ok">+{stats.added}</span>{' '}
            <span className="text-red-400">−{stats.removed}</span>
            {result.identical && ' · identical content'}
          </span>
        )}
      </div>
      {error && <div className="mt-2 text-[12px] text-red-400">{error}</div>}
      {result && (
        <div className="mt-2">
          {result.changed_fields.length > 0 && (
            <div className="mb-2 text-[11px] text-text-mid">
              Changed: {result.changed_fields.join(', ')}
            </div>
          )}
          <pre className="max-h-72 overflow-auto rounded-control border border-border bg-canvas p-2 text-[11px] leading-relaxed">
            {lines.map((l, i) => (
              <div key={i}
                className={l.op === 'added' ? 'text-ok' : l.op === 'removed' ? 'text-red-400' : 'text-text-mid'}>
                <span className="select-none text-text-low">
                  {l.op === 'added' ? '+ ' : l.op === 'removed' ? '− ' : '  '}
                </span>
                {l.text || ' '}
              </div>
            ))}
          </pre>
        </div>
      )}
    </Card>
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
          <div className="flex justify-end gap-2">
            <Button size="tiny" variant="new" onClick={() => { setDraft(versions[0]?.content ?? ''); setEditorOpen(true); }}>New version</Button>
          </div>
          <UsagePanel packId={pack.id} />
          {versions.length > 1 && <ComparePanel packId={pack.id} versions={versions} />}
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
