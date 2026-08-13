"""MCP Connector Layer (Pass 3, Decision 3.1).

Discovery (`tools/list`) auto-populates DRAFT Tool Registry entries — never
approved, never auto-promoted: governance fields cannot be declared by a
remote server. Re-discovery diffs: new tools → new drafts; changed schemas →
new draft VERSIONS; vanished tools → reported (never auto-deleted).

The wire client is behind a seam (`set_discovery_override` in tests); the real
implementation uses the official `mcp` SDK over streamable-http / SSE.
Endpoints are SSRF-guarded like every other outbound test call.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib
import re
import uuid
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import AssetStatus, McpConnector, Role, ToolRecord, User, utcnow
from . import ssrf
from .tools_router import tool_payload
from .vault import resolve_secret


@dataclass
class DiscoveredTool:
    name: str
    description: str
    input_schema: dict


class DiscoveryError(Exception):
    pass


class TransportUnsupported(DiscoveryError):
    """The installed SDK exposes no client we know how to drive."""


@contextlib.asynccontextmanager
async def open_transport(endpoint: str, transport: str, headers: dict[str, str]):
    """Open MCP transport streams, tolerating both SDK majors.

    Our pin is `mcp>=1.0`, and the two majors differ exactly here: v1 exported
    `streamablehttp_client(url, headers=...)`, while v2 renamed it to
    `streamable_http_client` and moved headers onto an httpx client passed in.
    A fresh install resolves to v2, so the v1-only call silently made the
    DEFAULT transport unusable — discovery and execution both failed with an
    ImportError wrapped as a connection failure.

    Discovery and execution share this helper so they cannot drift apart again.
    SSE is unchanged across the two majors.
    """
    if transport == "sse":
        from mcp.client.sse import sse_client
        async with sse_client(endpoint, headers=headers or None) as streams:
            yield streams[0], streams[1]
        return

    module = importlib.import_module("mcp.client.streamable_http")

    legacy = getattr(module, "streamablehttp_client", None)      # SDK v1
    if legacy is not None:
        async with legacy(endpoint, headers=headers or None) as streams:
            yield streams[0], streams[1]
        return

    modern = getattr(module, "streamable_http_client", None)     # SDK v2
    if modern is None:
        raise TransportUnsupported(
            "the installed mcp SDK exposes neither streamablehttp_client (v1) nor "
            "streamable_http_client (v2); cannot open a streamable-http connection")
    if headers:
        # v2 carries auth headers on the http client rather than the call
        async with module.create_mcp_http_client(headers=headers) as http_client:
            async with modern(endpoint, http_client=http_client) as streams:
                yield streams[0], streams[1]
    else:
        async with modern(endpoint) as streams:
            yield streams[0], streams[1]


def sdk_attr(obj: object, *names: str, default=None):
    """Read the first attribute that exists, across SDK naming conventions.

    v1 model fields were camelCase on the wire and in Python (`inputSchema`,
    `isError`); v2 exposes snake_case. Both majors satisfy our `mcp>=1.0` pin.
    """
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def explain_exc(exc: BaseException) -> str:
    """Flatten ExceptionGroups into something a human can act on.

    anyio task groups surface failures as 'unhandled errors in a TaskGroup
    (1 sub-exception)', which hides the actual cause — a connection refusal, a
    404 on the endpoint path, an SDK mismatch. Discovery failures are read by
    people trying to work out why their server will not register, so the real
    message has to survive.
    """
    inner = getattr(exc, "exceptions", None)
    if inner:
        return "; ".join(explain_exc(e) for e in inner)
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _discover_real(endpoint: str, transport: str, headers: dict[str, str], timeout: float) -> list[DiscoveredTool]:
    async def _run() -> list[DiscoveredTool]:
        from mcp import ClientSession
        async with open_transport(endpoint, transport, headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    DiscoveredTool(
                        name=t.name,
                        description=t.description or "",
                        input_schema=sdk_attr(t, "input_schema", "inputSchema", default={}),
                    )
                    for t in result.tools
                ]

    try:
        return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
    except Exception as exc:  # network/protocol errors become one honest failure kind
        raise DiscoveryError(explain_exc(exc)) from exc


# Test seam — same pattern as adapters.models.set_adapter_override.
_discovery_override: Callable[[str, str, dict, float], list[DiscoveredTool]] | None = None


def set_discovery_override(fn: Callable[[str, str, dict, float], list[DiscoveredTool]] | None) -> None:
    global _discovery_override
    _discovery_override = fn


def discover(endpoint: str, transport: str, headers: dict[str, str], timeout: float = 15.0) -> list[DiscoveredTool]:
    if _discovery_override is not None:
        return _discovery_override(endpoint, transport, headers, timeout)
    return _discover_real(endpoint, transport, headers, timeout)


# ---- router -----------------------------------------------------------------

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

_EDIT_ROLES = (Role.ai_engineer, Role.platform_admin)


def _payload(c: McpConnector) -> dict:
    return {
        "id": str(c.id), "name": c.name, "endpoint": c.endpoint, "transport": c.transport,
        "auth": {"header_name": (c.auth or {}).get("header_name"),
                 "credential_ref": (c.auth or {}).get("credential_ref")},
        "status": c.status, "health": c.health,
        "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
    }


class ConnectorBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    endpoint: str = Field(min_length=8)
    transport: str = Field(default="streamable_http", pattern="^(streamable_http|sse)$")
    auth: dict = Field(default_factory=lambda: {"header_name": None, "credential_ref": None})


def _get_connector(db: Session, connector_id: uuid.UUID) -> McpConnector:
    conn = db.get(McpConnector, connector_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return conn


def _headers_for(db: Session, conn: McpConnector) -> dict[str, str]:
    auth = conn.auth or {}
    ref = auth.get("credential_ref")
    if not ref:
        return {}
    secret = resolve_secret(db, ref)
    if secret is None:
        raise HTTPException(status_code=422, detail=f"credential {ref!r} not found in vault")
    return {auth.get("header_name") or "Authorization": secret}


@router.get("")
def list_connectors(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    return [_payload(c) for c in db.scalars(select(McpConnector).order_by(McpConnector.name)).all()]


@router.post("", status_code=201)
def create_connector(
    body: ConnectorBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    allowed, reason = ssrf.check_url(body.endpoint)
    if not allowed:
        raise HTTPException(status_code=403, detail=f"endpoint rejected: {reason}")
    if db.scalars(select(McpConnector).where(McpConnector.name == body.name)).first():
        raise HTTPException(status_code=409, detail="connector name exists")
    conn = McpConnector(created_by=user.id, **body.model_dump())
    db.add(conn)
    db.flush()
    audit(db, user, "mcp_connector_created", "mcp_connector", str(conn.id), {"endpoint_host": body.endpoint.split('//')[-1].split('/')[0]})
    db.commit()
    return _payload(conn)


def _slug_for(conn: McpConnector, tool_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{conn.name}-{tool_name}".lower()).strip("-")[:56]
    return base or "mcp-tool"


@router.post("/{connector_id}/discover")
def discover_tools(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    """tools/list → DRAFT registry entries + re-discovery diff report."""
    conn = _get_connector(db, connector_id)
    if conn.status != "active":
        raise HTTPException(status_code=409, detail="connector is disabled")
    allowed, reason = ssrf.check_url(conn.endpoint)
    if not allowed:
        raise HTTPException(status_code=403, detail=f"endpoint rejected: {reason}")

    try:
        found = discover(conn.endpoint, conn.transport, _headers_for(db, conn))
        health_ok = True
        note = f"{len(found)} tools listed"
    except DiscoveryError as exc:
        found = None
        health_ok = False
        note = str(exc)[:300]

    prev = dict(conn.health or {})
    conn.health = {
        "ok": health_ok,
        "last_checked": utcnow().isoformat(),
        "consecutive_failures": 0 if health_ok else int(prev.get("consecutive_failures") or 0) + 1,
        "note": note,
    }
    conn.updated_at = utcnow()

    if found is None:
        audit(db, user, "mcp_discovery_failed", "mcp_connector", str(conn.id), {"note": note})
        db.commit()
        raise HTTPException(status_code=502, detail=f"discovery failed: {note}")

    existing = db.scalars(select(ToolRecord).where(ToolRecord.mcp_connector_id == conn.id)).all()
    by_tool_name: dict[str, list[ToolRecord]] = {}
    for t in existing:
        by_tool_name.setdefault((t.implementation.get("config") or {}).get("tool_name", ""), []).append(t)

    created: list[dict] = []
    updated: list[dict] = []
    unchanged: list[str] = []
    for d in found:
        rows = sorted(by_tool_name.get(d.name, []), key=lambda t: t.version, reverse=True)
        impl = {"kind": "mcp", "config": {"connector_id": str(conn.id), "tool_name": d.name}}
        if not rows:
            tool = ToolRecord(
                slug=_slug_for(conn, d.name), name=d.name, description=d.description,
                input_schema=d.input_schema, implementation=impl,
                source="mcp_discovery", mcp_connector_id=conn.id, owner_id=user.id,
                # governance fields default conservative; a human reviews before approval
            )
            db.add(tool)
            db.flush()
            created.append(tool_payload(tool))
        else:
            newest = rows[0]
            if newest.input_schema != d.input_schema or newest.description != d.description:
                draft = ToolRecord(
                    slug=newest.slug, version=newest.version + 1, name=d.name,
                    description=d.description, input_schema=d.input_schema,
                    implementation=impl, permission_type=newest.permission_type,
                    risk_level=newest.risk_level, human_approval_required=newest.human_approval_required,
                    source="mcp_discovery", mcp_connector_id=conn.id, owner_id=user.id,
                )
                db.add(draft)
                db.flush()
                updated.append(tool_payload(draft))
            else:
                unchanged.append(d.name)

    vanished = [name for name in by_tool_name if name and name not in {d.name for d in found}]
    audit(db, user, "mcp_discovery", "mcp_connector", str(conn.id), {
        "created": len(created), "updated": len(updated),
        "unchanged": len(unchanged), "vanished": vanished,
    })
    events.emit("mcp.discovered", {"connector_id": str(conn.id), "created": len(created)})
    db.commit()
    return {
        "connector": _payload(conn),
        "created_drafts": created, "new_version_drafts": updated,
        "unchanged": unchanged,
        "vanished": vanished,  # reported, never auto-deleted
    }


@router.post("/{connector_id}/health")
def check_health(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user_dep),
):
    conn = _get_connector(db, connector_id)
    allowed, reason = ssrf.check_url(conn.endpoint)
    if not allowed:
        raise HTTPException(status_code=403, detail=f"endpoint rejected: {reason}")
    prev = dict(conn.health or {})
    try:
        found = discover(conn.endpoint, conn.transport, _headers_for(db, conn), timeout=8.0)
        conn.health = {"ok": True, "last_checked": utcnow().isoformat(),
                       "consecutive_failures": 0, "note": f"{len(found)} tools listed"}
    except DiscoveryError as exc:
        conn.health = {"ok": False, "last_checked": utcnow().isoformat(),
                       "consecutive_failures": int(prev.get("consecutive_failures") or 0) + 1,
                       "note": str(exc)[:300]}
    conn.updated_at = utcnow()
    db.commit()
    return _payload(conn)
