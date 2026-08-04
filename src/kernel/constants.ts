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
