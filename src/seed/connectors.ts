import type { McpConnector, McpGatewayPolicy } from '@/types';
import { isoTs, daysFromToday } from './helpers';

// Phase 6 — the gateway policy every seeded connector starts with: **none**.
//
// That is a deliberate, honest starting state, not an oversight. Nobody has
// written a dataset inventory or an approved-identity list for these five, so
// declaring one here would seed a fiction — and a fabricated boundary is worse
// than a visible gap, because it looks governed. The gateway records the gap on
// every call and the connector card shows it, which is how it gets closed.
//
// Mirrors the column defaults in backend db/migrate.py. `connectors_repo.insert`
// does not write these columns at all, so a seeded row takes those defaults and
// lands identically whichever side seeded it.
const UNDECLARED: McpGatewayPolicy = {
  allowed_datasets: [],
  allowed_fields: [],
  approved_identities: [],
  service_account: null,
  iam_principal: null,
  rate_limit_per_min: 60,
  timeout_ms: 10000,
};

// Section 12.2 — MCP connectors (5). jira is seeded degraded.
export const SEED_CONNECTORS: McpConnector[] = [
  {
    id: 'gcp-ticketing',
    name: 'GCP Ticketing',
    transport: 'sse',
    endpoint: 'sse://mcp.gcp-ticketing.brightspeed.internal/v1',
    auth_mode: 'secret_manager',
    status: 'connected',
    tools_provided: ['incident_reader', 'slack_notifier', 'ticket_updater'],
    last_healthcheck: isoTs(daysFromToday(0), 8, 15),
    ...UNDECLARED,
  },
  {
    id: 'confluence',
    name: 'Confluence',
    transport: 'http',
    endpoint: 'https://mcp.confluence.brightspeed.internal/v1',
    auth_mode: 'oauth',
    status: 'connected',
    tools_provided: ['confluence_reader'],
    last_healthcheck: isoTs(daysFromToday(0), 8, 12),
    ...UNDECLARED,
  },
  {
    id: 'jira',
    name: 'Jira',
    transport: 'http',
    endpoint: 'https://mcp.jira.brightspeed.internal/v1',
    auth_mode: 'oauth',
    status: 'degraded',
    tools_provided: ['jira_reader'],
    last_healthcheck: isoTs(daysFromToday(0), 7, 55),
    ...UNDECLARED,
  },
  {
    id: 'crm-readonly',
    name: 'CRM (read-only)',
    transport: 'sse',
    endpoint: 'sse://mcp.crm-ro.brightspeed.internal/v1',
    auth_mode: 'secret_manager',
    status: 'connected',
    tools_provided: ['crm_reader'],
    last_healthcheck: isoTs(daysFromToday(0), 8, 5),
    ...UNDECLARED,
  },
  {
    id: 'filings-gateway',
    name: 'Filings Gateway',
    transport: 'http',
    endpoint: 'https://mcp.filings.brightspeed.internal/v1',
    auth_mode: 'secret_manager',
    status: 'connected',
    tools_provided: ['filing_reader'],
    last_healthcheck: isoTs(daysFromToday(0), 8, 20),
    ...UNDECLARED,
  },
];
