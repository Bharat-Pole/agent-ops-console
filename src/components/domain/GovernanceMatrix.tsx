import type { CapabilityTier, RiskTier, GovernancePath, PathDefinition } from '@/types';
import { GOVERNANCE_MATRIX, TIER_ORDER, RISK_ORDER, PATH_DEFS } from '@/kernel/constants';
import { cn } from '@/utils/cn';

// Section 3.3 / 8.1 — 3×4 grid of capability × risk with the active cell highlighted.
const PATH_CLS: Record<GovernancePath, string> = {
  fast: 'bg-ok/15 text-ok border-ok/30',
  standard: 'bg-accent/15 text-accent border-accent/30',
  deep: 'bg-warn/15 text-warn border-warn/30',
  critical: 'bg-err/15 text-err border-err/30',
};

export function GovernanceMatrix({
  activeTier,
  activeRisk,
  counts,
  onCell,
  matrix = GOVERNANCE_MATRIX,
  pathDefs = PATH_DEFS,
}: {
  activeTier?: CapabilityTier;
  activeRisk?: RiskTier;
  counts?: Record<string, number>; // key `${tier}:${risk}` -> agent count
  onCell?: (tier: CapabilityTier, risk: RiskTier) => void;
  // Real, DB-backed policy (Blueprint §9 policy-as-configuration) — defaults
  // to the static constants for any caller that hasn't been updated yet.
  matrix?: Record<CapabilityTier, Record<RiskTier, GovernancePath>>;
  pathDefs?: Record<GovernancePath, PathDefinition>;
}) {
  return (
    <div className="inline-block overflow-hidden rounded-card border border-border">
      <table className="border-collapse text-[12px]">
        <thead>
          <tr>
            <th className="border-b border-r border-border bg-raised/50 px-3 py-2 text-left text-[10px] uppercase text-text-low">
              Capability \ Risk
            </th>
            {RISK_ORDER.map((r) => (
              <th key={r} className="border-b border-border bg-raised/50 px-3 py-2 text-center text-[10px] uppercase capitalize text-text-low">
                {r}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {TIER_ORDER.map((t) => (
            <tr key={t}>
              <td className="border-r border-border bg-raised/40 px-3 py-2 text-[11px] font-medium capitalize text-text-hi">{t}</td>
              {RISK_ORDER.map((r) => {
                const path = matrix[t][r];
                const active = activeTier === t && activeRisk === r;
                const count = counts?.[`${t}:${r}`];
                return (
                  <td key={r} className="border-l border-t border-border/50 p-1">
                    <button
                      onClick={onCell ? () => onCell(t, r) : undefined}
                      className={cn(
                        'flex h-12 w-24 flex-col items-center justify-center rounded border transition',
                        PATH_CLS[path],
                        active && 'ring-2 ring-offset-1 ring-offset-surface ring-white/70',
                        onCell && 'cursor-pointer hover:brightness-125',
                      )}
                      title={pathDefs[path]?.desc}
                    >
                      <span className="font-semibold">{pathDefs[path]?.label ?? path}</span>
                      {count !== undefined && count > 0 && (
                        <span className="text-[10px] opacity-80">{count} agent{count === 1 ? '' : 's'}</span>
                      )}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
