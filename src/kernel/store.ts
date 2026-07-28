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
  Job,
  Persona,
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

export interface UiState {
  persona: Persona;
  navCollapsed: boolean;
  searchOpen: boolean;
  toasts: Toast[];
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

  // ---- ui actions
  setPersona: (p: Persona) => void;
  toggleNav: () => void;
  setNavCollapsed: (v: boolean) => void;
  setSearchOpen: (v: boolean) => void;
  pushToast: (kind: ToastKind, message: string) => void;
  dismissToast: (id: string) => void;

  // ---- entity mutators (called by the kernel)
  addAuditEvent: (evt: AuditEvent) => void;
  upsertJob: (job: Job) => void;
  updateJob: (id: string, patch: Partial<Job>) => void;
  removeJob: (id: string) => void;

  addAgent: (agent: AgentRecord) => void;
  patchAgent: (agentId: string, updater: (a: AgentRecord) => AgentRecord) => void;

  addApproval: (item: ApprovalItem) => void;
  patchApproval: (id: string, patch: Partial<ApprovalItem>) => void;

  upsertEvalPack: (pack: EvaluationPack) => void;
  upsertSource: (s: KnowledgeSource) => void;
  patchSource: (id: string, updater: (s: KnowledgeSource) => KnowledgeSource) => void;
  addPipelineRun: (run: PipelineRun) => void;
  patchPipelineRun: (id: string, updater: (r: PipelineRun) => PipelineRun) => void;

  patchConnector: (id: string, patch: Partial<McpConnector>) => void;
  upsertPrompt: (p: PromptAsset) => void;
  patchTool: (id: string, patch: Partial<ToolAsset>) => void;
  setTelemetry: (t: AgentTelemetry[]) => void;

  addDraft: (d: OnboardingDraft) => void;
  patchDraft: (id: string, updater: (d: OnboardingDraft) => OnboardingDraft) => void;
  removeDraft: (id: string) => void;
}

const DEFAULT_UI: UiState = {
  persona: 'business_owner',
  navCollapsed: false,
  searchOpen: false,
  toasts: [],
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

  // ---- lifecycle ----------------------------------------------------------
  reset: () => {
    resetLatencyRng();
    set((s) => ({
      ...createInitialWorkspace(),
      jobs: [],
      drafts: SEED_DRAFTS.map((d) => structuredClone(d)),
      _seq: 1,
      // preserve the current persona + nav layout across a reset; clear toasts
      ui: { ...DEFAULT_UI, persona: s.ui.persona, navCollapsed: s.ui.navCollapsed },
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

  // ---- ui -----------------------------------------------------------------
  setPersona: (persona) => set((s) => ({ ui: { ...s.ui, persona } })),
  toggleNav: () => set((s) => ({ ui: { ...s.ui, navCollapsed: !s.ui.navCollapsed } })),
  setNavCollapsed: (v) => set((s) => ({ ui: { ...s.ui, navCollapsed: v } })),
  setSearchOpen: (v) => set((s) => ({ ui: { ...s.ui, searchOpen: v } })),
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
      const exists = s.prompts.some((x) => x.id === p.id && x.version === p.version);
      return {
        prompts: exists
          ? s.prompts.map((x) => (x.id === p.id && x.version === p.version ? p : x))
          : [...s.prompts, p],
      };
    }),
  patchTool: (id, patch) =>
    set((s) => ({ tools: s.tools.map((t) => (t.id === id ? { ...t, ...patch } : t)) })),
  setTelemetry: (t) => set({ telemetry: t }),

  addDraft: (d) => set((s) => ({ drafts: [...s.drafts, d] })),
  patchDraft: (id, updater) => set((s) => ({ drafts: s.drafts.map((d) => (d.id === id ? updater(d) : d)) })),
  removeDraft: (id) => set((s) => ({ drafts: s.drafts.filter((d) => d.id !== id) })),
}));

// Convenience non-hook accessors for the kernel.
export const ws = () => useWorkspace.getState();
