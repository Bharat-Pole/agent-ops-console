import type { AuditEvent, EntityType } from '@/types';
import { AGENT } from './ids';
import { isoTs, daysFromToday } from './helpers';

let n = 0;
function ev(
  daysAgo: number,
  hour: number,
  persona: string,
  action: string,
  entity_type: EntityType,
  entity_id: string,
  detail: string,
): AuditEvent {
  n += 1;
  return {
    id: `aud-seed-${String(n).padStart(3, '0')}`,
    at: isoTs(daysFromToday(-daysAgo), hour, (n * 7) % 60),
    actor_persona: persona,
    action,
    entity_type,
    entity_id,
    detail,
  };
}

const BO = 'Business Owner';
const PE = 'Platform Engineer';
const GO = 'Governance Officer';

// Section 12.2 — ~40 back-dated audit events.
export const SEED_AUDIT: AuditEvent[] = [
  // HR Policy Bot
  ev(88, 9, BO, 'create_agent', 'agent', AGENT.hr, 'Created HR Policy Bot (Minimal, Fast path).'),
  ev(88, 10, GO, 'auto_approve', 'agent', AGENT.hr, 'Fast-path auto-approval (schema valid).'),
  ev(84, 11, PE, 'provision', 'agent', AGENT.hr, 'Runtime provisioned on Cloud Run; agent LIVE.'),
  ev(2, 14, BO, 'config_change', 'agent', AGENT.hr, 'Updated persona_role wording.'),

  // Field Ops FAQ Bot
  ev(46, 9, BO, 'create_agent', 'agent', AGENT.faq, 'Created Field Ops FAQ Bot (Minimal, Fast path).'),
  ev(46, 10, GO, 'auto_approve', 'agent', AGENT.faq, 'Fast-path auto-approval.'),
  ev(40, 11, PE, 'provision', 'agent', AGENT.faq, 'Runtime provisioned; agent LIVE.'),

  // NOC Incident Summarizer
  ev(31, 9, BO, 'create_agent', 'agent', AGENT.noc, 'Created NOC Incident Summarizer (Standardized).'),
  ev(30, 10, BO, 'register', 'agent', AGENT.noc, 'Registered; approvals requested (Standard path).'),
  ev(29, 13, GO, 'approve', 'approval', 'appr-noc-bo', 'Business owner approval granted.'),
  ev(28, 13, GO, 'approve', 'approval', 'appr-noc-risk', 'Risk officer review passed.'),
  ev(30, 11, PE, 'provision', 'agent', AGENT.noc, 'Runtime + content provisioned; agent LIVE.'),
  ev(2, 9, BO, 'run_evaluation', 'eval', AGENT.noc, 'Eval pack scored 96.'),
  ev(1, 3, PE, 'pipeline_refresh', 'source', 'incident-db-prod-v3', 'Scheduled re-index completed (4,931 docs).'),

  // Incident Response Coordinator
  ev(14, 9, BO, 'create_agent', 'agent', AGENT.incident, 'Created Incident Response Coordinator (Advanced).'),
  ev(14, 10, BO, 'synthesize', 'agent', AGENT.incident, 'Engine decomposed 4 sub-agents; slack_notifier + email_sender FLAGGED (advisory-only).'),
  ev(12, 10, BO, 'register', 'agent', AGENT.incident, 'Registered; Deep path (committee approval required).'),
  ev(11, 13, GO, 'approve', 'approval', 'appr-incident-bo', 'Business owner approval granted.'),
  ev(10, 13, GO, 'approve', 'approval', 'appr-incident-risk', 'Risk officer review passed (risk_tier=high).'),
  ev(9, 13, GO, 'approve', 'approval', 'appr-incident-sec', 'Security committee approval granted.'),
  ev(0, 8, PE, 'provision', 'agent', AGENT.incident, 'Provisioning started — Runtime ⏳ Content ⏳.'),

  // Contract Clause Finder (failing eval story)
  ev(9, 9, BO, 'create_agent', 'agent', AGENT.contract, 'Created Contract Clause Finder (Standardized, Deep path).'),
  ev(9, 3, PE, 'pipeline_refresh', 'source', 'contracts-repo', 'Indexed contracts repository (1,180 docs).'),
  ev(6, 10, BO, 'register', 'agent', AGENT.contract, 'Registered; Deep path.'),
  ev(5, 13, GO, 'approve', 'approval', 'appr-contract-bo', 'Business owner approval granted.'),
  ev(4, 13, GO, 'approve', 'approval', 'appr-contract-risk', 'Risk officer review passed.'),
  ev(2, 11, BO, 'run_evaluation', 'eval', AGENT.contract, 'Eval pack scored 82 — 2 grounding cases failed (score_threshold=0.95). Promotion locked.'),

  // Churn Insight Assistant (approvals-queue story)
  ev(3, 9, BO, 'create_agent', 'agent', AGENT.churn, 'Created Churn Insight Assistant (Standardized).'),
  ev(3, 10, BO, 'register', 'agent', AGENT.churn, 'Registered; Standard path; approvals requested.'),
  ev(2, 13, GO, 'approve', 'approval', 'appr-churn-bo', 'Business owner approval granted (1 of 2).'),

  // Network Capacity Research Assistant (pipeline-refresh + demo mode story)
  ev(21, 9, BO, 'create_agent', 'agent', AGENT.capacity, 'Created Network Capacity Research Assistant (Standardized).'),
  ev(20, 13, GO, 'approve', 'approval', 'appr-capacity-bo', 'Business owner approval granted.'),
  ev(18, 13, GO, 'approve', 'approval', 'appr-capacity-risk', 'Risk officer review passed.'),
  ev(20, 11, PE, 'provision', 'agent', AGENT.capacity, 'Runtime + content provisioned; agent LIVE.'),
  ev(0, 2, PE, 'pipeline_refresh', 'source', 'capacity-reports', 'Re-index started — Content ⏳ (672 docs).'),

  // Regulatory Filing Coordinator (runtime-HITL story)
  ev(26, 9, BO, 'create_agent', 'agent', AGENT.regulatory, 'Created Regulatory Filing Coordinator (Advanced, Critical path).'),
  ev(24, 13, GO, 'approve', 'approval', 'appr-reg-bo', 'Business owner approval granted.'),
  ev(23, 13, GO, 'approve', 'approval', 'appr-reg-risk', 'Risk officer review passed (risk_tier=critical).'),
  ev(22, 13, GO, 'approve', 'approval', 'appr-reg-sec', 'Security committee approval granted; runtime HITL per action enabled.'),
  ev(25, 11, PE, 'provision', 'agent', AGENT.regulatory, 'Runtime + content provisioned; agent LIVE.'),

  // Draft
  ev(2, 14, BO, 'create_draft', 'agent', AGENT.vendor, 'Started onboarding draft: Vendor SLA Watcher (paused at Phase 3).'),

  // Connector health
  ev(1, 8, PE, 'healthcheck', 'connector', 'jira', 'Healthcheck returned degraded.'),
  ev(0, 8, PE, 'healthcheck', 'connector', 'gcp-ticketing', 'Healthcheck OK.'),
];
