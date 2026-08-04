import { useState } from 'react';
import type { ReviewCard as ReviewCardT, CapabilityTier } from '@/types';
import { Card, Button, Badge, TierBadge, RiskBadge } from '@/components/primitives';
import { SignalTable } from './SignalTable';
import { ARCHETYPE_LABEL } from '@/kernel/engine/weights';
import { TIER_ORDER, PATH_DEFS } from '@/kernel/constants';
import { titleCase } from '@/utils/format';
import { Bot, AlertTriangle, ChevronDown, ChevronRight, Scale } from 'lucide-react';
import { cn } from '@/utils/cn';

// Section 3.3 / 7.7 — renders the engine's review card. Used as the Phase 1
// proposal and the Phase 3 review. Actions: [Confirm] [Change Tier] [Edit].
export function ReviewCard({
  card,
  onConfirm,
  onOverrideTier,
  onEdit,
  confirmLabel = 'Confirm',
}: {
  card: ReviewCardT;
  onConfirm?: () => void;
  onOverrideTier?: (tier: CapabilityTier) => void;
  onEdit?: () => void;
  confirmLabel?: string;
}) {
  const [showTier, setShowTier] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const g = card.governance_summary;

  return (
    <Card className="border-l-2 border-l-tier-standardized">
      {/* header */}
      <div className="mb-3 flex items-start gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-accent">
          <Bot size={18} />
        </div>
        <div>
          <div className="text-[11px] text-text-low">Engine proposal</div>
          <div className="flex items-center gap-2">
            <span className="text-[16px] font-semibold text-text-hi">“{card.tier_label}”</span>
            <TierBadge tier={card.proposed_tier} />
          </div>
          <div className="text-[11px] text-text-low">archetype: {ARCHETYPE_LABEL[card.proposed_archetype]}</div>
        </div>
      </div>

      {/* tier score chips */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        {TIER_ORDER.map((t) => (
          <div
            key={t}
            className={cn(
              'rounded-control border px-3 py-2 text-center',
              t === card.proposed_tier ? 'border-accent bg-accent/10' : 'border-border bg-raised/40',
            )}
          >
            <div className="text-[10px] capitalize text-text-low">{t}</div>
            <div className={cn('text-[18px] font-semibold', t === card.proposed_tier ? 'text-accent' : 'text-text-mid')}>
              {card.scores[t]}
            </div>
          </div>
        ))}
      </div>

      {/* capability floor callout */}
      {card.capability_floor_note && (
        <div className="mb-3 flex items-start gap-2 rounded-control border border-info/40 bg-info/10 px-3 py-2 text-[12px] text-info">
          <Scale size={14} className="mt-0.5 shrink-0" />
          <span>{card.capability_floor_note}</span>
        </div>
      )}

      {/* signal table */}
      <div className="mb-3">
        <SignalTable breakdown={card.signal_breakdown} />
      </div>

      {/* config summary grid */}
      <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-control border border-border bg-raised/30 p-3 text-[12px]">
        <div><span className="text-text-low">Model </span><span className="mono text-text-hi">{card.config_summary.model}</span></div>
        <div><span className="text-text-low">RAG </span><span className="text-text-hi">{card.config_summary.rag}</span></div>
        <div><span className="text-text-low">Orchestration </span><span className="text-text-hi">{card.config_summary.orchestration}</span></div>
        <div><span className="text-text-low">A2A </span><span className="text-text-hi">{card.config_summary.a2a}</span></div>
        <div className="col-span-2">
          <span className="text-text-low">Tools </span>
          {card.config_summary.tools.length ? card.config_summary.tools.map((t) => <span key={t} className="mono text-text-hi">{t} </span>) : <span className="text-text-mid">none</span>}
        </div>
      </div>

      {/* governance line */}
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-control border border-border bg-raised/30 px-3 py-2 text-[12px]">
        <span className="text-text-low">Risk</span>
        <RiskBadge risk={g.risk_tier} />
        <span className="text-text-low">({g.risk_why})</span>
        <span className="text-text-low">→ Governance</span>
        <Badge tone="accent">{PATH_DEFS[g.governance_path].label}</Badge>
        <span className="text-text-low">· {g.hitl_gates} HITL gate(s) · approvals: {g.approvals_required.map(titleCase).join(', ') || 'auto'}</span>
      </div>

      {/* flagged write tools */}
      {card.flagged_write_tools.length > 0 && (
        <div className="mb-3 flex items-start gap-2 rounded-control border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            ⚠️ Write actions detected — advisory-only enforced. Flagged, <b>not bound</b>:{' '}
            <b>{card.flagged_write_tools.join(', ')}</b>.
          </span>
        </div>
      )}

      {/* fields requiring confirmation */}
      {card.fields_requiring_confirmation.length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-low">Fields requiring confirmation</div>
          <div className="space-y-1">
            {card.fields_requiring_confirmation.map((f, i) => (
              <div key={i} className="flex items-start gap-2 rounded border border-warn/30 bg-warn/5 px-2 py-1.5 text-[12px]">
                <AlertTriangle size={12} className="mt-0.5 shrink-0 text-warn" />
                <div>
                  <span className="mono text-text-hi">{f.field}</span>
                  {f.governance_critical && <span className="ml-1 rounded bg-warn/15 px-1 text-[9px] font-semibold text-warn">GOV</span>}
                  <span className="text-text-mid"> = {String(f.proposed_value)}</span>
                  <span className="text-text-low"> ({f.confidence}) — {f.gap_note}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* why / audit trail */}
      <button onClick={() => setShowWhy((v) => !v)} className="mb-2 flex items-center gap-1 text-[12px] text-accent hover:underline">
        {showWhy ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Why this tier? (audit trail)
      </button>
      {showWhy && (
        <ol className="mb-3 list-decimal space-y-0.5 pl-6 text-[12px] text-text-mid">
          {card.reasoning.map((r, i) => <li key={i}>{r}</li>)}
        </ol>
      )}

      {/* actions */}
      <div className="flex flex-wrap items-center gap-2">
        {onConfirm && <Button variant="primary" onClick={onConfirm}>{confirmLabel}</Button>}
        {onOverrideTier && (
          <div className="relative">
            <Button variant="outline" icon={<ChevronDown size={13} />} onClick={() => setShowTier((v) => !v)}>Change tier</Button>
            {showTier && (
              <div className="absolute left-0 z-40 mt-1 w-44 overflow-hidden rounded-card border border-border-strong bg-raised shadow-2xl">
                {TIER_ORDER.map((t) => (
                  <button key={t} onClick={() => { setShowTier(false); onOverrideTier(t); }} className="block w-full px-3 py-2 text-left text-[13px] capitalize text-text-hi hover:bg-surface">
                    {t}{t === card.proposed_tier ? ' (current)' : ''}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {onEdit && <Button variant="ghost" onClick={onEdit}>Edit details</Button>}
      </div>
    </Card>
  );
}
