// Risk inference (Section 1.4 / 7 — risk is inferred from data sensitivity, tool
// permissions, audience scope, regulatory domain; never from capability alone).
// Ported from POC infer_risk, extended with write-floor and Phase-5 overrides.

import type { Intent, WriteDetection } from './types';
import type { RiskTier } from '@/types';
import { RISK_ORDER } from '@/kernel/constants';

const CRITICAL_CUES = ['cross-border', 'financial', 'payment', 'trading', 'hipaa', 'phi', 'regulat', 'filing', 'fcc', 'attestation'];
const HIGH_CUES = ['customer', 'pii', 'personal', 'ssn', 'salary', 'medical', 'contract', 'confidential'];

function maxRisk(a: RiskTier, b: RiskTier): RiskTier {
  return RISK_ORDER.indexOf(a) >= RISK_ORDER.indexOf(b) ? a : b;
}

export interface RiskResult {
  risk_tier: RiskTier;
  why: string;
}

export function inferRisk(intent: Intent, write: WriteDetection): RiskResult {
  const text =
    (intent.objective || '').toLowerCase() +
    ' ' +
    (intent.data_sources ?? []).join(' ').toLowerCase() +
    ' ' +
    (intent.data_sensitivity ?? '').toLowerCase() +
    ' ' +
    (intent.regulatory_domain ?? '').toLowerCase();

  let tier: RiskTier;
  let why: string;
  if (CRITICAL_CUES.some((c) => text.includes(c))) {
    tier = 'critical';
    why = 'financial / regulated / cross-border data cues';
  } else if (HIGH_CUES.some((c) => text.includes(c))) {
    tier = 'high';
    why = 'customer / PII / confidential cues';
  } else if ((intent.data_sources ?? []).length > 0) {
    tier = 'medium';
    why = 'internal data sources present';
  } else {
    tier = 'low';
    why = 'no data sources; advisory-only';
  }

  // Phase-5 explicit sensitivity override.
  const sens = (intent.data_sensitivity ?? '').toLowerCase();
  if (sens === 'restricted') tier = maxRisk(tier, 'critical');
  else if (sens === 'confidential') tier = maxRisk(tier, 'high');

  // Write intent raises the risk floor to high (Section 7.4).
  if (write.risk_floor) {
    const floored = maxRisk(tier, write.risk_floor);
    if (floored !== tier) why = `${why}; write intent detected → risk floor ${write.risk_floor}`;
    tier = floored;
  }

  return { risk_tier: tier, why };
}
