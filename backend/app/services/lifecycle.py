import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.repositories import agents_repo, approvals_repo, audit_repo
from app.seed_data.constants import FAST_PATH_DAYS
from app.services.bound_tools_guard import record_stripped, sanitize_bound_tools


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def set_lifecycle(agent_id_str: str, status: str) -> Optional[dict[str, Any]]:
    now = _now_iso()

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        nxt = deepcopy(a)
        nxt["config"]["lifecycle"]["lifecycle_status"] = {
            **nxt["config"]["lifecycle"]["lifecycle_status"], "value": status,
        }
        nxt["updated_at"] = now
        return nxt

    agent = await agents_repo.patch(agent_id_str, updater)
    if agent is None:
        return None
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": "Governance Officer",
            "action": "resume" if status == "live" else status,
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": f"Lifecycle set to {status}.",
        }
    )
    return {"agent": agent, "auditEvent": audit_event}


async def recertify(agent_id_str: str) -> Optional[dict[str, Any]]:
    now = _now_iso()
    new_expiry = (datetime.now(timezone.utc) + timedelta(days=FAST_PATH_DAYS)).date().isoformat()

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        nxt = deepcopy(a)
        nxt["fast_path_expiry_date"] = new_expiry
        nxt["updated_at"] = now
        return nxt

    agent = await agents_repo.patch(agent_id_str, updater)
    if agent is None:
        return None
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": "Governance Officer",
            "action": "recertify",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": f"Fast-path re-certified; expiry extended to {new_expiry}.",
        }
    )
    return {"agent": agent, "auditEvent": audit_event}


async def enable_demo_mode(agent_id_str: str) -> Optional[dict[str, Any]]:
    now = _now_iso()

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        return {**a, "demo_mode": True, "updated_at": now}

    agent = await agents_repo.patch(agent_id_str, updater)
    if agent is None:
        return None
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": "Team Lead / Consumer",
            "action": "demo_mode",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": "Demo Mode enabled — attached vector://alloydb-demo; responding with synthetic data.",
        }
    )
    return {"agent": agent, "auditEvent": audit_event}


GOV_CRITICAL = {"risk_tier", "tool_permission", "sensitivity"}


async def propose_config_change(agent_id_str: str, group_key: str, field: str, new_value: Any) -> Optional[dict[str, Any]]:
    critical = field in GOV_CRITICAL
    now = _now_iso()

    # R8 — the third door onto `bound_tools`: this endpoint sets any field in
    # any group wholesale, so `groupKey: "tooling", field: "bound_tools"` would
    # otherwise write an arbitrary array. Same guard, same rules, one place.
    stripped: list[dict[str, Any]] = []
    if group_key == "tooling" and field == "bound_tools":
        new_value, stripped = await sanitize_bound_tools(new_value)

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        cfg = a["config"]
        group = cfg.get(group_key)
        # Preserve the Node quirk: an unknown groupKey/field is a silent
        # agent-unchanged no-op, not an error — nothing depends on this being
        # a 400 today, and changing it isn't in scope for the port.
        if not group or field not in group:
            return a
        nxt = deepcopy(a)
        g = nxt["config"][group_key]
        g[field] = {
            **g[field],
            "value": new_value,
            "value_source": "user",
            "verified_flag": not critical,
            "confidence": "medium" if critical else "high",
            "gap_note": "User-proposed change — pending re-review." if critical else None,
        }
        nxt["updated_at"] = now
        return nxt

    agent = await agents_repo.patch(agent_id_str, updater)
    if agent is None:
        return None

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": "Business Owner",
            "action": "config_change",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": (
                f"Proposed change: {field} → {json.dumps(new_value)}."
                + (" Governance-critical — new approval required." if critical else "")
            ),
        }
    )

    approval = None
    if critical:
        approval = {
            "id": f"appr-{uuid.uuid4()}",
            "agent_id": agent_id_str,
            "step": "risk_officer",
            "required_by_path": agent["governance_path"],
            "status": "pending",
            "actor_persona": None,
            "decided_at": None,
            "note": f"Re-review: {field} changed.",
            "requested_at": now,
        }
        await approvals_repo.insert(approval)

    await record_stripped(agent_id_str, stripped)

    return {"agent": agent, "approval": approval, "auditEvent": audit_event, "strippedTools": stripped}
