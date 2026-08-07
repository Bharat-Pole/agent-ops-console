import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Badge, TierBadge, EmptyState, JsonViewer } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { Share2, ChevronDown, ChevronRight, Info, Pencil, Check, X } from 'lucide-react';

function EndpointField({ agentId, endpoint, overridden }: { agentId: string; endpoint: string; overridden: boolean }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(endpoint);

  if (!editing) {
    return (
      <div className="mt-2 flex items-center gap-1 text-[11px] text-text-low">
        endpoint: <span className="mono text-text-mid">{endpoint}</span>
        {overridden && <Badge tone="accent">custom</Badge>}
        <button onClick={() => { setValue(endpoint); setEditing(true); }} className="text-text-low hover:text-accent">
          <Pencil size={11} />
        </button>
      </div>
    );
  }
  return (
    <div className="mt-2 flex items-center gap-1">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="flex-1 rounded-control border border-border bg-canvas px-1.5 py-1 text-[11px] text-text-hi mono"
      />
      <button
        onClick={() => { void api.updateA2AEndpoint(agentId, value); setEditing(false); }}
        className="text-ok hover:brightness-125"
      ><Check size={13} /></button>
      <button onClick={() => setEditing(false)} className="text-text-low hover:text-err"><X size={13} /></button>
    </div>
  );
}

export default function A2APage() {
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const a2aCards = useWorkspace((s) => s.a2aCards);
  const [skillFilter, setSkillFilter] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const nonA2a = agents.length - a2aCards.length;
  const allSkills = [...new Set(a2aCards.flatMap((c) => c.skills))].sort();
  const shown = skillFilter ? a2aCards.filter((c) => c.skills.includes(skillFilter)) : a2aCards;

  return (
    <div>
      <PageHeader title="A2A Directory" description="Real agent cards, derived from each agent's live config. Standardized agents are discovery-only; Advanced agents show full exchange config."
        action={<select value={skillFilter} onChange={(e) => setSkillFilter(e.target.value)} className="h-8 rounded-control border border-border bg-canvas px-2 text-[13px] text-text-mid focus-ring"><option value="">Filter by skill: all</option>{allSkills.map((s) => <option key={s} value={s}>{s}</option>)}</select>} />

      {a2aCards.length === 0 ? (
        <EmptyState icon={<Share2 size={26} />} title="No A2A-enabled agents" message="Minimal agents don't publish an agent card." />
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {shown.map((c) => {
            const isOpen = expanded === c.agent_id;
            return (
              <Card key={c.agent_id}>
                <div className="mb-2 flex items-start justify-between">
                  <button onClick={() => navigate(`/agents/${c.agent_id}`)} className="text-left text-[13px] font-semibold text-text-hi hover:text-accent">{c.name}</button>
                  <TierBadge tier={c.capability_tier} />
                </div>
                <Badge tone={c.discovery_only ? 'neutral' : 'info'}>{c.discovery_only ? 'Discovery only' : 'Full exchange'}</Badge>
                {c.discovery_only && <p className="mt-1 text-[11px] text-text-low">Findable but passive (message_task_format=null, artifact_exchange=false).</p>}
                {!c.discovery_only && <p className="mt-1 text-[11px] text-text-low">message_task_format={c.message_task_format}, artifact_exchange=true.</p>}

                <div className="mt-2 flex flex-wrap gap-1">
                  {c.skills.map((s) => <span key={s} className={`rounded px-1.5 py-0.5 text-[10px] ${s === skillFilter ? 'bg-accent/20 text-accent' : 'bg-raised text-text-mid'}`}>{s}</span>)}
                </div>

                <EndpointField agentId={c.agent_id} endpoint={c.endpoint} overridden={c.endpoint_overridden} />

                <button onClick={() => setExpanded(isOpen ? null : c.agent_id)} className="mt-2 flex items-center gap-1 text-[11px] text-accent hover:underline">
                  {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />} input/output schema
                </button>
                {isOpen && (
                  <div className="mt-1">
                    <JsonViewer data={{ input_schema: c.input_schema, output_schema: c.output_schema }} maxHeight={160} />
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
