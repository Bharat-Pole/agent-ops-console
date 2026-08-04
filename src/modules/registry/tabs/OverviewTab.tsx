import type { AgentRecord } from '@/types';
import { Card } from '@/components/primitives';
import { SignalTable, AssetRefLink, ScoreRing } from '@/components/domain';
import { ARCHETYPE_LABEL } from '@/kernel/engine/weights';
import { PATH_DEFS, FAST_PATH_WARN_DAYS } from '@/kernel/constants';
import { useWorkspace } from '@/kernel/store';
import { agentId } from '@/types';
import { fmtDate, daysUntil, titleCase } from '@/utils/format';
import { AlertTriangle, Clock } from 'lucide-react';
import { cn } from '@/utils/cn';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] text-text-low">{label}</span>
      <span className="text-[13px] text-text-hi">{children}</span>
    </div>
  );
}

export function OverviewTab({ agent }: { agent: AgentRecord }) {
  const c = agent.config;
  const pack = useWorkspace((s) => s.evalPacks.find((p) => p.agent_id === agentId(agent)));
  const expiryDays = daysUntil(agent.fast_path_expiry_date);
  const nearExpiry = expiryDays !== null && expiryDays <= FAST_PATH_WARN_DAYS;

  const assets: string[] = [
    c.prompt.system_prompt_ref.value,
    c.prompt.citation_rules.value ?? '',
    ...c.governance.policy_controls.value,
    ...c.data.knowledge_source_refs.value,
    ...c.tooling.bound_tools.value,
    c.runtime.model_gateway_ref.value,
    c.orchestration.agent_card?.value ?? '',
  ].filter(Boolean);

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2 space-y-4">
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Objective</div>
          <p className="text-[13px] text-text-mid">{c.identity.objective.value}</p>
        </Card>

        <Card>
          <div className="mb-3 text-[13px] font-semibold text-text-hi">Signal breakdown</div>
          <SignalTable breakdown={agent.signal_breakdown} />
        </Card>

        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Linked assets</div>
          <div className="flex flex-wrap gap-1.5">
            {assets.length ? assets.map((a, i) => <AssetRefLink key={i} refUri={a} />) : <span className="text-[12px] text-text-low">No linked assets.</span>}
          </div>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <div className="mb-3 text-[13px] font-semibold text-text-hi">Details</div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Archetype">{ARCHETYPE_LABEL[agent.review_card?.proposed_archetype ?? (agent.capability_tier === 'advanced' ? 'workflow_coordinator' : agent.capability_tier === 'standardized' ? 'rag_grounded_assistant' : 'simple_advisor')]}</Field>
            <Field label="Use case">{c.identity.use_case_category.value}</Field>
            <Field label="Business owner">{c.identity.business_owner.value}</Field>
            <Field label="Technical owner">{c.identity.technical_owner.value}</Field>
            <Field label="Executive sponsor">{c.identity.executive_sponsor.value ?? '—'}</Field>
            <Field label="Audience">{c.identity.intended_audience.value}</Field>
            <Field label="Created">{fmtDate(agent.created_at)}</Field>
            <Field label="Updated">{fmtDate(agent.updated_at)}</Field>
          </div>
        </Card>

        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Governance</div>
          <div className="space-y-2 text-[12px]">
            <div className="flex justify-between"><span className="text-text-low">Path</span><span className="font-medium text-text-hi">{PATH_DEFS[agent.governance_path].label}</span></div>
            <p className="text-text-low">{PATH_DEFS[agent.governance_path].desc}</p>
            <div className="flex justify-between"><span className="text-text-low">Approvals required</span><span className="text-text-hi">{PATH_DEFS[agent.governance_path].approvals.map(titleCase).join(', ') || 'auto'}</span></div>
            <div className="flex justify-between"><span className="text-text-low">HITL gates</span><span className="text-text-hi">{PATH_DEFS[agent.governance_path].hitl_gates}</span></div>
          </div>
        </Card>

        {agent.fast_path_expiry_date && (
          <Card className={cn(nearExpiry && 'border-warn/50')}>
            <div className="flex items-center gap-2">
              {nearExpiry ? <AlertTriangle size={16} className="text-warn" /> : <Clock size={16} className="text-text-mid" />}
              <div>
                <div className="text-[12px] font-medium text-text-hi">Fast-path expiry</div>
                <div className={cn('text-[12px]', nearExpiry ? 'text-warn' : 'text-text-low')}>
                  {fmtDate(agent.fast_path_expiry_date)} · {expiryDays !== null ? `${expiryDays} days` : '—'} remaining
                </div>
              </div>
            </div>
          </Card>
        )}

        {pack?.last_run && (
          <Card className="flex items-center justify-between">
            <div>
              <div className="text-[12px] font-medium text-text-hi">Latest eval</div>
              <div className="text-[11px] text-text-low">{fmtDate(pack.last_run.date)}</div>
            </div>
            <ScoreRing score={pack.last_run.score} size={64} />
          </Card>
        )}
      </div>
    </div>
  );
}
