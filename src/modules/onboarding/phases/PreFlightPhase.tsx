import { Card, Button } from '@/components/primitives';
import { usePreflight, PreflightList } from '../PreFlight';
import type { PhaseProps } from '../WizardPage';
import { Lock, ArrowRight } from 'lucide-react';

export function PreFlightPhase({ goPhase }: PhaseProps) {
  const { checks, hardBlocked } = usePreflight();
  return (
    <Card>
      {/* Verbatim Blueprint heading (acceptance #5) */}
      <div className="mb-1 text-[13px] font-semibold text-text-hi">11 prerequisites (Plan Section 8)</div>
      <p className="mb-3 text-[12px] text-text-low">
        All 🔴 hard blockers must be green before Phase 1. 🟡 soft blockers may proceed as “pending”. Hard-blocker
        state derives from live kernel state — toggle a connector offline in Tools &amp; MCP and check #4 turns red.
      </p>
      <PreflightList checks={checks} />
      <div className="mt-4 flex items-center gap-3">
        {hardBlocked ? (
          <>
            <Button variant="primary" disabled icon={<Lock size={14} />}>Start Onboarding</Button>
            <span className="text-[12px] text-err">🔒 Hard blockers pending — resolve all 🔴 items to begin.</span>
          </>
        ) : (
          <>
            <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => goPhase(1)}>Start Onboarding</Button>
            <span className="text-[12px] text-ok">All hard blockers green. Soft items can proceed as “pending”.</span>
          </>
        )}
      </div>
    </Card>
  );
}
