// LOCKED domain constants. Governance matrix (Section 8.1), path definitions,
// tier plain-language names, persona metadata. Verbatim from the spec.

import type {
  CapabilityTier,
  RiskTier,
  GovernancePath,
  Persona,
  PathDefinition,
} from '@/types';

// ---- Governance matrix f(capability, risk) — Section 8.1, VERBATIM --------
export const GOVERNANCE_MATRIX: Record<CapabilityTier, Record<RiskTier, GovernancePath>> = {
  minimal: { low: 'fast', medium: 'standard', high: 'standard', critical: 'deep' },
  standardized: { low: 'fast', medium: 'standard', high: 'deep', critical: 'deep' },
  advanced: { low: 'standard', medium: 'deep', high: 'deep', critical: 'critical' },
};

export function governancePathFor(tier: CapabilityTier, risk: RiskTier): GovernancePath {
  return GOVERNANCE_MATRIX[tier][risk];
}

// ---- Path definitions — Section 8.1, verbatim ----------------------------
export const PATH_DEFS: Record<GovernancePath, PathDefinition> = {
  fast: {
    path: 'fast',
    label: 'Fast',
    approvals: [],
    hitl_gates: 1,
    desc: 'Auto-approve if schema valid; 1 HITL gate max (pre-deploy); 5-min auto-approval SLA.',
  },
  standard: {
    path: 'standard',
    label: 'Standard',
    approvals: ['business_owner', 'risk_officer'],
    hitl_gates: 2,
    desc: 'business_owner approval + risk_officer review; 2 HITL gates.',
  },
  deep: {
    path: 'deep',
    label: 'Deep',
    approvals: ['business_owner', 'risk_officer', 'security_committee'],
    hitl_gates: 2,
    desc: 'Full Phase 6 eval (pack must score ≥90) + committee approval.',
  },
  critical: {
    path: 'critical',
    label: 'Critical',
    approvals: ['business_owner', 'risk_officer', 'security_committee'],
    hitl_gates: 3,
    desc: 'Deep + mandatory runtime HITL per action.',
  },
};

// Deep-path promotion requires eval score ≥ this (Section 8.2 / 11.3).
export const DEEP_EVAL_PASS_SCORE = 90;

// ---- Tool Permission Matrix — deck slide 25 --------------------------------
// `permission`, `description` and `treatment_text` are **verbatim from deck
// slide 25** ("Detailed Tool Permission Matrix"), read from the source .pptx on
// 2026-08-05. Slide 25 is a named Day-90 artifact, so this view quotes it
// rather than paraphrasing — an earlier version paraphrased, which meant the
// console and the deck could drift without anyone noticing. **If you edit these
// strings, you are editing a client-facing commitment: change the deck first.**
//
// Note the deck is not internally consistent about the vocabulary, and slide 25
// is the one to follow:
//   · slide 21 says "read, retrieve, summarize, draft, recommend, write-blocked"
//   · the SOW says "summarize, draft, recommend, classify, validate"
//   · slide 25 — the *Detailed* matrix — gives the nine below, and the locked
//     `ToolPermission` enum matches its five allowed values exactly.
// `retrieve` and `classify` therefore have no home in the model. That is a
// question for the product owner, not a reason to widen the enum (ROADMAP D1).
//
// This constant is presentation, never enforcement — nothing reads it to make a
// decision. The asymmetry in `implementation` is the point of the view: the code
// is STRONGER than the deck describes for the allowed rows (an invalid
// permission is a type error, not a policy violation) and COARSER for the
// blocked ones (all four collapse into one `write_capable` boolean — the model
// records *that* a tool writes, never *which* verb).
export interface PermissionMatrixRow {
  permission: string;
  treatment: 'allowed' | 'blocked'; // machine-readable, for styling only
  treatment_text: string;           // slide 25's own words
  description: string;              // slide 25's own words
  implementation: string;           // ours — how the deck's row maps onto code
}

export const PERMISSION_MATRIX: PermissionMatrixRow[] = [
  // Note "Allowed with approved access" — slide 25 qualifies Read and nothing else.
  { permission: 'Read', treatment: 'allowed', treatment_text: 'Allowed with approved access', description: 'Retrieve approved context from a system', implementation: 'ToolPermission member — a valid permission_ceiling.' },
  { permission: 'Summarize', treatment: 'allowed', treatment_text: 'Allowed', description: 'Summarize approved context', implementation: 'ToolPermission member — a valid permission_ceiling.' },
  { permission: 'Draft', treatment: 'allowed', treatment_text: 'Allowed', description: 'Draft content for human review', implementation: 'ToolPermission member — a valid permission_ceiling.' },
  { permission: 'Recommend', treatment: 'allowed', treatment_text: 'Allowed', description: 'Recommend next steps or options', implementation: 'ToolPermission member — a valid permission_ceiling.' },
  { permission: 'Validate', treatment: 'allowed', treatment_text: 'Allowed', description: 'Check completeness, consistency, or quality', implementation: 'ToolPermission member — a valid permission_ceiling.' },
  { permission: 'Create', treatment: 'blocked', treatment_text: 'Not allowed in base scope', description: 'Create records/tickets/code changes', implementation: 'write_capable = true → bind_tool() rejects, server-side.' },
  { permission: 'Update', treatment: 'blocked', treatment_text: 'Not allowed in base scope', description: 'Modify records, code, workflows, or systems', implementation: 'write_capable = true → bind_tool() rejects, server-side.' },
  { permission: 'Approve', treatment: 'blocked', treatment_text: 'Not allowed in base scope', description: 'Approve change/release/workflow decisions', implementation: 'write_capable = true → bind_tool() rejects, server-side.' },
  { permission: 'Deploy', treatment: 'blocked', treatment_text: 'Not allowed in base scope', description: 'Trigger deployment or production action', implementation: 'write_capable = true → bind_tool() rejects, server-side.' },
];

// ---- Tier plain-language names (Section 1.4) ------------------------------
export const TIER_LABEL: Record<CapabilityTier, string> = {
  minimal: 'Simple Advisor',
  standardized: 'Knowledge Assistant',
  advanced: 'Team Coordinator',
};

export const TIER_ORDER: CapabilityTier[] = ['minimal', 'standardized', 'advanced'];
export const RISK_ORDER: RiskTier[] = ['low', 'medium', 'high', 'critical'];

// ---- Personas (Section 1.5) ----------------------------------------------
export interface PersonaMeta {
  id: Persona;
  label: string;
  short: string;
  blurb: string;
}

export const PERSONAS: Record<Persona, PersonaMeta> = {
  business_owner: {
    id: 'business_owner',
    label: 'Business Owner',
    short: 'BO',
    blurb: 'Creates agents, tracks approvals, reads cost.',
  },
  platform_engineer: {
    id: 'platform_engineer',
    label: 'Platform Engineer',
    short: 'PE',
    blurb: 'Manages tools/MCP connectors, runtime status, pipelines.',
  },
  governance_officer: {
    id: 'governance_officer',
    label: 'Governance Officer',
    short: 'GO',
    blurb: 'Works the approvals queue, risk matrix, audit log.',
  },
  team_lead: {
    id: 'team_lead',
    label: 'Team Lead / Consumer',
    short: 'TL',
    blurb: 'Browses the A2A directory, tests agents in the Playground.',
  },
};

export const PERSONA_LIST: Persona[] = [
  'business_owner',
  'platform_engineer',
  'governance_officer',
  'team_lead',
];

// Fast-path lifetime and warning window (Section 8.3 / D10).
export const FAST_PATH_DAYS = 90;
export const FAST_PATH_WARN_DAYS = 14;

// Latency p95 targets by tier (Section 7.8), in ms.
export const P95_TARGET_MS: Record<CapabilityTier, number> = {
  minimal: 2000,
  standardized: 5000,
  advanced: 15000,
};

// Fixed "today" for the deterministic demo (matches the spec's document date).
// Avoids Date.now() so two runs render identical countdowns/telemetry windows.
export const DEMO_TODAY = '2026-07-28';
