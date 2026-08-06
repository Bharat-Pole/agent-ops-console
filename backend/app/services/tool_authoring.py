import json
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import audit_repo, tools_repo
from app.services.claude_service import MODEL_BY_TIER, _get_client, is_claude_configured
from app.services.tool_approval import request_tool_approval

# Advisory base scope (Section 7.6, LOCKED) — mirrors ToolPermission in
# src/types/agent.ts. `write` is intentionally not a member: write-capable
# tools are represented via the separate `write_capable` flag, never as a
# permission_ceiling value, so this list is the full set of valid ceilings.
ADVISORY_PERMISSIONS = ["read", "summarize", "draft", "recommend", "validate"]

# Phase 3.3 (Blueprint §3.4 `risk_level`). Same four values as the agent
# `RiskTier` on purpose — a platform with two risk vocabularies cannot report
# on risk. Optional: NULL means unclassified, which is a visible gap rather
# than a fabricated "low".
RISK_LEVELS = ["low", "medium", "high", "critical"]

# A write-capable tool cannot be declared below `high`. This is the one place
# risk_level is more than a label: the advisory-only invariant already says such
# a tool never binds, so letting someone file it as `low` would be a governance
# record that contradicts the enforcement.
WRITE_CAPABLE_RISK_FLOOR = "high"
_RISK_ORDER = {level: i for i, level in enumerate(RISK_LEVELS)}


def _validate_policy(risk_level: Any, write_capable: bool) -> Optional[str]:
    """Returns the normalized risk_level, or raises. None means unclassified."""
    if risk_level in (None, ""):
        # An omitted risk level is honest for a read-only tool. For a
        # write-capable one it is not — the floor applies whether or not the
        # author engaged with the field.
        return WRITE_CAPABLE_RISK_FLOOR if write_capable else None
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"risk_level must be one of {RISK_LEVELS}.")
    if write_capable and _RISK_ORDER[risk_level] < _RISK_ORDER[WRITE_CAPABLE_RISK_FLOOR]:
        raise ValueError(
            f"A write-capable tool cannot be classified below '{WRITE_CAPABLE_RISK_FLOOR}'."
        )
    return risk_level


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _slugify(s: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return slug.strip("-")[:40]


async def _unique_tool_id(name: str) -> str:
    base = _slugify(name) or "tool"
    candidate = base
    if await tools_repo.get_by_id(candidate) is None:
        return candidate
    return f"{base}-{secrets.token_hex(2)}"


async def create_tool(body: dict[str, Any]) -> dict[str, Any]:
    name = (body.get("name") or "").strip()
    category = (body.get("category") or "").strip()
    permission_ceiling = body.get("permission_ceiling")
    description = (body.get("description") or "").strip()
    write_capable = bool(body.get("write_capable", False))
    schema = body.get("schema") or {"inputs": {}, "outputs": {}}
    owner = (body.get("owner") or "").strip() or None

    if not name:
        raise ValueError("Tool name is required.")
    if not category:
        raise ValueError("Category is required.")
    if permission_ceiling not in ADVISORY_PERMISSIONS:
        raise ValueError(f"permission_ceiling must be one of {ADVISORY_PERMISSIONS}.")

    risk_level = _validate_policy(body.get("risk_level"), write_capable)

    tool_id = await _unique_tool_id(name)
    tool = {
        "id": tool_id,
        "version": "v1",
        "name": name,
        "description": description,
        "category": category,
        "permission_ceiling": permission_ceiling,
        "write_capable": write_capable,
        "connector_id": None,
        "schema": schema,
        "status": "available",
        # Phase 3.2 — discovery/authoring is not consent. Every tool created
        # through the console queues for approval and is unbindable until a
        # Governance Officer decides; `bind_tool()` re-checks this server-side.
        # A client-supplied approval_state is ignored, not merged.
        "approval_state": "pending",
        "owner": owner,
        "risk_level": risk_level,
        "used_by": [],
        "result_fixtures": [],
    }
    await tools_repo.insert(tool)
    approval = await request_tool_approval(tool)

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": "create_tool",
            "entity_type": "tool",
            "entity_id": tool_id,
            "detail": f"Created tool {tool_id} ({permission_ceiling}"
            + (", write-capable — advisory-block" if write_capable else "")
            + ") — queued for approval, not yet bindable.",
        }
    )

    return {"tool": tool, "approval": approval, "auditEvent": audit_event}


async def update_tool_policy(tool_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Phase 3.3 — set `owner` and `risk_level` on an existing tool.

    These are the only two author-editable fields. `permission_ceiling`,
    `write_capable`, `connector_id`, `status` and `approval_state` are all
    absent on purpose: the first two would silently invalidate an approval
    already given, `connector_id` belongs to discovery (ROADMAP D7), and the
    last two are owned by the health cascade and the approval queue
    respectively. Same shape as `connector_authoring.update_connector()`.
    """
    existing = await tools_repo.get_by_id(tool_id)
    if existing is None:
        raise LookupError("Tool not found.")

    changed: list[str] = []
    owner = existing["owner"]
    risk_level = existing["risk_level"]

    if "owner" in body:
        candidate = (body.get("owner") or "").strip() or None
        if candidate != owner:
            owner = candidate
            changed.append("owner")

    if "risk_level" in body:
        # Validated against the *merged* result, so the write-capable floor
        # cannot be dodged by patching one field at a time.
        candidate = _validate_policy(body.get("risk_level"), existing["write_capable"])
        if candidate != risk_level:
            risk_level = candidate
            changed.append("risk_level")

    if not changed:
        return {"tool": existing, "auditEvent": None, "changed": []}

    tool = await tools_repo.update_policy(tool_id, owner, risk_level)
    if tool is None:
        raise LookupError("Tool not found.")

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Governance Officer",
            "action": "update_tool_policy",
            "entity_type": "tool",
            "entity_id": tool_id,
            "detail": (
                f"Updated tool {tool_id}: {', '.join(changed)} "
                f"(owner={tool['owner'] or 'unassigned'}, risk_level={tool['risk_level'] or 'unclassified'})."
            ),
        }
    )

    return {"tool": tool, "auditEvent": audit_event, "changed": changed}


_SUGGEST_SYSTEM_PROMPT = f"""You draft entries for an AI agent tool catalog. Given a short description of \
what a tool should do, respond with STRICT JSON only — no prose, no markdown fences — matching exactly this shape:

{{"name": "snake_case_tool_name", "category": "short_category_slug", "description": "one sentence", \
"permission_ceiling": one of {ADVISORY_PERMISSIONS}, "write_capable": true or false, \
"risk_level": one of {RISK_LEVELS}, \
"schema": {{"inputs": {{"field_name": "type"}}, "outputs": {{"field_name": "type"}}}}}}

Rules:
- permission_ceiling must be exactly one of {ADVISORY_PERMISSIONS} — never "write".
- risk_level reflects the blast radius of the data or system the tool touches: \
"low" for public/reference data, "medium" for internal operational data, "high" for customer, \
financial or regulated data, "critical" for anything write-capable or safety-relevant. \
A write_capable tool must be at least "high".
- Set write_capable to true only if the description implies an action that changes external state \
(sending, updating, deleting, approving, closing, posting, executing). Such tools are catalogued for \
visibility only and can never be bound to an agent — this is expected and enforced elsewhere, just flag it honestly.
- Keep schema fields minimal and realistic (2-4 inputs, 1-3 outputs)."""


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response.")
    return json.loads(match.group(0))


async def suggest_tool(description: str) -> dict[str, Any]:
    model = MODEL_BY_TIER["standardized"]
    response = await _get_client().messages.create(
        model=model,
        max_tokens=1024,
        thinking={"type": "disabled"},
        system=_SUGGEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": description}],
    )
    text_block = next((b for b in response.content if b.type == "text"), None)
    draft = _extract_json(text_block.text if text_block else "")

    if draft.get("permission_ceiling") not in ADVISORY_PERMISSIONS:
        draft["permission_ceiling"] = "recommend"
    draft["write_capable"] = bool(draft.get("write_capable", False))
    draft.setdefault("schema", {"inputs": {}, "outputs": {}})

    # The model is a drafting aid, not an authority: a suggested risk_level is
    # clamped to the same floor create_tool() enforces, and an unusable value is
    # dropped rather than guessed at (NULL = unclassified is a legitimate state).
    try:
        draft["risk_level"] = _validate_policy(draft.get("risk_level"), draft["write_capable"])
    except ValueError:
        draft["risk_level"] = WRITE_CAPABLE_RISK_FLOOR if draft["write_capable"] else None

    return {"draft": draft, "model": model}
