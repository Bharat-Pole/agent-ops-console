import { useState, useEffect } from 'react';
import { Card, Button, Badge } from '@/components/primitives';
import { AssetRefLink } from '@/components/domain';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import type { OrchestrationPattern, SubAgent, GraphSpec } from '@/types';
import { ChevronDown, ChevronRight, ArrowRight, ArrowLeft, Ban, ShieldAlert, Plus, Trash2, ArrowUp, ArrowDown, Save } from 'lucide-react';
import { cn } from '@/utils/cn';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 last:border-0 text-[12px]">
      <span className="text-text-low">{label}</span>
      <span className="text-text-hi">{children}</span>
    </div>
  );
}

// Small SVG workflow diagram, pattern-aware:
//   hub      — coordinator fans out to sub-agents (and back)
//   pipeline — horizontal chain s1 → s2 → …
//   parallel — fan-out to branches, join into `aggregate`
function WorkflowDiagram({ subs, gates, pattern }: { subs: { name: string }[]; gates: number; pattern: OrchestrationPattern }) {
  const w = 520;
  if (subs.length === 0) {
    return <div className="py-6 text-center text-[11px] text-text-low">No sub-agents yet — add one below.</div>;
  }
  if (pattern === 'pipeline') {
    const step = Math.min(150, (w - 40) / subs.length);
    return (
      <svg width="100%" viewBox={`0 0 ${w} 70`} className="text-text-mid">
        {subs.map((s, i) => {
          const x = 14 + i * step;
          return (
            <g key={s.name}>
              <rect x={x} y={22} width={step - 30} height={26} rx={6} fill="var(--bg-raised)" stroke="var(--border)" />
              <text x={x + (step - 30) / 2} y={39} textAnchor="middle" fontSize="10" fill="var(--text-hi)">{s.name.slice(0, 16)}</text>
              {i < subs.length - 1 && <path d={`M${x + step - 30} 35 L${x + step - 4} 35`} stroke="var(--border-strong)" strokeWidth={1.5} markerEnd="" />}
              {i < subs.length - 1 && <text x={x + step - 20} y={32} fontSize="10" fill="var(--text-low)">›</text>}
            </g>
          );
        })}
        {gates > 0 && <text x={14} y={62} fontSize="9" fill="var(--warn)">● HITL gates apply on stage edges</text>}
      </svg>
    );
  }
  if (pattern === 'parallel') {
    const h = Math.max(120, subs.length * 40 + 24);
    const midY = h / 2;
    return (
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="text-text-mid">
        <rect x={8} y={midY - 13} width={70} height={26} rx={6} fill="var(--tier-advanced)" opacity={0.2} stroke="var(--tier-advanced)" />
        <text x={43} y={midY + 4} textAnchor="middle" fontSize="10" fill="var(--text-hi)">START</text>
        {subs.map((s, i) => {
          const y = 26 + i * 40;
          return (
            <g key={s.name}>
              <path d={`M78 ${midY} C 140 ${midY}, 150 ${y}, 200 ${y}`} fill="none" stroke="var(--border-strong)" strokeWidth={1.5} />
              <rect x={200} y={y - 13} width={160} height={26} rx={6} fill="var(--bg-raised)" stroke="var(--border)" />
              <text x={280} y={y + 4} textAnchor="middle" fontSize="10" fill="var(--text-hi)">{s.name.slice(0, 20)}</text>
              <path d={`M360 ${y} C 400 ${y}, 410 ${midY}, 440 ${midY}`} fill="none" stroke="var(--border-strong)" strokeWidth={1.5} />
            </g>
          );
        })}
        <rect x={440} y={midY - 13} width={72} height={26} rx={6} fill="var(--ok)" opacity={0.15} stroke="var(--ok)" />
        <text x={476} y={midY + 4} textAnchor="middle" fontSize="10" fill="var(--text-hi)">aggregate</text>
        {gates > 0 && <circle cx={430} cy={midY - 18} r={5} fill="var(--warn)" />}
        {gates > 0 && <text x={380} y={14} fontSize="9" fill="var(--warn)">● HITL — gate the aggregate (one-branch gates pause all)</text>}
      </svg>
    );
  }
  // hub (supervisor)
  const cy = 20 + subs.length * 18;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${Math.max(120, subs.length * 44 + 20)}`} className="text-text-mid">
      <rect x={10} y={cy - 14} width={100} height={28} rx={6} fill="var(--tier-advanced)" opacity={0.2} stroke="var(--tier-advanced)" />
      <text x={60} y={cy + 4} textAnchor="middle" fontSize="11" fill="var(--text-hi)">coordinator</text>
      {subs.map((s, i) => {
        const y = 24 + i * 44;
        return (
          <g key={s.name}>
            <path d={`M110 ${cy} C 200 ${cy}, 220 ${y}, 300 ${y}`} fill="none" stroke="var(--border-strong)" strokeWidth={1.5} />
            {i === 0 && gates > 0 && <circle cx={230} cy={(cy + y) / 2} r={5} fill="var(--warn)" />}
            <rect x={300} y={y - 14} width={200} height={28} rx={6} fill="var(--bg-raised)" stroke="var(--border)" />
            <text x={310} y={y + 4} fontSize="11" fill="var(--text-hi)">{s.name}</text>
          </g>
        );
      })}
      {gates > 0 && <text x={210} y={16} fontSize="9" fill="var(--warn)">● HITL gate</text>}
    </svg>
  );
}

// Read-only view of the recommender's explicit graph (nodes + edges). Rendered by
// agent_forge as a real LangGraph StateGraph — this is the shape that gets generated.
function GraphSpecView({ graph }: { graph: GraphSpec }) {
  const KIND_TONE: Record<string, string> = {
    retrieve: 'bg-info/15 text-info', llm: 'bg-accent/15 text-accent',
    tool: 'bg-warn/15 text-warn', route: 'bg-tier-advanced/20 text-tier-advanced', aggregate: 'bg-ok/15 text-ok',
  };
  return (
    <div className="space-y-2 text-[12px]">
      <div className="flex flex-wrap gap-1.5">
        {graph.nodes.map((n) => (
          <span key={n.id} className="flex items-center gap-1 rounded border border-border bg-raised/40 px-2 py-1">
            <span className="mono text-text-hi">{n.id}</span>
            <span className={cn('rounded px-1 text-[9px] font-semibold uppercase', KIND_TONE[n.kind] ?? 'bg-raised text-text-low')}>{n.kind}</span>
          </span>
        ))}
      </div>
      <div className="space-y-0.5">
        {graph.edges.map((e, i) => (
          <div key={i} className="flex items-center gap-1.5 text-text-mid">
            <span className="mono text-text-hi">{e.from}</span>
            <ArrowRight size={12} className="text-text-low" />
            <span className="mono text-text-hi">{e.to}</span>
            {e.when && <span className="text-[10px] text-text-low">· when {e.when}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function Phase4Configure({ draft, goPhase }: PhaseProps) {
  const agent = useWorkspace((s) => s.agents.find((a) => a.config.identity.agent_id.value === draft.agent_id));
  const tools = useWorkspace((s) => s.tools);
  const patchAgent = useWorkspace((s) => s.patchAgent);
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (!agent) {
    return <Card><div className="text-[13px] text-text-mid">Register the agent (Phase 3) before configuring.</div><Button className="mt-3" variant="ghost" onClick={() => goPhase(3)}>← Back to Phase 3</Button></Card>;
  }

  const c = agent.config;
  const tier = agent.capability_tier;
  const isAdv = tier === 'advanced';
  const rag = c.data.rag_enabled.value;
  const boundIds = c.tooling.bound_tools.value.map((t) => t.replace('tools://', '').split('@')[0]);

  const toggleA2A = () => {
    patchAgent(draft.agent_id!, (a) => ({ ...a, config: { ...a.config, orchestration: { ...a.config.orchestration, a2a_enabled: { ...a.config.orchestration.a2a_enabled, value: !a.config.orchestration.a2a_enabled.value } } } }));
  };

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[13px] font-semibold text-text-hi">Phase 4 · Configure Workflow</div>
          <Badge tone="accent">{tier} — progressive disclosure</Badge>
        </div>
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-low">Model</div>
            <Row label="model_primary"><AssetRefLink refUri={c.model.model_primary.value} /></Row>
            {c.model.model_fallback.value && <Row label="model_fallback"><AssetRefLink refUri={c.model.model_fallback.value} /></Row>}
            {rag && (
              <>
                <div className="mb-1 mt-3 text-[11px] font-semibold uppercase tracking-wide text-text-low">Knowledge & RAG</div>
                <Row label="retrieval_type">{c.data.retrieval_type.value}</Row>
                {c.data.knowledge_source_refs.value.map((r, i) => <Row key={i} label="source"><AssetRefLink refUri={r} /></Row>)}
                <Row label="citation_rules">{c.prompt.citation_rules.value ? <AssetRefLink refUri={c.prompt.citation_rules.value} /> : '—'}</Row>
              </>
            )}
            <div className="mb-1 mt-3 text-[11px] font-semibold uppercase tracking-wide text-text-low">A2A</div>
            <Row label="a2a_enabled">
              <button onClick={toggleA2A} className={cn('rounded px-2 py-0.5 text-[11px]', c.orchestration.a2a_enabled.value ? 'bg-ok/15 text-ok' : 'bg-raised text-text-low')}>{String(c.orchestration.a2a_enabled.value)}</button>
            </Row>
          </div>

          <div>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-low">Tool picker (max 3, read-only)</div>
            <div className="space-y-1">
              {/* custom tools bound in Phase 1 that aren't in the seed catalog */}
              {boundIds.filter((id) => !tools.some((t) => t.id === id)).map((id) => (
                <div key={id} className="flex items-center gap-2 rounded border border-accent/40 bg-accent/10 px-2 py-1.5 text-[12px]">
                  <span className="mono flex-1 text-text-hi">{id}</span>
                  {id.toLowerCase().includes('search') && <Badge tone="ok">live · web search (DuckDuckGo)</Badge>}
                  <Badge tone="accent">custom · bound</Badge>
                </div>
              ))}
              {tools.map((t) => {
                const bound = boundIds.includes(t.id);
                return (
                  <div key={t.id} className={cn('flex items-center gap-2 rounded border px-2 py-1.5 text-[12px]', t.write_capable ? 'border-err/30 bg-err/5 opacity-70' : bound ? 'border-accent/40 bg-accent/10' : 'border-border')}>
                    <span className="mono flex-1 text-text-hi">{t.id}</span>
                    {t.write_capable ? (
                      <Badge tone="err"><Ban size={10} /> WRITE — advisory-block</Badge>
                    ) : bound ? (
                      <Badge tone="accent">bound</Badge>
                    ) : (
                      <span className="text-[10px] text-text-low">{t.permission_ceiling}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </Card>

      {/* Recommended orchestration graph (Stage 2b) — the explicit shape the generator renders */}
      {c.orchestration.graph.value && (
        <Card>
          <div className="mb-1 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-text-hi">Orchestration graph</div>
            <Badge tone="accent">{c.orchestration.orchestration_type.value}</Badge>
          </div>
          <div className="mb-2 text-[11px] text-text-low">
            agent_forge renders this as an explicit LangGraph <span className="mono">StateGraph</span>.
          </div>
          <GraphSpecView graph={c.orchestration.graph.value} />
        </Card>
      )}

      {/* Advanced settings accordion (governance-critical fields NEVER live here) */}
      <Card pad={false}>
        <button onClick={() => setShowAdvanced((v) => !v)} className="flex w-full items-center gap-2 px-4 py-3 text-left">
          {showAdvanced ? <ChevronDown size={14} className="text-text-low" /> : <ChevronRight size={14} className="text-text-low" />}
          <span className="text-[13px] font-semibold text-text-hi">Advanced settings</span>
          <span className="text-[11px] text-text-low">temperature, tokens, RAG params{isAdv ? ', orchestration, scaling, HITL' : ''}</span>
        </button>
        {showAdvanced && (
          <div className="grid grid-cols-2 gap-6 border-t border-border px-4 py-3">
            <div>
              <Row label="temperature">{c.model.temperature.value}</Row>
              <Row label="max_output_tokens">{c.model.max_output_tokens.value}</Row>
              <Row label="cost_label">{c.observability.cost_label.value}</Row>
              {rag && (
                <>
                  <Row label="chunk_size">{c.data.chunk_size.value}</Row>
                  <Row label="chunk_overlap">{c.data.chunk_overlap.value}</Row>
                  <Row label="top_k">{c.data.top_k.value}</Row>
                  <Row label="score_threshold">{c.data.score_threshold.value}</Row>
                </>
              )}
            </div>
            {isAdv && (
              <div>
                <Row label="orchestration_type">{c.orchestration.orchestration_type.value}</Row>
                <Row label="scaling_policy">{c.runtime.scaling_policy.value}</Row>
                <Row label="concurrency">{c.runtime.concurrency.value}</Row>
                <Row label="timeout">{c.runtime.timeout.value}s</Row>
                <Row label="message_task_format">{c.orchestration.message_task_format.value ?? '—'}</Row>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Orchestration editor: pattern picker + editable sub-agents + diagram (Advanced) */}
      {isAdv && (
        <OrchestrationEditor
          agentId={draft.agent_id!}
          pattern={c.orchestration.pattern?.value ?? 'hub'}
          subAgents={c.orchestration.sub_agents.value}
          gates={c.orchestration.hitl_gate_placement.value.length}
        />
      )}

      <div className="flex items-center gap-2">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => goPhase(3)}>Back</Button>
        <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => goPhase(5)}>Next: Governance Gates</Button>
      </div>
    </div>
  );
}

const PATTERNS: { id: OrchestrationPattern; label: string; blurb: string }[] = [
  { id: 'hub', label: 'Hub-and-spoke', blurb: 'Coordinator routes to one sub-agent at a time' },
  { id: 'pipeline', label: 'Pipeline', blurb: 'Sequential stages — order matters' },
  { id: 'parallel', label: 'Parallel', blurb: 'All branches at once, then aggregate' },
];

// Editable orchestration: pattern picker + sub-agent list (add/remove/edit/reorder,
// tool assignment ≤3 read-only). Saves via the audited api.updateOrchestration.
function OrchestrationEditor({
  agentId: aid,
  pattern,
  subAgents,
  gates,
}: {
  agentId: string;
  pattern: OrchestrationPattern;
  subAgents: SubAgent[];
  gates: number;
}) {
  const catalog = useWorkspace((s) => s.tools);
  const [draftPattern, setDraftPattern] = useState<OrchestrationPattern>(pattern);
  const [draft, setDraft] = useState<SubAgent[]>(() => structuredClone(subAgents));
  const [dirty, setDirty] = useState(false);
  useEffect(() => { setDraftPattern(pattern); setDraft(structuredClone(subAgents)); setDirty(false); }, [aid]); // eslint-disable-line react-hooks/exhaustive-deps

  const edit = (fn: (d: SubAgent[]) => void) => {
    setDraft((d) => { const next = structuredClone(d); fn(next); return next; });
    setDirty(true);
  };
  const move = (i: number, dir: -1 | 1) => edit((d) => {
    const j = i + dir;
    if (j < 0 || j >= d.length) return;
    [d[i], d[j]] = [d[j], d[i]];
  });
  const toggleTool = (i: number, toolId: string) => edit((d) => {
    const ref = `tools://${toolId}@v1`;
    const has = d[i].tools.some((t) => t.includes(toolId));
    if (has) d[i].tools = d[i].tools.filter((t) => !t.includes(toolId));
    else if (d[i].tools.length < 3) d[i].tools = [...d[i].tools, ref];
  });

  const save = () => {
    const ok = api.updateOrchestration(aid, { pattern: draftPattern, sub_agents: draft });
    if (ok) setDirty(false);
  };

  const readTools = catalog.filter((t) => !t.write_capable);

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-text-hi">
          <ShieldAlert size={15} className="text-tier-advanced" /> Orchestration editor
        </div>
        <Button variant={dirty ? 'primary' : 'subtle'} size="sm" icon={<Save size={13} />} onClick={save} disabled={!dirty}>
          {dirty ? 'Save changes' : 'Saved'}
        </Button>
      </div>

      {/* pattern picker */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        {PATTERNS.map((p) => (
          <button
            key={p.id}
            onClick={() => { setDraftPattern(p.id); setDirty(true); }}
            className={cn('rounded-control border px-3 py-2 text-left', draftPattern === p.id ? 'border-accent bg-accent/10' : 'border-border hover:border-border-strong')}
          >
            <div className={cn('text-[12px] font-semibold', draftPattern === p.id ? 'text-accent' : 'text-text-hi')}>{p.label}</div>
            <div className="text-[10px] text-text-low">{p.blurb}</div>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* editable sub-agent list */}
        <div className="space-y-2">
          {draft.map((s, i) => (
            <div key={i} className="rounded-control border border-border bg-raised/30 p-2.5">
              <div className="mb-1 flex items-center gap-1.5">
                <input
                  value={s.name}
                  onChange={(e) => edit((d) => { d[i].name = e.target.value.replace(/\W+/g, '_').toLowerCase(); })}
                  className="mono w-40 rounded border border-border bg-canvas px-1.5 py-0.5 text-[12px] text-text-hi focus-ring"
                />
                <span className="flex-1" />
                <button onClick={() => move(i, -1)} disabled={i === 0} className="text-text-low hover:text-text-hi disabled:opacity-30"><ArrowUp size={12} /></button>
                <button onClick={() => move(i, 1)} disabled={i === draft.length - 1} className="text-text-low hover:text-text-hi disabled:opacity-30"><ArrowDown size={12} /></button>
                <button onClick={() => edit((d) => { d.splice(i, 1); })} className="text-text-low hover:text-err"><Trash2 size={12} /></button>
              </div>
              <input
                value={s.role}
                onChange={(e) => edit((d) => { d[i].role = e.target.value; })}
                placeholder="role"
                className="mb-1 w-full rounded border border-border bg-canvas px-1.5 py-0.5 text-[11px] text-text-mid focus-ring"
              />
              <input
                value={s.prompt_hint}
                onChange={(e) => edit((d) => { d[i].prompt_hint = e.target.value; })}
                placeholder="prompt hint"
                className="mb-1.5 w-full rounded border border-border bg-canvas px-1.5 py-0.5 text-[11px] text-text-mid focus-ring"
              />
              <div className="flex flex-wrap gap-1">
                {readTools.map((t) => {
                  const on = s.tools.some((ref) => ref.includes(t.id));
                  const full = !on && s.tools.length >= 3;
                  return (
                    <button
                      key={t.id}
                      onClick={() => toggleTool(i, t.id)}
                      disabled={full}
                      title={full ? 'max 3 tools per sub-agent (LOCKED)' : t.description}
                      className={cn('rounded px-1.5 py-0.5 text-[10px] mono', on ? 'bg-accent/20 text-accent' : 'bg-canvas text-text-low hover:text-text-mid', full && 'opacity-40 cursor-not-allowed')}
                    >
                      {t.id}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <Button
            variant="subtle"
            size="sm"
            icon={<Plus size={13} />}
            onClick={() => edit((d) => { d.push({ name: `agent_${d.length + 1}`, role: '', prompt_hint: 'Advisory only.', tools: [] }); })}
          >
            Add sub-agent
          </Button>
          <div className="text-[10px] text-text-low">Tools ≤3 per sub-agent, read-only catalog only (advisory scope LOCKED). Order matters for Pipeline.</div>
        </div>

        {/* live diagram */}
        <div className="rounded-control border border-border bg-canvas p-2">
          <WorkflowDiagram subs={draft} gates={gates} pattern={draftPattern} />
        </div>
      </div>
    </Card>
  );
}
