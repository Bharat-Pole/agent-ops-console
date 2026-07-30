from typing import Any

from app.db.connection import get_pool


async def insert(evt: dict[str, Any]) -> dict[str, Any]:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO audit_log (id, at, actor_persona, action, entity_type, entity_id, detail) VALUES ($1,$2,$3,$4,$5,$6,$7)",
        evt["id"],
        evt["at"],
        evt["actor_persona"],
        evt["action"],
        evt["entity_type"],
        evt["entity_id"],
        evt["detail"],
    )
    return evt


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM audit_log ORDER BY at DESC")
    return [dict(r) for r in rows]
