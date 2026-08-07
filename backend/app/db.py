"""Database layer. Postgres-first models; SQLite variant for zero-service local
tests (recorded deviation: CI/compose run the suite against real Postgres).
"""
from __future__ import annotations

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# One JSON type used everywhere: JSONB on Postgres, plain JSON on SQLite.
JsonDoc = JSONB().with_variant(JSON(), "sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
