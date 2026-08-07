"""Increment D: workflows + versions, runs + steps, durable HITL requests.

Revision ID: 0004_increment_d
Revises: 0003_increment_c
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db import JsonDoc

revision = "0004_increment_d"
down_revision = "0003_increment_c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workflow_id", sa.Uuid(), sa.ForeignKey("workflows.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph", JsonDoc, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("validation", JsonDoc, nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workflow_id", "version"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("workflow_version_id", sa.Uuid(), sa.ForeignKey("workflow_versions.id"), nullable=False, index=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("input", JsonDoc, nullable=False),
        sa.Column("output", JsonDoc, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("workflow_runs.id"), nullable=False, index=True),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(80), nullable=False),
        sa.Column("node_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("detail", JsonDoc, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "run_hitl",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("workflow_runs.id"), nullable=False, index=True),
        sa.Column("node_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("payload", JsonDoc, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    for table in ("run_hitl", "run_steps", "workflow_runs", "workflow_versions", "workflows"):
        op.drop_table(table)
