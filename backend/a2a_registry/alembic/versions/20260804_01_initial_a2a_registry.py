"""Initial internal A2A registry schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260804_01"
down_revision = None
branch_labels = ("a2a",)
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS a2a")
    op.create_table("agent_cards", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("agent_id", sa.String(128), nullable=False), sa.Column("name", sa.String(256), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("owner_team", sa.String(128), nullable=False), sa.Column("endpoint", sa.Text(), nullable=False), sa.Column("input_schema", postgresql.JSONB(), nullable=False), sa.Column("output_schema", postgresql.JSONB(), nullable=False), sa.Column("capability_tier", sa.String(32), nullable=False), sa.Column("discovery_only", sa.Boolean(), nullable=False), sa.Column("message_task_format", sa.String(128)), sa.Column("artifact_exchange", sa.Boolean(), nullable=False), sa.Column("card_status", sa.String(32), nullable=False), sa.Column("card_version", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("agent_id", name="uq_a2a_agent_id"), sa.CheckConstraint("capability_tier IN ('standardized', 'advanced')", name="ck_a2a_tier"), sa.CheckConstraint("card_status IN ('draft', 'published', 'suspended', 'retired')", name="ck_a2a_status"), sa.CheckConstraint("(capability_tier = 'standardized' AND discovery_only AND message_task_format IS NULL AND NOT artifact_exchange) OR (capability_tier = 'advanced' AND NOT discovery_only AND message_task_format IS NOT NULL AND artifact_exchange)", name="ck_a2a_tier_exchange"), schema="a2a")
    op.create_index("ix_a2a_published_cards", "agent_cards", ["name"], unique=False, schema="a2a", postgresql_where=sa.text("card_status = 'published'"))
    op.create_table("agent_skills", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("agent_card_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("a2a.agent_cards.id", ondelete="CASCADE"), nullable=False), sa.Column("skill", sa.String(100), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("agent_card_id", "skill", name="uq_a2a_card_skill"), schema="a2a")
    op.create_index("ix_a2a_skill", "agent_skills", ["skill"], unique=False, schema="a2a")
    op.create_table("eligibility_attestations", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("source_agent_id", sa.String(128), nullable=False), sa.Column("a2a_enabled", sa.Boolean(), nullable=False), sa.Column("capability_tier", sa.String(32), nullable=False), sa.Column("lifecycle_status", sa.String(32), nullable=False), sa.Column("registry_ready", sa.Boolean(), nullable=False), sa.Column("runtime_ready", sa.Boolean(), nullable=False), sa.Column("content_ready", sa.Boolean(), nullable=False), sa.Column("source_version", sa.String(128), nullable=False), sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("actor_id", sa.String(128), nullable=False), schema="a2a")
    op.create_index("ix_a2a_attestation_latest", "eligibility_attestations", ["source_agent_id", "observed_at"], unique=False, schema="a2a")
    op.create_table("agent_card_versions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("agent_card_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("a2a.agent_cards.id", ondelete="RESTRICT"), nullable=False), sa.Column("card_version", sa.Integer(), nullable=False), sa.Column("snapshot", postgresql.JSONB(), nullable=False), sa.Column("change_type", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("actor_id", sa.String(128), nullable=False), sa.UniqueConstraint("agent_card_id", "card_version", name="uq_a2a_card_version"), schema="a2a")
    op.create_table("audit_events", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("agent_id", sa.String(128), nullable=False), sa.Column("action", sa.String(64), nullable=False), sa.Column("actor_id", sa.String(128), nullable=False), sa.Column("actor_type", sa.String(16), nullable=False), sa.Column("card_version", sa.Integer()), sa.Column("detail", postgresql.JSONB(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), schema="a2a")
    op.create_index("ix_a2a_audit_timeline", "audit_events", ["agent_id", "occurred_at"], unique=False, schema="a2a")


def downgrade() -> None:
    op.drop_table("audit_events", schema="a2a")
    op.drop_table("agent_card_versions", schema="a2a")
    op.drop_table("eligibility_attestations", schema="a2a")
    op.drop_table("agent_skills", schema="a2a")
    op.drop_table("agent_cards", schema="a2a")
    op.execute("DROP SCHEMA IF EXISTS a2a")
