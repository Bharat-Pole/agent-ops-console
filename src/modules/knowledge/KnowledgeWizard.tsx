import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/primitives';
import { AssetWizard, type AssetPhase } from '@/modules/assets/AssetWizard';
import { useWorkspace } from '@/kernel/store';
import { audit } from '@/kernel/api';
import { prov, type KnowledgeSource, type RefreshCadence, type Sensitivity, type SourceApproval } from '@/types';

const SENSITIVITIES: Sensitivity[] = ['public', 'internal', 'confidential', 'restricted'];
const APPROVALS: SourceApproval[] = ['pending', 'approved', 'rejected'];
const CADENCES: RefreshCadence[] = ['manual', 'daily', 'weekly', 'monthly'];

interface KnowDraft {
  name: string;
  source_uri: string;
  parser: string;
  source_chunking: string;
  embedding_model: string;
  index_target: string;
  snippets_text: string; // "DOC-ID | text" per line
  sensitivity: Sensitivity;
  source_approval: SourceApproval;
  refresh_cadence: RefreshCadence;
}

const inputCls = 'w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring';

function parseSnippets(text: string) {
  return text.split('\n').map((line) => {
    const i = line.indexOf('|');
    if (i < 0) return null;
    return { doc_id: line.slice(0, i).trim(), text: line.slice(i + 1).trim() };
  }).filter((x): x is { doc_id: string; text: string } => !!x && !!x.doc_id && !!x.text);
}

export default function KnowledgeWizard() {
  const navigate = useNavigate();
  const nextId = useWorkspace((s) => s.nextId);
  const upsertSource = useWorkspace((s) => s.upsertSource);

  const initial: KnowDraft = {
    name: '', source_uri: '', parser: 'auto', source_chunking: 'recursive/800', embedding_model: 'vertex://text-embedding-004',
    index_target: 'vector://alloydb-main', snippets_text: '', sensitivity: 'internal', source_approval: 'pending', refresh_cadence: 'weekly',
  };

  const steps: AssetPhase<KnowDraft>[] = [
    {
      key: 'identity', label: 'Identity',
      validate: (d) => (!d.name.trim() ? 'Name the source.' : !d.source_uri.trim() ? 'Source URI is required.' : null),
      render: ({ draft, patch }) => (
        <div className="space-y-3">
          <Field label="Name"><input className={inputCls} value={draft.name} onChange={(e) => patch({ name: e.target.value })} placeholder="e.g. Incident DB (prod)" /></Field>
          <Field label="Source URI"><input className={inputCls} value={draft.source_uri} onChange={(e) => patch({ source_uri: e.target.value })} placeholder="gs://bucket/path/ or https://…" /></Field>
          <Field label="Parser"><input className={inputCls} value={draft.parser} onChange={(e) => patch({ parser: e.target.value })} /></Field>
        </div>
      ),
    },
    {
      key: 'chunk', label: 'Chunking & Embedding',
      render: ({ draft, patch }) => (
        <div className="space-y-3">
          <Field label="Chunking"><input className={inputCls} value={draft.source_chunking} onChange={(e) => patch({ source_chunking: e.target.value })} /></Field>
          <Field label="Embedding model"><input className={inputCls} value={draft.embedding_model} onChange={(e) => patch({ embedding_model: e.target.value })} /></Field>
          <Field label="Index target"><input className={inputCls} value={draft.index_target} onChange={(e) => patch({ index_target: e.target.value })} /></Field>
        </div>
      ),
    },
    {
      key: 'snippets', label: 'Snippets',
      render: ({ draft, patch }) => (
        <div className="space-y-2">
          <div className="text-[12px] text-text-mid">Paste grounding snippets, one per line as <span className="mono">DOC-ID | text</span>. These ground live RAG runs in the Playground.</div>
          <textarea className={inputCls} rows={6} value={draft.snippets_text} onChange={(e) => patch({ snippets_text: e.target.value })} placeholder={'INC-2026-0142 | Root cause was a config drift in the edge router.\nKB-0007 | PTO accrues at 1.5 days/month.'} />
          <div className="text-[11px] text-text-low">{parseSnippets(draft.snippets_text).length} snippet(s) parsed.</div>
        </div>
      ),
    },
    {
      key: 'gov', label: 'Governance & Review',
      render: ({ draft, patch }) => (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Sensitivity"><select className={inputCls} value={draft.sensitivity} onChange={(e) => patch({ sensitivity: e.target.value as Sensitivity })}>{SENSITIVITIES.map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
            <Field label="Approval"><select className={inputCls} value={draft.source_approval} onChange={(e) => patch({ source_approval: e.target.value as SourceApproval })}>{APPROVALS.map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
            <Field label="Refresh"><select className={inputCls} value={draft.refresh_cadence} onChange={(e) => patch({ refresh_cadence: e.target.value as RefreshCadence })}>{CADENCES.map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
          </div>
          <div className="rounded-control border border-border bg-raised/30 p-3 text-[12px] text-text-mid">
            <Row label="name"><span className="mono text-text-hi">{draft.name}</span></Row>
            <Row label="uri"><span className="mono text-[11px] break-all text-right">{draft.source_uri}</span></Row>
            <Row label="index"><span className="mono text-[11px]">{draft.index_target}</span></Row>
            <Row label="snippets">{parseSnippets(draft.snippets_text).length}</Row>
            <Row label="approval"><Badge tone={draft.source_approval === 'approved' ? 'ok' : 'warn'}>{draft.source_approval}</Badge></Row>
          </div>
          {draft.source_approval !== 'approved' && <div className="text-[11px] text-warn">Unapproved sources trip the Pre-Flight soft blocker until approved.</div>}
        </div>
      ),
    },
  ];

  const onRegister = (d: KnowDraft) => {
    const id = `src-${nextId('src')}`;
    const snippets = parseSnippets(d.snippets_text);
    const src: KnowledgeSource = {
      id, name: d.name.trim(),
      source_uri: prov(d.source_uri.trim(), 'user'),
      parser: prov(d.parser, 'user'),
      source_chunking: prov(d.source_chunking, 'user'),
      embedding_model: prov(d.embedding_model, 'user'),
      index_target: prov(d.index_target, 'user'),
      sensitivity: prov(d.sensitivity, 'user'),
      source_approval: prov(d.source_approval, 'user'),
      refresh_cadence: prov(d.refresh_cadence, 'user'),
      source_version: prov('v1', 'user'),
      document_count: snippets.length,
      index_size_mb: 0,
      used_by: [],
      snippets,
      ingestion: [],
    };
    upsertSource(src);
    audit('register_source', 'source', id, `Registered knowledge source "${d.name}" (${snippets.length} snippets).`);
    useWorkspace.getState().pushToast('ok', `Source "${d.name}" registered.`);
    navigate(`/knowledge/${id}`);
  };

  return (
    <AssetWizard<KnowDraft>
      title="Add a Knowledge Source"
      description="Onboard a knowledge source and its grounding snippets for RAG agents."
      breadcrumb={[{ label: 'Knowledge', to: '/knowledge' }, { label: 'New' }]}
      steps={steps}
      initial={initial}
      registerLabel="Register source"
      onRegister={onRegister}
    />
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><div className="mb-1 text-[11px] font-semibold uppercase text-text-low">{label}</div>{children}</label>;
}
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1 last:border-0"><span className="text-text-low">{label}</span><span className="text-text-hi">{children}</span></div>;
}
