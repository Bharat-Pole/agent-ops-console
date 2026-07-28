// Section 9.9 — seeded telemetry generator. For each non-draft agent, generate
// 30 days of {requests, tokens_in, tokens_out, p95_ms, errors} from the seeded
// PRNG, shaped by tier (Advanced ≈ 3× tokens of Minimal) with weekly seasonality
// + one seeded incident spike (the Incident Coordinator has a bad day on day 22).
// Deterministic: same seed → identical charts (acceptance #10).

import type { AgentRecord, AgentTelemetry, TelemetryPoint, CapabilityTier } from '@/types';
import { agentId } from '@/types';
import { Rng, FIXED_SEED } from './rng';
import { DEMO_TODAY } from './constants';
import { addDays } from '@/seed/helpers';

const WINDOW_DAYS = 30;

interface TierShape {
  requests: number;
  tokens_in: number;
  tokens_out: number;
  p95: number;
  errorRate: number;
}

const TIER_SHAPE: Record<CapabilityTier, TierShape> = {
  minimal: { requests: 140, tokens_in: 420, tokens_out: 260, p95: 1200, errorRate: 0.004 },
  standardized: { requests: 760, tokens_in: 1500, tokens_out: 900, p95: 3400, errorRate: 0.008 },
  advanced: { requests: 320, tokens_in: 4200, tokens_out: 2600, p95: 11000, errorRate: 0.012 },
};

// Per-agent traffic multipliers to make the stories legible.
const TRAFFIC_HINT: Record<string, number> = {
  'network-capacity-research': 1.1,
};

function hashStr(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function trafficMultiplier(a: AgentRecord): number {
  const name = a.config.identity.agent_name.value.toLowerCase();
  if (name.includes('noc incident')) return 2.6; // highest traffic
  if (name.includes('faq')) return 0.28; // near-zero cost row
  for (const [k, m] of Object.entries(TRAFFIC_HINT)) if (agentId(a).includes(k)) return m;
  return 1;
}

function genForAgent(a: AgentRecord, packScore: number | null): AgentTelemetry {
  const rng = new Rng(FIXED_SEED ^ hashStr(agentId(a)));
  const shape = TIER_SHAPE[a.capability_tier];
  const mult = trafficMultiplier(a);
  const isIncidentCoordinator = a.config.identity.agent_name.value.toLowerCase().includes('coordinator') &&
    a.config.identity.agent_name.value.toLowerCase().includes('incident');

  const series: TelemetryPoint[] = [];
  for (let i = 0; i < WINDOW_DAYS; i++) {
    const day = addDays(DEMO_TODAY, -(WINDOW_DAYS - 1 - i));
    const dow = new Date(day + 'T00:00:00Z').getUTCDay();
    const weekend = dow === 0 || dow === 6;
    const seasonal = weekend ? 0.55 : 1 + (rng.float() - 0.5) * 0.18;

    // one seeded incident spike on day index 22 for the Incident Coordinator
    const spike = isIncidentCoordinator && i === 22 ? 1 : 0;

    const requests = Math.max(1, Math.round(shape.requests * mult * seasonal * (1 + spike * 1.8)));
    const tin = Math.round(shape.tokens_in * requests * (0.9 + rng.float() * 0.2));
    const tout = Math.round(shape.tokens_out * requests * (0.9 + rng.float() * 0.2));
    const p95 = Math.round(shape.p95 * (0.85 + rng.float() * 0.3) * (1 + spike * 1.5));
    const errors = Math.round(requests * shape.errorRate * (1 + spike * 9) * (0.5 + rng.float()));

    series.push({ day, requests, tokens_in: tin, tokens_out: tout, p95_ms: p95, errors });
  }

  // Eval-score history trending toward the pack's last score.
  const eval_score_history: { date: string; score: number }[] = [];
  const finalScore = packScore ?? 90;
  for (let k = 0; k < 6; k++) {
    const date = addDays(DEMO_TODAY, -((5 - k) * 5));
    const drift = (rng.float() - 0.5) * 6;
    const score = k === 5 ? finalScore : Math.round(Math.min(99, Math.max(60, finalScore - (5 - k) * 1.5 + drift)));
    eval_score_history.push({ date, score });
  }

  return { agent_id: agentId(a), series, eval_score_history };
}

export function generateTelemetry(
  agents: AgentRecord[],
  packScoreByAgent: Record<string, number | null>,
): AgentTelemetry[] {
  return agents
    .filter((a) => a.config.lifecycle.lifecycle_status.value !== 'draft')
    .map((a) => genForAgent(a, packScoreByAgent[agentId(a)] ?? null));
}
