import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import agents_repo, approvals_repo, audit_repo
from app.services.registration import finalize_registry
from app.services.tool_approval import decide_tool_approval


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def decide_approval(
    approval_id: str, decision: str, note: str, actor_persona: str = "Governance Officer"
) -> Optional[dict[str, Any]]:
    item = await approvals_repo.get_by_id(approval_id)
    if item is None:
        return None

    now = _now_iso()
    approval = await approvals_repo.patch(approval_id, decision, actor_persona, now, note)

    # Phase 3.2 — the queue is shared across entity kinds (Blueprint §11), so
    # the subject of an item is `entity_type`/`entity_id`, not `agent_id`.
    # Pre-Phase-3 rows are backfilled to entity_type='agent', so this stays the
    # same decision path it always was for agents.
    subject = item.get("entity_id") or item.get("agent_id")
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": actor_persona,
            "action": "approve" if decision == "approved" else "reject",
            "entity_type": "approval",
            "entity_id": approval_id,
            "detail": f"{item['step']} {decision} for {subject}.{(' ' + note) if note else ''}",
        }
    )

    if item.get("entity_type") == "tool":
        tool = await decide_tool_approval(item, decision, note, actor_persona, now)
        return {"approval": approval, "agent": None, "tool": tool, "auditEvent": audit_event}

    agent = None
    if decision == "approved":
        agent = await finalize_registry(item["agent_id"])
    if agent is None:
        agent = await agents_repo.get_by_id(item["agent_id"])

    return {"approval": approval, "agent": agent, "tool": None, "auditEvent": audit_event}
