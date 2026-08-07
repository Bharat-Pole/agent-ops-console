"""Increment E: governance config, evaluation center, evidence, exceptions.

Revision ID: 0005_increment_e
Revises: 0004_increment_d
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db import JsonDoc

revision = "0005_increment_e"
down_revision = "0004_increment_d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("config", JsonDoc, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "eval_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "eval_cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pack_id", sa.Uuid(), sa.ForeignKey("eval_packs.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expectations", JsonDoc, nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("pack_id", sa.Uuid(), sa.ForeignKey("eval_packs.id"), nullable=False, index=True),
        sa.Column("workflow_version_id", sa.Uuid(), sa.ForeignKey("workflow_versions.id"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("scorecard", JsonDoc, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("eval_run_id", sa.Uuid(), sa.ForeignKey("eval_runs.id"), nullable=False, index=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("eval_cases.id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("workflow_runs.id"), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("checks", JsonDoc, nullable=False),
    )
    op.create_table(
        "evidence_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("content", JsonDoc, nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "governance_exceptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("governance_exceptions", "evidence_packs", "eval_results", "eval_runs",
                  "eval_cases", "eval_packs", "policy_configs"):
        op.drop_table(table)
