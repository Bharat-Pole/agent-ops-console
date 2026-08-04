// Seed construction helpers: signal breakdowns (exact Section 7.2 formula),
// track builders, date math (relative to the fixed DEMO_TODAY), and the
// AgentRecord assembler.

import type {
  SignalId,
  SignalBreakdown,
  TierScores,
  Track,
  TrackStep,
  TrackStatus,
  AgentConfig,
  AgentRecord,
  CapabilityTier,
  GovernancePath,
  ReviewCard,
} from '@/types';
import { WEIGHTS, BASE_MINIMAL, SIGNAL_LABEL } from '@/kernel/engine/weights';
import { DEMO_TODAY } from '@/kernel/constants';

const ALL_SIGNALS: SignalId[] = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'];

// Build a full SignalBreakdown. Keys present in `firedWhys` are the fired signals.
export function buildSignals(firedWhys: Partial<Record<SignalId, string>>): SignalBreakdown {
  const out = {} as SignalBreakdown;
  for (const id of ALL_SIGNALS) {
    const w = WEIGHTS[id];
    const fired = id in firedWhys;
    out[id] = {
      fired,
      why: firedWhys[id] ?? `no ${SIGNAL_LABEL[id].toLowerCase()} cue`,
      weight_minimal: w.minimal,
      weight_standardized: w.standardized,
      weight_advanced: w.advanced,
    };
  }
  return out;
}

// Exact Section 7.2 scoring formula (LOCKED):
//   score_minimal      = 20
//   score_standardized = S1 + S2 + S3 + S4 + S5   (standardized weights, if fired)
//   score_advanced     = S2 + S3 + S4 + S5 + S6   (advanced weights, if fired)
export function scoresFrom(b: SignalBreakdown): TierScores {
  const std = (['S1', 'S2', 'S3', 'S4', 'S5'] as SignalId[]).reduce(
    (acc, id) => acc + (b[id].fired ? WEIGHTS[id].standardized : 0),
    0,
  );
  const adv = (['S2', 'S3', 'S4', 'S5', 'S6'] as SignalId[]).reduce(
    (acc, id) => acc + (b[id].fired ? WEIGHTS[id].advanced : 0),
    0,
  );
  return { minimal: BASE_MINIMAL, standardized: std, advanced: adv };
}

// ---- Track builders -------------------------------------------------------
export function step(name: string, status: TrackStatus, at: string | null = null): TrackStep {
  return { name, status, at };
}

export function track(status: TrackStatus, steps: TrackStep[]): Track {
  return { status, steps };
}

export const RUNTIME_STEP_NAMES = [
  'Resolver profile',
  'Runtime host',
  'Model gateway',
  'MCP sidecars',
  'Telemetry sink',
];

export const CONTENT_STEP_NAMES = ['Ingest', 'Parse', 'Chunk', 'Embed', 'Index', 'Tag & Govern', 'Refresh'];

export function registryTrack(status: TrackStatus, at: string | null): Track {
  const done = status === 'ready';
  return track(status, [
    step('Schema validated', done ? 'ready' : status === 'blocked' ? 'blocked' : 'in_progress', at),
    step('Registered', done ? 'ready' : 'not_started', done ? at : null),
    step('Approvals granted', done ? 'ready' : 'in_progress', done ? at : null),
  ]);
}

export function runtimeTrack(status: TrackStatus, at: string | null): Track {
  const ready = status === 'ready';
  return track(
    status,
    RUNTIME_STEP_NAMES.map((n, idx) =>
      step(
        n,
        ready ? 'ready' : status === 'in_progress' ? (idx < 2 ? 'ready' : idx === 2 ? 'in_progress' : 'not_started') : 'not_started',
        ready ? at : status === 'in_progress' && idx < 2 ? at : null,
      ),
    ),
  );
}

export function contentTrack(status: TrackStatus, at: string | null, rag: boolean): Track {
  if (!rag) {
    // Minimal agents have no content track work — mark ready immediately.
    return track('ready', [step('No knowledge sources', 'ready', at)]);
  }
  const ready = status === 'ready';
  return track(
    status,
    CONTENT_STEP_NAMES.map((n, idx) =>
      step(
        n,
        ready ? 'ready' : status === 'in_progress' ? (idx < 4 ? 'ready' : idx === 4 ? 'in_progress' : 'not_started') : 'not_started',
        ready ? at : status === 'in_progress' && idx < 4 ? at : null,
      ),
    ),
  );
}

// ---- Date math (relative to fixed DEMO_TODAY, deterministic) ---------------
export function addDays(isoDate: string, days: number): string {
  const d = new Date(isoDate + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysFromToday(days: number): string {
  return addDays(DEMO_TODAY, days);
}

export function isoTs(date: string, hour = 9, minute = 0): string {
  return `${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00Z`;
}

// ---- AgentRecord assembler ------------------------------------------------
export interface AgentPlatformState {
  capability_tier: CapabilityTier;
  governance_path: GovernancePath;
  registry: Track;
  runtime: Track;
  content: Track;
  signal_breakdown: SignalBreakdown;
  review_card?: ReviewCard | null;
  evaluation_pack_id?: string | null;
  approval_ids?: string[];
  fast_path_expiry_date?: string | null;
  created_at: string;
  updated_at: string;
  demo_mode?: boolean;
}

export function mkReviewCard(
  p: Omit<ReviewCard, 'editable' | 'user_can_override_tier' | 'user_can_override_risk'>,
): ReviewCard {
  return { ...p, editable: true, user_can_override_tier: true, user_can_override_risk: true };
}

export function assembleAgent(config: AgentConfig, st: AgentPlatformState): AgentRecord {
  return {
    config,
    capability_tier: st.capability_tier,
    governance_path: st.governance_path,
    tracks: { registry: st.registry, runtime: st.runtime, content: st.content },
    signal_breakdown: st.signal_breakdown,
    review_card: st.review_card ?? null,
    evaluation_pack_id: st.evaluation_pack_id ?? null,
    approval_ids: st.approval_ids ?? [],
    fast_path_expiry_date: st.fast_path_expiry_date ?? null,
    created_at: st.created_at,
    updated_at: st.updated_at,
    demo_mode: st.demo_mode ?? false,
  };
}
