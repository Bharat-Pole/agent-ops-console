// Section 6 — service façade. Function names mirror the Blueprint's REST API so
// the app could later be rewired to a real backend. NO UI component mutates the
// store directly; everything goes through here. Endpoint-shaped methods
// (synthesize/validate/register/provision/approve/runEvaluation/triggerPipeline)
// are added in their respective milestones.

import { ws } from './store';
import { latency } from './rng';
import type { AuditEvent, EntityType, Persona, AgentRecord, ToolAsset } from '@/types';
import { PERSONAS } from './constants';

// Resolve an agent's bound tools to transport defs (names-only auth — no secret
// values). Sent to the engine so http_api tools execute for real at run time.
function toolDefsFor(agent: AgentRecord): Array<Record<string, unknown>> {
  const byId = new Map(ws().tools.map((t: ToolAsset) => [t.id, t]));
  const byName = new Map(ws().tools.map((t: ToolAsset) => [t.name, t]));
  return agent.config.tooling.bound_tools.value
    .map((ref) => {
      const key = ref.replace('tools://', '').split('@')[0];
      return byId.get(key) ?? byName.get(key);
    })
    .filter((t): t is ToolAsset => !!t)
    .map((t) => ({
      name: t.name,
      kind: t.kind ?? 'catalog',
      capability: t.capability ?? null, // declared impl; null → engine legacy name-heuristic
      permission: t.permission_ceiling,
      write_capable: t.write_capable,
      http: t.http
        ? {
            method: t.http.method,
            url_template: t.http.url_template,
            query_params: t.http.query_params ?? {},
            headers: t.http.headers ?? {},
            body_template: t.http.body_template ?? null,
            auth_header: t.http.auth_header ?? 'Authorization: Bearer {secret}',
          }
        : null,
      auth_secret_ref: t.http?.auth_secret_ref ?? null, // NAME only
    }));
}

// agent_forge engine service (Python/FastAPI). Configurable via VITE_ENGINE_URL.
// Guard import.meta.env access so this module also loads under node/tsx (tests),
// where import.meta.env is undefined.
const _env = (import.meta as { env?: ImportMetaEnv }).env;
const ENGINE_URL = (_env?.VITE_ENGINE_URL ?? '').replace(/\/$/, '') || 'http://localhost:8099';

export interface EngineGenerateResponse {
  topology: string;
  blockers: Record<string, unknown>;
  file_tree: string[];
  preview: Record<string, string>;
  filename: string;
  artifact_b64: string;
}

// Live-action timestamp. (Determinism that acceptance #10 cares about —
// telemetry charts + eval outcomes — flows from the seeded RNG + fixed
// DEMO_TODAY, not from these action timestamps.)
export function nowIso(): string {
  return new Date().toISOString();
}

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// A simulated read (150–400ms) / mutation (300–700ms) latency (Section 6.3).
export const readLatency = () => latency(150, 400);
export const writeLatency = () => latency(300, 700);

// Append an audit event (Section 8.5) under the active persona.
export function audit(
  action: string,
  entity_type: EntityType,
  entity_id: string,
  detail: string,
  actor?: Persona,
): AuditEvent {
  const s = ws();
  const evt: AuditEvent = {
    id: s.nextId('aud'),
    at: nowIso(),
    actor_persona: PERSONAS[actor ?? s.ui.persona].label,
    action,
    entity_type,
    entity_id,
    detail,
  };
  s.addAuditEvent(evt);
  return evt;
}

function toast(kind: 'info' | 'ok' | 'warn' | 'err', message: string) {
  ws().pushToast(kind, message);
}

function download(filename: string, text: string) {
  const blob = new Blob([text], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

import { services } from './services';

export const api = {
  // ---- Endpoint-shaped services (Section 6). See kernel/services.ts. ----
  synthesize: services.synthesize,
  register: services.register,
  decideApproval: services.decideApproval,
  provision: services.provision,
  runEvaluation: services.runEvaluation,
  triggerPipeline: services.triggerPipeline,
  finalizeRegistry: services.finalizeRegistry,
  recertify: services.recertify,
  setLifecycle: services.setLifecycle,
  bindTool: services.bindTool,
  healthcheck: services.healthcheck,
  toggleConnectorOffline: services.toggleConnectorOffline,
  proposeConfigChange: services.proposeConfigChange,
  updateOrchestration: services.updateOrchestration,
  enableDemoMode: services.enableDemoMode,

  // ---- agent_forge (spec → code) — calls the Python engine service ----
  // Generate a runnable LangGraph project from an agent's canonical config.
  // Degrades gracefully (toast + null) when the engine service isn't running.
  async generateProject(
    agent: AgentRecord,
    llmTarget: 'aistudio' | 'vertex' = 'aistudio',
  ): Promise<EngineGenerateResponse | null> {
    try {
      const res = await fetch(`${ENGINE_URL}/v1/agents/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent, llm_target: llmTarget, tools: toolDefsFor(agent) }),
      });
      if (!res.ok) {
        toast('err', `Engine error ${res.status} generating project.`);
        return null;
      }
      const data = (await res.json()) as EngineGenerateResponse;
      audit(
        'generate_project',
        'agent',
        agent.config.identity.agent_id.value,
        `Generated ${data.topology} LangGraph project (${data.file_tree.length} files, ${llmTarget}).`,
      );
      toast('ok', `Generated ${data.topology} project — ${data.file_tree.length} files.`);
      return data;
    } catch {
      toast('warn', 'Engine offline — start agent_forge: (cd engine && uvicorn service.app:app --port 8099)');
      return null;
    }
  },

  // Is the agent_forge engine service reachable, and what credentials does it hold?
  async engineHealth(): Promise<{ up: boolean; hasEnvKey: boolean; hasDefaultKey: boolean; hasAnthropicKey: boolean; secretNames: string[] }> {
    try {
      const res = await fetch(`${ENGINE_URL}/v1/health`, { method: 'GET' });
      if (!res.ok) return { up: false, hasEnvKey: false, hasDefaultKey: false, hasAnthropicKey: false, secretNames: [] };
      const data = await res.json();
      return {
        up: true,
        hasEnvKey: data.has_env_key === true,
        hasDefaultKey: data.has_default_key === true,
        hasAnthropicKey: data.has_anthropic_key === true,
        secretNames: Array.isArray(data.secret_names) ? data.secret_names : [],
      };
    } catch {
      return { up: false, hasEnvKey: false, hasDefaultKey: false, hasAnthropicKey: false, secretNames: [] };
    }
  },

  // ---- secrets vault (engine-side; names only ever cross this boundary) ----
  async listSecrets(): Promise<string[] | null> {
    try {
      const res = await fetch(`${ENGINE_URL}/v1/secrets`);
      if (!res.ok) return null;
      const data = await res.json();
      return Array.isArray(data.names) ? data.names : [];
    } catch {
      return null;
    }
  },

  async putSecret(name: string, value: string): Promise<string[] | null> {
    try {
      const res = await fetch(`${ENGINE_URL}/v1/secrets/${encodeURIComponent(name)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast('err', err?.detail ?? `Failed to save secret (${res.status}).`);
        return null;
      }
      audit('secret_put', 'workspace', name, `Vault secret "${name}" set/updated (value stored engine-side).`);
      const data = await res.json();
      return Array.isArray(data.names) ? data.names : [];
    } catch {
      toast('warn', 'Engine offline — cannot save secret.');
      return null;
    }
  },

  async deleteSecret(name: string): Promise<string[] | null> {
    try {
      const res = await fetch(`${ENGINE_URL}/v1/secrets/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (!res.ok) return null;
      audit('secret_delete', 'workspace', name, `Vault secret "${name}" deleted.`);
      const data = await res.json();
      return Array.isArray(data.names) ? data.names : [];
    } catch {
      return null;
    }
  },

  // Run the REAL agent live via the engine (LangGraph + Gemini). Returns the reply
  // + a small trace, or null when the engine is unreachable (caller falls back to
  // the deterministic simulation).
  async runAgentLive(
    agent: AgentRecord,
    message: string,
    threadId: string,
    snippets: { doc_id: string; text: string }[],
    llmTarget: 'aistudio' | 'vertex' | 'claude' = 'aistudio',
  ): Promise<{ reply: string; trace: Record<string, unknown>; error: string | null } | null> {
    try {
      const res = await fetch(`${ENGINE_URL}/v1/agents/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent,
          message,
          thread_id: threadId,
          llm_target: llmTarget,
          knowledge_snippets: snippets,
          tools: toolDefsFor(agent), // executable tool defs (names-only auth)
          // key entered in the UI (Playground → API key); beats the engine's env.
          // The browser key is a GEMINI key — never send it on a Claude run.
          api_key: llmTarget === 'claude' ? null : (ws().ui.geminiKey || null),
        }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      // Defensive: never let a non-string reply reach React (content blocks etc.)
      if (data && typeof data.reply !== 'string') {
        data.reply = Array.isArray(data.reply)
          ? data.reply
              .map((b: unknown) => (typeof b === 'string' ? b : ((b as { text?: string })?.text ?? '')))
              .join('')
          : JSON.stringify(data.reply ?? '');
      }
      if (data && (typeof data.trace !== 'object' || data.trace === null)) data.trace = {};
      return data;
    } catch {
      return null;
    }
  },

  // Live "try it" for an HTTP GET tool (wizard/detail Test). Engine executes it
  // (GET only; mutating refused) and injects the vault secret; graceful null offline.
  async tryTool(
    def: Record<string, unknown>,
    query: string,
  ): Promise<{ ok: boolean; status?: number; text?: string; error?: string } | null> {
    try {
      const res = await fetch(`${ENGINE_URL}/v1/tools/try`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: def, query }),
      });
      if (!res.ok) return { ok: false, error: `engine error ${res.status}` };
      return await res.json();
    } catch {
      return null;
    }
  },

  // Decode the base64 zip the engine returned and download it.
  downloadArtifact(b64: string, filename: string): void {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob = new Blob([bytes], { type: 'application/zip' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  // Reset demo — re-seeds the kernel from /seed (Section 3.1, acceptance #10).
  reset(): void {
    ws().reset();
    toast('ok', 'Demo reset — kernel re-seeded from the fixed seed.');
  },

  // Section 6.6 — Export workspace JSON (the persistence story; no browser storage).
  exportWorkspace(): void {
    const data = ws().exportWorkspace();
    download('brightspeed-agent-ops-workspace.json', JSON.stringify(data, null, 2));
    audit('export_workspace', 'workspace', 'workspace', 'Exported full workspace to JSON.');
    toast('ok', 'Workspace exported.');
  },

  // Section 6.6 — Import re-hydrates the store from a previously exported file.
  async importWorkspace(file: File): Promise<void> {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      if (parsed?._schema !== 'brightspeed-agent-ops/v1') {
        toast('err', 'Not a Brightspeed workspace file.');
        return;
      }
      ws().importWorkspace(parsed);
      audit('import_workspace', 'workspace', 'workspace', `Imported ${parsed.agents?.length ?? 0} agents.`);
      toast('ok', 'Workspace imported.');
    } catch {
      toast('err', 'Import failed — invalid JSON.');
    }
  },
};
