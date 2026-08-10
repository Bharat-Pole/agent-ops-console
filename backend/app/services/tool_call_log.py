"""Tool-call audit trail — deck slide 21, element 6.

The console could already show *what an agent is allowed to do* (Tool Catalog)
and *how we reach the systems* (MCP Connectors). It could not show **what an
agent actually did**: every tool call the Playground simulated was discarded.

This module is the write side. Slide 21 names eight fields and the table
carries them verbatim; the two that matter for trust are resolved **server-side
and never taken from the client**:

  system_accessed  the connector the tool resolves to, via Phase 0's
                   `connector_resolution.resolve_tool_connector()` -- the one
                   place that walks the tool -> connector edge. NULL for local
                   tools; never a placeholder.
  permission       the ceiling actually exercised, read from the server's own
                   `tools` table, the same trust boundary `tool_binding.py`
                   uses. A client claiming `read` for a write-capable tool
                   cannot launder it through this log.

  authority        whether the agent was *allowed* to call this tool, re-derived
                   from the agent's own `bound_tools`. A caller claiming
                   `resultStatus: ok` for a tool it was never bound to has its
                   status **overridden to `blocked`** with the reason recorded.

`result_status` and `latency_ms` remain client-supplied **on this path**, and
that is an honest limit rather than an oversight: a client-simulated tool call
has no server-side invocation to time or to observe failing. The authority check
above is what stops that being a hole worth exploiting.

**Phase 6 added a second write path — `record_gateway_call()` — where that limit
does not apply.** There, the server ran the checkpoints, started the clock and
read the response, so every field is its own. The two paths are distinguishable
in the data by `tool_calls.gateway`, and they must stay that way: describing a
reported row as observed evidence is the single easiest way to overclaim this
workstream. `CONCERNS.md` R7.

`blocked` results additionally write an audit event. That is the point of
logging them: the advisory-only invariant stops being a silent rejection and
becomes a row someone can point at.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories import agents_repo, audit_repo, tool_calls_repo, tools_repo
from app.services.connector_resolution import parse_tool_ref, resolve_tool_connector

# Slide 21's "consumer" — which surface issued the call. `console` covers
# operator actions (a blocked bind attempt is not a Playground turn).
CONSUMERS = ("playground", "api", "workflow", "console")

# Slide 21's "result status".
RESULT_STATUSES = ("ok", "error", "blocked")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def record_tool_call(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one tool call. Raises ValueError on invalid input."""
    agent_id = payload.get("agentId") or payload.get("agent_id")
    tool_raw = payload.get("toolInvoked") or payload.get("tool_invoked")

    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agentId is required.")
    if not isinstance(tool_raw, str) or not tool_raw.strip():
        raise ValueError("toolInvoked is required.")

    consumer = payload.get("consumer") or "playground"
    if consumer not in CONSUMERS:
        raise ValueError(f"consumer must be one of {', '.join(CONSUMERS)}.")

    result_status = payload.get("resultStatus") or payload.get("result_status") or "ok"
    if result_status not in RESULT_STATUSES:
        raise ValueError(f"resultStatus must be one of {', '.join(RESULT_STATUSES)}.")

    try:
        latency_ms = int(payload.get("latencyMs") or payload.get("latency_ms") or 0)
    except (TypeError, ValueError):
        raise ValueError("latencyMs must be a number.")
    if latency_ms < 0:
        raise ValueError("latencyMs must not be negative.")

    # Accept a versioned ref or a bare id — the Playground holds refs.
    tool_id = parse_tool_ref(tool_raw.strip())

    # Server-side resolution. The client's opinion about which system was
    # touched, or under what permission, is never used.
    tool = await tools_repo.get_by_id(tool_id)
    system_accessed = await resolve_tool_connector(tool_id)
    permission = tool["permission_ceiling"] if tool else "unknown"

    notes: list[str] = []
    client_detail = payload.get("exceptionDetail") or payload.get("exception_detail")
    if client_detail:
        notes.append(str(client_detail))

    if tool is None:
        # Don't silently log a call against a tool the catalog has never heard
        # of — that mismatch is itself the finding.
        notes.append(f"{tool_id} is not in the tool catalog.")

    # Authorization. `result_status` and `latency_ms` are the two fields the
    # client still supplies, so a caller could claim `ok` for a tool the agent
    # was never allowed to touch. The server therefore re-derives *authority*
    # from the agent's own bound_tools and **overrides** a claimed status when
    # it fails -- the same "ignored, not merged" rule that governs
    # system_accessed, permission and at.
    #
    # It records rather than rejects: refusing to write the row would destroy
    # the evidence of the very thing worth catching.
    violation = await _binding_violation(agent_id, tool_id)
    if violation:
        notes.append(violation)
        result_status = "blocked"

    exception_detail = " ".join(notes) if notes else None

    call = {
        "id": f"tc-{uuid.uuid4()}",
        "agent_id": agent_id,
        "request_id": payload.get("requestId") or payload.get("request_id") or f"req-{uuid.uuid4()}",
        "consumer": consumer,
        "tool_invoked": tool_id,
        "system_accessed": system_accessed,
        "result_status": result_status,
        "latency_ms": latency_ms,
        "exception_detail": exception_detail,
        "permission": permission,
        # Server-authoritative. A client-supplied timestamp has no place in an
        # audit trail — it is the one field a caller would most want to bend.
        "at": _now_iso(),
    }

    await tool_calls_repo.insert(call)

    audit_event = None
    if result_status == "blocked":
        audit_event = await _audit_blocked(call)

    return {"toolCall": call, "auditEvent": audit_event}


async def _binding_violation(agent_id: str, tool_id: str) -> Optional[str]:
    """Return a reason string if this agent may not call this tool, else None.

    Read from the agent's own `bound_tools` — the server's copy, never the
    client's claim. `record_blocked_bind()` deliberately does not go through
    here: a *bind attempt* is by definition for a tool that is not yet bound,
    and it already carries its own advisory-block reason.
    """
    agent = await agents_repo.get_by_id(agent_id)
    if agent is None:
        return f"Agent {agent_id} is not registered — call could not be authorized."

    bound = {
        parse_tool_ref(ref)
        for ref in (agent["config"]["tooling"]["bound_tools"]["value"] or [])
    }
    if tool_id not in bound:
        return f"{tool_id} is not bound to this agent — unauthorized tool call."
    return None


async def _audit_blocked(call: dict[str, Any]) -> dict[str, Any]:
    return await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": "tool_call_blocked",
            "entity_type": "agent",
            "entity_id": call["agent_id"],
            "detail": (
                f"Tool call to {call['tool_invoked']} BLOCKED. "
                f"{call['exception_detail'] or 'No reason recorded.'}"
            ),
        }
    )


async def record_blocked_bind(agent_id: str, tool_id: str, reason: str) -> None:
    """A rejected bind attempt, logged as a `blocked` call.

    Called from `tool_binding.py`. Best-effort: the advisory-only rejection is
    the contract and must not fail because the audit trail did. The rejection
    already writes its own `bind_rejected` audit event, so this deliberately
    does not write a second one.
    """
    tool = await tools_repo.get_by_id(tool_id)
    try:
        await tool_calls_repo.insert(
            {
                "id": f"tc-{uuid.uuid4()}",
                "agent_id": agent_id,
                "request_id": f"req-{uuid.uuid4()}",
                "consumer": "console",
                "tool_invoked": tool_id,
                "system_accessed": await resolve_tool_connector(tool_id),
                "result_status": "blocked",
                "latency_ms": 0,
                "exception_detail": reason,
                "permission": tool["permission_ceiling"] if tool else "unknown",
                "at": _now_iso(),
            }
        )
    except Exception as err:  # pragma: no cover - logging must never break the bind path
        print("[tool_call_log:record_blocked_bind]", err)


async def record_gateway_call(record: dict[str, Any]) -> dict[str, Any]:
    """Persist one call that went through the Phase 6 gateway.

    Deliberately *not* an extension of `record_tool_call()`. That function's job
    is to take a client's account of something and make it as trustworthy as it
    can — resolving four fields server-side and overriding a claimed status when
    authority fails. This function has no client account to sanitise: the
    gateway is the caller, it ran every checkpoint itself, and it timed its own
    invocation. Merging the two would mean the sanitising path could be reached
    with `gateway = True` in the payload, which is the one thing that must never
    be possible.

    So the only validation here is on our own caller, and the audit event is
    written for a *denial* — a successful call is already a row, and an audit
    entry per successful tool call would bury the governance events the log
    exists for.
    """
    call = {
        "id": f"tc-{uuid.uuid4()}",
        "agent_id": record["agent_id"],
        "request_id": record.get("request_id") or f"req-{uuid.uuid4()}",
        "consumer": record.get("consumer") or "playground",
        "tool_invoked": record["tool_id"],
        "system_accessed": record.get("system_accessed"),
        "result_status": record["result_status"],
        "latency_ms": max(0, int(record.get("latency_ms") or 0)),
        "exception_detail": record.get("reason"),
        "permission": record.get("permission") or "unknown",
        "at": _now_iso(),
        # The four Phase 6 columns that make this row *observed* rather than
        # reported. `gateway` is hardcoded True here and settable nowhere else.
        "gateway": True,
        "decision": record["decision"],
        "denied_by": record.get("denied_by"),
        "invocation": record.get("invocation") or "none",
        "principal": record.get("principal"),
        "team": record.get("team"),
        "redacted_fields": record.get("redacted_fields") or [],
    }

    await tool_calls_repo.insert(call)

    audit_event = None
    if call["decision"] == "deny":
        audit_event = await audit_repo.insert(
            {
                "id": f"aud-{uuid.uuid4()}",
                "at": _now_iso(),
                "actor_persona": "Platform Engineer",
                "action": "gateway_denied",
                "entity_type": "agent",
                "entity_id": call["agent_id"],
                "detail": (
                    f"Gateway DENIED {call['tool_invoked']} at checkpoint "
                    f"'{call['denied_by']}'. {call['exception_detail'] or 'No reason recorded.'}"
                ),
            }
        )

    return {"toolCall": call, "auditEvent": audit_event}


async def list_tool_calls(
    agent_id: Optional[str] = None,
    tool_id: Optional[str] = None,
    result_status: Optional[str] = None,
    limit: int = 200,
    gateway: Optional[bool] = None,
) -> dict[str, Any]:
    calls = await tool_calls_repo.get_filtered(agent_id, tool_id, result_status, limit, gateway)
    return {"toolCalls": calls}
