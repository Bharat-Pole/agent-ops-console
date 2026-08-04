import { Card, Button } from '@/components/primitives';
import { TagInput } from '../TagInput';
import type { PhaseProps } from '../WizardPage';
import { DOR_ITEMS, DOD_ITEMS } from '@/kernel/wizard';
import { Check, ArrowRight, ArrowLeft } from 'lucide-react';
import { cn } from '@/utils/cn';

function CheckRow({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle} className="flex w-full items-center gap-2.5 rounded-control border border-border bg-raised/30 px-3 py-2 text-left hover:border-border-strong">
      <span className={cn('flex h-4 w-4 items-center justify-center rounded border', checked ? 'border-ok bg-ok text-white' : 'border-border-strong')}>
        {checked && <Check size={11} />}
      </span>
      <span className="text-[13px] text-text-hi">{label}</span>
    </button>
  );
}

export function Phase2WorkPackage({ draft, patch, goPhase }: PhaseProps) {
  const wp = draft.workPackage;
  const dorComplete = DOR_ITEMS.every((i) => wp.dor[i.key]);

  const setDor = (k: string) => patch((d) => ({ ...d, workPackage: { ...d.workPackage, dor: { ...d.workPackage.dor, [k]: !d.workPackage.dor[k] } } }));
  const setDod = (k: string) => patch((d) => ({ ...d, workPackage: { ...d.workPackage, dod: { ...d.workPackage.dod, [k]: !d.workPackage.dod[k] } } }));

  return (
    <div>
      <div className="mb-3 text-[13px] font-semibold text-text-hi">Phase 2 · Create Work Package</div>
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-3 text-[13px] font-semibold text-text-hi">Scope</div>
          <div className="mb-3">
            <div className="mb-1 text-[12px] font-medium text-text-mid">In scope</div>
            <TagInput value={wp.inScope} onChange={(v) => patch((d) => ({ ...d, workPackage: { ...d.workPackage, inScope: v } }))} placeholder="add an in-scope item…" />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Out of scope</div>
            <TagInput value={wp.outScope} onChange={(v) => patch((d) => ({ ...d, workPackage: { ...d.workPackage, outScope: v } }))} placeholder="add an out-of-scope item…" />
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <div className="mb-2 text-[13px] font-semibold text-text-hi">Definition of Ready <span className="text-[11px] font-normal text-err">(hard stops for Next)</span></div>
            <div className="space-y-1.5">
              {DOR_ITEMS.map((i) => <CheckRow key={i.key} label={i.label} checked={wp.dor[i.key]} onToggle={() => setDor(i.key)} />)}
            </div>
          </Card>
          <Card>
            <div className="mb-2 text-[13px] font-semibold text-text-hi">Definition of Done</div>
            <div className="space-y-1.5">
              {DOD_ITEMS.map((i) => <CheckRow key={i.key} label={i.label} checked={wp.dod[i.key]} onToggle={() => setDod(i.key)} />)}
            </div>
          </Card>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => goPhase(1)}>Back</Button>
        <Button variant="primary" icon={<ArrowRight size={14} />} onClick={() => goPhase(3)} disabled={!dorComplete}>Next: Register</Button>
        {!dorComplete && <span className="text-[12px] text-warn">Complete all Definition-of-Ready items to continue.</span>}
      </div>
    </div>
  );
}
