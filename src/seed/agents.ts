import type { AgentRecord, SubAgent, HitlGate, ReviewCard } from '@/types';
import { buildConfig } from './config-factory';
import {
  assembleAgent,
  buildSignals,
  scoresFrom,
  registryTrack,
  runtimeTrack,
  contentTrack,
  mkReviewCard,
  daysFromToday,
  isoTs,
} from './helpers';
import { AGENT, PACK, SOURCE } from './ids';
import { governancePathFor, TIER_LABEL, PATH_DEFS } from '@/kernel/constants';

// ---- Sub-agent decomposition (Advanced) ----
const INCIDENT_SUBAGENTS: SubAgent[] = [
  { name: 'log_analyzer', role: 'Analyze logs and telemetry to characterize the incident.', prompt_hint: 'Identify root cause signals from logs.', tools: ['tools://log_reader@v1', 'tools://incident_reader@v1'] },
  { name: 'impact_assessor', role: 'Assess customer and service impact.', prompt_hint: 'Quantify blast radius and SLO burn.', tools: ['tools://health_checker@v1'] },
  { name: 'comms_drafter', role: 'Draft incident communications (advisory — never sends).', prompt_hint: 'Draft status updates; do not send.', tools: [] },
  { name: 'notification_router', role: 'Recommend who to notify and route the draft for human sign-off.', prompt_hint: 'Recommend recipients; a human sends.', tools: ['tools://jira_reader@v1'] },
];

const REGULATORY_SUBAGENTS: SubAgent[] = [
  { name: 'filing_researcher', role: 'Research filing requirements per jurisdiction.', prompt_hint: 'Gather form + deadline requirements.', tools: ['tools://filing_reader@v1'] },
  { name: 'compliance_checker', role: 'Validate draft against regulatory rules.', prompt_hint: 'Flag gaps vs. requirements.', tools: ['tools://filing_reader@v1'] },
  { name: 'filing_drafter', role: 'Draft the submission (advisory — never files).', prompt_hint: 'Produce a review-ready draft.', tools: [] },
  { name: 'submission_router', role: 'Route the draft to compliance officers for filing.', prompt_hint: 'Recommend reviewers; a human files.', tools: [] },
];

const INCIDENT_GATES: HitlGate[] = [
  { placement: 'pre-deploy', trigger: 'Deep-path pre-deploy sign-off' },
  { placement: 'on comms_drafter → notification_router edge', trigger: 'Human approves recipients before routing' },
];

const REGULATORY_GATES: HitlGate[] = [
  { placement: 'pre-deploy', trigger: 'Critical-path committee sign-off' },
  { placement: 'per-tool-call (runtime)', trigger: 'Mandatory HITL per action (Critical path)' },
  { placement: 'on filing_drafter → submission_router edge', trigger: 'Compliance officer approves before routing' },
];

// Helper: build a review card for the advanced agents that carry flagged-tool stories.
function advancedReviewCard(opts: {
  tier: 'advanced';
  archetype: ReviewCard['proposed_archetype'];
  signals: ReviewCard['signal_breakdown'];
  scores: ReviewCard['scores'];
  risk: ReviewCard['governance_summary']['risk_tier'];
  risk_why: string;
  path: ReviewCard['governance_summary']['governance_path'];
  boundTools: string[];
  flagged: string[];
  subAgentCount: number;
}): ReviewCard {
  const pd = PATH_DEFS[opts.path];
  return mkReviewCard({
    proposed_tier: opts.tier,
    proposed_archetype: opts.archetype,
    tier_label: TIER_LABEL[opts.tier],
    signal_breakdown: opts.signals,
    scores: opts.scores,
    config_summary: {
      model: 'vertex://gemini-1.5-pro (per-sub-agent routing)',
      rag: 'Enabled (structured grounding)',
      tools: opts.boundTools,
      orchestration: 'coordinator+subagents',
      a2a: 'full exchange',
    },
    governance_summary: {
      risk_tier: opts.risk,
      risk_why: opts.risk_why,
      governance_path: opts.path,
      path_desc: pd.desc,
      approvals_required: pd.approvals,
      hitl_gates: pd.hitl_gates,
    },
    capability_floor_note: null,
    flagged_write_tools: opts.flagged,
    fields_requiring_confirmation: [
      {
        field: 'bound_tools',
        proposed_value: `${opts.flagged.length} write-capable tool(s) FLAGGED`,
        confidence: 'low',
        gap_note: 'Write-capable tools detected. NOT bound. Advisory-only scope enforced — human decision required.',
        governance_critical: false,
      },
      {
        field: 'risk_tier',
        proposed_value: opts.risk,
        confidence: 'medium',
        gap_note: 'Inferred from objective — confirm data sensitivity.',
        governance_critical: true,
      },
      {
        field: 'sub_agents',
        proposed_value: `${opts.subAgentCount} sub-agents decomposed`,
        confidence: 'low',
        gap_note: 'Auto-decomposed. Confirm ownership and prompts.',
        governance_critical: false,
      },
    ],
    reasoning: [
      `argmax(minimal=${opts.scores.minimal}, standardized=${opts.scores.standardized}, advanced=${opts.scores.advanced}) → advanced`,
      'OVERRIDE: explicit multi-agent (S6>0) → force Advanced',
    ],
  });
}

// =========================================================================
// The 9 seed agents (Section 12.1)
// =========================================================================
export const SEED_AGENTS: AgentRecord[] = [
  // 1 — HR Policy Bot · Minimal · Low · Fast · LIVE (fast-path expiry in 6 days)
  (() => {
    const sig = buildSignals({});
    const cfg = buildConfig({
      tier: 'minimal',
      agent_name: 'HR Policy Bot',
      agent_id: AGENT.hr,
      business_owner: 'dana.hr@brightspeed.com',
      technical_owner: 'raj.patel@brightspeed.com',
      use_case_category: 'HR',
      consumer_type: 'employees',
      intended_audience: 'All Brightspeed employees',
      description: 'A simple advisor that answers HR policy and benefits questions in plain language.',
      objective: 'Answer employee questions about company HR policies and benefits in plain language.',
      lifecycle_status: 'live',
      risk_tier: 'low',
      risk_confirmed: true,
      system_prompt_ref: 'prompts://hr-safety-v2.1@v2.1',
      safety_instructions: 'prompts://hr-safety-v2.1@v2.1',
      cost_label: 'hr-ops',
      last_review_date: daysFromToday(-84),
      next_review_date: daysFromToday(6),
    });
    return assembleAgent(cfg, {
      capability_tier: 'minimal',
      governance_path: governancePathFor('minimal', 'low'),
      registry: registryTrack('ready', isoTs(daysFromToday(-84), 10)),
      runtime: runtimeTrack('ready', isoTs(daysFromToday(-84), 11)),
      content: contentTrack('ready', isoTs(daysFromToday(-84), 11), false),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.hr,
      fast_path_expiry_date: daysFromToday(6), // expiry story
      created_at: isoTs('2026-01-15', 9),
      updated_at: isoTs(daysFromToday(-2), 14),
    });
  })(),

  // 2 — NOC Incident Summarizer · Standardized · Medium · Standard · LIVE (highest traffic)
  (() => {
    const sig = buildSignals({
      S1: 'incident database provided (retrieval need)',
      S2: 'summarize AND flag (2 action verbs)',
      S4: 'incident_reader tool bound',
    });
    const cfg = buildConfig({
      tier: 'standardized',
      agent_name: 'NOC Incident Summarizer',
      agent_id: AGENT.noc,
      business_owner: 'sarah.chen@brightspeed.com',
      technical_owner: 'marcus.dev@brightspeed.com',
      use_case_category: 'network_ops',
      consumer_type: 'NOC team',
      intended_audience: 'Network Operations Center analysts',
      description: 'Summarizes weekly incident reports and flags critical incidents, grounded in the incident DB.',
      objective: 'Summarize weekly incident reports for the NOC team and flag critical ones, grounded in the incident database.',
      lifecycle_status: 'live',
      risk_tier: 'medium',
      risk_confirmed: true,
      data_sources: ['incident_db'],
      knowledge_source_refs: [`kb://${SOURCE.incidentDb}@v3`],
      primary_source_uri: 'gs://brightspeed-noc/incident-db/',
      index_target: 'vector://alloydb-incidents',
      sensitivity: 'internal',
      bound_tools: ['tools://incident_reader@v1'],
      mcp_connectors: ['gcp-ticketing'],
      system_prompt_ref: 'prompts://noc-summarizer@v2',
      citation_rules: 'prompts://citation-standard-v1@v1',
      policy_controls: ['policies://advisory-scope-v1', 'policies://citation-standard-v1'],
      approvals_required: ['business_owner', 'risk_officer'],
      cost_label: 'noc-ops',
      agent_card_ref: `a2a://${AGENT.noc}`,
      last_review_date: daysFromToday(-30),
      next_review_date: daysFromToday(60),
      evidence_store_uri: 'gs://brightspeed-evidence/noc-summarizer/',
    });
    return assembleAgent(cfg, {
      capability_tier: 'standardized',
      governance_path: governancePathFor('standardized', 'medium'),
      registry: registryTrack('ready', isoTs(daysFromToday(-30), 10)),
      runtime: runtimeTrack('ready', isoTs(daysFromToday(-30), 11)),
      content: contentTrack('ready', isoTs(daysFromToday(-1), 3), true),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.noc,
      approval_ids: ['appr-noc-bo', 'appr-noc-risk'],
      created_at: isoTs('2026-01-22', 9),
      updated_at: isoTs(daysFromToday(0), 8),
    });
  })(),

  // 3 — Incident Response Coordinator · Advanced · High · Deep · approved; Runtime ⏳ Content ⏳
  (() => {
    const sig = buildSignals({
      S1: 'incident DB + ticketing (retrieval need)',
      S2: 'analyze, assess, draft, route (multi-skill)',
      S3: 'incident DB + ticketing + Slack (cross-system)',
      S4: 'multiple reader tools bound',
      S5: 'route notifications to on-call (hand-off)',
      S6: 'coordinate a team of agents (explicit multi-agent)',
    });
    const scores = scoresFrom(sig);
    const cfg = buildConfig({
      tier: 'advanced',
      agent_name: 'Incident Response Coordinator',
      agent_id: AGENT.incident,
      business_owner: 'sarah.chen@brightspeed.com',
      technical_owner: 'marcus.dev@brightspeed.com',
      executive_sponsor: 'vp.networkops@brightspeed.com',
      use_case_category: 'network_ops',
      consumer_type: 'NOC team',
      intended_audience: 'NOC incident responders and on-call leads',
      description: 'Coordinates sub-agents to triage major incidents: log analysis, impact, comms drafting, and notification routing.',
      objective: 'Coordinate a team of agents to triage major incidents: analyze logs from the incident database and ticketing system, assess customer impact, draft comms, and route notifications to the on-call NOC lead and Slack.',
      lifecycle_status: 'approved',
      risk_tier: 'high',
      risk_confirmed: true,
      data_sources: ['incident_db', 'ticketing'],
      knowledge_source_refs: [`kb://${SOURCE.incidentDb}@v3`],
      primary_source_uri: 'gs://brightspeed-noc/incident-db/',
      index_target: 'vector://alloydb-incidents',
      sensitivity: 'internal',
      bound_tools: ['tools://incident_reader@v1', 'tools://log_reader@v1', 'tools://health_checker@v1', 'tools://jira_reader@v1'],
      mcp_connectors: ['gcp-ticketing', 'jira'],
      sub_agents: INCIDENT_SUBAGENTS,
      hitl_gates: INCIDENT_GATES,
      per_sub_agent_prompts: {
        log_analyzer: 'Analyze logs; identify root-cause signals; cite incident records.',
        impact_assessor: 'Quantify customer/service impact and SLO burn.',
        comms_drafter: 'Draft status comms; advisory only, never send.',
        notification_router: 'Recommend recipients; route draft for human approval.',
      },
      system_prompt_ref: 'prompts://coordinator-system-v1@v1',
      citation_rules: 'prompts://citation-standard-v1@v1',
      policy_controls: ['policies://advisory-scope-v1', 'policies://citation-standard-v1'],
      approvals_required: ['business_owner', 'risk_officer', 'security_committee'],
      cost_label: 'noc-ops',
      artifact_exchange: true,
      message_task_format: 'a2a/task-v1',
      agent_card_ref: `a2a://${AGENT.incident}`,
      evidence_store_uri: 'gs://brightspeed-evidence/incident-coordinator/',
    });
    return assembleAgent(cfg, {
      capability_tier: 'advanced',
      governance_path: governancePathFor('advanced', 'high'),
      registry: registryTrack('ready', isoTs(daysFromToday(-10), 10)),
      runtime: runtimeTrack('in_progress', isoTs(daysFromToday(0), 8)),
      content: contentTrack('in_progress', isoTs(daysFromToday(0), 8), true),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.incident,
      approval_ids: ['appr-incident-bo', 'appr-incident-risk', 'appr-incident-sec'],
      review_card: advancedReviewCard({
        tier: 'advanced',
        archetype: 'workflow_coordinator',
        signals: sig,
        scores,
        risk: 'high',
        risk_why: 'customer-impacting incidents + write-intent detected',
        path: 'deep',
        boundTools: ['incident_reader', 'log_reader', 'health_checker', 'jira_reader'],
        flagged: ['slack_notifier', 'email_sender'],
        subAgentCount: 4,
      }),
      created_at: isoTs('2026-02-05', 9),
      updated_at: isoTs(daysFromToday(0), 8),
    });
  })(),

  // 4 — Contract Clause Finder · Standardized · High · Deep · in_review; eval score 82 (failing-eval story)
  (() => {
    const sig = buildSignals({
      S1: 'contracts repository provided (retrieval need)',
      S4: 'contract_reader tool bound',
    });
    const cfg = buildConfig({
      tier: 'standardized',
      agent_name: 'Contract Clause Finder',
      agent_id: AGENT.contract,
      business_owner: 'lena.legal@brightspeed.com',
      technical_owner: 'raj.patel@brightspeed.com',
      use_case_category: 'legal',
      consumer_type: 'legal team',
      intended_audience: 'Legal counsel and contract managers',
      description: 'Finds and summarizes specific clauses from the contracts repository.',
      objective: 'Find and summarize specific clauses from the contracts repository for the legal team.',
      lifecycle_status: 'in_review',
      risk_tier: 'high',
      risk_confirmed: false,
      data_sources: ['contracts_repo'],
      knowledge_source_refs: [`kb://${SOURCE.contractsRepo}@v1`],
      primary_source_uri: 'gs://brightspeed-legal/contracts/',
      index_target: 'vector://alloydb-contracts',
      sensitivity: 'confidential',
      bound_tools: ['tools://contract_reader@v1'],
      system_prompt_ref: 'prompts://rag-answer-template-v1@v1',
      citation_rules: 'prompts://citation-standard-v1@v1',
      policy_controls: ['policies://advisory-scope-v1', 'policies://citation-standard-v1'],
      approvals_required: ['business_owner', 'risk_officer', 'security_committee'],
      cost_label: 'legal-ops',
      // Deliberately mis-set per Section 11.3: threshold 0.95 fails two grounding cases.
      score_threshold: 0.95,
      evidence_store_uri: 'gs://brightspeed-evidence/contract-finder/',
    });
    return assembleAgent(cfg, {
      capability_tier: 'standardized',
      governance_path: governancePathFor('standardized', 'high'),
      registry: registryTrack('in_progress', isoTs(daysFromToday(-6), 10)),
      runtime: runtimeTrack('not_started', null),
      content: contentTrack('ready', isoTs(daysFromToday(-9), 3), true),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.contract,
      approval_ids: ['appr-contract-bo', 'appr-contract-risk', 'appr-contract-sec'],
      created_at: isoTs('2026-02-18', 9),
      updated_at: isoTs(daysFromToday(-1), 15),
    });
  })(),

  // 5 — Field Ops FAQ Bot · Minimal · Low · Fast · LIVE (faq_bot, near-zero cost)
  (() => {
    const sig = buildSignals({});
    const cfg = buildConfig({
      tier: 'minimal',
      agent_name: 'Field Ops FAQ Bot',
      agent_id: AGENT.faq,
      business_owner: 'tom.field@brightspeed.com',
      technical_owner: 'raj.patel@brightspeed.com',
      use_case_category: 'field_ops',
      consumer_type: 'field technicians',
      intended_audience: 'Field installation technicians',
      description: 'Answers common field-technician questions about installation and equipment.',
      objective: 'Answer common field-technician questions about installation procedures and equipment.',
      lifecycle_status: 'live',
      risk_tier: 'low',
      risk_confirmed: true,
      system_prompt_ref: 'prompts://faq-template-v1@v1',
      cost_label: 'field-ops',
      last_review_date: daysFromToday(-40),
      next_review_date: daysFromToday(50),
    });
    return assembleAgent(cfg, {
      capability_tier: 'minimal',
      governance_path: governancePathFor('minimal', 'low'),
      registry: registryTrack('ready', isoTs(daysFromToday(-40), 10)),
      runtime: runtimeTrack('ready', isoTs(daysFromToday(-40), 11)),
      content: contentTrack('ready', isoTs(daysFromToday(-40), 11), false),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.faq,
      fast_path_expiry_date: daysFromToday(50),
      created_at: isoTs('2026-01-12', 9),
      updated_at: isoTs(daysFromToday(-5), 12),
    });
  })(),

  // 6 — Churn Insight Assistant · Standardized · Medium · Standard · registered; 1 of 2 approvals pending
  (() => {
    const sig = buildSignals({
      S1: 'churn analytics provided (retrieval need)',
      S2: 'analyze AND recommend (multi-skill)',
      S4: 'crm_reader tool bound',
    });
    const cfg = buildConfig({
      tier: 'standardized',
      agent_name: 'Churn Insight Assistant',
      agent_id: AGENT.churn,
      business_owner: 'nina.sales@brightspeed.com',
      technical_owner: 'raj.patel@brightspeed.com',
      use_case_category: 'sales',
      consumer_type: 'retention team',
      intended_audience: 'Customer retention analysts',
      description: 'Analyzes churn signals and recommends save plays.',
      objective: 'Analyze customer churn signals from CRM data and recommend save plays for the retention team.',
      lifecycle_status: 'registered',
      risk_tier: 'medium',
      risk_confirmed: false,
      data_sources: ['churn_analytics'],
      knowledge_source_refs: [`kb://${SOURCE.churnAnalytics}@v1`],
      primary_source_uri: 'gs://brightspeed-sales/churn/',
      index_target: 'vector://alloydb-churn',
      sensitivity: 'confidential',
      bound_tools: ['tools://crm_reader@v1'],
      mcp_connectors: ['crm-readonly'],
      system_prompt_ref: 'prompts://rag-answer-template-v1@v1',
      citation_rules: 'prompts://citation-standard-v1@v1',
      policy_controls: ['policies://advisory-scope-v1', 'policies://citation-standard-v1'],
      approvals_required: ['business_owner', 'risk_officer'],
      cost_label: 'sales-ops',
    });
    return assembleAgent(cfg, {
      capability_tier: 'standardized',
      governance_path: governancePathFor('standardized', 'medium'),
      registry: registryTrack('in_progress', isoTs(daysFromToday(-3), 10)),
      runtime: runtimeTrack('not_started', null),
      content: contentTrack('ready', isoTs(daysFromToday(-5), 3), true),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.churn,
      approval_ids: ['appr-churn-bo', 'appr-churn-risk'],
      created_at: isoTs('2026-03-01', 9),
      updated_at: isoTs(daysFromToday(-3), 10),
    });
  })(),

  // 7 — Network Capacity Research Assistant · Standardized · Medium · Standard · LIVE; Content re-indexing ⏳
  (() => {
    const sig = buildSignals({
      S1: 'capacity reports provided (retrieval need)',
      S2: 'research AND summarize (multi-skill)',
      S4: 'capacity_api_reader tool bound',
    });
    const cfg = buildConfig({
      tier: 'standardized',
      agent_name: 'Network Capacity Research Assistant',
      agent_id: AGENT.capacity,
      business_owner: 'omar.planning@brightspeed.com',
      technical_owner: 'marcus.dev@brightspeed.com',
      use_case_category: 'network_ops',
      consumer_type: 'capacity planning team',
      intended_audience: 'Network capacity planners',
      description: 'Researches capacity trends and summarizes regional headroom for planning.',
      objective: 'Research network capacity trends from capacity reports and summarize regional headroom for planning.',
      lifecycle_status: 'live',
      risk_tier: 'medium',
      risk_confirmed: true,
      data_sources: ['capacity_reports'],
      knowledge_source_refs: [`kb://${SOURCE.capacityReports}@v2`],
      primary_source_uri: 'gs://brightspeed-noc/capacity/',
      index_target: 'vector://alloydb-capacity',
      sensitivity: 'internal',
      bound_tools: ['tools://capacity_api_reader@v1'],
      system_prompt_ref: 'prompts://rag-answer-template-v1@v1',
      citation_rules: 'prompts://citation-standard-v1@v1',
      policy_controls: ['policies://advisory-scope-v1', 'policies://citation-standard-v1'],
      approvals_required: ['business_owner', 'risk_officer'],
      cost_label: 'noc-ops',
      agent_card_ref: `a2a://${AGENT.capacity}`,
      last_review_date: daysFromToday(-20),
      next_review_date: daysFromToday(70),
      evidence_store_uri: 'gs://brightspeed-evidence/capacity-research/',
    });
    return assembleAgent(cfg, {
      capability_tier: 'standardized',
      governance_path: governancePathFor('standardized', 'medium'),
      registry: registryTrack('ready', isoTs(daysFromToday(-20), 10)),
      runtime: runtimeTrack('ready', isoTs(daysFromToday(-20), 11)),
      // Content re-indexing in progress (pipeline-refresh + Demo Mode story)
      content: contentTrack('in_progress', isoTs(daysFromToday(0), 2), true),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.capacity,
      approval_ids: ['appr-capacity-bo', 'appr-capacity-risk'],
      created_at: isoTs('2026-03-10', 9),
      updated_at: isoTs(daysFromToday(0), 2),
    });
  })(),

  // 8 — Regulatory Filing Coordinator · Advanced · Critical · Critical · approved, LIVE (runtime-HITL-per-action)
  (() => {
    const sig = buildSignals({
      S1: 'filings repository provided (retrieval need)',
      S2: 'research, check, draft, route (multi-skill)',
      S4: 'filing_reader tool bound',
      S5: 'route for review (hand-off)',
      S6: 'coordinate a team of agents (explicit multi-agent)',
    });
    const scores = scoresFrom(sig);
    const cfg = buildConfig({
      tier: 'advanced',
      agent_name: 'Regulatory Filing Coordinator',
      agent_id: AGENT.regulatory,
      business_owner: 'grace.compliance@brightspeed.com',
      technical_owner: 'marcus.dev@brightspeed.com',
      executive_sponsor: 'chief.compliance@brightspeed.com',
      use_case_category: 'compliance',
      consumer_type: 'compliance team',
      intended_audience: 'Regulatory compliance officers',
      description: 'Coordinates sub-agents to prepare regulatory filings across jurisdictions with runtime HITL per action.',
      objective: 'Coordinate a team of agents to prepare regulatory filings across FCC and state PUC jurisdictions: research requirements from the filings repository, check compliance, draft submissions, and route for review — including cross-border data attestations.',
      lifecycle_status: 'live',
      risk_tier: 'critical',
      risk_confirmed: true,
      data_sources: ['regulatory_filings'],
      knowledge_source_refs: [`kb://${SOURCE.regulatoryFilings}@v1`],
      primary_source_uri: 'gs://brightspeed-compliance/filings/',
      index_target: 'vector://alloydb-filings',
      sensitivity: 'restricted',
      bound_tools: ['tools://filing_reader@v1'],
      mcp_connectors: ['filings-gateway'],
      sub_agents: REGULATORY_SUBAGENTS,
      hitl_gates: REGULATORY_GATES,
      per_sub_agent_prompts: {
        filing_researcher: 'Research filing requirements and deadlines per jurisdiction.',
        compliance_checker: 'Validate the draft against regulatory rules; flag gaps.',
        filing_drafter: 'Draft the submission; advisory only, never file.',
        submission_router: 'Recommend reviewers; route for human filing.',
      },
      system_prompt_ref: 'prompts://coordinator-system-v1@v1',
      citation_rules: 'prompts://citation-standard-v1@v1',
      policy_controls: ['policies://advisory-scope-v1', 'policies://citation-standard-v1', 'policies://runtime-hitl-v1'],
      approvals_required: ['business_owner', 'risk_officer', 'security_committee'],
      cost_label: 'compliance-ops',
      artifact_exchange: true,
      message_task_format: 'a2a/task-v1',
      agent_card_ref: `a2a://${AGENT.regulatory}`,
      last_review_date: daysFromToday(-25),
      next_review_date: daysFromToday(65),
      evidence_store_uri: 'gs://brightspeed-evidence/regulatory-coordinator/',
    });
    return assembleAgent(cfg, {
      capability_tier: 'advanced',
      governance_path: governancePathFor('advanced', 'critical'),
      registry: registryTrack('ready', isoTs(daysFromToday(-25), 10)),
      runtime: runtimeTrack('ready', isoTs(daysFromToday(-25), 11)),
      content: contentTrack('ready', isoTs(daysFromToday(-11), 3), true),
      signal_breakdown: sig,
      evaluation_pack_id: PACK.regulatory,
      approval_ids: ['appr-reg-bo', 'appr-reg-risk', 'appr-reg-sec'],
      review_card: advancedReviewCard({
        tier: 'advanced',
        archetype: 'workflow_coordinator',
        signals: sig,
        scores,
        risk: 'critical',
        risk_why: 'cross-border / regulated filing data',
        path: 'critical',
        boundTools: ['filing_reader'],
        flagged: ['email_sender'],
        subAgentCount: 4,
      }),
      created_at: isoTs('2026-03-20', 9),
      updated_at: isoTs(daysFromToday(-1), 16),
    });
  })(),
];
