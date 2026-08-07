from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row_to_connector(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "transport": row["transport"],
        "endpoint": row["endpoint"],
        "auth_mode": row["auth_mode"],
        "status": row["status"],
        "tools_provided": row["tools_provided_json"],
        "last_healthcheck": row["last_healthcheck"],
        "last_error": row["last_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM mcp_connectors ORDER BY name ASC")
    return [_row_to_connector(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM mcp_connectors WHERE id = $1", id_)
    return _row_to_connector(row) if row else None


async def insert(connector: dict[str, Any]) -> None:
    pool = get_pool()
    now = connector.get("created_at") or _now_iso()
    await pool.execute(
        """INSERT INTO mcp_connectors
           (id, name, transport, endpoint, auth_mode, status, tools_provided_json, last_healthcheck, last_error, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
        connector["id"],
        connector["name"],
        connector.get("transport", "http"),
        connector["endpoint"],
        connector.get("auth_mode", "none"),
        connector.get("status", "connected"),
        connector.get("tools_provided", []),
        connector.get("last_healthcheck"),
        connector.get("last_error"),
        now,
        now,
    )


async def patch(id_: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
    allowed = {"name", "transport", "endpoint", "auth_mode", "status", "last_healthcheck", "last_error"}
    upd = {k: v for k, v in fields.items() if k in allowed}
    if not upd:
        return await get_by_id(id_)
    pool = get_pool()
    set_clause = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(upd))
    await pool.execute(
        f"UPDATE mcp_connectors SET {set_clause}, updated_at = ${len(upd) + 2} WHERE id = $1",
        id_, *upd.values(), _now_iso(),
    )
    return await get_by_id(id_)


async def delete_by_id(id_: str) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM mcp_connectors WHERE id = $1", id_)
    return result.split()[-1] != "0"
