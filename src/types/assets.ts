// Section 5.4 — Other entities (assets that agents reference).

import type { Prov } from './provenance';
import type { ToolPermission, Sensitivity, SourceApproval, RefreshCadence, TrackStatus, RiskTier, CapabilityTier } from './agent';

// ---- Prompt Repository ----------------------------------------------------
export type PromptKind =
  | 'system'
  | 'user_template'
  | 'task'
  | 'persona'
  | 'tool_use'
  | 'citation'
  | 'template'
  | 'safety'
  | 'refusal'
  | 'escalation'
  | 'stop_condition';
export type PromptCategory = 'agent' | 'tool' | 'mcp' | 'rag'; // which module consumes this prompt
export type PromptSource = 'manual' | 'llm_generated';
export type PromptStatus = 'draft' | 'approved' | 'deprecated';

export interface PromptHistoryEntry {
  version: string;
  date: string;
  note: string;
  // Full body snapshot as of this version — absent on entries recorded
  // before version-snapshotting shipped, so compare/rollback can't offer
  // those older entries rather than fabricate their text.
  body?: string;
}

export interface PromptAsset {
  id: string;
  version: string;
  name: string;
  kind: PromptKind;
  category: PromptCategory;
  source: PromptSource;
  generated_from: string | null; // agent_id or job_id, when source = llm_generated
  body: string;
  status: PromptStatus;
  owner: string;
  used_by: string[]; // agent_id[]
  history: PromptHistoryEntry[];
  domain: string | null; // free text, mirrors G_Identity.use_case_category vocabulary
  use_case: string | null; // free text description of the specific use case this prompt supports
  risk_tier: RiskTier | null;
  agent_type: CapabilityTier | null;
  // Real, mechanically-applied citation template for kind='citation' prompts —
  // placeholders: {source_name} {source_id} {doc_id} {doc_title}. Null = the
  // platform default "[source: kb://<id> · <doc_id>]" bracket format.
  citation_format: string | null;
}

// ---- Tool Catalog ---------------------------------------------------------
export type ToolStatus = 'available' | 'degraded' | 'offline';

export interface ToolSchema {
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

export type ToolRiskLevel = 'low' | 'medium' | 'high';

export interface ToolAsset {
  id: string;
  version: string;
  name: string;
  description: string;
  category: string;
  permission_ceiling: ToolPermission;
  write_capable: boolean; // true → catalogued but NEVER bindable (Section 7.6)
  connector_id: string | null;
  schema: ToolSchema;
  status: ToolStatus;
  used_by: string[]; // agent_id[]
  // Real backend fields (routes/tools.py) — optional so seed-era literals
  // built before the real Tool Registry backend still typecheck.
  owner?: string | null;
  risk_level?: ToolRiskLevel;
  created_at?: string | null;
  updated_at?: string;
  // Canned fixtures the Playground uses to render a simulated tool result.
  result_fixtures?: string[];
}

// ---- MCP Connectors -------------------------------------------------------
export type McpTransport = 'sse' | 'stdio' | 'http';
export type McpAuthMode = 'secret_manager' | 'oauth' | 'none';
export type McpStatus = 'connected' | 'degraded' | 'offline';

export interface McpConnector {
  id: string;
  name: string;
  transport: McpTransport;
  endpoint: string;
  auth_mode: McpAuthMode;
  status: McpStatus;
  tools_provided: string[]; // tool_id[]
  last_healthcheck: string | null;
  last_error?: string | null;
  created_at?: string;
  updated_at?: string;
}

// ---- Knowledge Sources (the 5.12 group verbatim + entity metadata) --------
export interface KnowledgeSnippet {
  doc_id: string; // fake doc id e.g. INC-2026-0142
  text: string;
}

export interface KnowledgeSource {
  id: string;
  name: string;
  // 5.12 group verbatim, each Prov-wrapped
  source_uri: Prov<string>;
  parser: Prov<string>;
  source_chunking: Prov<string>;
  embedding_model: Prov<string>;
  index_target: Prov<string>;
  sensitivity: Prov<Sensitivity>;
  source_approval: Prov<SourceApproval>;
  refresh_cadence: Prov<RefreshCadence>;
  source_version: Prov<string>;
  // entity metadata
  document_count: number;
  index_size_mb: number;
  used_by: string[]; // agent_id[]
  snippets: KnowledgeSnippet[]; // 4–6 canned snippets for Playground grounding
  ingestion: string[]; // PipelineRun ids
}

// ---- Pipeline runs (content indexing) -------------------------------------
export const PIPELINE_STAGE_NAMES = [
  'Ingest',
  'Parse',
  'Chunk',
  'Embed',
  'Index',
  'Tag & Govern',
  'Refresh',
] as const;
export type PipelineStageName = (typeof PIPELINE_STAGE_NAMES)[number];

export interface PipelineStage {
  name: PipelineStageName;
  status: TrackStatus;
  started_at: string | null;
  duration_s: number | null;
  items: number | null;
}

export interface PipelineRun {
  id: string;
  source_id: string;
  stages: PipelineStage[];
  trigger: 'manual' | 'scheduled';
  overall: TrackStatus;
  started_at: string;
}

// ---- Model Repository ------------------------------------------------------
// Blueprint §3.7 — the approved catalog that G_Model.model_primary /
// model_fallback (Section 5.3) should be validated against. Today those fields
// are free-text refs set at synthesis time with nothing enforcing that the
// value is actually an approved, catalogued model — this repo is that backstop.
export type ModelRole = 'llm' | 'embedding' | 'eval';
export type ModelDeployStatus = 'approved' | 'candidate' | 'deprecated';

export interface ModelAsset {
  id: string; // matches a G_Model.model_primary / model_fallback value, or the real runtime model id
  name: string;
  provider: string;
  roles: ModelRole[]; // a model can serve more than one role, e.g. LLM + eval judge
  context_window: number;
  cost_input_per_mtok: number; // USD per 1M input tokens
  cost_output_per_mtok: number; // USD per 1M output tokens
  latency_p50_ms: number;
  approved_use_case: string;
  risk_tier_mapping: RiskTier[]; // risk tiers this model is cleared for
  owner: string;
  deployment_status: ModelDeployStatus;
  access_policy: string;
  fallback_of: string | null; // model id this serves as fallback for, if any
  routing_note: string;
}

// ---- A2A Agent Card ---------------------------------------------------------
// Real cards derived server-side from each agent's own persisted config
// (services/a2a.py), re-synced on every bootstrap so this can never go stale.
export interface AgentCard {
  agent_id: string;
  name: string;
  description: string | null;
  skills: string[];
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  endpoint: string;
  endpoint_overridden: boolean;
  discovery_only: boolean;
  message_task_format: string | null;
  capability_tier: CapabilityTier;
  model: string | null;
  updated_at: string;
}
