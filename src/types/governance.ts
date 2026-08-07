// Section 5.4 / 8 — Governance, evaluation, approvals, audit.

import type { CapabilityTier, GovernancePath, RiskTier } from './agent';

// ---- Evaluation packs -----------------------------------------------------
export type EvalCategory =
  | 'grounding'
  | 'correctness'
  | 'safety_boundary'
  | 'latency_cost'
  | 'regression';

export type EvalResult = 'pass' | 'fail' | null;

export interface EvalCase {
  test_id: string;
  category: EvalCategory;
  input: string;
  expected_output: string;
  evaluation_method: string;
  pass_threshold: string;
  last_result: EvalResult;
}

export interface EvalRun {
  date: string;
  score: number; // 0–100
  results: Record<string, EvalResult>; // test_id -> result
}

export interface EvaluationPack {
  id: string;
  agent_id: string;
  generated_by: 'engine';
  cases: EvalCase[];
  last_run: EvalRun | null;
}

// ---- Approvals ------------------------------------------------------------
export type ApprovalStep =
  | 'business_owner'
  | 'risk_officer'
  | 'security_committee'
  | 'data_source';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected';

export interface ApprovalItem {
  id: string;
  agent_id: string;
  step: ApprovalStep;
  required_by_path: GovernancePath;
  status: ApprovalStatus;
  actor_persona: string | null;
  target_ref: string | null;
  decided_at: string | null;
  note: string | null;
  requested_at: string;
}

// ---- Audit log (append-only) ---------------------------------------------
export type EntityType =
  | 'agent'
  | 'prompt'
  | 'tool'
  | 'connector'
  | 'model'
  | 'source'
  | 'pipeline'
  | 'eval'
  | 'approval'
  | 'workspace';

export interface AuditEvent {
  id: string;
  at: string;
  actor_persona: string;
  action: string;
  entity_type: EntityType;
  entity_id: string;
  detail: string;
}

// ---- Governance path definitions (Section 8.1), verbatim ------------------
export interface PathDefinition {
  path: GovernancePath;
  label: string;
  approvals: string[];
  hitl_gates: number;
  desc: string;
}

// ---- Policy-as-configuration (Blueprint §9) — real DB rows backing what used
// to be the hardcoded GOVERNANCE_MATRIX; registration.py reads these live. ---
export interface PolicyRule {
  capability_tier: CapabilityTier;
  risk_tier: RiskTier;
  governance_path: GovernancePath;
  updated_at?: string;
  updated_by?: string | null;
}

// ---- Governance Exception Register (Blueprint §9 "Exception Management") --
export type ExceptionStatus = 'active' | 'expired' | 'revoked';

export interface GovernanceException {
  id: string;
  agent_id: string;
  reason: string;
  granted_by: string;
  status: ExceptionStatus;
  expires_at: string;
  created_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
}
