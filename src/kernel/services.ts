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
  AgentRecord, AuditEvent, ConnectorBacklogItem, EvalResult, EvaluationPack, McpConnector,
  McpGatewayPolicy, PipelineRun, ToolAsset,
} from '@/types';
import { agentId, isLive } from '@/types';

// Both connector mutation endpoints return this shape: the updated connector,
// the tools whose status the server cascaded, and the audit event it wrote.
interface ConnectorMutationResponse {
  connector: McpConnector;
  changedTools: ToolAsset[];
  auditEvent: AuditEvent | null;
}

// MCP tools/list + the discovery diff against the catalog.
export interface ConnectorToolsResponse {
  connector: McpConnector;
  tools: ToolAsset[];
  undiscovered: string[]; // advertised by the connector, absent from the catalog
  orphaned: string[];     // catalogued against this connector, no longer advertised
  // Phase 5A. `live` distinguishes a real `tools/list` over the wire from a
  // read-back of what the catalog already held. When true, `undiscovered` is
  // always empty (we just wrote everything the server advertised) and
  // `rejected` carries definitions the client refused as non-conformant.
  live?: boolean;
  rejected?: { name: string | null; reason: string; detail: string }[];
  created?: string[];     // tool ids that did not exist before this discovery
  protocol_version?: string | null;
  server_info?: { name: string | null; version: string | null } | null;
}

// Tool-call audit trail — deck slide 21 element 6's eight fields. `system_accessed`
// and `permission` are resolved server-side and are NOT accepted from the client.
export interface ToolCallRecord {
  id: string;
  agent_id: string;
  request_id: string;
  consumer: string;
  tool_invoked: string;
  system_accessed: string | null; // NULL for local tools — never a placeholder
  result_status: 'ok' | 'error' | 'blocked';
  latency_ms: number;
  exception_detail: string | null;
  permission: string;
  at: string;
  // ---- Phase 6: how much this row can be trusted --------------------------
  // `gateway` is the load-bearing field. false = a client reported this call
  // (the Phase 1 path, still live), so result and latency are claims. true =
  // every checkpoint ran server-side and the outcome was observed there.
  // `invocation: 'live'` narrows it further: only then is `latency_ms` a real
  // system's latency rather than our own simulation's. CONCERNS R7.
  gateway: boolean;
  decision: 'allow' | 'deny' | null;
  denied_by: string | null;   // the checkpoint id that refused
  invocation: 'live' | 'simulated' | 'none' | null;
  principal: string | null;
  team: string | null;
  redacted_fields: string[];
}

// One checkpoint in the gateway chain. Served by the backend rather than
// restated here — a second copy in TypeScript is a second thing to keep in step
// with the enforcement, and the copy always loses.
export interface GatewayCheckpoint {
  id: string;
  label: string;
  source: string;      // the deck slide / Blueprint section it comes from
  description: string;
}

// What one checkpoint did on one call. `skipped` is a real outcome, not a gap:
// a local tool has no connector to be unreachable and no boundary to cross.
export interface GatewayTraceEntry {
  checkpoint: string;
  status: 'pass' | 'warn' | 'deny' | 'skipped';
  detail: string | null;
}

export interface GatewayPolicyResponse {
  checkpoints: GatewayCheckpoint[];
  principals: string[];
  rateWindowSeconds: number;
  policies: (McpGatewayPolicy & {
    connector_id: string;
    name: string;
    status: string;
    live: boolean;
    undeclared: string[]; // policy fields nobody has written yet
  })[];
}

// A denied call is a 200 with `allowed: false`, never an HTTP error — see
// backend routes/gateway.py for why.
export interface GatewayCallResponse {
  allowed: boolean;
  decision: 'allow' | 'deny';
  deniedBy: string | null;
  reason: string | null;
  checkpoints: GatewayTraceEntry[];
  warnings: string[];
  result: {
    invocation: 'live' | 'simulated';
    content: string | null;
    structured: unknown;
    error: string | null;
    latencyMs: number;
  } | null;
  redacted: string[];
  toolCall: ToolCallRecord;
  auditEvent?: AuditEvent | null;
}

// An agent's MCP dependency set — the connectors its bound tools resolve to.
// The tool→connector edge is a fixed FK, so this is a lookup, not a choice;
// see backend services/connector_resolution.py.
export interface AgentConnectorsResponse {
  agent_id: string;
  bound_tools: string[];
  connectors: (McpConnector & { tools: string[] })[];
  local_tools: string[];   // connector_id IS NULL — need no MCP server
  unknown_tools: string[]; // bound, but no longer in the catalog
  offline: string[];       // deploy-time hard blockers
  unhealthy: string[];     // offline ∪ degraded
}

// The connector prioritization backlog and its **server-derived** summary
// (deck slide 21, element 7). `recommended` and the blocked/unassessed lists are
// computed server-side from the ranking — never re-derived here, so the headline
// cannot drift from the table it summarises.
export interface ConnectorBacklogResponse {
  backlog: ConnectorBacklogItem[];
  summary: {
    total: number;
    day_90: number;
    later: number;
    recommended: string | null;
    blocked_on_no_server: string[];
    unassessed: string[];
  };
}

// A tool ref the server refused to persist into `bound_tools` (R8). Every route
// that writes bound_tools runs the same guard, so this shape is returned by
// register, the config sync PATCH, and config-change alike.
// See backend services/bound_tools_guard.py.
export interface StrippedTool {
  tool_id: string;
  ref: string;
  reason: 'not_in_catalog' | 'write_capable' | 'not_approved';
  message: string;
}

const STRIP_REASON_LABEL: Record<StrippedTool['reason'], string> = {
  not_in_catalog: 'not in the catalog',
  write_capable: 'write-capable — advisory-block',
  not_approved: 'pending approval',
};

export function describeStripped(stripped: StrippedTool[]): string {
  const list = stripped.map((s) => `${s.tool_id} (${STRIP_REASON_LABEL[s.reason] ?? s.reason})`).join(', ');
  return `${stripped.length} tool${stripped.length === 1 ? '' : 's'} not bound: ${list}.`;
}
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

async function postJson<T>(path: string, body: unknown, method: 'POST' | 'PATCH' = 'POST'): Promise<{ ok: boolean; status: number; data: T | null }> {
  try {
    const res = await fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
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

    const { ok, data } = await postJson<{ agent: AgentRecord; pack: EvaluationPack; approvals: import('@/types').ApprovalItem[]; auditEvent: import('@/types').AuditEvent; strippedTools?: StrippedTool[] }>(
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
    // R8 — the server strips refs that could never be bound (write-capable,
    // unapproved, uncatalogued). `addAgent` above already adopted the sanitized
    // config, so this only has to *explain* the difference; never silently.
    if (data.strippedTools?.length) {
      store.pushToast('warn', `Registered ${draft.name}. ${describeStripped(data.strippedTools)}`);
    } else {
      store.pushToast('ok', `Registered ${draft.name}.`);
    }

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
  // The queue is shared across entity kinds (Phase 3.2), so the response
  // carries whichever subject the item was about: an agent, or a tool.
  async decideApproval(approvalId: string, decision: 'approved' | 'rejected', note: string): Promise<void> {
    const store = ws();
    const { ok, data } = await postJson<{ approval: import('@/types').ApprovalItem; agent: AgentRecord | null; tool?: ToolAsset | null; auditEvent: import('@/types').AuditEvent }>(
      `/v1/approvals/${encodeURIComponent(approvalId)}/decide`,
      { decision, note, actorPersona: PERSONAS[store.ui.persona].label },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — decision failed.'); return; }
    store.patchApproval(data.approval.id, data.approval);
    if (data.agent) store.patchAgent(agentId(data.agent), () => data.agent!);
    if (data.tool) {
      store.patchTool(data.tool.id, data.tool);
      store.pushToast(data.tool.approval_state === 'approved' ? 'ok' : 'warn',
        data.tool.approval_state === 'approved'
          ? `${data.tool.name} approved — now bindable.`
          : `${data.tool.name} rejected — stays catalogued, cannot be bound.`);
    }
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
    const { ok, data } = await postJson<{ agent: AgentRecord; approval: import('@/types').ApprovalItem | null; auditEvent: import('@/types').AuditEvent; strippedTools?: StrippedTool[] }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/config-change`,
      { groupKey, field, newValue },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — change failed.'); return; }
    store.patchAgent(agentIdStr, () => data.agent);
    if (data.approval) store.addApproval(data.approval);
    store.addAuditEvent(data.auditEvent);
    // Setting bound_tools through here runs the same guard as registration.
    if (data.strippedTools?.length) {
      store.pushToast('warn', `Change applied to ${field}. ${describeStripped(data.strippedTools)}`);
    } else {
      store.pushToast('ok', `Change applied to ${field}.`);
    }
  },

  // Advisory-only bind guard (acceptance #3), enforced server-side — the
  // server's own `tools` table is the trust boundary, not anything the client claims.
  async bindTool(agentIdStr: string, toolId: string): Promise<boolean> {
    const store = ws();
    const { ok, data } = await postJson<{ ok: boolean; agent?: AgentRecord; tool?: { used_by: string[] }; auditEvent?: import('@/types').AuditEvent; message?: string; warning?: string | null }>(
      `/v1/agents/${encodeURIComponent(agentIdStr)}/tools/bind`,
      { toolId },
    );
    if (!ok || !data) { store.pushToast('err', 'Could not reach the server — bind failed.'); return false; }
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    if (!data.ok) { store.pushToast('err', data.message ?? `${toolId} cannot be bound.`); return false; }
    if (data.agent) store.patchAgent(agentIdStr, () => data.agent!);
    if (data.tool) store.patchTool(toolId, { used_by: data.tool.used_by });
    // An unhealthy connector warns but never blocks — binding is design-time,
    // connector health is runtime. The blocking gate is Pre-Flight check #4.
    if (data.warning) store.pushToast('warn', data.warning);
    return true;
  },

  // POST /v1/tools — persists a new catalog entry. Server re-validates
  // permission_ceiling against the same advisory-only set the client uses.
  async createTool(input: {
    name: string;
    category: string;
    description: string;
    permission_ceiling: string;
    write_capable: boolean;
    owner?: string | null;
    risk_level?: string | null;
    schema: { inputs: Record<string, string>; outputs: Record<string, string> };
  }): Promise<ToolAsset | null> {
    const store = ws();
    const { ok, data } = await postJson<{ tool?: ToolAsset; approval?: import('@/types').ApprovalItem; auditEvent?: import('@/types').AuditEvent; message?: string }>(
      '/v1/tools',
      input,
    );
    if (!ok || !data || !data.tool) { store.pushToast('err', data?.message ?? 'Could not reach the server — tool creation failed.'); return null; }
    store.addTool(data.tool);
    // Phase 3.2 — a new tool is catalogued but NOT bindable; it arrives with a
    // pending item on the shared approval queue (Blueprint §11).
    if (data.approval) store.addApproval(data.approval);
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${data.tool.name} catalogued — pending approval before it can be bound.`);
    return data.tool;
  },

  // PATCH /v1/tools/:id — Phase 3.3. Only `owner` and `risk_level`; the server
  // will not accept anything governance depends on through this path.
  async updateToolPolicy(toolId: string, input: { owner?: string | null; risk_level?: string | null }): Promise<ToolAsset | null> {
    const store = ws();
    const { ok, data } = await postJson<{ tool?: ToolAsset; auditEvent?: import('@/types').AuditEvent; changed?: string[]; message?: string }>(
      `/v1/tools/${encodeURIComponent(toolId)}`,
      input,
      'PATCH',
    );
    if (!ok || !data || !data.tool) { store.pushToast('err', data?.message ?? 'Could not reach the server — update failed.'); return null; }
    store.patchTool(data.tool.id, data.tool);
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    store.pushToast(data.changed?.length ? 'ok' : 'info', data.changed?.length ? `${data.tool.name}: ${data.changed.join(', ')} updated.` : 'No changes.');
    return data.tool;
  },

  // POST /v1/tools/suggest — Claude drafts catalog fields from a free-text
  // description. Never persists; the caller reviews/edits before createTool().
  async suggestTool(description: string): Promise<Partial<ToolAsset> | null> {
    const store = ws();
    const { ok, data } = await postJson<{ draft?: Partial<ToolAsset>; message?: string }>(
      '/v1/tools/suggest',
      { description },
    );
    if (!ok || !data || !data.draft) { store.pushToast('err', data?.message ?? 'Could not reach the server — suggestion failed.'); return null; }
    return data.draft;
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

  // Applies a connector mutation response from the server. Both connector
  // endpoints return the same shape: the updated connector, the tools whose
  // status the server cascaded, and the audit event it wrote.
  _applyConnectorResult(
    connectorId: string,
    data: ConnectorMutationResponse,
    toast: { kind: 'ok' | 'warn'; message: string },
  ): void {
    const store = ws();
    store.patchConnector(connectorId, { status: data.connector.status, last_healthcheck: data.connector.last_healthcheck });
    // A tool is never healthier than the connector serving it — the server
    // derives this and hands back only the rows that actually changed.
    for (const t of data.changedTools) store.patchTool(t.id, { status: t.status });
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    store.pushToast(toast.kind, toast.message);
  },

  // POST /v1/connectors — register an MCP server (Blueprint §3.5). The server
  // seeds `status: connected` and `tools_provided: []`; neither is accepted
  // from this form. Status belongs to the health cascade, and an empty
  // `tools_provided` is what makes "Discover tools" show a real diff.
  async createConnector(input: {
    name: string;
    transport: string;
    endpoint: string;
    auth_mode: string;
  }): Promise<McpConnector | null> {
    const store = ws();
    const { ok, data } = await postJson<{ connector?: McpConnector; auditEvent?: AuditEvent; message?: string }>('/v1/connectors', input);
    if (!ok || !data?.connector) { store.pushToast('err', data?.message ?? 'Could not register the connector.'); return null; }
    store.addConnector(data.connector);
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    store.pushToast('ok', `${data.connector.name} registered. Run Discover tools to map its catalog.`);
    return data.connector;
  },

  // PATCH /v1/connectors/:id — edit the author-owned fields only.
  async updateConnector(connectorId: string, patch: Partial<Pick<McpConnector, 'name' | 'transport' | 'endpoint' | 'auth_mode'>>): Promise<McpConnector | null> {
    const store = ws();
    try {
      const res = await fetch(`/v1/connectors/${encodeURIComponent(connectorId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data = (await res.json().catch(() => null)) as { connector?: McpConnector; auditEvent?: AuditEvent; changed?: string[]; message?: string } | null;
      if (!res.ok || !data?.connector) { store.pushToast('err', data?.message ?? 'Could not update the connector.'); return null; }
      store.patchConnector(connectorId, data.connector);
      if (data.auditEvent) store.addAuditEvent(data.auditEvent);
      store.pushToast(data.changed?.length ? 'ok' : 'info', data.changed?.length ? `${data.connector.name} updated (${data.changed.join(', ')}).` : 'No changes.');
      return data.connector;
    } catch {
      store.pushToast('err', 'Could not reach the server — update failed.');
      return null;
    }
  },

  // POST /v1/connectors/:id/healthcheck — server-persisted (Section 9.5).
  // Was a client-simulated job; the connector's health is now authoritative
  // server state because tool status derives from it. Per the repo convention,
  // real backend calls do NOT use the kernel/jobs.ts queue — the caller drives
  // its own loading state.
  async healthcheck(connectorId: string): Promise<void> {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;

    const { ok, data } = await postJson<ConnectorMutationResponse & { skipped?: boolean; message?: string }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/healthcheck`,
      {},
    );
    if (!ok || !data?.connector) { store.pushToast('err', data?.message ?? 'Could not reach the server — healthcheck failed.'); return; }

    // An offline connector stays offline; a healthcheck never silently revives it.
    if (data.skipped) { store.pushToast('warn', `${conn.name} is offline.`); return; }

    services._applyConnectorResult(connectorId, data, {
      kind: data.connector.status === 'degraded' ? 'warn' : 'ok',
      message: `${conn.name}: ${data.connector.status}.`,
    });
  },

  // POST /v1/connectors/:id/toggle-offline — the demo lever, server-persisted.
  // Cascades to the connector's tools and survives a refresh.
  async toggleConnectorOffline(connectorId: string): Promise<void> {
    const store = ws();
    const conn = store.connectors.find((c) => c.id === connectorId);
    if (!conn) return;

    const { ok, data } = await postJson<ConnectorMutationResponse & { message?: string }>(
      `/v1/connectors/${encodeURIComponent(connectorId)}/toggle-offline`,
      {},
    );
    if (!ok || !data?.connector) { store.pushToast('err', data?.message ?? 'Could not reach the server — toggle failed.'); return; }

    const offline = data.connector.status === 'offline';
    services._applyConnectorResult(connectorId, data, {
      kind: offline ? 'warn' : 'ok',
      message: `${conn.name} ${data.connector.status}.${offline && data.changedTools.length ? ` ${data.changedTools.length} tool(s) offline.` : ''}`,
    });
  },

  // GET /v1/connectors/:id/tools — MCP `tools/list`. Returns what the connector
  // advertises plus a discovery diff against the catalog (`undiscovered` =
  // advertised but not catalogued, `orphaned` = catalogued but no longer
  // advertised). The seam a real MCP client swaps into.
  async listConnectorTools(connectorId: string): Promise<ConnectorToolsResponse | null> {
    try {
      const res = await fetch(`/v1/connectors/${encodeURIComponent(connectorId)}/tools`);
      if (!res.ok) return null;
      return (await res.json()) as ConnectorToolsResponse;
    } catch {
      ws().pushToast('err', 'Could not reach the server — tools/list failed.');
      return null;
    }
  },

  // GET /v1/connector-backlog — the assessment plus its server-derived summary.
  // Not in the store on purpose: the summary is computed server-side from the
  // ranking, and a store copy would tempt someone to re-derive it.
  async listConnectorBacklog(): Promise<ConnectorBacklogResponse | null> {
    try {
      const res = await fetch('/v1/connector-backlog');
      if (!res.ok) return null;
      return (await res.json()) as ConnectorBacklogResponse;
    } catch {
      ws().pushToast('err', 'Could not reach the server — connector backlog unavailable.');
      return null;
    }
  },

  // PATCH /v1/connector-backlog/:id — re-rank, re-phase, or move a system along.
  // The server refuses to put a system with no existing MCP server into the
  // 90-day phase; that is a SOW boundary, not a preference, so the error is
  // surfaced verbatim rather than reworded.
  async updateBacklogItem(itemId: string, patch: Partial<ConnectorBacklogItem>): Promise<ConnectorBacklogItem | null> {
    const store = ws();
    const { ok, data } = await postJson<{ item?: ConnectorBacklogItem; auditEvent?: AuditEvent; changed?: string[]; message?: string }>(
      `/v1/connector-backlog/${encodeURIComponent(itemId)}`,
      patch,
      'PATCH',
    );
    if (!ok || !data?.item) { store.pushToast('err', data?.message ?? 'Could not update the backlog.'); return null; }
    if (data.auditEvent) store.addAuditEvent(data.auditEvent);
    store.pushToast(data.changed?.length ? 'ok' : 'info',
      data.changed?.length ? `${data.item.system_name}: ${data.changed.join(', ')} updated.` : 'No changes.');
    return data.item;
  },

  // POST /v1/tool-calls — record one tool call (slide 21 element 6).
  // Fire-and-forget by design: the audit trail must never block or fail the
  // conversation that produced it. Send only what the client legitimately
  // knows — the server resolves `system_accessed` and `permission` itself.
  async recordToolCall(input: {
    agentId: string;
    toolInvoked: string;
    consumer?: 'playground' | 'api' | 'workflow' | 'console';
    resultStatus?: 'ok' | 'error' | 'blocked';
    latencyMs: number;
    requestId?: string;
    exceptionDetail?: string | null;
  }): Promise<ToolCallRecord | null> {
    const { ok, data } = await postJson<{ toolCall?: ToolCallRecord; message?: string }>('/v1/tool-calls', input);
    if (!ok || !data?.toolCall) return null;
    return data.toolCall;
  },

  // POST /v1/gateway/tool-call — Phase 6. The only governed way to *invoke* a
  // tool, as opposed to `recordToolCall` above, which only reports that one
  // happened. Eleven checkpoints run server-side, the server performs the
  // invocation, and the row it writes carries an observed result and a measured
  // latency.
  //
  // NOT fire-and-forget, unlike recordToolCall: the caller needs the verdict,
  // because a denial means there is no result to show. And a denial arrives as
  // a 200 with `allowed: false` — `ok` here is about reaching the server, not
  // about the gateway's decision.
  async callToolThroughGateway(input: {
    agentId: string;
    toolId: string;
    principal: string;
    consumer?: 'playground' | 'api' | 'workflow' | 'console';
    arguments?: Record<string, unknown>;
    dataset?: string;
    team?: string;
    requestId?: string;
    hitlApproved?: boolean;
  }): Promise<GatewayCallResponse | null> {
    const { ok, data } = await postJson<GatewayCallResponse & { message?: string }>('/v1/gateway/tool-call', input);
    if (!ok || !data?.toolCall) {
      ws().pushToast('err', data?.message ?? 'Could not reach the gateway.');
      return null;
    }
    if (data.auditEvent) ws().addAuditEvent(data.auditEvent);
    return data;
  },

  // GET /v1/gateway/policy — the checkpoint chain and each connector's declared
  // policy. Read-only, and the chain is served rather than restated in the
  // client so the console cannot disagree with the enforcement about what the
  // checks are or what order they run in.
  async getGatewayPolicy(): Promise<GatewayPolicyResponse | null> {
    try {
      const res = await fetch('/v1/gateway/policy');
      if (!res.ok) return null;
      return (await res.json()) as GatewayPolicyResponse;
    } catch {
      ws().pushToast('err', 'Could not reach the server — gateway policy unavailable.');
      return null;
    }
  },

  // PATCH /v1/connectors/:id/policy — declare the data boundary and identity
  // binding (slide 21 elements 4 and 5). A different route from
  // `updateConnector` on purpose: that edits how we reach a server, this
  // declares what it may expose and to whom.
  async updateConnectorPolicy(connectorId: string, patch: Partial<McpGatewayPolicy>): Promise<McpConnector | null> {
    const store = ws();
    try {
      const res = await fetch(`/v1/connectors/${encodeURIComponent(connectorId)}/policy`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data = (await res.json().catch(() => null)) as { connector?: McpConnector; auditEvent?: AuditEvent; changed?: string[]; message?: string } | null;
      if (!res.ok || !data?.connector) { store.pushToast('err', data?.message ?? 'Could not update the policy.'); return null; }
      store.patchConnector(connectorId, data.connector);
      if (data.auditEvent) store.addAuditEvent(data.auditEvent);
      store.pushToast(data.changed?.length ? 'ok' : 'info', data.changed?.length ? `Gateway policy updated (${data.changed.join(', ')}).` : 'No changes.');
      return data.connector;
    } catch {
      store.pushToast('err', 'Could not reach the server — policy update failed.');
      return null;
    }
  },

  // GET /v1/tool-calls — newest first, filters ANDed server-side.
  async listToolCalls(filter?: { agentId?: string; toolId?: string; status?: string; limit?: number; gateway?: boolean }): Promise<ToolCallRecord[] | null> {
    const qs = new URLSearchParams();
    if (filter?.agentId) qs.set('agentId', filter.agentId);
    if (filter?.toolId) qs.set('toolId', filter.toolId);
    if (filter?.status) qs.set('status', filter.status);
    if (filter?.limit) qs.set('limit', String(filter.limit));
    if (filter?.gateway !== undefined) qs.set('gateway', String(filter.gateway));
    try {
      const res = await fetch(`/v1/tool-calls${qs.toString() ? `?${qs}` : ''}`);
      if (!res.ok) return null;
      return ((await res.json()) as { toolCalls: ToolCallRecord[] }).toolCalls;
    } catch {
      ws().pushToast('err', 'Could not reach the server — tool calls unavailable.');
      return null;
    }
  },

  // GET /v1/agents/:id/connectors — the agent's MCP dependency set. Server-side
  // derivation over agents + tools + connectors; the client never walks the
  // tool→connector edge itself, so there is one answer to "which systems will
  // this agent touch?" shared by the bind warning, Pre-Flight, and the panel.
  async listAgentConnectors(agentIdStr: string): Promise<AgentConnectorsResponse | null> {
    try {
      const res = await fetch(`/v1/agents/${encodeURIComponent(agentIdStr)}/connectors`);
      if (!res.ok) return null;
      return (await res.json()) as AgentConnectorsResponse;
    } catch {
      ws().pushToast('err', 'Could not reach the server — connector resolve failed.');
      return null;
    }
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
