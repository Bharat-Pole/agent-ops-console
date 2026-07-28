import { useNavigate, useParams } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Breadcrumbs } from '@/components/shell/Breadcrumbs';
import { Card, Button, Badge, EmptyState, Tooltip } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { audit, nowIso } from '@/kernel/api';
import { agentId } from '@/types';
import { fmtDate, titleCase } from '@/utils/format';
import { Copy, GitBranch, CheckCircle2, Archive, Trash2 } from 'lucide-react';
import { useState } from 'react';

function bumpVersion(v: string): string {
  const m = /^v(\d+)(?:\.(\d+))?$/.exec(v);
  if (!m) return v + '-next';
  if (m[2] !== undefined) return `v${m[1]}.${Number(m[2]) + 1}`;
  return `v${Number(m[1]) + 1}`;
}

export default function PromptDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const prompt = useWorkspace((s) => s.prompts.find((p) => p.id === id));
  const agents = useWorkspace((s) => s.agents);
  const upsertPrompt = useWorkspace((s) => s.upsertPrompt);
  const persona = useWorkspace((s) => s.ui.persona);
  const pushToast = useWorkspace((s) => s.pushToast);
  const [copied, setCopied] = useState(false);
  const canApprove = persona === 'governance_officer';

  if (!prompt) {
    return <div><Breadcrumbs items={[{ label: 'Prompt Repository', to: '/prompts' }, { label: id ?? 'prompt' }]} /><EmptyState title="Prompt not found" action={<Button variant="primary" onClick={() => navigate('/prompts')}>Back</Button>} /></div>;
  }

  const usedByAgents = agents.filter((a) => prompt.used_by.includes(agentId(a)));
  const inUse = usedByAgents.length > 0;

  const copy = async () => { try { await navigator.clipboard.writeText(prompt.body); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { /* ignore */ } };
  const newVersion = () => { const nv = bumpVersion(prompt.version); upsertPrompt({ ...prompt, version: nv, status: 'draft', history: [...prompt.history, { version: nv, date: nowIso().slice(0, 10), note: 'New version drafted.' }] }); audit('new_version', 'prompt', prompt.id, `Drafted ${nv}.`); pushToast('ok', `Drafted ${nv}.`); };
  const approve = () => { upsertPrompt({ ...prompt, status: 'approved' }); audit('approve', 'prompt', prompt.id, `Approved ${prompt.version}.`); pushToast('ok', 'Prompt approved.'); };
  const deprecate = () => { upsertPrompt({ ...prompt, status: 'deprecated' }); audit('deprecate', 'prompt', prompt.id, `Deprecated ${prompt.version}.`); pushToast('info', 'Prompt deprecated.'); };

  return (
    <div>
      <Breadcrumbs items={[{ label: 'Prompt Repository', to: '/prompts' }, { label: prompt.name }]} />
      <PageHeader title={prompt.name} description={`prompts://${prompt.id}@${prompt.version}`} badges={<span className="flex gap-1.5"><Badge tone="accent">{prompt.kind}</Badge><Badge tone={prompt.status === 'approved' ? 'ok' : prompt.status === 'deprecated' ? 'muted' : 'neutral'}>{titleCase(prompt.status)}</Badge></span>}
        action={
          <div className="flex gap-2">
            <Button variant="subtle" icon={<GitBranch size={14} />} onClick={newVersion}>New version</Button>
            {prompt.status !== 'approved' && <Tooltip content={canApprove ? '' : 'Governance Officer only'}><Button variant="primary" icon={<CheckCircle2 size={14} />} disabled={!canApprove} onClick={approve}>Approve</Button></Tooltip>}
            {prompt.status === 'approved' && <Button variant="ghost" icon={<Archive size={14} />} onClick={deprecate}>Deprecate</Button>}
          </div>
        }
      />
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 space-y-4">
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[13px] font-semibold text-text-hi">Body</span>
              <Button variant="subtle" size="tiny" icon={<Copy size={11} />} onClick={copy}>{copied ? 'Copied' : 'Copy'}</Button>
            </div>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-control border border-border bg-canvas p-3 mono text-[12px] text-text-hi">{prompt.body || '(empty)'}</pre>
          </Card>
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
