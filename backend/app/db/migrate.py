from datetime import datetime, timezone

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
-- Tool Registry backfill (Blueprint §3.4) — richer catalog metadata beyond the
-- original bind-check-only columns above.
ALTER TABLE tools ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'general';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS connector_id TEXT;
ALTER TABLE tools ADD COLUMN IF NOT EXISTS schema_json JSONB NOT NULL DEFAULT '{"inputs":{},"outputs":{}}';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'available';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS owner TEXT;
ALTER TABLE tools ADD COLUMN IF NOT EXISTS risk_level TEXT NOT NULL DEFAULT 'low';
ALTER TABLE tools ADD COLUMN IF NOT EXISTS created_at TEXT;
ALTER TABLE tools ADD COLUMN IF NOT EXISTS updated_at TEXT;

-- ── MCP Connectors (Blueprint §3.5) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mcp_connectors (
  id                 TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  transport          TEXT NOT NULL DEFAULT 'http',
  endpoint           TEXT NOT NULL,
  auth_mode          TEXT NOT NULL DEFAULT 'none',
  status             TEXT NOT NULL DEFAULT 'connected',
  tools_provided_json JSONB NOT NULL DEFAULT '[]',
  last_healthcheck   TEXT,
  last_error         TEXT,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
  id             TEXT PRIMARY KEY,
  version        TEXT NOT NULL,
  name           TEXT NOT NULL,
  kind           TEXT NOT NULL,
  category       TEXT NOT NULL DEFAULT 'agent',
  source         TEXT NOT NULL DEFAULT 'manual',
  generated_from TEXT,
  body           TEXT NOT NULL DEFAULT '',
  status         TEXT NOT NULL DEFAULT 'draft',
  owner          TEXT NOT NULL,
  used_by_json   JSONB NOT NULL DEFAULT '[]',
  history_json   JSONB NOT NULL DEFAULT '[]'
);
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS domain     TEXT;
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS use_case   TEXT;
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS risk_tier  TEXT;
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS agent_type TEXT;
-- Structured citation template (Blueprint 3.3 "configure citation rules") —
-- a citation-kind prompt's `body` is free text for the LLM to read as an
-- instruction; this is a real, mechanically-applied format the backend uses
-- to render the system-generated citation strings, e.g.
-- "({doc_title}, source: {source_name})". Placeholders: {source_name}
-- {source_id} {doc_id} {doc_title}. NULL = use the platform default format.
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS citation_format TEXT;

-- ── Evaluation Runs (Blueprint §6 core data object "Evaluation Run") ──────────
-- eval_packs.pack_json.last_run holds only the MOST RECENT run (unchanged,
-- existing frontend reads it directly) — this table is the full history, one
-- row per real execution, so score-over-time trends are answerable.
CREATE TABLE IF NOT EXISTS eval_runs (
  id           TEXT PRIMARY KEY,
  pack_id      TEXT NOT NULL REFERENCES eval_packs(id) ON DELETE CASCADE,
  agent_id     TEXT NOT NULL,
  score        INT NOT NULL,
  results_json JSONB NOT NULL,
  model_used   TEXT,
  error_msg    TEXT,
  started_at   TEXT NOT NULL,
  finished_at  TEXT NOT NULL,
  actor_persona TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_pack ON eval_runs(pack_id, finished_at DESC);

-- ── Governance Policy-as-Configuration (Blueprint §4, §9 "Policy-as-Config") ──
-- Was hardcoded in kernel/constants.ts AND duplicated in
-- backend/app/seed_data/constants.py — registration.py now reads this table
-- instead, so an edit here actually changes real registration behavior.
CREATE TABLE IF NOT EXISTS policy_rules (
  capability_tier TEXT NOT NULL,
  risk_tier       TEXT NOT NULL,
  governance_path TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  updated_by      TEXT,
  PRIMARY KEY (capability_tier, risk_tier)
);

CREATE TABLE IF NOT EXISTS path_definitions (
  path         TEXT PRIMARY KEY,
  label        TEXT NOT NULL,
  approvals_json JSONB NOT NULL DEFAULT '[]',
  hitl_gates   INT NOT NULL DEFAULT 0,
  description  TEXT NOT NULL DEFAULT '',
  updated_at   TEXT NOT NULL,
  updated_by   TEXT
);

-- ── Governance Exception Register (Blueprint §9 "Exception Management") ──────
-- Was a single free-text config.lifecycle.exception_status string per agent
-- with no expiry tracking anywhere — this is the real register the Blueprint's
-- "temporary exceptions must not silently become permanent risk" gap needs.
CREATE TABLE IF NOT EXISTS governance_exceptions (
  id           TEXT PRIMARY KEY,
  agent_id     TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  reason       TEXT NOT NULL,
  granted_by   TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'active',
  expires_at   TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  revoked_at   TEXT,
  revoked_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_exceptions_agent ON governance_exceptions(agent_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_status ON governance_exceptions(status);

-- ── Model Repository (Blueprint §3.7) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS models (
  id                     TEXT PRIMARY KEY,
  name                   TEXT NOT NULL,
  provider               TEXT NOT NULL,
  roles_json             JSONB NOT NULL DEFAULT '[]',
  context_window         INT NOT NULL DEFAULT 0,
  cost_input_per_mtok    DOUBLE PRECISION NOT NULL DEFAULT 0,
  cost_output_per_mtok   DOUBLE PRECISION NOT NULL DEFAULT 0,
  latency_p50_ms         INT NOT NULL DEFAULT 0,
  approved_use_case      TEXT NOT NULL DEFAULT '',
  risk_tier_mapping_json JSONB NOT NULL DEFAULT '[]',
  owner                  TEXT,
  deployment_status      TEXT NOT NULL DEFAULT 'candidate',
  access_policy          TEXT NOT NULL DEFAULT '',
  fallback_of            TEXT,
  routing_note           TEXT NOT NULL DEFAULT '',
  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id         TEXT PRIMARY KEY,
  source_id  TEXT NOT NULL,
  doc_id     TEXT NOT NULL,
  text       TEXT NOT NULL,
  embedding  vector(1536),
  created_at TEXT NOT NULL
);
-- Backfill columns added by the knowledge/RAG ingestion pipeline (idempotent
-- on fresh installs too): run_id ties a chunk to the pipeline_run that created
-- it; embedding_local (384-dim) backs the sentence-transformers local
-- embedding provider alongside the original OpenAI 1536-dim column.
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS run_id TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS chunk_index INT NOT NULL DEFAULT 0;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_local vector(384);
-- embedding was NOT NULL when OpenAI was the only provider — local-provider
-- chunks populate embedding_local instead and leave this NULL.
ALTER TABLE knowledge_chunks ALTER COLUMN embedding DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source ON knowledge_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source_run ON knowledge_chunks(source_id, run_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding ON knowledge_chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_local ON knowledge_chunks
  USING hnsw (embedding_local vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- ── Knowledge Sources ─────────────────────────────────────────────────────────
-- Stores metadata + raw file bytes (BYTEA) so ingestion needs no filesystem.
CREATE TABLE IF NOT EXISTS knowledge_sources (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  source_type   TEXT NOT NULL,
  mime_type     TEXT,
  file_content  BYTEA,
  raw_text      TEXT,
  uri           TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'pending',
  sensitivity   TEXT NOT NULL DEFAULT 'internal',
  ingestion_mode TEXT NOT NULL DEFAULT 'hybrid',
  chunk_count   INT NOT NULL DEFAULT 0,
  size_bytes    BIGINT NOT NULL DEFAULT 0,
  error_msg     TEXT,
  domain        TEXT,
  owner         TEXT,
  tags          JSONB NOT NULL DEFAULT '[]',
  valid_until   TEXT,
  lifecycle     TEXT NOT NULL DEFAULT 'active',
  last_queried_at TEXT,
  chunk_size    INT NOT NULL DEFAULT 800,
  chunk_overlap INT NOT NULL DEFAULT 100,
  connector_config_masked TEXT,
  embedding_provider TEXT NOT NULL DEFAULT 'openai',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS used_by_json JSONB NOT NULL DEFAULT '[]';
-- Upload-time approval gate (Blueprint 3.2 "Upload approved documents") — a
-- gated-sensitivity source starts life needing sign-off before it can be
-- ingested/queried, mirroring the existing bind-time approval gate.
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved';
-- Content category (Blueprint 3.2 supported-source prose: runbooks, policy
-- documents, MDR/golden data, internal business rules, logs/evidence) — these
-- aren't distinct connector protocols, just a content classification layered
-- on top of whatever connector actually fetched the bytes.
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS category TEXT;

CREATE INDEX IF NOT EXISTS idx_ks_status ON knowledge_sources(status);
CREATE INDEX IF NOT EXISTS idx_ks_created ON knowledge_sources(created_at DESC);

-- ── Knowledge Documents ────────────────────────────────────────────────────────
-- A source can fetch more than one discrete content unit (a Confluence space
-- pulls N pages, a Jira JQL pulls N issues, a GitHub path pulls N files, a
-- ServiceNow query pulls N records) — each such unit is a real, independently
-- taggable "document" (Blueprint 3.2 "tag documents by domain/owner/sensitivity/
-- validity/usage"). Single-item sources (file/url/text/database/bigquery) get
-- exactly one row here too, so every source uniformly has >=1 document.
CREATE TABLE IF NOT EXISTS knowledge_documents (
  id              TEXT PRIMARY KEY,
  source_id       TEXT NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
  doc_ref         TEXT NOT NULL,
  title           TEXT NOT NULL,
  domain          TEXT,
  owner           TEXT,
  sensitivity     TEXT NOT NULL DEFAULT 'internal',
  valid_until     TEXT,
  lifecycle       TEXT NOT NULL DEFAULT 'active',
  last_queried_at TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  UNIQUE (source_id, doc_ref)
);
CREATE INDEX IF NOT EXISTS idx_kdoc_source ON knowledge_documents(source_id);

-- ── Retrieval Test Runs (Blueprint 3.3 "Retrieval test results" key output) ────
-- Was purely ephemeral — the Retrieval Test panel showed real numbers per
-- call but nothing survived a page refresh. Every real /retrieve call now
-- persists a summary so past test results are a real, durable artifact.
CREATE TABLE IF NOT EXISTS retrieval_test_runs (
  id                  TEXT PRIMARY KEY,
  query               TEXT NOT NULL,
  source_ids_json     JSONB NOT NULL,
  top_k               INT NOT NULL,
  score_threshold     DOUBLE PRECISION NOT NULL,
  rerank_enabled      BOOLEAN NOT NULL,
  result_count        INT NOT NULL,
  passed_count        INT NOT NULL,
  latency_ms          DOUBLE PRECISION NOT NULL,
  estimated_cost_usd  DOUBLE PRECISION,
  created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rtr_created ON retrieval_test_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ks_lifecycle ON knowledge_sources(lifecycle);

-- Carries which binding a pending approval is about (e.g. 'kb://<source_id>'),
-- since approvals_repo.patch() overwrites `note` with the officer's own decision text.
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS target_ref TEXT;
CREATE INDEX IF NOT EXISTS idx_approvals_target ON approvals(target_ref) WHERE target_ref IS NOT NULL;

-- ── Pipeline Runs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id             TEXT PRIMARY KEY,
  source_id      TEXT NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
  trigger        TEXT NOT NULL DEFAULT 'manual',
  status         TEXT NOT NULL DEFAULT 'running',
  chunks_created INT NOT NULL DEFAULT 0,
  error_msg      TEXT,
  started_at     TEXT NOT NULL,
  finished_at    TEXT,
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pr_source ON pipeline_runs(source_id, created_at DESC);

-- ── Pipeline Run Stages ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_run_stages (
  id          TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
  stage_name  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',
  items_total INT NOT NULL DEFAULT 0,
  items_done  INT NOT NULL DEFAULT 0,
  error_msg   TEXT,
  started_at  TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_prs_run ON pipeline_run_stages(run_id);

-- ── Brightspeed Incident Logs ──────────────────────────────────────────────────
-- Real structured-data table for the "database source" / text-to-SQL demo path
-- (routes/knowledge.py sources/database, sources/{id}/ask) — not a mock fixture,
-- an actual queryable table the SQL executor runs real read-only SQL against.
CREATE TABLE IF NOT EXISTS brightspeed_incident_logs (
  ticket_id       TEXT PRIMARY KEY,
  region          TEXT NOT NULL,
  component       TEXT NOT NULL,
  severity        TEXT NOT NULL,
  status          TEXT NOT NULL,
  summary         TEXT NOT NULL,
  root_cause      TEXT,
  resolution      TEXT,
  affected_users  INT NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL
);

-- ── Deployment & Access Management (Blueprint §5.10 / §9) ────────────────────
-- Was a single free-text config.deployment.environment string with no history
-- — this is the real environment ladder (staging <-> production) an agent
-- actually moves through, plus who has access to it.
CREATE TABLE IF NOT EXISTS deployment_records (
  id               TEXT PRIMARY KEY,
  agent_id         TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  action           TEXT NOT NULL,             -- 'initial' | 'promote' | 'rollback'
  from_environment TEXT,
  to_environment   TEXT NOT NULL,
  strategy         TEXT NOT NULL DEFAULT 'blue-green',
  status           TEXT NOT NULL DEFAULT 'success',
  reason           TEXT,
  actor_persona    TEXT NOT NULL,
  created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deploy_records_agent ON deployment_records(agent_id, created_at DESC);

CREATE TABLE IF NOT EXISTS access_grants (
  id           TEXT PRIMARY KEY,
  agent_id     TEXT REFERENCES agents(id) ON DELETE CASCADE,  -- NULL = platform-wide grant
  grantee      TEXT NOT NULL,
  role_label   TEXT NOT NULL,
  scope        TEXT NOT NULL DEFAULT 'owner', -- 'owner' | 'admin' | 'viewer'
  granted_by   TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'active',
  granted_at   TEXT NOT NULL,
  revoked_at   TEXT,
  revoked_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_access_grants_agent ON access_grants(agent_id);
CREATE INDEX IF NOT EXISTS idx_access_grants_status ON access_grants(status);

-- ── Monitoring & Observability ────────────────────────────────────────────────
-- Was a fully-fabricated PRNG series (kernel/telemetry.ts) with no backing
-- data at all. Every row here is a real event recorded at the moment a real
-- chat (routes/chat.py) or eval case (services/evaluation.py) call completes
-- or fails — latency measured with time.monotonic(), tokens from the real
-- Anthropic response.usage. Starts empty on a fresh install; there is no
-- historical activity to honestly backfill it from.
CREATE TABLE IF NOT EXISTS request_telemetry (
  id          TEXT PRIMARY KEY,
  agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  source      TEXT NOT NULL,          -- 'chat' | 'eval'
  status      TEXT NOT NULL,          -- 'ok' | 'error'
  model       TEXT,
  latency_ms  INT NOT NULL,
  tokens_in   INT NOT NULL DEFAULT 0,
  tokens_out  INT NOT NULL DEFAULT 0,
  error_msg   TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_request_telemetry_agent ON request_telemetry(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_request_telemetry_created ON request_telemetry(created_at);

-- ── Admin Console — Feature Flags ─────────────────────────────────────────────
-- Was pure Zustand `ui.featureFlags` client state (store.ts) with no
-- server-side representation at all — reset to its hardcoded default on
-- every page reload, and not shared across users. A real, durable register.
CREATE TABLE IF NOT EXISTS feature_flags (
  key        TEXT PRIMARY KEY,
  enabled    BOOLEAN NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);

-- ── A2A Directory (Blueprint §9.10) ───────────────────────────────────────────
-- Was computed entirely client-side from live agent config PLUS one hardcoded
-- input/output schema stub identical across every card regardless of the
-- agent's actual capabilities. Real generator (services/a2a.py) derives every
-- field from the agent's own persisted config_json — no new fabricated data —
-- and is re-synced from current config on every read, so it can never go
-- stale. `endpoint` is the one field a Platform Admin can real-edit (e.g. to
-- point at an actual deployed A2A gateway); `endpoint_overridden` protects
-- that edit from being clobbered by the next auto-sync.
CREATE TABLE IF NOT EXISTS agent_cards (
  agent_id            TEXT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
  name                TEXT NOT NULL,
  description         TEXT,
  skills_json         JSONB NOT NULL DEFAULT '[]',
  endpoint            TEXT NOT NULL,
  endpoint_overridden BOOLEAN NOT NULL DEFAULT FALSE,
  discovery_only      BOOLEAN NOT NULL DEFAULT TRUE,
  message_task_format TEXT,
  capability_tier     TEXT NOT NULL,
  model               TEXT,
  input_schema_json   JSONB NOT NULL DEFAULT '{}',
  output_schema_json  JSONB NOT NULL DEFAULT '{}',
  updated_at          TEXT NOT NULL
);
"""

_INCIDENT_LOGS_SEED = [
    (
        "INC-2026-9001", "Ohio Valley", "Fiber Core Backbone", "CRITICAL", "RESOLVED",
        "Major fiber cut along Highway 33 due to third-party directional drilling.",
        "Physical fiber cut across 48-strand single-mode fiber bundle.",
        "Splicing team dispatched; fused 48 strands and restored full optical throughput.",
        14200, "2026-07-28T04:12:00Z"
    ),
    (
        "INC-2026-9002", "North Carolina", "OLT Switch Node NC-04", "HIGH", "RESOLVED",
        "GPON Optical Line Terminal flap leading to intermittent subscriber drops.",
        "SFP+ transceiver power degradation causing elevated optical bit error rate (BER).",
        "Replaced faulty SFP+ optics and re-balanced attenuation levels.",
        3400, "2026-07-29T11:45:00Z"
    ),
    (
        "INC-2026-9003", "Virginia", "DNS Gateway East", "MEDIUM", "RESOLVED",
        "Elevated latency on primary DNS resolvers (ns1.brightspeed.net).",
        "UDP flood targeting DNS port 53 causing cache lookup timeouts.",
        "Enabled DDoS rate-limiting rules at edge border routers.",
        28000, "2026-07-30T16:20:00Z"
    ),
    (
        "INC-2026-9004", "Missouri", "BGP Edge Router MO-R01", "CRITICAL", "INVESTIGATING",
        "BGP routing table instability causing packet loss for enterprise customer traffic.",
        "Upstream peer advertised invalid AS path prefix.",
        "Applied strict RPKI route origin validation filtering rules.",
        8900, "2026-07-31T08:05:00Z"
    ),
]


async def run_migrations() -> None:
    pool = get_pool()
    await pool.execute(DDL)

    count = await pool.fetchval("SELECT COUNT(*) FROM brightspeed_incident_logs")
    if count == 0:
        await pool.executemany(
            """
            INSERT INTO brightspeed_incident_logs
            (ticket_id, region, component, severity, status, summary, root_cause, resolution, affected_users, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            _INCIDENT_LOGS_SEED,
        )
        print("[migrate] seeded brightspeed_incident_logs for the database-source/text-to-SQL demo path.")

    flag_count = await pool.fetchval("SELECT COUNT(*) FROM feature_flags")
    if flag_count == 0:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        await pool.executemany(
            "INSERT INTO feature_flags (key, enabled, updated_at, updated_by) VALUES ($1, $2, $3, $4)",
            [("model_repository", True, now, "system"), ("workflow_builder", True, now, "system")],
        )
        print("[migrate] seeded feature_flags with their existing client-side defaults (both enabled).")
