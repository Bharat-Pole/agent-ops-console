# Internal A2A Registry

This independently runnable service owns the A2A Readiness Layer for internal company agents. It prepares agents for future multi-agent flows by storing and validating agent cards, A2A-ready contracts, and handoff approval design records.

It does not execute cross-agent tasks. The runtime handoff itself remains a future integration concern; this asset only answers, "Is this agent discoverable and ready to be handed off to?"

## Scope covered

- Create agent card
- Define capabilities and supported tasks
- Define input and output JSON message schemas
- Define artifact exchange format for advanced cards
- Define handoff rules, timeout, and failure behavior
- Define trace correlation ID for handoff validation
- Define authentication and authorization metadata
- Define human approval requirement for cross-agent handoff
- Preserve version history and audit events for every mutation

## Development configuration

Use your local PostgreSQL server. You do not need Docker Desktop.

```powershell
$env:A2A_DATABASE_URL='postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/a2a_registry'
$env:A2A_DEV_API_KEY='dev-secret'
$env:A2A_INTERNAL_ENDPOINT_HOSTS='localhost,internal-api.example.com'
```

Do not share your real PostgreSQL password in chat or commit it to a file.

## Install requirements

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\a2a_registry\requirements.txt
```

Expected important packages include `fastapi`, `uvicorn`, `SQLAlchemy`, `psycopg`, and `alembic`.

## Apply database migrations

Run from the `backend` directory:

```powershell
Push-Location backend
$env:A2A_DATABASE_URL='postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/a2a_registry'
..\.venv\Scripts\python.exe -m alembic -c a2a_registry\alembic.ini upgrade head
Pop-Location
```

Expected output includes lines like:

```text
Running upgrade  -> 20260804_01
Running upgrade 20260804_01 -> 20260811_02
```

## Run the service

Run from the `backend` directory:

```powershell
$env:A2A_DATABASE_URL='postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/a2a_registry'
$env:A2A_DEV_API_KEY='dev-secret'
$env:A2A_INTERNAL_ENDPOINT_HOSTS='localhost,internal-api.example.com'
..\.venv\Scripts\python.exe -m uvicorn a2a_registry.main:app --reload --port 8001
```

Expected output:

```text
Uvicorn running on http://127.0.0.1:8001
Application startup complete.
```

## Manual verification

Run these from a second terminal at the repo root.

```powershell
curl.exe http://127.0.0.1:8001/healthz
```

Expected:

```json
{"status":"ok"}
```

```powershell
curl.exe http://127.0.0.1:8001/readyz
```

Expected after migrations and correct DB env:

```json
{"status":"ok"}
```

Create one draft standardized card:

```powershell
$body = @{
  agent_id = "agt-noc-incident-20260811-a1b2"
  name = "NOC Incident Summarizer"
  description = "Summarizes internal incident records for operator review."
  owner_team = "network-operations"
  endpoint = "https://internal-api.example.com/a2a/noc"
  skills = @("summarization","grounded-answer")
  supported_tasks = @("incident-summary")
  input_schema = @{ type = "object"; properties = @{ query = @{ type = "string" } } }
  output_schema = @{ type = "object"; properties = @{ answer = @{ type = "string" } } }
  capability_tier = "standardized"
  discovery_only = $true
  message_task_format = $null
  artifact_exchange = $false
  handoff_rules = @{ max_hops = 1; require_human_approval = $false; allowed_target_skills = @() }
  timeout_seconds = 30
  failure_behavior = "fail_fast"
  authn_methods = @("internal_api_key")
  authorized_callers = @("agent-ops-console")
} | ConvertTo-Json -Depth 20

curl.exe -X POST http://127.0.0.1:8001/a2a/v1/agent-cards -H "Content-Type: application/json" -H "X-A2A-API-Key: dev-secret" -d $body
```

Expected response contains:

```json
"agent_id":"agt-noc-incident-20260811-a1b2"
"card_status":"draft"
"supported_tasks":["incident-summary"]
```

Attest LIVE eligibility:

```powershell
$attestation = @{
  source_agent_id = "agt-noc-incident-20260811-a1b2"
  a2a_enabled = $true
  capability_tier = "standardized"
  lifecycle_status = "live"
  registry_ready = $true
  runtime_ready = $true
  content_ready = $true
  source_version = "1"
  observed_at = "2026-08-11T10:00:00Z"
} | ConvertTo-Json -Depth 10

curl.exe -X POST http://127.0.0.1:8001/a2a/v1/agent-cards/agt-noc-incident-20260811-a1b2/eligibility-attestations -H "Content-Type: application/json" -H "X-A2A-API-Key: dev-secret" -d $attestation
```

Expected:

```json
"eligible_for_discovery":true
```

Publish:

```powershell
curl.exe -X POST http://127.0.0.1:8001/a2a/v1/agent-cards/agt-noc-incident-20260811-a1b2/publish -H "X-A2A-API-Key: dev-secret"
```

Expected:

```json
"card_status":"published"
"eligible_for_discovery":true
```

Discover:

```powershell
curl.exe http://127.0.0.1:8001/a2a/v1/agent-cards
```

Expected:

```json
"total":1
```
