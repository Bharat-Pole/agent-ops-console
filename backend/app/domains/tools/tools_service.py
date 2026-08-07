import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.domains.audit import audit_repo
from app.domains.tools import tools_repo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "tool"


# Advisory base scope (Section 7.6, LOCKED): this registration path can never
# mint a write_capable tool — write_capable is hardcoded False here, not left
# to the caller, so a client bug or malicious request can't smuggle one in.
async def register_tool(input_: dict[str, Any], actor_persona: str = "Platform Engineer") -> dict[str, Any]:
    name = (input_.get("name") or "").strip()
    if not name:
        raise ValueError("name is required.")
    if input_.get("permission_ceiling") not in ("read", "summarize", "draft", "recommend", "validate"):
        raise ValueError("permission_ceiling must be one of: read, summarize, draft, recommend, validate.")

    base_id = _slugify(name)
    tool_id = base_id
    suffix = 2
    while await tools_repo.get_by_id(tool_id) is not None:
        tool_id = f"{base_id}_{suffix}"
        suffix += 1

    tool = {
        "id": tool_id,
        "version": "v1",
        "name": name,
        "description": input_.get("description", ""),
        "category": input_.get("category", "general"),
        "permission_ceiling": input_["permission_ceiling"],
        "write_capable": False,
        "connector_id": input_.get("connector_id"),
        "schema": input_.get("schema") or {"inputs": {"query": "string"}, "outputs": {"result": "string"}},
        "status": "available",
        "owner": input_.get("owner"),
        "risk_level": input_.get("risk_level", "low"),
        "used_by": [],
    }
    await tools_repo.insert(tool)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "register_tool",
            "entity_type": "tool",
            "entity_id": tool_id,
            "detail": f"Registered tool \"{name}\" ({tool['permission_ceiling']}, advisory-only).",
        }
    )
    return {"tool": await tools_repo.get_by_id(tool_id), "auditEvent": audit_event}


async def update_tool(tool_id: str, patch: dict[str, Any], actor_persona: str = "Platform Engineer") -> Optional[dict[str, Any]]:
    existing = await tools_repo.get_by_id(tool_id)
    if existing is None:
        return None
    updated = await tools_repo.update_fields(tool_id, patch)
    await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "update_tool",
            "entity_type": "tool",
            "entity_id": tool_id,
            "detail": f"Updated fields: {', '.join(sorted(patch.keys()))}.",
        }
    )
    return updated


async def delete_tool(tool_id: str, actor_persona: str = "Platform Engineer") -> Optional[dict[str, Any]]:
    existing = await tools_repo.get_by_id(tool_id)
    if existing is None:
        return None
    if existing["used_by"]:
        raise ValueError(f"Cannot delete — bound to {len(existing['used_by'])} agent(s). Unbind first.")
    await tools_repo.delete_by_id(tool_id)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "delete_tool",
            "entity_type": "tool",
            "entity_id": tool_id,
            "detail": f"Deleted tool \"{existing['name']}\" ({tool_id}).",
        }
    )
    return {"auditEvent": audit_event}
