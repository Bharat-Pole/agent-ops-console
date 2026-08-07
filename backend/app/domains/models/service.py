import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.domains.audit import audit_repo
from app.domains.models import models_repo

VALID_ROLES = {"llm", "embedding", "eval"}
VALID_DEPLOY_STATUS = {"approved", "candidate", "deprecated"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# Unlike Tool Registry registration, a model's `id` is meaningful (a real
# provider model identifier, e.g. "claude-opus-6" or "vertex://gemini-2.0") —
# so the caller supplies it directly rather than deriving one from the name.
async def register_model(input_: dict[str, Any], actor_persona: str = "Platform Admin") -> dict[str, Any]:
    model_id = (input_.get("id") or "").strip()
    name = (input_.get("name") or "").strip()
    provider = (input_.get("provider") or "").strip()
    if not model_id or not name or not provider:
        raise ValueError("id, name, and provider are required.")
    if await models_repo.get_by_id(model_id) is not None:
        raise ValueError(f"Model '{model_id}' is already catalogued.")

    roles = input_.get("roles") or ["llm"]
    if not set(roles).issubset(VALID_ROLES):
        raise ValueError(f"roles must be a subset of {sorted(VALID_ROLES)}.")
    deployment_status = input_.get("deployment_status", "candidate")
    if deployment_status not in VALID_DEPLOY_STATUS:
        raise ValueError(f"deployment_status must be one of {sorted(VALID_DEPLOY_STATUS)}.")

    model = {
        "id": model_id,
        "name": name,
        "provider": provider,
        "roles": roles,
        "context_window": input_.get("context_window", 0),
        "cost_input_per_mtok": input_.get("cost_input_per_mtok", 0),
        "cost_output_per_mtok": input_.get("cost_output_per_mtok", 0),
        "latency_p50_ms": input_.get("latency_p50_ms", 0),
        "approved_use_case": input_.get("approved_use_case", ""),
        "risk_tier_mapping": input_.get("risk_tier_mapping", []),
        "owner": input_.get("owner"),
        "deployment_status": deployment_status,
        "access_policy": input_.get("access_policy", ""),
        "fallback_of": input_.get("fallback_of"),
        "routing_note": input_.get("routing_note", ""),
    }
    await models_repo.insert(model)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "register_model",
            "entity_type": "model",
            "entity_id": model_id,
            "detail": f"Catalogued model \"{name}\" ({provider}, {deployment_status}).",
        }
    )
    return {"model": await models_repo.get_by_id(model_id), "auditEvent": audit_event}


async def update_model(model_id: str, patch: dict[str, Any], actor_persona: str = "Platform Admin") -> Optional[dict[str, Any]]:
    existing = await models_repo.get_by_id(model_id)
    if existing is None:
        return None
    if "deployment_status" in patch and patch["deployment_status"] not in VALID_DEPLOY_STATUS:
        raise ValueError(f"deployment_status must be one of {sorted(VALID_DEPLOY_STATUS)}.")
    updated = await models_repo.update_fields(model_id, patch)
    await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "update_model",
            "entity_type": "model",
            "entity_id": model_id,
            "detail": f"Updated fields: {', '.join(sorted(patch.keys()))}.",
        }
    )
    return updated


async def delete_model(model_id: str, actor_persona: str = "Platform Admin") -> Optional[dict[str, Any]]:
    existing = await models_repo.get_by_id(model_id)
    if existing is None:
        return None
    await models_repo.delete_by_id(model_id)
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "delete_model",
            "entity_type": "model",
            "entity_id": model_id,
            "detail": f"Removed model \"{existing['name']}\" ({model_id}) from the catalog.",
        }
    )
    return {"auditEvent": audit_event}
