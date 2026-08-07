"""Increment C: Asset Studio tables — secrets vault, model catalog, tool
registry, MCP connectors, prompt packs/versions, knowledge sources/chunks,
RAG pipelines, agent-asset bindings.

Revision ID: 0003_increment_c
Revises: 0002_increment_b
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db import JsonDoc

revision = "0003_increment_c"
down_revision = "0002_increment_b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "model_catalog",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model_ref", sa.String(120), nullable=False, unique=True),
        sa.Column("kind", sa.String(20), nullable=False, index=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("cost_per_1k_in", sa.Float(), nullable=False),
        sa.Column("cost_per_1k_out", sa.Float(), nullable=False),
        sa.Column("latency_note", sa.String(120), nullable=False),
        sa.Column("max_risk_tier", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("fallback_ref", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tools",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("business_purpose", sa.Text(), nullable=False),
        sa.Column("permission_type", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("input_schema", JsonDoc, nullable=False),
        sa.Column("output_schema", JsonDoc, nullable=False),
        sa.Column("implementation", JsonDoc, nullable=False),
        sa.Column("auth", JsonDoc, nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("logging_requirement", sa.String(40), nullable=False),
        sa.Column("human_approval_required", sa.Boolean(), nullable=False),
        sa.Column("error_handling", JsonDoc, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("mcp_connector_id", sa.Uuid(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("slug", "version"),
    )
    op.create_table(
        "mcp_connectors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("transport", sa.String(20), nullable=False),
        sa.Column("auth", JsonDoc, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("health", JsonDoc, nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "prompt_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("prompt_type", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", JsonDoc, nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pack_id", sa.Uuid(), sa.ForeignKey("prompt_packs.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("variables", JsonDoc, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("rolled_back_from", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pack_id", "version"),
    )
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime", sa.String(80), nullable=False),
        sa.Column("sensitivity", sa.String(20), nullable=False),
        sa.Column("access_policy", JsonDoc, nullable=False),
        sa.Column("validity_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedded", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("knowledge_sources.id"), nullable=False, index=True),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("meta", JsonDoc, nullable=False),
        sa.Column("embedding", JsonDoc, nullable=True),
    )
    op.create_table(
        "rag_pipelines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("source_ids", JsonDoc, nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False),
        sa.Column("embedding_model_ref", sa.String(120), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("score_threshold", sa.Float(), nullable=False),
        sa.Column("hybrid_alpha", sa.Float(), nullable=False),
        sa.Column("metadata_filters", JsonDoc, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "asset_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent_control_records.id"), nullable=False, index=True),
        sa.Column("asset_type", sa.String(20), nullable=False),
        sa.Column("asset_ref", sa.String(140), nullable=False),
        sa.Column("version_policy", sa.String(40), nullable=False),
        sa.Column("pinned_version", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "asset_type", "asset_ref"),
    )


def downgrade() -> None:
    for table in (
        "asset_bindings", "rag_pipelines", "kb_chunks", "knowledge_sources",
        "prompt_versions", "prompt_packs", "mcp_connectors", "tools",
        "model_catalog", "secrets",
    ):
        op.drop_table(table)
