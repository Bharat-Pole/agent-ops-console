// Kernel services (Section 6 api.* surface). Endpoint-shaped operations that
// mutate the store through the job queue. Imported and attached to `api` in api.ts.

import { ws } from './store';
import { startJob } from './jobs';
import { audit, nowIso } from './api';
import { generateEvalPack } from './engine/evalGen';
import { synthesize as runEngine } from './engine';
import type { OnboardingDraft } from './wizard';
import type {
  AgentRecord, ApprovalItem, ApprovalStep, EvalResult, EvaluationPack, PipelineRun, TrackStep, Track,
} from '@/types';
import { agentId, isLive } from '@/types';
import { governancePathFor, PATH_DEFS, FAST_PATH_DAYS, DEMO_TODAY } from './constants';
import { RUNTIME_STEP_NAMES, CONTENT_STEP_NAMES } from '@/seed/helpers';
import { latency } from './rng';

function hashStr(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '').slice(0, 32);
}

function step(name: string, status: TrackStep['status'], at: string | null = null): TrackStep {
  return { name, status, at };
}
function track(status: Track['status'], steps: TrackStep[]): Track {
  return { status, steps };
}

// ---- Build an AgentRecord from a completed draft (Phase 3 Register) ----
function buildAgentFromDraft(draft: OnboardingDraft, newId: string): { agent: AgentRecord; pack: EvaluationPack } {
  const synth = draft.synthesis!;
  const tier = draft.confirmedTier ?? synth.capability_tier;
  const risk = draft.confirmedRisk ?? synth.risk_tier;
  const path = governancePathFor(tier, risk);
  const now = nowIso();

  // clone the engine config and stamp identity/lifecycle
  const config = structuredClone(synth.config);
  config.identity.agent_id = { value: newId, value_source: 'system', verified_flag: true, confidence: 'high', gap_note: null };
  config.lifecycle.lifecycle_status = { value: 'registered', value_source: 'system', verified_flag: true, confidence: 'high', gap_note: null };
  config.lifecycle.risk_tier = { ...config.lifecycle.risk_tier, value: risk, verified_flag: true, confidence: 'high', gap_note: null };

  const rag = config.data.rag_enabled.value;
  const fastPath = path === 'fast';

  const agent: AgentRecord = {
    config,
    capability_tier: tier,
    governance_path: path,
    tracks: {
      registry: track(fastPath ? 'in_progress' : 'in_progress', [
        step('Schema validated', 'ready', now),
        step('Registered', 'ready', now),
        step('Approvals granted', fastPath ? 'in_progress' : 'in_progress', null),
      ]),
      runtime: track('not_started', RUNTIME_STEP_NAMES.map((n) => step(n, 'not_started', null))),
      content: rag ? track('not_started', CONTENT_STEP_NAMES.map((n) => step(n, 'not_started', null))) : track('ready', [step('No knowledge sources', 'ready', now)]),
    },
    signal_breakdown: synth.trace.stage2_classification.signal_breakdown,
    review_card: synth.review_card,
    evaluation_pack_id: `pack-${slugify(draft.name)}`,
    approval_ids: [],
    fast_path_expiry_date: null,
    created_at: draft.created_at,
    updated_at: now,
    demo_mode: false,
  };

  const pack = generateEvalPack(agent.evaluation_pack_id!, newId, config, tier);
  return { agent, pack };
}

// ---- Deterministic eval scoring (Section 11.3) ----
function casePasses(cat: string, agent: AgentRecord): boolean {
  const cfg = agent.config;
  const threshold = cfg.data.score_threshold.value ?? 0.75;
  const rag = cfg.data.rag_enabled.value;
  const hasSource = cfg.data.knowledge_source_refs.value.length > 0;
  switch (cat) {
    case 'grounding':
      // passes iff RAG on, a source is attached/indexed, and the threshold is sane
      return rag && hasSource && threshold <= 0.9;
    case 'safety_boundary':
      // passes iff no write-capable tool is bound (always true — advisory only)
      return true;
    default:
      return true;
  }
}

function cleanScore(agent: AgentRecord): number {
  const name = agent.config.identity.agent_name.value.toLowerCase();
  if (name.includes('contract')) return 94; // Section 11.3 story: fixed threshold → 94
  return 90 + (hashStr(agentId(agent)) % 9); // stable per-agent baseline 90–98
}

export const services = {
  // POST /v1/agents/synthesize — Phase 1 "Generate proposal" (async engine).
  synthesize(draftId: string): void {
    const store = ws();
    const draft = store.drafts.find((d) => d.id === draftId);
    if (!draft) return;
    // Advanced intents take the top of the 1.5–3.5s range.
    const looksAdvanced = /coordinat|orchestrat|team of agents/i.test(draft.intent.objective);
    const ms = looksAdvanced ? latency(2800, 3500) : latency(1500, 2800);
    startJob('synthesis', `Synthesizing “${draft.name}”`, draftId, [{ label: 'Draft generating…', ms }], () => {
      const result = runEngine(draft.intent);
      ws().patchDraft(draftId, (d) => ({
        ...d,
        synthesis: result,
        confirmedTier: result.capability_tier,
        confirmedRisk: result.risk_tier,
        updated_at: nowIso(),
      }));
    });
  },

  // POST /v1/agents/register — Phase 3.
  register(draftId: string): string | null {
    const store = ws();
    const draft = store.drafts.find((d) => d.id === draftId);
    if (!draft?.synthesis) return null;

    const tier = draft.confirmedTier ?? draft.synthesis.capability_tier;
    const risk = draft.confirmedRisk ?? draft.synthesis.risk_tier;
    const path = governancePathFor(tier, risk);
    const newId = `agt-${slugify(draft.name)}-20260728-${(hashStr(draftId) % 65536).toString(16).padStart(4, '0')}`;

    const { agent, pack } = buildAgentFromDraft(draft, newId);

    // approval items per path
    const approvalIds: string[] = [];
    const steps = PATH_DEFS[path].approvals as ApprovalStep[];
    for (const stp of steps) {
      const id = store.nextId('appr');
      approvalIds.push(id);
      const item: ApprovalItem = {
        id, agent_id: newId, step: stp, required_by_path: path, status: 'pending',
        actor_persona: null, decided_at: null, note: null, requested_at: nowIso(),
      };
      store.addApproval(item);
    }
    agent.approval_ids = approvalIds;

    store.addAgent(agent);
    store.upsertEvalPack(pack);
    store.patchDraft(draftId, (d) => ({ ...d, agent_id: newId, eval_pack_id: pack.id, phase: Math.max(d.phase, 4), maxPhaseReached: Math.max(d.maxPhaseReached, 4), updated_at: nowIso() }));
    audit('register', 'agent', newId, `Registered ${draft.name} (${tier}, ${path} path). ${approvalIds.length} approval(s) created.`);
    ws().pushToast('ok', `Registered ${draft.name}.`);

    // Fast path: auto-approve ~10s after registration (Section 8.1, simulated).
    if (path === 'fast') {
      window.setTimeout(() => services.finalizeRegistry(newId), 10000);
    }
    return newId;
  },

  // Mark the Registry track ready once approvals are satisfied (auto or manual).
  finalizeRegistry(agentIdStr: string): void {
    const store = ws();
    const pending = store.approvals.filter((a) => a.agent_id === agentIdStr && a.status === 'pending');
    if (pending.length > 0) return;
    store.patchAgent(agentIdStr, (a) => ({
      ...a,
      config: { ...a.config, lifecycle: { ...a.config.lifecycle, lifecycle_status: { ...a.config.lifecycle.lifecycle_status, value: 'approved' } } },
      tracks: { ...a.tracks, registry: track('ready', a.tracks.registry.steps.map((s) => ({ ...s, status: 'ready', at: s.at ?? nowIso() }))) },
      updated_at: nowIso(),
    }));
    audit('approve', 'agent', agentIdStr, 'All approvals satisfied → agent approved; Registry track ready.');
  },

  // Governance action — approve/reject a single item; cascades on last approval.
  decideApproval(approvalId: string, decision: 'approved' | 'rejected', note: string): void {
    const store = ws();
    const item = store.approvals.find((a) => a.id === approvalId);
    if (!item) return;
    store.patchApproval(approvalId, { status: decision, actor_persona: 'Governance Officer', decided_at: nowIso(), note });
    audit(decision === 'approved' ? 'approve' : 'reject', 'approval', approvalId, `${item.step} ${decision} for ${item.agent_id}.${note ? ' ' + note : ''}`);
    if (decision === 'approved') services.finalizeRegistry(item.agent_id);
  },

  // Phase 7 — provision runtime + content (Section 6.2 timings & sub-steps).
  provision(agentIdStr: string): void {
    const store = ws();
    const agent = store.agents.find((a) => agentId(a) === agentIdStr);
    if (!agent) return;

    // Runtime provisioning: 4–8s across named sub-steps.
    const per = () => latency(800, 1600);
    startJob(
      'runtime_provision',
      `Provisioning runtime · ${agent.config.identity.agent_name.value}`,
      agentIdStr,
      RUNTIME_STEP_NAMES.map((n, i) => ({
        label: n,
        ms: per(),
        onStep: () => {
          ws().patchAgent(agentIdStr, (a) => {
            const steps = a.tracks.runtime.steps.map((s, si) => (si <= i ? { ...s, status: 'ready' as const, at: s.at ?? nowIso() } : s));
            const status = steps.every((s) => s.status === 'ready') ? ('ready' as const) : ('in_progress' as const);
            return { ...a, tracks: { ...a.tracks, runtime: { status, steps } } };
          });
        },
      })),
      () => services.maybeGoLive(agentIdStr),
    );
    audit('provision', 'agent', agentIdStr, 'Runtime provisioning started.');

    // Content indexing (only if RAG): 6–12s across the 7 pipeline stages.
    if (agent.config.data.rag_enabled.value) {
      startJob(
        'content_index',
        `Indexing content · ${agent.config.identity.agent_name.value}`,
        agentIdStr,
        CONTENT_STEP_NAMES.map((n, i) => ({
          label: n,
          ms: latency(700, 1400),
          onStep: () => {
            ws().patchAgent(agentIdStr, (a) => {
              const steps = a.tracks.content.steps.map((s, si) => (si <= i ? { ...s, status: 'ready' as const, at: s.at ?? nowIso() } : s));
              const status = steps.every((s) => s.status === 'ready') ? ('ready' as const) : ('in_progress' as const);
              return { ...a, tracks: { ...a.tracks, content: { status, steps } } };
            });
          },
        })),
        () => services.maybeGoLive(agentIdStr),
      );
    }
  },

  // Flip to LIVE when all three tracks are ready.
  maybeGoLive(agentIdStr: string): void {
    const store = ws();
    const agent = store.agents.find((a) => agentId(a) === agentIdStr);
    if (!agent) return;
    if (isLive(agent) && agent.config.lifecycle.lifecycle_status.value !== 'live') {
      store.patchAgent(agentIdStr, (a) => ({
        ...a,
        config: { ...a.config, lifecycle: { ...a.config.lifecycle, lifecycle_status: { ...a.config.lifecycle.lifecycle_status, value: 'live' } } },
        demo_mode: false,
        updated_at: nowIso(),
      }));
      audit('go_live', 'agent', agentIdStr, 'All three tracks ready → agent is LIVE.');
      ws().pushToast('ok', `${agent.config.identity.agent_name.value} is LIVE.`);
    }
  },

  // POST /v1/evaluations/:id/run — deterministic eval runner (Section 11.3).
  runEvaluation(packId: string): void {
    const store = ws();
    const pack = store.evalPacks.find((p) => p.id === packId);
    if (!pack) return;
    const agent = store.agents.find((a) => agentId(a) === pack.agent_id);
    if (!agent) return;

    startJob('evaluation_run', `Running evaluation · ${agent.config.identity.agent_name.value}`, packId, [{ label: 'Executing cases…', ms: latency(2000, 4000) }], () => {
      const results: Record<string, EvalResult> = {};
      let failGround = 0, failSafety = 0, failOther = 0;
      for (const c of pack.cases) {
        const pass = casePasses(c.category, agent);
        results[c.test_id] = pass ? 'pass' : 'fail';
        if (!pass) { if (c.category === 'grounding') failGround++; else if (c.category === 'safety_boundary') failSafety++; else failOther++; }
      }
      const score = Math.max(0, Math.min(100, cleanScore(agent) - 6 * failGround - 15 * failSafety - 5 * failOther));
      const updated: EvaluationPack = {
        ...pack,
        cases: pack.cases.map((c) => ({ ...c, last_result: results[c.test_id] })),
        last_run: { date: nowIso().slice(0, 10), score, results },
      };
      ws().upsertEvalPack(updated);
      audit('run_evaluation', 'eval', packId, `Eval scored ${score}${failGround ? ` (${failGround} grounding fail)` : ''}.`);
      ws().pushToast(score >= 90 ? 'ok' : 'warn', `${agent.config.identity.agent_name.value} eval: ${score}/100.`);
    });
  },

  // Section 9.2 change control — "Propose change". Patches a config leaf, writes
  // an audit event, and for governance-critical fields creates a new approval
  // item (re-review). Enables the failing-eval fix story (score_threshold 0.95→0.75).
  proposeConfigChange(agentIdStr: string, groupKey: string, field: string, newValue: unknown): void {
    const store = ws();
    const GOV_CRITICAL = new Set(['risk_tier', 'tool_permission', 'sensitivity']);
    const critical = GOV_CRITICAL.has(field);
    store.patchAgent(agentIdStr, (a) => {
      const cfg = a.config as unknown as Record<string, Record<string, { value: unknown; value_source: string; verified_flag: boolean; confidence: string; gap_note: string | null }>>;
      const group = cfg[groupKey];
      if (!group || !group[field]) return a;
      const next = structuredClone(a);
      const g = (next.config as unknown as typeof cfg)[groupKey];
      g[field] = { ...g[field], value: newValue, value_source: 'user', verified_flag: !critical, confidence: critical ? 'medium' : 'high', gap_note: critical ? 'User-proposed change — pending re-review.' : null };
      return { ...next, updated_at: nowIso() };
    });
    audit('config_change', 'agent', agentIdStr, `Proposed change: ${field} → ${JSON.stringify(newValue)}.${critical ? ' Governance-critical — new approval required.' : ''}`);
    if (critical) {
      const id = store.nextId('appr');
      store.addApproval({ id, agent_id: agentIdStr, step: 'risk_officer', required_by_path: store.agents.find((a) => agentId(a) === agentIdStr)?.governance_path ?? 'standard', status: 'pending', actor_persona: null, decided_at: null, note: `Re-review: ${field} changed.`, requested_at: nowIso() });
    }
    ws().pushToast('ok', `Change applied to ${field}.`);
  },

  // Advisory-only bind guard (acceptance #3). No flow can bind a write_capable
  // tool — this guard rejects it and writes an audit event, whatever the caller.
  bindTool(agentIdStr: string, toolId: string): boolean {
    const store = ws();
    const tool = store.tools.find((t) => t.id === toolId);
    if (!tool) return false;
    if (tool.write_capable) {
      audit('bind_rejected', 'agent', agentIdStr, `Attempt to bind write-capable tool ${toolId} REJECTED — advisory-only scope enforced.`);
      ws().pushToast('err', `${toolId} is write-capable — advisory-block. Cannot be bound.`);
      return false;
    }
    const ref = `tools://${toolId}@${tool.version}`;
    store.patchAgent(agentIdStr, (a) => {
      const cur = a.config.tooling.bound_tools.value;
      if (cur.includes(ref)) return a;
      return { ...a, config: { ...a.config, tooling: { ...a.config.tooling, bound_tools: { ...a.config.tooling.bound_tools, value: [...cur, ref] } } }, updated_at: nowIso() };
    });
    store.patchTool(toolId, { used_by: [...new Set([...tool.used_by, agentIdStr])] });
    audit('bind_tool', 'agent', agentIdStr, `Bound read-only tool ${toolId} (${tool.permission_ceiling}).`);
    return true;
  },

  // Run an MCP connector healthcheck (Section 9.5). Small seeded chance of degraded.
  healthcheck(connectorId: string): void {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;
    startJob('healthcheck', `Healthcheck · ${conn.name}`, connectorId, [{ label: 'Probing endpoint…', ms: latency(600, 1400) }], () => {
      if (conn.status === 'offline') { ws().pushToast('warn', `${conn.name} is offline.`); return; }
      const degraded = latency(0, 100) < 18; // ~18% seeded chance
      const status = degraded ? 'degraded' : 'connected';
      ws().patchConnector(connectorId, { status, last_healthcheck: nowIso() });
      audit('healthcheck', 'connector', connectorId, `Healthcheck → ${status}.`);
      ws().pushToast(degraded ? 'warn' : 'ok', `${conn.name}: ${status}.`);
    });
  },

  // Demo lever — toggle a connector offline/connected (Section 9.5 / Section 10 #1).
  toggleConnectorOffline(connectorId: string): void {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;
    const status = conn.status === 'offline' ? 'connected' : 'offline';
    store.patchConnector(connectorId, { status, last_healthcheck: nowIso() });
    audit('toggle_connector', 'connector', connectorId, `Connector set ${status}.${status === 'offline' ? ' Pre-Flight hard blocker #4 now red.' : ''}`);
    ws().pushToast(status === 'offline' ? 'warn' : 'ok', `${conn.name} ${status}.`);
  },

  // Section 6.5 — Demo Mode for an agent whose Content track is not ready.
  enableDemoMode(agentIdStr: string): void {
    const store = ws();
    store.patchAgent(agentIdStr, (a) => ({ ...a, demo_mode: true, updated_at: nowIso() }));
    audit('demo_mode', 'agent', agentIdStr, 'Demo Mode enabled — attached vector://alloydb-demo; responding with synthetic data.');
    ws().pushToast('info', 'Demo Mode enabled.');
  },

  // Fast-path re-certification (Section 8.3 / D10). Extends expiry 90 days.
  recertify(agentIdStr: string): void {
    const store = ws();
    const agent = store.agents.find((a) => agentId(a) === agentIdStr);
    if (!agent) return;
    const base = new Date(DEMO_TODAY + 'T00:00:00Z');
    base.setUTCDate(base.getUTCDate() + FAST_PATH_DAYS);
    const newExpiry = base.toISOString().slice(0, 10);
    store.patchAgent(agentIdStr, (a) => ({ ...a, fast_path_expiry_date: newExpiry, updated_at: nowIso() }));
    audit('recertify', 'agent', agentIdStr, `Fast-path re-certified; expiry extended to ${newExpiry}.`);
    ws().pushToast('ok', `${agent.config.identity.agent_name.value} re-certified (+${FAST_PATH_DAYS} days).`);
  },

  // Suspend / retire (Section 9.2 — Governance Officer actions).
  setLifecycle(agentIdStr: string, status: 'suspended' | 'retired' | 'live'): void {
    const store = ws();
    store.patchAgent(agentIdStr, (a) => ({
      ...a,
      config: { ...a.config, lifecycle: { ...a.config.lifecycle, lifecycle_status: { ...a.config.lifecycle.lifecycle_status, value: status } } },
      updated_at: nowIso(),
    }));
    audit(status === 'live' ? 'resume' : status, 'agent', agentIdStr, `Lifecycle set to ${status}.`);
    ws().pushToast('info', `Agent ${status}.`);
  },

  // POST /v1/knowledge/:id/refresh — manual pipeline run (Section 9.6, M6 uses this).
  triggerPipeline(sourceId: string): void {
    const store = ws();
    const source = store.sources.find((s) => s.id === sourceId);
    if (!source) return;
    const runId = store.nextId('run');
    const run: PipelineRun = {
      id: runId, source_id: sourceId, trigger: 'manual', overall: 'in_progress', started_at: nowIso(),
      stages: CONTENT_STEP_NAMES.map((n) => ({ name: n as PipelineRun['stages'][number]['name'], status: 'not_started', started_at: null, duration_s: null, items: null })),
    };
    store.addPipelineRun(run);
    startJob(
      'content_index',
      `Pipeline refresh · ${source.name}`,
      sourceId,
      CONTENT_STEP_NAMES.map((n, i) => ({
        label: n,
        ms: latency(600, 1200),
        onStep: () => {
          ws().patchPipelineRun(runId, (r) => ({
            ...r,
            stages: r.stages.map((s, si) => (si <= i ? { ...s, status: 'ready', started_at: s.started_at ?? nowIso(), duration_s: 10, items: source.document_count } : s)),
            overall: i === CONTENT_STEP_NAMES.length - 1 ? 'ready' : 'in_progress',
          }));
        },
      })),
      () => {
        // any live agent consuming this source has its Content track brought to ready
        ws().agents.forEach((a) => {
          if (a.config.data.knowledge_source_refs.value.some((r) => r.includes(sourceId))) {
            ws().patchAgent(agentId(a), (ag) => ({
              ...ag,
              demo_mode: false,
              tracks: { ...ag.tracks, content: track('ready', ag.tracks.content.steps.map((s) => ({ ...s, status: 'ready', at: s.at ?? nowIso() }))) },
            }));
            services.maybeGoLive(agentId(a));
          }
        });
        audit('pipeline_refresh', 'source', sourceId, `Manual re-index completed for ${source.name}.`);
        ws().pushToast('ok', `${source.name} re-indexed.`);
      },
    );
    audit('pipeline_refresh', 'source', sourceId, `Manual re-index started for ${source.name}.`);
  },
};
