// Stage 5 — Targeted elicitation (Section 7.6). A question qualifies only if its
// answer changes (a) tier, (b) risk tier, or (c) a low-confidence field. Rank by
// priority = 0.4*architecture_impact + 0.3*risk_impact + 0.2*confidence_gap +
// 0.1*user_burden_penalty. MAX 3 questions shown; the rest become optional.

import type { Intent, NluResult, Classification, WriteDetection, Elicitation, ElicitationQuestion } from './types';
import type { RiskTier } from '@/types';

function priority(a: number, r: number, c: number, burden: number): number {
  return 0.4 * a + 0.3 * r + 0.2 * c + 0.1 * (1 - burden);
}

export function elicit(
  intent: Intent,
  nlu: NluResult,
  cls: Classification,
  write: WriteDetection,
  _risk: RiskTier,
): Elicitation {
  const q: ElicitationQuestion[] = [];

  // Risk-changing: data sensitivity of a named source
  if ((intent.data_sources ?? []).length > 0 && !intent.data_sensitivity) {
    const src = intent.data_sources![0];
    q.push({
      id: 'q_sensitivity',
      question: `Does ${src} contain customer personal information (PII) or regulated data?`,
      kind: 'risk',
      priority: priority(0.3, 1, 0.8, 0.2),
      options: ['No — internal only', 'Yes — customer PII', 'Yes — regulated / cross-border'],
      affects: 'risk_tier',
    });
  }

  // Risk-changing: confirm write-intent handling
  if (write.flagged_tools.length > 0 || write.write_intents.length > 0) {
    q.push({
      id: 'q_write',
      question: 'This agent mentions actions like send/notify/update. Confirm it should remain advisory-only (draft, never send)?',
      kind: 'risk',
      priority: priority(0.5, 0.8, 0.6, 0.3),
      options: ['Yes — advisory only (recommended)', 'No — needs write actions (requires exception)'],
      affects: 'tool_permission / risk_tier',
    });
  }

  // Tier-changing: ambiguous multi-skill vs single
  if (cls.proposed_tier === 'standardized' && nlu.action_verbs.length >= 2 && !cls.forced) {
    q.push({
      id: 'q_multiskill',
      question: `Do these steps (${nlu.action_verbs.slice(0, 3).join(', ')}) run as one flow, or must they be coordinated across separate specialists?`,
      kind: 'tier',
      priority: priority(0.9, 0.2, 0.4, 0.4),
      options: ['One flow (Standardized)', 'Coordinated specialists (Advanced)'],
      affects: 'capability_tier',
    });
  }

  // Confidence-gap: audience unknown
  if (!intent.intended_audience && nlu.gaps.includes('intended_audience')) {
    q.push({
      id: 'q_audience',
      question: 'Who is the primary audience for this agent?',
      kind: 'confidence',
      priority: priority(0.2, 0.2, 0.9, 0.5),
      options: ['Internal team', 'All employees', 'External / customers'],
      affects: 'intended_audience',
    });
  }

  // Confidence-gap: refresh cadence of the knowledge source
  if ((intent.data_sources ?? []).length > 0) {
    q.push({
      id: 'q_refresh',
      question: 'How often does the underlying data change (drives refresh cadence)?',
      kind: 'confidence',
      priority: priority(0.1, 0.2, 0.7, 0.6),
      options: ['Daily', 'Weekly', 'Monthly', 'Rarely / manual'],
      affects: 'refresh_cadence',
    });
  }

  q.sort((a, b) => b.priority - a.priority);
  return { questions: q.slice(0, 3), optional: q.slice(3) };
}
