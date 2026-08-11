"""Add A2A contract fields and handoff approval requests."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260811_02"
down_revision = "20260804_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_cards", sa.Column("contract_version", sa.String(16), server_default="1.1", nullable=False), schema="a2a")
    op.add_column("agent_cards", sa.Column("supported_tasks", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False), schema="a2a")
    op.add_column("agent_cards", sa.Column("artifact_format", sa.String(32)), schema="a2a")
    op.add_column("agent_cards", sa.Column("handoff_rules", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False), schema="a2a")
    op.add_column("agent_cards", sa.Column("timeout_seconds", sa.Integer(), server_default="30", nullable=False), schema="a2a")
    op.add_column("agent_cards", sa.Column("failure_behavior", sa.String(32), server_default="fail_fast", nullable=False), schema="a2a")
    op.add_column("agent_cards", sa.Column("authn_methods", postgresql.JSONB(), server_default=sa.text("'[\"internal_api_key\"]'::jsonb"), nullable=False), schema="a2a")
    op.add_column("agent_cards", sa.Column("authorized_callers", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False), schema="a2a")

    op.create_table(
        "handoff_approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_agent_id", sa.String(128), nullable=False),
        sa.Column("target_agent_id", sa.String(128), nullable=False),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("trace_correlation_id", sa.String(64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("decided_by", sa.String(128)),
        sa.Column("decision_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_a2a_approval_status"),
        sa.UniqueConstraint("trace_correlation_id", name="uq_a2a_handoff_trace"),
        schema="a2a",
    )
    op.create_index("ix_a2a_handoff_source", "handoff_approval_requests", ["source_agent_id"], unique=False, schema="a2a")
    op.create_index("ix_a2a_handoff_target", "handoff_approval_requests", ["target_agent_id"], unique=False, schema="a2a")
    op.create_index("ix_a2a_handoff_status", "handoff_approval_requests", ["status"], unique=False, schema="a2a")


def downgrade() -> None:
    op.drop_index("ix_a2a_handoff_status", table_name="handoff_approval_requests", schema="a2a")
    op.drop_index("ix_a2a_handoff_target", table_name="handoff_approval_requests", schema="a2a")
    op.drop_index("ix_a2a_handoff_source", table_name="handoff_approval_requests", schema="a2a")
    op.drop_table("handoff_approval_requests", schema="a2a")
    op.drop_column("agent_cards", "authorized_callers", schema="a2a")
    op.drop_column("agent_cards", "authn_methods", schema="a2a")
    op.drop_column("agent_cards", "failure_behavior", schema="a2a")
    op.drop_column("agent_cards", "timeout_seconds", schema="a2a")
    op.drop_column("agent_cards", "handoff_rules", schema="a2a")
    op.drop_column("agent_cards", "artifact_format", schema="a2a")
    op.drop_column("agent_cards", "supported_tasks", schema="a2a")
    op.drop_column("agent_cards", "contract_version", schema="a2a")
