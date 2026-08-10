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
  // Phase 5A. Set only on tools discovered from an MCP server — the name that
  // server uses for the tool. NULL marks a seeded or console-authored tool, and
  // that distinction is what keeps discovery from orphaning hand-made tools.
  remote_tool_id?: string | null;
  discovered_at?: string | null;
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
// `streamable_http` and `stdio` are the only two bindings MCP spec 2026-07-28
// defines as standard. `sse` and `http` remain in the union because five seeded
// connectors still carry them and existing rows must stay readable — they are
// deprecated input, not a live choice (CONCERNS.md D8). Only `streamable_http`
// endpoints are actually probed over the wire.
export type McpTransport = 'streamable_http' | 'stdio' | 'sse' | 'http';
export type McpAuthMode = 'secret_manager' | 'oauth' | 'none';
export type McpStatus = 'connected' | 'degraded' | 'offline';

// Evidence from a real MCP probe (Phase 5A). Its ABSENCE is the meaningful
// case: a connector with no `last_probe` has never been contacted over the
// wire, and its status came from the simulated roll. The UI must be able to
// tell those apart — a fabricated green tick is worse than no tick.
export interface McpProbe {
  ok: boolean;
  latency_ms: number;
  protocol_version: string | null;
  tool_count: number;
  error: string | null;
  at: string;
}

// Phase 6 — the gateway policy a connector declares (deck slide 21 elements 4
// and 5). Written only through `PATCH /v1/connectors/:id/policy`, read only by
// the gateway. Deliberately disjoint from the four author-owned fields above:
// whoever can move an endpoint must not also be able to widen a data boundary.
//
// **An empty array means "not declared", never "nothing allowed."** The gateway
// records an undeclared boundary as a warning on every call, so the gap is
// visible rather than either silent or fictional.
export interface McpGatewayPolicy {
  allowed_datasets: string[];
  allowed_fields: string[];
  approved_identities: string[]; // persona ids — enforcement real, principal simulated
  service_account: string | null;
  iam_principal: string | null;
  rate_limit_per_min: number;
  timeout_ms: number;
}

export interface McpConnector extends McpGatewayPolicy {
  id: string;
  name: string;
  transport: McpTransport;
  endpoint: string;
  auth_mode: McpAuthMode;
  status: McpStatus;
  tools_provided: string[]; // tool_id[]
  last_healthcheck: string;
  last_probe?: McpProbe | null; // null/undefined = never probed for real
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
