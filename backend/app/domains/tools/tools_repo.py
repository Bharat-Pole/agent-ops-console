from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row_to_tool(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "version": row["version"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "permission_ceiling": row["permission_ceiling"],
        "write_capable": row["write_capable"],
        "connector_id": row["connector_id"],
        "schema": row["schema_json"],
        "status": row["status"],
        "owner": row["owner"],
        "risk_level": row["risk_level"],
        "used_by": row["used_by_json"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM tools ORDER BY name ASC")
    return [_row_to_tool(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM tools WHERE id = $1", id_)
    return _row_to_tool(row) if row else None


async def insert(tool: dict[str, Any]) -> None:
    pool = get_pool()
    now = tool.get("created_at") or _now_iso()
    await pool.execute(
        """INSERT INTO tools
           (id, version, name, description, category, permission_ceiling, write_capable,
            connector_id, schema_json, status, owner, risk_level, used_by_json, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)""",
        tool["id"],
        tool["version"],
        tool["name"],
        tool.get("description", ""),
        tool.get("category", "general"),
        tool["permission_ceiling"],
        tool["write_capable"],
        tool.get("connector_id"),
        tool.get("schema", {"inputs": {}, "outputs": {}}),
        tool.get("status", "available"),
        tool.get("owner"),
        tool.get("risk_level", "low"),
        tool.get("used_by", []),
        now,
        now,
    )


async def update_fields(id_: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Whitelisted partial update — only catalog-editable fields, never id/version/used_by."""
    allowed = {"name", "description", "category", "permission_ceiling", "connector_id", "status", "owner", "risk_level"}
    fields = {k: v for k, v in patch.items() if k in allowed}
    if not fields:
        return await get_by_id(id_)
    pool = get_pool()
    set_clause = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(fields))
    await pool.execute(
        f"UPDATE tools SET {set_clause}, updated_at = ${len(fields) + 2} WHERE id = $1",
        id_, *fields.values(), _now_iso(),
    )
    return await get_by_id(id_)


async def delete_by_id(id_: str) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM tools WHERE id = $1", id_)
    return result.split()[-1] != "0"


async def mark_used_by(id_: str, used_by: list[str]) -> None:
    pool = get_pool()
    await pool.execute("UPDATE tools SET used_by_json = $2, updated_at = $3 WHERE id = $1", id_, used_by, _now_iso())
