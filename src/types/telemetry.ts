// Section 6.2 / 9.9 — jobs and telemetry.

export type JobKind =
  | 'synthesis'
  | 'runtime_provision'
  | 'content_index'
  | 'evaluation_run'
  | 'healthcheck';

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface Job {
  id: string;
  kind: JobKind;
  label: string;
  entity_id: string; // agent_id / source_id / pack_id
  status: JobStatus;
  progress: number; // 0–1
  step_label: string | null; // current named sub-step
  result: unknown;
  created_at: string;
}

// Per-agent daily telemetry point (Section 9.9), from real request_telemetry
// rows recorded on every chat/eval call (services/monitoring.py). `cost` is
// real too — real tokens that day priced at the real per-model rate from the
// Model Repository (module 3), not a flat per-token estimate.
export interface TelemetryPoint {
  day: string; // ISO date
  requests: number;
  tokens_in: number;
  tokens_out: number;
  p95_ms: number;
  errors: number;
  cost: number;
}

export interface AgentTelemetry {
  agent_id: string;
  series: TelemetryPoint[];
  eval_score_history: { date: string; score: number }[];
}

export type Persona =
  | 'business_owner'
  | 'platform_engineer'
  | 'governance_officer'
  | 'team_lead';
