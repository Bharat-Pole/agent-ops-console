import uuid
from datetime import datetime, timezone
from typing import Any

from app.domains.admin import feature_flags_repo
from app.domains.audit import audit_repo

KNOWN_FLAGS = {"model_repository", "workflow_builder"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def update_feature_flag(key: str, enabled: bool, actor_persona: str = "Platform Admin") -> dict[str, Any]:
    if key not in KNOWN_FLAGS:
        raise ValueError(f"Unknown feature flag '{key}'.")
    flag = await feature_flags_repo.set_flag(key, enabled, _now_iso(), actor_persona)
    if flag is None:
        raise ValueError(f"Unknown feature flag '{key}'.")
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "update_feature_flag",
            "entity_type": "workspace",
            "entity_id": key,
            "detail": f"{key} → {'enabled' if enabled else 'disabled'}.",
        }
    )
    return {"flag": flag, "auditEvent": audit_event}
