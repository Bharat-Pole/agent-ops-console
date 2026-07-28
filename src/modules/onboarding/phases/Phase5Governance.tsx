import { Card, Button, Badge } from '@/components/primitives';
import { GovernanceMatrix } from '@/components/domain';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { governancePathFor, PATH_DEFS, RISK_ORDER } from '@/kernel/constants';
import { nowIso, audit } from '@/kernel/api';
import type { RiskTier } from '@/types';
import { titleCase } from '@/utils/format';
import { ArrowRight, ArrowLeft } from 'lucide-react';

function deriveRisk(sensitivity: string, regulatory: string, base: RiskTier): RiskTier {
  if (/cross-border|fcc|puc|financial/i.test(regulatory) || sensitivity === 'restricted') return 'critical';
  if (regulatory.trim() !== '' || sensitivity === 'confidential') return 'high';
  if (sensitivity === 'internal') return base === 'critical' || base === 'high' ? base : 'medium';
  return base;
}

export function Phase5Governance({ draft, patch, goPhase }: PhaseProps) {
  const agent = useWorkspace((s) => s.agents.find((a) => a.config.identity.agent_id.value === draft.agent_id));
  const patchAgent = useWorkspace((s) => s.patchAgent);

  if (!agent) {
    return <Card><div className="text-[13px] text-text-mid">Register the agent (Phase 3) first.</div><Button className="mt-3" variant="ghost" onClick={() => goPhase(3)}>← Back to Phase 3</Button></Card>;
  }

  const tier = agent.capability_tier;
  const risk = agent.config.lifecycle.risk_tier.value;
  const path = agent.governance_path;
  const pd = PATH_DEFS[path];

  const applyRisk = (newRisk: RiskTier) => {
    const newPath = governancePathFor(tier, newRisk);
    patchAgent(draft.agent_id!, (a) => ({
      ...a,
      governance_path: newPath,
      config: { ...a.config, lifecycle: { ...a.config.lifecycle, risk_tier: { ...a.config.lifecycle.risk_tier, value: newRisk, verified_flag: true, confidence: 'high', gap_note: null } } },
      updated_at: nowIso(),
    }));
    patch((d) => ({ ...d, confirmedRisk: newRisk }));
    audit('config_change', 'agent', draft.agent_id!, `risk_tier → ${newRisk}; governance path re-derived → ${newPath}.`);
  };

  const onSensitivity = (sensitivity: string) => {
    patch((d) => ({ ...d, governance: { ...d.governance, sensitivity } }));
    applyRisk(deriveRisk(sensitivity, draft.governance.regulatory, risk));
  };
  const onRegulatory = (regulatory: string) => {
    patch((d) => ({ ...d, governance: { ...d.governance, regulatory } }));
    applyRisk(deriveRisk(draft.governance.sensitivity, regulatory, risk));
  };

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <div className="mb-3 text-[13px] font-semibold text-text-hi">Phase 5 · Add Governance Gates</div>
        <div className="space-y-3">
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Data sensitivity</div>
            <select value={draft.governance.sensitivity} onChange={(e) => onSensitivity(e.target.value)} className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring">
              <option value="">select…</option>
              <option value="public">public</option>
              <option value="internal">internal</option>
              <option value="confidential">confidential</option>
              <option value="restricted">restricted</option>
            </select>
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Regulatory domain</div>
            <input value={draft.governance.regulatory} onChange={(e) => onRegulatory(e.target.value)} placeholder="e.g. FCC / PUC / cross-border (blank if none)" className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring" />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Risk tier (override)</div>
            <div className="flex gap-1.5">
              {RISK_ORDER.map((r) => (
                <button key={r} onClick={() => applyRisk(r)} className={`flex-1 rounded-control border px-2 py-1.5 text-[12px] capitalize ${r === risk ? 'border-accent bg-accent/15 text-accent' : 'border-border text-text-mid hover:border-border-strong'}`}>{r}</button>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <div className="space-y-4">
        <Card>
          <div className="mb-3 text-[13px] font-semibold text-text-hi">Governance path = f(capability, risk)</div>
          <GovernanceMatrix activeTier={tier} activeRisk={risk} />
        </Card>
        <Card>
          <div className="mb-2 flex items-center gap-2 text-[13px] font-semibold text-text-hi">Path: <Badge tone="accent">{pd.label}</Badge></div>
          <p className="mb-2 text-[12px] text-text-low">{pd.desc}</p>
          <div className="text-[12px] text-text-mid">Required approvals: {pd.approvals.map(titleCase).join(', ') || 'auto (fast path)'}</div>
          <div className="text-[12px] text-text-mid">HITL gates: {pd.hitl_gates}</div>
        </Card>
        <div className="flex items-center gap-2">
          <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => goPhase(4)}>Back</Button>
          <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => goPhase(6)}>Next: Evaluate & Approve</Button>
        </div>
      </div>
    </div>
  );
}
