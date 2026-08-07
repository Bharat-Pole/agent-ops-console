from typing import Optional

from app.db.connection import get_pool


async def get_all() -> dict[str, bool]:
    pool = get_pool()
    rows = await pool.fetch("SELECT key, enabled FROM feature_flags")
    return {r["key"]: r["enabled"] for r in rows}


async def set_flag(key: str, enabled: bool, updated_at: str, updated_by: str) -> Optional[dict]:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE feature_flags SET enabled = $2, updated_at = $3, updated_by = $4 WHERE key = $1",
        key, enabled, updated_at, updated_by,
    )
    if result.split()[-1] == "0":
        return None
    return {"key": key, "enabled": enabled}
