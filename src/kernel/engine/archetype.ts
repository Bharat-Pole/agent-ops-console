// Archetype selection from tier + NLU (LOCKED archetype list, Section 7.2).
import type { CapabilityTier, Archetype } from '@/types';
import type { NluResult } from './types';

export function pickArchetypeForTier(tier: CapabilityTier, nlu: NluResult): Archetype {
  if (tier === 'advanced') return 'workflow_coordinator';
  if (tier === 'minimal') return nlu.domain === 'support' ? 'faq_bot' : 'simple_advisor';
  // standardized
  if (nlu.task_type === 'analyze' || nlu.task_type === 'research') return 'research_assistant';
  if (nlu.task_type === 'summarize' && nlu.output_format === 'report') return 'report_generator';
  return 'rag_grounded_assistant';
}
