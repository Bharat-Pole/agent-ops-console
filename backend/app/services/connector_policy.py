"""Declare a connector's gateway policy — Phase 6.

Deck slide 21 element 4 (*"Define which datasets, systems, and fields each agent
is allowed to access"*) and element 5 (*"Align MCP/tool access with IAM, service
accounts, approved identities, and system-level permissions"*). This module is
the write side of both; `services/tool_gateway.py` is the only reader.

**Why this is not part of `connector_authoring.py`.** Registering a server
answers *how do we reach it*. Declaring a boundary answers *what may it expose,
and to whom*. Those are different jobs held by different people — a Platform
Engineer registers, a Governance Officer bounds — and merging them would mean
whoever can edit an endpoint can also widen their own data boundary. The two
field sets are therefore disjoint, enforced by two repository functions that
physically cannot write each other's columns (`connectors_repo.update()` vs.
`connectors_repo.set_policy()`), which is the same shape as the rule that keeps
`status` out of an author's hands.

**Empty means undeclared, not deny-all.** Stated once here and once in
`db/migrate.py` because it is the one thing about this module that is easy to
get backwards. A deny-all default would have been the stricter-looking choice
and the dishonest one: nobody has written a dataset inventory for the seeded
connectors, so enforcing an empty allowlist would be enforcing a policy that
does not exist. The gateway records every undeclared boundary on every call
instead, which makes the gap visible rather than either silent or fictional.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import audit_repo, connectors_repo

# The list-valued fields, and the scalar ones. Anything not named here is
# unreachable through this route — including every field `connector_authoring`
# owns, plus `status` and `tools_provided`, which belong to the health cascade
# and to discovery respectively.
LIST_FIELDS = ("allowed_datasets", "allowed_fields", "approved_identities")
TEXT_FIELDS = ("service_account", "iam_principal")
INT_FIELDS = ("rate_limit_per_min", "timeout_ms")

# Bounds chosen to be permissive but not absurd: a limit of 0 would be a silent
# deny-all wearing a rate limit's clothing, and an unbounded timeout would let
# one hung connector hold a request open indefinitely.
_INT_BOUNDS = {"rate_limit_per_min": (1, 10_000), "timeout_ms": (100, 120_000)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _clean_list(field: str, raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be an array of strings.")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain non-empty strings.")
        value = item.strip()
        if value not in out:  # de-duplicated, order preserved
            out.append(value)
    return out


def _clean_text(field: str, raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be a string or null.")
    return raw.strip() or None


def _clean_int(field: str, raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number.")
    lo, hi = _INT_BOUNDS[field]
    if not lo <= value <= hi:
        raise ValueError(f"{field} must be between {lo} and {hi}.")
    return value


async def update_connector_policy(connector_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Patch the policy fields. Absent keys are left alone.

    Merge-then-write rather than replace: a console that only edits identities
    must not silently clear a dataset boundary somebody else declared.
    """
    existing = await connectors_repo.get_by_id(connector_id)
    if existing is None:
        raise LookupError("Connector not found.")

    merged = {
        **{f: existing[f] or [] for f in LIST_FIELDS},
        **{f: existing[f] for f in TEXT_FIELDS},
        **{f: existing[f] for f in INT_FIELDS},
    }
    changed: list[str] = []

    for field in LIST_FIELDS:
        if field in body:
            value = _clean_list(field, body[field])
            if value != (merged[field] or []):
                merged[field] = value
                changed.append(field)

    for field in TEXT_FIELDS:
        if field in body:
            value = _clean_text(field, body[field])
            if value != merged[field]:
                merged[field] = value
                changed.append(field)

    for field in INT_FIELDS:
        if field in body:
            value = _clean_int(field, body[field])
            if value != merged[field]:
                merged[field] = value
                changed.append(field)

    if not changed:
        return {"connector": existing, "auditEvent": None, "changed": []}

    connector = await connectors_repo.set_policy(connector_id, merged)
    if connector is None:
        raise LookupError("Connector not found.")

    # Changing a boundary is a governance act, so it is audited by a Governance
    # Officer rather than the Platform Engineer who audits connector edits. The
    # persona is what tells the two apart in the log.
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Governance Officer",
            "action": "update_connector_policy",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": (
                f"Gateway policy for {connector_id} updated: {', '.join(changed)}. "
                f"Datasets: {len(merged['allowed_datasets'])}, "
                f"fields: {len(merged['allowed_fields'])}, "
                f"identities: {len(merged['approved_identities'])}."
            ),
        }
    )

    return {"connector": connector, "auditEvent": audit_event, "changed": changed}
