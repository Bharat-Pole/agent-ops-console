// Section 7.2 / Appendix F — signal weights, EXACT and LOCKED. Shared by the
// synthesis engine (M4) and seed-data breakdown construction (M2).
//
// | Signal | Weights (Min / Std / Adv) |
// | S1 Retrieval Need       | 0 / +10 / +5  |
// | S2 Multi-Skill          | 0 / +3  / +10 |
// | S3 Cross-System         | 0 / +5  / +10 |
// | S4 Tool Actions         | +5 / +5 / +5  |
// | S5 Hand-off/Routing     | 0 / +2  / +10 |
// | S6 Explicit Multi-Agent | 0 / 0   / +15 |

import type { SignalId, Archetype, CapabilityTier } from '@/types';

export interface SignalWeight {
  minimal: number;
  standardized: number;
  advanced: number;
}

export const WEIGHTS: Record<SignalId, SignalWeight> = {
  S1: { minimal: 0, standardized: 10, advanced: 5 },
  S2: { minimal: 0, standardized: 3, advanced: 10 },
  S3: { minimal: 0, standardized: 5, advanced: 10 },
  S4: { minimal: 5, standardized: 5, advanced: 5 },
  S5: { minimal: 0, standardized: 2, advanced: 10 },
  S6: { minimal: 0, standardized: 0, advanced: 15 },
};

// score_minimal = 20 (base). Section 7.2, LOCKED.
export const BASE_MINIMAL = 20;

export const SIGNAL_LABEL: Record<SignalId, string> = {
  S1: 'Retrieval Need',
  S2: 'Multi-Skill',
  S3: 'Cross-System',
  S4: 'Tool Actions',
  S5: 'Hand-off / Routing',
  S6: 'Explicit Multi-Agent',
};

// Archetype template library — LOCKED list (Section 7.2).
export const ARCHETYPES: Archetype[] = [
  'simple_advisor',
  'rag_grounded_assistant',
  'faq_bot',
  'report_generator',
  'research_assistant',
  'workflow_coordinator',
];

export const ARCHETYPE_LABEL: Record<Archetype, string> = {
  simple_advisor: 'Simple Advisor',
  rag_grounded_assistant: 'RAG-Grounded Assistant',
  faq_bot: 'FAQ Bot',
  report_generator: 'Report Generator',
  research_assistant: 'Research Assistant',
  workflow_coordinator: 'Workflow Coordinator',
};

// Default archetype by tier (used when no more specific match applies).
export const DEFAULT_ARCHETYPE: Record<CapabilityTier, Archetype> = {
  minimal: 'simple_advisor',
  standardized: 'rag_grounded_assistant',
  advanced: 'workflow_coordinator',
};
