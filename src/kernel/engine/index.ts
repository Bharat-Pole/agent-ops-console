// The synthesis engine orchestrator (Section 7). Runs the 7 stages in sequence
// and returns a SynthesisResult carrying the full config, review card, elicitation
// questions, and the per-stage engine trace (shown in the wizard's trace panel).

import type { Intent, SynthesisResult, Classification, EngineTrace, ArchitectureRecommendation } from './types';
import type { CapabilityTier, Architecture } from '@/types';
import { detectNlu } from './nlu';
import { classify } from './signals';
import { detectWriteActions } from './writeDetect';
import { inferRisk } from './risk';
import { synthesize as synthArch, toolRef } from './templates';
import { assessConfidence } from './confidence';
import { elicit } from './elicitation';
import { buildReviewCard } from './reviewCard';
import { pickArchetypeForTier } from './archetype';
import { deriveBaselineArchitecture, buildRecommendation, validateArchitecture, recommendationFromLlm } from './architecture';
import type { LlmArchitectureProposal } from './architecture';

export * from './types';
export { WEIGHTS, BASE_MINIMAL, SIGNAL_LABEL, ARCHETYPE_LABEL } from './weights';
export { ARCHITECTURES, ARCHITECTURE_LABEL, deriveBaselineArchitecture, validateArchitecture, synthesizeGraphSpec, recommendationFromLlm } from './architecture';
export type { LlmArchitectureProposal } from './architecture';

const TIER_INDEX: Record<CapabilityTier, number> = { minimal: 0, standardized: 1, advanced: 2 };

function assemble(intent: Intent, cls: Classification, recOverride?: ArchitectureRecommendation): SynthesisResult {
  const nlu = detectNlu(intent);
  const write = detectWriteActions(intent);
  const riskRes = inferRisk(intent, write);
  const risk = riskRes.risk_tier;

  // Stage 2b — architecture recommendation (deterministic baseline unless an
  // already-validated recommendation is supplied, e.g. a user override).
  const rec = recOverride ?? deriveBaselineArchitecture(intent, nlu, cls);
  const synth = synthArch(intent, nlu, cls, write, risk, rec);
  const conf = assessConfidence(cls, write, risk, cls.proposed_tier);
  const elicitation = elicit(intent, nlu, cls, write, risk);
  const reviewCard = buildReviewCard(cls, synth, write, conf, risk, riskRes.why);

  const trace: EngineTrace = {
    stage1_nlu: nlu,
    stage2_classification: cls,
    stage2b_architecture: rec,
    stage3_synthesis: {
      summary: {
        model: synth.config.model.model_primary.value,
        rag_enabled: synth.config.data.rag_enabled.value,
        orchestration: synth.config.orchestration.orchestration_type.value,
        bound_tools: synth.config.tooling.bound_tools.value,
      },
      sub_agents: synth.sub_agents,
    },
    stage3b_writeDetect: write,
    stage4_confidence: conf,
    stage5_elicitation: elicitation,
    stage6_reviewCard: reviewCard,
    stage7_evalGen: { case_count: cls.proposed_tier === 'minimal' ? 4 : 6, categories: ['grounding', 'correctness', 'safety_boundary', 'latency_cost', 'regression'] },
  };

  return {
    intent,
    config: synth.config,
    review_card: reviewCard,
    risk_tier: risk,
    capability_tier: cls.proposed_tier,
    archetype: cls.proposed_archetype,
    architecture: rec.architecture,
    elicitation,
    flagged_write_tools: write.flagged_tools,
    trace,
  };
}

// Full 7-stage synthesis from an intent.
export function synthesize(intent: Intent): SynthesisResult {
  const nlu = detectNlu(intent);
  const cls = classify(intent, nlu);
  return assemble(intent, cls);
}

export interface TierOverrideResult {
  accepted: boolean;
  note: string;
  result?: SynthesisResult;
}

// Section 7.7 — tier override. Upward is free; downward re-runs Stage 2 and
// either concedes or explains why not.
export function applyTierOverride(intent: Intent, desired: CapabilityTier): TierOverrideResult {
  const nlu = detectNlu(intent);
  const engineCls = classify(intent, nlu);
  const engineTier = engineCls.proposed_tier;

  if (TIER_INDEX[desired] >= TIER_INDEX[engineTier]) {
    const cls: Classification = {
      ...engineCls,
      proposed_tier: desired,
      proposed_archetype: pickArchetypeForTier(desired, nlu),
      reasoning: [...engineCls.reasoning, `USER OVERRIDE: raised tier ${engineTier} → ${desired} (upward, accepted)`],
    };
    return { accepted: true, note: `Raised to ${desired}.`, result: assemble(intent, cls) };
  }

  // downward — re-evaluate against hard gates / capability floor
  const b = engineCls.signal_breakdown;
  if (desired === 'minimal' && b.S1.fired) {
    return { accepted: false, note: 'Retrieval need detected (S1) → Minimal cannot ground answers. Override refused.' };
  }
  if (engineCls.forced && TIER_INDEX[desired] < TIER_INDEX.advanced) {
    return { accepted: false, note: 'Explicit multi-agent (S6) or ≥4 tools forces Advanced. Override refused.' };
  }
  const cls: Classification = {
    ...engineCls,
    proposed_tier: desired,
    proposed_archetype: pickArchetypeForTier(desired, nlu),
    reasoning: [...engineCls.reasoning, `USER OVERRIDE: lowered tier ${engineTier} → ${desired} (re-evaluated, conceded)`],
  };
  return { accepted: true, note: `Lowered to ${desired} after re-evaluation.`, result: assemble(intent, cls) };
}

export interface ArchitectureOverrideResult {
  accepted: boolean;
  note: string;
  result?: SynthesisResult;
}

// Architecture override — mirrors applyTierOverride. Builds the desired shape,
// re-validates it against the hard gates + advisory rules, and either re-synthesizes
// or refuses with the first violation. Tier is left untouched.
export function applyArchitectureOverride(intent: Intent, desired: Architecture): ArchitectureOverrideResult {
  const nlu = detectNlu(intent);
  const cls = classify(intent, nlu);
  const write = detectWriteActions(intent);
  const boundTools = (intent.tools ?? []).filter((t) => !write.flagged_tools.includes(t)).map(toolRef);

  const candidate = buildRecommendation(desired, intent, nlu, cls, 'deterministic', [
    `USER OVERRIDE: architecture → ${desired}`,
  ]);
  const check = validateArchitecture(candidate, cls, boundTools);
  if (!check.ok) {
    return { accepted: false, note: check.violations[0] ?? `Cannot switch to ${desired}.` };
  }
  return { accepted: true, note: `Architecture set to ${desired}.`, result: assemble(intent, cls, candidate) };
}

// Apply an LLM recommender's proposal (LLM-first mechanism). Re-validates the
// proposal deterministically; on any validation failure the caller keeps the
// deterministic baseline. Never trusts the LLM blindly.
export function applyLlmRecommendation(intent: Intent, llm: LlmArchitectureProposal): ArchitectureOverrideResult {
  const nlu = detectNlu(intent);
  const cls = classify(intent, nlu);
  const write = detectWriteActions(intent);
  const boundTools = (intent.tools ?? []).filter((t) => !write.flagged_tools.includes(t)).map(toolRef);

  const rec = recommendationFromLlm(intent, nlu, cls, boundTools, llm);
  if (!rec) {
    return { accepted: false, note: `LLM architecture "${llm.architecture}" failed validation — keeping rule-based default.` };
  }
  return { accepted: true, note: `Architecture recommended: ${rec.architecture}.`, result: assemble(intent, cls, rec) };
}
