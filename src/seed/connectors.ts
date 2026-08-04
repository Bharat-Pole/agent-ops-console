import type { McpConnector } from '@/types';
import { isoTs, daysFromToday } from './helpers';

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
  },
];
