from typing import Any, Optional

from app.db.connection import get_pool


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
    }


async def insert(connector: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO connectors (
            id, name, transport, endpoint, auth_mode, status, tools_provided_json, last_healthcheck
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        """,
        connector["id"],
        connector["name"],
        connector["transport"],
        connector["endpoint"],
        connector["auth_mode"],
        connector["status"],
        connector.get("tools_provided") or [],
        connector["last_healthcheck"],
    )


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM connectors WHERE id = $1", id_)
    return _row_to_connector(row) if row else None


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM connectors ORDER BY name")
    return [_row_to_connector(r) for r in rows]


async def update(
    id_: str, name: str, transport: str, endpoint: str, auth_mode: str
) -> Optional[dict[str, Any]]:
    """Edit the author-owned fields only.

    `status`, `tools_provided_json` and `last_healthcheck` are intentionally not
    updatable here — they belong to the health cascade and to discovery, never
    to an editor (see services/connector_authoring.py).
    """
    pool = get_pool()
    row = await pool.fetchrow(
        """UPDATE connectors SET name = $2, transport = $3, endpoint = $4, auth_mode = $5
           WHERE id = $1 RETURNING *""",
        id_,
        name,
        transport,
        endpoint,
        auth_mode,
    )
    return _row_to_connector(row) if row else None


async def set_status(id_: str, status: str, last_healthcheck: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE connectors SET status = $2, last_healthcheck = $3 WHERE id = $1 RETURNING *",
        id_,
        status,
        last_healthcheck,
    )
    return _row_to_connector(row) if row else None
