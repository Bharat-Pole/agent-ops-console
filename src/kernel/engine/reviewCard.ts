// Stage 6 — Review card (Section 7.7). Emits exactly the Blueprint's structure.

import type { Classification, WriteDetection, ConfidenceResult, Synthesis } from './types';
import type { ReviewCard, RiskTier } from '@/types';
import { TIER_LABEL, PATH_DEFS, governancePathFor } from '@/kernel/constants';

export function buildReviewCard(
  cls: Classification,
  synth: Synthesis,
  write: WriteDetection,
  conf: ConfidenceResult,
  risk: RiskTier,
  riskWhy: string,
): ReviewCard {
  const tier = cls.proposed_tier;
  const cfg = synth.config;
  const path = governancePathFor(tier, risk);
  const pd = PATH_DEFS[path];

  const modelSummary =
    tier === 'minimal'
      ? cfg.model.model_primary.value
      : `${cfg.model.model_primary.value}${cfg.model.model_fallback.value ? ` (+ ${cfg.model.model_fallback.value} fallback)` : ''}`;

  return {
    proposed_tier: tier,
    proposed_archetype: cls.proposed_archetype,
    tier_label: TIER_LABEL[tier],
    signal_breakdown: cls.signal_breakdown,
    scores: cls.scores,
    config_summary: {
      model: modelSummary,
      rag: cfg.data.rag_enabled.value ? `Enabled (${cfg.data.retrieval_type.value ?? 'hybrid'} retrieval)` : 'Disabled',
      tools: cfg.tooling.bound_tools.value.map((t) => t.replace('tools://', '').split('@')[0]),
      orchestration: cfg.orchestration.orchestration_type.value,
      a2a: cfg.orchestration.a2a_enabled.value ? (cfg.orchestration.artifact_exchange.value ? 'full exchange' : 'discovery only') : 'disabled',
    },
    governance_summary: {
      risk_tier: risk,
      risk_why: riskWhy,
      governance_path: path,
      path_desc: pd.desc,
      approvals_required: pd.approvals,
      hitl_gates: pd.hitl_gates,
    },
    capability_floor_note: cls.capability_floor_note,
    flagged_write_tools: write.flagged_tools,
    fields_requiring_confirmation: conf.fields_requiring_confirmation,
    reasoning: cls.reasoning,
    editable: true,
    user_can_override_tier: true,
    user_can_override_risk: true,
  };
}
