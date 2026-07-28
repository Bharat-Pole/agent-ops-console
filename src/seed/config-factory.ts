// Tier-template config factory (Section 7.3). Produces a full 13-group AgentConfig
// with every leaf present and a realistic provenance mix (U/S/D/I/G/H). Used by
// seed data (M2) and the synthesis engine (M4).

import type {
  AgentConfig,
  CapabilityTier,
  RiskTier,
  LifecycleStatus,
  RetrievalType,
  ToolPermission,
  OrchestrationType,
  SubAgent,
  HitlGate,
  Sensitivity,
  Prov,
} from '@/types';
import { prov } from '@/types';

// Provenance shortcuts.
const u = <T,>(v: T): Prov<T> => prov(v, 'user', { verified_flag: true, confidence: 'high' });
const s = <T,>(v: T): Prov<T> => prov(v, 'system', { confidence: 'high' });
const d = <T,>(v: T): Prov<T> => prov(v, 'default', { confidence: 'high' });
const h = <T,>(v: T): Prov<T> => prov(v, 'inherited', { confidence: 'high', verified_flag: true });
const i = <T,>(v: T, gap?: string): Prov<T> =>
  prov(v, 'inferred', { confidence: 'medium', gap_note: gap ?? 'Engine-inferred — confirm in review card.' });
// engine-generated → shows as "G" chip (inferred + low confidence)
const g = <T,>(v: T, gap?: string): Prov<T> =>
  prov(v, 'inferred', { confidence: 'low', gap_note: gap ?? 'Auto-generated. Confirm with owner.' });
// governance-critical field: never `high` until user-confirmed (Section 7.5)
const gc = <T,>(v: T, confirmed: boolean, gap: string): Prov<T> =>
  prov(v, 'inferred', {
    confidence: confirmed ? 'high' : 'medium',
    verified_flag: confirmed,
    gap_note: confirmed ? null : gap,
  });

export interface ConfigInput {
  tier: CapabilityTier;
  agent_name: string;
  agent_id: string;
  business_owner: string;
  technical_owner: string;
  executive_sponsor?: string | null;
  use_case_category: string;
  consumer_type: string;
  intended_audience: string;
  description: string;
  objective: string;

  lifecycle_status: LifecycleStatus;
  risk_tier: RiskTier;
  risk_confirmed?: boolean;
  last_review_date?: string | null;
  next_review_date?: string | null;

  data_sources?: string[];
  knowledge_source_refs?: string[]; // kb://...
  sensitivity?: Sensitivity;
  primary_source_uri?: string | null;
  index_target?: string | null;

  bound_tools?: string[]; // tools://...
  mcp_connectors?: string[];

  sub_agents?: SubAgent[];
  hitl_gates?: HitlGate[];
  per_sub_agent_prompts?: Record<string, string> | null;

  system_prompt_ref?: string;
  persona_role?: string;
  citation_rules?: string | null;
  safety_instructions?: string;
  policy_controls?: string[];
  response_format_contract?: string | null;

  approvals_required?: string[];
  cost_label: string;
  cost_awareness?: string;

  a2a_enabled?: boolean;
  agent_card_ref?: string | null;
  message_task_format?: string | null;
  artifact_exchange?: boolean;

  evidence_store_uri?: string | null;
  artifact_links?: string[];

  // overrides for the deliberately-broken agent (Section 11.3)
  score_threshold?: number;
}

export function buildConfig(inp: ConfigInput): AgentConfig {
  const tier = inp.tier;
  const isMin = tier === 'minimal';
  const isAdv = tier === 'advanced';
  const rag = !isMin;

  const modelPrimary = isMin
    ? 'vertex://gemini-1.5-flash'
    : isAdv
      ? 'vertex://gemini-1.5-pro'
      : 'vertex://gemini-1.5-flash';
  const modelFallback = isMin ? null : 'vertex://gemini-1.5-pro';
  const runtimeHost = isAdv ? 'GKE' : 'Cloud Run';
  const orchestration: OrchestrationType = isAdv ? 'coordinator+subagents' : 'single';
  const retrieval: RetrievalType | null = rag ? 'hybrid' : null;

  const toolPerm: ToolPermission = 'read'; // advisory base scope, LOCKED

  return {
    // 5.1 Identity & Ownership
    identity: {
      agent_name: u(inp.agent_name),
      agent_id: s(inp.agent_id),
      business_owner: u(inp.business_owner),
      technical_owner: u(inp.technical_owner),
      executive_sponsor: inp.executive_sponsor ? u(inp.executive_sponsor) : d<string | null>(null),
      use_case_category: i(inp.use_case_category),
      consumer_type: u(inp.consumer_type),
      intended_audience: u(inp.intended_audience),
      description: u(inp.description),
      objective: u(inp.objective),
    },
    // 5.2 Lifecycle & Risk
    lifecycle: {
      lifecycle_status: s(inp.lifecycle_status),
      risk_tier: gc(
        inp.risk_tier,
        inp.risk_confirmed ?? false,
        'Inferred from objective — confirm data sensitivity in the review card.',
      ),
      last_review_date: inp.last_review_date ? s<string | null>(inp.last_review_date) : d<string | null>(null),
      next_review_date: inp.next_review_date ? s<string | null>(inp.next_review_date) : d<string | null>(null),
      exception_status: d<string | null>(null),
    },
    // 5.3 Model
    model: {
      model_primary: s(modelPrimary),
      model_fallback: modelFallback ? s<string | null>(modelFallback) : d<string | null>(null),
      temperature: d(isAdv ? 0.3 : 0.2),
      max_output_tokens: d(isAdv ? 4096 : 2048),
      context_window_ref: s(isMin ? '32k' : '128k'),
      cost_awareness: i(inp.cost_awareness ?? (isAdv ? 'high — multi-agent fan-out' : 'moderate')),
    },
    // 5.4 Prompt & Instruction
    prompt: {
      system_prompt_ref: h(inp.system_prompt_ref ?? `prompts://${tier}-base-v1`),
      user_prompt_template: d<string | null>(null),
      task_prompt: i<string | null>(
        `Perform: ${inp.objective}`,
        'Derived from objective — refine before production.',
      ),
      persona_role: i(inp.persona_role ?? `${inp.use_case_category} assistant`),
      tool_use_instructions: rag ? h<string | null>('policies://tool-use-advisory-v1') : d<string | null>(null),
      safety_instructions: h(inp.safety_instructions ?? 'policies://safety-standard-v1'),
      citation_rules: rag ? h<string | null>(inp.citation_rules ?? 'policies://citation-standard-v1') : d<string | null>(null),
      response_format_contract: inp.response_format_contract
        ? i<string | null>(inp.response_format_contract)
        : d<string | null>(null),
      stop_conditions: d<string | null>(null),
      per_sub_agent_prompts: isAdv && inp.per_sub_agent_prompts ? g<Record<string, string> | null>(inp.per_sub_agent_prompts) : d<Record<string, string> | null>(null),
    },
    // 5.5 Data & Knowledge
    data: {
      data_sources: (inp.data_sources?.length ? u(inp.data_sources) : d<string[]>([])),
      rag_enabled: s(rag),
      retrieval_type: rag ? i<RetrievalType | null>(retrieval) : d<RetrievalType | null>(null),
      chunk_size: rag ? g<number | null>(512) : d<number | null>(null),
      chunk_overlap: rag ? g<number | null>(128) : d<number | null>(null),
      top_k: rag ? g<number | null>(5) : d<number | null>(null),
      score_threshold: rag ? g<number | null>(inp.score_threshold ?? 0.75) : d<number | null>(null),
      knowledge_source_refs: inp.knowledge_source_refs?.length ? u(inp.knowledge_source_refs) : d<string[]>([]),
      structured_grounding: s(isAdv),
    },
    // 5.6 Tooling & MCP
    tooling: {
      bound_tools: inp.bound_tools?.length ? u(inp.bound_tools) : d<string[]>([]),
      tool_permission: gc(toolPerm, true, ''), // advisory-only, confirmed by policy
      mcp_connectors: inp.mcp_connectors?.length ? u(inp.mcp_connectors) : d<string[]>([]),
      tool_auth: inp.mcp_connectors?.length ? s<string | null>('secret_manager') : d<string | null>(null),
      rate_limits: rag ? d<string | null>('60/min') : d<string | null>(null),
    },
    // 5.7 Orchestration
    orchestration: {
      orchestration_type: i(orchestration),
      sub_agents: isAdv && inp.sub_agents?.length ? g<SubAgent[]>(inp.sub_agents, 'Auto-decomposed from objective. Confirm ownership.') : d<SubAgent[]>([]),
      retries: d(isAdv ? 2 : 1),
      fallback_behavior: d(isMin ? 'return_error' : 'graceful_degrade'),
      hitl_gate_placement: inp.hitl_gates?.length ? i<HitlGate[]>(inp.hitl_gates) : d<HitlGate[]>([]),
      a2a_enabled: s(inp.a2a_enabled ?? !isMin),
      agent_card: inp.agent_card_ref ? s<string | null>(inp.agent_card_ref) : d<string | null>(null),
      message_task_format: isAdv ? i<string | null>(inp.message_task_format ?? 'a2a/task-v1') : d<string | null>(null),
      artifact_exchange: s(isAdv ? (inp.artifact_exchange ?? true) : false),
    },
    // 5.8 Governance & Approval
    governance: {
      approvals_required: inp.approvals_required?.length ? i<string[]>(inp.approvals_required) : d<string[]>([]),
      audit_level: d(isAdv ? 'verbose' : 'standard'),
      policy_controls: inp.policy_controls?.length ? h<string[]>(inp.policy_controls) : h<string[]>(['policies://advisory-scope-v1']),
    },
    // 5.9 Observability & FinOps
    observability: {
      cost_label: u(inp.cost_label),
      logging_level: d(isAdv ? 'debug' : 'info'),
      required_telemetry: s(['requests', 'tokens', 'p95_latency', 'errors']),
    },
    // 5.10 Deployment
    deployment: {
      exposure_channel: i(inp.consumer_type.includes('team') ? 'internal-web' : 'internal-api'),
      auth_gating: d('sso-required'),
      deploy_rate_limits: rag ? d<string | null>('120/min') : d<string | null>(null),
      environment: s(inp.lifecycle_status === 'live' ? 'production' : 'staging'),
      promotion_rollback: d('blue-green'),
    },
    // 5.11 Runtime (execution)
    runtime: {
      runtime_host: s(runtimeHost),
      resolver_profile: s(`${tier}-resolver-v1`),
      concurrency: d(isAdv ? 8 : isMin ? 2 : 4),
      timeout: d(isAdv ? 60 : 30),
      scaling_policy: d(isAdv ? 'auto:1-8' : 'auto:0-4'),
      model_gateway_ref: s(modelPrimary),
    },
    // 5.12 Knowledge Sources (per RAG source) — ingestion policy / primary source
    knowledge_sources: {
      source_uri: rag && inp.primary_source_uri ? g<string | null>(inp.primary_source_uri) : d<string | null>(null),
      parser: rag ? g<string | null>('document_ai') : d<string | null>(null),
      source_chunking: rag ? g<string | null>('recursive/512-128') : d<string | null>(null),
      embedding_model: rag ? g<string | null>('vertex://text-embedding-004') : d<string | null>(null),
      index_target: rag ? g<string | null>(inp.index_target ?? 'vector://alloydb-default') : d<string | null>(null),
      sensitivity: rag ? gc<Sensitivity | null>(inp.sensitivity ?? 'internal', inp.risk_confirmed ?? false, 'Auto-inferred sensitivity. Confirm with data owner.') : d<Sensitivity | null>(null),
      source_approval: rag ? g<'pending' | 'approved' | 'rejected' | null>(inp.risk_confirmed ? 'approved' : 'pending') : d<'pending' | 'approved' | 'rejected' | null>(null),
      refresh_cadence: rag ? g<'manual' | 'daily' | 'weekly' | 'monthly' | null>('weekly') : d<'manual' | 'daily' | 'weekly' | 'monthly' | null>(null),
      source_version: rag ? g<string | null>('v1') : d<string | null>(null),
    },
    // 5.13 Evidence & Artifact Store
    evidence: {
      evidence_store_uri: inp.evidence_store_uri ? s<string | null>(inp.evidence_store_uri) : d<string | null>(null),
      evidence_retention: inp.evidence_store_uri ? d<string | null>('90d') : d<string | null>(null),
      artifact_links: inp.artifact_links?.length ? s<string[]>(inp.artifact_links) : d<string[]>([]),
    },
  };
}
