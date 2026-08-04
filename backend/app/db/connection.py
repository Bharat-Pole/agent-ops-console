import json

import asyncpg

from app.env import env

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # asyncpg has no automatic JSONB (de)serialization like node-postgres does —
    # register a codec once per connection so repo functions can pass/receive
    # plain dicts, matching the Node code's "reads are automatic" behavior.
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def connect_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=env.DATABASE_URL, init=_init_connection)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call connect_pool() first.")
    return _pool
