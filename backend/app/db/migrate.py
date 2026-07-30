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
