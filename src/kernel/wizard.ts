// Onboarding wizard draft model (Section 9.3). A draft holds the intent, the
// engine's synthesis output, the accumulated per-phase state, and (after Phase 3)
// the created agent id. Drafts live in the store so /onboarding/:draftId/phase/:n
// resumes them.

import type { CapabilityTier, RiskTier } from '@/types';
import type { Intent, SynthesisResult } from './engine/types';

export interface WorkPackage {
  inScope: string[];
  outScope: string[];
  dor: Record<string, boolean>; // Definition of Ready (hard stops for Next)
  dod: Record<string, boolean>; // Definition of Done
}

export interface OnboardingDraft {
  id: string;
  name: string;
  intent: Intent;
  phase: number; // current phase 1..7
  maxPhaseReached: number;
  synthesis: SynthesisResult | null;
  confirmedTier: CapabilityTier | null;
  confirmedRisk: RiskTier | null;
  workPackage: WorkPackage;
  elicitationAnswers: Record<string, string>;
  governance: { sensitivity: string; regulatory: string };
  agent_id: string | null; // set after Register (Phase 3)
  eval_pack_id: string | null;
  created_at: string;
  updated_at: string;
}

// Section 9.3 Phase 2 — DoR items are hard stops; DoD items track completion.
export const DOR_ITEMS: { key: string; label: string }[] = [
  { key: 'objective_measurable', label: 'Objective is specific and measurable' },
  { key: 'sources_approved', label: 'Data sources identified and approved' },
  { key: 'eval_cases_drafted', label: 'Evaluation cases drafted' },
];

export const DOD_ITEMS: { key: string; label: string }[] = [
  { key: 'grounding_pass', label: 'Grounding & correctness eval passes' },
  { key: 'advisory_confirmed', label: 'Advisory-only scope confirmed (no write tools bound)' },
  { key: 'latency_target', label: 'Latency target met for tier' },
];

export function emptyWorkPackage(): WorkPackage {
  return {
    inScope: [],
    outScope: [],
    dor: Object.fromEntries(DOR_ITEMS.map((i) => [i.key, false])),
    dod: Object.fromEntries(DOD_ITEMS.map((i) => [i.key, false])),
  };
}

export function newDraft(id: string, now: string, intent?: Partial<Intent>): OnboardingDraft {
  return {
    id,
    name: intent?.agent_name || 'Untitled agent',
    intent: {
      objective: intent?.objective ?? '',
      intended_audience: intent?.intended_audience,
      data_sources: intent?.data_sources ?? [],
      tools: intent?.tools ?? [],
      business_owner: intent?.business_owner,
      technical_owner: intent?.technical_owner,
      agent_name: intent?.agent_name,
    },
    phase: 1,
    maxPhaseReached: 1,
    synthesis: null,
    confirmedTier: null,
    confirmedRisk: null,
    workPackage: emptyWorkPackage(),
    elicitationAnswers: {},
    governance: { sensitivity: '', regulatory: '' },
    agent_id: null,
    eval_pack_id: null,
    created_at: now,
    updated_at: now,
  };
}
