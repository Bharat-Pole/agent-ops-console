import type { ApprovalItem, ApprovalStep, ApprovalStatus, GovernancePath } from '@/types';
import { AGENT } from './ids';
import { isoTs, daysFromToday } from './helpers';

function appr(
  id: string,
  agent_id: string,
  step: ApprovalStep,
  path: GovernancePath,
  status: ApprovalStatus,
  requestedDaysAgo: number,
  decidedDaysAgo?: number,
  note?: string | null,
): ApprovalItem {
  return {
    id,
    agent_id,
    step,
    required_by_path: path,
    status,
    actor_persona: status === 'pending' ? null : 'Governance Officer',
    target_ref: null,
    decided_at: status === 'pending' ? null : isoTs(daysFromToday(-(decidedDaysAgo ?? requestedDaysAgo)), 13),
    note: note ?? (status === 'approved' ? 'Approved — schema valid, advisory scope confirmed.' : status === 'rejected' ? 'Rejected.' : null),
    requested_at: isoTs(daysFromToday(-requestedDaysAgo), 9),
  };
}

// Section 12.2 — Approvals. Churn (#6) has 1 of 2 pending (the queue story);
// Contract (#4) has a pending committee item (blocked additionally by eval < 90).
export const SEED_APPROVALS: ApprovalItem[] = [
  // NOC (live, Standard) — both approved
  appr('appr-noc-bo', AGENT.noc, 'business_owner', 'standard', 'approved', 30, 29),
  appr('appr-noc-risk', AGENT.noc, 'risk_officer', 'standard', 'approved', 30, 28),

  // Incident Coordinator (approved, Deep) — all three approved
  appr('appr-incident-bo', AGENT.incident, 'business_owner', 'deep', 'approved', 12, 11),
  appr('appr-incident-risk', AGENT.incident, 'risk_officer', 'deep', 'approved', 12, 10),
  appr('appr-incident-sec', AGENT.incident, 'security_committee', 'deep', 'approved', 12, 9),

  // Contract Clause Finder (in_review, Deep) — bo+risk approved, committee pending
  appr('appr-contract-bo', AGENT.contract, 'business_owner', 'deep', 'approved', 6, 5),
  appr('appr-contract-risk', AGENT.contract, 'risk_officer', 'deep', 'approved', 6, 4),
  appr('appr-contract-sec', AGENT.contract, 'security_committee', 'deep', 'pending', 4, undefined, null),

  // Churn Insight Assistant (registered, Standard) — 1 of 2 pending
  appr('appr-churn-bo', AGENT.churn, 'business_owner', 'standard', 'approved', 3, 2),
  appr('appr-churn-risk', AGENT.churn, 'risk_officer', 'standard', 'pending', 2, undefined, null),

  // Network Capacity Research (live, Standard) — both approved
  appr('appr-capacity-bo', AGENT.capacity, 'business_owner', 'standard', 'approved', 20, 19),
  appr('appr-capacity-risk', AGENT.capacity, 'risk_officer', 'standard', 'approved', 20, 18),

  // Regulatory Filing Coordinator (live, Critical) — all three approved
  appr('appr-reg-bo', AGENT.regulatory, 'business_owner', 'critical', 'approved', 25, 24),
  appr('appr-reg-risk', AGENT.regulatory, 'risk_officer', 'critical', 'approved', 25, 23),
  appr('appr-reg-sec', AGENT.regulatory, 'security_committee', 'critical', 'approved', 25, 22),
];
