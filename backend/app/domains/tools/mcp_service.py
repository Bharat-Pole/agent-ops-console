import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.domains.audit import audit_repo
from app.domains.tools import mcp_connectors_repo

HEALTHCHECK_TIMEOUT_S = 4.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# A REAL network attempt, not a simulated status flip. Note: this repo's seeded
# connectors point at fictional *.brightspeed.internal hostnames (Brightspeed's
# actual internal MCP servers) — those will genuinely fail to resolve from any
# environment outside Brightspeed's network, and this will honestly report that
# rather than pretend success. Point `endpoint` at a real reachable URL to see
# a real "connected" result.
async def healthcheck_connector(connector_id: str, actor_persona: str = "Platform Engineer") -> Optional[dict[str, Any]]:
    connector = await mcp_connectors_repo.get_by_id(connector_id)
    if connector is None:
        return None

    now = _now_iso()
    status = "offline"
    error: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=HEALTHCHECK_TIMEOUT_S) as client:
            resp = await client.get(connector["endpoint"])
        status = "connected" if resp.status_code < 500 else "degraded"
        if resp.status_code >= 400:
            error = f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        error = f"Timed out after {HEALTHCHECK_TIMEOUT_S}s."
    except httpx.ConnectError as e:
        error = f"Connection failed: {e}"
    except Exception as e:
        error = str(e)

    updated = await mcp_connectors_repo.patch(
        connector_id, {"status": status, "last_healthcheck": now, "last_error": error}
    )
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": actor_persona,
            "action": "healthcheck",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": f"Healthcheck → {status}." + (f" ({error})" if error else ""),
        }
    )
    return {"connector": updated, "auditEvent": audit_event}


async def toggle_connector(connector_id: str, actor_persona: str = "Platform Engineer") -> Optional[dict[str, Any]]:
    connector = await mcp_connectors_repo.get_by_id(connector_id)
    if connector is None:
        return None
    new_status = "connected" if connector["status"] == "offline" else "offline"
    updated = await mcp_connectors_repo.patch(connector_id, {"status": new_status, "last_healthcheck": _now_iso()})
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "toggle_connector",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": f"Manually set to {new_status}.",
        }
    )
    return {"connector": updated, "auditEvent": audit_event}


async def delete_connector(connector_id: str, actor_persona: str = "Platform Engineer") -> Optional[dict[str, Any]]:
    existing = await mcp_connectors_repo.get_by_id(connector_id)
    if existing is None:
        return None
    if existing["tools_provided"]:
        raise ValueError(f"Cannot delete — {len(existing['tools_provided'])} tool(s) still reference this connector.")
    await mcp_connectors_repo.delete_by_id(connector_id)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "delete_connector",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": f"Deleted MCP connector \"{existing['name']}\" ({connector_id}).",
        }
    )
    return {"auditEvent": audit_event}


async def register_connector(input_: dict[str, Any], actor_persona: str = "Platform Engineer") -> dict[str, Any]:
    name = (input_.get("name") or "").strip()
    endpoint = (input_.get("endpoint") or "").strip()
    if not name or not endpoint:
        raise ValueError("name and endpoint are required.")

    connector_id = input_.get("id") or name.strip().lower().replace(" ", "-")
    connector = {
        "id": connector_id,
        "name": name,
        "transport": input_.get("transport", "http"),
        "endpoint": endpoint,
        "auth_mode": input_.get("auth_mode", "none"),
        "status": "connected",
        "tools_provided": input_.get("tools_provided", []),
    }
    await mcp_connectors_repo.insert(connector)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "register_connector",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": f"Registered MCP connector \"{name}\" ({connector['transport']}).",
        }
    )
    return {"connector": await mcp_connectors_repo.get_by_id(connector_id), "auditEvent": audit_event}
