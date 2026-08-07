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
export type ToolStatus = 'available' | 'degraded' | 'offline';

export interface ToolSchema {
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

// Executable HTTP tool definition. {param} placeholders are filled from the tool's
// single-string input at call time. auth_secret_ref is a vault secret NAME only —
// the value is injected engine-side and never stored/transported here.
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

export interface HttpToolConfig {
  method: HttpMethod;
  url_template: string; // e.g. "https://api.example.com/v1/search?q={query}"
  query_params?: Record<string, string>; // values may contain {param} placeholders
  headers?: Record<string, string>; // MUST NOT contain secret values
  body_template?: string | null; // {param} placeholders, for non-GET
  auth_secret_ref?: string | null; // vault secret NAME only — never a value
  auth_header?: string; // default 'Authorization: Bearer {secret}'
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
  used_by: string[]; // agent_id[]
  // Canned fixtures the Playground uses to render a simulated tool result.
  result_fixtures?: string[];
  // 'catalog' (default) = metadata/simulated; 'http_api' = real live HTTP call.
  kind?: 'catalog' | 'http_api';
  http?: HttpToolConfig; // present iff kind === 'http_api'
  // DECLARED implementation (kills name-based capability guessing):
  //   'web_search' = live web search; 'http_api' = the http config above;
  //   'none' = not connected — the agent gets an honest "not connected" stub.
  // Absent (legacy tools) → engine falls back to its name heuristic.
  capability?: 'web_search' | 'http_api' | 'none';
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
