import { useState } from 'react';
import { Check, ArrowLeft, ArrowRight, CheckCircle2 } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Breadcrumbs } from '@/components/shell/Breadcrumbs';
import { Card, Button } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { cn } from '@/utils/cn';

export interface AssetPhaseProps<D> {
  draft: D;
  patch: (u: Partial<D>) => void;
  goPhase: (n: number) => void;
}

export interface AssetPhase<D> {
  key: string;
  label: string;
  // returns an error string to block Next, or null when the phase is valid
  validate?: (d: D) => string | null;
  render: (p: AssetPhaseProps<D>) => React.ReactNode;
}

// Reusable multi-phase wizard shell for onboarding a single asset. Local state
// (short, single-session); mirrors the agent WizardPage stepper.
export function AssetWizard<D>({
  title,
  description,
  breadcrumb,
  steps,
  initial,
  registerLabel = 'Register',
  onRegister,
}: {
  title: string;
  description: string;
  breadcrumb: { label: string; to?: string }[];
  steps: AssetPhase<D>[];
  initial: D;
  registerLabel?: string;
  onRegister: (d: D) => void;
}) {
  const [draft, setDraft] = useState<D>(initial);
  const [idx, setIdx] = useState(0);
  const [showError, setShowError] = useState(false);
  const pushToast = useWorkspace((s) => s.pushToast);

  const patch = (u: Partial<D>) => setDraft((d) => ({ ...d, ...u }));
  const step = steps[idx];
  const error = step.validate?.(draft) ?? null;
  const isLast = idx === steps.length - 1;

  const next = () => {
    if (error) { setShowError(true); pushToast('warn', error); return; }
    setShowError(false);
    setIdx((i) => Math.min(i + 1, steps.length - 1));
  };
  const back = () => { setShowError(false); setIdx((i) => Math.max(i - 1, 0)); };
  const goPhase = (n: number) => { if (n <= idx) { setShowError(false); setIdx(n); } };

  const register = () => {
    if (error) { setShowError(true); pushToast('warn', error); return; }
    onRegister(draft);
  };

  return (
    <div>
      <Breadcrumbs items={breadcrumb} />
      <PageHeader title={title} description={description} />

      <div className="mb-5 flex items-center gap-1 overflow-x-auto rounded-card border border-border bg-surface p-2">
        {steps.map((s, i) => {
          const active = i === idx;
          const done = i < idx;
          const reachable = i <= idx;
          return (
            <div key={s.key} className="flex items-center">
              <button
                disabled={!reachable}
                onClick={() => goPhase(i)}
                className={cn(
                  'flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-[12px] transition',
                  active ? 'bg-accent/15 text-text-hi font-medium' : reachable ? 'text-text-mid hover:bg-raised' : 'text-text-low opacity-50 cursor-not-allowed',
                )}
              >
                <span className={cn('flex h-4 w-4 items-center justify-center rounded-full text-[9px]', done ? 'bg-ok text-white' : active ? 'bg-accent text-white' : 'bg-raised text-text-low')}>
                  {done ? <Check size={10} /> : i + 1}
                </span>
                {s.label}
              </button>
              {i < steps.length - 1 && <span className="mx-0.5 text-text-low">›</span>}
            </div>
          );
        })}
      </div>

      <Card>
        {step.render({ draft, patch, goPhase })}
        {showError && error && <div className="mt-3 rounded-control border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err">{error}</div>}
      </Card>

      <div className="mt-4 flex items-center gap-2">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={back} disabled={idx === 0}>Back</Button>
        {isLast ? (
          <Button variant="primary" icon={<CheckCircle2 size={14} />} onClick={register}>{registerLabel}</Button>
        ) : (
          <Button variant="primary" icon={<ArrowRight size={14} />} onClick={next}>Next</Button>
        )}
      </div>
    </div>
  );
}
