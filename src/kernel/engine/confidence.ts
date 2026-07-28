// Stage 4 — Confidence & provenance (Section 7.5, LOCKED rules).
// user_provided→high · system_default→high · engine_inferred (tier, orchestration,
// risk)→medium · engine_generated (sub_agents, chunk_size, 5.12)→low ·
// governance-critical fields (risk_tier, tool_permission, sensitivity) never high
// until user-confirmed. Any field with confidence != high ∧ governance_critical
// goes on the review card's ⚠️ list.

import type { Classification, WriteDetection, ConfidenceResult } from './types';
import type { RiskTier, CapabilityTier, FieldConfirmation } from '@/types';

export function assessConfidence(
  cls: Classification,
  write: WriteDetection,
  risk: RiskTier,
  tier: CapabilityTier,
): ConfidenceResult {
  const out: FieldConfirmation[] = [];

  // Governance-critical: risk_tier (inferred, must be confirmed)
  out.push({
    field: 'risk_tier',
    proposed_value: risk,
    confidence: 'medium',
    gap_note: 'Inferred from objective — confirm data sensitivity.',
    governance_critical: true,
  });

  if (tier !== 'minimal') {
    // Governance-critical: sensitivity of the knowledge source
    out.push({
      field: 'sensitivity',
      proposed_value: risk === 'critical' ? 'restricted' : risk === 'high' ? 'confidential' : 'internal',
      confidence: 'medium',
      gap_note: 'Auto-inferred sensitivity. Confirm with data owner.',
      governance_critical: true,
    });
    // Engine-generated low-confidence RAG params
    out.push({
      field: 'chunk_size',
      proposed_value: 512,
      confidence: 'low',
      gap_note: 'Auto-generated default. Confirm with data owner.',
      governance_critical: false,
    });
  }

  if (tier === 'advanced') {
    out.push({
      field: 'sub_agents',
      proposed_value: `${cls.proposed_tier === 'advanced' ? 'decomposed' : ''} sub-agents`,
      confidence: 'low',
      gap_note: 'Auto-decomposed from objective. Confirm ownership and prompts.',
      governance_critical: false,
    });
  }

  if (write.flagged_tools.length > 0) {
    out.push({
      field: 'bound_tools',
      proposed_value: `${write.flagged_tools.length} write-capable tool(s) FLAGGED: ${write.flagged_tools.join(', ')}`,
      confidence: 'low',
      gap_note: 'Write-capable tools detected. NOT bound. Advisory-only scope enforced — human decision required.',
      governance_critical: false,
    });
  }

  return { fields_requiring_confirmation: out };
}
