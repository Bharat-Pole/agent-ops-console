import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import audit_repo, connectors_repo, tools_repo
from app.services import mcp_client
from app.services.tool_approval import request_tool_approval

# Connector status values (mirrors McpStatus in src/types/assets.ts).
CONNECTED = "connected"
DEGRADED = "degraded"
OFFLINE = "offline"

# Chance a *simulated* healthcheck comes back degraded. Matches the ~18% the
# client-side simulation used, so seeded connectors behave as before.
_DEGRADED_CHANCE = 0.18

# Phase 5A — a connector is "live" when its endpoint is one we can actually
# open a session against. Everything else stays on the simulated path.
#
# The distinction is deliberately visible in the data (`connectors.last_probe`)
# and not just in behaviour: a fabricated green tick on a connector that was
# never contacted is worse than no tick at all, so the two must never be
# indistinguishable downstream.
_LIVE_SCHEMES = ("http://", "https://")

# `streamable_http` is the opt-in signal for real traffic. This is deliberately
# stricter than "the endpoint looks like a URL": the seeded connectors carry
# plausible-looking `https://…brightspeed.internal/…` endpoints that were never
# meant to resolve, and probing those would mark every seeded connector offline
# the first time anyone ran a healthcheck.
#
# So the rule is: choosing the spec-current transport is how a connector says
# "I am real, talk to me". Legacy `sse`/`http` rows stay on the simulated path,
# which is also what makes the D8 migration safe to land incrementally.
LIVE_TRANSPORT = "streamable_http"


def is_live_connector(connector: dict[str, Any]) -> bool:
    """True when this connector should be contacted over the wire."""
    if connector.get("transport") != LIVE_TRANSPORT:
        return False
    endpoint = connector.get("endpoint") or ""
    return endpoint.lower().startswith(_LIVE_SCHEMES)


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
    """Probe a connector. Real over the wire when possible, simulated otherwise.

    Phase 5A split this in two. A connector with a reachable Streamable HTTP
    endpoint is genuinely contacted — session opened, `tools/list` issued,
    latency measured — and the evidence is stored in `last_probe`. A connector
    without one keeps the ~18% roll and stores **no** probe evidence, so the
    difference is legible in the data rather than only in behaviour.
    """
    connector = await connectors_repo.get_by_id(connector_id)
    if connector is None:
        raise ValueError("Connector not found.")

    # An offline connector stays offline — a healthcheck doesn't silently
    # revive something an operator deliberately took down.
    if connector["status"] == OFFLINE:
        return {"connector": connector, "changedTools": [], "auditEvent": None, "skipped": True}

    if not is_live_connector(connector):
        status = DEGRADED if random.random() < _DEGRADED_CHANCE else CONNECTED
        result = await _apply_status(
            connector_id, status, "healthcheck", f"Healthcheck (simulated) → {status}."
        )
        # Enforce the invariant rather than merely honour it: `last_probe` is
        # non-NULL if and only if the *most recent* healthcheck actually reached
        # a socket. A connector that was live and is no longer must not keep
        # presenting stale evidence of a real probe.
        if connector.get("last_probe") is not None:
            cleared = await connectors_repo.set_probe(connector_id, None)
            if cleared is not None:
                result["connector"] = cleared
        return result

    probe = await mcp_client.probe(connector["endpoint"])
    status = CONNECTED if probe["ok"] else OFFLINE
    detail = (
        f"Healthcheck (live probe) → {status} in {probe['latency_ms']}ms, "
        f"protocol {probe['protocol_version']}, {probe['tool_count']} tool(s) advertised."
        if probe["ok"]
        else f"Healthcheck (live probe) → {status}. Unreachable: {probe['error']}"
    )

    result = await _apply_status(connector_id, status, "healthcheck", detail)
    updated = await connectors_repo.set_probe(connector_id, {**probe, "at": _now_iso()})
    if updated is not None:
        result["connector"] = updated
    return result


async def toggle_offline(connector_id: str) -> dict[str, Any]:
    connector = await connectors_repo.get_by_id(connector_id)
    if connector is None:
        raise ValueError("Connector not found.")

    status = CONNECTED if connector["status"] == OFFLINE else OFFLINE
    detail = f"Connector set {status}."
    if status == OFFLINE:
        detail += " Pre-Flight hard blocker #4 now red."

    return await _apply_status(connector_id, status, "toggle_connector", detail)


def discovered_tool_id(connector_id: str, remote_tool_id: str) -> str:
    """Namespaced id for a discovered tool.

    `{connector_id}.{remote_tool_id}` — deterministic, so re-running discovery
    updates rather than duplicates; namespaced, so two connectors may serve a
    same-named tool; and legible, so a tool's origin is obvious from its id.
    """
    return f"{connector_id}.{remote_tool_id}"


async def list_connector_tools(connector_id: str) -> dict[str, Any]:
    """MCP `tools/list` — the tools a connector advertises.

    **Phase 5A made this real (closes ROADMAP D7).** For a connector with a
    reachable endpoint this issues an actual `tools/list` and *writes* what it
    finds into the catalog, with `connector_id` and `remote_tool_id` set. That
    is what makes the `undiscovered`/`orphaned` diff meaningful: previously
    nothing in the product could attach a tool to a connector, so the diff was
    structurally unreachable.

    For a connector without a reachable endpoint the old behaviour stands — read
    back what the catalog already holds — because inventing a listing for a
    server we never contacted would be fabricating evidence.

    Returned shape is unchanged apart from three additive keys (`live`,
    `rejected`, `created`), so existing callers keep working.
    """
    connector = await connectors_repo.get_by_id(connector_id)
    if connector is None:
        raise ValueError("Connector not found.")

    if is_live_connector(connector):
        return await _discover_live(connector)

    advertised = set(connector["tools_provided"] or [])
    tools = [t for t in await tools_repo.get_all() if t["connector_id"] == connector_id or t["id"] in advertised]
    catalogued_ids = {t["id"] for t in tools}
    return {
        "connector": connector,
        "tools": tools,
        "undiscovered": sorted(advertised - catalogued_ids),
        "orphaned": sorted(t["id"] for t in tools if t["id"] not in advertised and t["connector_id"] == connector_id),
        "live": False,
        "rejected": [],
        "created": [],
    }


async def _discover_live(connector: dict[str, Any]) -> dict[str, Any]:
    """Real `tools/list` against a reachable connector, persisting the result."""
    connector_id = connector["id"]

    try:
        listing = await mcp_client.list_remote_tools(connector["endpoint"], connector_id)
    except mcp_client.McpProtocolError as exc:
        # Unreachable mid-discovery is a health fact, so record it as one rather
        # than only failing the request. Deliberately does NOT wipe previously
        # discovered tools: a transient outage must not erase the catalog.
        await _apply_status(
            connector_id, OFFLINE, "healthcheck", f"Discovery failed, connector unreachable: {exc}"
        )
        raise

    known_before = {t["remote_tool_id"]: t for t in await tools_repo.get_discovered_for_connector(connector_id)}
    now = _now_iso()
    tool_status = connector_health_to_tool_status(connector["status"])

    persisted: list[dict[str, Any]] = []
    created_ids: list[str] = []
    flipped: list[str] = []

    for mapped in listing["tools"]:
        record = {
            **mapped,
            "id": discovered_tool_id(connector_id, mapped["remote_tool_id"]),
            "status": tool_status,
            "discovered_at": now,
        }
        tool, created = await tools_repo.upsert_discovered(record)
        persisted.append(tool)

        # A tool left `pending` with nothing in the approval queue is a dead
        # end: the state is visible but unapprovable, because the queue is the
        # only route to a decision. So anything that lands pending must also be
        # queued — on first discovery, and again if a write-capability change
        # sent an already-approved tool back to pending.
        if created:
            created_ids.append(tool["id"])
            await request_tool_approval(tool)
        elif tool.get("write_flipped"):
            flipped.append(tool["id"])
            if tool["approval_state"] == "pending":
                await request_tool_approval(tool)

    # Orphans: previously discovered from THIS connector, absent from this
    # listing. Reported, never deleted — a tool can be referenced by audit rows
    # and tool-call history that must outlive it.
    seen = {m["remote_tool_id"] for m in listing["tools"]}
    orphaned = sorted(t["id"] for rid, t in known_before.items() if rid not in seen)

    # `tools_provided` becomes evidence rather than a claim: it is now exactly
    # what the server said, on this listing.
    updated_connector = await connectors_repo.set_tools_provided(
        connector_id, sorted(t["id"] for t in persisted)
    )

    detail = (
        f"Discovered {len(persisted)} tool(s) over MCP "
        f"(protocol {listing['protocol_version']}); {len(created_ids)} new, "
        f"{len(listing['rejected'])} rejected, {len(orphaned)} orphaned."
    )
    if flipped:
        detail += f" {len(flipped)} tool(s) returned to pending after a write-capability change."
    await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": "Platform Engineer",
            "action": "discover_tools",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": detail,
        }
    )

    return {
        "connector": updated_connector or connector,
        "tools": persisted,
        # Nothing is undiscovered after a real listing: we just wrote everything
        # the server advertised. A non-empty list here would be a bug.
        "undiscovered": [],
        "orphaned": orphaned,
        "live": True,
        "rejected": listing["rejected"],
        "created": created_ids,
        "protocol_version": listing["protocol_version"],
        "server_info": listing["server_info"],
    }
