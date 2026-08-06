import type { ToolAsset } from '@/types';
import { AGENT } from './ids';

// Phase 3 added three fields to ToolAsset. They are applied once, below, rather
// than repeated across all twelve entries — the value is the same for every
// seeded tool and the reason is a single fact about the seed, not twelve.
type SeedTool = Omit<ToolAsset, 'approval_state' | 'owner' | 'risk_level'>;

// Section 12.2 — Tools (12). Nine read-only + three write-capable.
// write_capable:true tools are catalogued for visibility but can NEVER be bound
// (Section 7.6 / acceptance #3). They render with a red "WRITE — advisory-block" badge.
const SEED_TOOLS_RAW: SeedTool[] = [
  {
    id: 'incident_reader',
    version: 'v1',
    name: 'incident_reader',
    description: 'Read incident records from the ticketing system.',
    category: 'network_ops',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: 'gcp-ticketing',
    schema: { inputs: { query: 'string', window: 'string' }, outputs: { incidents: 'IncidentRecord[]' } },
    status: 'available',
    used_by: [AGENT.noc, AGENT.incident],
    result_fixtures: [
      '{"incident_id":"INC-2026-0142","severity":"critical","service":"core-routing","status":"resolved","mttr_min":47}',
      '{"incident_id":"INC-2026-0151","severity":"high","service":"dns-edge","status":"resolved","mttr_min":88}',
    ],
  },
  {
    id: 'confluence_reader',
    version: 'v1',
    name: 'confluence_reader',
    description: 'Read approved policy and runbook pages from Confluence.',
    category: 'knowledge',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: 'confluence',
    schema: { inputs: { space: 'string', query: 'string' }, outputs: { pages: 'Page[]' } },
    status: 'available',
    used_by: [AGENT.hr, AGENT.faq],
    result_fixtures: ['{"page":"HR-PTO-Policy","version":"2026.2","excerpt":"Full-time employees accrue 15 days PTO annually."}'],
  },
  {
    id: 'jira_reader',
    version: 'v1',
    name: 'jira_reader',
    description: 'Read Jira issues and epics (read-only).',
    category: 'engineering',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: 'jira',
    schema: { inputs: { jql: 'string' }, outputs: { issues: 'Issue[]' } },
    status: 'degraded', // its connector (jira) is degraded
    used_by: [AGENT.incident],
    result_fixtures: ['{"issue":"NET-4821","summary":"Edge router flapping","status":"In Progress"}'],
  },
  {
    id: 'log_reader',
    version: 'v1',
    name: 'log_reader',
    description: 'Query structured logs for a service and window.',
    category: 'observability',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: null,
    schema: { inputs: { service: 'string', window: 'string' }, outputs: { lines: 'LogLine[]' } },
    status: 'available',
    used_by: [AGENT.incident],
    result_fixtures: ['{"service":"core-routing","errors_last_1h":312,"p95_ms":9400}'],
  },
  {
    id: 'health_checker',
    version: 'v1',
    name: 'health_checker',
    description: 'Check current health/SLO status of a service.',
    category: 'observability',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: null,
    schema: { inputs: { service: 'string' }, outputs: { status: 'string', slo: 'number' } },
    status: 'available',
    used_by: [AGENT.incident],
    result_fixtures: ['{"service":"dns-edge","status":"degraded","slo_burn":2.3}'],
  },
  {
    id: 'contract_reader',
    version: 'v1',
    name: 'contract_reader',
    description: 'Read clauses from the contracts repository.',
    category: 'legal',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: null,
    schema: { inputs: { contract_id: 'string', clause_type: 'string' }, outputs: { clauses: 'Clause[]' } },
    status: 'available',
    used_by: [AGENT.contract],
    result_fixtures: ['{"contract":"MSA-ACME-2025","clause":"Limitation of Liability","cap":"12 months fees"}'],
  },
  {
    id: 'crm_reader',
    version: 'v1',
    name: 'crm_reader',
    description: 'Read customer accounts and churn signals from the CRM (read-only).',
    category: 'sales',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: 'crm-readonly',
    schema: { inputs: { segment: 'string' }, outputs: { accounts: 'Account[]' } },
    status: 'available',
    used_by: [AGENT.churn],
    result_fixtures: ['{"segment":"enterprise-northeast","at_risk":14,"top_driver":"support_latency"}'],
  },
  {
    id: 'capacity_api_reader',
    version: 'v1',
    name: 'capacity_api_reader',
    description: 'Read network capacity and utilization reports.',
    category: 'network_ops',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: null,
    schema: { inputs: { region: 'string', horizon: 'string' }, outputs: { forecast: 'CapacityForecast' } },
    status: 'available',
    used_by: [AGENT.capacity],
    result_fixtures: ['{"region":"midwest","utilization":0.81,"headroom_months":7}'],
  },
  {
    id: 'filing_reader',
    version: 'v1',
    name: 'filing_reader',
    description: 'Read regulatory filings and submission templates.',
    category: 'compliance',
    permission_ceiling: 'read',
    write_capable: false,
    connector_id: 'filings-gateway',
    schema: { inputs: { jurisdiction: 'string', form: 'string' }, outputs: { filings: 'Filing[]' } },
    status: 'available',
    used_by: [AGENT.regulatory],
    result_fixtures: ['{"jurisdiction":"FCC","form":"477","due":"2026-09-01","status":"draft"}'],
  },
  // ---- Write-capable (catalogued, NEVER bindable) ----
  {
    id: 'slack_notifier',
    version: 'v1',
    name: 'slack_notifier',
    description: 'Post messages to Slack channels. WRITE action — advisory-blocked, never bound.',
    category: 'notifications',
    permission_ceiling: 'draft',
    write_capable: true,
    connector_id: 'gcp-ticketing',
    schema: { inputs: { channel: 'string', message: 'string' }, outputs: { ts: 'string' } },
    status: 'available',
    used_by: [], // flagged during synthesis for the Incident Coordinator, but never bound
  },
  {
    id: 'email_sender',
    version: 'v1',
    name: 'email_sender',
    description: 'Send email. WRITE action — advisory-blocked, never bound.',
    category: 'notifications',
    permission_ceiling: 'draft',
    write_capable: true,
    connector_id: null,
    schema: { inputs: { to: 'string', subject: 'string', body: 'string' }, outputs: { message_id: 'string' } },
    status: 'available',
    used_by: [],
  },
  {
    id: 'ticket_updater',
    version: 'v1',
    name: 'ticket_updater',
    description: 'Create/update/close tickets. WRITE action — advisory-blocked, never bound.',
    category: 'network_ops',
    permission_ceiling: 'recommend',
    write_capable: true,
    connector_id: 'gcp-ticketing',
    schema: { inputs: { ticket_id: 'string', op: 'string', fields: 'object' }, outputs: { ok: 'boolean' } },
    status: 'available',
    used_by: [],
  },
];

// Phase 3.2 — the seeded catalog is the platform's *pre-vetted* set, so it is
// grandfathered `approved` rather than retro-queued; the same grandfathering
// the `approval_state` column default performs server-side. Only tools created
// through the console from here on start `pending`.
//
// Phase 3.3 — `owner`/`risk_level` are deliberately unset. A seeded tool has no
// real owner, and inventing one would fabricate accountability in the exact
// screen a Governance Officer uses to find gaps. They render as "unassigned"
// and are filled in through PATCH /v1/tools/:id.
export const SEED_TOOLS: ToolAsset[] = SEED_TOOLS_RAW.map((t) => ({
  ...t,
  approval_state: 'approved',
  owner: null,
  risk_level: null,
}));
