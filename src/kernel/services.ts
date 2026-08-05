// Kernel services (Section 6 api.* surface). Endpoint-shaped operations,
// attached to `api` in api.ts.
//
// Phase 1 (persistence) moved agent registration, approvals, tool binding,
// lifecycle changes, and config-change proposals to real backend endpoints
// (see /server) — those functions below are now thin `fetch()` wrappers that
// patch the server's response into the store via the existing mutators.
// Provisioning, evaluation runs, and pipeline refreshes stay client-simulated
// this round (see plan §0 "Stay client-only, unchanged") — their job-step
// callbacks additionally sync the resulting tracks/demo_mode back to the
// server with a best-effort PATCH so a refresh doesn't regress a LIVE agent.

import { ws } from './store';
import { startJob } from './jobs';
import { audit, nowIso } from './api';
import { synthesize as runEngine } from './engine';
import { generatePlaygroundResponse, resolvePromptRef, type MessageKind, type PlaygroundResponse, type RetrievalChunk } from './playground';
import type {
  AgentRecord, EvalResult, EvaluationPack, PipelineRun, ToolAsset,
} from '@/types';
import { agentId, isLive } from '@/types';
import { governancePathFor, FAST_PATH_DAYS } from './constants';
import { PERSONAS } from './constants';
import { RUNTIME_STEP_NAMES, CONTENT_STEP_NAMES } from '@/seed/helpers';
import { latency } from './rng';

function hashStr(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function track(status: 'not_started' | 'in_progress' | 'ready' | 'blocked', steps: AgentRecord['tracks']['runtime']['steps']) {
  return { status, steps };
}

async function postJson<T>(path: string, body: unknown): Promise<{ ok: boolean; status: number; data: T | null }> {
  try {
    const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: null };
  }
}

// Best-effort sync of an agent's current tracks/config/demo_mode to the
// server, called after the client-simulated provisioning/pipeline jobs mutate
// local state. Fire-and-forget — the local simulation stays the source of
// truth for animation timing; this just keeps the DB from going stale.
function syncAgentToServer(agentIdStr: string): void {
  const a = ws().agents.find((x) => agentId(x) === agentIdStr);
  if (!a) return;
  fetch(`/v1/agents/${encodeURIComponent(agentIdStr)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config: a.config, tracks: a.tracks, demo_mode: a.demo_mode }),
  }).catch(() => {});
}

// ---- Deterministic eval scoring (Section 11.3) — unchanged, still simulated ----
function casePasses(cat: string, agent: AgentRecord): boolean {
  const cfg = agent.config;
  const threshold = cfg.data.score_threshold.value ?? 0.75;
  const rag = cfg.data.rag_enabled.value;
  const hasSource = cfg.data.knowledge_source_refs.value.length > 0;
  switch (cat) {
    case 'grounding':
      return rag && hasSource && threshold <= 0.9;
    case 'safety_boundary':
      return true;
    default:
      return true;
  }
}

function cleanScore(agent: AgentRecord): number {
  const name = agent.config.identity.agent_name.value.toLowerCase();
  if (name.includes('contract')) return 94;
  return 90 + (hashStr(agentId(agent)) % 9);
}

export const services = {
  // POST /v1/agents/synthesize — Phase 1 "Generate proposal" (async engine).
  // Unchanged: the deterministic synthesis engine stays client-side this round.
  synthesize(draftId: string): void {
    const store = ws();
    const draft = store.drafts.find((d) => d.id === draftId);
    if (!draft) return;
    const looksAdvanced = /coordinat|orchestrat|team of agents/i.test(draft.intent.objective);
    const ms = looksAdvanced ? latency(2800, 3500) : latency(1500, 2800);
    startJob('synthesis', `Synthesizing "${draft.name}"`, draftId, [{ label: 'Draft generating…', ms }], () => {
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

  // POST /v1/agents/register — Phase 3. Server-persisted; real IDs/dates.
  async register(draftId: string): Promise<string | null> {
    const store = ws();
    const draft = store.drafts.find((d) => d.id === draftId);
    if (!draft?.synthesis) return null;

    const tier = draft.confirmedTier ?? draft.synthesis.capability_tier;
    const risk = draft.confirmedRisk ?? draft.synthesis.risk_tier;
    const path = governancePathFor(tier, risk);

    const { ok, data } = await postJson<{ agent: AgentRecord; pack: EvaluationPack; approvals: import('@/types').ApprovalItem[]; auditEvent: import('@/types').AuditEvent }>(
      '/v1/agents/register',
      {
        name: draft.name,
        createdAt: draft.created_at,
        synthesis: {
          config: draft.synthesis.config,
          capability_tier: draft.synthesis.capability_tier,
          risk_tier: draft.synthesis.risk_tier,
          review_card: draft.synthesis.review_card,
          signal_breakdown: draft.synthesis.trace.stage2_classification.signal_breakdown,
        },
        confirmedTier: draft.confirmedTier,
        confirmedRisk: draft.confirmedRisk,
        actorPersona: PERSONAS[store.ui.persona].label,
      },
    );

    if (!ok || !data) {
      store.pushToast('err', 'Could not reach the server — registration failed.');
      return null;
    }

    store.addAgent(data.agent);
    store.upsertEvalPack(data.pack);
    for (const a of data.approvals) store.addApproval(a);
    store.addAuditEvent(data.auditEvent);
    const newId = agentId(data.agent);
    store.patchDraft(draftId, (d) => ({ ...d, agent_id: newId, eval_pack_id: data.pack.id, phase: Math.max(d.phase, 4), maxPhaseReached: Math.max(d.maxPhaseReached, 4), updated_at: nowIso() }));
    store.pushToast('ok', `Registered ${draft.name}.`);

    // Fast path auto-approves ~10s later via the server's scheduled_jobs
    // poller (survives a restart, unlike the old client-only setTimeout).
    // Re-hydrate once it's done so the UI reflects it without a manual refresh.
    if (path === 'fast') {
      window.setTimeout(() => { void services.bootstrapWorkspace(); }, 11000);
    }
    return newId;
  },

  // GET /v1/bootstrap — hydrates agents/approvals/auditLog/evalPacks from the
  // server. Called once on app load, and again after fast-path auto-approval.
  async bootstrapWorkspace(): Promise<void> {
    try {
      const res = await fetch('/v1/bootstrap');
      if (!res.ok) return;
      const data = await res.json();
      ws().hydrateFromServer(data);
    } catch {
      // Server unreachable — the client keeps its local seed data.
    }
  },

  // Governance action — approve/reject a single item; cascades on last approval.
  async decideApproval(approvalId: string, decision: 'approved' | 'rejected', note: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ approval: import('@/types').ApprovalItem; agent: AgentRecord | null; auditEvent: import('@/types').AuditEvent }>(
      `/v1/approvals/${encodeURIComponent(approvalId)}/decide`,
      { decision, note, actorPersona: PERSONAS[store.ui.persona].label },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — decision failed.'); return; }
    store.patchApproval(data.approval.id, data.approval);
    if (data.agent) store.patchAgent(agentId(data.agent), () => data.agent!);
    store.addAuditEvent(data.auditEvent);
  },

  // Phase 7 — provision runtime + content (Section 6.2 timings & sub-steps).
  // Unchanged simulation; each step additionally syncs tracks to the server.
  provision(agentIdStr: string): void {
    const store = ws();
    const agent = store.agents.find((a) => agentId(a) === agentIdStr);
    if (!agent) return;

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
          syncAgentToServer(agentIdStr);
        },
      })),
      () => services.maybeGoLive(agentIdStr),
    );
    audit('provision', 'agent', agentIdStr, 'Runtime provisioning started.');

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
            syncAgentToServer(agentIdStr);
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
      syncAgentToServer(agentIdStr);
    }
  },

  // POST /v1/evaluations/:id/run — deterministic eval runner (Section 11.3).
  // Unchanged this round — real LLM-graded evaluation is a later phase.
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

  // Section 9.2 change control — "Propose change". Server-persisted.
  async proposeConfigChange(agentIdStr: string, groupKey: string, field: string, newValue: unknown): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ agent: AgentRecord; approval: import('@/types').ApprovalItem | null; auditEvent: import('@/types').AuditEvent }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/config-change`,
      { groupKey, field, newValue },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — change failed.'); return; }
    store.patchAgent(agentIdStr, () => data.agent);
    if (data.approval) store.addApproval(data.approval);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `Change applied to ${field}.`);
  },

  // Advisory-only bind guard (acceptance #3), enforced server-side — the
  // server's own `tools` table is the trust boundary, not anything the client claims.
  async bindTool(agentIdStr: string, toolId: string): Promise<boolean> {
    const store = ws();
    const { ok, data } = await postJson<{ ok: boolean; agent?: AgentRecord; tool?: { used_by: string[] }; auditEvent?: import('@/types').AuditEvent; message?: string }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/tools/bind`,
      { toolId },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — bind failed.'); return false; }
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    if (!data.ok) { store.pushToast('err', data.message ?? `${toolId} cannot be bound.`); return false; }
    if (data.agent) store.patchAgent(agentIdStr, () => data.agent!);
    if (data.tool) store.patchTool(toolId, { used_by: data.tool.used_by });
    return true;
  },

  // Sensitivity-gated bind guard — mirrors bindTool above, but a confidential/
  // restricted source doesn't hard-reject: it creates a pending risk-officer
  // approval instead, resolved server-side by the same approvals queue used
  // for critical config-field changes.
  async bindKnowledgeSource(agentIdStr: string, sourceId: string): Promise<boolean> {
    const store = ws();
    const { ok, data } = await postJson<{
      ok: boolean;
      pending?: boolean;
      agent?: AgentRecord;
      source?: import('@/types').RealKnowledgeSource;
      approval?: import('@/types').ApprovalItem;
      auditEvent?: import('@/types').AuditEvent;
      message?: string;
    }>(`/v1/agents/${encodeURIComponent(agentIdStr)}/knowledge/bind`, { sourceId });
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — bind failed.'); return false; }
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    if (data.pending) {
      if (data.approval) store.addApproval(data.approval);
      store.pushToast('warn', data.message ?? 'Pending risk-officer approval.');
      return false;
    }
    if (!data.ok) { store.pushToast('err', data.message ?? `${sourceId} cannot be bound.`); return false; }
    if (data.agent) store.patchAgent(agentIdStr, () => data.agent!);
    if (data.source) store.upsertRealSource(data.source);
    store.pushToast('ok', `${data.source?.name ?? sourceId} bound.`);
    return true;
  },

  // POST /v1/agents/:id/chat — Phase 2. The deterministic parts (kind,
  // retrieval, citations, toolCalls, routing, shapedBy, canned text for
  // refusal/tool_call) are computed locally via generatePlaygroundResponse
  // (needs sources/tools, which are client-side only). For grounded_answer/
  // general_answer, the canned text is replaced with a real Claude response;
  // if the server is unreachable or has no API key configured, the canned
  // text stays as a graceful fallback.
  async chatWithAgent(agentIdStr: string, message: string, turns: { role: 'user' | 'agent'; text: string }[], tools: ToolAsset[]): Promise<PlaygroundResponse> {
    const store = ws();
    const agent = store.agents.find((a) => agentId(a) === agentIdStr);
    if (!agent) throw new Error('Agent not found.');

    const base = generatePlaygroundResponse(agent, tools, message);
    if (base.kind !== 'grounded_answer' && base.kind !== 'general_answer') {
      // refusal / tool_call — no LLM needed, matches the server's own rule.
      return base;
    }

    const sysBody = resolvePromptRef(agent.config.prompt.system_prompt_ref.value, store.prompts);
    const citeBody = resolvePromptRef(agent.config.prompt.citation_rules.value, store.prompts);
    const { ok, data } = await postJson<{ kind: MessageKind; text: string; citations: string[]; retrieval: RetrievalChunk[]; tokenCount: number; model: string | null }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/chat`,
      { message, history: turns, resolvedSystemPromptBody: sysBody, resolvedCitationRulesBody: citeBody },
    );

    if (!ok || !data) return base; // server unreachable — fall back to the placeholder text.

    if (data.kind === 'refusal') {
      // The server's independent write-intent re-check overrode the client's classification.
      return { ...base, kind: 'refusal', citations: [], retrieval: [], toolCalls: [], text: data.text, tokenCount: 0, shapedBy: ['tool_permission=read (advisory-only)', 'safety_instructions', 'server-side re-check'] };
    }
    // Real retrieval/citations/kind from the server replace the placeholder —
    // this is what makes the Inspector panel show what was actually sent to Claude.
    return { ...base, kind: data.kind, citations: data.citations, retrieval: data.retrieval, text: data.text, tokenCount: data.tokenCount || base.tokenCount, shapedBy: [...base.shapedBy, data.model ? `model=${data.model}` : 'model=unavailable (fallback text)'] };
  },

  // Run an MCP connector healthcheck (Section 9.5). Unchanged — client-simulated.
  healthcheck(connectorId: string): void {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;
    startJob('healthcheck', `Healthcheck · ${conn.name}`, connectorId, [{ label: 'Probing endpoint…', ms: latency(600, 1400) }], () => {
      if (conn.status === 'offline') { ws().pushToast('warn', `${conn.name} is offline.`); return; }
      const degraded = latency(0, 100) < 18;
      const status = degraded ? 'degraded' : 'connected';
      ws().patchConnector(connectorId, { status, last_healthcheck: nowIso() });
      audit('healthcheck', 'connector', connectorId, `Healthcheck → ${status}.`);
      ws().pushToast(degraded ? 'warn' : 'ok', `${conn.name}: ${status}.`);
    });
  },

  // Demo lever — toggle a connector offline/connected. Unchanged.
  toggleConnectorOffline(connectorId: string): void {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;
    const status = conn.status === 'offline' ? 'connected' : 'offline';
    store.patchConnector(connectorId, { status, last_healthcheck: nowIso() });
    audit('toggle_connector', 'connector', connectorId, `Connector set ${status}.${status === 'offline' ? ' Pre-Flight hard blocker #4 now red.' : ''}`);
    ws().pushToast(status === 'offline' ? 'warn' : 'ok', `${conn.name} ${status}.`);
  },

  // Section 6.5 — Demo Mode for an agent whose Content track is not ready. Server-persisted.
  async enableDemoMode(agentIdStr: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ agent: AgentRecord; auditEvent: import('@/types').AuditEvent }>(`/v1/agents/${encodeURIComponent(agentIdStr)}/demo-mode`, {});
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server.'); return; }
    store.patchAgent(agentIdStr, () => data.agent);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('info', 'Demo Mode enabled.');
  },

  // Fast-path re-certification (Section 8.3 / D10). Server-persisted, real dates.
  async recertify(agentIdStr: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ agent: AgentRecord; auditEvent: import('@/types').AuditEvent }>(`/v1/agents/${encodeURIComponent(agentIdStr)}/recertify`, {});
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server.'); return; }
    store.patchAgent(agentIdStr, () => data.agent);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${data.agent.config.identity.agent_name.value} re-certified (+${FAST_PATH_DAYS} days).`);
  },

  // Suspend / retire (Section 9.2 — Governance Officer actions). Server-persisted.
  async setLifecycle(agentIdStr: string, status: 'suspended' | 'retired' | 'live'): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ agent: AgentRecord; auditEvent: import('@/types').AuditEvent }>(`/v1/agents/${encodeURIComponent(agentIdStr)}/lifecycle`, { status });
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server.'); return; }
    store.patchAgent(agentIdStr, () => data.agent);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('info', `Agent ${status}.`);
  },

  // POST /v1/knowledge/:id/refresh — manual pipeline run (Section 9.6). Unchanged simulation.
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
        ws().agents.forEach((a) => {
          if (a.config.data.knowledge_source_refs.value.some((r) => r.includes(sourceId))) {
            const id = agentId(a);
            ws().patchAgent(id, (ag) => ({
              ...ag,
              demo_mode: false,
              tracks: { ...ag.tracks, content: track('ready', ag.tracks.content.steps.map((s) => ({ ...s, status: 'ready', at: s.at ?? nowIso() }))) },
            }));
            services.maybeGoLive(id);
            syncAgentToServer(id);
          }
        });
        audit('pipeline_refresh', 'source', sourceId, `Manual re-index completed for ${source.name}.`);
        ws().pushToast('ok', `${source.name} re-indexed.`);
      },
    );
    audit('pipeline_refresh', 'source', sourceId, `Manual re-index started for ${source.name}.`);
  },
};
