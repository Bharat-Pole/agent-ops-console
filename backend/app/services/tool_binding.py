import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.repositories import agents_repo, audit_repo, tools_repo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# The real enforcement point for the advisory-only invariant: no flow can bind
# a write_capable tool. This is the server's own trust boundary — it never
# trusts a client-supplied `write_capable` claim, only its own `tools` table.
async def bind_tool(agent_id_str: str, tool_id: str) -> dict[str, Any]:
    tool = await tools_repo.get_by_id(tool_id)
    if tool is None:
        return {"ok": False, "message": "Tool not found."}

    if tool["write_capable"]:
        audit_event = await audit_repo.insert(
            {
                "id": f"aud-{uuid.uuid4()}",
                "at": _now_iso(),
                "actor_persona": "Platform Engineer",
                "action": "bind_rejected",
                "entity_type": "agent",
                "entity_id": agent_id_str,
                "detail": f"Attempt to bind write-capable tool {tool_id} REJECTED — advisory-only scope enforced.",
            }
        )
        return {
            "ok": False,
            "message": f"{tool_id} is write-capable — advisory-block. Cannot be bound.",
            "auditEvent": audit_event,
        }

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

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": "bind_tool",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": f"Bound read-only tool {tool_id} ({tool['permission_ceiling']}).",
        }
    )

    return {"ok": True, "agent": agent, "tool": tool, "auditEvent": audit_event}
