import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.domains.agents import agents_repo
from app.domains.audit import audit_repo
from app.domains.deployment import deployment_repo
from app.domains.evaluations import eval_packs_repo

# The only two environments the system actually models today (see
# src/seed/config-factory.ts: environment = 'production' if lifecycle_status
# == 'live' else 'staging') — this is the real ladder an agent moves through,
# not an invented dev/staging/prod scheme with no backing data.
ENV_LADDER = ["staging", "production"]
DEEP_EVAL_PASS_SCORE = 90  # mirrors kernel/constants.ts DEEP_EVAL_PASS_SCORE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _current_environment(agent: dict[str, Any], latest_record: Optional[dict[str, Any]]) -> str:
    if latest_record is not None:
        return latest_record["to_environment"]
    return agent["config"]["deployment"]["environment"]["value"]


async def backfill_deployment_state() -> int:
    """For every agent with no deployment history yet, record its current real
    environment (derived from its existing config, not fabricated) as the
    'initial' entry, and grant its real business/technical owners access.
    Idempotent — agents that already have records are skipped, so this is
    safe to call on every boot."""
    agents = await agents_repo.get_all()
    created = 0
    for agent in agents:
        aid = agents_repo.agent_id(agent)
        if await deployment_repo.has_records(aid):
            continue
        cfg = agent["config"]
        env = cfg["deployment"]["environment"]["value"]
        strategy = cfg["deployment"]["promotion_rollback"]["value"]
        stamp = agent.get("created_at") or _now_iso()
        await deployment_repo.insert_record(
            {
                "id": f"dep-{uuid.uuid4()}",
                "agent_id": aid,
                "action": "initial",
                "from_environment": None,
                "to_environment": env,
                "strategy": strategy,
                "status": "success",
                "reason": "Initial environment recorded from agent configuration.",
                "actor_persona": "system",
                "created_at": stamp,
            }
        )
        for grantee, label in (
            (cfg["identity"]["business_owner"]["value"], "Business Owner"),
            (cfg["identity"]["technical_owner"]["value"], "Technical Owner"),
        ):
            if grantee:
                await deployment_repo.insert_grant(
                    {
                        "id": f"grant-{uuid.uuid4()}",
                        "agent_id": aid,
                        "grantee": grantee,
                        "role_label": label,
                        "scope": "owner",
                        "granted_by": "system",
                        "status": "active",
                        "granted_at": stamp,
                    }
                )
        created += 1

    if not await deployment_repo.has_platform_grant():
        await deployment_repo.insert_grant(
            {
                "id": f"grant-{uuid.uuid4()}",
                "agent_id": None,
                "grantee": "Platform Admin",
                "role_label": "Platform Admin",
                "scope": "admin",
                "granted_by": "system",
                "status": "active",
                "granted_at": _now_iso(),
            }
        )
    return created


async def get_history(agent_id: str) -> dict[str, Any]:
    agent = await agents_repo.get_by_id(agent_id)
    if agent is None:
        raise ValueError("Agent not found.")
    records = await deployment_repo.get_history(agent_id)
    current = _current_environment(agent, records[0] if records else None)
    return {"current_environment": current, "records": records}


async def get_all_environments() -> dict[str, str]:
    """Real current environment per agent, for the Agent Registry list —
    every agent already has at least one deployment_record from the
    module's backfill, so the config fallback below only matters defensively."""
    agents = await agents_repo.get_all()
    latest = await deployment_repo.get_latest_environments()
    result: dict[str, str] = {}
    for agent in agents:
        aid = agents_repo.agent_id(agent)
        result[aid] = latest.get(aid) or agent["config"]["deployment"]["environment"]["value"]
    return result


async def promote(agent_id: str, actor_persona: str, reason: Optional[str] = None) -> dict[str, Any]:
    agent = await agents_repo.get_by_id(agent_id)
    if agent is None:
        raise ValueError("Agent not found.")
    latest = await deployment_repo.get_latest(agent_id)
    current = _current_environment(agent, latest)
    idx = ENV_LADDER.index(current) if current in ENV_LADDER else 0
    if idx >= len(ENV_LADDER) - 1:
        raise ValueError(f"{current} is already the top of the environment ladder — nothing to promote to.")
    target = ENV_LADDER[idx + 1]

    lifecycle_status = agent["config"]["lifecycle"]["lifecycle_status"]["value"]
    if lifecycle_status not in ("approved", "live"):
        raise ValueError(
            f"Cannot promote to {target}: agent lifecycle_status is '{lifecycle_status}', "
            "must be 'approved' or 'live'."
        )
    pack_id = agent.get("evaluation_pack_id")
    if pack_id:
        pack = await eval_packs_repo.get_by_id(pack_id)
        score = (pack or {}).get("last_run", {}).get("score") if pack else None
        if score is None:
            raise ValueError(f"Cannot promote to {target}: no evaluation has been run for this agent yet.")
        if score < DEEP_EVAL_PASS_SCORE:
            raise ValueError(
                f"Cannot promote to {target}: last eval score is {score}, below the required {DEEP_EVAL_PASS_SCORE}."
            )

    record = await deployment_repo.insert_record(
        {
            "id": f"dep-{uuid.uuid4()}",
            "agent_id": agent_id,
            "action": "promote",
            "from_environment": current,
            "to_environment": target,
            "strategy": agent["config"]["deployment"]["promotion_rollback"]["value"],
            "status": "success",
            "reason": reason,
            "actor_persona": actor_persona,
            "created_at": _now_iso(),
        }
    )
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "promote_deployment",
            "entity_type": "agent",
            "entity_id": agent_id,
            "detail": f"Promoted {current} → {target}.",
        }
    )
    return {"record": record, "auditEvent": audit_event}


async def rollback(agent_id: str, actor_persona: str, reason: Optional[str] = None) -> dict[str, Any]:
    agent = await agents_repo.get_by_id(agent_id)
    if agent is None:
        raise ValueError("Agent not found.")
    latest = await deployment_repo.get_latest(agent_id)
    current = _current_environment(agent, latest)
    idx = ENV_LADDER.index(current) if current in ENV_LADDER else 0
    if idx <= 0:
        raise ValueError(f"{current} is already the bottom of the environment ladder — nothing to roll back to.")
    target = ENV_LADDER[idx - 1]

    record = await deployment_repo.insert_record(
        {
            "id": f"dep-{uuid.uuid4()}",
            "agent_id": agent_id,
            "action": "rollback",
            "from_environment": current,
            "to_environment": target,
            "strategy": agent["config"]["deployment"]["promotion_rollback"]["value"],
            "status": "success",
            "reason": reason,
            "actor_persona": actor_persona,
            "created_at": _now_iso(),
        }
    )
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "rollback_deployment",
            "entity_type": "agent",
            "entity_id": agent_id,
            "detail": f"Rolled back {current} → {target}." + (f" Reason: {reason}" if reason else ""),
        }
    )
    return {"record": record, "auditEvent": audit_event}


async def get_grants(agent_id: str) -> list[dict[str, Any]]:
    if await agents_repo.get_by_id(agent_id) is None:
        raise ValueError("Agent not found.")
    return await deployment_repo.get_grants(agent_id)


async def grant_access(input_: dict[str, Any], actor_persona: str) -> dict[str, Any]:
    agent_id = input_.get("agent_id")
    grantee = (input_.get("grantee") or "").strip()
    role_label = (input_.get("role_label") or "").strip()
    scope = input_.get("scope", "viewer")
    if not grantee or not role_label:
        raise ValueError("grantee and role_label are required.")
    if scope not in ("owner", "admin", "viewer"):
        raise ValueError("scope must be one of: owner, admin, viewer.")
    if agent_id and await agents_repo.get_by_id(agent_id) is None:
        raise ValueError("Agent not found.")

    grant_id = f"grant-{uuid.uuid4()}"
    grant = await deployment_repo.insert_grant(
        {
            "id": grant_id,
            "agent_id": agent_id,
            "grantee": grantee,
            "role_label": role_label,
            "scope": scope,
            "granted_by": actor_persona,
            "status": "active",
            "granted_at": _now_iso(),
        }
    )
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "grant_access",
            "entity_type": "agent",
            "entity_id": agent_id or "platform",
            "detail": f"Granted {scope} access to {grantee} ({role_label}).",
        }
    )
    return {"grant": grant, "auditEvent": audit_event}


async def revoke_access(grant_id: str, actor_persona: str) -> Optional[dict[str, Any]]:
    existing = await deployment_repo.get_grant(grant_id)
    if existing is None:
        return None
    updated = await deployment_repo.revoke_grant(grant_id, actor_persona, _now_iso())
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "revoke_access",
            "entity_type": "agent",
            "entity_id": existing["agent_id"] or "platform",
            "detail": f"Revoked access grant for {existing['grantee']}.",
        }
    )
    return {"grant": updated, "auditEvent": audit_event}
