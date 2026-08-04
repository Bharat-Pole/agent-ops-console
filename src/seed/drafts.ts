import type { OnboardingDraft } from '@/kernel/wizard';
import { emptyWorkPackage } from '@/kernel/wizard';
import { synthesize, type Intent } from '@/kernel/engine';
import { isoTs } from './helpers';

// Section 12.1 #9 — the resume-a-draft story: Vendor SLA Watcher, paused at
// Phase 3 (Register). It lives as a wizard draft (not yet a registered agent),
// so the onboarding drafts table + /onboarding/:draftId/phase/3 resume it.
function vendorDraft(): OnboardingDraft {
  const intent: Intent = {
    objective: 'Watch vendor SLA compliance against contract terms and flag breaches for the vendor management team.',
    intended_audience: 'Vendor management analysts',
    data_sources: ['contracts_repo'],
    tools: ['contract_reader'],
    business_owner: 'priya.vendor@brightspeed.com',
    technical_owner: 'raj.patel@brightspeed.com',
    agent_name: 'Vendor SLA Watcher',
  };
  const synthesis = synthesize(intent);
  const wp = emptyWorkPackage();
  wp.inScope = ['SLA breach detection', 'Contract term lookup'];
  wp.outScope = ['Auto-remediation', 'Vendor communications'];
  wp.dor.objective_measurable = true;
  wp.dor.sources_approved = true;

  return {
    id: 'draft-vendor-sla',
    name: 'Vendor SLA Watcher',
    intent,
    phase: 3,
    maxPhaseReached: 3,
    synthesis,
    confirmedTier: synthesis.capability_tier,
    confirmedRisk: synthesis.risk_tier,
    workPackage: wp,
    elicitationAnswers: {},
    governance: { sensitivity: '', regulatory: '' },
    agent_id: null,
    eval_pack_id: null,
    created_at: isoTs('2026-07-26', 14),
    updated_at: isoTs('2026-07-26', 15),
  };
}

export const SEED_DRAFTS: OnboardingDraft[] = [vendorDraft()];
