import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Button, Badge, TierBadge, EmptyState } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, isLive } from '@/types';
import type { PlaygroundResponse } from '@/kernel/playground';
import { Send, ShieldAlert, Check, X, Bot, User, MessagesSquare, FlaskConical, Loader2 } from 'lucide-react';
import { cn } from '@/utils/cn';

interface Turn { role: 'user' | 'agent'; text: string; response?: PlaygroundResponse; approved?: boolean | null }

export default function PlaygroundPage() {
  const { agentId: paramId } = useParams();
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const tools = useWorkspace((s) => s.tools);

  const selected = agents.find((a) => agentId(a) === paramId) ?? null;

  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [showInspector, setShowInspector] = useState(true);
  const [sending, setSending] = useState(false);

  const lastResponse = useMemo(() => [...turns].reverse().find((t) => t.role === 'agent')?.response, [turns]);

  const canChat = selected && (isLive(selected) || selected.demo_mode);

  const send = async () => {
    if (!selected || !input.trim() || !canChat || sending) return;
    const msg = input.trim();
    const id = agentId(selected);
    const history = turns.map((t) => ({ role: t.role, text: t.text }));
    setTurns((t) => [...t, { role: 'user', text: msg }]);
    setInput('');
    setSending(true);
    try {
      const response = await api.chatWithAgent(id, msg, history, tools);
      // Critical-path tool calls need a HITL approval before showing the result.
      const needsHitl = response.toolCalls[0]?.requiresHitl;
      setTurns((t) => [...t, { role: 'agent', text: response.text, response, approved: needsHitl ? null : true }]);
    } finally {
      setSending(false);
    }
  };

  const decideHitl = (idx: number, approve: boolean) => setTurns((t) => t.map((turn, i) => (i === idx ? { ...turn, approved: approve } : turn)));

  return (
    <div>
      <PageHeader title="Playground" description="Deterministic responses assembled from the agent's own config. Grounded answers cite kb:// sources; write asks get the advisory refusal." />
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
            <div className="flex flex-1 items-center justify-center"><EmptyState icon={<MessagesSquare size={26} />} title="Pick an agent" message="Choose a live agent to chat, or a non-live one to try Demo Mode." /></div>
          ) : (
            <>
              <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-text-hi">{selected.config.identity.agent_name.value}</span>
                  <TierBadge tier={selected.capability_tier} />
                  {selected.governance_path === 'critical' && <Badge tone="err"><ShieldAlert size={10} /> runtime HITL</Badge>}
                </div>
                <button onClick={() => setShowInspector((v) => !v)} className="text-[11px] text-accent hover:underline">{showInspector ? 'Hide' : 'Show'} inspector</button>
              </div>

              {selected.demo_mode && (
                <div className="border-b border-info/40 bg-info/10 px-3 py-1.5 text-[12px] text-info"><FlaskConical size={12} className="mr-1 inline" /> DEMO MODE — responding with synthetic data (index vector://alloydb-demo). Auto-clears when content indexing completes.</div>
              )}

              <div className="flex-1 space-y-3 overflow-auto p-3">
                {turns.length === 0 && <div className="py-8 text-center text-[12px] text-text-low">Try: &quot;Summarize the latest incident&quot; &middot; &quot;Delete all records&quot; &middot; &quot;Use the reader tool&quot;.</div>}
                {turns.map((t, i) => (
                  <div key={i} className={cn('flex gap-2', t.role === 'user' && 'flex-row-reverse')}>
                    <span className={cn('mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full', t.role === 'user' ? 'bg-raised text-text-mid' : 'bg-accent/15 text-accent')}>{t.role === 'user' ? <User size={13} /> : <Bot size={13} />}</span>
                    <div className={cn('max-w-[80%] rounded-card px-3 py-2 text-[13px]', t.role === 'user' ? 'bg-accent/15 text-text-hi' : 'bg-raised text-text-hi')}>
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
                {sending && (
                  <div className="flex gap-2">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent"><Bot size={13} /></span>
                    <div className="flex items-center gap-1.5 rounded-card bg-raised px-3 py-2 text-[12px] text-text-low"><Loader2 size={12} className="animate-spin-slow" /> Thinking…</div>
                  </div>
                )}
              </div>

              {!canChat ? (
                <div className="border-t border-border p-3">
                  <div className="rounded-card border border-info/40 bg-info/5 p-3 text-center">
                    <div className="mb-2 text-[12px] text-text-mid">This agent's Content track isn't ready. Test it with synthetic data?</div>
                    <Button variant="primary" size="sm" icon={<FlaskConical size={13} />} onClick={() => api.enableDemoMode(agentId(selected))}>Enable Demo Mode</Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2 border-t border-border p-3">
                  <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && void send()} placeholder="Ask the agent…" disabled={sending} className="flex-1 rounded-control border border-border bg-canvas px-3 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring disabled:opacity-60" />
                  <Button variant="primary" icon={sending ? <Loader2 size={14} className="animate-spin-slow" /> : <Send size={14} />} onClick={() => void send()} disabled={sending}>{sending ? 'Thinking…' : 'Send'}</Button>
                </div>
              )}
            </>
          )}
        </Card>

        {/* Inspector */}
        {showInspector && (
          <Card pad={false} className="overflow-hidden">
            <div className="border-b border-border px-3 py-2 text-[12px] font-semibold text-text-hi">Inspector — last turn</div>
            <div className="max-h-[540px] space-y-3 overflow-auto p-3 text-[12px]">
              {!lastResponse ? <div className="text-text-low">Send a message to see the trace.</div> : (
                <>
                  <div><div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Intent</div><Badge tone="accent">{lastResponse.kind}</Badge> <span className="text-text-low">· {lastResponse.tokenCount} tokens</span></div>
                  {lastResponse.retrieval.length > 0 && (
                    <div>
                      <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Retrieval trace (vs score_threshold)</div>
                      {lastResponse.retrieval.map((c) => (
                        <div key={c.doc_id} className="mb-1 flex items-center gap-2">
                          <span className={cn('mono text-[10px] w-10', c.passed ? 'text-ok' : 'text-text-low')}>{c.score.toFixed(2)}</span>
                          <span className="mono text-[10px] text-text-mid flex-1 truncate">{c.doc_id}</span>
                          {c.passed ? <Check size={11} className="text-ok" /> : <X size={11} className="text-text-low" />}
                        </div>
                      ))}
                    </div>
                  )}
                  {lastResponse.routing.length > 0 && <div><div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Sub-agent routing</div><div className="text-info">{lastResponse.routing.join(' → ')}</div></div>}
                  <div>
                    <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Config fields that shaped this</div>
                    {lastResponse.shapedBy.map((s, i) => <div key={i} className="mono text-[11px] text-text-mid">· {s}</div>)}
                  </div>
                </>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
