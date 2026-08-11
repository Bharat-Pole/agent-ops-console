import { useNavigate, useParams } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Breadcrumbs } from '@/components/shell/Breadcrumbs';
import { Card, Button, Badge, EmptyState, Tooltip, Modal } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId } from '@/types';
import type { PromptCategory, PromptKind, RiskTier, CapabilityTier } from '@/types';
import { fmtDate, titleCase } from '@/utils/format';
import { Copy, GitBranch, CheckCircle2, Archive, Trash2, Sparkles, Save, Scale, Undo2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { CompareVersionsDialog } from './CompareVersionsDialog';

const KIND_OPTIONS: PromptKind[] = [
  'system', 'user_template', 'task', 'persona', 'tool_use', 'citation', 'template', 'safety', 'refusal', 'escalation', 'stop_condition',
];
const CATEGORY_OPTIONS: PromptCategory[] = ['agent', 'tool', 'mcp', 'rag'];
const RISK_TIER_OPTIONS: RiskTier[] = ['low', 'medium', 'high', 'critical'];
const AGENT_TYPE_OPTIONS: CapabilityTier[] = ['minimal', 'standardized', 'advanced'];
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
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [draftKind, setDraftKind] = useState<PromptKind>('template');
  const [draftCategory, setDraftCategory] = useState<PromptCategory>('agent');
  const [draftBody, setDraftBody] = useState('');
  const [draftDomain, setDraftDomain] = useState('');
  const [draftUseCase, setDraftUseCase] = useState('');
  const [draftRiskTier, setDraftRiskTier] = useState<RiskTier | ''>('');
  const [draftAgentType, setDraftAgentType] = useState<CapabilityTier | ''>('');
  const [draftCitationFormat, setDraftCitationFormat] = useState('');
  const [compareSelection, setCompareSelection] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const canApprove = persona === 'governance_officer';

  useEffect(() => {
    if (!prompt) return;
    setDraftName(prompt.name);
    setDraftKind(prompt.kind);
    setDraftCategory(prompt.category);
    setDraftBody(prompt.body);
    setDraftDomain(prompt.domain ?? '');
    setDraftUseCase(prompt.use_case ?? '');
    setDraftRiskTier(prompt.risk_tier ?? '');
    setDraftAgentType(prompt.agent_type ?? '');
    setDraftCitationFormat(prompt.citation_format ?? '');
  }, [prompt?.id, prompt?.version]);

  if (!prompt) {
    return <div><Breadcrumbs items={[{ label: 'Prompt Repository', to: '/prompts' }, { label: id ?? 'prompt' }]} /><EmptyState title="Prompt not found" action={<Button variant="primary" onClick={() => navigate('/prompts')}>Back</Button>} /></div>;
  }

  const isDraft = prompt.status === 'draft';
  const isDirty = isDraft && (
    draftName !== prompt.name || draftKind !== prompt.kind || draftCategory !== prompt.category || draftBody !== prompt.body ||
    draftDomain !== (prompt.domain ?? '') || draftUseCase !== (prompt.use_case ?? '') ||
    draftRiskTier !== (prompt.risk_tier ?? '') || draftAgentType !== (prompt.agent_type ?? '') ||
    draftCitationFormat !== (prompt.citation_format ?? '')
  );
  const usedByAgents = agents.filter((a) => prompt.used_by.includes(agentId(a)));
  const inUse = usedByAgents.length > 0;

  const copy = async () => { try { await navigator.clipboard.writeText(prompt.body); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { /* ignore */ } };

  const save = async () => {
    setBusy(true);
    await api.updatePromptFields(prompt.id, {
      name: draftName, kind: draftKind, category: draftCategory, body: draftBody,
      domain: draftDomain || null, use_case: draftUseCase || null,
      risk_tier: draftRiskTier || null, agent_type: draftAgentType || null,
      citation_format: draftKind === 'citation' ? (draftCitationFormat || null) : prompt.citation_format,
    });
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
  const rollback = async (targetVersion: string) => { setBusy(true); await api.rollbackPrompt(prompt.id, targetVersion); setBusy(false); };

  const confirmDelete = async () => {
    setDeleting(true);
    const ok = await api.deletePrompt(prompt.id);
    setDeleting(false);
    if (ok) { setConfirmDeleteOpen(false); navigate('/prompts'); }
  };

  const toggleCompareSelect = (version: string) => {
    setCompareSelection((prev) => {
      if (prev.includes(version)) return prev.filter((v) => v !== version);
      if (prev.length >= 2) return [prev[1], version];
      return [...prev, version];
    });
  };

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
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Domain</Label>
                    <input className={inputCls} value={draftDomain} onChange={(e) => setDraftDomain(e.target.value)} placeholder="e.g. network_ops, HR, legal" />
                  </div>
                  <div>
                    <Label>Use case</Label>
                    <input className={inputCls} value={draftUseCase} onChange={(e) => setDraftUseCase(e.target.value)} placeholder="e.g. refund dispute resolution" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Risk tier</Label>
                    <select className={inputCls} value={draftRiskTier} onChange={(e) => setDraftRiskTier(e.target.value as RiskTier | '')}>
                      <option value="">—</option>
                      {RISK_TIER_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label>Agent type</Label>
                    <select className={inputCls} value={draftAgentType} onChange={(e) => setDraftAgentType(e.target.value as CapabilityTier | '')}>
                      <option value="">—</option>
                      {AGENT_TYPE_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                </div>
                {draftKind === 'citation' && (
                  <div>
                    <Label>Citation format (optional)</Label>
                    <input
                      className={`${inputCls} mono`}
                      value={draftCitationFormat}
                      onChange={(e) => setDraftCitationFormat(e.target.value)}
                      placeholder="e.g. ({doc_title}, source: {source_name})"
                    />
                    <div className="mt-1 text-[11px] text-text-low">
                      Real, mechanically applied to every system-generated citation for agents using this prompt. Placeholders: <span className="mono">{'{source_name} {source_id} {doc_id} {doc_title}'}</span>. Leave blank for the platform default <span className="mono">[source: kb://&lt;id&gt; · &lt;doc_id&gt;]</span>.
                    </div>
                  </div>
                )}
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
              {prompt.kind === 'citation' && (
                <div className="mt-2 text-[11px] text-text-low">
                  Citation format: <span className="mono text-text-mid">{prompt.citation_format || '[source: kb://<id> · <doc_id>] (platform default)'}</span>
                </div>
              )}
            </Card>
          )}
          {(prompt.domain || prompt.use_case || prompt.risk_tier || prompt.agent_type) && !isDraft && (
            <Card>
              <div className="mb-2 text-[13px] font-semibold text-text-hi">Tags</div>
              <div className="flex flex-wrap gap-1.5">
                {prompt.domain && <Badge tone="neutral">domain: {prompt.domain}</Badge>}
                {prompt.use_case && <Badge tone="neutral">use case: {prompt.use_case}</Badge>}
                {prompt.risk_tier && <Badge tone="warn">risk: {prompt.risk_tier}</Badge>}
                {prompt.agent_type && <Badge tone="info">agent type: {prompt.agent_type}</Badge>}
              </div>
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
              <Tooltip content={inUse ? 'Referenced by an agent — deprecate instead of deleting.' : !canApprove ? 'Governance Officer only' : ''}>
                <Button variant="danger" size="sm" icon={<Trash2 size={13} />} disabled={inUse || !canApprove} onClick={() => setConfirmDeleteOpen(true)}>Delete</Button>
              </Tooltip>
            </div>
          </Card>
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[13px] font-semibold text-text-hi">Version history</span>
              <Tooltip content={compareSelection.length === 2 ? '' : 'Select two versions to compare'}>
                <Button variant="subtle" size="tiny" icon={<Scale size={11} />} disabled={compareSelection.length !== 2} onClick={() => setCompareOpen(true)}>Compare</Button>
              </Tooltip>
            </div>
            <div className="space-y-2">
              {prompt.history.slice().reverse().map((h, i) => {
                const hasSnapshot = h.body !== undefined;
                const isCurrent = h.version === prompt.version;
                return (
                  <div key={i} className="flex items-start gap-2 border-l-2 border-border pl-2.5 text-[12px]">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={compareSelection.includes(h.version)}
                      disabled={!hasSnapshot}
                      onChange={() => toggleCompareSelect(h.version)}
                      title={hasSnapshot ? 'Select for compare' : 'No snapshot stored for this version'}
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="mono text-accent">{h.version}</span>
                        {!hasSnapshot && <Tooltip content="Recorded before version snapshotting shipped — no stored body."><span className="text-[10px] text-text-low">(no snapshot)</span></Tooltip>}
                      </div>
                      <div className="text-text-mid">{h.note}</div>
                      <div className="text-[10px] text-text-low">{fmtDate(h.date)}</div>
                    </div>
                    {!isCurrent && (
                      <Tooltip content={hasSnapshot ? `Roll back to ${h.version} (creates a new version)` : 'No snapshot stored for this version'}>
                        <Button variant="ghost" size="tiny" icon={<Undo2 size={11} />} disabled={!hasSnapshot || busy} onClick={() => rollback(h.version)} />
                      </Tooltip>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      </div>
      {compareSelection.length === 2 && (
        <CompareVersionsDialog
          open={compareOpen}
          onClose={() => setCompareOpen(false)}
          promptId={prompt.id}
          versionA={compareSelection[0]}
          versionB={compareSelection[1]}
        />
      )}
      <Modal
        open={confirmDeleteOpen}
        onClose={() => setConfirmDeleteOpen(false)}
        title="Delete prompt?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDeleteOpen(false)} disabled={deleting}>Cancel</Button>
            <Button variant="danger" icon={<Trash2 size={14} />} onClick={confirmDelete} disabled={deleting}>{deleting ? 'Deleting…' : 'Delete'}</Button>
          </>
        }
      >
        <p className="text-[13px] text-text-mid">
          Are you sure you want to delete <span className="font-semibold text-text-hi">{prompt.name}</span> {prompt.version}? This cannot be undone.
        </p>
      </Modal>
    </div>
  );
}
