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

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id          TEXT PRIMARY KEY,
  source_id   TEXT NOT NULL,
  run_id      TEXT,
  doc_id      TEXT NOT NULL,
  chunk_index INT NOT NULL DEFAULT 0,
  text        TEXT NOT NULL,
  embedding   vector(1536),
  embedding_local vector(384),
  metadata    JSONB NOT NULL DEFAULT '{}',
  created_at  TEXT NOT NULL
);
-- Backfill new columns on existing tables (idempotent on fresh installs too)
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS run_id TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS chunk_index INT NOT NULL DEFAULT 0;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_local vector(384);
-- embedding was NOT NULL when OpenAI was the only provider — local-provider chunks
-- populate embedding_local instead and leave this one NULL, so relax the constraint.
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
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS ingestion_mode TEXT NOT NULL DEFAULT 'hybrid';
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS embedding_provider TEXT NOT NULL DEFAULT 'openai';
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS owner TEXT;
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]';
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS valid_until TEXT;
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS lifecycle TEXT NOT NULL DEFAULT 'active';
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS last_queried_at TEXT;
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS chunk_size INT NOT NULL DEFAULT 800;
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS chunk_overlap INT NOT NULL DEFAULT 100;
ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS connector_config_masked TEXT;

CREATE INDEX IF NOT EXISTS idx_ks_status ON knowledge_sources(status);
CREATE INDEX IF NOT EXISTS idx_ks_created ON knowledge_sources(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ks_lifecycle ON knowledge_sources(lifecycle);

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

-- ── Brightspeed Incident Logs Table (Telecommunications & Fiber Operations) ────
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

    # Seed Brightspeed Incident Logs if empty
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
        print("[seed] inserted Brightspeed incident logs table for RAG ingestion testing.")

