"""Tool Registry (Pass 3). Declared implementation binding only; write-class
permission types structurally force HITL + dual sign-off; the base phase
additionally refuses BINDING write tools to agents regardless of approval
(enforced in policy.can_bind_tool — Decision 0.3 phased doctrine).

Try-out endpoint carries the /v1/tools/try redesign: session-auth, GET-only,
URL + secret from PERSISTED config exclusively, SSRF-guarded, audited.
"""
from __future__ import annotations

import re
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import (
    AssetStatus, PermissionType, Role, ToolRecord, User, WRITE_PERMISSION_TYPES, utcnow,
)
from . import ssrf, workflow
from .vault import resolve_secret

router = APIRouter(prefix="/api/tools", tags=["tools"])

_EDIT_ROLES = (Role.ai_engineer, Role.agent_creator, Role.platform_admin)
# Only kinds the ENGINE can actually execute are registrable. ("none" is the
# honest not-connected stub.) A kind the engine cannot run has no business
# being declarable — that is how you get fail-at-runtime surprises.
_IMPL_KINDS = {"http_api", "mcp", "none"}


def tool_payload(t: ToolRecord) -> dict:
    return {
        "id": str(t.id), "slug": t.slug, "version": t.version, "name": t.name,
        "description": t.description, "business_purpose": t.business_purpose,
        "permission_type": t.permission_type.value, "is_write_class": t.permission_type in WRITE_PERMISSION_TYPES,
        "risk_level": t.risk_level, "input_schema": t.input_schema, "output_schema": t.output_schema,
        "implementation": t.implementation,
        # auth is metadata + credential NAME only — never a value
        "auth": {"method": (t.auth or {}).get("method", "none"),
                 "credential_ref": (t.auth or {}).get("credential_ref")},
        "rate_limit_per_min": t.rate_limit_per_min, "timeout_seconds": t.timeout_seconds,
        "logging_requirement": t.logging_requirement,
        "human_approval_required": t.human_approval_required,
        "error_handling": t.error_handling, "status": t.status.value, "source": t.source,
        "mcp_connector_id": str(t.mcp_connector_id) if t.mcp_connector_id else None,
        "superseded_by": str(t.superseded_by) if t.superseded_by else None,
        "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat(),
    }


class ToolBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = ""
    business_purpose: str = ""
    permission_type: PermissionType = PermissionType.read
    risk_level: str = Field(default="low", pattern="^(low|medium|high|restricted)$")
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    implementation: dict = Field(default_factory=lambda: {"kind": "none", "config": {}})
    auth: dict = Field(default_factory=lambda: {"method": "none", "credential_ref": None})
    rate_limit_per_min: int | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    logging_requirement: str = "standard"
    human_approval_required: bool = False
    error_handling: dict = Field(default_factory=lambda: {"retry_count": 0, "fallback_behavior": "fail_gracefully"})


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:56] or "tool"


def _apply_structural_rules(tool: ToolRecord, notes: list[str]) -> None:
    """Write-class forcing is code, not convention."""
    if tool.permission_type in WRITE_PERMISSION_TYPES:
        if not tool.human_approval_required:
            tool.human_approval_required = True
            notes.append("human_approval_required forced true (write-class permission)")
        if tool.risk_level in ("low", "medium"):
            tool.risk_level = "high"
            notes.append("risk_level floored to high (write-class permission)")


def _validate_body(body: ToolBody) -> None:
    kind = (body.implementation or {}).get("kind")
    if kind not in _IMPL_KINDS:
        raise HTTPException(status_code=422, detail=f"implementation.kind must be one of {sorted(_IMPL_KINDS)}")
    method = (body.auth or {}).get("method", "none")
    if method not in ("none", "api_key_header", "bearer"):
        raise HTTPException(status_code=422, detail="auth.method must be none | api_key_header | bearer")
    if method != "none" and not (body.auth or {}).get("credential_ref"):
        raise HTTPException(status_code=422, detail="auth.credential_ref (secret name) required when auth.method != none")


@router.get("")
def list_tools(
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    stmt = select(ToolRecord).order_by(ToolRecord.slug, ToolRecord.version.desc())
    if status:
        stmt = stmt.where(ToolRecord.status == AssetStatus(status))
    if q:
        stmt = stmt.where(ToolRecord.name.ilike(f"%{q}%"))
    return [tool_payload(t) for t in db.scalars(stmt).all()]


@router.post("", status_code=201)
def create_tool(
    body: ToolBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    _validate_body(body)
    slug = _slugify(body.name)
    exists = db.scalars(select(ToolRecord).where(ToolRecord.slug == slug)).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"tool slug {slug!r} exists — create a new version on it instead")
    tool = ToolRecord(slug=slug, owner_id=user.id, **body.model_dump())
    notes: list[str] = []
    _apply_structural_rules(tool, notes)
    db.add(tool)
    db.flush()
    audit(db, user, "tool_created", "tool", str(tool.id), {"slug": slug, "structural": notes})
    db.commit()
    return tool_payload(tool)


def _get_tool(db: Session, tool_id: uuid.UUID) -> ToolRecord:
    tool = db.get(ToolRecord, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="tool not found")
    return tool


@router.get("/{tool_id}")
def get_tool(tool_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    return tool_payload(_get_tool(db, tool_id))


@router.put("/{tool_id}")
def update_tool(
    tool_id: uuid.UUID,
    body: ToolBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    tool = _get_tool(db, tool_id)
    if tool.status not in (AssetStatus.draft, AssetStatus.rejected):
        raise HTTPException(status_code=409, detail="only draft/rejected versions are editable — create a new version")
    _validate_body(body)
    for key, value in body.model_dump().items():
        setattr(tool, key, value)
    tool.status = AssetStatus.draft  # editing a rejected tool returns it to draft
    notes: list[str] = []
    _apply_structural_rules(tool, notes)
    tool.updated_at = utcnow()
    audit(db, user, "tool_updated", "tool", str(tool.id), {"structural": notes})
    db.commit()
    return tool_payload(tool)


@router.post("/{tool_id}/new-version", status_code=201)
def new_tool_version(
    tool_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    """Fork the newest version of this slug as a new DRAFT (approved rows are
    immutable — create→version→supersede doctrine)."""
    tool = _get_tool(db, tool_id)
    newest = db.scalars(
        select(ToolRecord).where(ToolRecord.slug == tool.slug).order_by(ToolRecord.version.desc())
    ).first()
    draft = ToolRecord(
        slug=tool.slug, version=newest.version + 1, name=tool.name, description=tool.description,
        business_purpose=tool.business_purpose, permission_type=tool.permission_type,
        risk_level=tool.risk_level, input_schema=tool.input_schema, output_schema=tool.output_schema,
        implementation=tool.implementation, auth=tool.auth, rate_limit_per_min=tool.rate_limit_per_min,
        timeout_seconds=tool.timeout_seconds, logging_requirement=tool.logging_requirement,
        human_approval_required=tool.human_approval_required, error_handling=tool.error_handling,
        source=tool.source, mcp_connector_id=tool.mcp_connector_id, owner_id=user.id,
    )
    db.add(draft)
    db.flush()
    audit(db, user, "tool_version_created", "tool", str(draft.id), {"slug": tool.slug, "version": draft.version})
    db.commit()
    return tool_payload(draft)


@router.post("/{tool_id}/submit")
def submit_tool_for_approval(
    tool_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    tool = _get_tool(db, tool_id)
    if tool.status != AssetStatus.draft:
        raise HTTPException(status_code=409, detail=f"cannot submit from status {tool.status.value}")
    steps: list[tuple[str, Role]] = [("governance_review", Role.governance_reviewer)]
    if tool.permission_type in WRITE_PERMISSION_TYPES:
        steps.append(("security_signoff", Role.security_data_owner))  # dual sign-off
    workflow.request_approval(db, "tool", tool.id, steps)
    tool.status = AssetStatus.pending_approval
    audit(db, user, "tool_submitted_for_approval", "tool", str(tool.id),
          {"steps": [s for s, _ in steps], "write_class": tool.permission_type in WRITE_PERMISSION_TYPES})
    events.emit("asset.submitted", {"type": "tool", "id": str(tool.id)})
    db.commit()
    return tool_payload(tool)


class TryoutBody(BaseModel):
    params: dict = Field(default_factory=dict)  # query params only — GET-only endpoint


@router.post("/{tool_id}/tryout")
def tryout_tool(
    tool_id: uuid.UUID,
    body: TryoutBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    """Secure try-out (the /v1/tools/try redesign):
    - outbound GET only; URL comes ONLY from the persisted implementation config
    - SSRF guard resolves the host and denies private ranges
    - secret resolved server-side from the tool's credential_ref; never echoed
    """
    tool = _get_tool(db, tool_id)
    impl = tool.implementation or {}
    if impl.get("kind") != "http_api":
        raise HTTPException(status_code=422, detail=f"try-out supports http_api implementations (this tool: {impl.get('kind')})")
    url = (impl.get("config") or {}).get("base_url")
    if not url:
        raise HTTPException(status_code=422, detail="implementation.config.base_url is not configured")

    allowed, reason = ssrf.check_url(url)
    audit(db, user, "tool_tryout", "tool", str(tool.id), {"url_host": httpx.URL(url).host, "allowed": allowed, "reason": reason})
    if not allowed:
        db.commit()  # the denial is audited
        raise HTTPException(status_code=403, detail=f"try-out blocked: {reason}")

    # same source-of-truth rule as the engine: static headers from persisted
    # config, auth applied on top; nothing header-ish comes from the caller
    headers: dict[str, str] = {
        str(k): str(v) for k, v in ((impl.get("config") or {}).get("headers") or {}).items()
    }
    auth = tool.auth or {}
    if auth.get("method") in ("api_key_header", "bearer"):
        secret = resolve_secret(db, auth.get("credential_ref") or "")
        if secret is None:
            db.commit()
            raise HTTPException(status_code=422, detail=f"credential {auth.get('credential_ref')!r} not found in vault")
        if auth["method"] == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        else:
            headers[(auth.get("header_name") or "X-API-Key")] = secret

    try:
        response = httpx.get(url, params=body.params, headers=headers,
                             timeout=min(tool.timeout_seconds, 30), follow_redirects=False)
        preview = response.text[:2000]
        db.commit()
        return {"status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "body_preview": preview, "truncated": len(response.text) > 2000}
    except httpx.HTTPError as exc:
        db.commit()
        raise HTTPException(status_code=502, detail=f"outbound call failed: {exc}") from exc
