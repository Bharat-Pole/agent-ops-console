// Section 5.4 / 8 — Governance, evaluation, approvals, audit.

import type { GovernancePath } from './agent';

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
