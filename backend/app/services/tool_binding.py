import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.repositories import agents_repo, audit_repo, connectors_repo, tools_repo
from app.services.tool_call_log import record_blocked_bind


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# Binding is a *design-time* declaration; connector health is a *runtime*
# condition. Gating a config write on flapping infrastructure would make agent
# definitions non-deterministic, so an unhealthy connector warns and never
# blocks. The blocking gate lives at deploy time (Pre-Flight check #4).
async def _health_warning(tool: dict[str, Any]) -> str | None:
    connector_id = tool["connector_id"]
    if connector_id is None:
        return None  # local tool — serves itself, no MCP server to be unhealthy
    connector = await connectors_repo.get_by_id(connector_id)
    if connector is None or connector["status"] == "connected":
        return None
    return (
        f"{connector['name']} is {connector['status']} — {tool['id']} is bound "
        f"but will not be callable until the connector recovers."
    )


async def _reject(agent_id_str: str, tool_id: str, reason: str, detail: str) -> dict[str, Any]:
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": "bind_rejected",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": detail,
        }
    )
    # Slide 21 element 6: a blocked attempt is evidence, not a non-event. This
    # turns a governance rejection into a visible row instead of a silent
    # failure. Best-effort — it must never break the rejection itself.
    await record_blocked_bind(agent_id_str, tool_id, reason)
    return {"ok": False, "message": reason, "auditEvent": audit_event}


# The real enforcement point for the advisory-only invariant: no flow can bind
# a write_capable tool. This is the server's own trust boundary — it never
# trusts a client-supplied `write_capable` claim, only its own `tools` table.
#
# Phase 3.2 adds a second, independent gate here: an unapproved tool does not
# bind either. Both are re-read from the server's own row for the same reason —
# a client that could assert either field could bind anything.
async def bind_tool(agent_id_str: str, tool_id: str) -> dict[str, Any]:
    tool = await tools_repo.get_by_id(tool_id)
    if tool is None:
        return {"ok": False, "message": "Tool not found."}

    # Checked first, and independently of approval: write-capability is the
    # locked invariant, so a write-capable tool is rejected on that ground even
    # if someone has approved it. Approval must never become a way to launder a
    # write tool into a binding (ROADMAP Q6 — changing that is a governance
    # decision, not a code tweak).
    if tool["write_capable"]:
        return await _reject(
            agent_id_str,
            tool_id,
            f"{tool_id} is write-capable — advisory-block. Cannot be bound.",
            f"Attempt to bind write-capable tool {tool_id} REJECTED — advisory-only scope enforced.",
        )

    if tool["approval_state"] != "approved":
        state = tool["approval_state"]
        return await _reject(
            agent_id_str,
            tool_id,
            f"{tool_id} is {state} approval — cannot be bound until it is approved.",
            f"Attempt to bind {state} tool {tool_id} REJECTED — tool approval required (Blueprint §11).",
        )

    ref = f"tools://{tool_id}@{tool['version']}"
    now = _now_iso()

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        cur = a["config"]["tooling"]["bound_tools"]["value"]
        if ref in cur:
            return a
        nxt = deepcopy(a)
        nxt["config"]["tooling"]["bound_tools"]["value"] = [*cur, ref]
        nxt["updated_at"] = now
        return nxt

    agent = await agents_repo.patch(agent_id_str, updater)
    if agent is None:
        return {"ok": False, "message": "Agent not found."}

    used_by = list(dict.fromkeys([*tool["used_by"], agent_id_str]))
    await tools_repo.mark_used_by(tool_id, used_by)

    warning = await _health_warning(tool)
    detail = f"Bound read-only tool {tool_id} ({tool['permission_ceiling']})."
    if warning:
        detail += f" WARNING: {warning}"

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": "bind_tool",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": detail,
        }
    )

    return {"ok": True, "agent": agent, "tool": tool, "auditEvent": audit_event, "warning": warning}
