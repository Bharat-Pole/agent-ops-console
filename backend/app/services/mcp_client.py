"""The real MCP client — Phase 5A.

Everything before this file simulated MCP. This is the first code that speaks
the protocol, against **spec revision 2026-07-28** via the official SDK
(`CONCERNS.md` Q9 closed 2026-08-10).

Three things this module is responsible for, in order of importance:

1. **Talking MCP.** `list_remote_tools()` performs a genuine `tools/list`. The
   revision is stateless — there is no `initialize` handshake any more — so a
   listing is one exchange with no session to manage.

2. **Refusing malformed definitions.** The spec says a client MUST reject tool
   definitions carrying invalid ``x-mcp-header`` annotations and exclude them
   from the result while logging a warning. One bad definition must not poison a
   whole discovery. We do this *before* anything downstream sees the tool, and
   we report what was dropped rather than dropping it silently — a connector
   serving junk is a fact an operator needs.

3. **Holding the governance line at the boundary.** A remote server is an
   untrusted counterparty. Nothing it says may widen our permission model:
   `write_capable` is deny-by-default, `approval_state` is never taken from the
   wire, and a discovered tool arrives `pending`. **Discovery is not consent.**

What this module deliberately does NOT do: write to the database. Persistence
lives in `connector_health.list_connector_tools()`, so this stays a pure
protocol adapter that can be tested against an in-memory server.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Optional

from mcp import Client

log = logging.getLogger(__name__)

# The revision this client is written against. Asserted rather than assumed —
# if the SDK negotiates something else, we want a loud, early signal.
TARGET_PROTOCOL_VERSION = "2026-07-28"

# Reasons a definition can be rejected. Stable strings — surfaced in the API
# response and asserted by the suite.
REJECT_INVALID_HEADER = "invalid_x_mcp_header"
REJECT_NO_NAME = "missing_name"


class McpProtocolError(RuntimeError):
    """Raised when a connector cannot be reached or does not speak MCP."""


# ---------------------------------------------------------------------------
# Conformance: x-mcp-header validation
# ---------------------------------------------------------------------------


def validate_header_annotation(meta: Optional[dict[str, Any]]) -> Optional[str]:
    """Return a human-readable reason if the annotation is invalid, else None.

    An ``x-mcp-header`` annotation maps header names to **string** values. The
    malformed shapes we reject are the ones that would otherwise be passed
    through into an outbound HTTP header, where a non-string is either a crash
    or — worse — a silently coerced value nobody intended to send.

    Absent metadata is *not* an error. Most tools carry none, and treating
    "no annotation" as "bad annotation" would reject almost every real server.
    """
    if not meta or not isinstance(meta, dict):
        return None
    if "x-mcp-header" not in meta:
        return None

    headers = meta["x-mcp-header"]
    if not isinstance(headers, dict):
        return f"x-mcp-header must be an object, got {type(headers).__name__}"

    for key, value in headers.items():
        if not isinstance(key, str) or not key.strip():
            return "x-mcp-header contains a non-string or empty header name"
        if not isinstance(value, str):
            return (
                f"x-mcp-header['{key}'] must be a string, "
                f"got {type(value).__name__}"
            )
    return None


# ---------------------------------------------------------------------------
# Mapping an MCP tool definition onto our catalog shape
# ---------------------------------------------------------------------------


def _schema_pairs(schema: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    """Flatten a JSON Schema `properties` block into our {name, type} pairs."""
    if not isinstance(schema, dict):
        return []
    props = schema.get("properties")
    if not isinstance(props, dict):
        return []
    pairs: list[dict[str, str]] = []
    for name, spec in props.items():
        kind = "string"
        if isinstance(spec, dict):
            raw = spec.get("type")
            if isinstance(raw, str):
                kind = raw
            elif isinstance(raw, list) and raw:
                kind = str(raw[0])
        pairs.append({"name": str(name), "type": kind})
    return pairs


def _is_read_only(annotations: Any) -> bool:
    """Deny-by-default read-only detection.

    A server must **explicitly** declare `readOnlyHint: true` for us to treat a
    tool as read-only. Absence is treated as "may write", which is the
    conservative reading and keeps the advisory-only invariant intact: a tool we
    are unsure about is catalogued and visible, but does not bind.
    """
    if annotations is None:
        return False
    hint = getattr(annotations, "read_only_hint", None)
    if hint is None and isinstance(annotations, dict):
        hint = annotations.get("readOnlyHint", annotations.get("read_only_hint"))
    return hint is True


def map_tool_definition(tool: Any, connector_id: str) -> dict[str, Any]:
    """Map one MCP tool definition onto the fields our catalog stores.

    Governance decisions encoded here, all deny-by-default:

    - **`write_capable = not readOnlyHint`.** A remote server has to declare
      itself read-only to get a bindable tool. This is the single most important
      line in the module: it means a silent or sloppy server produces
      catalogued-but-unbindable tools rather than quietly bindable ones.
    - **`permission_ceiling` is always `read`** for discovered tools. Discovery
      cannot infer intent, and `read` is the floor of the locked advisory enum.
      A human widens it later through the existing policy editor.
    - **`approval_state` is not set here at all** — the persistence layer forces
      `pending`. Nothing on the wire may grant consent.
    """
    name = getattr(tool, "name", None)
    description = getattr(tool, "description", None) or ""
    input_schema = getattr(tool, "input_schema", None)
    output_schema = getattr(tool, "output_schema", None)
    annotations = getattr(tool, "annotations", None)

    read_only = _is_read_only(annotations)

    return {
        "remote_tool_id": name,
        "name": name,
        "description": description.strip(),
        "category": "mcp",
        "permission_ceiling": "read",
        "write_capable": not read_only,
        "connector_id": connector_id,
        "schema": {
            "inputs": _schema_pairs(input_schema),
            "outputs": _schema_pairs(output_schema),
        },
    }


# ---------------------------------------------------------------------------
# The protocol calls
# ---------------------------------------------------------------------------


async def list_remote_tools(target: Any, connector_id: str) -> dict[str, Any]:
    """Perform a real `tools/list` and return mapped, validated definitions.

    `target` is whatever the SDK's `Client` accepts: a Streamable HTTP URL
    string for a real connector, or an `MCPServer` instance for in-memory
    testing. That polymorphism is the seam described in `ROADMAP.md` §4.0 —
    swapping local for remote changes this argument and nothing else.

    Returns `{tools, rejected, protocol_version, server_info}`. Rejections are
    returned, not raised: a server with one bad definition is still useful, and
    the operator needs to see what was dropped.
    """
    try:
        async with Client(target) as client:
            result = await client.list_tools()
            protocol_version = getattr(client, "protocol_version", None)
            info = getattr(client, "server_info", None)
    except Exception as exc:  # noqa: BLE001 — any failure here is "unreachable"
        raise McpProtocolError(str(exc)) from exc

    raw: Iterable[Any] = getattr(result, "tools", None) or []

    tools: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for definition in raw:
        name = getattr(definition, "name", None)
        if not name:
            rejected.append({"name": None, "reason": REJECT_NO_NAME, "detail": "definition has no name"})
            log.warning("[mcp] %s: dropped a tool definition with no name", connector_id)
            continue

        problem = validate_header_annotation(getattr(definition, "meta", None))
        if problem:
            # Spec: reject and EXCLUDE from the result, log a warning, keep going.
            rejected.append({"name": name, "reason": REJECT_INVALID_HEADER, "detail": problem})
            log.warning("[mcp] %s: excluded tool %r — %s", connector_id, name, problem)
            continue

        tools.append(map_tool_definition(definition, connector_id))

    if protocol_version and protocol_version != TARGET_PROTOCOL_VERSION:
        # Not fatal — the SDK negotiated something workable — but it means this
        # module's assumptions were written against a different revision.
        log.warning(
            "[mcp] %s: negotiated protocol %s, expected %s",
            connector_id, protocol_version, TARGET_PROTOCOL_VERSION,
        )

    return {
        "tools": tools,
        "rejected": rejected,
        "protocol_version": protocol_version,
        "server_info": {
            "name": getattr(info, "name", None),
            "version": getattr(info, "version", None),
        } if info is not None else None,
    }


async def call_remote_tool(
    target: Any,
    tool_name: str,
    arguments: Optional[dict[str, Any]] = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Perform a real `tools/call` and report what actually happened.

    **This is the function that closes the measurement half of CONCERNS R7.**
    Before it, `result_status` and `latency_ms` on a tool-call row were numbers a
    client sent us; here they are a clock we started and a response we read. The
    distinction is the whole reason Phase 5A was built before Phase 6.

    Never raises for a tool-level failure. Three outcomes are all *data*:

      - the call succeeded                      → ``ok=True,  is_error=False``
      - the server ran the tool and it failed   → ``ok=True,  is_error=True``
      - the server could not be reached at all  → ``ok=False``

    Collapsing the middle case into an exception would lose the difference
    between "the system said no" and "the system was not there", which is
    precisely the difference an operator is looking at the audit trail to find.

    The timeout is enforced by the SDK per round trip *and* by the caller around
    the whole call (`services/tool_gateway.py`), because a connector that accepts
    a socket and then goes quiet is a real failure mode and only the outer guard
    catches it.
    """
    started = time.perf_counter()
    try:
        async with Client(target) as client:
            result = await client.call_tool(
                tool_name, arguments or {}, read_timeout_seconds=timeout_s
            )
    except Exception as exc:  # noqa: BLE001 — unreachable, refused, timed out
        return {
            "ok": False,
            "is_error": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "content": None,
            "structured": None,
            "error": str(exc)[:500],
        }

    elapsed = int((time.perf_counter() - started) * 1000)

    # `content` is a list of typed blocks. We keep the text ones: the console
    # renders a result preview, not a rich MCP viewer, and an image or an
    # embedded resource has no honest one-line rendering.
    text_blocks = [
        getattr(block, "text", None)
        for block in (getattr(result, "content", None) or [])
        if getattr(block, "text", None)
    ]

    is_error = bool(getattr(result, "is_error", False))
    return {
        "ok": True,
        "is_error": is_error,
        "latency_ms": elapsed,
        "content": "\n".join(t for t in text_blocks if t) or None,
        "structured": getattr(result, "structured_content", None),
        "error": "\n".join(t for t in text_blocks if t)[:500] if is_error else None,
    }


async def probe(target: Any) -> dict[str, Any]:
    """Real healthcheck: open a session, list tools, measure it.

    This is a genuine round trip, which is what makes the resulting status
    meaningful. A connector without a real endpoint must NOT be sent here — the
    caller keeps those on the simulated path and labels them as such, because a
    fabricated green tick on a real connector is worse than no tick at all.
    """
    started = time.perf_counter()
    try:
        async with Client(target) as client:
            result = await client.list_tools()
            elapsed = int((time.perf_counter() - started) * 1000)
            return {
                "ok": True,
                "latency_ms": elapsed,
                "protocol_version": getattr(client, "protocol_version", None),
                "tool_count": len(getattr(result, "tools", None) or []),
                "error": None,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "protocol_version": None,
            "tool_count": 0,
            "error": str(exc)[:500],
        }
