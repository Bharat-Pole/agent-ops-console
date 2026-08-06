from typing import Any, Optional

from app.db.connection import get_pool


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
        # Health (`status`) and consent (`approval_state`) are separate columns
        # on purpose — see db/migrate.py.
        "approval_state": row["approval_state"],
        "owner": row["owner"],
        "risk_level": row["risk_level"],
        "used_by": row["used_by_json"],
        "result_fixtures": row["result_fixtures_json"],
    }


async def insert(tool: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO tools (
            id, version, name, description, category, permission_ceiling,
            write_capable, connector_id, schema_json, status, used_by_json, result_fixtures_json,
            approval_state, owner, risk_level
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
        """,
        tool["id"],
        tool["version"],
        tool["name"],
        tool["description"],
        tool["category"],
        tool["permission_ceiling"],
        tool["write_capable"],
        tool["connector_id"],
        tool["schema"],
        tool["status"],
        tool["used_by"],
        tool.get("result_fixtures") or [],
        # The seed snapshot predates Phase 3 and carries none of these keys, so
        # a seeded tool lands pre-approved and unassigned — same result as the
        # column defaults in db/migrate.py, by design.
        tool.get("approval_state") or "approved",
        tool.get("owner"),
        tool.get("risk_level"),
    )


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM tools WHERE id = $1", id_)
    return _row_to_tool(row) if row else None


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM tools ORDER BY name")
    return [_row_to_tool(r) for r in rows]


async def mark_used_by(id_: str, used_by: list[str]) -> None:
    pool = get_pool()
    await pool.execute("UPDATE tools SET used_by_json = $2 WHERE id = $1", id_, used_by)


async def set_status(id_: str, status: str) -> None:
    """Only ever called by the connector health cascade — a tool's status is
    derived from its connector, never set directly by a client."""
    pool = get_pool()
    await pool.execute("UPDATE tools SET status = $2 WHERE id = $1", id_, status)


async def set_approval_state(id_: str, state: str) -> None:
    """Only ever called by `services/tool_approval.py`, i.e. off the back of a
    decision on the shared approval queue. Note this writes `approval_state`
    and never `status` — consent must not be able to launder itself into health
    (or the reverse), which is why they are separate columns."""
    pool = get_pool()
    await pool.execute("UPDATE tools SET approval_state = $2 WHERE id = $1", id_, state)


async def update_policy(id_: str, owner: Optional[str], risk_level: Optional[str]) -> Optional[dict[str, Any]]:
    """Phase 3.3 — the only mutable-by-an-author fields on a tool.

    Deliberately cannot touch `permission_ceiling`, `write_capable`,
    `connector_id`, `status` or `approval_state`. Re-classifying a tool's
    permission after it was approved would silently invalidate the approval;
    that belongs to versioning, not to an edit form.
    """
    pool = get_pool()
    await pool.execute(
        "UPDATE tools SET owner = $2, risk_level = $3 WHERE id = $1", id_, owner, risk_level
    )
    return await get_by_id(id_)
