import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import agents_repo, approvals_repo, audit_repo
from app.services.registration import finalize_registry


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

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": actor_persona,
            "action": "approve" if decision == "approved" else "reject",
            "entity_type": "approval",
            "entity_id": approval_id,
            "detail": f"{item['step']} {decision} for {item['agent_id']}.{(' ' + note) if note else ''}",
        }
    )

    agent = None
    if decision == "approved":
        if item["step"] == "data_source" and item.get("target_ref"):
            from app.services.knowledge_binding import finalize_bind_after_approval
            await finalize_bind_after_approval(item["agent_id"], item["target_ref"])
        agent = await finalize_registry(item["agent_id"])
    if agent is None:
        agent = await agents_repo.get_by_id(item["agent_id"])

    return {"approval": approval, "agent": agent, "auditEvent": audit_event}
