import { useParams, useNavigate } from 'react-router-dom';
import { Check } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Breadcrumbs } from '@/components/shell/Breadcrumbs';
import { EmptyState, Button } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import type { OnboardingDraft } from '@/kernel/wizard';
import { nowIso } from '@/kernel/api';
import { cn } from '@/utils/cn';

import { PreFlightPhase } from './phases/PreFlightPhase';
import { Phase1Intent } from './phases/Phase1Intent';
import { Phase2WorkPackage } from './phases/Phase2WorkPackage';
import { Phase3Register } from './phases/Phase3Register';
import { Phase4Configure } from './phases/Phase4Configure';
import { Phase5Governance } from './phases/Phase5Governance';
import { Phase6Evaluate } from './phases/Phase6Evaluate';
import { Phase7Deploy } from './phases/Phase7Deploy';

export interface PhaseProps {
  draft: OnboardingDraft;
  patch: (updater: (d: OnboardingDraft) => OnboardingDraft) => void;
  goPhase: (n: number | 'pre') => void;
}

// Seven phase names are VERBATIM from Section 1.3 (immutable lifecycle).
const STEPS = [
  { key: 'pre', label: 'Pre-Flight' },
  { key: '1', label: 'Capture Intent' },
  { key: '2', label: 'Create Work Package' },
  { key: '3', label: 'Register' },
  { key: '4', label: 'Configure Workflow' },
  { key: '5', label: 'Add Governance Gates' },
  { key: '6', label: 'Evaluate & Approve' },
  { key: '7', label: 'Deploy / Monitor / Improve' },
];

export default function WizardPage() {
  const { draftId, n } = useParams();
  const navigate = useNavigate();
  const draft = useWorkspace((s) => s.drafts.find((d) => d.id === draftId));
  const patchDraft = useWorkspace((s) => s.patchDraft);

  if (!draft) {
    return (
      <div>
        <Breadcrumbs items={[{ label: 'Onboarding', to: '/onboarding' }, { label: 'draft' }]} />
        <EmptyState title="Draft not found" message="This onboarding draft no longer exists." action={<Button variant="primary" onClick={() => navigate('/onboarding')}>Back to onboarding</Button>} />
      </div>
    );
  }

  const patch: PhaseProps['patch'] = (updater) => patchDraft(draft.id, (d) => ({ ...updater(d), updated_at: nowIso() }));

  const goPhase = (target: number | 'pre') => {
    navigate(`/onboarding/${draft.id}/phase/${target}`);
    if (typeof target === 'number') {
      patchDraft(draft.id, (d) => ({ ...d, phase: target, maxPhaseReached: Math.max(d.maxPhaseReached, target), updated_at: nowIso() }));
    }
  };

  const current = n ?? 'pre';
  const props: PhaseProps = { draft, patch, goPhase };

  const stepIndex = (k: string) => STEPS.findIndex((s) => s.key === k);
  const isReachable = (k: string) => k === 'pre' || Number(k) <= draft.maxPhaseReached;

  return (
    <div>
      <Breadcrumbs items={[{ label: 'Onboarding', to: '/onboarding' }, { label: draft.name }]} />
      <PageHeader title={draft.name} description="Seven-phase lifecycle. Tiers change values, never steps." />

      {/* Phase stepper */}
      <div className="mb-5 flex items-center gap-1 overflow-x-auto rounded-card border border-border bg-surface p-2">
        {STEPS.map((s, i) => {
          const active = s.key === current;
          const done = s.key !== 'pre' && Number(s.key) < draft.maxPhaseReached;
          const reachable = isReachable(s.key);
          return (
            <div key={s.key} className="flex items-center">
              <button
                disabled={!reachable}
                onClick={() => reachable && (s.key === 'pre' ? goPhase('pre') : goPhase(Number(s.key)))}
                className={cn(
                  'flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-[12px] transition',
                  active ? 'bg-accent/15 text-text-hi font-medium' : reachable ? 'text-text-mid hover:bg-raised' : 'text-text-low opacity-50 cursor-not-allowed',
                )}
              >
                <span className={cn('flex h-4 w-4 items-center justify-center rounded-full text-[9px]', done ? 'bg-ok text-white' : active ? 'bg-accent text-white' : 'bg-raised text-text-low')}>
                  {done ? <Check size={10} /> : s.key === 'pre' ? '✦' : s.key}
                </span>
                {s.label}
              </button>
              {i < STEPS.length - 1 && <span className="mx-0.5 text-text-low">›</span>}
            </div>
          );
        })}
      </div>

      {/* Phase content */}
      {current === 'pre' && <PreFlightPhase {...props} />}
      {current === '1' && <Phase1Intent {...props} />}
      {current === '2' && <Phase2WorkPackage {...props} />}
      {current === '3' && <Phase3Register {...props} />}
      {current === '4' && <Phase4Configure {...props} />}
      {current === '5' && <Phase5Governance {...props} />}
      {current === '6' && <Phase6Evaluate {...props} />}
      {current === '7' && <Phase7Deploy {...props} />}

      {stepIndex(current) === -1 && <EmptyState title="Unknown phase" />}
    </div>
  );
}
