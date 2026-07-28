import type { CapabilityTier } from '@/types';
import { TIER_LABEL } from '@/kernel/constants';
import { Tooltip } from './Tooltip';
import { cn } from '@/utils/cn';

// Section 3.3 — TierBadge: colored badge with plain-language tooltip
// (e.g., Standardized → "Knowledge Assistant").
const CLS: Record<CapabilityTier, string> = {
  minimal: 'text-tier-minimal border-tier-minimal/40 bg-tier-minimal/10',
  standardized: 'text-tier-standardized border-tier-standardized/40 bg-tier-standardized/10',
  advanced: 'text-tier-advanced border-tier-advanced/40 bg-tier-advanced/10',
};

export function TierBadge({ tier, showLabel }: { tier: CapabilityTier; showLabel?: boolean }) {
  return (
    <Tooltip content={`${cap(tier)} → “${TIER_LABEL[tier]}”`}>
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold border capitalize',
          CLS[tier],
        )}
      >
        {tier}
        {showLabel && <span className="font-normal opacity-80">· {TIER_LABEL[tier]}</span>}
      </span>
    </Tooltip>
  );
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
