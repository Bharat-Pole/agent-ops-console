import type { PolicyRule, GovernanceException } from '@/types';
import { GOVERNANCE_MATRIX, PATH_DEFS, TIER_ORDER, RISK_ORDER } from '@/kernel/constants';

// Initial in-memory values only — real hydration (GET /v1/bootstrap) overwrites
// these with the live policy_rules/path_definitions/governance_exceptions
// tables the instant the app loads, same pattern as tools/connectors/models.
// Flattened from the same GOVERNANCE_MATRIX the onboarding synthesis engine's
// preview still reads, so there's no drift before the first hydration.
export const SEED_POLICY_RULES: PolicyRule[] = TIER_ORDER.flatMap((tier) =>
  RISK_ORDER.map((risk) => ({
    capability_tier: tier,
    risk_tier: risk,
    governance_path: GOVERNANCE_MATRIX[tier][risk],
  })),
);

export const SEED_PATH_DEFINITIONS = Object.values(PATH_DEFS);

// Real register — genuinely starts empty, not a fabricated example.
export const SEED_GOVERNANCE_EXCEPTIONS: GovernanceException[] = [];
