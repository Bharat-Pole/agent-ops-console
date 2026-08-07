"""Increment F: deployments, access groups + hashed API keys, budgets,
feedback.

Revision ID: 0006_increment_f
Revises: 0005_increment_e
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db import JsonDoc

revision = "0006_increment_f"
down_revision = "0005_increment_e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("access_groups.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deployments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("workflow_version_id", sa.Uuid(), sa.ForeignKey("workflow_versions.id"), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, index=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("manifest", JsonDoc, nullable=False),
        sa.Column("admission", JsonDoc, nullable=False),
        sa.Column("access_group_id", sa.Uuid(), sa.ForeignKey("access_groups.id"), nullable=True),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("previous_deployment_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, unique=True),
        sa.Column("monthly_usd", sa.Float(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "feedback_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("workflow_runs.id"), nullable=False, index=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("feedback_records", "budgets", "deployments", "api_keys", "access_groups"):
        op.drop_table(table)
