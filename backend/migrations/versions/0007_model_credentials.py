"""Model catalog entries carry a vault credential reference.

Moves LLM API keys onto the same footing as tool credentials: encrypted at
rest, rotatable without a restart, and per-model rather than one global key.
The PLATFORM_GEMINI_API_KEY env var remains a bootstrap fallback — a fresh
install has no UI to create a secret before it can start.

Revision ID: 0007_model_credentials
Revises: 0006_increment_f
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_model_credentials"
down_revision = "0006_increment_f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_catalog", sa.Column("credential_ref", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("model_catalog", "credential_ref")
