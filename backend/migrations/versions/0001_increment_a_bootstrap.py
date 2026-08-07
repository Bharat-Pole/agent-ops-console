"""Increment A schema — FROZEN explicit DDL.

Originally a metadata create_all bootstrap; frozen to explicit DDL when
Increment B landed (a metadata bootstrap tracks live models, so migration 0002
collided with columns 0001 had already created — the classic drift). This file
now records the Increment A schema permanently; models keep evolving via later
migrations only.

JsonDoc keeps per-dialect resolution (JSONB on Postgres, JSON on SQLite).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db import JsonDoc

revision = "0001_increment_a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("granted_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "role"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "agent_control_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("intent_type", sa.String(40), nullable=False),
        sa.Column("lifecycle_status", sa.String(40), nullable=False, index=True),
        sa.Column("business_owner", sa.String(255), nullable=True),
        sa.Column("technical_owner", sa.String(255), nullable=True),
        sa.Column("governance_owner", sa.String(255), nullable=True),
        sa.Column("support_group", sa.String(255), nullable=True),
        sa.Column("cost_center", sa.String(120), nullable=True),
        sa.Column("draft_risk_tier", sa.String(20), nullable=True),
        sa.Column("confirmed_risk_tier", sa.String(20), nullable=True),
        sa.Column("current_intent_id", sa.Uuid(), nullable=True),
        sa.Column("current_intent_version", sa.Integer(), nullable=True),
        sa.Column("design_recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "agent_intent_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=True),
        sa.Column("payload", JsonDoc, nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_intent_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("payload", JsonDoc, nullable=False),
        sa.Column("pii_flags", JsonDoc, nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("agent_id", "version"),
    )
    op.create_table(
        "design_recommendations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("agent_intent_documents.id"), nullable=False, index=True),
        sa.Column("raw_output", JsonDoc, nullable=False),
        sa.Column("validation", JsonDoc, nullable=False),
        sa.Column("item_states", JsonDoc, nullable=False),
        sa.Column("model_id", sa.String(120), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("resource_type", sa.String(40), nullable=False, index=True),
        sa.Column("resource_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("step", sa.String(80), nullable=False),
        sa.Column("required_role", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("action", sa.String(80), nullable=False, index=True),
        sa.Column("resource_type", sa.String(40), nullable=False, index=True),
        sa.Column("resource_id", sa.String(64), nullable=False, index=True),
        sa.Column("detail", JsonDoc, nullable=False),
    )


def downgrade() -> None:
    for table in (
        "audit_log", "approvals", "design_recommendations", "agent_intent_documents",
        "agent_intent_drafts", "agent_control_records", "auth_sessions",
        "role_assignments", "users",
    ):
        op.drop_table(table)
