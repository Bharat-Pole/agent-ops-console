import { Modal } from '@/components/primitives/Modal';

/**
 * Orientation for the console.
 *
 * This replaced a demo script that walked through Pre-Flight, "Start
 * Onboarding", the Playground and a Demo Mode banner — none of which exist any
 * more. Help that describes a product you are not using is worse than no help,
 * so this describes the governed path as it actually works.
 */
export function HelpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title="About this console" width="max-w-2xl">
      <div className="space-y-4 text-[13px] text-text-mid">
        <div>
          <div className="mb-1 font-semibold text-text-hi">What this is</div>
          <p>
            A governed workspace for building and running agents. Every asset — prompt, tool,
            knowledge source, workflow — is versioned and approved before an agent can use it, and
            the server enforces that, not the screens.
          </p>
        </div>

        <div>
          <div className="mb-1 font-semibold text-text-hi">The path an agent takes</div>
          <ol className="list-decimal space-y-1 pl-5">
            <li><b>Assets</b> — register a tool, prompt or knowledge source. Each starts as a draft.</li>
            <li><b>Approvals &amp; Gates</b> — a second person approves it. Dual sign-off means two
              people, not one person holding two roles.</li>
            <li><b>Agent Registry</b> — create the agent, then build its workflow on the canvas from
              approved assets only.</li>
            <li><b>Run console</b> — test it on the agent's own page. The same engine and the same
              governance controls run here as in production.</li>
            <li><b>Evaluations</b> — a passing run on the active workflow version is what admits a
              production deployment.</li>
            <li><b>Deploy</b> — from the agent page. The manifest pins exact asset versions, so what
              ran yesterday still runs the same today.</li>
          </ol>
        </div>

        <div>
          <div className="mb-1 font-semibold text-text-hi">Things worth knowing</div>
          <ul className="list-disc space-y-1 pl-5">
            <li>Nothing here is sample data. Empty means nothing has happened yet.</li>
            <li>Write-capable tools can be registered but not bound or executed — the platform is
              advisory-only in this phase, and refuses at three separate layers.</li>
            <li>Editing an approved workflow forks a new draft. What runs is always what was
              approved.</li>
            <li>Drawn edges route execution. An edge with a condition branches; a branch point needs
              one default edge. Loops are refused until iteration limits land.</li>
            <li>Your permissions come from the roles the server granted you — visible under your name
              in the top right.</li>
          </ul>
        </div>
      </div>
    </Modal>
  );
}
