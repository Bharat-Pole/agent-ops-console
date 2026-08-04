// Verbatim group labels + ordered leaf field names for the canonical schema.
// Drives the Configuration tab (13 collapsible sections, Section 9.2 #2) and any
// full-schema enumeration. Labels and field names are copied verbatim from
// Section 5.2 — do not paraphrase.

import type { ConfigGroupKey } from './agent';

export interface SchemaGroupMeta {
  key: ConfigGroupKey;
  label: string; // verbatim group heading
  fields: string[]; // verbatim leaf field names, in table order
}

export const SCHEMA_GROUPS: SchemaGroupMeta[] = [
  {
    key: 'identity',
    label: '5.1 Identity & Ownership',
    fields: [
      'agent_name',
      'agent_id',
      'business_owner',
      'technical_owner',
      'executive_sponsor',
      'use_case_category',
      'consumer_type',
      'intended_audience',
      'description',
      'objective',
    ],
  },
  {
    key: 'lifecycle',
    label: '5.2 Lifecycle & Risk',
    fields: ['lifecycle_status', 'risk_tier', 'last_review_date', 'next_review_date', 'exception_status'],
  },
  {
    key: 'model',
    label: '5.3 Model',
    fields: [
      'model_primary',
      'model_fallback',
      'temperature',
      'max_output_tokens',
      'context_window_ref',
      'cost_awareness',
    ],
  },
  {
    key: 'prompt',
    label: '5.4 Prompt & Instruction',
    fields: [
      'system_prompt_ref',
      'user_prompt_template',
      'task_prompt',
      'persona_role',
      'tool_use_instructions',
      'safety_instructions',
      'citation_rules',
      'response_format_contract',
      'stop_conditions',
      'per_sub_agent_prompts',
    ],
  },
  {
    key: 'data',
    label: '5.5 Data & Knowledge',
    fields: [
      'data_sources',
      'rag_enabled',
      'retrieval_type',
      'chunk_size',
      'chunk_overlap',
      'top_k',
      'score_threshold',
      'knowledge_source_refs',
      'structured_grounding',
    ],
  },
  {
    key: 'tooling',
    label: '5.6 Tooling & MCP',
    fields: ['bound_tools', 'tool_permission', 'mcp_connectors', 'tool_auth', 'rate_limits'],
  },
  {
    key: 'orchestration',
    label: '5.7 Orchestration',
    fields: [
      'orchestration_type',
      'sub_agents',
      'retries',
      'fallback_behavior',
      'hitl_gate_placement',
      'a2a_enabled',
      'agent_card',
      'message_task_format',
      'artifact_exchange',
    ],
  },
  {
    key: 'governance',
    label: '5.8 Governance & Approval',
    fields: ['approvals_required', 'audit_level', 'policy_controls'],
  },
  {
    key: 'observability',
    label: '5.9 Observability & FinOps',
    fields: ['cost_label', 'logging_level', 'required_telemetry'],
  },
  {
    key: 'deployment',
    label: '5.10 Deployment',
    fields: ['exposure_channel', 'auth_gating', 'deploy_rate_limits', 'environment', 'promotion_rollback'],
  },
  {
    key: 'runtime',
    label: '5.11 Runtime (execution)',
    fields: ['runtime_host', 'resolver_profile', 'concurrency', 'timeout', 'scaling_policy', 'model_gateway_ref'],
  },
  {
    key: 'knowledge_sources',
    label: '5.12 Knowledge Sources (per RAG source)',
    fields: [
      'source_uri',
      'parser',
      'source_chunking',
      'embedding_model',
      'index_target',
      'sensitivity',
      'source_approval',
      'refresh_cadence',
      'source_version',
    ],
  },
  {
    key: 'evidence',
    label: '5.13 Evidence & Artifact Store',
    fields: ['evidence_store_uri', 'evidence_retention', 'artifact_links'],
  },
];

// Governance-critical fields never resolve to `high` confidence until user-confirmed
// (Section 7.5). Used by the engine and the review card's ⚠️ list.
export const GOVERNANCE_CRITICAL_FIELDS = new Set<string>([
  'risk_tier',
  'tool_permission',
  'sensitivity',
]);
