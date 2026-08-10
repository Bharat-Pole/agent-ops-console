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
        # Phase 5A. NULL marks a seeded or console-authored tool; a value marks
        # one discovered from an MCP server.
        "remote_tool_id": row["remote_tool_id"],
        "discovered_at": row["discovered_at"],
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


async def upsert_discovered(tool: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Insert or refresh a tool discovered from an MCP server (Phase 5A).

    Returns `(tool, created)`.

    Three rules are enforced here rather than by the caller, because this is the
    only write path discovery has:

    1. **A new discovered tool is always `pending`.** Discovery is not consent —
       a server advertising a tool must never be able to make it bindable.
    2. **Re-discovery preserves an existing `approval_state`.** Re-running
       discovery is a routine operation and must not silently revoke a decision
       a human already made.
    3. **...unless `write_capable` changed.** That is a material change to what
       the tool can do, so the prior approval no longer describes it and the
       tool returns to `pending`. The caller is told via the `write_flipped`
       key so it can write an audit record.

    `status` is deliberately absent from the UPDATE: it belongs to the connector
    health cascade, and a discovery run is not a healthcheck.
    """
    pool = get_pool()
    existing = await get_by_id(tool["id"])

    if existing is None:
        await pool.execute(
            """
            INSERT INTO tools (
                id, version, name, description, category, permission_ceiling,
                write_capable, connector_id, schema_json, status, used_by_json,
                result_fixtures_json, approval_state, owner, risk_level,
                remote_tool_id, discovered_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            """,
            # "v1" matches tool_authoring.create_tool — the column is TEXT and
            # the bound-tools ref format is `tools://{id}@{version}`.
            tool["id"], tool.get("version") or "v1", tool["name"], tool["description"],
            tool["category"], tool["permission_ceiling"], tool["write_capable"],
            tool["connector_id"], tool["schema"], tool.get("status") or "available",
            [], [],
            "pending",                      # rule 1 — never negotiable
            tool.get("owner"), tool.get("risk_level"),
            tool["remote_tool_id"], tool["discovered_at"],
        )
        created = await get_by_id(tool["id"])
        assert created is not None
        return {**created, "write_flipped": False}, True

    write_flipped = bool(existing["write_capable"]) != bool(tool["write_capable"])
    approval_state = "pending" if write_flipped else existing["approval_state"]  # rules 2 & 3

    await pool.execute(
        """
        UPDATE tools SET
            name = $2, description = $3, category = $4, write_capable = $5,
            connector_id = $6, schema_json = $7, approval_state = $8,
            remote_tool_id = $9, discovered_at = $10
        WHERE id = $1
        """,
        tool["id"], tool["name"], tool["description"], tool["category"],
        tool["write_capable"], tool["connector_id"], tool["schema"],
        approval_state, tool["remote_tool_id"], tool["discovered_at"],
    )
    refreshed = await get_by_id(tool["id"])
    assert refreshed is not None
    return {**refreshed, "write_flipped": write_flipped}, False


async def get_discovered_for_connector(connector_id: str) -> list[dict[str, Any]]:
    """Tools this connector previously advertised — i.e. those with a
    `remote_tool_id`. Hand-authored tools attached to the same connector are
    excluded on purpose: they were never advertised, so they can never be
    orphaned by a listing that omits them."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM tools WHERE connector_id = $1 AND remote_tool_id IS NOT NULL ORDER BY name",
        connector_id,
    )
    return [_row_to_tool(r) for r in rows]


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
