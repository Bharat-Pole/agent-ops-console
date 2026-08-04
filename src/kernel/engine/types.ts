// Engine I/O types (Section 7). The synthesis job runs 7 pure-function stages in
// sequence and stores per-stage output on the draft (the wizard's "engine trace").

import type {
  CapabilityTier,
  RiskTier,
  Archetype,
  SignalBreakdown,
  TierScores,
  AgentConfig,
  ReviewCard,
  SubAgent,
  FieldConfirmation,
} from '@/types';

export interface Intent {
  objective: string;
  intended_audience?: string;
  data_sources?: string[];
  tools?: string[];
  business_owner?: string;
  technical_owner?: string;
  agent_name?: string;
  // optional Phase-5 signals the user can supply to steer risk
  data_sensitivity?: string;
  regulatory_domain?: string;
}

// Stage 1 — Intake & Normalize
export interface NluResult {
  task_type: string;
  domain: string;
  data_source_mentions: string[];
  tool_mentions: string[];
  audience: string | null;
  output_format: string | null;
  action_verbs: string[];
  systems: string[];
  gaps: string[];
}

// Stage 2 — Archetype classification
export interface Classification {
  proposed_tier: CapabilityTier;
  proposed_archetype: Archetype;
  signal_breakdown: SignalBreakdown;
  scores: TierScores;
  reasoning: string[];
  capability_floor_note: string | null;
  forced: boolean;
  tool_count: number;
}

// Stage 3 — Architecture synthesis
export interface Synthesis {
  config: AgentConfig;
  sub_agents: SubAgent[];
}

// Stage 3b — Write-action detection
export interface WriteDetection {
  flagged_tools: string[];
  write_intents: { phrase: string; verb: string; note: string }[];
  risk_floor: RiskTier | null;
}

// Stage 4 — Confidence & provenance
export interface ConfidenceResult {
  fields_requiring_confirmation: FieldConfirmation[];
}

// Stage 5 — Targeted elicitation
export interface ElicitationQuestion {
  id: string;
  question: string;
  kind: 'tier' | 'risk' | 'confidence';
  priority: number;
  options: string[];
  affects: string;
}
export interface Elicitation {
  questions: ElicitationQuestion[];
  optional: ElicitationQuestion[];
}

export interface EngineTrace {
  stage1_nlu: NluResult;
  stage2_classification: Classification;
  stage3_synthesis: { summary: Record<string, unknown>; sub_agents: SubAgent[] };
  stage3b_writeDetect: WriteDetection;
  stage4_confidence: ConfidenceResult;
  stage5_elicitation: Elicitation;
  stage6_reviewCard: ReviewCard;
  stage7_evalGen: { case_count: number; categories: string[] };
}

export interface SynthesisResult {
  intent: Intent;
  config: AgentConfig;
  review_card: ReviewCard;
  risk_tier: RiskTier;
  capability_tier: CapabilityTier;
  archetype: Archetype;
  elicitation: Elicitation;
  flagged_write_tools: string[];
  trace: EngineTrace;
}
