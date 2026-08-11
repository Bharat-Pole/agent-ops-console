// Section 5 — Canonical agent schema (13 groups). Field names are VERBATIM from
// the Blueprint / Section 5.2 table and must not be renamed anywhere.
//
// Design note (documented per Section 16 "report the conflict rather than
// improvising"): the Section 5.2 table enumerates every leaf across 13 groups;
// the headline "56 FIELDS" is the Blueprint's own count label (kept verbatim in
// UI copy) and does not re-derive from the table row count — analogous to the
// "11 prerequisites = 12 rows" off-by-one the spec tells us to preserve. We
// include every field the table lists, with its exact key.

import type { Prov } from './provenance';

// ---- Key enums (Section 5.2), verbatim ------------------------------------
export type CapabilityTier = 'minimal' | 'standardized' | 'advanced';
export type RiskTier = 'low' | 'medium' | 'high' | 'critical';
export type LifecycleStatus =
  | 'draft'
  | 'registered'
  | 'in_review'
  | 'approved'
  | 'live'
  | 'suspended'
  | 'retired';
export type OrchestrationType = 'single' | 'router' | 'coordinator+subagents';
export type ToolPermission = 'read' | 'summarize' | 'draft' | 'recommend' | 'validate'; // advisory-only, LOCKED
export type RetrievalType = 'semantic' | 'keyword' | 'hybrid';
export type GovernancePath = 'fast' | 'standard' | 'deep' | 'critical';
export type TrackStatus = 'not_started' | 'in_progress' | 'ready' | 'blocked';

export type Sensitivity = 'public' | 'internal' | 'confidential' | 'restricted';
export type SourceApproval = 'pending' | 'approved' | 'rejected';
export type RefreshCadence = 'manual' | 'daily' | 'weekly' | 'monthly';

// The five advisory-only tool permissions, LOCKED (Section 1.2 #4, acceptance #3).
export const ADVISORY_PERMISSIONS: ToolPermission[] = [
  'read',
  'summarize',
  'draft',
  'recommend',
  'validate',
];

// ---- Sub-structures -------------------------------------------------------
export interface SubAgent {
  name: string;
  role: string;
  prompt_hint: string;
  tools: string[]; // ≤3, no write permissions (Section 7.3, LOCKED)
}

export interface HitlGate {
  placement: string; // e.g. "pre-deploy", "per-tool-call", "on edge coordinator→notifier"
  trigger: string;
}

// ---- The 13 groups (each leaf wrapped in Prov<T>) -------------------------

// 5.1 Identity & Ownership
export interface G_Identity {
  agent_name: Prov<string>;
  agent_id: Prov<string>;
  business_owner: Prov<string>;
  technical_owner: Prov<string>;
  executive_sponsor: Prov<string | null>;
  use_case_category: Prov<string>;
  consumer_type: Prov<string>;
  intended_audience: Prov<string>;
  description: Prov<string>;
  objective: Prov<string>;
}

// 5.2 Lifecycle & Risk
export interface G_Lifecycle {
  lifecycle_status: Prov<LifecycleStatus>;
  risk_tier: Prov<RiskTier>;
  last_review_date: Prov<string | null>;
  next_review_date: Prov<string | null>;
  exception_status: Prov<string | null>;
}

// 5.3 Model
export interface G_Model {
  model_primary: Prov<string>;
  model_fallback: Prov<string | null>;
  temperature: Prov<number>;
  max_output_tokens: Prov<number>;
  context_window_ref: Prov<string>;
  cost_awareness: Prov<string>;
}

// 5.4 Prompt & Instruction
export interface G_Prompt {
  system_prompt_ref: Prov<string>;
  user_prompt_template: Prov<string | null>;
  task_prompt: Prov<string | null>;
  persona_role: Prov<string>;
  tool_use_instructions: Prov<string | null>;
  safety_instructions: Prov<string>;
  citation_rules: Prov<string | null>;
  response_format_contract: Prov<string | null>;
  stop_conditions: Prov<string | null>;
  per_sub_agent_prompts: Prov<Record<string, string> | null>;
}

// 5.5 Data & Knowledge
export interface G_Data {
  data_sources: Prov<string[]>;
  rag_enabled: Prov<boolean>;
  retrieval_type: Prov<RetrievalType | null>;
  chunk_size: Prov<number | null>;
  chunk_overlap: Prov<number | null>;
  top_k: Prov<number | null>;
  score_threshold: Prov<number | null>;
  rerank_enabled: Prov<boolean>;
  knowledge_source_refs: Prov<string[]>; // kb://<id>@<version>
  structured_grounding: Prov<boolean>;
}

// 5.6 Tooling & MCP
export interface G_Tooling {
  bound_tools: Prov<string[]>; // tools://<id>@<version> — advisory only
  tool_permission: Prov<ToolPermission>;
  mcp_connectors: Prov<string[]>;
  tool_auth: Prov<string | null>;
  rate_limits: Prov<string | null>;
}

// 5.7 Orchestration
export interface G_Orchestration {
  orchestration_type: Prov<OrchestrationType>;
  sub_agents: Prov<SubAgent[]>;
  retries: Prov<number>;
  fallback_behavior: Prov<string>;
  hitl_gate_placement: Prov<HitlGate[]>;
  a2a_enabled: Prov<boolean>;
  agent_card: Prov<string | null>; // ref to AgentCard
  message_task_format: Prov<string | null>;
  artifact_exchange: Prov<boolean>;
}

// 5.8 Governance & Approval
export interface G_Governance {
  approvals_required: Prov<string[]>;
  audit_level: Prov<string>;
  policy_controls: Prov<string[]>; // policies://<id>@<version>
}

// 5.9 Observability & FinOps
export interface G_Observability {
  cost_label: Prov<string>;
  logging_level: Prov<string>;
  required_telemetry: Prov<string[]>;
}

// 5.10 Deployment
export interface G_Deployment {
  exposure_channel: Prov<string>;
  auth_gating: Prov<string>;
  deploy_rate_limits: Prov<string | null>;
  environment: Prov<string>;
  promotion_rollback: Prov<string>;
}

// 5.11 Runtime (execution)
export interface G_Runtime {
  runtime_host: Prov<string>;
  resolver_profile: Prov<string>;
  concurrency: Prov<number>;
  timeout: Prov<number>;
  scaling_policy: Prov<string>;
  model_gateway_ref: Prov<string>; // vertex://<model-endpoint>
}

// 5.12 Knowledge Sources (per RAG source). On the agent config this represents
// the agent's ingestion policy / primary-source defaults (Section 7.3); the same
// shape is embedded verbatim on each KnowledgeSource entity (Section 5.4).
export interface G_KnowledgeSource {
  source_uri: Prov<string | null>;
  parser: Prov<string | null>;
  source_chunking: Prov<string | null>;
  embedding_model: Prov<string | null>;
  index_target: Prov<string | null>;
  sensitivity: Prov<Sensitivity | null>;
  source_approval: Prov<SourceApproval | null>;
  refresh_cadence: Prov<RefreshCadence | null>;
  source_version: Prov<string | null>;
}

// 5.13 Evidence & Artifact Store
export interface G_Evidence {
  evidence_store_uri: Prov<string | null>;
  evidence_retention: Prov<string | null>;
  artifact_links: Prov<string[]>;
}

// ---- The full config (all 13 groups) -------------------------------------
export interface AgentConfig {
  identity: G_Identity; // 5.1
  lifecycle: G_Lifecycle; // 5.2
  model: G_Model; // 5.3
  prompt: G_Prompt; // 5.4
  data: G_Data; // 5.5
  tooling: G_Tooling; // 5.6
  orchestration: G_Orchestration; // 5.7
  governance: G_Governance; // 5.8
  observability: G_Observability; // 5.9
  deployment: G_Deployment; // 5.10
  runtime: G_Runtime; // 5.11
  knowledge_sources: G_KnowledgeSource; // 5.12
  evidence: G_Evidence; // 5.13
}

export type ConfigGroupKey = keyof AgentConfig;

// ---- Signal breakdown (Section 7.2) --------------------------------------
export type SignalId = 'S1' | 'S2' | 'S3' | 'S4' | 'S5' | 'S6';

export interface SignalDetail {
  fired: boolean;
  why: string;
  // per-tier weight contribution when fired (Appendix F table), for the trace
  weight_minimal: number;
  weight_standardized: number;
  weight_advanced: number;
}

export type SignalBreakdown = Record<SignalId, SignalDetail>;

export interface TierScores {
  minimal: number;
  standardized: number;
  advanced: number;
}

// ---- Review card (Section 7.7) -------------------------------------------
export interface FieldConfirmation {
  field: string; // verbatim schema field path
  proposed_value: unknown;
  confidence: 'high' | 'medium' | 'low';
  gap_note: string;
  governance_critical: boolean;
}

export interface ReviewCard {
  proposed_tier: CapabilityTier;
  proposed_archetype: Archetype;
  tier_label: string;
  signal_breakdown: SignalBreakdown;
  scores: TierScores;
  config_summary: {
    model: string;
    rag: string;
    tools: string[];
    orchestration: string;
    a2a: string;
  };
  governance_summary: {
    risk_tier: RiskTier;
    risk_why: string;
    governance_path: GovernancePath;
    path_desc: string;
    approvals_required: string[];
    hitl_gates: number;
  };
  capability_floor_note: string | null;
  flagged_write_tools: string[];
  fields_requiring_confirmation: FieldConfirmation[];
  reasoning: string[];
  editable: true;
  user_can_override_tier: true;
  user_can_override_risk: true;
}

// Archetype template library, LOCKED list (Section 7.2)
export type Archetype =
  | 'simple_advisor'
  | 'rag_grounded_assistant'
  | 'faq_bot'
  | 'report_generator'
  | 'research_assistant'
  | 'workflow_coordinator';

// ---- Track state (Section 5.2, three tracks) -----------------------------
export interface TrackStep {
  name: string;
  status: TrackStatus;
  at: string | null;
}

export interface Track {
  status: TrackStatus;
  steps: TrackStep[];
}

export interface AgentTracks {
  registry: Track;
  runtime: Track;
  content: Track;
}

// ---- The AgentRecord aggregate (Section 5.2) -----------------------------
export interface AgentRecord {
  config: AgentConfig;
  capability_tier: CapabilityTier;
  governance_path: GovernancePath;
  tracks: AgentTracks;
  signal_breakdown: SignalBreakdown;
  review_card: ReviewCard | null;
  evaluation_pack_id: string | null;
  approval_ids: string[];
  fast_path_expiry_date: string | null;
  created_at: string;
  updated_at: string;
  demo_mode: boolean;
}

// Convenience accessors used across the UI (read `.value` off the envelope).
export function agentId(a: AgentRecord): string {
  return a.config.identity.agent_id.value;
}
export function agentName(a: AgentRecord): string {
  return a.config.identity.agent_name.value;
}

// LIVE iff all three tracks are ready (Section 1.2 #2 / acceptance #7).
export function isLive(a: AgentRecord): boolean {
  return (
    a.tracks.registry.status === 'ready' &&
    a.tracks.runtime.status === 'ready' &&
    a.tracks.content.status === 'ready'
  );
}
