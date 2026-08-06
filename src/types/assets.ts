// Section 5.4 — Other entities (assets that agents reference).

import type { Prov } from './provenance';
import type { ToolPermission, Sensitivity, SourceApproval, RefreshCadence, TrackStatus } from './agent';

// ---- Prompt Repository ----------------------------------------------------
export type PromptKind = 'system' | 'safety' | 'citation' | 'template';
export type PromptStatus = 'draft' | 'approved' | 'deprecated';

export interface PromptHistoryEntry {
  version: string;
  date: string;
  note: string;
}

export interface PromptAsset {
  id: string;
  version: string;
  name: string;
  kind: PromptKind;
  body: string;
  status: PromptStatus;
  owner: string;
  used_by: string[]; // agent_id[]
  history: PromptHistoryEntry[];
}

// ---- Tool Catalog ---------------------------------------------------------
// `status` is OPERATIONAL health, derived server-side from the connector that
// serves the tool. It is not, and must not become, a governance state.
export type ToolStatus = 'available' | 'degraded' | 'offline';

// ...which is why consent is a separate axis (Phase 3.2, Blueprint §11). A tool
// can be `available` and `pending`: reachable, but not yet allowed.
export type ToolApprovalState = 'pending' | 'approved' | 'rejected';

// Blueprint §3.4. Same four values as the agent RiskTier on purpose — one risk
// vocabulary per platform. `null` = unclassified, a real gap rather than a
// fabricated default.
export type ToolRiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface ToolSchema {
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

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
  approval_state: ToolApprovalState; // only `approved` binds (Phase 3.2)
  owner: string | null;
  risk_level: ToolRiskLevel | null;
  used_by: string[]; // agent_id[]
  // Canned fixtures the Playground uses to render a simulated tool result.
  result_fixtures?: string[];
}

// ---- Connector prioritization backlog (deck slide 21, element 7) ----------
// An *assessment* of a candidate system — distinct from McpConnector, which is
// a server we actually talk to. `existing_connector_id` links the two.
export type BacklogPhase = 'day_90' | 'later';
export type BacklogMcpServer = 'official' | 'community' | 'none' | 'unknown';
// Only the two bindings MCP spec 2026-07-28 defines as standard — deliberately
// NOT McpTransport, which still carries the deprecated `sse` (CONCERNS.md D8).
export type BacklogTransport = 'streamable_http' | 'stdio';
export type BacklogAuthModel = 'oauth2' | 'api_token' | 'iam' | 'unknown';
export type BacklogStatus =
  | 'proposed'
  | 'access_requested'
  | 'approved'
  | 'connected'
  | 'deferred'
  | 'blocked';

export interface ConnectorBacklogItem {
  id: string;
  system_name: string;
  rank: number;
  phase: BacklogPhase;
  mcp_server: BacklogMcpServer;
  mcp_server_note: string | null;
  transport: BacklogTransport | null;
  auth_model: BacklogAuthModel | null;
  data_sensitivity: Sensitivity;
  candidate_tools: string[];
  access_owner: string | null;
  status: BacklogStatus;
  rationale: string;
  blockers: string | null;
  existing_connector_id: string | null;
  updated_at: string;
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
  last_healthcheck: string;
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

// ---- A2A Agent Card -------------------------------------------------------
export interface AgentCard {
  agent_id: string;
  skills: string[];
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  endpoint: string;
  discovery_only: boolean;
  message_task_format: string | null;
  artifact_exchange: boolean;
}
