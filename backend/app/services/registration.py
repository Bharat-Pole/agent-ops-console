import re
import secrets
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.repositories import agents_repo, approvals_repo, audit_repo, eval_packs_repo, scheduled_jobs_repo
from app.seed_data.constants import CONTENT_STEP_NAMES, PATH_DEFS, RUNTIME_STEP_NAMES, governance_path_for
from app.seed_data.eval_gen import generate_eval_pack

# Server port of the client's services.register()/buildAgentFromDraft()
# (src/kernel/services.ts) — same logic, real IDs/dates, DB-persisted.


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _slugify(s: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return slug.strip("-")[:32]


def _new_agent_id(name: str) -> str:
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    hex_ = secrets.token_hex(2)
    return f"agt-{_slugify(name)}-{date}-{hex_}"


def _step(name: str, status: str, at: Optional[str] = None) -> dict[str, Any]:
    return {"name": name, "status": status, "at": at}


def _track(status: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": status, "steps": steps}


async def register_agent(req: dict[str, Any]) -> dict[str, Any]:
    if not req.get("name") or not (req.get("synthesis") or {}).get("config"):
        raise ValueError("Missing name or synthesis payload.")

    synthesis = req["synthesis"]
    tier = req.get("confirmedTier") or synthesis["capability_tier"]
    risk = req.get("confirmedRisk") or synthesis["risk_tier"]
    path = governance_path_for(tier, risk)
    new_id = _new_agent_id(req["name"])
    now = _now_iso()

    config = deepcopy(synthesis["config"])
    config["identity"]["agent_id"] = {
        "value": new_id, "value_source": "system", "verified_flag": True, "confidence": "high", "gap_note": None,
    }
    config["lifecycle"]["lifecycle_status"] = {
        "value": "registered", "value_source": "system", "verified_flag": True, "confidence": "high", "gap_note": None,
    }
    config["lifecycle"]["risk_tier"] = {
        **config["lifecycle"]["risk_tier"], "value": risk, "verified_flag": True, "confidence": "high", "gap_note": None,
    }

    rag = config["data"]["rag_enabled"]["value"]
    fast_path = path == "fast"

    registry_track = _track(
        "in_progress",
        [
            _step("Schema validated", "ready", now),
            _step("Registered", "ready", now),
            _step("Approvals granted", "in_progress", None),
        ],
    )
    runtime_track = _track("not_started", [_step(n, "not_started", None) for n in RUNTIME_STEP_NAMES])
    content_track = (
        _track("not_started", [_step(n, "not_started", None) for n in CONTENT_STEP_NAMES])
        if rag
        else _track("ready", [_step("No knowledge sources", "ready", now)])
    )

    agent = {
        "config": config,
        "capability_tier": tier,
        "governance_path": path,
        "tracks": {"registry": registry_track, "runtime": runtime_track, "content": content_track},
        "signal_breakdown": synthesis["signal_breakdown"],
        "review_card": synthesis.get("review_card"),
        "evaluation_pack_id": f"pack-{new_id}",
        "approval_ids": [],
        "fast_path_expiry_date": None,
        "created_at": req.get("createdAt") or now,
        "updated_at": now,
        "demo_mode": False,
    }

    pack = generate_eval_pack(agent["evaluation_pack_id"], new_id, config, tier)

    approvals: list[dict[str, Any]] = []
    for stp in PATH_DEFS[path]["approvals"]:
        approvals.append(
            {
                "id": f"appr-{uuid.uuid4()}",
                "agent_id": new_id,
                "step": stp,
                "required_by_path": path,
                "status": "pending",
                "actor_persona": None,
                "decided_at": None,
                "note": None,
                "requested_at": now,
            }
        )
    agent["approval_ids"] = [a["id"] for a in approvals]

    await agents_repo.insert(agent)
    await eval_packs_repo.insert(pack)
    for a in approvals:
        await approvals_repo.insert(a)

    actor_persona = req.get("actorPersona") or "Business Owner"
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": actor_persona,
            "action": "register",
            "entity_type": "agent",
            "entity_id": new_id,
            "detail": f"Registered {req['name']} ({tier}, {path} path). {len(approvals)} approval(s) created.",
        }
    )

    if fast_path:
        # Row-backed delayed auto-approval — survives a server restart, unlike
        # a client-side setTimeout.
        run_at = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        await scheduled_jobs_repo.insert(
            {
                "id": f"sched-{uuid.uuid4()}",
                "kind": "finalize_registry",
                "entity_id": new_id,
                "run_at": run_at,
                "status": "pending",
                "created_at": now,
            }
        )

    return {"agent": agent, "pack": pack, "approvals": approvals, "auditEvent": audit_event}


async def finalize_registry(agent_id_str: str) -> Optional[dict[str, Any]]:
    pending = await approvals_repo.count_pending(agent_id_str)
    if pending > 0:
        return None

    now = _now_iso()

    def updater(a: dict[str, Any]) -> dict[str, Any]:
        nxt = deepcopy(a)
        nxt["config"]["lifecycle"]["lifecycle_status"] = {
            **nxt["config"]["lifecycle"]["lifecycle_status"], "value": "approved",
        }
        steps = nxt["tracks"]["registry"]["steps"]
        nxt["tracks"]["registry"] = {
            "status": "ready",
            "steps": [{**s, "status": "ready", "at": s["at"] or now} for s in steps],
        }
        nxt["updated_at"] = now
        return nxt

    agent = await agents_repo.patch(agent_id_str, updater)
    if agent is not None:
        await audit_repo.insert(
            {
                "id": f"aud-{uuid.uuid4()}",
                "at": now,
                "actor_persona": "Governance Officer",
                "action": "approve",
                "entity_type": "agent",
                "entity_id": agent_id_str,
                "detail": "All approvals satisfied → agent approved; Registry track ready.",
            }
        )
    return agent
