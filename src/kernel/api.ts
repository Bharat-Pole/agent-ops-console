// Section 6 — service façade. Function names mirror the Blueprint's REST API so
// the app could later be rewired to a real backend. NO UI component mutates the
// store directly; everything goes through here. Endpoint-shaped methods
// (synthesize/validate/register/provision/approve/runEvaluation/triggerPipeline)
// are added in their respective milestones.

import { ws } from './store';
import { latency } from './rng';
import type { AuditEvent, EntityType, Persona } from '@/types';
import { PERSONAS } from './constants';

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
  bootstrapWorkspace: services.bootstrapWorkspace,
  decideApproval: services.decideApproval,
  provision: services.provision,
  runEvaluation: services.runEvaluation,
  triggerPipeline: services.triggerPipeline,
  recertify: services.recertify,
  setLifecycle: services.setLifecycle,
  bindTool: services.bindTool,
  healthcheck: services.healthcheck,
  toggleConnectorOffline: services.toggleConnectorOffline,
  proposeConfigChange: services.proposeConfigChange,
  enableDemoMode: services.enableDemoMode,
  chatWithAgent: services.chatWithAgent,

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
