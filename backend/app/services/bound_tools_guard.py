"""Server-side guard on `config.tooling.bound_tools` — closes R8.

`bind_tool()` was the *governed* way a tool becomes bound to an agent. It was
never the *only* way. Three routes write `bound_tools` straight out of a
client-supplied config with no validation at all:

    POST  /v1/agents/register            services/registration.py
    PATCH /v1/agents/:id                 routes/agents.py (the config sync)
    POST  /v1/agents/:id/config-change   services/lifecycle.py

Verified by experiment (2026-08-05), not inferred: registering with
`bound_tools: ["tools://ticket_updater@v1", "tools://<pending>@v1"]` returned
**201** with both refs persisted — bypassing the locked write-capable invariant
*and* Phase 3's approval gate. It compounds the tool-call trail, because
`tool_call_log._binding_violation()` authorizes calls **against** `bound_tools`:
a laundered bind makes a write-capable call record `ok`.

This is not a theoretical hole. The only thing filtering write tools before
registration today is `kernel/engine/writeDetect.ts`, a **client-side name
heuristic** (`notifier`, `sender`, `updater`, …). The three seeded write tools
are caught by luck of naming; a tool called `payment_authorizer` is not. And
nothing at all filters *unapproved* tools, so a tool catalogued a minute ago
walks straight past the Phase 3 gate.

**Strip, don't reject.** A registration is not failed over a bad ref: the
synthesis engine proposes tools heuristically, so rejecting would dead-end an
onboarding run over a tool the user never hand-picked, and would leave no agent
for the audit trail to hang off. This mirrors the catalogue-but-never-bind
treatment write tools already get. The cost of stripping is that it rewrites the
caller's config, which is what the audit event and the `blocked` tool-call row
are here to pay for.

There is exactly ONE place that decides what may be bound. If a fourth write
path appears, it calls this — it does not re-derive the rules.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import audit_repo, tools_repo
from app.services.connector_resolution import parse_tool_ref
from app.services.tool_call_log import record_blocked_bind


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

# Why a ref was dropped. Kept machine-readable so the client can group them;
# the human sentence is built alongside it.
REASON_NOT_IN_CATALOG = "not_in_catalog"
REASON_WRITE_CAPABLE = "write_capable"
REASON_NOT_APPROVED = "not_approved"


def _reason_message(tool_id: str, reason: str, state: Optional[str] = None) -> str:
    if reason == REASON_NOT_IN_CATALOG:
        return f"{tool_id} is not in the tool catalog — not bound."
    if reason == REASON_WRITE_CAPABLE:
        return f"{tool_id} is write-capable — advisory-block. Not bound."
    return f"{tool_id} is {state or 'not approved'} approval — not bound until it is approved."


async def sanitize_bound_tools(refs: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Split a `bound_tools` list into (kept, removed).

    Applies the *same* rules as `tool_binding.bind_tool()`, re-read from the
    server's own `tools` table, and in the same order — write-capability first,
    so approval can never become a laundering path for it (ROADMAP Q6).

    Order and duplicates: kept refs preserve the caller's order, with duplicates
    collapsed. A non-list input yields ([], []) — malformed config is the
    caller's problem to reject, not this function's to guess at.
    """
    if not isinstance(refs, list):
        return [], []

    kept: list[str] = []
    removed: list[dict[str, Any]] = []
    seen: set[str] = set()

    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            continue
        tool_id = parse_tool_ref(ref.strip())
        if tool_id in seen:
            continue
        seen.add(tool_id)

        tool = await tools_repo.get_by_id(tool_id)
        if tool is None:
            reason, state = REASON_NOT_IN_CATALOG, None
        elif tool["write_capable"]:
            reason, state = REASON_WRITE_CAPABLE, None
        elif tool["approval_state"] != "approved":
            reason, state = REASON_NOT_APPROVED, tool["approval_state"]
        else:
            kept.append(ref)
            continue

        removed.append(
            {"tool_id": tool_id, "ref": ref, "reason": reason, "message": _reason_message(tool_id, reason, state)}
        )

    return kept, removed


async def record_stripped(
    agent_id: str, removed: list[dict[str, Any]], actor_persona: str = "Platform Engineer"
) -> Optional[dict[str, Any]]:
    """Audit + evidence for refs this guard dropped.

    Writes one audit event summarising the strip, and one `blocked` tool-call
    row per dropped ref — the same evidence a rejected `bind_tool()` produces,
    so `/tools` → Tool Calls shows every refused bind regardless of which door
    it came through. Silent when nothing was dropped.
    """
    if not removed:
        return None

    for item in removed:
        # Best-effort, exactly as in tool_binding: the strip is the contract and
        # must not fail because the evidence trail did.
        await record_blocked_bind(agent_id, item["tool_id"], item["message"])

    return await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "bind_stripped",
            "entity_type": "agent",
            "entity_id": agent_id,
            "detail": (
                f"{len(removed)} tool ref(s) removed from bound_tools before persisting: "
                + " ".join(item["message"] for item in removed)
            ),
        }
    )


async def guard_config(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Sanitize `config.tooling.bound_tools` in a config dict, in place.

    Returns the same dict plus what was removed. Tolerates a config with no
    tooling group rather than raising — an incomplete config is a validation
    concern for the caller, and this guard must never be the thing that breaks
    an otherwise valid registration.
    """
    tooling = config.get("tooling") or {}
    slot = tooling.get("bound_tools")
    if not isinstance(slot, dict) or "value" not in slot:
        return config, []

    # Assign unconditionally: `kept` also collapses duplicate refs, which
    # `bind_tool()` has always done, and an "only write when something was
    # removed" shortcut would silently skip that.
    kept, removed = await sanitize_bound_tools(slot["value"])
    slot["value"] = kept
    return config, removed
