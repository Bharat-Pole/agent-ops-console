"""Agent↔asset bindings (Decision 1.1: refs with a version policy; deploy-time
snapshots pin exact versions in Increment F). The bind-time write-tool gate is
PolicyService's — every DENY is audited with the rules version.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events, policy
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import (
    AgentControlRecord, AssetBinding, AssetStatus, KnowledgeSource, ModelCatalogEntry,
    PromptPack, RagPipeline, Role, ToolRecord, User,
)

router = APIRouter(prefix="/api/agents/{agent_id}/bindings", tags=["bindings"])

_EDIT_ROLES = (Role.agent_creator, Role.agent_owner, Role.ai_engineer)
_ASSET_TYPES = ("tool", "prompt", "knowledge", "rag", "model")


def _payload(b: AssetBinding) -> dict:
    return {
        "id": str(b.id), "agent_id": str(b.agent_id), "asset_type": b.asset_type,
        "asset_ref": b.asset_ref, "version_policy": b.version_policy,
        "pinned_version": b.pinned_version, "created_at": b.created_at.isoformat(),
    }


def _get_agent(db: Session, agent_id: uuid.UUID) -> AgentControlRecord:
    agent = db.get(AgentControlRecord, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


class BindBody(BaseModel):
    asset_type: str
    asset_ref: str = Field(min_length=1, max_length=140)
    version_policy: str = Field(default="latest_approved", pattern="^(latest_approved|pinned)$")
    pinned_version: int | None = None


@router.get("")
def list_bindings(agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    _get_agent(db, agent_id)
    rows = db.scalars(select(AssetBinding).where(AssetBinding.agent_id == agent_id)).all()
    return [_payload(b) for b in rows]


@router.post("", status_code=201)
def bind_asset(
    agent_id: uuid.UUID,
    body: BindBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    agent = _get_agent(db, agent_id)
    if body.asset_type not in _ASSET_TYPES:
        raise HTTPException(status_code=422, detail=f"asset_type must be one of {_ASSET_TYPES}")

    # resolve the ref — nothing binds that doesn't exist
    if body.asset_type == "tool":
        stmt = select(ToolRecord).where(ToolRecord.slug == body.asset_ref).order_by(ToolRecord.version.desc())
        if body.version_policy == "pinned" and body.pinned_version:
            stmt = select(ToolRecord).where(ToolRecord.slug == body.asset_ref,
                                            ToolRecord.version == body.pinned_version)
        tool = db.scalars(stmt).first()
        if tool is None:
            raise HTTPException(status_code=404, detail=f"tool {body.asset_ref!r} not found")
        decision = policy.can_bind_tool(tool)
        audit(db, user, "bind_checked", "agent", str(agent.id), {
            "asset_type": "tool", "asset_ref": body.asset_ref,
            "allowed": decision.allowed, "reasons": decision.reasons,
            "rules_version": decision.rules_version,
        })
        if not decision.allowed:
            db.commit()  # DENY audited
            raise HTTPException(status_code=403, detail={"reasons": decision.reasons})
    elif body.asset_type == "prompt":
        if db.scalars(select(PromptPack).where(PromptPack.slug == body.asset_ref)).first() is None:
            raise HTTPException(status_code=404, detail=f"prompt pack {body.asset_ref!r} not found")
    elif body.asset_type == "knowledge":
        try:
            source_id = uuid.UUID(body.asset_ref)
        except ValueError:
            raise HTTPException(status_code=422, detail="knowledge asset_ref must be a source id")
        if db.get(KnowledgeSource, source_id) is None:
            raise HTTPException(status_code=404, detail="knowledge source not found")
    elif body.asset_type == "rag":
        if db.scalars(select(RagPipeline).where(RagPipeline.name == body.asset_ref)).first() is None:
            raise HTTPException(status_code=404, detail=f"rag pipeline {body.asset_ref!r} not found")
    elif body.asset_type == "model":
        entry = db.scalars(select(ModelCatalogEntry).where(
            ModelCatalogEntry.model_ref == body.asset_ref)).first()
        if entry is None or entry.status != "active":
            raise HTTPException(status_code=404, detail=f"active model {body.asset_ref!r} not in catalog")

    exists = db.scalars(select(AssetBinding).where(
        AssetBinding.agent_id == agent.id, AssetBinding.asset_type == body.asset_type,
        AssetBinding.asset_ref == body.asset_ref)).first()
    if exists:
        raise HTTPException(status_code=409, detail="already bound")

    binding = AssetBinding(agent_id=agent.id, created_by=user.id, **body.model_dump())
    db.add(binding)
    db.flush()
    audit(db, user, "asset_bound", "agent", str(agent.id),
          {"asset_type": body.asset_type, "asset_ref": body.asset_ref})
    events.emit("agent.asset_bound", {"agent_id": str(agent.id), "asset_type": body.asset_type,
                                      "asset_ref": body.asset_ref})
    db.commit()
    return _payload(binding)


@router.delete("/{binding_id}")
def unbind_asset(
    agent_id: uuid.UUID,
    binding_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    agent = _get_agent(db, agent_id)
    binding = db.get(AssetBinding, binding_id)
    if binding is None or binding.agent_id != agent.id:
        raise HTTPException(status_code=404, detail="binding not found")
    db.delete(binding)
    audit(db, user, "asset_unbound", "agent", str(agent.id),
          {"asset_type": binding.asset_type, "asset_ref": binding.asset_ref})
    db.commit()
    return {"ok": True}
