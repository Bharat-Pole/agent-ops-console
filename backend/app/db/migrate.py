from app.db.connection import get_pool

# Idempotent DDL — safe to run on every boot. Ported verbatim from
# server/db/migrate.ts (Node backend) — no migration framework at this scale.
DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS agents (
  id                    TEXT PRIMARY KEY,
  agent_name            TEXT NOT NULL,
  lifecycle_status      TEXT NOT NULL,
  risk_tier             TEXT NOT NULL,
  capability_tier       TEXT NOT NULL,
  governance_path       TEXT NOT NULL,
  demo_mode             BOOLEAN NOT NULL DEFAULT FALSE,
  config_json           JSONB NOT NULL,
  tracks_json           JSONB NOT NULL,
  signal_breakdown_json JSONB,
  review_card_json      JSONB,
  evaluation_pack_id    TEXT,
  approval_ids_json     JSONB NOT NULL DEFAULT '[]',
  fast_path_expiry_date TEXT,
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
  id               TEXT PRIMARY KEY,
  agent_id         TEXT NOT NULL REFERENCES agents(id),
  step             TEXT NOT NULL,
  required_by_path TEXT NOT NULL,
  status           TEXT NOT NULL,
  actor_persona    TEXT,
  decided_at       TEXT,
  note             TEXT,
  requested_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_agent ON approvals(agent_id);

-- Phase 3.2: the approval queue becomes a *shared platform object* (Blueprint
-- §11 — "prompt, tool, data, model, deployment and exception approvals"), not
-- an agent-only one. Widened rather than duplicated on purpose: a tool-local
-- approval state would be a second queue nobody governs.
--
-- `agent_id` drops NOT NULL but KEEPS its foreign key — a nullable FK still
-- enforces referential integrity for every non-null value, so agent approvals
-- lose nothing and a tool approval simply has no agent. `required_by_path`
-- likewise: a governance path is an agent concept, and writing 'standard' on a
-- tool row to satisfy a NOT NULL would be inventing a fact.
ALTER TABLE approvals ALTER COLUMN agent_id DROP NOT NULL;
ALTER TABLE approvals ALTER COLUMN required_by_path DROP NOT NULL;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS entity_type TEXT NOT NULL DEFAULT 'agent';
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS entity_id TEXT;
-- Backfill: every pre-Phase-3 row is an agent approval, so its subject is its
-- agent. Idempotent — the WHERE clause matches nothing on a second run.
UPDATE approvals SET entity_id = agent_id WHERE entity_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_approvals_entity ON approvals(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id            TEXT PRIMARY KEY,
  at            TEXT NOT NULL,
  actor_persona TEXT NOT NULL,
  action        TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  entity_id     TEXT NOT NULL,
  detail        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC);

CREATE TABLE IF NOT EXISTS eval_packs (
  id        TEXT PRIMARY KEY,
  agent_id  TEXT NOT NULL REFERENCES agents(id),
  pack_json JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  entity_id  TEXT NOT NULL,
  run_at     TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_due ON scheduled_jobs(status, run_at);

CREATE TABLE IF NOT EXISTS tools (
  id                 TEXT PRIMARY KEY,
  version            TEXT NOT NULL,
  name               TEXT NOT NULL,
  permission_ceiling TEXT NOT NULL,
  write_capable      BOOLEAN NOT NULL,
  used_by_json       JSONB NOT NULL DEFAULT '[]'
);
-- Widened after the fact (Section: tool authoring) — ADD COLUMN IF NOT EXISTS
-- keeps this idempotent for dev DBs that already had the narrower table.
ALTER TABLE tools ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT '';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS connector_id TEXT;
ALTER TABLE tools ADD COLUMN IF NOT EXISTS schema_json JSONB NOT NULL DEFAULT '{"inputs": {}, "outputs": {}}';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'available';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS result_fixtures_json JSONB NOT NULL DEFAULT '[]';

-- Phase 3.2 — tool approval (Blueprint §11). Deliberately a SEPARATE column
-- from `status`, not a new `status` value: `status` is owned end-to-end by the
-- connector health cascade (services/connector_health.py) and would overwrite a
-- pending state the moment a connector flapped. Health and consent are two
-- different questions about a tool, so they get two different columns.
--
-- DEFAULT 'approved' grandfathers the seeded catalog: those 12 tools are the
-- platform's pre-vetted set, and retro-queueing them would put 12 items a
-- Governance Officer never requested in front of them. Everything created
-- through the console from here on starts 'pending' (services/tool_authoring.py).
ALTER TABLE tools ADD COLUMN IF NOT EXISTS approval_state TEXT NOT NULL DEFAULT 'approved';

-- Phase 3.3 — tool policy fields (Blueprint §3.4, ROADMAP D6). Nullable on
-- purpose: a seeded tool genuinely has no declared owner, and defaulting one in
-- would fabricate accountability. NULL renders as "unassigned" and is a real
-- governance gap to close, not a display bug.
ALTER TABLE tools ADD COLUMN IF NOT EXISTS owner TEXT;
ALTER TABLE tools ADD COLUMN IF NOT EXISTS risk_level TEXT;

-- MCP connectors. Added when the MCP layer was moved server-side to match
-- tools: a connector's health is now authoritative state the server owns, not
-- a client-side simulation, because tool status derives from it (see
-- services/connector_health.py).
CREATE TABLE IF NOT EXISTS connectors (
  id                 TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  transport          TEXT NOT NULL,
  endpoint           TEXT NOT NULL,
  auth_mode          TEXT NOT NULL,
  status             TEXT NOT NULL,
  tools_provided_json JSONB NOT NULL DEFAULT '[]',
  last_healthcheck   TEXT NOT NULL
);

-- Tool-call audit trail (deck slide 21, element 6). The column list is the
-- slide's own field list, verbatim and in order, so the table can be read
-- against the commitment directly. `system_accessed` is the connector the tool
-- resolved to and is NULL for local tools -- never a placeholder.
CREATE TABLE IF NOT EXISTS tool_calls (
  id               TEXT PRIMARY KEY,
  agent_id         TEXT NOT NULL,
  request_id       TEXT NOT NULL,
  consumer         TEXT NOT NULL,
  tool_invoked     TEXT NOT NULL,
  system_accessed  TEXT,
  result_status    TEXT NOT NULL,
  latency_ms       INTEGER NOT NULL,
  exception_detail TEXT,
  permission       TEXT NOT NULL,
  at               TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_agent ON tool_calls(agent_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool_invoked, at DESC);

-- Connector prioritization backlog — deck slide 21, element 7 ("identify which
-- systems should be connected in the first 90 days versus future phases") and
-- the SOW's Week-11 deliverable 3.3. This is an *assessment*, not connectivity:
-- a row here is a candidate system, whereas a row in `connectors` is a server we
-- actually talk to. `existing_connector_id` links the two when both exist.
--
-- Persisted rather than hardcoded because the assessment changes across the
-- engagement — a system moves proposed → access_requested → connected as
-- approvals land, and ServiceNow stops being ineligible the day a server ships.
CREATE TABLE IF NOT EXISTS connector_backlog (
  id                    TEXT PRIMARY KEY,
  system_name           TEXT NOT NULL,
  rank                  INTEGER NOT NULL,
  phase                 TEXT NOT NULL,          -- day_90 | later
  mcp_server            TEXT NOT NULL,          -- official | community | none | unknown
  mcp_server_note       TEXT,
  transport             TEXT,                   -- streamable_http | stdio | NULL when there is no server
  auth_model            TEXT,                   -- oauth2 | api_token | iam | unknown | NULL
  data_sensitivity      TEXT NOT NULL,          -- mirrors Sensitivity in src/types/agent.ts
  candidate_tools_json  JSONB NOT NULL DEFAULT '[]',
  access_owner          TEXT,
  status                TEXT NOT NULL,          -- proposed | access_requested | approved | connected | deferred | blocked
  rationale             TEXT NOT NULL,
  blockers              TEXT,
  existing_connector_id TEXT,                   -- a connectors.id we already seeded, or NULL
  updated_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backlog_rank ON connector_backlog(rank);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id         TEXT PRIMARY KEY,
  source_id  TEXT NOT NULL,
  doc_id     TEXT NOT NULL,
  text       TEXT NOT NULL,
  embedding  vector(1536) NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source ON knowledge_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
"""


async def run_migrations() -> None:
    pool = get_pool()
    await pool.execute(DDL)
