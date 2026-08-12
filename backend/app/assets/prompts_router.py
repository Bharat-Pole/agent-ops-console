"""Prompt Repository (Pass 3): packs + immutable versions. History is never
mutated — edits create new versions, rollback creates a NEW version whose
content copies the target (rolled_back_from records provenance).
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import (
    AgentControlRecord, AssetBinding, AssetStatus, Deployment, PromptPack,
    PromptVersion, Role, User, Workflow, WorkflowStatus, WorkflowVersion,
)
from . import workflow

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

_EDIT_ROLES = (Role.ai_engineer, Role.agent_creator, Role.platform_admin)

# 10 Blueprint prompt types
PROMPT_TYPES = (
    "system", "persona", "task", "chain_of_thought", "few_shot", "guardrail",
    "citation", "refusal", "output_format", "evaluation_rubric",
)


def _pack_payload(p: PromptPack, versions: list[PromptVersion] | None = None) -> dict:
    out = {
        "id": str(p.id), "slug": p.slug, "name": p.name, "prompt_type": p.prompt_type,
        "description": p.description, "tags": p.tags, "created_at": p.created_at.isoformat(),
    }
    if versions is not None:
        out["versions"] = [_version_payload(v) for v in versions]
    return out


def _version_payload(v: PromptVersion) -> dict:
    return {
        "id": str(v.id), "pack_id": str(v.pack_id), "version": v.version,
        "content": v.content, "variables": v.variables, "status": v.status.value,
        "notes": v.notes, "rolled_back_from": v.rolled_back_from,
        "created_at": v.created_at.isoformat(),
    }


class PackBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    prompt_type: str = "system"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    content: str = Field(min_length=1)  # first version content
    variables: list[str] = Field(default_factory=list)


@router.get("")
def list_packs(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    packs = db.scalars(select(PromptPack).order_by(PromptPack.name)).all()
    out = []
    for p in packs:
        versions = db.scalars(
            select(PromptVersion).where(PromptVersion.pack_id == p.id).order_by(PromptVersion.version.desc())
        ).all()
        row = _pack_payload(p)
        row["latest_version"] = versions[0].version if versions else 0
        row["latest_status"] = versions[0].status.value if versions else None
        row["approved_version"] = next((v.version for v in versions if v.status == AssetStatus.approved), None)
        out.append(row)
    return out


@router.post("", status_code=201)
def create_pack(
    body: PackBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    if body.prompt_type not in PROMPT_TYPES:
        raise HTTPException(status_code=422, detail=f"prompt_type must be one of {PROMPT_TYPES}")
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:56] or "prompt"
    if db.scalars(select(PromptPack).where(PromptPack.slug == slug)).first():
        raise HTTPException(status_code=409, detail=f"prompt slug {slug!r} exists")
    pack = PromptPack(slug=slug, name=body.name, prompt_type=body.prompt_type,
                      description=body.description, tags=body.tags, owner_id=user.id)
    db.add(pack)
    db.flush()
    v1 = PromptVersion(pack_id=pack.id, version=1, content=body.content,
                       variables=body.variables, created_by=user.id)
    db.add(v1)
    db.flush()
    audit(db, user, "prompt_pack_created", "prompt", str(pack.id), {"slug": slug})
    db.commit()
    return _pack_payload(pack, [v1])


def _get_pack(db: Session, pack_id: uuid.UUID) -> PromptPack:
    pack = db.get(PromptPack, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="prompt pack not found")
    return pack


def _versions(db: Session, pack_id: uuid.UUID) -> list[PromptVersion]:
    return list(db.scalars(
        select(PromptVersion).where(PromptVersion.pack_id == pack_id).order_by(PromptVersion.version.desc())
    ).all())


@router.get("/{pack_id}")
def get_pack(pack_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    pack = _get_pack(db, pack_id)
    return _pack_payload(pack, _versions(db, pack.id))


_COMPARED_FIELDS = ("content", "variables", "status", "notes", "rolled_back_from")


@router.get("/{pack_id}/versions/{version_a}/compare/{version_b}")
def compare_versions(
    pack_id: uuid.UUID,
    version_a: int,
    version_b: int,
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
):
    """READ-ONLY comparison of two versions of the SAME pack.

    Returns both immutable rows plus which fields differ; the textual diff is
    rendered client-side. Nothing is written — no version is created, no
    approval state moves, and no diff result is persisted.
    """
    pack = _get_pack(db, pack_id)
    rows = {v.version: v for v in _versions(db, pack.id)}
    for wanted in (version_a, version_b):
        if wanted not in rows:
            # scoping the lookup to this pack is what stops a caller comparing
            # versions across two different packs
            raise HTTPException(status_code=404,
                                detail=f"version {wanted} does not belong to this prompt pack")
    a, b = rows[version_a], rows[version_b]
    changed = [f for f in _COMPARED_FIELDS if getattr(a, f, None) != getattr(b, f, None)]
    return {
        "pack": _pack_payload(pack),
        "a": _version_payload(a),
        "b": _version_payload(b),
        "changed_fields": changed,
        "identical": not changed,
    }


@router.get("/{pack_id}/usage")
def pack_usage(
    pack_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
):
    """Where this prompt is referenced, COMPUTED from persisted references.

    Nothing is stored: a `used_by` column would be a duplicate that silently
    drifts from the graphs and bindings it claims to summarise. Three real
    reference paths exist — asset bindings, workflow-version graphs, and the
    frozen asset pins inside deployment manifests — and workflow/deployment
    status gives an honest active-vs-historical split.
    """
    pack = _get_pack(db, pack_id)
    slug = pack.slug
    agents = {a.id: a for a in db.scalars(select(AgentControlRecord)).all()}

    def agent_info(agent_id) -> dict:
        agent = agents.get(agent_id)
        return {
            "agent_id": str(agent_id),
            "agent_name": agent.name if agent else None,
            "agent_slug": agent.slug if agent else None,
            "lifecycle_status": agent.lifecycle_status.value if agent else None,
        }

    bindings = [
        {**agent_info(b.agent_id), "reference_type": "binding",
         "version_policy": b.version_policy, "pinned_version": b.pinned_version}
        for b in db.scalars(select(AssetBinding).where(
            AssetBinding.asset_type == "prompt", AssetBinding.asset_ref == slug)).all()
    ]

    active_workflows: list[dict] = []
    historical_workflows: list[dict] = []
    workflows = {w.id: w for w in db.scalars(select(Workflow)).all()}
    for version in db.scalars(select(WorkflowVersion)).all():
        nodes = (version.graph or {}).get("nodes") or []
        if not any((n.get("config") or {}).get("pack_ref") == slug for n in nodes):
            continue
        workflow = workflows.get(version.workflow_id)
        entry = {
            **agent_info(workflow.agent_id if workflow else None),
            "reference_type": "workflow_node",
            "workflow_id": str(version.workflow_id),
            "workflow_name": workflow.name if workflow else None,
            "workflow_version": version.version,
            "workflow_status": version.status.value,
        }
        (active_workflows if version.status == WorkflowStatus.active
         else historical_workflows).append(entry)

    active_deployments: list[dict] = []
    historical_deployments: list[dict] = []
    for deployment in db.scalars(select(Deployment)).all():
        pin = ((deployment.manifest or {}).get("asset_pins") or {}).get("prompts", {}).get(slug)
        if not pin:
            continue
        entry = {
            **agent_info(deployment.agent_id),
            "reference_type": "deployment_pin",
            "deployment_id": str(deployment.id),
            "channel": deployment.channel,
            "deployment_status": deployment.status,
            "pinned_version": pin.get("version"),
        }
        (active_deployments if deployment.status == "active"
         else historical_deployments).append(entry)

    return {
        "pack_id": str(pack.id),
        "slug": slug,
        # currently in force
        "active": {
            "bindings": bindings,
            "workflow_versions": active_workflows,
            "deployments": active_deployments,
        },
        # referenced, but not by anything live — shown separately so a reviewer
        # never mistakes an old draft or superseded deployment for current use
        "historical": {
            "workflow_versions": historical_workflows,
            "deployments": historical_deployments,
        },
        "totals": {
            "active": len(bindings) + len(active_workflows) + len(active_deployments),
            "historical": len(historical_workflows) + len(historical_deployments),
        },
    }


class VersionBody(BaseModel):
    content: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    notes: str = ""


@router.post("/{pack_id}/versions", status_code=201)
def create_version(
    pack_id: uuid.UUID,
    body: VersionBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    pack = _get_pack(db, pack_id)
    versions = _versions(db, pack.id)
    next_v = (versions[0].version + 1) if versions else 1
    row = PromptVersion(pack_id=pack.id, version=next_v, content=body.content,
                        variables=body.variables, notes=body.notes, created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user, "prompt_version_created", "prompt", str(pack.id), {"version": next_v})
    db.commit()
    return _version_payload(row)


@router.post("/{pack_id}/versions/{version}/rollback", status_code=201)
def rollback_to_version(
    pack_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    """Rollback = NEW version with the target's content (history untouched)."""
    pack = _get_pack(db, pack_id)
    target = db.scalars(select(PromptVersion).where(
        PromptVersion.pack_id == pack.id, PromptVersion.version == version)).first()
    if target is None:
        raise HTTPException(status_code=404, detail=f"version {version} not found")
    versions = _versions(db, pack.id)
    row = PromptVersion(
        pack_id=pack.id, version=versions[0].version + 1, content=target.content,
        variables=target.variables, notes=f"rollback to v{version}",
        rolled_back_from=version, created_by=user.id,
    )
    db.add(row)
    db.flush()
    audit(db, user, "prompt_rolled_back", "prompt", str(pack.id),
          {"to_version": version, "as_version": row.version})
    db.commit()
    return _version_payload(row)


@router.post("/{pack_id}/versions/{version}/submit")
def submit_version(
    pack_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    pack = _get_pack(db, pack_id)
    row = db.scalars(select(PromptVersion).where(
        PromptVersion.pack_id == pack.id, PromptVersion.version == version)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"version {version} not found")
    if row.status != AssetStatus.draft:
        raise HTTPException(status_code=409, detail=f"cannot submit from status {row.status.value}")
    workflow.request_approval(db, "prompt_version", row.id, [("governance_review", Role.governance_reviewer)])
    row.status = AssetStatus.pending_approval
    audit(db, user, "prompt_submitted_for_approval", "prompt", str(pack.id), {"version": version})
    events.emit("asset.submitted", {"type": "prompt_version", "id": str(row.id)})
    db.commit()
    return _version_payload(row)
