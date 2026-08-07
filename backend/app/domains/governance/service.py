import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.domains.audit import audit_repo
from app.domains.governance import governance_repo

VALID_PATHS = {"fast", "standard", "deep", "critical"}
VALID_TIERS = {"minimal", "standardized", "advanced"}
VALID_RISKS = {"low", "medium", "high", "critical"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def update_policy_rule(tier: str, risk: str, path: str, actor_persona: str = "Platform Admin") -> dict[str, Any]:
    if tier not in VALID_TIERS or risk not in VALID_RISKS or path not in VALID_PATHS:
        raise ValueError("Invalid capability_tier, risk_tier, or governance_path.")
    rule = await governance_repo.upsert_policy_rule(tier, risk, path, actor_persona)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "update_policy_rule",
            "entity_type": "policy",
            "entity_id": f"{tier}:{risk}",
            "detail": f"{tier} × {risk} → {path} path.",
        }
    )
    return {"rule": rule, "auditEvent": audit_event}


async def update_path_definition(path: str, patch: dict[str, Any], actor_persona: str = "Platform Admin") -> Optional[dict[str, Any]]:
    existing = await governance_repo.get_path_definition(path)
    if existing is None:
        return None
    updated = await governance_repo.update_path_definition(path, patch, actor_persona)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "update_path_definition",
            "entity_type": "policy",
            "entity_id": path,
            "detail": f"Updated {path} path definition: {', '.join(sorted(patch.keys()))}.",
        }
    )
    return {"pathDefinition": updated, "auditEvent": audit_event}


# Exception Management (Blueprint §9) — a temporary exception must carry a real
# expiry date, and this is a real register, not just a free-text agent field.
async def grant_exception(input_: dict[str, Any], actor_persona: str = "Governance Officer") -> dict[str, Any]:
    from app.domains.agents import agents_repo

    agent_id = input_.get("agent_id")
    reason = (input_.get("reason") or "").strip()
    expires_at = input_.get("expires_at")
    if not agent_id or not reason or not expires_at:
        raise ValueError("agent_id, reason, and expires_at are required.")
    if await agents_repo.get_by_id(agent_id) is None:
        raise ValueError("Agent not found.")
    if expires_at <= _now_iso():
        raise ValueError("expires_at must be in the future.")

    exception_id = f"exc-{uuid.uuid4()}"
    exc = {
        "id": exception_id,
        "agent_id": agent_id,
        "reason": reason,
        "granted_by": actor_persona,
        "status": "active",
        "expires_at": expires_at,
    }
    await governance_repo.insert_exception(exc)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "grant_exception",
            "entity_type": "agent",
            "entity_id": agent_id,
            "detail": f"Granted governance exception (expires {expires_at}): {reason}",
        }
    )
    return {"exception": await governance_repo.get_exception(exception_id), "auditEvent": audit_event}


async def revoke_exception(exception_id: str, actor_persona: str = "Governance Officer") -> Optional[dict[str, Any]]:
    existing = await governance_repo.get_exception(exception_id)
    if existing is None:
        return None
    updated = await governance_repo.revoke_exception(exception_id, actor_persona)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "revoke_exception",
            "entity_type": "agent",
            "entity_id": existing["agent_id"],
            "detail": f"Revoked governance exception {exception_id}.",
        }
    )
    return {"exception": updated, "auditEvent": audit_event}
