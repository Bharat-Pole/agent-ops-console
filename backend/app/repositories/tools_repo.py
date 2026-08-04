from typing import Any, Optional

from app.db.connection import get_pool


def _row_to_tool(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "version": row["version"],
        "name": row["name"],
        "permission_ceiling": row["permission_ceiling"],
        "write_capable": row["write_capable"],
        "used_by": row["used_by_json"],
    }


async def insert(tool: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO tools (id, version, name, permission_ceiling, write_capable, used_by_json) VALUES ($1,$2,$3,$4,$5,$6)",
        tool["id"],
        tool["version"],
        tool["name"],
        tool["permission_ceiling"],
        tool["write_capable"],
        tool["used_by"],
    )


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM tools WHERE id = $1", id_)
    return _row_to_tool(row) if row else None


async def mark_used_by(id_: str, used_by: list[str]) -> None:
    pool = get_pool()
    await pool.execute("UPDATE tools SET used_by_json = $2 WHERE id = $1", id_, used_by)
