// Stage 3 — Architecture synthesis (Section 7.3). Apply the winning tier template,
// overlay extracted specifics, decompose sub-agents (Advanced), and build the
// full config via the shared tier-template factory.

import type { Intent, NluResult, Classification, WriteDetection, Synthesis } from './types';
import type { RiskTier, SubAgent, HitlGate, CapabilityTier, Sensitivity } from '@/types';
import { buildConfig, type ConfigInput } from '@/seed/config-factory';

// Sub-agent pattern library (Advanced). Template-match first; else derive one
// sub-agent per detected verb-cluster. Constraints (LOCKED): ≤3 tools, no write,
// coordinator owns routing.
const PATTERN_LIBRARY: { match: RegExp; subs: SubAgent[] }[] = [
  {
    match: /\bincident|outage|triage\b/,
    subs: [
      { name: 'log_analyzer', role: 'Analyze logs and telemetry.', prompt_hint: 'Identify root-cause signals.', tools: [] },
      { name: 'impact_assessor', role: 'Assess customer/service impact.', prompt_hint: 'Quantify blast radius.', tools: [] },
      { name: 'comms_drafter', role: 'Draft incident communications (advisory).', prompt_hint: 'Draft status; never send.', tools: [] },
      { name: 'notification_router', role: 'Recommend recipients; route for human sign-off.', prompt_hint: 'Recommend; a human sends.', tools: [] },
    ],
  },
  {
    match: /\bfiling|regulat|compliance\b/,
    subs: [
      { name: 'filing_researcher', role: 'Research filing requirements.', prompt_hint: 'Gather form + deadlines.', tools: [] },
      { name: 'compliance_checker', role: 'Validate draft vs. rules.', prompt_hint: 'Flag gaps.', tools: [] },
      { name: 'filing_drafter', role: 'Draft the submission (advisory).', prompt_hint: 'Review-ready draft.', tools: [] },
      { name: 'submission_router', role: 'Route for human filing.', prompt_hint: 'Recommend reviewers.', tools: [] },
    ],
  },
];

function decomposeSubAgents(intent: Intent, nlu: NluResult): SubAgent[] {
  const text = (intent.objective || '').toLowerCase();
  for (const p of PATTERN_LIBRARY) if (p.match.test(text)) return p.subs;
  // fallback — one sub-agent per detected action verb (cap at 4)
  const verbs = nlu.action_verbs.slice(0, 4);
  if (verbs.length === 0) return [{ name: 'worker', role: 'Perform the task.', prompt_hint: 'Do the work; advisory only.', tools: [] }];
  return verbs.map((v) => ({ name: `${v}_agent`, role: `Handle the "${v}" step.`, prompt_hint: `Perform ${v}; advisory only.`, tools: [] }));
}

function toolRef(name: string): string {
  return name.startsWith('tools://') ? name : `tools://${name}@v1`;
}

function kbRef(source: string): string {
  return source.startsWith('kb://') ? source : `kb://${source.replace(/_/g, '-')}@v1`;
}

export function synthesize(
  intent: Intent,
  nlu: NluResult,
  cls: Classification,
  write: WriteDetection,
  risk: RiskTier,
): Synthesis {
  const tier: CapabilityTier = cls.proposed_tier;
  const isAdv = tier === 'advanced';
  const dataSources = intent.data_sources ?? [];
  const rag = tier !== 'minimal';

  // advisory-only: never bind flagged (write-capable) tools
  const boundToolNames = (intent.tools ?? []).filter((t) => !write.flagged_tools.includes(t)).slice(0, isAdv ? 6 : 3);
  const subAgents = isAdv ? decomposeSubAgents(intent, nlu) : [];

  const sensitivity: Sensitivity =
    risk === 'critical' ? 'restricted' : risk === 'high' ? 'confidential' : 'internal';

  const gates: HitlGate[] = [];
  if (cls.proposed_tier === 'advanced') gates.push({ placement: 'pre-deploy', trigger: `${tier} pre-deploy sign-off` });
  if (risk === 'critical') gates.push({ placement: 'per-tool-call (runtime)', trigger: 'Mandatory HITL per action (Critical path)' });

  const input: ConfigInput = {
    tier,
    agent_name: intent.agent_name || nlu.domain + ' agent',
    agent_id: 'DRAFT',
    business_owner: intent.business_owner || 'unassigned',
    technical_owner: intent.technical_owner || 'unassigned',
    use_case_category: nlu.domain,
    consumer_type: nlu.audience || 'internal team',
    intended_audience: intent.intended_audience || nlu.audience || 'internal team',
    description: intent.objective,
    objective: intent.objective,
    lifecycle_status: 'draft',
    risk_tier: risk,
    risk_confirmed: false,
    data_sources: dataSources,
    knowledge_source_refs: rag ? dataSources.map(kbRef) : [],
    primary_source_uri: rag && dataSources.length ? `gs://brightspeed-${nlu.domain}/${dataSources[0]}/` : null,
    sensitivity,
    bound_tools: boundToolNames.map(toolRef),
    sub_agents: subAgents,
    hitl_gates: gates,
    per_sub_agent_prompts: isAdv ? Object.fromEntries(subAgents.map((s) => [s.name, s.prompt_hint])) : null,
    citation_rules: rag ? 'policies://citation-standard-v1' : null,
    cost_label: `${nlu.domain}-ops`,
    a2a_enabled: !rag ? false : true,
    artifact_exchange: isAdv,
    message_task_format: isAdv ? 'a2a/task-v1' : null,
    system_prompt_ref: isAdv ? 'prompts://coordinator-system-v1' : `prompts://${tier}-base-v1`,
  };

  return { config: buildConfig(input), sub_agents: subAgents };
}
