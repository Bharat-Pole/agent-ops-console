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
from ..models import AssetStatus, PromptPack, PromptVersion, Role, User
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
