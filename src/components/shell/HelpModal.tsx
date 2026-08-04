import { Modal } from '@/components/primitives/Modal';

// Surfaces the five cross-module causality moments (Section 10) — the demo's
// "magic moments" — plus the LOCKED governing principles.
export function HelpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title="Brightspeed Agent Ops — demo guide" width="max-w-2xl">
      <div className="space-y-4 text-[13px] text-text-mid">
        <div>
          <div className="mb-1 font-semibold text-text-hi">The thesis</div>
          <p>
            <b>An agent is data, not code.</b> Every screen is a different lens over one canonical
            agent config. An agent is <b>LIVE</b> only when all three tracks — Registry, Runtime,
            Content — are green.
          </p>
        </div>
        <div>
          <div className="mb-1 font-semibold text-text-hi">Five causality moments (Section 10)</div>
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              Toggle a connector offline in <b>Tools &amp; MCP</b> → a Pre-Flight hard blocker turns
              red → the wizard's <b>Start Onboarding</b> disables.
            </li>
            <li>
              Approve the final pending item in <b>Governance</b> → the agent flips to{' '}
              <b>approved</b> → <b>Provision</b> unlocks → swimlanes animate to LIVE → the agent
              appears in <b>Playground</b> and <b>A2A</b>.
            </li>
            <li>
              Run a pipeline refresh in <b>Knowledge &amp; RAG</b> → the Content pill goes ⏳ then ✓
              → the Playground <b>Demo Mode</b> banner auto-clears.
            </li>
            <li>
              A Deep-path agent whose eval score &lt; 90 keeps <b>Promote to Production</b> locked in
              both the wizard and the registry.
            </li>
            <li>Every one of these writes an <b>audit event</b> visible in Governance → Audit Log.</li>
          </ol>
        </div>
        <div>
          <div className="mb-1 font-semibold text-text-hi">Personas</div>
          <p>
            Use the persona switcher (top-right) to change what needs your attention. Only the{' '}
            <b>Governance Officer</b> can approve; the queue is persona-gated as a UI simulation.
          </p>
        </div>
        <div>
          <div className="mb-1 font-semibold text-text-hi">Determinism</div>
          <p>
            All "AI" behavior is deterministic rule/template logic — no LLM calls. <b>Reset demo</b>{' '}
            re-seeds from a fixed seed, so two runs look identical. State is in-memory only; use{' '}
            <b>Export/Import workspace JSON</b> to persist.
          </p>
        </div>
      </div>
    </Modal>
  );
}
