// A2A Directory (server-backed) — replaces the legacy in-browser-kernel page.
// Cards are governed assets tied to a real agent; readiness is computed by the
// server from lifecycle/workflow/deployment state, so this page only renders
// verdicts. Handoff validation here is read-only: it never executes anything.
import { useCallback, useEffect, useState } from 'react';
import { Plus, Search, Radar } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import {
  Badge, Button, Card, CardHeader, ComboBox, EmptyState, Modal, type ComboOption,
} from '@/components/primitives';
import {
  a2aApi, agentsApi, apiErrorMessage,
  type AgentCardBody, type HandoffDecision, type ServerAgent, type ServerAgentCard,
} from '@/api/client';
import { titleCase } from '@/utils/format';

const STATUS_TONE: Record<string, 'ok' | 'warn' | 'muted' | 'err' | 'neutral'> = {
  draft: 'muted', pending_approval: 'warn', approved: 'ok', rejected: 'err', deprecated: 'muted',
};
const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function ServerA2APage() {
  const [cards, setCards] = useState<ServerAgentCard[] | null>(null);
  const [agents, setAgents] = useState<ServerAgent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [createFor, setCreateFor] = useState<string>('');
  const [createOpen, setCreateOpen] = useState(false);
  const [skill, setSkill] = useState('');
  const [discovered, setDiscovered] = useState<ServerAgentCard[] | null>(null);

  const load = useCallback(() => {
    a2aApi.list().then(setCards).catch((e) => setError(apiErrorMessage(e)));
    agentsApi.list().then(setAgents).catch(() => setAgents([]));
  }, []);
  useEffect(load, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); load(); } catch (e) { setError(apiErrorMessage(e)); }
  };

  const runDiscover = async () => {
    setError(null);
    try { setDiscovered(await a2aApi.discover(skill ? { skill } : undefined)); }
    catch (e) { setError(apiErrorMessage(e)); }
  };

  const agentOptions: ComboOption[] = agents.map((a) => ({ value: a.id, label: a.name, hint: a.slug }));

  return (
    <div>
      <PageHeader
        title="A2A Directory"
        description="Agent cards declare how an agent may be called by another. Discovery and handoff checks are read-only."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>New card</Button>}
      />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {cards === null ? <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
            : cards.length === 0 ? (
              <EmptyState title="No agent cards yet"
                message="Create a card for an agent to declare its A2A contract." />
            ) : (
              <div className="flex flex-col gap-3">
                {cards.map((c) => (
                  <Card key={c.id}>
                    <CardHeader
                      title={<span className="flex flex-wrap items-center gap-2">
                        {c.agent_name ?? c.agent_slug}
                        <span className="mono text-[11px] text-text-low">v{c.version}</span>
                        <Badge tone={STATUS_TONE[c.status] ?? 'muted'}>{titleCase(c.status)}</Badge>
                        <Badge tone="neutral">{c.capability_tier}</Badge>
                        {c.readiness?.discoverable && <Badge tone="ok">discoverable</Badge>}
                      </span>}
                      subtitle={c.description || 'No description.'}
                      action={<div className="flex gap-1">
                        {c.status === 'draft' && (
                          <Button size="tiny" variant="primary"
                            onClick={() => act(() => a2aApi.submit(c.id))}>Submit</Button>
                        )}
                        {c.status !== 'draft' && (
                          <Button size="tiny" variant="ghost"
                            onClick={() => act(() => a2aApi.newVersion(c.id))}>New version</Button>
                        )}
                      </div>}
                    />
                    <div className="flex flex-wrap gap-1.5 text-[11px]">
                      {(c.skills ?? []).map((s) => (
                        <span key={s} className="rounded border border-border bg-canvas px-1.5 py-0.5 text-text-mid">{s}</span>
                      ))}
                      {(c.supported_tasks ?? []).map((t) => (
                        <span key={t} className="rounded border border-border bg-canvas px-1.5 py-0.5 text-text-low">task: {t}</span>
                      ))}
                    </div>
                    {c.readiness && !c.readiness.discoverable && (
                      <div className="mt-2 text-[11px] text-amber-400">
                        Not discoverable — {c.readiness.reasons.join('; ')}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}
        </div>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader title="Discovery" subtitle="Approved cards whose agent is genuinely ready." />
            <div className="flex gap-2">
              <input className={INPUT} placeholder="filter by skill (blank = all)"
                value={skill} onChange={(e) => setSkill(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && runDiscover()} />
              <Button variant="subtle" icon={<Radar size={14} />} onClick={runDiscover}>Find</Button>
            </div>
            {discovered !== null && (
              <div className="mt-3 flex flex-col gap-1.5">
                {discovered.length === 0
                  ? <div className="text-[12px] text-text-low">No discoverable agents match.</div>
                  : discovered.map((c) => (
                    <div key={c.id} className="rounded-control border border-border bg-canvas px-2 py-1.5 text-[12px]">
                      <span className="text-text-hi">{c.agent_name}</span>{' '}
                      <span className="mono text-[10px] text-text-low">{c.agent_slug}</span>
                      <div className="text-[11px] text-text-mid">{(c.skills ?? []).join(', ')}</div>
                    </div>
                  ))}
              </div>
            )}
          </Card>

          <HandoffValidator cards={cards ?? []} />
        </div>
      </div>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New agent card"
        footer={null} width="max-w-lg">
        <CardForm
          agentOptions={agentOptions}
          agentId={createFor}
          onAgentChange={setCreateFor}
          onDone={() => { setCreateOpen(false); setCreateFor(''); load(); }}
        />
      </Modal>
    </div>
  );
}

function HandoffValidator({ cards }: { cards: ServerAgentCard[] }) {
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [task, setTask] = useState('');
  const [result, setResult] = useState<HandoffDecision | null>(null);
  const [error, setError] = useState<string | null>(null);

  const slugs: ComboOption[] = cards
    .filter((c) => c.agent_slug)
    .map((c) => ({ value: c.agent_slug as string, hint: c.agent_name ?? undefined }));

  const run = async () => {
    setError(null); setResult(null);
    try {
      setResult(await a2aApi.validateHandoff({
        source_agent_slug: source, target_agent_slug: target, task,
      }));
    } catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <Card>
      <CardHeader title="Handoff validation"
        subtitle="Checks whether A → B would be permitted. Executes nothing." />
      <div className="flex flex-col gap-2">
        <ComboBox value={source} options={slugs} onChange={setSource} placeholder="source agent slug" />
        <ComboBox value={target} options={slugs} onChange={setTarget} placeholder="target agent slug" />
        <input className={INPUT} placeholder="task" value={task} onChange={(e) => setTask(e.target.value)} />
        <Button variant="subtle" icon={<Search size={14} />}
          disabled={!source || !target || !task} onClick={run}>Validate</Button>
        {error && <div className="text-[12px] text-red-400">{error}</div>}
        {result && (
          <div className="mt-1">
            <Badge tone={result.allowed ? 'ok' : 'err'}>
              {result.allowed ? 'permitted' : 'blocked'}
            </Badge>
            <div className="mt-2 flex flex-col gap-0.5">
              {Object.entries(result.checks).map(([name, ok]) => (
                <div key={name} className="text-[11px]">
                  <span className={ok ? 'text-ok' : 'text-red-400'}>{ok ? '✓' : '✕'}</span>{' '}
                  <span className="text-text-mid">{name}</span>
                </div>
              ))}
            </div>
            {result.reasons.length > 0 && (
              <div className="mt-1 text-[11px] text-amber-400">{result.reasons.join('; ')}</div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function CardForm({
  agentOptions, agentId, onAgentChange, onDone,
}: {
  agentOptions: ComboOption[];
  agentId: string;
  onAgentChange: (v: string) => void;
  onDone: () => void;
}) {
  const [description, setDescription] = useState('');
  const [tier, setTier] = useState('standardized');
  const [skills, setSkills] = useState('');
  const [tasks, setTasks] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true); setError(null);
    const body: AgentCardBody = {
      description,
      capability_tier: tier,
      discovery_only: tier === 'standardized',
      artifact_exchange: false,
      skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
      supported_tasks: tasks.split(',').map((s) => s.trim()).filter(Boolean),
    };
    try { await a2aApi.create(agentId, body); onDone(); }
    catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Agent</span>
        <ComboBox value={agentId} options={agentOptions} onChange={onAgentChange}
          emptyHint="no agents yet — create one in the registry first" /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Description</span>
        <input className={INPUT} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Capability tier</span>
        <select className={INPUT} value={tier} onChange={(e) => setTier(e.target.value)}>
          <option value="standardized">standardized (discovery only)</option>
          <option value="advanced">advanced</option>
        </select></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Skills (comma-separated)</span>
        <input className={INPUT} value={skills} onChange={(e) => setSkills(e.target.value)}
          placeholder="incident-summary, network-ops" /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Supported tasks (comma-separated)</span>
        <input className={INPUT} value={tasks} onChange={(e) => setTasks(e.target.value)}
          placeholder="summarize_incident" /></label>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end">
        <Button variant="primary" disabled={busy || !agentId} onClick={submit}>
          {busy ? 'Creating…' : 'Create draft card'}
        </Button>
      </div>
    </div>
  );
}
