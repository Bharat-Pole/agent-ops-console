import random
import uuid
from datetime import datetime, timezone
from typing import Any

from app.repositories import audit_repo, connectors_repo, tools_repo

# Connector status values (mirrors McpStatus in src/types/assets.ts).
CONNECTED = "connected"
DEGRADED = "degraded"
OFFLINE = "offline"

# Chance a healthcheck comes back degraded. Matches the ~18% the client-side
# simulation used, so the demo behaves the same now that it runs server-side.
_DEGRADED_CHANCE = 0.18


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def connector_health_to_tool_status(status: str) -> str:
    """A tool is never healthier than the connector that serves it.

    An offline MCP server cannot serve its tools, so tool status is *derived*
    from connector status rather than stored independently. The inverse has no
    physical meaning, which is why this mapping is one-directional.
    """
    if status == OFFLINE:
        return "offline"
    if status == DEGRADED:
        return "degraded"
    return "available"


async def cascade_connector_health(connector_id: str, status: str) -> list[dict[str, Any]]:
    """Push a connector's health down onto every tool it serves.

    Returns the tools that actually changed, so the caller can hand the client
    a precise patch list instead of forcing a full bootstrap refetch.

    Tools with `connector_id = NULL` are local and deliberately untouched —
    roughly half the seeded catalog is local, so cascading blindly would be
    wrong.
    """
    tool_status = connector_health_to_tool_status(status)
    changed: list[dict[str, Any]] = []

    for tool in await tools_repo.get_all():
        if tool["connector_id"] == connector_id and tool["status"] != tool_status:
            await tools_repo.set_status(tool["id"], tool_status)
            changed.append({**tool, "status": tool_status})

    return changed


async def _apply_status(connector_id: str, status: str, action: str, detail: str) -> dict[str, Any]:
    connector = await connectors_repo.set_status(connector_id, status, _now_iso())
    if connector is None:
        raise ValueError("Connector not found.")

    changed_tools = await cascade_connector_health(connector_id, status)

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": action,
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": detail
            + (f" Cascaded to {len(changed_tools)} tool(s)." if changed_tools else ""),
        }
    )

    return {"connector": connector, "changedTools": changed_tools, "auditEvent": audit_event}


async def run_healthcheck(connector_id: str) -> dict[str, Any]:
    connector = await connectors_repo.get_by_id(connector_id)
    if connector is None:
        raise ValueError("Connector not found.")

    # An offline connector stays offline — a healthcheck doesn't silently
    # revive something an operator deliberately took down.
    if connector["status"] == OFFLINE:
        return {"connector": connector, "changedTools": [], "auditEvent": None, "skipped": True}

    status = DEGRADED if random.random() < _DEGRADED_CHANCE else CONNECTED
    return await _apply_status(connector_id, status, "healthcheck", f"Healthcheck → {status}.")


async def toggle_offline(connector_id: str) -> dict[str, Any]:
    connector = await connectors_repo.get_by_id(connector_id)
    if connector is None:
        raise ValueError("Connector not found.")

    status = CONNECTED if connector["status"] == OFFLINE else OFFLINE
    detail = f"Connector set {status}."
    if status == OFFLINE:
        detail += " Pre-Flight hard blocker #4 now red."

    return await _apply_status(connector_id, status, "toggle_connector", detail)


async def list_connector_tools(connector_id: str) -> dict[str, Any]:
    """MCP `tools/list` — the tools a connector advertises.

    Today this reads the catalog the server already owns. A real MCP client
    would issue a tools/list RPC over the connector's transport and map the
    response into this same shape, which is why the return contract is the
    tool list plus the connector it came from.
    """
    connector = await connectors_repo.get_by_id(connector_id)
    if connector is None:
        raise ValueError("Connector not found.")

    advertised = set(connector["tools_provided"] or [])
    tools = [t for t in await tools_repo.get_all() if t["connector_id"] == connector_id or t["id"] in advertised]

    # Discovery diff — what the connector claims vs. what the catalog holds.
    catalogued_ids = {t["id"] for t in tools}
    return {
        "connector": connector,
        "tools": tools,
        "undiscovered": sorted(advertised - catalogued_ids),
        "orphaned": sorted(t["id"] for t in tools if t["id"] not in advertised and t["connector_id"] == connector_id),
    }
