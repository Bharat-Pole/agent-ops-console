"""Alembic environment. URL resolution order:
1. config.attributes["sqlalchemy_url"] — programmatic callers (tests)
2. app settings (PLATFORM_DATABASE_URL env / .env) — CLI + compose + CI

No separate alembic URL exists by design: the app's config seam is the only one.
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ importable

from app.config import settings  # noqa: E402
from app.db import Base  # noqa: E402
from app import models  # noqa: E402,F401 — registers all tables on Base.metadata

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    return config.attributes.get("sqlalchemy_url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
