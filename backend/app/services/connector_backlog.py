"""Connector prioritization backlog — deck slide 21 element 7, SOW deliverable 3.3.

The last unbuilt element of the deck's seven-element MCP Connectivity Pattern:
*"Identify which systems should be connected in the first 90 days versus future
phases."* Slide 18 names this workstream's Day-90 evidence as an *"MCP and tool
registry strategy package"*, and the SOW's acceptance criterion is *"Internal
connectivity strategy and priority connector model **defined**"* — so this is
the contracted artifact, and it is **defined**, not **working**, that is being
asked for.

It is also the thing that answers the question we spent a day treating as a
blocker (`CONCERNS.md` Q5): nobody ever named the "priority reference
connector", because naming it is *our* deliverable.

**The invariant this module exists to enforce.** The SOW's boundaries table
says:

    "Will install and configure MCP servers only; building new MCP servers is
     out of scope."  ->  "Install/configure approved/existing MCP servers and
     connectors; backlog custom MCP server creation."

So a system with **no existing MCP server cannot be scheduled into the 90
days**. That is a contract term, not a preference, and it is checked
server-side on every write — the same treatment `write_capable` gets in
`tool_binding.py`. Without it, "day 90" becomes a wish rather than a plan, and
the one boundary the SOW is most explicit about would live only in a comment.

**What this is not.** A row here is a *candidate system under assessment*. A row
in `connectors` is *a server we actually talk to*. They are different tables on
purpose: assessing ServiceNow must not create a connector for it, and deleting a
connector must not erase the assessment that chose it. `existing_connector_id`
links them where both exist.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import audit_repo, connector_backlog_repo

# Which delivery window a system is assigned to.
PHASES = ("day_90", "later")

# Whether an MCP server already exists for this system. `official` = first-party
# from the vendor; `community` = third-party, which is a security review of its
# own; `none` = confirmed absent; `unknown` = nobody has checked.
MCP_SERVER_STATES = ("official", "community", "none", "unknown")

# Only the two bindings MCP spec revision 2026-07-28 defines as standard. The
# legacy HTTP+SSE transport is deliberately absent — see CONCERNS.md D8.
TRANSPORTS = ("streamable_http", "stdio")

AUTH_MODELS = ("oauth2", "api_token", "iam", "unknown")

# Mirrors Sensitivity in src/types/agent.ts — one vocabulary per platform.
SENSITIVITIES = ("public", "internal", "confidential", "restricted")

STATUSES = ("proposed", "access_requested", "approved", "connected", "deferred", "blocked")

# The SOW boundary, as data: only these count as "a server exists".
_SERVER_EXISTS = ("official", "community")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate(item: dict[str, Any]) -> None:
    """Validate a *merged* item, so a partial patch cannot slip an invalid
    combination past a per-field check — the same rule connector_authoring uses.
    """
    if item["phase"] not in PHASES:
        raise ValueError(f"phase must be one of {', '.join(PHASES)}.")
    if item["mcp_server"] not in MCP_SERVER_STATES:
        raise ValueError(f"mcp_server must be one of {', '.join(MCP_SERVER_STATES)}.")
    if item["status"] not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}.")
    if item["data_sensitivity"] not in SENSITIVITIES:
        raise ValueError(f"data_sensitivity must be one of {', '.join(SENSITIVITIES)}.")
    if item.get("transport") is not None and item["transport"] not in TRANSPORTS:
        raise ValueError(f"transport must be one of {', '.join(TRANSPORTS)}, or null.")
    if item.get("auth_model") is not None and item["auth_model"] not in AUTH_MODELS:
        raise ValueError(f"auth_model must be one of {', '.join(AUTH_MODELS)}, or null.")
    if not str(item.get("rationale") or "").strip():
        raise ValueError("rationale is required — a ranking without a reason is not an assessment.")
    try:
        rank = int(item["rank"])
    except (TypeError, ValueError):
        raise ValueError("rank must be a number.")
    if rank < 1:
        raise ValueError("rank starts at 1.")

    # THE invariant. See the module docstring: this is a contract term.
    if item["phase"] == "day_90" and item["mcp_server"] not in _SERVER_EXISTS:
        raise ValueError(
            f"{item.get('system_name') or item.get('id')} has no existing MCP server "
            f"(mcp_server={item['mcp_server']}), so it cannot be scheduled into the 90-day "
            "phase — the SOW puts building new MCP servers out of scope. Move it to 'later', "
            "or change mcp_server once a server is confirmed."
        )


async def list_backlog() -> dict[str, Any]:
    """The backlog plus the summary a reader actually wants off slide 21."""
    items = await connector_backlog_repo.get_all()
    day_90 = [i for i in items if i["phase"] == "day_90"]
    return {
        "backlog": items,
        "summary": {
            "total": len(items),
            "day_90": len(day_90),
            "later": len(items) - len(day_90),
            # The recommendation the deliverable exists to make: rank 1 of the
            # 90-day set. Derived, never stored — so it cannot drift from the
            # ranking it claims to summarise.
            "recommended": day_90[0]["id"] if day_90 else None,
            "blocked_on_no_server": [
                i["id"] for i in items if i["mcp_server"] not in _SERVER_EXISTS
            ],
            "unassessed": [i["id"] for i in items if i["mcp_server"] == "unknown"],
        },
    }


async def update_backlog_item(item_id: str, body: dict[str, Any]) -> dict[str, Any]:
    existing = await connector_backlog_repo.get_by_id(item_id)
    if existing is None:
        raise LookupError("Backlog item not found.")

    merged = {**existing}
    changed: list[str] = []
    for field in connector_backlog_repo.EDITABLE:
        if field in body and body[field] != merged.get(field):
            merged[field] = body[field]
            changed.append(field)

    _validate(merged)

    if not changed:
        return {"item": existing, "auditEvent": None, "changed": []}

    now = _now_iso()
    item = await connector_backlog_repo.update(item_id, merged, now)
    if item is None:
        raise LookupError("Backlog item not found.")

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": now,
            "actor_persona": "Platform Engineer",
            "action": "update_connector_backlog",
            "entity_type": "connector",
            "entity_id": item_id,
            "detail": (
                f"Connector backlog updated for {item['system_name']}: {', '.join(changed)} "
                f"(rank {item['rank']}, {item['phase']}, {item['status']})."
            ),
        }
    )

    return {"item": item, "auditEvent": audit_event, "changed": changed}
