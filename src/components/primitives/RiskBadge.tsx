import type { RiskTier } from '@/types';
import { Tooltip } from './Tooltip';
import { cn } from '@/utils/cn';

// Section 3.3 — RiskBadge with plain-language tooltip.
const CLS: Record<RiskTier, string> = {
  low: 'text-risk-low border-risk-low/40 bg-risk-low/10',
  medium: 'text-risk-medium border-risk-medium/40 bg-risk-medium/10',
  high: 'text-risk-high border-risk-high/40 bg-risk-high/10',
  critical: 'text-risk-critical border-risk-critical/40 bg-risk-critical/10',
};

const BLURB: Record<RiskTier, string> = {
  low: 'Low risk — advisory-only, no sensitive data.',
  medium: 'Medium risk — internal data sources present.',
  high: 'High risk — customer/PII or write-intent detected.',
  critical: 'Critical risk — regulated/financial data; runtime HITL per action.',
};

export function RiskBadge({ risk }: { risk: RiskTier }) {
  return (
    <Tooltip content={BLURB[risk]}>
      <span
        className={cn(
          'inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold border capitalize',
          CLS[risk],
        )}
      >
        {risk}
      </span>
    </Tooltip>
  );
}
