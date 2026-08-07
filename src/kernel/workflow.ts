// Blueprint Module 5 — Workflow & Agent Builder. Unlike a free-form drag-and-drop
// canvas, step ORDER here is fixed pipeline semantics (mirrors how a real agent
// runtime actually executes a request): intake → retrieval → prompt assembly →
// model call → tool calls → orchestration/handoff → approval gate → guardrails
// → evaluation → output shaping → deployment. What IS editable per agent is
// which optional steps are enabled and which real assets each step binds to —
// this is a second, pipeline-shaped view onto the exact same AgentConfig the
// Configuration tab edits, not a separate/parallel data model.
import type { AgentRecord, ConfigGroupKey } from '@/types';

export type WorkflowStepKind =
  | 'intake'
  | 'rag'
  | 'structured_query'
  | 'prompt'
  | 'llm'
  | 'tool_call'
  | 'orchestration'
  | 'a2a'
  | 'human_approval'
  | 'guardrail'
  | 'evaluation'
  | 'output_format'
  | 'deployment';

export interface WorkflowStep {
  kind: WorkflowStepKind;
  label: string;
  optional: boolean; // only appears / is meaningful conditionally
  enabled: boolean; // current on/off state for this agent
  toggleField: { groupKey: ConfigGroupKey; field: string } | null; // present when a single boolean field drives `enabled`
  detail: string;
  badges: string[];
  assetRefs: string[]; // verbatim asset URIs — rendered via <AssetRefLink>
}

export function deriveWorkflowSteps(agent: AgentRecord): WorkflowStep[] {
  const c = agent.config;
  const steps: WorkflowStep[] = [];

  steps.push({
    kind: 'intake',
    label: 'Intake',
    optional: false,
    enabled: true,
    toggleField: null,
    detail: `${c.identity.consumer_type.value} request from ${c.identity.intended_audience.value}, scoped to "${c.identity.use_case_category.value}".`,
    badges: [agent.capability_tier],
    assetRefs: [],
  });

  const ragOn = c.data.rag_enabled.value;
  steps.push({
    kind: 'rag',
    label: 'Retrieval (RAG)',
    optional: true,
    enabled: ragOn,
    toggleField: { groupKey: 'data', field: 'rag_enabled' },
    detail: ragOn
      ? `${c.data.retrieval_type.value ?? 'semantic'} retrieval, top_k ${c.data.top_k.value ?? '—'}, score threshold ${c.data.score_threshold.value ?? '—'}.`
      : 'Not grounded — this agent answers from prompt + parametric knowledge only.',
    badges: ragOn ? [String(c.data.retrieval_type.value ?? 'semantic')] : ['disabled'],
    assetRefs: ragOn ? c.data.knowledge_source_refs.value : [],
  });

  const structOn = c.data.structured_grounding.value;
  steps.push({
    kind: 'structured_query',
    label: 'Structured data query',
    optional: true,
    enabled: structOn,
    toggleField: { groupKey: 'data', field: 'structured_grounding' },
    detail: structOn ? `Queries structured sources: ${c.data.data_sources.value.join(', ') || '—'}.` : 'No structured-data query step for this agent.',
    badges: structOn ? ['enabled'] : ['disabled'],
    assetRefs: [],
  });

  steps.push({
    kind: 'prompt',
    label: 'Prompt assembly',
    optional: false,
    enabled: true,
    toggleField: null,
    detail: `Persona: ${c.prompt.persona_role.value}.`,
    badges: [],
    assetRefs: [c.prompt.system_prompt_ref.value, c.prompt.citation_rules.value].filter((v): v is string => !!v),
  });

  steps.push({
    kind: 'llm',
    label: 'Model call',
    optional: false,
    enabled: true,
    toggleField: null,
    detail: `temperature ${c.model.temperature.value}, max_output_tokens ${c.model.max_output_tokens.value}.`,
    badges: [c.model.cost_awareness.value],
    assetRefs: [c.model.model_primary.value, c.model.model_fallback.value].filter((v): v is string => !!v),
  });

  const hasTools = c.tooling.bound_tools.value.length > 0;
  steps.push({
    kind: 'tool_call',
    label: 'Tool / MCP calls',
    optional: true,
    enabled: hasTools,
    toggleField: null, // array-valued — bind/unbind individual tools on the Tools & MCP page, not a single flip here
    detail: hasTools ? `permission ceiling: ${c.tooling.tool_permission.value}.` : 'No tools bound to this agent.',
    badges: hasTools ? [c.tooling.tool_permission.value] : ['disabled'],
    // mcp_connectors is stored as bare connector ids (no scheme, unlike bound_tools) —
    // prefix for display only so AssetRefLink can resolve it into a real chip.
    assetRefs: [...c.tooling.bound_tools.value, ...c.tooling.mcp_connectors.value.map((id) => `mcp://${id}`)],
  });

  const multiAgent = c.orchestration.orchestration_type.value !== 'single';
  steps.push({
    kind: 'orchestration',
    label: 'Sub-agent orchestration',
    optional: true,
    enabled: multiAgent,
    toggleField: null, // enum-valued — reconstructing the orchestration topology is a bigger change than a flip
    detail: multiAgent
      ? `${c.orchestration.orchestration_type.value} · ${c.orchestration.sub_agents.value.map((s) => s.name).join(', ') || 'sub-agents unnamed'} · retries ${c.orchestration.retries.value}.`
      : 'Single-agent — no coordinator/sub-agent fan-out.',
    badges: multiAgent ? [c.orchestration.orchestration_type.value] : ['single'],
    assetRefs: [],
  });

  const a2aOn = c.orchestration.a2a_enabled.value;
  steps.push({
    kind: 'a2a',
    label: 'A2A handoff',
    optional: true,
    enabled: a2aOn,
    toggleField: { groupKey: 'orchestration', field: 'a2a_enabled' },
    detail: a2aOn ? 'Discoverable/handoff-capable per its A2A agent card.' : 'Not A2A-enabled.',
    badges: a2aOn ? ['enabled'] : ['disabled'],
    assetRefs: [c.orchestration.agent_card.value].filter((v): v is string => !!v),
  });

  const hitlOn = c.orchestration.hitl_gate_placement.value.length > 0;
  steps.push({
    kind: 'human_approval',
    label: 'Human approval gate',
    optional: true,
    enabled: hitlOn,
    toggleField: null, // array-valued — gate placements are set by governance path, not a single flip
    detail: hitlOn
      ? c.orchestration.hitl_gate_placement.value.map((g) => `${g.placement} (${g.trigger})`).join('; ')
      : 'No runtime HITL gate configured.',
    badges: hitlOn ? [`${c.orchestration.hitl_gate_placement.value.length} gate(s)`] : ['none'],
    assetRefs: [],
  });

  steps.push({
    kind: 'guardrail',
    label: 'Guardrails & safety',
    optional: false,
    enabled: true,
    toggleField: null,
    detail: c.prompt.safety_instructions.value,
    badges: [`audit: ${c.governance.audit_level.value}`],
    assetRefs: c.governance.policy_controls.value,
  });

  steps.push({
    kind: 'evaluation',
    label: 'Evaluation',
    optional: false,
    enabled: !!agent.evaluation_pack_id,
    toggleField: null,
    detail: agent.evaluation_pack_id ? `Scored by ${agent.evaluation_pack_id}.` : 'No evaluation pack linked yet.',
    badges: [],
    assetRefs: [],
  });

  steps.push({
    kind: 'output_format',
    label: 'Output formatting',
    optional: false,
    enabled: true,
    toggleField: null,
    detail: c.prompt.response_format_contract.value ?? 'No fixed response-format contract — free-form text.',
    badges: [],
    assetRefs: [],
  });

  steps.push({
    kind: 'deployment',
    label: 'Deployment',
    optional: false,
    enabled: true,
    toggleField: null,
    detail: `${c.deployment.exposure_channel.value} · ${c.deployment.environment.value} · ${c.deployment.auth_gating.value}.`,
    badges: [c.deployment.promotion_rollback.value],
    assetRefs: [],
  });

  return steps;
}
