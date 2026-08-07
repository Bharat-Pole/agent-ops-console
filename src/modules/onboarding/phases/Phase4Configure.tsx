import { useState } from 'react';
import { Card, Button, Badge } from '@/components/primitives';
import { AssetRefLink } from '@/components/domain';
import { GeneratePromptDialog } from '@/modules/prompts/GeneratePromptDialog';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import type { AgentRecord } from '@/types';
import { ChevronDown, ChevronRight, ArrowRight, ArrowLeft, Ban, ShieldAlert, Sparkles } from 'lucide-react';
import { cn } from '@/utils/cn';

// Section 9.4/9.3 bridge — citation_rules is the one G_Prompt field already
// surfaced on this page. Lets the builder pick an existing governed citation
// prompt or draft a fresh one with AI (reviewed before it's saved) instead of
// only ever inheriting whatever the synthesis engine picked in Phase 1.
function CitationRulesField({ agent }: { agent: AgentRecord }) {
  const citationPrompts = useWorkspace((s) => s.prompts.filter((p) => p.kind === 'citation'));
  const knowledgeSources = useWorkspace((s) => s.knowledgeSources);
  const persona = useWorkspace((s) => s.ui.persona);
  const [dialogOpen, setDialogOpen] = useState(false);
  const currentRef = agent.config.prompt.citation_rules.value;
  const currentId = currentRef ? currentRef.replace('prompts://', '').split('@')[0] : '';

  const setRef = (ref: string) => {
    void api.proposeConfigChange(agent.config.identity.agent_id.value, 'prompt', 'citation_rules', ref);
  };

  const onSelect = (id: string) => {
    const p = citationPrompts.find((x) => x.id === id);
    if (p) setRef(`prompts://${p.id}@${p.version}`);
  };

  const onAccept = async (result: { name: string; body: string }) => {
    const id = await api.createPrompt({
      name: result.name,
      body: result.body,
      kind: 'citation',
      category: 'rag',
      owner: `${persona}@brightspeed.com`,
      source: 'llm_generated',
      generated_from: agent.config.identity.agent_id.value,
    });
    if (id) setRef(`prompts://${id}@v1`);
  };

  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 last:border-0 text-[12px]">
      <span className="text-text-low">citation_rules</span>
      <div className="flex items-center gap-1.5">
        {currentRef ? <AssetRefLink refUri={currentRef} /> : <span className="text-text-low">—</span>}
        <select
          className="rounded border border-border bg-canvas px-1.5 py-1 text-[11px] text-text-hi focus-ring"
          value={citationPrompts.some((p) => p.id === currentId) ? currentId : ''}
          onChange={(e) => e.target.value && onSelect(e.target.value)}
        >
          <option value="" disabled>Select existing…</option>
          {citationPrompts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.status})</option>)}
        </select>
        <button
          onClick={() => setDialogOpen(true)}
          className="flex items-center gap-1 rounded border border-border px-1.5 py-1 text-[11px] text-text-mid hover:border-border-strong"
        >
          <Sparkles size={11} /> Generate with AI
        </button>
        <GeneratePromptDialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          kind="citation"
          category="rag"
          // Was only {agent_name, agent_id} — the AI had no idea what the
          // agent actually does, hence generic output. Real objective/
          // audience/tools/sources give it something to ground the draft in.
          baseContext={{
            agent_name: agent.config.identity.agent_name.value,
            agent_id: agent.config.identity.agent_id.value,
            objective: agent.config.identity.objective.value,
            audience: agent.config.identity.intended_audience.value,
            tools: agent.config.tooling.bound_tools.value.map((ref) => ref.replace('tools://', '').split('@')[0]),
            data_sources: agent.config.data.knowledge_source_refs.value.map((ref) => {
              const id = ref.replace('kb://', '').split('@')[0];
              return knowledgeSources.find((s) => s.id === id)?.name ?? id;
            }),
          }}
          onAccept={onAccept}
        />
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 last:border-0 text-[12px]">
      <span className="text-text-low">{label}</span>
      <span className="text-text-hi">{children}</span>
    </div>
  );
}

// Small SVG workflow diagram: coordinator → sub-agents, with HITL gate markers.
function WorkflowDiagram({ subs, gates }: { subs: { name: string }[]; gates: number }) {
  const w = 520, cx = 60, cy = 20 + subs.length * 18;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${Math.max(120, subs.length * 44 + 20)}`} className="text-text-mid">
      <rect x={10} y={cy - 14} width={100} height={28} rx={6} fill="var(--tier-advanced)" opacity={0.2} stroke="var(--tier-advanced)" />
      <text x={cx} y={cy + 4} textAnchor="middle" fontSize="11" fill="var(--text-hi)">coordinator</text>
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

export function Phase4Configure({ draft, goPhase }: PhaseProps) {
  const agent = useWorkspace((s) => s.agents.find((a) => a.config.identity.agent_id.value === draft.agent_id));
  const tools = useWorkspace((s) => s.tools);
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
    void api.proposeConfigChange(draft.agent_id!, 'orchestration', 'a2a_enabled', !c.orchestration.a2a_enabled.value);
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
                <CitationRulesField agent={agent} />
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

      {/* Sub-agent editor + SVG workflow diagram (Advanced) */}
      {isAdv && c.orchestration.sub_agents.value.length > 0 && (
        <Card>
          <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-text-hi"><ShieldAlert size={15} className="text-tier-advanced" /> Sub-agent editor</div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              {c.orchestration.sub_agents.value.map((s) => (
                <div key={s.name} className="rounded-control border border-border bg-raised/30 p-2.5">
                  <div className="mono text-[12px] text-text-hi">{s.name}</div>
                  <div className="text-[11px] text-text-mid">{s.role}</div>
                  <div className="mt-1 text-[10px] text-text-low">tools ≤3, no write: {s.tools.length ? s.tools.map((t) => t.replace('tools://', '').split('@')[0]).join(', ') : 'none'}</div>
                </div>
              ))}
            </div>
            <div className="rounded-control border border-border bg-canvas p-2">
              <WorkflowDiagram subs={c.orchestration.sub_agents.value} gates={c.orchestration.hitl_gate_placement.value.length} />
            </div>
          </div>
        </Card>
      )}

      <div className="flex items-center gap-2">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => goPhase(3)}>Back</Button>
        <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => goPhase(5)}>Next: Governance Gates</Button>
      </div>
    </div>
  );
}
