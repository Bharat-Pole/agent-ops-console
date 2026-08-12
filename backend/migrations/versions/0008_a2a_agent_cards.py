"""A2A agent cards — governed A2A metadata tied to a real agent.

One table. Skills are a JSON list rather than a normalized table, matching how
the platform already stores tags/source lists; discovery filters in Python at
v1 scale. Readiness is computed from lifecycle/workflow/deployment state and is
deliberately NOT persisted here.

Revision ID: 0008_a2a_cards
Revises: 0007_model_credentials
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db import JsonDoc

revision = "0008_a2a_cards"
down_revision = "0007_model_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_cards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"),
                  nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("capability_tier", sa.String(32), nullable=False),
        sa.Column("discovery_only", sa.Boolean(), nullable=False),
        sa.Column("message_task_format", sa.String(128), nullable=True),
        sa.Column("artifact_exchange", sa.Boolean(), nullable=False),
        sa.Column("artifact_format", sa.String(32), nullable=True),
        sa.Column("supported_tasks", JsonDoc, nullable=False),
        sa.Column("skills", JsonDoc, nullable=False),
        sa.Column("input_schema", JsonDoc, nullable=False),
        sa.Column("output_schema", JsonDoc, nullable=False),
        sa.Column("handoff_rules", JsonDoc, nullable=False),
        sa.Column("authn_methods", JsonDoc, nullable=False),
        sa.Column("authorized_callers", JsonDoc, nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("failure_behavior", sa.String(32), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "version"),
    )


def downgrade() -> None:
    op.drop_table("agent_cards")
