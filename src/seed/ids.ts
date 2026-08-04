// Stable IDs for all seed entities. Agent ids follow the Blueprint pattern
// agt-<slug>-<yyyymmdd>-<4hex> (Section 12). Centralized so prompts/tools/
// sources/evals/approvals can cross-reference agents without circular imports.

export const AGENT = {
  hr: 'agt-hr-policy-bot-20260115-a1f3',
  noc: 'agt-noc-incident-summarizer-20260122-b2e7',
  incident: 'agt-incident-response-coordinator-20260205-c3d9',
  contract: 'agt-contract-clause-finder-20260218-d4c1',
  faq: 'agt-field-ops-faq-bot-20260112-e5b8',
  churn: 'agt-churn-insight-assistant-20260301-f6a2',
  capacity: 'agt-network-capacity-research-20260310-071d',
  regulatory: 'agt-regulatory-filing-coordinator-20260320-1829',
  vendor: 'agt-vendor-sla-watcher-20260726-2a3b', // draft
} as const;

export const PACK = {
  hr: 'pack-hr-policy-bot',
  noc: 'pack-noc-incident-summarizer',
  incident: 'pack-incident-response-coordinator',
  contract: 'pack-contract-clause-finder',
  faq: 'pack-field-ops-faq-bot',
  churn: 'pack-churn-insight-assistant',
  capacity: 'pack-network-capacity-research',
  regulatory: 'pack-regulatory-filing-coordinator',
} as const;

export const SOURCE = {
  incidentDb: 'incident-db-prod-v3',
  hrPolicies: 'hr-policies',
  contractsRepo: 'contracts-repo',
  capacityReports: 'capacity-reports',
  churnAnalytics: 'churn-analytics',
  regulatoryFilings: 'regulatory-filings',
} as const;
