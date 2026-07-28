// Stage 2 — Archetype classification (Section 7.2). EXACT weights + formula +
// override rules + the documented capability floor. This is the LOCKED core the
// acceptance criteria test against.

import type { Intent, NluResult, Classification } from './types';
import type { SignalId, SignalBreakdown, TierScores, CapabilityTier } from '@/types';
import { WEIGHTS, BASE_MINIMAL } from './weights';
import { firesRetrieval } from './nlu';
import { pickArchetypeForTier } from './archetype';

const ROUTING_CUES = ['route to', 'route ', 'escalate', 'assign to', 'hand off', 'hand-off', 'notify', 'on-call', 'on call', 'page ', 'dispatch'];
const MULTI_AGENT_CUES = ['coordinator', 'orchestrat', 'team of agents', 'sub-agent', 'subagent', 'multi-agent', 'multi agent', 'pipeline of'];
const TOOL_CUES = ['tool', 'api', 'query', 'read from', 'check ', 'call ', 'connector'];

function detectSignalFlags(intent: Intent, nlu: NluResult): Record<SignalId, { fired: boolean; why: string }> {
  const text = (intent.objective || '').toLowerCase();
  const tools = intent.tools ?? [];
  const dataSources = intent.data_sources ?? [];

  const s1 = firesRetrieval(text, dataSources);
  const s2 = nlu.action_verbs.length >= 2;
  const s3 = nlu.systems.length >= 2;
  const s4 = tools.length > 0 || TOOL_CUES.some((c) => text.includes(c));
  const s5 = ROUTING_CUES.some((c) => text.includes(c));
  const s6 = MULTI_AGENT_CUES.some((c) => text.includes(c)) || (text.match(/\b(agent|bot)s?\b/g)?.length ?? 0) >= 2;

  return {
    S1: { fired: s1, why: s1 ? 'data source / retrieval language present' : 'no retrieval cue' },
    S2: { fired: s2, why: s2 ? `${nlu.action_verbs.length} distinct action verbs` : 'single skill' },
    S3: { fired: s3, why: s3 ? `${nlu.systems.length} distinct systems (${nlu.systems.join(', ')})` : 'single or no system' },
    S4: { fired: s4, why: s4 ? 'tool / API / action language' : 'no tool cue' },
    S5: { fired: s5, why: s5 ? 'routing / notify language' : 'no hand-off cue' },
    S6: { fired: s6, why: s6 ? 'explicit multi-agent language' : 'no multi-agent cue' },
  };
}

function buildBreakdown(flags: Record<SignalId, { fired: boolean; why: string }>): SignalBreakdown {
  const ids: SignalId[] = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'];
  const out = {} as SignalBreakdown;
  for (const id of ids) {
    out[id] = {
      fired: flags[id].fired,
      why: flags[id].why,
      weight_minimal: WEIGHTS[id].minimal,
      weight_standardized: WEIGHTS[id].standardized,
      weight_advanced: WEIGHTS[id].advanced,
    };
  }
  return out;
}

// Exact Section 7.2 scoring formula:
//   score_minimal      = 20
//   score_standardized = S1 + S2 + S3 + S4 + S5   (standardized weights, if fired)
//   score_advanced     = S2 + S3 + S4 + S5 + S6   (advanced weights, if fired)
export function scoreTiers(b: SignalBreakdown): TierScores {
  const std = (['S1', 'S2', 'S3', 'S4', 'S5'] as SignalId[]).reduce((a, id) => a + (b[id].fired ? WEIGHTS[id].standardized : 0), 0);
  const adv = (['S2', 'S3', 'S4', 'S5', 'S6'] as SignalId[]).reduce((a, id) => a + (b[id].fired ? WEIGHTS[id].advanced : 0), 0);
  return { minimal: BASE_MINIMAL, standardized: std, advanced: adv };
}

const TIER_INDEX: Record<CapabilityTier, number> = { minimal: 0, standardized: 1, advanced: 2 };

export function classify(intent: Intent, nlu: NluResult): Classification {
  const flags = detectSignalFlags(intent, nlu);
  const breakdown = buildBreakdown(flags);
  const scores = scoreTiers(breakdown);
  // Section 7.2 override is on tools.length only. tool_count (tools + sources) is
  // kept for the review card's informational tally.
  const toolsLen = intent.tools?.length ?? 0;
  const toolCount = toolsLen + (intent.data_sources?.length ?? 0);

  // argmax
  let winner: CapabilityTier = 'minimal';
  if (scores.advanced >= scores.standardized && scores.advanced >= scores.minimal) winner = 'advanced';
  else if (scores.standardized >= scores.minimal) winner = 'standardized';
  else winner = 'minimal';

  const reasoning: string[] = [
    `argmax(minimal=${scores.minimal}, standardized=${scores.standardized}, advanced=${scores.advanced}) → ${winner}`,
  ];

  // ---- Override rules (hard gates) ----
  let forced = false;
  if (breakdown.S6.fired) {
    winner = 'advanced';
    forced = true;
    reasoning.push('OVERRIDE: explicit multi-agent (S6>0) → force Advanced review');
  }
  if (toolsLen >= 4) {
    winner = 'advanced';
    forced = true;
    reasoning.push(`OVERRIDE: ${toolsLen} tools (≥4) → force Advanced review`);
  }
  if (!breakdown.S1.fired && !breakdown.S2.fired && !breakdown.S3.fired) {
    if (!forced) {
      winner = 'minimal';
      reasoning.push('OVERRIDE: no S1/S2/S3 → default lowest sufficient (Minimal)');
    }
  }

  // ---- Capability floor (Section 7.2): S1 fired → never below Standardized ----
  let capability_floor_note: string | null = null;
  if (breakdown.S1.fired && TIER_INDEX[winner] < TIER_INDEX.standardized && !forced) {
    winner = 'standardized';
    capability_floor_note = 'CAPABILITY FLOOR: retrieval need (S1) requires RAG, which Minimal cannot do → floored to Standardized';
    reasoning.push(capability_floor_note);
  }

  return {
    proposed_tier: winner,
    proposed_archetype: pickArchetypeForTier(winner, nlu),
    signal_breakdown: breakdown,
    scores,
    reasoning,
    capability_floor_note,
    forced,
    tool_count: toolCount,
  };
}
