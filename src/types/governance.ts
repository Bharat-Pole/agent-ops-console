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
  | 'data_source'
  // Phase 3.2 — the queue is shared across entity kinds (Blueprint §11), and
  // none of the four agent governance roles above describes cataloguing a tool.
  | 'tool_registration';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected';

// What an approval item is *about*. Everything before Phase 3.2 was an agent,
// and pre-existing rows are backfilled to 'agent' by the migration.
export type ApprovalEntityType = 'agent' | 'tool';

export interface ApprovalItem {
  id: string;
  // NULL for a non-agent item — a tool belongs to no agent. Use `entity_id`
  // for the subject; `agent_id` remains for the agent-specific machinery
  // (finalize_registry, the per-agent pending count).
  agent_id: string | null;
  step: ApprovalStep;
  // NULL for a non-agent item — a governance path is an agent concept.
  required_by_path: GovernancePath | null;
  status: ApprovalStatus;
  actor_persona: string | null;
  decided_at: string | null;
  note: string | null;
  requested_at: string;
  entity_type: ApprovalEntityType;
  entity_id: string;
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
