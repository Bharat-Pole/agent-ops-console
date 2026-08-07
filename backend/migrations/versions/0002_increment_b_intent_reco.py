"""Increment B: intent validation storage + recommendation run columns.

First explicit-DDL migration (the 0001 metadata bootstrap is the sole
exception per its convention note).

Revision ID: 0002_increment_b
Revises: 0001_increment_a
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db import JsonDoc

revision = "0002_increment_b"
down_revision = "0001_increment_a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_intent_documents", sa.Column("validation", JsonDoc, nullable=False, server_default="{}"))
    op.add_column("design_recommendations", sa.Column("status", sa.String(30), nullable=False, server_default="ready"))
    op.add_column("design_recommendations", sa.Column("engine", sa.String(40), nullable=False, server_default=""))
    op.add_column("design_recommendations", sa.Column("items", JsonDoc, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("design_recommendations", "items")
    op.drop_column("design_recommendations", "engine")
    op.drop_column("design_recommendations", "status")
    op.drop_column("agent_intent_documents", "validation")
