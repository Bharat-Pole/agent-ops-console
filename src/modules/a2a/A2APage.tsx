import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Badge, TierBadge, EmptyState, JsonViewer } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { agentId, type AgentRecord } from '@/types';
import { Share2, ChevronDown, ChevronRight, Info } from 'lucide-react';

function skillsOf(a: AgentRecord): string[] {
  const base = [`${a.config.identity.use_case_category.value}-qa`];
  if (a.config.data.rag_enabled.value) base.push('grounded-answer', 'summarization');
  const subs = a.config.orchestration.sub_agents.value.map((s) => s.name);
  return [...base, ...subs];
}

export default function A2APage() {
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const [skillFilter, setSkillFilter] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const a2aAgents = agents.filter((a) => a.config.orchestration.a2a_enabled.value);
  const nonA2a = agents.length - a2aAgents.length;

  const allSkills = [...new Set(a2aAgents.flatMap(skillsOf))].sort();
  const shown = skillFilter ? a2aAgents.filter((a) => skillsOf(a).includes(skillFilter)) : a2aAgents;

  return (
    <div>
      <PageHeader title="A2A Directory" description="Agent cards for a2a_enabled agents. Standardized agents are discovery-only; Advanced agents show full exchange config."
        action={<select value={skillFilter} onChange={(e) => setSkillFilter(e.target.value)} className="h-8 rounded-control border border-border bg-canvas px-2 text-[13px] text-text-mid focus-ring"><option value="">Filter by skill: all</option>{allSkills.map((s) => <option key={s} value={s}>{s}</option>)}</select>} />

      {a2aAgents.length === 0 ? (
        <EmptyState icon={<Share2 size={26} />} title="No A2A-enabled agents" message="Minimal agents don't publish an agent card." />
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {shown.map((a) => {
            const discoveryOnly = !a.config.orchestration.artifact_exchange.value;
            const endpoint = a.config.orchestration.agent_card.value ?? `a2a://${agentId(a)}`;
            const isOpen = expanded === agentId(a);
            return (
              <Card key={agentId(a)}>
                <div className="mb-2 flex items-start justify-between">
                  <button onClick={() => navigate(`/agents/${agentId(a)}`)} className="text-left text-[13px] font-semibold text-text-hi hover:text-accent">{a.config.identity.agent_name.value}</button>
                  <TierBadge tier={a.capability_tier} />
                </div>
                <Badge tone={discoveryOnly ? 'neutral' : 'info'}>{discoveryOnly ? 'Discovery only' : 'Full exchange'}</Badge>
                {discoveryOnly && <p className="mt-1 text-[11px] text-text-low">Findable but passive (message_task_format=null, artifact_exchange=false).</p>}
                {!discoveryOnly && <p className="mt-1 text-[11px] text-text-low">message_task_format={a.config.orchestration.message_task_format.value}, artifact_exchange=true.</p>}

                <div className="mt-2 flex flex-wrap gap-1">
                  {skillsOf(a).map((s) => <span key={s} className={`rounded px-1.5 py-0.5 text-[10px] ${s === skillFilter ? 'bg-accent/20 text-accent' : 'bg-raised text-text-mid'}`}>{s}</span>)}
                </div>

                <div className="mt-2 text-[11px] text-text-low">endpoint: <span className="mono text-text-mid">{endpoint}</span></div>

                <button onClick={() => setExpanded(isOpen ? null : agentId(a))} className="mt-2 flex items-center gap-1 text-[11px] text-accent hover:underline">
                  {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />} input/output schema
                </button>
                {isOpen && (
                  <div className="mt-1">
                    <JsonViewer data={{ input_schema: { query: 'string', context: 'string?' }, output_schema: { answer: 'string', citations: 'string[]' } }} maxHeight={160} />
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {nonA2a > 0 && (
        <Card className="mt-4 border-info/30 bg-info/5">
          <div className="flex items-start gap-2 text-[12px] text-text-mid">
            <Info size={14} className="mt-0.5 text-info" />
            <span><b>{nonA2a}</b> agent(s) are not shown — Minimal-tier agents (Simple Advisor / FAQ Bot) don't publish an A2A card. A2A begins at Standardized (discovery-only) and becomes full exchange at Advanced.</span>
          </div>
        </Card>
      )}
    </div>
  );
}
