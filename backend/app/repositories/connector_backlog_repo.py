from typing import Any, Optional

from app.db.connection import get_pool

# Fields an editor may change. `id` and `system_name` are absent: the id is the
# key other rows cite, and renaming the system would silently change what the
# assessment is *about*. Retire a row by setting status='deferred' instead.
EDITABLE = (
    "rank",
    "phase",
    "mcp_server",
    "mcp_server_note",
    "transport",
    "auth_model",
    "data_sensitivity",
    "candidate_tools",
    "access_owner",
    "status",
    "rationale",
    "blockers",
    "existing_connector_id",
)


def _row_to_item(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "system_name": row["system_name"],
        "rank": row["rank"],
        "phase": row["phase"],
        "mcp_server": row["mcp_server"],
        "mcp_server_note": row["mcp_server_note"],
        "transport": row["transport"],
        "auth_model": row["auth_model"],
        "data_sensitivity": row["data_sensitivity"],
        "candidate_tools": row["candidate_tools_json"],
        "access_owner": row["access_owner"],
        "status": row["status"],
        "rationale": row["rationale"],
        "blockers": row["blockers"],
        "existing_connector_id": row["existing_connector_id"],
        "updated_at": row["updated_at"],
    }


async def insert(item: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO connector_backlog (
            id, system_name, rank, phase, mcp_server, mcp_server_note, transport,
            auth_model, data_sensitivity, candidate_tools_json, access_owner,
            status, rationale, blockers, existing_connector_id, updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        """,
        item["id"],
        item["system_name"],
        item["rank"],
        item["phase"],
        item["mcp_server"],
        item.get("mcp_server_note"),
        item.get("transport"),
        item.get("auth_model"),
        item["data_sensitivity"],
        item.get("candidate_tools") or [],
        item.get("access_owner"),
        item["status"],
        item["rationale"],
        item.get("blockers"),
        item.get("existing_connector_id"),
        item["updated_at"],
    )


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM connector_backlog ORDER BY rank ASC")
    return [_row_to_item(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM connector_backlog WHERE id = $1", id_)
    return _row_to_item(row) if row else None


async def update(id_: str, merged: dict[str, Any], updated_at: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    await pool.execute(
        """
        UPDATE connector_backlog SET
            rank = $2, phase = $3, mcp_server = $4, mcp_server_note = $5,
            transport = $6, auth_model = $7, data_sensitivity = $8,
            candidate_tools_json = $9, access_owner = $10, status = $11,
            rationale = $12, blockers = $13, existing_connector_id = $14,
            updated_at = $15
        WHERE id = $1
        """,
        id_,
        merged["rank"],
        merged["phase"],
        merged["mcp_server"],
        merged.get("mcp_server_note"),
        merged.get("transport"),
        merged.get("auth_model"),
        merged["data_sensitivity"],
        merged.get("candidate_tools") or [],
        merged.get("access_owner"),
        merged["status"],
        merged["rationale"],
        merged.get("blockers"),
        merged.get("existing_connector_id"),
        updated_at,
    )
    return await get_by_id(id_)
