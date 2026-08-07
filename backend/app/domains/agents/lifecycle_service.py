import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.domains.agents import agents_repo
from app.domains.approvals import approvals_repo
from app.domains.audit import audit_repo
from app.seed_data.constants import FAST_PATH_DAYS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def set_lifecycle(agent_id_str: str, status: str) -> Optional[dict[str, Any]]:
    now = _now_iso()

    # Retire is a one-way door by design (real decommissioning semantics —
    # register a new agent instead of resurrecting one). Enforced here, not
    # just by hiding the button client-side, since nothing stops a direct API
    # call otherwise.
    current = await agents_repo.get_by_id(agent_id_str)
    if current is not None and current["config"]["lifecycle"]["lifecycle_status"]["value"] == "retired":
        raise ValueError("Cannot change lifecycle — agent is retired (permanent).")

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


async def update_risk_tier(agent_id_str: str, risk_tier: str, actor_persona: str = "Governance Officer") -> dict[str, Any]:
    """Onboarding wizard's Phase 5 risk override used to re-derive the
    governance path client-side from a hardcoded copy of the policy matrix
    (kernel/constants.ts) — the same class of drift risk the real
    policy_rules table (module 4) was built to eliminate. This re-derives it
    server-side from that same real table, so an admin editing the policy
    matrix is reflected here too."""
    from app.domains.governance import governance_repo

    agent = await agents_repo.get_by_id(agent_id_str)
    if agent is None:
        raise ValueError("Agent not found.")
    tier = agent["capability_tier"]
    new_path = await governance_repo.governance_path_for(tier, risk_tier)
    if new_path is None:
        raise ValueError(f"No governance policy rule defined for {tier} × {risk_tier}.")

    now = _now_iso()

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        nxt = deepcopy(a)
        nxt["governance_path"] = new_path
        nxt["config"]["lifecycle"]["risk_tier"] = {
            **nxt["config"]["lifecycle"]["risk_tier"],
            "value": risk_tier,
            "value_source": "user",
            "verified_flag": True,
            "confidence": "high",
            "gap_note": None,
        }
        nxt["updated_at"] = now
        return nxt

    updated = await agents_repo.patch(agent_id_str, updater)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": actor_persona,
            "action": "update_risk_tier",
            "entity_type": "agent",
            "entity_id": agent_id_str,
            "detail": f"risk_tier → {risk_tier}; governance path re-derived → {new_path}.",
        }
    )
    return {"agent": updated, "auditEvent": audit_event}


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

    return {"agent": agent, "approval": approval, "auditEvent": audit_event}
