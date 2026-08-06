"""Tool approval — Phase 3.2 (Blueprint §11, deck slide 21's approval narrative).

Until now a tool created through the console was bindable the instant it was
saved. Blueprint §11 names an **Approval Queue** covering *"prompt, tool, data,
model, deployment and exception approvals"*, which settled the open question
(ROADMAP Q1/D3): tool approval is real, **and it is a shared platform object**.

So this module deliberately owns almost nothing. It does not define a queue, a
status vocabulary, a decision endpoint or a UI: it writes a row into the same
`approvals` table agent registration uses, and `services/approvals.py` routes
the decision back here. A tool-local approval state would have been less code
today and a second ungoverned queue forever.

Three decisions worth keeping:

  1. **`approval_state` is not a `status` value.** `status` is owned end-to-end
     by the connector health cascade and would overwrite a pending state the
     moment a connector flapped. Health and consent are different questions.
  2. **The seeded catalog is grandfathered approved** (the column default), not
     retro-queued. Twelve items a Governance Officer never asked for would be
     noise, and the seed *is* the pre-vetted set.
  3. **A rejected tool stays in the catalog.** It is visible, unbindable, and
     carries the reason — the same principle as write-capable tools being
     catalogued rather than hidden. Deleting it would erase the decision.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import approvals_repo, audit_repo, tools_repo

# Mirrors ToolApprovalState in src/types/assets.ts.
APPROVAL_STATES = ("pending", "approved", "rejected")

# The queue's `step` for a tool item. `step` is a free-text column; the four
# agent steps (business_owner / risk_officer / security_committee / data_source)
# are governance-path roles and none of them describes cataloguing a tool.
TOOL_APPROVAL_STEP = "tool_registration"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def request_tool_approval(tool: dict[str, Any]) -> dict[str, Any]:
    """Queue a newly catalogued tool for approval. Returns the approval row.

    `agent_id` and `required_by_path` are NULL: a tool belongs to no agent, and
    a governance path is an agent concept. Writing 'standard' there to satisfy
    the old NOT NULL would have been inventing a fact — hence the migration.
    """
    approval = {
        "id": f"apr-{uuid.uuid4()}",
        "agent_id": None,
        "step": TOOL_APPROVAL_STEP,
        "required_by_path": None,
        "status": "pending",
        "actor_persona": None,
        "decided_at": None,
        "note": None,
        "requested_at": _now_iso(),
        "entity_type": "tool",
        "entity_id": tool["id"],
    }
    await approvals_repo.insert(approval)
    return approval


async def decide_tool_approval(
    item: dict[str, Any], decision: str, note: str, actor_persona: str, at: str
) -> Optional[dict[str, Any]]:
    """Apply a queue decision to the tool it refers to. Returns the fresh tool.

    Called only by `services/approvals.py`, which owns the queue. The state
    written here is the *only* thing that unblocks `bind_tool()` — the guard
    there re-reads the server's own `tools` row, never a client claim.
    """
    tool_id = item.get("entity_id")
    if not tool_id:
        return None

    state = "approved" if decision == "approved" else "rejected"
    await tools_repo.set_approval_state(tool_id, state)
    tool = await tools_repo.get_by_id(tool_id)
    if tool is None:
        return None

    await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": at,
            "actor_persona": actor_persona,
            "action": "approve_tool" if state == "approved" else "reject_tool",
            "entity_type": "tool",
            "entity_id": tool_id,
            "detail": (
                f"Tool {tool_id} {state}"
                + (" — now bindable." if state == "approved" else " — catalogued but not bindable.")
                + (f" {note}" if note else "")
            ),
        }
    )
    return tool
