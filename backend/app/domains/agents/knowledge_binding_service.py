import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.domains.agents import agents_repo
from app.domains.approvals import approvals_repo
from app.domains.audit import audit_repo
from app.domains.knowledge import knowledge_sources_repo

GATED_SENSITIVITIES = ("confidential", "restricted")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _apply_bind(agent_id_str: str, source: dict[str, Any], ref: str) -> dict[str, Any]:
    """Shared by the immediate (public/internal) bind path and the deferred
    post-approval path — the actual write to config.data.knowledge_source_refs."""
    now = _now_iso()

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        cur = a["config"]["data"]["knowledge_source_refs"]["value"]
        if ref in cur:
            return a
        nxt = deepcopy(a)
        nxt["config"]["data"]["knowledge_source_refs"]["value"] = [*cur, ref]
        nxt["updated_at"] = now
        return nxt

    agent = await agents_repo.patch(agent_id_str, updater)
    if agent is None:
        return {"ok": False, "message": "Agent not found."}

    used_by = list(dict.fromkeys([*source.get("used_by", []), agent_id_str]))
    await knowledge_sources_repo.mark_used_by(source["id"], used_by)
    source = {**source, "used_by": used_by}

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": "Platform Engineer",
            "action": "bind_knowledge",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": f"Bound knowledge source {source['name']} ({source['sensitivity']}).",
        }
    )

    return {"ok": True, "agent": agent, "source": source, "auditEvent": audit_event}


# The real enforcement point for the sensitivity gate: a confidential/restricted
# source is never written into an agent's config until a risk-officer approves
# it — mirrors tool_binding.py's server-side trust boundary, gated on sensitivity
# instead of write_capable.
async def bind_knowledge_source(agent_id_str: str, source_id: str) -> dict[str, Any]:
    source = await knowledge_sources_repo.get_by_id(source_id)
    if source is None:
        return {"ok": False, "message": "Source not found."}
    if source["lifecycle"] == "retired":
        return {"ok": False, "message": "Cannot bind a retired source."}

    agent = await agents_repo.get_by_id(agent_id_str)
    if agent is None:
        return {"ok": False, "message": "Agent not found."}

    ref = f"kb://{source_id}"

    if source["sensitivity"] in GATED_SENSITIVITIES:
        existing = await approvals_repo.get_pending_by_target(agent_id_str, ref)
        if existing:
            return {
                "ok": False,
                "pending": True,
                "approval": existing,
                "message": "Approval already pending for this source.",
            }

        now = _now_iso()
        approval = {
            "id": f"appr-{uuid.uuid4()}",
            "agent_id": agent_id_str,
            "step": "data_source",
            "required_by_path": agent["governance_path"],
            "status": "pending",
            "actor_persona": None,
            "decided_at": None,
            "note": f"Bind request: {source['name']} ({source['sensitivity']}).",
            "requested_at": now,
            "target_ref": ref,
        }
        await approvals_repo.insert(approval)

        audit_event = await audit_repo.insert(
            {
                "id": f"aud-{uuid.uuid4()}",
                "at": now,
                "actor_persona": "Platform Engineer",
                "action": "bind_pending",
                "entity_type": "agent",
                "entity_id": agent_id_str,
                "detail": f"Bind request for {source['sensitivity']} source {source['name']} — pending risk-officer approval.",
            }
        )

        return {
            "ok": False,
            "pending": True,
            "approval": approval,
            "auditEvent": audit_event,
            "message": f"{source['name']} is {source['sensitivity']} — requires risk-officer approval.",
        }

    return await _apply_bind(agent_id_str, source, ref)


async def finalize_bind_after_approval(agent_id_str: str, target_ref: str) -> None:
    source_id = target_ref.replace("kb://", "", 1)
    source = await knowledge_sources_repo.get_by_id(source_id)
    if source is not None:
        await _apply_bind(agent_id_str, source, target_ref)
