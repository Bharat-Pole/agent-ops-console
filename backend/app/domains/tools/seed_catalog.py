# Real Tool Registry & MCP Connector catalog metadata (Blueprint §3.4/§3.5).
#
# The `tools` table already has 12 rows (id/version/name/permission_ceiling/
# write_capable/used_by) from the original agents-workspace snapshot — those
# IDs are load-bearing: real agents in the `agents` table already reference
# them via config.tooling.bound_tools (e.g. "tools://incident_reader@v1").
# This is the richer catalog metadata (description, category, connector
# binding, I/O schema, risk level) for those SAME tool ids, backfilled onto
# the existing rows rather than inventing new ones — keeps every agent's
# existing tool references valid.
TOOL_CATALOG_ENRICHMENT: dict[str, dict] = {
    "incident_reader": {
        "description": "Read incident records from the ticketing system.",
        "category": "network_ops",
        "connector_id": "gcp-ticketing",
        "schema": {"inputs": {"query": "string", "window": "string"}, "outputs": {"incidents": "IncidentRecord[]"}},
        "risk_level": "low",
    },
    "confluence_reader": {
        "description": "Read approved policy and runbook pages from Confluence.",
        "category": "knowledge",
        "connector_id": "confluence",
        "schema": {"inputs": {"space": "string", "query": "string"}, "outputs": {"pages": "Page[]"}},
        "risk_level": "low",
    },
    "jira_reader": {
        "description": "Read Jira issues and epics (read-only).",
        "category": "engineering",
        "connector_id": "jira",
        "schema": {"inputs": {"jql": "string"}, "outputs": {"issues": "Issue[]"}},
        "risk_level": "low",
    },
    "log_reader": {
        "description": "Query structured logs for a service and window.",
        "category": "observability",
        "connector_id": None,
        "schema": {"inputs": {"service": "string", "window": "string"}, "outputs": {"lines": "LogLine[]"}},
        "risk_level": "low",
    },
    "health_checker": {
        "description": "Check current health/SLO status of a service.",
        "category": "observability",
        "connector_id": None,
        "schema": {"inputs": {"service": "string"}, "outputs": {"status": "string", "slo": "number"}},
        "risk_level": "low",
    },
    "contract_reader": {
        "description": "Read clauses from the contracts repository.",
        "category": "legal",
        "connector_id": None,
        "schema": {"inputs": {"contract_id": "string", "clause_type": "string"}, "outputs": {"clauses": "Clause[]"}},
        "risk_level": "low",
    },
    "crm_reader": {
        "description": "Read customer accounts and churn signals from the CRM (read-only).",
        "category": "sales",
        "connector_id": "crm-readonly",
        "schema": {"inputs": {"segment": "string"}, "outputs": {"accounts": "Account[]"}},
        "risk_level": "low",
    },
    "capacity_api_reader": {
        "description": "Read network capacity and utilization reports.",
        "category": "network_ops",
        "connector_id": None,
        "schema": {"inputs": {"region": "string", "horizon": "string"}, "outputs": {"forecast": "CapacityForecast"}},
        "risk_level": "low",
    },
    "filing_reader": {
        "description": "Read regulatory filings and submission templates.",
        "category": "compliance",
        "connector_id": "filings-gateway",
        "schema": {"inputs": {"jurisdiction": "string", "form": "string"}, "outputs": {"filings": "Filing[]"}},
        "risk_level": "medium",
    },
    # Write-capable — catalogued for visibility, never bindable (Section 7.6, LOCKED).
    "slack_notifier": {
        "description": "Post messages to Slack channels. WRITE action — advisory-blocked, never bound.",
        "category": "notifications",
        "connector_id": "gcp-ticketing",
        "schema": {"inputs": {"channel": "string", "message": "string"}, "outputs": {"ts": "string"}},
        "risk_level": "medium",
    },
    "email_sender": {
        "description": "Send email. WRITE action — advisory-blocked, never bound.",
        "category": "notifications",
        "connector_id": None,
        "schema": {"inputs": {"to": "string", "subject": "string", "body": "string"}, "outputs": {"message_id": "string"}},
        "risk_level": "medium",
    },
    "ticket_updater": {
        "description": "Create/update/close tickets. WRITE action — advisory-blocked, never bound.",
        "category": "network_ops",
        "connector_id": "gcp-ticketing",
        "schema": {"inputs": {"ticket_id": "string", "op": "string", "fields": "object"}, "outputs": {"ok": "boolean"}},
        "risk_level": "high",
    },
}

# MCP connectors these tools bind through (Blueprint §3.5 initial recommended
# connectors). jira is seeded degraded to give the Tools & MCP page a real
# non-uniform state to show, matching the frontend's original seed story.
MCP_CONNECTOR_CATALOG: list[dict] = [
    {
        "id": "gcp-ticketing",
        "name": "GCP Ticketing",
        "transport": "sse",
        "endpoint": "https://mcp.gcp-ticketing.brightspeed.internal/v1",
        "auth_mode": "secret_manager",
        "status": "connected",
        "tools_provided": ["incident_reader", "slack_notifier", "ticket_updater"],
    },
    {
        "id": "confluence",
        "name": "Confluence",
        "transport": "http",
        "endpoint": "https://mcp.confluence.brightspeed.internal/v1",
        "auth_mode": "oauth",
        "status": "connected",
        "tools_provided": ["confluence_reader"],
    },
    {
        "id": "jira",
        "name": "Jira",
        "transport": "http",
        "endpoint": "https://mcp.jira.brightspeed.internal/v1",
        "auth_mode": "oauth",
        "status": "degraded",
        "tools_provided": ["jira_reader"],
    },
    {
        "id": "crm-readonly",
        "name": "CRM (read-only)",
        "transport": "sse",
        "endpoint": "https://mcp.crm-ro.brightspeed.internal/v1",
        "auth_mode": "secret_manager",
        "status": "connected",
        "tools_provided": ["crm_reader"],
    },
    {
        "id": "filings-gateway",
        "name": "Filings Gateway",
        "transport": "http",
        "endpoint": "https://mcp.filings.brightspeed.internal/v1",
        "auth_mode": "secret_manager",
        "status": "connected",
        "tools_provided": ["filing_reader"],
    },
]
