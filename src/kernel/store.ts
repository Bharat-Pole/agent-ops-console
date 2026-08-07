// Section 6.1 — the single workspace store (the platform kernel state).
// State lives in memory only (NO localStorage/sessionStorage/IndexedDB anywhere,
// acceptance #11). Persistence is via Export/Import Workspace JSON (Section 6.6).
//
// Mutation discipline (Section 6): UI components never mutate the store directly;
// they call kernel/api.ts, which calls the well-named mutators below (or the
// vanilla setState/getState). UI reads state via the useWorkspace hook.

import { create } from 'zustand';
import type {
  AgentRecord,
  PromptAsset,
  ToolAsset,
  McpConnector,
  KnowledgeSource,
  PipelineRun,
  EvaluationPack,
  ApprovalItem,
  AuditEvent,
  AgentTelemetry,
  ModelAsset,
  Job,
  Persona,
  RealKnowledgeSource,
  PolicyRule,
  PathDefinition,
  GovernanceException,
  AgentCard,
  Environment,
} from '@/types';
import { createInitialWorkspace, type WorkspaceData } from '@/seed';
import { SEED_DRAFTS } from '@/seed/drafts';
import type { OnboardingDraft } from './wizard';
import { resetLatencyRng } from './rng';

export type ToastKind = 'info' | 'ok' | 'warn' | 'err';
export interface Toast {
  id: string;
  kind: ToastKind;
  message: string;
}

// Admin Console → Feature Flags (Blueprint §3 cross-cutting admin module).
// Nav-level gates only, deliberately: flipping one off hides the module from
// the left nav / Cmd+K, it does not block direct navigation to the route —
// same scope as most real feature-flag systems' UI-visibility gates.
export interface FeatureFlags {
  model_repository: boolean;
  workflow_builder: boolean;
}

export interface UiState {
  persona: Persona;
  navCollapsed: boolean;
  searchOpen: boolean;
  toasts: Toast[];
  featureFlags: FeatureFlags;
}

export interface ExportShape extends WorkspaceData {
  jobs: Job[];
  drafts: OnboardingDraft[];
  _seq: number;
  _exported_at: string;
  _schema: 'brightspeed-agent-ops/v1';
}

export interface WorkspaceState extends WorkspaceData {
  jobs: Job[];
  drafts: OnboardingDraft[];
  ui: UiState;
  _seq: number;

  // ---- lifecycle
  reset: () => void;
  importWorkspace: (data: Partial<ExportShape>) => void;
  exportWorkspace: () => ExportShape;
  nextId: (prefix: string) => string;
  // Overwrites the server-owned slices (agents/approvals/auditLog/evalPacks)
  // with persisted truth from GET /v1/bootstrap. Called once on app load.
  // Note: "Reset demo" (reset(), below) only resets these client-side — it
  // does not reset the server's DB, so a hard refresh after a demo reset will
  // re-hydrate the pre-reset persisted state. Out of scope for this round.
  hydrateFromServer: (data: { agents: AgentRecord[]; approvals: ApprovalItem[]; auditLog: AuditEvent[]; evalPacks: EvaluationPack[]; prompts?: PromptAsset[]; knowledgeSources?: RealKnowledgeSource[]; tools?: ToolAsset[]; connectors?: McpConnector[]; models?: ModelAsset[]; policyRules?: PolicyRule[]; pathDefinitions?: PathDefinition[]; governanceExceptions?: GovernanceException[]; telemetry?: AgentTelemetry[]; featureFlags?: Partial<FeatureFlags>; a2aCards?: AgentCard[]; agentEnvironments?: Record<string, Environment> }) => void;
  // Real knowledge sources from the backend DB — separate from the Prov-wrapped
  // `sources: KnowledgeSource[]` (WorkspaceData/seed) kept for existing agent configs.
  knowledgeSources: RealKnowledgeSource[];
  upsertRealSource: (s: RealKnowledgeSource) => void;
  removeRealSource: (id: string) => void;
  setRealSources: (sources: RealKnowledgeSource[]) => void;
  // Real current environment per agent (deployment_records, not the static
  // config.deployment.environment field which never updates after a real
  // promote()/rollback()) — read-only, refreshed on every bootstrap.
  agentEnvironments: Record<string, Environment>;

  // ---- ui actions
  setPersona: (p: Persona) => void;
  toggleNav: () => void;
  setNavCollapsed: (v: boolean) => void;
  setSearchOpen: (v: boolean) => void;
  setFeatureFlag: (key: keyof FeatureFlags, value: boolean) => void;
  pushToast: (kind: ToastKind, message: string) => void;
  dismissToast: (id: string) => void;

  // ---- entity mutators (called by the kernel)
  addAuditEvent: (evt: AuditEvent) => void;
  upsertJob: (job: Job) => void;
  updateJob: (id: string, patch: Partial<Job>) => void;
  removeJob: (id: string) => void;

  addAgent: (agent: AgentRecord) => void;
  patchAgent: (agentId: string, updater: (a: AgentRecord) => AgentRecord) => void;
  removeAgent: (agentId: string) => void;

  addApproval: (item: ApprovalItem) => void;
  patchApproval: (id: string, patch: Partial<ApprovalItem>) => void;

  upsertEvalPack: (pack: EvaluationPack) => void;
  upsertSource: (s: KnowledgeSource) => void;
  patchSource: (id: string, updater: (s: KnowledgeSource) => KnowledgeSource) => void;
  addPipelineRun: (run: PipelineRun) => void;
  patchPipelineRun: (id: string, updater: (r: PipelineRun) => PipelineRun) => void;

  patchConnector: (id: string, patch: Partial<McpConnector>) => void;
  upsertPrompt: (p: PromptAsset) => void;
  addTool: (tool: ToolAsset) => void;
  patchTool: (id: string, patch: Partial<ToolAsset>) => void;
  addModel: (model: ModelAsset) => void;
  patchModel: (id: string, patch: Partial<ModelAsset>) => void;
  removeModel: (id: string) => void;
  upsertPolicyRule: (rule: PolicyRule) => void;
  upsertPathDefinition: (pd: PathDefinition) => void;
  addException: (exc: GovernanceException) => void;
  patchException: (id: string, patch: Partial<GovernanceException>) => void;
  setTelemetry: (t: AgentTelemetry[]) => void;
  patchA2ACard: (agentId: string, patch: Partial<AgentCard>) => void;

  addDraft: (d: OnboardingDraft) => void;
  patchDraft: (id: string, updater: (d: OnboardingDraft) => OnboardingDraft) => void;
  removeDraft: (id: string) => void;
}

const DEFAULT_UI: UiState = {
  persona: 'business_owner',
  navCollapsed: false,
  searchOpen: false,
  toasts: [],
  featureFlags: { model_repository: true, workflow_builder: true },
};

function agentKey(a: AgentRecord): string {
  return a.config.identity.agent_id.value;
}

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  ...createInitialWorkspace(),
  jobs: [],
  drafts: SEED_DRAFTS.map((d) => structuredClone(d)),
  ui: { ...DEFAULT_UI },
  _seq: 1,
  knowledgeSources: [],
  agentEnvironments: {},

  // ---- lifecycle ----------------------------------------------------------
  reset: () => {
    resetLatencyRng();
    set((s) => ({
      ...createInitialWorkspace(),
      jobs: [],
      drafts: SEED_DRAFTS.map((d) => structuredClone(d)),
      _seq: 1,
      // preserve the current persona + nav layout + feature flags across a reset; clear toasts
      ui: { ...DEFAULT_UI, persona: s.ui.persona, navCollapsed: s.ui.navCollapsed, featureFlags: s.ui.featureFlags },
    }));
  },

  importWorkspace: (data) => {
    set((s) => ({
      agents: data.agents ?? s.agents,
      prompts: data.prompts ?? s.prompts,
      tools: data.tools ?? s.tools,
      connectors: data.connectors ?? s.connectors,
      sources: data.sources ?? s.sources,
      pipelineRuns: data.pipelineRuns ?? s.pipelineRuns,
      evalPacks: data.evalPacks ?? s.evalPacks,
      approvals: data.approvals ?? s.approvals,
      auditLog: data.auditLog ?? s.auditLog,
      telemetry: data.telemetry ?? s.telemetry,
      models: data.models ?? s.models,
      policyRules: data.policyRules ?? s.policyRules,
      pathDefinitions: data.pathDefinitions ?? s.pathDefinitions,
      governanceExceptions: data.governanceExceptions ?? s.governanceExceptions,
      a2aCards: data.a2aCards ?? s.a2aCards,
      jobs: data.jobs ?? [],
      drafts: data.drafts ?? s.drafts,
      // restore the id counter so nextId() cannot collide with imported ids
      _seq: Math.max(s._seq, data._seq ?? 0),
    }));
  },

  exportWorkspace: () => {
    const s = get();
    return {
      agents: s.agents,
      prompts: s.prompts,
      tools: s.tools,
      connectors: s.connectors,
      sources: s.sources,
      pipelineRuns: s.pipelineRuns,
      evalPacks: s.evalPacks,
      approvals: s.approvals,
      auditLog: s.auditLog,
      telemetry: s.telemetry,
      models: s.models,
      policyRules: s.policyRules,
      pathDefinitions: s.pathDefinitions,
      governanceExceptions: s.governanceExceptions,
      a2aCards: s.a2aCards,
      jobs: s.jobs,
      drafts: s.drafts,
      _seq: s._seq,
      _exported_at: new Date(0).toISOString(), // deterministic stamp (no Date.now)
      _schema: 'brightspeed-agent-ops/v1',
    };
  },

  nextId: (prefix) => {
    const n = get()._seq;
    set({ _seq: n + 1 });
    return `${prefix}-${n.toString(36).padStart(4, '0')}`;
  },

  hydrateFromServer: (data) =>
    set((s) => ({
      agents: data.agents,
      approvals: data.approvals,
      auditLog: data.auditLog,
      evalPacks: data.evalPacks,
      prompts: data.prompts ?? s.prompts,
      knowledgeSources: data.knowledgeSources ?? s.knowledgeSources,
      tools: data.tools ?? s.tools,
      connectors: data.connectors ?? s.connectors,
      models: data.models ?? s.models,
      policyRules: data.policyRules ?? s.policyRules,
      pathDefinitions: data.pathDefinitions ?? s.pathDefinitions,
      governanceExceptions: data.governanceExceptions ?? s.governanceExceptions,
      telemetry: data.telemetry ?? s.telemetry,
      a2aCards: data.a2aCards ?? s.a2aCards,
      agentEnvironments: data.agentEnvironments ?? s.agentEnvironments,
      ui: data.featureFlags ? { ...s.ui, featureFlags: { ...s.ui.featureFlags, ...data.featureFlags } } : s.ui,
    })),

  // ---- ui -----------------------------------------------------------------
  setPersona: (persona) => set((s) => ({ ui: { ...s.ui, persona } })),
  toggleNav: () => set((s) => ({ ui: { ...s.ui, navCollapsed: !s.ui.navCollapsed } })),
  setNavCollapsed: (v) => set((s) => ({ ui: { ...s.ui, navCollapsed: v } })),
  setSearchOpen: (v) => set((s) => ({ ui: { ...s.ui, searchOpen: v } })),
  setFeatureFlag: (key, value) => set((s) => ({ ui: { ...s.ui, featureFlags: { ...s.ui.featureFlags, [key]: value } } })),
  pushToast: (kind, message) =>
    set((s) => {
      const id = `toast-${s._seq}`;
      return {
        _seq: s._seq + 1,
        ui: { ...s.ui, toasts: [...s.ui.toasts, { id, kind, message }] },
      };
    }),
  dismissToast: (id) =>
    set((s) => ({ ui: { ...s.ui, toasts: s.ui.toasts.filter((t) => t.id !== id) } })),

  // ---- mutators -----------------------------------------------------------
  addAuditEvent: (evt) => set((s) => ({ auditLog: [evt, ...s.auditLog] })),

  upsertJob: (job) =>
    set((s) => {
      const exists = s.jobs.some((j) => j.id === job.id);
      return { jobs: exists ? s.jobs.map((j) => (j.id === job.id ? job : j)) : [...s.jobs, job] };
    }),
  updateJob: (id, patch) =>
    set((s) => ({ jobs: s.jobs.map((j) => (j.id === id ? { ...j, ...patch } : j)) })),
  removeJob: (id) => set((s) => ({ jobs: s.jobs.filter((j) => j.id !== id) })),

  addAgent: (agent) => set((s) => ({ agents: [...s.agents, agent] })),
  patchAgent: (id, updater) =>
    set((s) => ({ agents: s.agents.map((a) => (agentKey(a) === id ? updater(a) : a)) })),
  removeAgent: (id) => set((s) => ({ agents: s.agents.filter((a) => agentKey(a) !== id) })),

  addApproval: (item) => set((s) => ({ approvals: [...s.approvals, item] })),
  patchApproval: (id, patch) =>
    set((s) => ({ approvals: s.approvals.map((a) => (a.id === id ? { ...a, ...patch } : a)) })),

  upsertEvalPack: (pack) =>
    set((s) => {
      const exists = s.evalPacks.some((p) => p.id === pack.id);
      return {
        evalPacks: exists ? s.evalPacks.map((p) => (p.id === pack.id ? pack : p)) : [...s.evalPacks, pack],
      };
    }),
  upsertSource: (src) =>
    set((s) => {
      const exists = s.sources.some((x) => x.id === src.id);
      return { sources: exists ? s.sources.map((x) => (x.id === src.id ? src : x)) : [...s.sources, src] };
    }),
  patchSource: (id, updater) =>
    set((s) => ({ sources: s.sources.map((x) => (x.id === id ? updater(x) : x)) })),
  addPipelineRun: (run) => set((s) => ({ pipelineRuns: [run, ...s.pipelineRuns] })),
  patchPipelineRun: (id, updater) =>
    set((s) => ({ pipelineRuns: s.pipelineRuns.map((r) => (r.id === id ? updater(r) : r)) })),

  patchConnector: (id, patch) =>
    set((s) => ({ connectors: s.connectors.map((c) => (c.id === id ? { ...c, ...patch } : c)) })),
  upsertPrompt: (p) =>
    set((s) => {
      const exists = s.prompts.some((x) => x.id === p.id);
      return {
        prompts: exists ? s.prompts.map((x) => (x.id === p.id ? p : x)) : [...s.prompts, p],
      };
    }),
  addTool: (tool) => set((s) => ({ tools: [...s.tools, tool] })),
  patchTool: (id, patch) =>
    set((s) => ({ tools: s.tools.map((t) => (t.id === id ? { ...t, ...patch } : t)) })),
  addModel: (model) => set((s) => ({ models: [...s.models, model] })),
  patchModel: (id, patch) =>
    set((s) => ({ models: s.models.map((m) => (m.id === id ? { ...m, ...patch } : m)) })),
  removeModel: (id) => set((s) => ({ models: s.models.filter((m) => m.id !== id) })),
  upsertPolicyRule: (rule) =>
    set((s) => {
      const exists = s.policyRules.some((r) => r.capability_tier === rule.capability_tier && r.risk_tier === rule.risk_tier);
      return {
        policyRules: exists
          ? s.policyRules.map((r) => (r.capability_tier === rule.capability_tier && r.risk_tier === rule.risk_tier ? rule : r))
          : [...s.policyRules, rule],
      };
    }),
  upsertPathDefinition: (pd) =>
    set((s) => {
      const exists = s.pathDefinitions.some((p) => p.path === pd.path);
      return {
        pathDefinitions: exists ? s.pathDefinitions.map((p) => (p.path === pd.path ? pd : p)) : [...s.pathDefinitions, pd],
      };
    }),
  addException: (exc) => set((s) => ({ governanceExceptions: [exc, ...s.governanceExceptions] })),
  patchException: (id, patch) =>
    set((s) => ({ governanceExceptions: s.governanceExceptions.map((e) => (e.id === id ? { ...e, ...patch } : e)) })),
  setTelemetry: (t) => set({ telemetry: t }),
  patchA2ACard: (agentId, patch) =>
    set((s) => ({ a2aCards: s.a2aCards.map((c) => (c.agent_id === agentId ? { ...c, ...patch } : c)) })),

  addDraft: (d) => set((s) => ({ drafts: [...s.drafts, d] })),
  patchDraft: (id, updater) => set((s) => ({ drafts: s.drafts.map((d) => (d.id === id ? updater(d) : d)) })),
  removeDraft: (id) => set((s) => ({ drafts: s.drafts.filter((d) => d.id !== id) })),

  // Real knowledge sources
  upsertRealSource: (src) =>
    set((s) => {
      const exists = s.knowledgeSources.some((x) => x.id === src.id);
      return {
        knowledgeSources: exists
          ? s.knowledgeSources.map((x) => (x.id === src.id ? src : x))
          : [src, ...s.knowledgeSources],
      };
    }),
  removeRealSource: (id) =>
    set((s) => ({ knowledgeSources: s.knowledgeSources.filter((x) => x.id !== id) })),
  setRealSources: (sources) => set({ knowledgeSources: sources }),
}));

// Convenience non-hook accessors for the kernel.
export const ws = () => useWorkspace.getState();
