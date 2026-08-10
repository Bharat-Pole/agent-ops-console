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
        # Phase 5A. NULL means never probed over the wire — the UI relies on
        # this to distinguish a real healthcheck from a simulated one.
        "last_probe": row["last_probe_json"],
        # Phase 6 — gateway policy (slide 21 elements 4 and 5). Empty list means
        # "not declared", never "nothing allowed"; see db/migrate.py.
        "allowed_datasets": row["allowed_datasets_json"],
        "allowed_fields": row["allowed_fields_json"],
        "approved_identities": row["approved_identities_json"],
        "service_account": row["service_account"],
        "iam_principal": row["iam_principal"],
        "rate_limit_per_min": row["rate_limit_per_min"],
        "timeout_ms": row["timeout_ms"],
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


async def set_probe(id_: str, probe: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Record the result of a **real** probe (Phase 5A).

    Only ever written by `connector_health.run_healthcheck()` when it actually
    reached a socket. A simulated healthcheck must leave this NULL — that is the
    whole point of the column, and writing a fabricated probe here would make
    the two indistinguishable in the data.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE connectors SET last_probe_json = $2 WHERE id = $1 RETURNING *", id_, probe
    )
    return _row_to_connector(row) if row else None


async def set_policy(id_: str, policy: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Write the gateway policy fields (Phase 6).

    Only ever called by `services/connector_policy.py`, and deliberately a
    different function from `update()`: an author edits *how we reach* a server,
    a governance owner declares *what it may expose*. Sharing one setter would
    make the two field sets one field set, and an author who could widen their
    own data boundary is exactly the hole the gateway exists to close.

    `status`, `endpoint` and `tools_provided` are unreachable from here for the
    mirror-image reason.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        """UPDATE connectors SET
               allowed_datasets_json = $2, allowed_fields_json = $3,
               approved_identities_json = $4, service_account = $5,
               iam_principal = $6, rate_limit_per_min = $7, timeout_ms = $8
           WHERE id = $1 RETURNING *""",
        id_,
        policy["allowed_datasets"],
        policy["allowed_fields"],
        policy["approved_identities"],
        policy["service_account"],
        policy["iam_principal"],
        policy["rate_limit_per_min"],
        policy["timeout_ms"],
    )
    return _row_to_connector(row) if row else None


async def set_tools_provided(id_: str, tools_provided: list[str]) -> Optional[dict[str, Any]]:
    """Rewrite what a connector advertises, from a real `tools/list`.

    Not reachable from the connector editor by design: `tools_provided` is
    evidence gathered from the server, never a claim an author types in
    (services/connector_authoring.py).
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "UPDATE connectors SET tools_provided_json = $2 WHERE id = $1 RETURNING *",
        id_,
        tools_provided,
    )
    return _row_to_connector(row) if row else None
