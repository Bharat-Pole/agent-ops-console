"""Migration chain executes reality: upgrade builds the full Increment A
schema, downgrade removes it. Runs against a scratch SQLite; compose/CI run the
same chain against Postgres.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "users", "role_assignments", "auth_sessions",
    "agent_control_records", "agent_intent_drafts", "agent_intent_documents",
    "design_recommendations", "approvals", "audit_log",
}


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["sqlalchemy_url"] = db_url
    return cfg


def test_upgrade_head_then_downgrade_base(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables, tables
    assert "alembic_version" in tables

    command.downgrade(cfg, "base")
    remaining = set(inspect(create_engine(url)).get_table_names())
    assert not (EXPECTED_TABLES & remaining), remaining
    engine.dispose()


def test_migration_chain_matches_orm_metadata(tmp_path):
    """Drift guard: a DB built by the migration chain must have the same
    tables/columns as one built from the live ORM metadata. Catches the
    add-a-model-column-but-forget-the-migration mistake at CI time."""
    from app.db import Base

    mig_url = f"sqlite:///{tmp_path / 'via_migrations.db'}"
    command.upgrade(_alembic_config(mig_url), "head")

    orm_url = f"sqlite:///{tmp_path / 'via_orm.db'}"
    orm_engine = create_engine(orm_url)
    Base.metadata.create_all(orm_engine)

    def schema_map(url: str) -> dict[str, set[str]]:
        insp = inspect(create_engine(url))
        return {
            t: {c["name"] for c in insp.get_columns(t)}
            for t in insp.get_table_names()
            if t != "alembic_version"
        }

    migrated, orm = schema_map(mig_url), schema_map(orm_url)
    assert migrated.keys() == orm.keys(), (
        f"tables differ — only in migrations: {migrated.keys() - orm.keys()}; "
        f"only in ORM: {orm.keys() - migrated.keys()}"
    )
    for table in orm:
        assert migrated[table] == orm[table], (
            f"columns differ on {table} — only in migrations: {migrated[table] - orm[table]}; "
            f"only in ORM: {orm[table] - migrated[table]}"
        )
    orm_engine.dispose()
