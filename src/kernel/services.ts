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

import { ws, type FeatureFlags } from './store';
import { startJob } from './jobs';
import { audit, nowIso } from './api';
import { synthesize as runEngine } from './engine';
import { generatePlaygroundResponse, resolvePromptRef, type MessageKind, type PlaygroundResponse, type RetrievalChunk } from './playground';
import type {
  AccessGrant, AgentCard, AgentRecord, CapabilityTier, DeploymentRecord, EvaluationPack, GovernanceException,
  GovernancePath, KnowledgeSource, McpConnector, ModelAsset, PathDefinition, PipelineRun, PolicyRule, PromptAsset,
  PromptCategory, PromptKind, RefreshCadence, RiskTier, Sensitivity, ToolAsset, ToolPermission,
} from '@/types';
import { agentId, isLive, prov } from '@/types';
import { governancePathFor, FAST_PATH_DAYS } from './constants';
import { PERSONAS } from './constants';
import { RUNTIME_STEP_NAMES, CONTENT_STEP_NAMES } from '@/seed/helpers';
import { latency } from './rng';

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

async function patchJson<T>(path: string, body: unknown): Promise<{ ok: boolean; status: number; data: T | null }> {
  try {
    const res = await fetch(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
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

  // Real backend call (services/evaluation.py) — actually invokes the agent's
  // real chat pipeline per case (safety_boundary re-checks the same real
  // write-intent guard chat.py enforces; grounding/correctness are graded by
  // a real cheap-tier LLM judge; latency_cost measures a real call's elapsed
  // time). Needs a running server + ANTHROPIC_API_KEY with credits for any
  // case beyond safety_boundary — surfaces the real error if not.
  async runEvaluation(packId: string): Promise<void> {
    const store = ws();
    const pack = store.evalPacks.find((p) => p.id === packId);
    const agent = pack ? store.agents.find((a) => agentId(a) === pack.agent_id) : undefined;
    const jobId = store.nextId('job');
    store.upsertJob({
      id: jobId, kind: 'evaluation_run', label: `Running evaluation · ${agent?.config.identity.agent_name.value ?? packId}`,
      entity_id: packId, status: 'processing', progress: 0.5, step_label: 'Executing cases…', result: null, created_at: nowIso(),
    });
    const { ok, data } = await postJson<{ pack: EvaluationPack; run: { score: number; error_msg: string | null }; auditEvent: import('@/types').AuditEvent; message?: string }>(
      `/v1/evaluations/${encodeURIComponent(packId)}/run`, {},
    );
    store.removeJob(jobId);
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — evaluation run failed.'); return; }
    store.upsertEvalPack(data.pack);
    store.addAuditEvent(data.auditEvent);
    // Same staleness issue as chatWithAgent — a real run also records real
    // telemetry and a real eval_score_history point; resync so those aren't
    // stuck showing pre-run numbers.
    void services.bootstrapWorkspace();
    const name = agent?.config.identity.agent_name.value ?? packId;
    if (data.run.error_msg) {
      store.pushToast('warn', `${name} eval: ${data.run.score}/100 — some cases errored (${data.run.error_msg.slice(0, 80)}).`);
    } else {
      store.pushToast(data.run.score >= 90 ? 'ok' : 'warn', `${name} eval: ${data.run.score}/100.`);
    }
  },

  // Rebuilds a pack's cases from the agent's current config using the real,
  // content-aware generator (services/evaluations/seed_gen.py) — for packs
  // generated before that existed, or whose agent/source has since changed.
  async regenerateEvalPack(packId: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ pack: EvaluationPack; auditEvent: import('@/types').AuditEvent; message?: string }>(
      `/v1/evaluations/${encodeURIComponent(packId)}/regenerate`, {},
    );
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — regeneration failed.'); return; }
    store.upsertEvalPack(data.pack);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${data.pack.cases.length} eval case(s) regenerated from current config.`);
  },

  // Registry — delete an agent (Platform Engineer only, gated client-side same
  // as other persona-restricted actions in this app). Server-persisted.
  async deleteAgent(agentIdStr: string): Promise<boolean> {
    const store = ws();
    try {
      const res = await fetch(`/v1/agents/${encodeURIComponent(agentIdStr)}?actorPersona=${encodeURIComponent(PERSONAS[store.ui.persona].label)}`, { method: 'DELETE' });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) { store.pushToast('err', 'Could not reach the server — delete failed.'); return false; }
      store.removeAgent(agentIdStr);
      if (data.auditEvent) store.addAuditEvent(data.auditEvent);
      store.pushToast('ok', 'Agent deleted.');
      return true;
    } catch {
      store.pushToast('err', 'Could not reach the server — delete failed.');
      return false;
    }
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

    // The real call just recorded real telemetry server-side (request_telemetry
    // table) — but `store.telemetry` is a snapshot taken once at bootstrap and
    // nothing else refreshes it, so the Telemetry tab would otherwise sit
    // frozen even after real traffic. Fire-and-forget resync, doesn't block
    // returning the answer to the Playground UI.
    void services.bootstrapWorkspace();

    if (data.kind === 'refusal') {
      // The server's independent write-intent re-check overrode the client's classification.
      return { ...base, kind: 'refusal', citations: [], retrieval: [], toolCalls: [], text: data.text, tokenCount: 0, shapedBy: ['tool_permission=read (advisory-only)', 'safety_instructions', 'server-side re-check'] };
    }
    // Real retrieval/citations/kind from the server replace the placeholder —
    // this is what makes the Inspector panel show what was actually sent to Claude.
    return { ...base, kind: data.kind, citations: data.citations, retrieval: data.retrieval, text: data.text, tokenCount: data.tokenCount || base.tokenCount, shapedBy: [...base.shapedBy, data.model ? `model=${data.model}` : 'model=unavailable (fallback text)'] };
  },

  // Run an MCP connector healthcheck (Section 9.5). Unchanged — client-simulated.
  // Real network attempt (services/mcp.py) — an actual HTTP request to the
  // connector's endpoint, not a simulated status flip. The seeded connectors
  // point at fictional *.brightspeed.internal hostnames, so a real healthcheck
  // against them will honestly report unreachable rather than pretend success.
  async healthcheck(connectorId: string): Promise<void> {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;
    const jobId = store.nextId('job');
    store.upsertJob({ id: jobId, kind: 'healthcheck', label: `Healthcheck · ${conn.name}`, entity_id: connectorId, status: 'processing', progress: 0.5, step_label: 'Probing endpoint…', result: null, created_at: nowIso() });
    const { ok, data } = await postJson<{ connector: McpConnector; auditEvent: import('@/types').AuditEvent }>(`/v1/mcp/connectors/${encodeURIComponent(connectorId)}/healthcheck`, {});
    store.removeJob(jobId);
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — healthcheck failed.'); return; }
    store.patchConnector(connectorId, data.connector);
    store.addAuditEvent(data.auditEvent);
    store.pushToast(data.connector.status === 'connected' ? 'ok' : 'warn', `${conn.name}: ${data.connector.status}.`);
  },

  // Manual override — real DB-persisted status flip (services/mcp.py), not a
  // connectivity test (see healthcheck above for that).
  async toggleConnectorOffline(connectorId: string): Promise<void> {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;
    const { ok, data } = await postJson<{ connector: McpConnector; auditEvent: import('@/types').AuditEvent }>(`/v1/mcp/connectors/${encodeURIComponent(connectorId)}/toggle`, {});
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — toggle failed.'); return; }
    store.patchConnector(connectorId, data.connector);
    store.addAuditEvent(data.auditEvent);
    store.pushToast(data.connector.status === 'offline' ? 'warn' : 'ok', `${conn.name} ${data.connector.status}.`);
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

  // Onboarding wizard Phase 5 risk override (Section 9.2). Server re-derives
  // governance_path from the real policy_rules table (governance_repo) —
  // was a client-side lookup against a hardcoded copy of the matrix.
  async updateRiskTier(agentIdStr: string, riskTier: RiskTier): Promise<boolean> {
    const store = ws();
    const { ok, data } = await postJson<{ agent: AgentRecord; auditEvent: import('@/types').AuditEvent; message?: string }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/risk-tier`, { risk_tier: riskTier },
    );
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — risk tier update failed.'); return false; }
    store.patchAgent(agentIdStr, () => data.agent);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `risk_tier → ${riskTier}; governance path → ${data.agent.governance_path}.`);
    return true;
  },

  // Onboarding Phase 1 — real LLM ranking of existing knowledge sources
  // against the agent's stated objective (services/source_suggestion_service.py).
  // Was entirely absent; source selection was 100% manual.
  async suggestSources(objective: string): Promise<{ source_id: string; name: string; relevance: string; reason: string }[]> {
    const store = ws();
    try {
      const res = await fetch('/v1/knowledge/sources/suggest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ objective }) });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — suggestion failed.'); return []; }
      return data.suggestions ?? [];
    } catch {
      store.pushToast('err', 'Could not reach the server — suggestion failed.');
      return [];
    }
  },

  // Suspend / retire (Section 9.2 — Governance Officer actions). Server-persisted.
  async setLifecycle(agentIdStr: string, status: 'suspended' | 'retired' | 'live'): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ agent: AgentRecord; auditEvent: import('@/types').AuditEvent; message?: string }>(`/v1/agents/${encodeURIComponent(agentIdStr)}/lifecycle`, { status });
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server.'); return; }
    store.patchAgent(agentIdStr, () => data.agent);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('info', status === 'live' ? 'Agent reactivated.' : `Agent ${status}.`);
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

  // ---- Prompt Repository (Section 9.4) — creation + approval, server-persisted ----

  async createPrompt(input: { name: string; kind: PromptKind; category: PromptCategory; owner: string; body?: string; source?: 'manual' | 'llm_generated'; generated_from?: string | null }): Promise<string | null> {
    const { ok, data } = await postJson<{ prompt: PromptAsset }>('/v1/prompts', input);
    if (!ok || !data) { ws().pushToast('err', 'Could not reach the server — prompt creation failed.'); return null; }
    ws().upsertPrompt(data.prompt);
    return data.prompt.id;
  },

  // Preview-only draft (name + body) — does not create a new prompt row.
  // Used by the Generate-with-AI review dialog (create flow) and by the
  // in-place regenerate button on an existing draft's editor.
  async generatePromptBody(input: { kind: PromptKind; category: PromptCategory; context: Record<string, unknown> }): Promise<{ name: string; body: string } | null> {
    const { ok, data } = await postJson<{ name: string; body: string }>('/v1/prompts/generate-body', input);
    if (!ok || !data) { ws().pushToast('err', 'Could not reach the server — generation failed.'); return null; }
    return data;
  },

  async newPromptVersion(promptId: string): Promise<void> {
    const { ok, data } = await postJson<{ prompt: PromptAsset }>(`/v1/prompts/${encodeURIComponent(promptId)}/new-version`, {});
    if (!ok || !data) { ws().pushToast('err', 'Could not reach the server — new version failed.'); return; }
    ws().upsertPrompt(data.prompt);
    audit('new_version', 'prompt', promptId, `Drafted ${data.prompt.version}.`);
    ws().pushToast('ok', `Drafted ${data.prompt.version}.`);
  },

  async updatePromptFields(promptId: string, patch: Partial<Pick<PromptAsset, 'name' | 'kind' | 'category' | 'body' | 'owner'>>): Promise<void> {
    try {
      const res = await fetch(`/v1/prompts/${encodeURIComponent(promptId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) { ws().pushToast('err', 'Could not reach the server — save failed.'); return; }
      ws().upsertPrompt(data.prompt);
      ws().pushToast('ok', 'Prompt saved.');
    } catch {
      ws().pushToast('err', 'Could not reach the server — save failed.');
    }
  },

  async decidePrompt(promptId: string, decision: 'approved' | 'rejected'): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ prompt: PromptAsset; auditEvent: import('@/types').AuditEvent }>(
      `/v1/prompts/${encodeURIComponent(promptId)}/decide`,
      { decision, actorPersona: PERSONAS[store.ui.persona].label },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — decision failed.'); return; }
    store.upsertPrompt(data.prompt);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', decision === 'approved' ? 'Prompt approved.' : 'Prompt rejected.');
  },

  async deprecatePrompt(promptId: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ prompt: PromptAsset; auditEvent: import('@/types').AuditEvent }>(
      `/v1/prompts/${encodeURIComponent(promptId)}/deprecate`,
      { actorPersona: PERSONAS[store.ui.persona].label },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — deprecate failed.'); return; }
    store.upsertPrompt(data.prompt);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('info', 'Prompt deprecated.');
  },

  // Knowledge & RAG has no backend route yet (client-simulated, like
  // triggerPipeline/healthcheck below) — this is a real, immediate store
  // mutation, not a placeholder. New sources start pending approval; nothing
  // can bind to them until a Governance Officer approves the source.
  addKnowledgeSource(input: { name: string; source_uri: string; parser: string; sensitivity: Sensitivity; refresh_cadence: RefreshCadence }): string {
    const store = ws();
    const id = store.nextId('src');
    const source: KnowledgeSource = {
      id,
      name: input.name,
      source_uri: prov(input.source_uri, 'user'),
      parser: prov(input.parser, 'user'),
      source_chunking: prov('recursive_1024_128', 'default'),
      embedding_model: prov('vertex://text-embedding-004', 'default'),
      index_target: prov(`vector://alloydb-${id}`, 'default'),
      sensitivity: prov(input.sensitivity, 'user'),
      source_approval: prov('pending', 'system'),
      refresh_cadence: prov(input.refresh_cadence, 'user'),
      source_version: prov('v1', 'default'),
      document_count: 0,
      index_size_mb: 0,
      used_by: [],
      snippets: [],
      ingestion: [],
    };
    store.upsertSource(source);
    audit('create_source', 'source', id, `Registered knowledge source "${input.name}" (${input.sensitivity}, pending approval).`);
    store.pushToast('ok', `${input.name} added — pending approval before any agent can use it.`);
    return id;
  },

  // Real backend call (routes/tools.py) — the advisory-only rule (Section 7.6)
  // is enforced server-side: POST /v1/tools can never mint a write_capable tool
  // regardless of what the client sends.
  async registerTool(input: { name: string; description: string; category: string; permission_ceiling: ToolPermission; connector_id: string | null }): Promise<string | null> {
    const store = ws();
    const { ok, data } = await postJson<{ tool: ToolAsset; auditEvent: import('@/types').AuditEvent }>('/v1/tools', input);
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — tool registration failed.'); return null; }
    store.addTool(data.tool);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${data.tool.name} registered to the catalog.`);
    return data.tool.id;
  },

  // Real backend call (routes/models.py). Unlike registerTool, `id` is
  // caller-supplied — a model id is a meaningful provider identifier
  // (e.g. "claude-opus-6"), not something to derive from the display name.
  async registerModel(input: { id: string; name: string; provider: string; roles: ModelAsset['roles']; deployment_status?: ModelAsset['deployment_status']; approved_use_case?: string }): Promise<string | null> {
    const store = ws();
    const { ok, data } = await postJson<{ model: ModelAsset; auditEvent: import('@/types').AuditEvent }>('/v1/models', input);
    if (!ok || !data) { store.pushToast('err', data ? 'Model registration failed.' : 'Could not reach the server — model registration failed.'); return null; }
    store.addModel(data.model);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${data.model.name} added to the catalog.`);
    return data.model.id;
  },

  async updateModel(modelId: string, patch: Partial<ModelAsset>): Promise<void> {
    const store = ws();
    const { ok, data } = await patchJson<{ model: ModelAsset }>(`/v1/models/${encodeURIComponent(modelId)}`, patch);
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — update failed.'); return; }
    store.patchModel(modelId, data.model);
    store.pushToast('ok', `${data.model.name} updated.`);
  },

  async deleteModel(modelId: string): Promise<boolean> {
    const store = ws();
    try {
      const res = await fetch(`/v1/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
      if (!res.ok) { store.pushToast('err', 'Could not reach the server — delete failed.'); return false; }
    } catch {
      store.pushToast('err', 'Could not reach the server — delete failed.');
      return false;
    }
    store.removeModel(modelId);
    store.pushToast('ok', 'Model removed from the catalog.');
    return true;
  },

  // Policy-as-configuration (Blueprint §9) — real backend call
  // (routes/governance.py); services/registration.py reads this same table,
  // so this edit changes real registration behavior immediately.
  async updatePolicyRule(tier: CapabilityTier, risk: RiskTier, path: GovernancePath): Promise<void> {
    const store = ws();
    const { ok, data } = await patchJson<{ rule: PolicyRule; auditEvent: import('@/types').AuditEvent }>(
      '/v1/governance/policy-rule',
      { capability_tier: tier, risk_tier: risk, governance_path: path },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — policy update failed.'); return; }
    store.upsertPolicyRule(data.rule);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${tier} × ${risk} → ${path} path.`);
  },

  async updatePathDefinition(path: GovernancePath, patch: Partial<Pick<PathDefinition, 'label' | 'hitl_gates' | 'desc' | 'approvals'>>): Promise<void> {
    const store = ws();
    const { ok, data } = await patchJson<{ pathDefinition: PathDefinition; auditEvent: import('@/types').AuditEvent }>(
      `/v1/governance/path-definition/${encodeURIComponent(path)}`,
      patch,
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — path definition update failed.'); return; }
    store.upsertPathDefinition(data.pathDefinition);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${path} path definition updated.`);
  },

  // Exception Management (Blueprint §9) — a real register with an expiry
  // date, not a free-text agent field. Server-side validates expires_at is
  // actually in the future.
  async grantException(input: { agent_id: string; reason: string; expires_at: string }): Promise<boolean> {
    const store = ws();
    const { ok, data } = await postJson<{ exception: GovernanceException; auditEvent: import('@/types').AuditEvent }>('/v1/governance/exceptions', input);
    if (!ok || !data) { store.pushToast('err', 'Could not grant exception.'); return false; }
    store.addException(data.exception);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('warn', `Exception granted — expires ${new Date(input.expires_at).toLocaleDateString()}.`);
    return true;
  },

  async revokeException(exceptionId: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ exception: GovernanceException; auditEvent: import('@/types').AuditEvent }>(`/v1/governance/exceptions/${encodeURIComponent(exceptionId)}/revoke`, {});
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — revoke failed.'); return; }
    store.patchException(exceptionId, data.exception);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', 'Exception revoked.');
  },

  // Evidence Pack Center (Blueprint §6.3/§11) — a real, freshly-assembled join
  // of agent config + prompts + eval history + approvals + audit trail
  // (services/evaluation.py build_evidence_pack), not a stored duplicate.
  async downloadEvidencePack(packId: string): Promise<void> {
    const store = ws();
    try {
      const res = await fetch(`/v1/evaluations/${encodeURIComponent(packId)}/evidence-pack`);
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) { store.pushToast('err', 'Could not reach the server — evidence pack failed.'); return; }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `evidence-pack-${packId}.json`; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
      store.pushToast('ok', 'Evidence pack downloaded.');
    } catch {
      store.pushToast('err', 'Could not reach the server — evidence pack failed.');
    }
  },

  // Deployment & Access Management (Blueprint §5.10/§9) — a real environment
  // ladder (staging <-> production), gated server-side on lifecycle_status and
  // last eval score (services/deployment.py), not a free-text config field.
  async promoteDeployment(agentIdStr: string, reason?: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ record: DeploymentRecord; auditEvent: import('@/types').AuditEvent; message?: string }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/deployment/promote`, { reason },
    );
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — promotion failed.'); return; }
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `Promoted to ${data.record.to_environment}.`);
  },

  async rollbackDeployment(agentIdStr: string, reason?: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ record: DeploymentRecord; auditEvent: import('@/types').AuditEvent; message?: string }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/deployment/rollback`, { reason },
    );
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — rollback failed.'); return; }
    store.addAuditEvent(data.auditEvent);
    store.pushToast('warn', `Rolled back to ${data.record.to_environment}.`);
  },

  async grantAccess(input: { agent_id: string; grantee: string; role_label: string; scope: 'owner' | 'admin' | 'viewer' }): Promise<boolean> {
    const store = ws();
    const { ok, data } = await postJson<{ grant: AccessGrant; auditEvent: import('@/types').AuditEvent; message?: string }>('/v1/access-grants', input);
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not grant access.'); return false; }
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `Access granted to ${input.grantee}.`);
    return true;
  },

  async revokeAccess(grantId: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ grant: AccessGrant; auditEvent: import('@/types').AuditEvent; message?: string }>(`/v1/access-grants/${encodeURIComponent(grantId)}/revoke`, {});
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — revoke failed.'); return; }
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', 'Access revoked.');
  },

  // Admin Console → Feature Flags — a real, durable register (feature_flags
  // table) instead of Zustand-only ui state that reset on every reload.
  async setFeatureFlag(key: keyof FeatureFlags, value: boolean): Promise<void> {
    const store = ws();
    const { ok, data } = await patchJson<{ flag: { key: string; enabled: boolean }; auditEvent: import('@/types').AuditEvent; message?: string }>(
      `/v1/admin/feature-flags/${encodeURIComponent(key)}`, { enabled: value },
    );
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — flag update failed.'); return; }
    store.setFeatureFlag(key, data.flag.enabled);
    store.addAuditEvent(data.auditEvent);
  },

  // A2A Directory — the one real-editable field on an otherwise fully
  // config-derived card (services/a2a.py update_endpoint).
  async updateA2AEndpoint(agentIdStr: string, endpoint: string): Promise<void> {
    const store = ws();
    const { ok, data } = await patchJson<{ card: AgentCard; auditEvent: import('@/types').AuditEvent; message?: string }>(
      `/v1/a2a/cards/${encodeURIComponent(agentIdStr)}`, { endpoint },
    );
    if (!ok || !data) { store.pushToast('err', data?.message ?? 'Could not reach the server — endpoint update failed.'); return; }
    store.patchA2ACard(agentIdStr, data.card);
    store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', 'A2A endpoint updated.');
  },
};
