"""Register and edit MCP servers — Phase 2 (Blueprint §3.5, capability #1).

Connectors were seed-only, which was conspicuous once they became persisted:
registering an MCP server is the most basic capability of an MCP page, and
Blueprint §10 names "Tool Registry / MCP Connector Setup" as an MVP screen.

Two invariants this module must not break:

  1. **Status is owned by the health cascade, never by an author.** A new
     connector seeds `connected` and is thereafter set only by
     `services/connector_health.py`. Neither create nor update accepts a
     `status` from the client -- a tool is never healthier than the connector
     that serves it, and that chain starts here.
  2. **`tools_provided` is a *claim*, not a binding.** It is what the server
     advertises. The catalog is separate, and the diff between them is exactly
     what `GET /v1/connectors/:id/tools` reports as `undiscovered`/`orphaned`.
     Registering a connector therefore does NOT create tools.
"""

import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from app.repositories import audit_repo, connectors_repo

# Mirrors McpTransport / McpAuthMode in src/types/assets.ts.
TRANSPORTS = ("sse", "stdio", "http")
AUTH_MODES = ("secret_manager", "oauth", "none")

# Fields an update may touch. `status`, `tools_provided` and `last_healthcheck`
# are deliberately absent -- they belong to the health cascade and to
# discovery, not to an editor. See invariant 1.
EDITABLE = ("name", "transport", "endpoint", "auth_mode")

# Transport → the URI scheme(s) its endpoint may use.
#
# `sse` accepts http(s) as well as sse:// **on purpose**: MCP's SSE transport is
# an HTTP endpoint that streams Server-Sent Events, so `https://host/sse` is the
# canonical real-world form. The seed happens to use `sse://` throughout, which
# makes the pair look stricter than it is — do not "tighten" this to sse:// only.
#
# `stdio` has no network endpoint; it is a command line, so it is only checked
# for non-emptiness.
_SCHEMES = {"sse": ("sse://", "http://", "https://"), "http": ("http://", "https://")}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


async def _unique_connector_id(name: str) -> str:
    base = _slugify(name) or "connector"
    if await connectors_repo.get_by_id(base) is None:
        return base
    return f"{base}-{secrets.token_hex(2)}"


def _validate(name: str, transport: str, endpoint: str, auth_mode: str) -> None:
    if not name:
        raise ValueError("Connector name is required.")
    if transport not in TRANSPORTS:
        raise ValueError(f"transport must be one of {', '.join(TRANSPORTS)}.")
    if auth_mode not in AUTH_MODES:
        raise ValueError(f"auth_mode must be one of {', '.join(AUTH_MODES)}.")
    if not endpoint:
        raise ValueError("endpoint is required.")

    expected = _SCHEMES.get(transport)
    if expected and not endpoint.startswith(expected):
        raise ValueError(f"endpoint for transport '{transport}' must start with {' or '.join(expected)}.")


async def create_connector(body: dict[str, Any]) -> dict[str, Any]:
    name = (body.get("name") or "").strip()
    transport = (body.get("transport") or "").strip()
    endpoint = (body.get("endpoint") or "").strip()
    auth_mode = (body.get("auth_mode") or "").strip()

    _validate(name, transport, endpoint, auth_mode)

    connector_id = await _unique_connector_id(name)
    connector = {
        "id": connector_id,
        "name": name,
        "transport": transport,
        "endpoint": endpoint,
        "auth_mode": auth_mode,
        # Seeded connected, then owned solely by the cascade (invariant 1).
        "status": "connected",
        # Empty on purpose: a fresh connector advertises nothing until it is
        # discovered, so "Discover tools" shows a real diff (invariant 2).
        "tools_provided": [],
        "last_healthcheck": _now_iso(),
    }
    await connectors_repo.insert(connector)

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": "create_connector",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": f"Registered MCP server {connector_id} ({transport}, {auth_mode}) at {endpoint}.",
        }
    )

    return {"connector": connector, "auditEvent": audit_event}


async def update_connector(connector_id: str, body: dict[str, Any]) -> dict[str, Any]:
    existing = await connectors_repo.get_by_id(connector_id)
    if existing is None:
        raise LookupError("Connector not found.")

    # Merge only editable fields, then validate the *result* — so a partial
    # patch cannot slip an invalid combination past the transport/scheme check.
    merged = {**existing}
    changed: list[str] = []
    for field in EDITABLE:
        if field in body:
            value = (body.get(field) or "").strip()
            if value != merged[field]:
                merged[field] = value
                changed.append(field)

    _validate(merged["name"], merged["transport"], merged["endpoint"], merged["auth_mode"])

    if not changed:
        return {"connector": existing, "auditEvent": None, "changed": []}

    connector = await connectors_repo.update(
        connector_id, merged["name"], merged["transport"], merged["endpoint"], merged["auth_mode"]
    )
    if connector is None:
        raise LookupError("Connector not found.")

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": "Platform Engineer",
            "action": "update_connector",
            "entity_type": "connector",
            "entity_id": connector_id,
            "detail": f"Updated MCP server {connector_id}: {', '.join(changed)}.",
        }
    )

    return {"connector": connector, "auditEvent": audit_event, "changed": changed}
