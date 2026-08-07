import { useNavigate, useParams } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Breadcrumbs } from '@/components/shell/Breadcrumbs';
import { Card, Button, Badge, EmptyState, Tooltip } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId } from '@/types';
import type { PromptCategory, PromptKind } from '@/types';
import { fmtDate, titleCase } from '@/utils/format';
import { Copy, GitBranch, CheckCircle2, Archive, Trash2, Sparkles, Save } from 'lucide-react';
import { useEffect, useState } from 'react';

const KIND_OPTIONS: PromptKind[] = ['system', 'safety', 'citation', 'template'];
const CATEGORY_OPTIONS: PromptCategory[] = ['agent', 'tool', 'mcp', 'rag'];
const inputCls = 'w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring';

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 text-[12px] font-medium text-text-mid">{children}</div>;
}

export default function PromptDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const prompt = useWorkspace((s) => s.prompts.find((p) => p.id === id));
  const agents = useWorkspace((s) => s.agents);
  const persona = useWorkspace((s) => s.ui.persona);
  const pushToast = useWorkspace((s) => s.pushToast);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [draftKind, setDraftKind] = useState<PromptKind>('template');
  const [draftCategory, setDraftCategory] = useState<PromptCategory>('agent');
  const [draftBody, setDraftBody] = useState('');
  const canApprove = persona === 'governance_officer';

  useEffect(() => {
    if (!prompt) return;
    setDraftName(prompt.name);
    setDraftKind(prompt.kind);
    setDraftCategory(prompt.category);
    setDraftBody(prompt.body);
  }, [prompt?.id, prompt?.version]);

  if (!prompt) {
    return <div><Breadcrumbs items={[{ label: 'Prompt Repository', to: '/prompts' }, { label: id ?? 'prompt' }]} /><EmptyState title="Prompt not found" action={<Button variant="primary" onClick={() => navigate('/prompts')}>Back</Button>} /></div>;
  }

  const isDraft = prompt.status === 'draft';
  const isDirty = isDraft && (draftName !== prompt.name || draftKind !== prompt.kind || draftCategory !== prompt.category || draftBody !== prompt.body);
  const usedByAgents = agents.filter((a) => prompt.used_by.includes(agentId(a)));
  const inUse = usedByAgents.length > 0;

  const copy = async () => { try { await navigator.clipboard.writeText(prompt.body); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { /* ignore */ } };

  const save = async () => {
    setBusy(true);
    await api.updatePromptFields(prompt.id, { name: draftName, kind: draftKind, category: draftCategory, body: draftBody });
    setBusy(false);
  };

  const generateWithAi = async () => {
    setBusy(true);
    const result = await api.generatePromptBody({ kind: draftKind, category: draftCategory, context: { objective: draftName } });
    setBusy(false);
    if (result) setDraftBody(result.body);
  };

  const newVersion = async () => { setBusy(true); await api.newPromptVersion(prompt.id); setBusy(false); };
  const approve = async () => { setBusy(true); await api.decidePrompt(prompt.id, 'approved'); setBusy(false); };
  const deprecate = async () => { setBusy(true); await api.deprecatePrompt(prompt.id); setBusy(false); };

  return (
    <div>
      <Breadcrumbs items={[{ label: 'Prompt Repository', to: '/prompts' }, { label: prompt.name }]} />
      <PageHeader title={prompt.name} description={`prompts://${prompt.id}@${prompt.version}`} badges={
        <span className="flex gap-1.5">
          <Badge tone="accent">{prompt.kind}</Badge>
          <Badge tone="neutral">{prompt.category}</Badge>
          <Badge tone={prompt.status === 'approved' ? 'ok' : prompt.status === 'deprecated' ? 'muted' : 'neutral'}>{titleCase(prompt.status)}</Badge>
          {prompt.source === 'llm_generated' && <Badge tone="info">AI-generated</Badge>}
        </span>
      }
        action={
          <div className="flex gap-2">
            <Button variant="subtle" icon={<GitBranch size={14} />} disabled={busy} onClick={newVersion}>New version</Button>
            {prompt.status !== 'approved' && <Tooltip content={canApprove ? '' : 'Governance Officer only'}><Button variant="primary" icon={<CheckCircle2 size={14} />} disabled={!canApprove || busy} onClick={approve}>Approve</Button></Tooltip>}
            {prompt.status === 'approved' && <Button variant="ghost" icon={<Archive size={14} />} disabled={busy} onClick={deprecate}>Deprecate</Button>}
          </div>
        }
      />
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 space-y-4">
          {isDraft ? (
            <Card>
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[13px] font-semibold text-text-hi">Edit draft</span>
                <Button variant="primary" size="sm" icon={<Save size={13} />} disabled={busy || !isDirty} onClick={save}>Save</Button>
              </div>
              <div className="space-y-3">
                <div>
                  <Label>Name</Label>
                  <input className={inputCls} value={draftName} onChange={(e) => setDraftName(e.target.value)} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Kind</Label>
                    <select className={inputCls} value={draftKind} onChange={(e) => setDraftKind(e.target.value as PromptKind)}>
                      {KIND_OPTIONS.map((k) => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label>Type</Label>
                    <select className={inputCls} value={draftCategory} onChange={(e) => setDraftCategory(e.target.value as PromptCategory)}>
                      {CATEGORY_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <Label>Body</Label>
                    <Button variant="subtle" size="tiny" icon={<Sparkles size={11} />} disabled={busy} onClick={generateWithAi}>Generate with AI</Button>
                  </div>
                  <textarea className={`${inputCls} mono`} rows={10} value={draftBody} onChange={(e) => setDraftBody(e.target.value)} placeholder="Prompt body…" />
                </div>
              </div>
            </Card>
          ) : (
            <Card>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[13px] font-semibold text-text-hi">Body</span>
                <Button variant="subtle" size="tiny" icon={<Copy size={11} />} onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>
              </div>
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-control border border-border bg-canvas p-3 mono text-[12px] text-text-hi">{prompt.body || '(empty)'}</pre>
            </Card>
          )}
        </div>
        <div className="space-y-4">
          <Card>
            <div className="mb-2 text-[13px] font-semibold text-text-hi">Used by</div>
            {usedByAgents.length ? usedByAgents.map((a) => (
              <button key={agentId(a)} onClick={() => navigate(`/agents/${agentId(a)}`)} className="block w-full rounded border border-border bg-raised/40 px-2 py-1 text-left text-[12px] text-text-hi hover:border-border-strong mb-1">{a.config.identity.agent_name.value}</button>
            )) : <div className="text-[12px] text-text-low">Not referenced by any agent.</div>}
            <div className="mt-2">
              <Tooltip content={inUse ? 'Referenced by an agent — deprecate instead of deleting.' : ''}>
                <Button variant="danger" size="sm" icon={<Trash2 size={13} />} disabled={inUse} onClick={() => pushToast('warn', 'Delete not implemented in demo.')}>Delete</Button>
              </Tooltip>
            </div>
          </Card>
          <Card>
            <div className="mb-2 text-[13px] font-semibold text-text-hi">Version history</div>
            <div className="space-y-2">
              {prompt.history.slice().reverse().map((h, i) => (
                <div key={i} className="flex gap-2 border-l-2 border-border pl-2.5 text-[12px]">
                  <span className="mono text-accent">{h.version}</span>
                  <div><div className="text-text-mid">{h.note}</div><div className="text-[10px] text-text-low">{fmtDate(h.date)}</div></div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
