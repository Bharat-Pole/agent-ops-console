import type { SignalBreakdown, SignalId } from '@/types';
import { SIGNAL_LABEL } from '@/kernel/engine/weights';
import { cn } from '@/utils/cn';

const IDS: SignalId[] = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'];

// Section 7.2 / 9.2 — the six-signal breakdown table (fired dot + why + weights).
export function SignalTable({ breakdown }: { breakdown: SignalBreakdown }) {
  return (
    <div className="overflow-hidden rounded-card border border-border">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border bg-raised/50 text-left text-[10px] uppercase tracking-wide text-text-low">
            <th className="px-3 py-1.5">Signal</th>
            <th className="px-2 py-1.5 text-center">Fired</th>
            <th className="px-2 py-1.5 text-center" title="weight when fired (Minimal)">Min</th>
            <th className="px-2 py-1.5 text-center" title="weight when fired (Standardized)">Std</th>
            <th className="px-2 py-1.5 text-center" title="weight when fired (Advanced)">Adv</th>
            <th className="px-3 py-1.5">Why</th>
          </tr>
        </thead>
        <tbody>
          {IDS.map((id) => {
            const s = breakdown[id];
            return (
              <tr key={id} className={cn('border-b border-border/60 last:border-0', !s.fired && 'opacity-55')}>
                <td className="px-3 py-1.5">
                  <span className="mono text-text-hi">{id}</span>{' '}
                  <span className="text-text-mid">{SIGNAL_LABEL[id]}</span>
                </td>
                <td className="px-2 py-1.5 text-center">
                  <span className={cn('inline-block h-2 w-2 rounded-full', s.fired ? 'bg-ok' : 'bg-border-strong')} />
                </td>
                <td className="px-2 py-1.5 text-center mono text-text-low">{s.weight_minimal}</td>
                <td className="px-2 py-1.5 text-center mono text-text-low">+{s.weight_standardized}</td>
                <td className="px-2 py-1.5 text-center mono text-text-low">+{s.weight_advanced}</td>
                <td className="px-3 py-1.5 text-text-low">{s.why}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
