import { useState, useMemo, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Button, Badge, TierBadge, EmptyState, Modal } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, isLive, type AgentRecord } from '@/types';
import { generatePlaygroundResponse, type PlaygroundResponse } from '@/kernel/playground';
import { SecretsModal } from './SecretsModal';
import { Send, ShieldAlert, Check, X, Bot, User, MessagesSquare, Zap, Loader2, KeyRound, Link2 } from 'lucide-react';
import { cn } from '@/utils/cn';

interface Turn {
  role: 'user' | 'agent';
  text: string;
  mode?: 'live' | 'sim';
  response?: PlaygroundResponse; // sim only
  liveTrace?: Record<string, unknown>; // live only
  note?: string;
  approved?: boolean | null;
}

export default function PlaygroundPage() {
  const { agentId: paramId } = useParams();
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const sources = useWorkspace((s) => s.sources);
  const tools = useWorkspace((s) => s.tools);

  const selected = agents.find((a) => agentId(a) === paramId) ?? null;

  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [showInspector, setShowInspector] = useState(true);
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  const [engineHasDefaultKey, setEngineHasDefaultKey] = useState(false);
  const [engineHasAnthropicKey, setEngineHasAnthropicKey] = useState(false);
  const [secretNames, setSecretNames] = useState<string[]>([]);
  const [preferLive, setPreferLive] = useState(true);
  // opt-in Claude runtime — Gemini stays the default; toggle only shows when the
  // engine vault has an ANTHROPIC key
  const [llmTarget, setLlmTarget] = useState<'aistudio' | 'claude'>('aistudio');
  const [sending, setSending] = useState(false);

  // legacy browser key (migration source; still works as a per-request override)
  const geminiKey = useWorkspace((s) => s.ui.geminiKey);
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  const [credsOpen, setCredsOpen] = useState(false);

  const refreshHealth = () => {
    api.engineHealth().then((h) => {
      setEngineUp(h.up);
      setEngineHasDefaultKey(h.hasDefaultKey);
      setEngineHasAnthropicKey(h.hasAnthropicKey);
      if (!h.hasAnthropicKey) setLlmTarget('aistudio'); // key removed → back to default
      setSecretNames(h.secretNames);
    });
  };
  useEffect(() => {
    refreshHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lastAgentTurn = useMemo(() => [...turns].reverse().find((t) => t.role === 'agent'), [turns]);
  const keyReady = Boolean(geminiKey) || engineHasDefaultKey;
  const liveMode = preferLive && engineUp === true && keyReady;

  const openKeyModal = () => setKeyModalOpen(true);

  const snippetsFor = (a: AgentRecord) => {
    const ids = new Set(a.config.data.knowledge_source_refs.value.map((r) => r.replace('kb://', '').split('@')[0]));
    const out: { doc_id: string; text: string }[] = [];
    for (const s of sources) if (ids.has(s.id)) for (const sn of s.snippets) out.push({ doc_id: sn.doc_id, text: sn.text });
    return out;
  };

  const send = async () => {
    if (!selected || !input.trim() || sending) return;
    const msg = input.trim();
    setInput('');
    setTurns((t) => [...t, { role: 'user', text: msg }]);

    if (liveMode) {
      setSending(true);
      const res = await api.runAgentLive(selected, msg, agentId(selected), snippetsFor(selected), llmTarget);
      setSending(false);
      if (res && !res.error && res.reply) {
        setTurns((t) => [...t, { role: 'agent', mode: 'live', text: res.reply, liveTrace: res.trace }]);
        return;
      }
      // fall back to the simulation, but surface why the live run didn't happen
      const note = res?.error ? `engine error — showing simulated: ${res.error}` : 'engine offline — showing simulated';
      if (!res) setEngineUp(false);
      const sim = generatePlaygroundResponse(selected, sources, tools, msg);
      setTurns((t) => [...t, { role: 'agent', mode: 'sim', text: sim.text, response: sim, note, approved: sim.toolCalls[0]?.requiresHitl ? null : true }]);
      return;
    }

    // simulated mode
    const sim = generatePlaygroundResponse(selected, sources, tools, msg);
    setTurns((t) => [...t, { role: 'agent', mode: 'sim', text: sim.text, response: sim, approved: sim.toolCalls[0]?.requiresHitl ? null : true }]);
  };

  const decideHitl = (idx: number, approve: boolean) => setTurns((t) => t.map((turn, i) => (i === idx ? { ...turn, approved: approve } : turn)));

  return (
    <div>
      <PageHeader
        title="Playground"
        description="Live mode runs the real agent via the engine (Gemini + real tools). If the engine is offline, responses fall back to the deterministic simulation."
        badges={
          <span className="flex items-center gap-1.5">
            {engineUp === null ? <Badge tone="muted">checking engine…</Badge>
              : engineUp ? <Badge tone="ok"><Zap size={10} /> engine online</Badge>
              : <Badge tone="warn">engine offline — simulated</Badge>}
            {engineUp && (
              engineHasDefaultKey
                ? <Badge tone="ok"><KeyRound size={10} /> vault ready{secretNames.length ? ` (${secretNames.length})` : ''}</Badge>
                : geminiKey
                  ? <button onClick={openKeyModal}><Badge tone="warn"><KeyRound size={10} /> legacy browser key — migrate</Badge></button>
                  : <button onClick={openKeyModal}><Badge tone="warn"><KeyRound size={10} /> add secrets</Badge></button>
            )}
          </span>
        }
        action={
          <Button variant="outline" size="sm" icon={<KeyRound size={13} />} onClick={openKeyModal}>
            Secrets
          </Button>
        }
      />
      <div className="grid grid-cols-[220px_1fr_300px] gap-4" style={{ minHeight: 560 }}>
        {/* Agent picker */}
        <Card pad={false} className="overflow-hidden">
          <div className="border-b border-border px-3 py-2 text-[12px] font-semibold text-text-hi">Agents</div>
          <div className="max-h-[540px] overflow-auto p-2">
            {agents.map((a) => {
              const live = isLive(a);
              const active = agentId(a) === paramId;
              return (
                <button key={agentId(a)} onClick={() => { navigate(`/playground/${agentId(a)}`); setTurns([]); }} className={cn('mb-1 w-full rounded-control border px-2.5 py-2 text-left', active ? 'border-accent bg-accent/10' : 'border-transparent hover:bg-raised')}>
                  <div className="flex items-center gap-1.5">
                    <span className={cn('h-2 w-2 rounded-full', live ? 'bg-ok' : a.demo_mode ? 'bg-info' : 'bg-border-strong')} />
                    <span className="flex-1 truncate text-[12px] text-text-hi">{a.config.identity.agent_name.value}</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-1"><TierBadge tier={a.capability_tier} />{!live && !a.demo_mode && <span className="text-[9px] text-text-low">not live</span>}</div>
                </button>
              );
            })}
          </div>
        </Card>

        {/* Chat surface */}
        <Card pad={false} className="flex flex-col">
          {!selected ? (
            <div className="flex flex-1 items-center justify-center"><EmptyState icon={<MessagesSquare size={26} />} title="Pick an agent" message="Choose an agent to chat. Live mode runs it for real via the engine." /></div>
          ) : (
            <>
              <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-text-hi">{selected.config.identity.agent_name.value}</span>
                  <TierBadge tier={selected.capability_tier} />
                  {selected.governance_path === 'critical' && <Badge tone="err"><ShieldAlert size={10} /> runtime HITL</Badge>}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCredsOpen(true)}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-raised text-text-mid hover:text-text-hi"
                    title="Bind this agent's model/tools to named vault secrets"
                  >
                    <Link2 size={10} /> credentials
                  </button>
                  {liveMode && engineHasAnthropicKey && (
                    <button
                      onClick={() => setLlmTarget((t) => (t === 'claude' ? 'aistudio' : 'claude'))}
                      className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', llmTarget === 'claude' ? 'bg-accent/20 text-accent' : 'bg-raised text-text-low hover:text-text-mid')}
                      title="Opt-in: run this agent on Claude (ANTHROPIC_DEFAULT vault key). Gemini is the default."
                    >
                      {llmTarget === 'claude' ? 'on Claude' : 'on Gemini'}
                    </button>
                  )}
                  <button
                    onClick={() => (engineUp && !keyReady ? openKeyModal() : setPreferLive((v) => !v))}
                    disabled={engineUp !== true}
                    className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', liveMode ? 'bg-ok/15 text-ok' : 'bg-raised text-text-low', engineUp !== true && 'opacity-50 cursor-not-allowed')}
                    title={engineUp !== true ? 'Engine offline' : !keyReady ? 'Add a vault secret to go live' : 'Toggle live vs simulated'}
                  >
                    {liveMode ? 'LIVE (engine)' : engineUp && !keyReady ? 'SIMULATED — add key' : 'SIMULATED'}
                  </button>
                  <button onClick={() => setShowInspector((v) => !v)} className="text-[11px] text-accent hover:underline">{showInspector ? 'Hide' : 'Show'} inspector</button>
                </div>
              </div>

              <div className="flex-1 space-y-3 overflow-auto p-3">
                {turns.length === 0 && <div className="py-8 text-center text-[12px] text-text-low">Try: “Summarize the latest incident” · “Delete all records” · a real question if this agent has web search.</div>}
                {turns.map((t, i) => (
                  <div key={i} className={cn('flex gap-2', t.role === 'user' && 'flex-row-reverse')}>
                    <span className={cn('mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full', t.role === 'user' ? 'bg-raised text-text-mid' : 'bg-accent/15 text-accent')}>{t.role === 'user' ? <User size={13} /> : <Bot size={13} />}</span>
                    <div className={cn('max-w-[80%] rounded-card px-3 py-2 text-[13px]', t.role === 'user' ? 'bg-accent/15 text-text-hi' : 'bg-raised text-text-hi')}>
                      {t.role === 'agent' && (
                        <div className="mb-1 flex items-center gap-1 text-[10px]">
                          {t.mode === 'live' ? <span className="text-ok"><Zap size={9} className="inline" /> live</span> : <span className="text-text-low">simulated</span>}
                          {((t.liveTrace?.tool_calls as string[] | undefined)?.length ?? 0) > 0 && <span className="text-info">· tools: {(t.liveTrace!.tool_calls as string[]).join(', ')}</span>}
                        </div>
                      )}
                      {t.note && <div className="mb-1 text-[10px] text-warn">{t.note}</div>}
                      {t.response?.routing && t.response.routing.length > 0 && <div className="mb-1 text-[10px] text-info">↳ routing: {t.response.routing.join(' → ')}</div>}
                      <div className="whitespace-pre-wrap">{t.text}</div>
                      {t.response?.toolCalls.map((tc, j) => (
                        <div key={j} className="mt-2 rounded-control border border-border bg-canvas p-2 text-[12px]">
                          <div className="mb-1 flex items-center justify-between"><span className="mono text-accent">tool_call · {tc.tool_id}</span><Badge tone="info">{tc.permission}</Badge></div>
                          {tc.requiresHitl && t.approved === null ? (
                            <div className="rounded border border-warn/40 bg-warn/10 p-2">
                              <div className="mb-1.5 text-[12px] text-warn">Runtime HITL gate — approve this action?</div>
                              <div className="flex gap-1.5"><Button variant="primary" size="tiny" icon={<Check size={11} />} onClick={() => decideHitl(i, true)}>Approve</Button><Button variant="danger" size="tiny" icon={<X size={11} />} onClick={() => decideHitl(i, false)}>Deny</Button></div>
                            </div>
                          ) : t.approved === false ? (
                            <div className="text-[12px] text-err">Denied by human gate — no result executed.</div>
                          ) : (
                            <pre className="whitespace-pre-wrap mono text-[11px] text-text-mid">{tc.result}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
                {sending && <div className="flex items-center gap-2 text-[12px] text-text-low"><Loader2 size={13} className="animate-spin-slow" /> running the live agent…</div>}
              </div>

              <div className="flex gap-2 border-t border-border p-3">
                <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} placeholder={liveMode ? 'Ask the live agent…' : 'Ask the agent (simulated)…'} disabled={sending} className="flex-1 rounded-control border border-border bg-canvas px-3 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring disabled:opacity-60" />
                <Button variant="primary" icon={sending ? <Loader2 size={14} className="animate-spin-slow" /> : <Send size={14} />} onClick={send} disabled={sending}>Send</Button>
              </div>
            </>
          )}
        </Card>

        {/* Inspector */}
        {showInspector && (
          <Card pad={false} className="overflow-hidden">
            <div className="border-b border-border px-3 py-2 text-[12px] font-semibold text-text-hi">Inspector — last turn</div>
            <div className="max-h-[540px] space-y-3 overflow-auto p-3 text-[12px]">
              {!lastAgentTurn ? (
                <div className="text-text-low">Send a message to see the trace.</div>
              ) : lastAgentTurn.mode === 'live' && lastAgentTurn.liveTrace ? (
                <LiveTrace trace={lastAgentTurn.liveTrace} />
              ) : lastAgentTurn.response ? (
                <SimTrace r={lastAgentTurn.response} />
              ) : null}
            </div>
          </Card>
        )}
      </div>

      {/* Engine-side secrets vault manager (values write-only from the browser) */}
      <SecretsModal
        open={keyModalOpen}
        onClose={() => { setKeyModalOpen(false); refreshHealth(); }}
        onChanged={(names) => { setSecretNames(names); refreshHealth(); }}
      />

      {/* Per-agent credential bindings: model/tools → named vault secrets */}
      {selected && (
        <CredentialsModal
          open={credsOpen}
          onClose={() => setCredsOpen(false)}
          agent={selected}
          secretNames={secretNames}
        />
      )}
    </div>
  );
}

// Bind the selected agent's model + each bound tool to a named vault secret.
// Writes tooling.secret_refs via the audited proposeConfigChange path.
function CredentialsModal({
  open,
  onClose,
  agent,
  secretNames,
}: {
  open: boolean;
  onClose: () => void;
  agent: AgentRecord;
  secretNames: string[];
}) {
  const current = (agent.config.tooling.secret_refs?.value ?? {}) as Record<string, string>;
  const [draft, setDraft] = useState<Record<string, string>>(current);
  useEffect(() => { if (open) setDraft(current); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [open]);

  const toolIds = agent.config.tooling.bound_tools.value.map((t) => t.replace('tools://', '').split('@')[0]);
  const rows: { key: string; label: string }[] = [
    { key: 'model', label: 'model (LLM key)' },
    ...toolIds.map((t) => ({ key: t, label: `tool · ${t}` })),
  ];

  const setRef = (key: string, secret: string) => {
    setDraft((d) => {
      const next = { ...d };
      if (secret) next[key] = secret;
      else delete next[key];
      return next;
    });
  };

  const save = () => {
    api.proposeConfigChange(agentId(agent), 'tooling', 'secret_refs', draft);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={<span className="flex items-center gap-2"><Link2 size={15} /> Credentials · {agent.config.identity.agent_name.value}</span>}
      width="max-w-md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save}>Save bindings</Button>
        </>
      }
    >
      <div className="space-y-2 text-[12px] text-text-mid">
        <p>
          Bind this agent's model and tools to named vault secrets. Unbound entries fall back to{' '}
          <span className="mono">GEMINI_DEFAULT</span> (model) or run keyless (tools like web_search).
        </p>
        {secretNames.length === 0 && (
          <p className="text-warn">No vault secrets yet — add them via the Secrets button first.</p>
        )}
        {rows.map((r) => (
          <div key={r.key} className="flex items-center gap-2">
            <span className="mono w-40 shrink-0 text-text-hi">{r.label}</span>
            <select
              value={draft[r.key] ?? ''}
              onChange={(e) => setRef(r.key, e.target.value)}
              className="h-8 flex-1 rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi focus-ring"
            >
              <option value="">(default)</option>
              {secretNames.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function LiveTrace({ trace }: { trace: Record<string, unknown> }) {
  const row = (k: string) => trace[k];
  return (
    <>
      <div><Badge tone="ok"><Zap size={10} /> live via engine</Badge></div>
      <TraceRow label="topology" value={String(row('topology') ?? '')} />
      {row('pattern') != null && String(row('pattern')) !== 'hub' && <TraceRow label="pattern" value={String(row('pattern'))} />}
      <TraceRow label="model" value={String(row('model') ?? '')} />
      <TraceRow label="llm_target" value={String(row('llm_target') ?? '')} />
      {row('credential_source') != null && <TraceRow label="credentials" value={String(row('credential_source'))} />}
      <TraceRow label="rag" value={String(row('rag') ?? '')} />
      {Array.isArray(row('bound_tools')) && <TraceRow label="bound_tools" value={(row('bound_tools') as string[]).join(', ') || '—'} />}
      {Array.isArray(row('tool_calls')) && <TraceRow label="tool_calls" value={(row('tool_calls') as string[]).join(', ') || 'none'} />}
      {Array.isArray(row('sub_agents')) && (row('sub_agents') as string[]).length > 0 && <TraceRow label="sub_agents" value={(row('sub_agents') as string[]).join(', ')} />}
      {Array.isArray(row('disabled_tools')) && (row('disabled_tools') as string[]).length > 0 && <TraceRow label="disabled (write)" value={(row('disabled_tools') as string[]).join(', ')} />}
      {row('branch_outputs') != null && typeof row('branch_outputs') === 'object' && (
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Branch outputs</div>
          {Object.entries(row('branch_outputs') as Record<string, string>).map(([name, text]) => (
            <details key={name} className="mb-1 rounded border border-border bg-raised/40 px-2 py-1">
              <summary className="mono cursor-pointer text-[11px] text-text-hi">{name}</summary>
              <div className="whitespace-pre-wrap py-1 text-[11px] text-text-mid">{text}</div>
            </details>
          ))}
        </div>
      )}
    </>
  );
}

function TraceRow({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-2"><span className="text-[11px] uppercase text-text-low">{label}</span><span className="mono text-[11px] text-text-hi text-right">{value}</span></div>;
}

function SimTrace({ r }: { r: PlaygroundResponse }) {
  return (
    <>
      <div><Badge tone="muted">simulated</Badge> <span className="text-text-low">· {r.tokenCount} tokens</span></div>
      <div><div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Intent</div><Badge tone="accent">{r.kind}</Badge></div>
      {r.retrieval.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Retrieval trace (vs score_threshold)</div>
          {r.retrieval.map((c) => (
            <div key={c.doc_id} className="mb-1 flex items-center gap-2">
              <span className={cn('mono text-[10px] w-10', c.passed ? 'text-ok' : 'text-text-low')}>{c.score.toFixed(2)}</span>
              <span className="mono text-[10px] text-text-mid flex-1 truncate">{c.doc_id}</span>
              {c.passed ? <Check size={11} className="text-ok" /> : <X size={11} className="text-text-low" />}
            </div>
          ))}
        </div>
      )}
      {r.routing.length > 0 && <div><div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Sub-agent routing</div><div className="text-info">{r.routing.join(' → ')}</div></div>}
      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Config fields that shaped this</div>
        {r.shapedBy.map((s, i) => <div key={i} className="mono text-[11px] text-text-mid">· {s}</div>)}
      </div>
    </>
  );
}
