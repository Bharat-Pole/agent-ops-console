// Typed client for the platform backend (Increment A). Requests ride the Vite
// /api proxy (same-origin), so the httpOnly session cookie flows automatically
// — no tokens in JS, no CORS configuration in the browser.
//
// The hand-written shapes below mirror backend/app serializers; they are
// replaced by OpenAPI-generated types once that pipeline lands (Pass 0.5).

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

/** Human-readable message out of a FastAPI error `detail` (string | object). */
export function apiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.detail as { reasons?: string[] } | string | null;
    if (typeof d === 'string') return d;
    if (d && Array.isArray(d.reasons)) return d.reasons.join('; ');
    if (d) return JSON.stringify(d);
    return `request failed (${err.status})`;
  }
  return err instanceof Error ? err.message : String(err);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, (body as { detail?: unknown } | null)?.detail ?? body);
  }
  return body as T;
}

// ---- backend shapes ---------------------------------------------------------

export const SERVER_ROLES = [
  'business_user', 'agent_creator', 'agent_owner', 'ai_engineer',
  'governance_reviewer', 'evaluator', 'platform_admin', 'finops_admin',
  'security_data_owner',
] as const;
export type ServerRole = (typeof SERVER_ROLES)[number];

export interface Me {
  id: string;
  email: string;
  display_name: string;
  roles: ServerRole[];
}

// Blueprint 9-state lifecycle (supersedes the kernel's 7-state demo enum).
export const SERVER_LIFECYCLE = [
  'draft', 'sandbox', 'candidate', 'approved_prototype', 'production_candidate',
  'production', 'needs_review', 'deprecated', 'retired',
] as const;
export type ServerLifecycleStatus = (typeof SERVER_LIFECYCLE)[number];

export type ServerRiskTier = 'low' | 'medium' | 'high' | 'restricted';

export interface ServerAgent {
  id: string;
  slug: string;
  name: string;
  description: string;
  intent_type: string;
  lifecycle_status: ServerLifecycleStatus;
  business_owner: string | null;
  technical_owner: string | null;
  governance_owner: string | null;
  cost_center: string | null;
  draft_risk_tier: ServerRiskTier | null;
  confirmed_risk_tier: ServerRiskTier | null;
  current_intent_id: string | null;
  current_intent_version: number | null;
  created_at: string;
  updated_at: string;
}

export interface AuditRow {
  id: number;
  at: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: Record<string, unknown>;
}

// ---- endpoint groups --------------------------------------------------------

export const authApi = {
  me: () => api<Me>('/api/auth/me'),
  login: (email: string, password: string) =>
    api<Me>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => api<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
};

export const agentsApi = {
  list: (params?: { status?: string; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.q) qs.set('q', params.q);
    const tail = qs.toString();
    return api<ServerAgent[]>(`/api/agents${tail ? `?${tail}` : ''}`);
  },
  create: (name: string, description: string) =>
    api<ServerAgent>('/api/agents', { method: 'POST', body: JSON.stringify({ name, description }) }),
  get: (id: string) => api<ServerAgent>(`/api/agents/${id}`),
  transition: (id: string, to: ServerLifecycleStatus, note?: string) =>
    api<ServerAgent>(`/api/agents/${id}/transition`, {
      method: 'POST',
      body: JSON.stringify({ to, note: note || null }),
    }),
};

export const auditApi = {
  forResource: (resourceType: string, resourceId: string, limit = 100) =>
    api<AuditRow[]>(
      `/api/audit?resource_type=${encodeURIComponent(resourceType)}&resource_id=${encodeURIComponent(resourceId)}&limit=${limit}`,
    ),
};

// ---- intent (6 field groups; server validates + PII-flags on submit) --------
// The wizard writes raw leaf values; the backend also accepts Prov envelopes
// ({value, source}) — engine-stamped provenance arrives with materialization.

export interface IntentPayload {
  identity_purpose?: {
    objective?: string;
    business_function?: string;
    target_users?: string;
    success_criteria?: string;
  };
  trigger_contract?: {
    trigger_type?: string;
    input_description?: string;
    output_description?: string;
    output_format?: string;
  };
  data_rules?: {
    data_sources?: string[];
    data_sensitivity?: string;
    business_rules?: string;
    knowledge_freshness?: string;
  };
  tools_interaction?: {
    tools_required?: { name: string; purpose: string; system?: string }[];
    mcp_connectors_required?: boolean;
    interaction_style?: string;
    external_systems?: string[];
  };
  risk_governance?: {
    risk_tier?: string;
    human_approval_requirement?: string;
    write_actions_expected?: boolean;
    compliance_notes?: string;
    deployment_channel?: string;
  };
  volume_evidence?: {
    expected_volume_per_day?: number | null;
    latency_target?: string;
    evidence_requirement?: string;
  };
}

export interface PiiFlag {
  path: string;
  kind: string;
  preview: string;
  count: number;
  detector: string;
}

export interface SubmittedIntent {
  intent_id: string;
  version: number;
  status: string;
  payload: IntentPayload;
  pii_flags: PiiFlag[];
  validation: { warnings?: string[]; rules_version?: string };
  submitted_at: string;
}

export const intentApi = {
  getDraft: (agentId: string) =>
    api<{ draft_id: string; payload: IntentPayload; updated_at: string }>(`/api/agents/${agentId}/intent/draft`),
  saveDraft: (agentId: string, payload: IntentPayload) =>
    api<{ draft_id: string; updated_at: string }>(`/api/agents/${agentId}/intent/draft`, {
      method: 'PUT',
      body: JSON.stringify({ payload }),
    }),
  submit: (agentId: string) =>
    api<{ intent_id: string; version: number; status: string; warnings: string[]; pii_flags: PiiFlag[] }>(
      `/api/agents/${agentId}/intent/submit`,
      { method: 'POST' },
    ),
  getCurrent: (agentId: string) => api<SubmittedIntent>(`/api/agents/${agentId}/intent`),
};

// ---- design recommendation --------------------------------------------------

export type ItemVerification = 'grounded' | 'unverified' | 'deterministic';
export type ItemState = 'pending' | 'accepted' | 'rejected';

export interface FlowNode {
  id: string;
  type: string;
  label: string;
  config?: Record<string, unknown>;
}
/** A condition the engine can actually evaluate — see engine/conditions.py. */
export interface EdgeCondition {
  field: string;
  op: string;
  value?: unknown;
}

export interface FlowEdge {
  from: string;
  to: string;
  /** Recommender annotation of intent ("route:refunds"). Documents a branch;
   *  does NOT execute one. */
  when?: string;
  /** The executable predicate. Its presence is what makes an edge conditional. */
  condition?: EdgeCondition;
}

export interface RecommendationItem {
  id: string;
  kind: string;
  title: string;
  detail: Record<string, unknown> & { flow?: { nodes: FlowNode[]; edges: FlowEdge[] } };
  basis: string;
  verification: ItemVerification;
  overlap?: number;
  note?: string;
  state: 'proposed' | 'described_need';
}

export interface Recommendation {
  id: string;
  intent_id: string;
  status: string;
  engine: string; // 'deterministic' | 'llm+deterministic'
  items: RecommendationItem[];
  item_states: Record<string, ItemState>;
  validation: {
    contradictions?: { field: string; llm: string; deterministic: string; note: string }[];
    closed_world_demotions?: { item: string; kind: string; ref: string; note: string }[];
    flow?: { source: string; violations: string[]; adjustments: string[]; note?: string };
    llm_error?: string;
    basis_threshold?: number;
  };
  summary: string | null;
  missing_information: string[];
  clarifying_questions: string[];
  model_id: string | null;
  prompt_version: string | null;
  created_at: string;
}

export interface Materialization {
  materialized: boolean;
  asset_type: string | null;
  asset_id?: string;
  note?: string;
  guidance?: string;
}

export const recommendationApi = {
  get: (agentId: string) => api<Recommendation>(`/api/agents/${agentId}/recommendation`),
  generate: (agentId: string) =>
    api<Recommendation>(`/api/agents/${agentId}/recommendation`, { method: 'POST' }),
  setItemState: (agentId: string, itemId: string, state: ItemState) =>
    api<{ item_id: string; state: ItemState; item_states: Record<string, ItemState>; materialization: Materialization | null }>(
      `/api/agents/${agentId}/recommendation/items/${itemId}`,
      { method: 'POST', body: JSON.stringify({ state }) },
    ),
};

// ---- Asset Studio (Increment C) ---------------------------------------------

export type AssetStatus = 'draft' | 'pending_approval' | 'approved' | 'rejected' | 'deprecated';

export interface ServerTool {
  id: string;
  slug: string;
  version: number;
  name: string;
  description: string;
  business_purpose: string;
  permission_type: string;
  is_write_class: boolean;
  risk_level: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  implementation: { kind: string; config: Record<string, unknown> };
  auth: { method: string; credential_ref: string | null };
  timeout_seconds: number;
  human_approval_required: boolean;
  status: AssetStatus;
  source: string;
  /** Set when the tool was created by MCP discovery — already returned by the API. */
  mcp_connector_id: string | null;
  created_at: string;
  updated_at: string;
}

export const toolsApi = {
  list: () => api<ServerTool[]>('/api/tools'),
  create: (body: Partial<ServerTool> & { name: string }) =>
    api<ServerTool>('/api/tools', { method: 'POST', body: JSON.stringify(body) }),
  submit: (id: string) => api<ServerTool>(`/api/tools/${id}/submit`, { method: 'POST' }),
  newVersion: (id: string) => api<ServerTool>(`/api/tools/${id}/new-version`, { method: 'POST' }),
  tryout: (id: string, params: Record<string, string>) =>
    api<{ status_code: number; content_type: string | null; body_preview: string; truncated: boolean }>(
      `/api/tools/${id}/tryout`,
      { method: 'POST', body: JSON.stringify({ params }) },
    ),
};

export interface ServerConnector {
  id: string;
  name: string;
  endpoint: string;
  transport: string;
  auth: { header_name: string | null; credential_ref: string | null };
  status: string;
  health: { ok: boolean | null; last_checked: string | null; consecutive_failures: number; note?: string };
  created_at: string;
  updated_at: string;
}

export const mcpApi = {
  list: () => api<ServerConnector[]>('/api/mcp'),
  create: (body: { name: string; endpoint: string; transport?: string; auth?: Record<string, unknown> }) =>
    api<ServerConnector>('/api/mcp', { method: 'POST', body: JSON.stringify(body) }),
  discover: (id: string) =>
    api<{ connector: ServerConnector; created_drafts: ServerTool[]; new_version_drafts: ServerTool[]; unchanged: string[]; vanished: string[] }>(
      `/api/mcp/${id}/discover`,
      { method: 'POST' },
    ),
  health: (id: string) => api<ServerConnector>(`/api/mcp/${id}/health`, { method: 'POST' }),
};

export interface ServerPromptVersion {
  id: string;
  pack_id: string;
  version: number;
  content: string;
  variables: string[];
  status: AssetStatus;
  notes: string;
  rolled_back_from: number | null;
  created_at: string;
}

export interface ServerPromptPack {
  id: string;
  slug: string;
  name: string;
  prompt_type: string;
  description: string;
  tags: string[];
  created_at: string;
  versions?: ServerPromptVersion[];
  latest_version?: number;
  latest_status?: AssetStatus | null;
  approved_version?: number | null;
}

export interface PromptComparison {
  pack: ServerPromptPack;
  a: ServerPromptVersion;
  b: ServerPromptVersion;
  changed_fields: string[];
  identical: boolean;
}

export interface PromptUsageRef {
  agent_id: string;
  agent_name: string | null;
  agent_slug: string | null;
  lifecycle_status: string | null;
  reference_type: 'binding' | 'workflow_node' | 'deployment_pin';
  version_policy?: string;
  pinned_version?: number | null;
  workflow_id?: string;
  workflow_name?: string | null;
  workflow_version?: number;
  workflow_status?: string;
  deployment_id?: string;
  channel?: string;
  deployment_status?: string;
}

export interface PromptUsage {
  pack_id: string;
  slug: string;
  active: { bindings: PromptUsageRef[]; workflow_versions: PromptUsageRef[]; deployments: PromptUsageRef[] };
  historical: { workflow_versions: PromptUsageRef[]; deployments: PromptUsageRef[] };
  totals: { active: number; historical: number };
}

export const promptsApi = {
  list: () => api<ServerPromptPack[]>('/api/prompts'),
  compare: (packId: string, a: number, b: number) =>
    api<PromptComparison>(`/api/prompts/${packId}/versions/${a}/compare/${b}`),
  usage: (packId: string) => api<PromptUsage>(`/api/prompts/${packId}/usage`),
  create: (body: { name: string; prompt_type: string; description?: string; content: string }) =>
    api<ServerPromptPack>('/api/prompts', { method: 'POST', body: JSON.stringify(body) }),
  get: (id: string) => api<ServerPromptPack>(`/api/prompts/${id}`),
  newVersion: (id: string, content: string, notes = '') =>
    api<ServerPromptVersion>(`/api/prompts/${id}/versions`, { method: 'POST', body: JSON.stringify({ content, notes }) }),
  rollback: (id: string, version: number) =>
    api<ServerPromptVersion>(`/api/prompts/${id}/versions/${version}/rollback`, { method: 'POST' }),
  submit: (id: string, version: number) =>
    api<ServerPromptVersion>(`/api/prompts/${id}/versions/${version}/submit`, { method: 'POST' }),
};

export interface ServerKnowledgeSource {
  id: string;
  name: string;
  filename: string;
  mime: string;
  sensitivity: string;
  status: string;
  bytes: number;
  chunk_count: number;
  embedded: boolean;
  retrieval_mode: string;
  error: string | null;
  created_at: string;
  chunk_preview?: { ord: number; text: string; meta: Record<string, unknown>; has_embedding: boolean }[];
}

export interface KbChunkRow {
  id: string;
  ord: number;
  text: string;
  location: string | null;
  meta: Record<string, unknown>;
  has_embedding: boolean;
}

export interface KbChunkPage {
  source_id: string;
  source_name: string;
  total: number;
  offset: number;
  limit: number;
  items: KbChunkRow[];
}

export const knowledgeApi = {
  list: () => api<ServerKnowledgeSource[]>('/api/knowledge'),
  get: (id: string) => api<ServerKnowledgeSource>(`/api/knowledge/${id}`),
  chunks: (id: string, offset = 0, limit = 25) =>
    api<KbChunkPage>(`/api/knowledge/${id}/chunks?offset=${offset}&limit=${limit}`),
  upload: async (file: File, name: string, sensitivity: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('name', name);
    form.append('sensitivity', sensitivity);
    const res = await fetch('/api/knowledge/upload', { method: 'POST', body: form, credentials: 'same-origin' });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, (body as { detail?: unknown } | null)?.detail ?? body);
    return body as ServerKnowledgeSource;
  },
};

export interface ServerRagPipeline {
  id: string;
  name: string;
  source_ids: string[];
  top_k: number;
  score_threshold: number;
  hybrid_alpha: number;
  status: string;
  created_at: string;
}

export interface RetrievalPreview {
  mode: string;
  mode_notes: string[];
  alpha: number;
  results: { chunk_id: string; source: string; location: string | null; text: string; score: number; vector_score: number; keyword_score: number }[];
}

export const ragApi = {
  list: () => api<ServerRagPipeline[]>('/api/rag'),
  create: (body: { name: string; source_ids: string[]; top_k?: number; score_threshold?: number }) =>
    api<ServerRagPipeline>('/api/rag', { method: 'POST', body: JSON.stringify(body) }),
  preview: (id: string, query: string) =>
    api<RetrievalPreview>(`/api/rag/${id}/preview`, { method: 'POST', body: JSON.stringify({ query }) }),
};

export interface ServerModel {
  id: string;
  provider: string;
  model_ref: string;
  kind: string;
  display_name: string;
  cost_per_1k_in: number;
  cost_per_1k_out: number;
  max_risk_tier: string;
  status: string;
  /** Vault secret NAME this model authenticates with — never the value. */
  credential_ref?: string | null;
}

export type ModelBody = Omit<ServerModel, 'id' | 'credential_ref'> & { credential_ref: string | null };

export const modelsApi = {
  list: () => api<ServerModel[]>('/api/models'),
  create: (body: ModelBody) =>
    api<ServerModel>('/api/models', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: ModelBody) =>
    api<ServerModel>(`/api/models/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
};

export interface SecretMeta {
  name: string;
  created_at: string;
  updated_at: string;
}

export const secretsApi = {
  list: () => api<SecretMeta[]>('/api/secrets'),
  put: (name: string, value: string) =>
    api<SecretMeta>('/api/secrets', { method: 'PUT', body: JSON.stringify({ name, value }) }),
  remove: (name: string) => api<{ ok: boolean }>(`/api/secrets/${name}`, { method: 'DELETE' }),
};

export interface ApprovalStep {
  id: string;
  resource_type: string;
  resource_id: string;
  step: string;
  required_role: string;
  status: string;
  note: string | null;
  requested_at: string;
  decided_at: string | null;
  asset_status?: string | null;
}

export const approvalsApi = {
  queue: (status = 'pending') => api<ApprovalStep[]>(`/api/approvals?status=${status}`),
  decide: (id: string, approve: boolean, note?: string) =>
    api<ApprovalStep>(`/api/approvals/${id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ approve, note: note || null }),
    }),
};

export interface AssetBindingRow {
  id: string;
  agent_id: string;
  asset_type: string;
  asset_ref: string;
  version_policy: string;
  pinned_version: number | null;
  created_at: string;
}

// ---- workflows + runs (Increment D) -----------------------------------------

export type WorkflowVersionStatus =
  | 'draft' | 'validated' | 'pending_approval' | 'approved' | 'active' | 'rejected' | 'superseded';

export interface WorkflowGraph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface ServerWorkflowVersion {
  id: string;
  workflow_id: string;
  version: number;
  graph: WorkflowGraph;
  status: WorkflowVersionStatus;
  validation: { violations?: string[]; warnings?: string[]; adjustments?: string[]; rules_version?: string };
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface ServerWorkflow {
  id: string;
  agent_id: string;
  name: string;
  created_at: string;
  versions: ServerWorkflowVersion[];
  active_version: number | null;
  seeded_from?: { recommendation_id: string; flow_item_state: string } | null;
}

export const workflowsApi = {
  listForAgent: (agentId: string) => api<ServerWorkflow[]>(`/api/agents/${agentId}/workflows`),
  create: (agentId: string, body: { name: string; from_recommendation?: boolean; graph?: WorkflowGraph }) =>
    api<ServerWorkflow>(`/api/agents/${agentId}/workflows`, { method: 'POST', body: JSON.stringify(body) }),
  get: (workflowId: string) => api<ServerWorkflow>(`/api/workflows/${workflowId}`),
  updateDraft: (workflowId: string, version: number, graph: WorkflowGraph, notes = '') =>
    api<ServerWorkflowVersion>(`/api/workflows/${workflowId}/versions/${version}`, {
      method: 'PUT', body: JSON.stringify({ graph, notes }),
    }),
  validate: (workflowId: string, version: number) =>
    api<ServerWorkflowVersion>(`/api/workflows/${workflowId}/versions/${version}/validate`, { method: 'POST' }),
  submit: (workflowId: string, version: number) =>
    api<ServerWorkflowVersion>(`/api/workflows/${workflowId}/versions/${version}/submit`, { method: 'POST' }),
  activate: (workflowId: string, version: number) =>
    api<ServerWorkflowVersion>(`/api/workflows/${workflowId}/versions/${version}/activate`, { method: 'POST' }),
  fork: (workflowId: string, version: number) =>
    api<ServerWorkflowVersion>(`/api/workflows/${workflowId}/versions/${version}/fork`, { method: 'POST' }),
};

export interface RunStepRow {
  ord: number;
  node_id: string;
  node_type: string;
  status: string;
  duration_ms: number;
  tokens_in: number;
  tokens_out: number;
  cost: number;
  detail: Record<string, unknown>;
  at: string;
}

export interface RunHitlRow {
  id: string;
  node_id: string;
  status: string;
  payload: { user_input?: string; llm_output_preview?: string };
  requested_at: string;
  note: string | null;
}

export interface ServerRun {
  id: string;
  agent_id: string;
  workflow_version_id: string;
  mode: string;
  status: 'running' | 'paused_hitl' | 'completed' | 'failed' | 'cancelled';
  input: { text?: string };
  output: { final_output?: string | Record<string, unknown>; citation_check?: Record<string, unknown> };
  error: string | null;
  started_at: string;
  finished_at: string | null;
  steps?: RunStepRow[];
  totals?: { tokens_in: number; tokens_out: number; cost: number; duration_ms: number };
  hitl?: RunHitlRow[];
}

export const runsApi = {
  start: (agentId: string, input: string, workflowVersionId?: string) =>
    api<ServerRun>(`/api/agents/${agentId}/runs`, {
      method: 'POST',
      body: JSON.stringify({ input, workflow_version_id: workflowVersionId ?? null }),
    }),
  listForAgent: (agentId: string) => api<ServerRun[]>(`/api/agents/${agentId}/runs`),
  get: (runId: string) => api<ServerRun>(`/api/runs/${runId}`),
  decideHitl: (runId: string, hitlId: string, approve: boolean, note?: string) =>
    api<ServerRun>(`/api/runs/${runId}/hitl/${hitlId}`, {
      method: 'POST', body: JSON.stringify({ approve, note: note || null }),
    }),
};

// ---- evaluation + governance (Increment E) ----------------------------------

export interface EvalCheck {
  check: string;
  ok: boolean | null;
  note: string;
}

export interface EvalCaseRow {
  id: string;
  name: string;
  category: string;
  input: string;
  expectations: Record<string, unknown>;
  weight: number;
  source: string;
  review_status: string;
}

export interface EvalPackRow {
  id: string;
  agent_id: string;
  name: string;
  threshold: number;
  status: string;
  created_at: string;
  cases: EvalCaseRow[];
}

export interface Scorecard {
  score: number;
  threshold: number;
  overall_passed: boolean;
  categories: Record<string, { passed: number; failed: number; not_evaluated: number }>;
  cases_total: number;
  cases_run: number;
  cases_excluded_pending_review: number;
  cases_not_evaluated: number;
  computed_at: string;
}

export interface EvalRunRow {
  id: string;
  agent_id?: string;
  pack_id: string;
  workflow_version_id?: string;
  status: string;
  scorecard: Scorecard;
  started_at: string;
  finished_at?: string | null;
  results?: { case_id: string; case_name: string; category: string; run_id: string | null; passed: boolean | null; checks: EvalCheck[] }[];
}

export const evalApi = {
  packs: (agentId: string) => api<EvalPackRow[]>(`/api/agents/${agentId}/eval-packs`),
  createPack: (agentId: string, name: string, threshold: number) =>
    api<EvalPackRow>(`/api/agents/${agentId}/eval-packs`, {
      method: 'POST', body: JSON.stringify({ name, threshold }),
    }),
  addCase: (packId: string, body: { name: string; category: string; input: string; expectations: Record<string, unknown>; weight?: number }) =>
    api<EvalPackRow>(`/api/eval-packs/${packId}/cases`, { method: 'POST', body: JSON.stringify(body) }),
  runPack: (packId: string, workflowVersionId?: string) =>
    api<EvalRunRow>(`/api/eval-packs/${packId}/run`, {
      method: 'POST', body: JSON.stringify({ workflow_version_id: workflowVersionId ?? null }),
    }),
  runs: (agentId: string) => api<EvalRunRow[]>(`/api/agents/${agentId}/eval-runs`),
  run: (runId: string) => api<EvalRunRow>(`/api/eval-runs/${runId}`),
};

export interface GovernanceExceptionRow {
  id: string;
  agent_id: string;
  reason: string;
  expires_at: string;
  status: string;
  created_at?: string;
}

export const governanceApi = {
  exceptions: () => api<GovernanceExceptionRow[]>('/api/governance/exceptions'),
  createException: (agentId: string, reason: string, expiresDays: number) =>
    api<GovernanceExceptionRow>('/api/governance/exceptions', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, reason, expires_days: expiresDays }),
    }),
  revokeException: (id: string) =>
    api<{ id: string; status: string }>(`/api/governance/exceptions/${id}/revoke`, { method: 'POST' }),
  config: () => api<{ version: number; config: Record<string, unknown> }>('/api/governance/config'),
  evidence: (agentId: string) =>
    api<{ id: string; content: Record<string, unknown>; created_at: string }[]>(`/api/governance/evidence/${agentId}`),
};

// ---- deployment + telemetry (Increment F) -----------------------------------

export interface ServerDeployment {
  id: string;
  agent_id: string;
  slug: string;
  channel: string;
  workflow_version: number | null;
  asset_pins: Record<string, unknown> | null;
  admission: { allowed?: boolean; reasons?: string[]; note?: string };
  status: string;
  access_group_id: string | null;
  rate_limit_per_min: number;
  invoke_path: string | null;
  created_at: string;
}

export interface AccessGroupRow {
  id: string;
  name: string;
  description: string;
  keys: { id: string; name: string; prefix: string; revoked: boolean; created_at: string }[];
}

export interface AdmissionPreview {
  channel: string;
  allowed: boolean;
  reasons: string[];
  workflow_version_id: string | null;
  evaluation: { run_id: string; passed: boolean; score: number | null; started_at: string } | null;
}

export const deploymentsApi = {
  list: (agentId: string) => api<ServerDeployment[]>(`/api/agents/${agentId}/deployments`),
  admission: (agentId: string, channel: string) =>
    api<AdmissionPreview>(`/api/agents/${agentId}/deployments/admission?channel=${channel}`),
  deploy: (agentId: string, body: { channel: string; access_group_id?: string | null; rate_limit_per_min?: number }) =>
    api<ServerDeployment>(`/api/agents/${agentId}/deployments`, { method: 'POST', body: JSON.stringify(body) }),
  rollback: (deploymentId: string) =>
    api<ServerDeployment>(`/api/deployments/${deploymentId}/rollback`, { method: 'POST' }),
  groups: () => api<AccessGroupRow[]>('/api/access-groups'),
  createGroup: (name: string) =>
    api<{ id: string; name: string }>('/api/access-groups', { method: 'POST', body: JSON.stringify({ name }) }),
  createKey: (groupId: string, name: string) =>
    api<{ id: string; name: string; prefix: string; api_key: string; note: string }>(
      `/api/access-groups/${groupId}/keys`, { method: 'POST', body: JSON.stringify({ name }) }),
  revokeKey: (keyId: string) => api<{ id: string; revoked: boolean }>(`/api/api-keys/${keyId}/revoke`, { method: 'POST' }),
};

export interface TelemetrySummary {
  runs: number;
  note?: string;
  by_status?: Record<string, number>;
  by_mode?: Record<string, number>;
  error_rate?: number | null;
  latency_ms?: { p50: number; p95: number };
  tokens?: { in: number; out: number };
  cost_usd?: number;
  feedback?: { count: number; positive: number; negative: number };
}

export interface AgentCostRow {
  agent_id: string;
  agent: string;
  cost_center: string | null;
  runs: number;
  cost_usd: number;
  mtd_cost_usd: number;
  budget: { monthly_usd: number; alert: boolean; utilization: number | null } | null;
}

export const telemetryApi = {
  summary: (agentId?: string) =>
    api<TelemetrySummary>(`/api/telemetry/summary${agentId ? `?agent_id=${agentId}` : ''}`),
  costs: () => api<AgentCostRow[]>('/api/telemetry/costs'),
  setBudget: (agentId: string, monthlyUsd: number) =>
    api<{ agent_id: string; monthly_usd: number }>(`/api/agents/${agentId}/budget`, {
      method: 'PUT', body: JSON.stringify({ monthly_usd: monthlyUsd }),
    }),
  feedback: (runId: string, rating: 1 | -1, note = '') =>
    api<{ id: string }>(`/api/runs/${runId}/feedback`, {
      method: 'POST', body: JSON.stringify({ rating, note }),
    }),
};

// ---- A2A agent cards --------------------------------------------------------

export interface CardReadiness {
  card_approved: boolean;
  agent_in_production: boolean;
  has_active_workflow: boolean;
  has_active_deployment: boolean;
  discoverable: boolean;
  reasons: string[];
}

export interface ServerAgentCard {
  id: string;
  agent_id: string;
  agent_slug: string | null;
  agent_name: string | null;
  version: number;
  status: AssetStatus;
  description: string;
  capability_tier: string;
  discovery_only: boolean;
  message_task_format: string | null;
  artifact_exchange: boolean;
  artifact_format: string | null;
  supported_tasks: string[];
  skills: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  handoff_rules: Record<string, unknown>;
  authn_methods: string[];
  authorized_callers: string[];
  timeout_seconds: number;
  failure_behavior: string;
  superseded_by: string | null;
  readiness?: CardReadiness;
  created_at: string;
  updated_at: string;
}

export interface HandoffDecision {
  allowed: boolean;
  reasons: string[];
  checks: Record<string, boolean>;
  target: Record<string, unknown> | null;
  rules_version: string;
}

export type AgentCardBody = Partial<Omit<ServerAgentCard, 'id' | 'agent_id' | 'version' | 'status'>>;

export const a2aApi = {
  list: () => api<ServerAgentCard[]>('/api/a2a/agent-cards'),
  discover: (params?: { skill?: string; task?: string }) => {
    const qs = new URLSearchParams();
    if (params?.skill) qs.set('skill', params.skill);
    if (params?.task) qs.set('task', params.task);
    const tail = qs.toString();
    return api<ServerAgentCard[]>(`/api/a2a/discover${tail ? `?${tail}` : ''}`);
  },
  getForAgent: (agentId: string) => api<ServerAgentCard>(`/api/a2a/agents/${agentId}/card`),
  create: (agentId: string, body: AgentCardBody) =>
    api<ServerAgentCard>(`/api/a2a/agents/${agentId}/card`, { method: 'POST', body: JSON.stringify(body) }),
  update: (cardId: string, body: AgentCardBody) =>
    api<ServerAgentCard>(`/api/a2a/cards/${cardId}`, { method: 'PUT', body: JSON.stringify(body) }),
  newVersion: (cardId: string) =>
    api<ServerAgentCard>(`/api/a2a/cards/${cardId}/new-version`, { method: 'POST' }),
  submit: (cardId: string) =>
    api<ServerAgentCard>(`/api/a2a/cards/${cardId}/submit`, { method: 'POST' }),
  validateHandoff: (body: {
    source_agent_slug: string; target_agent_slug: string; task: string; required_skill?: string | null;
  }) => api<HandoffDecision>('/api/a2a/handoffs/validate', { method: 'POST', body: JSON.stringify(body) }),
};

export const bindingsApi = {
  list: (agentId: string) => api<AssetBindingRow[]>(`/api/agents/${agentId}/bindings`),
  bind: (agentId: string, body: { asset_type: string; asset_ref: string; version_policy?: string }) =>
    api<AssetBindingRow>(`/api/agents/${agentId}/bindings`, { method: 'POST', body: JSON.stringify(body) }),
  unbind: (agentId: string, bindingId: string) =>
    api<{ ok: boolean }>(`/api/agents/${agentId}/bindings/${bindingId}`, { method: 'DELETE' }),
};
