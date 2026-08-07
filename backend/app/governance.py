"""Governance mechanics (Increment E): evidence packs, the event-driven
re-certification trigger, the exception register, and governance-config
versioning. All server-side; every action audited.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import events, policy
from .audit import audit
from .auth.deps import current_user_dep, require_role
from .db import SessionLocal, get_db
from .models import (
    AgentControlRecord, Approval, AssetBinding, EvalRun, EvidencePack,
    GovernanceException, LifecycleStatus, PolicyConfigRow, PromptPack, PromptVersion,
    Role, ToolRecord, User, Workflow, WorkflowStatus, WorkflowVersion, utcnow,
)


# ---- evidence packs ---------------------------------------------------------

def assemble_evidence_pack(db: Session, agent: AgentControlRecord, user: User) -> EvidencePack:
    """Frozen snapshot at promotion: what was approved, what was measured."""
    version = db.scalars(
        select(WorkflowVersion).join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .where(Workflow.agent_id == agent.id, WorkflowVersion.status == WorkflowStatus.active)
    ).first()
    latest_eval = db.scalars(select(EvalRun).where(
        EvalRun.agent_id == agent.id, EvalRun.status == "completed")
        .order_by(EvalRun.started_at.desc())).first()
    approvals = db.scalars(select(Approval).where(
        Approval.resource_id == (version.id if version else agent.id))).all()
    config, config_version = policy.active_config(db)

    pack = EvidencePack(agent_id=agent.id, created_by=user.id, content={
        "agent": {"id": str(agent.id), "slug": agent.slug, "name": agent.name,
                  "risk_tier": (agent.confirmed_risk_tier or agent.draft_risk_tier).value
                  if (agent.confirmed_risk_tier or agent.draft_risk_tier) else None,
                  "intent_version": agent.current_intent_version},
        "workflow_version": {"id": str(version.id), "version": version.version,
                             "validation": version.validation} if version else None,
        "eval_run": {"id": str(latest_eval.id),
                     "scorecard": latest_eval.scorecard,  # FROZEN copy
                     "started_at": latest_eval.started_at.isoformat()} if latest_eval else None,
        "approvals": [{"id": str(a.id), "step": a.step, "status": a.status.value,
                       "actor_user_id": str(a.actor_user_id) if a.actor_user_id else None,
                       "decided_at": a.decided_at.isoformat() if a.decided_at else None}
                      for a in approvals],
        "governance_config_version": config_version,
        "assembled_at": utcnow().isoformat(),
    })
    db.add(pack)
    db.flush()
    return pack


# ---- re-certification trigger (Pass 4, event-driven) ------------------------

def _refs_for_approved_asset(db: Session, asset_type: str, asset_id: uuid.UUID) -> list[tuple[str, str]]:
    """→ [(binding asset_type, asset_ref)] the approval affects."""
    if asset_type == "tool":
        tool = db.get(ToolRecord, asset_id)
        return [("tool", tool.slug)] if tool else []
    if asset_type == "prompt_version":
        version = db.get(PromptVersion, asset_id)
        if version is None:
            return []
        pack = db.get(PromptPack, version.pack_id)
        return [("prompt", pack.slug)] if pack else []
    return []  # workflow_version approvals are the agent's own artifact — no re-cert


def _agents_using_ref(db: Session, asset_type: str, asset_ref: str) -> set[uuid.UUID]:
    """Usage = explicit bindings AND references inside ACTIVE workflow graphs
    (fresh-resolve reaches both paths, so re-certification must too)."""
    agent_ids: set[uuid.UUID] = set()
    for binding in db.scalars(select(AssetBinding).where(
            AssetBinding.asset_type == asset_type, AssetBinding.asset_ref == asset_ref)).all():
        agent_ids.add(binding.agent_id)
    config_key = "pack_ref" if asset_type == "prompt" else "tool_ref"
    active_versions = db.scalars(
        select(WorkflowVersion).where(WorkflowVersion.status == WorkflowStatus.active)).all()
    for version in active_versions:
        for node in (version.graph or {}).get("nodes", []):
            if (node.get("config") or {}).get(config_key) == asset_ref:
                workflow = db.get(Workflow, version.workflow_id)
                if workflow:
                    agent_ids.add(workflow.agent_id)
                break
    return agent_ids


def _on_asset_approved(payload: dict) -> None:
    """A newer version of a used asset was approved → every PRODUCTION agent
    using it moves to Needs Review (fresh-resolve means behavior changed).
    Frozen deployments keep serving their pinned manifests — the flag is about
    the NEXT promotion, not the running snapshot."""
    with SessionLocal() as db:
        refs = _refs_for_approved_asset(db, payload.get("type", ""), uuid.UUID(payload["id"]))
        for asset_type, asset_ref in refs:
            for agent_id in _agents_using_ref(db, asset_type, asset_ref):
                agent = db.get(AgentControlRecord, agent_id)
                if agent is None or agent.lifecycle_status != LifecycleStatus.production:
                    continue
                agent.lifecycle_status = LifecycleStatus.needs_review
                agent.row_version += 1
                audit(db, None, "recertification_triggered", "agent", str(agent.id), {
                    "asset_type": asset_type, "asset_ref": asset_ref,
                    "approved_resource": payload,
                    "note": "used asset changed — production certification is stale",
                })
                events.emit("agent.needs_review", {"agent_id": str(agent.id),
                                                   "asset_ref": asset_ref})
        db.commit()


def register_event_handlers() -> None:
    events.subscribe("asset.approved", _on_asset_approved)


# ---- exception register + governance config ---------------------------------

router = APIRouter(prefix="/api/governance", tags=["governance"])


class ExceptionBody(BaseModel):
    agent_id: uuid.UUID
    reason: str = Field(min_length=10)
    expires_days: int = Field(default=30, ge=1, le=180)  # hard cap (Pass 4)


@router.post("/exceptions", status_code=201)
def create_exception(
    body: ExceptionBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.governance_reviewer)),
):
    agent = db.get(AgentControlRecord, body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    exc = GovernanceException(
        agent_id=agent.id, reason=body.reason,
        expires_at=utcnow() + timedelta(days=body.expires_days), created_by=user.id,
    )
    db.add(exc)
    db.flush()
    audit(db, user, "governance_exception_created", "agent", str(agent.id), {
        "exception_id": str(exc.id), "reason": body.reason, "expires_days": body.expires_days,
    })
    db.commit()
    return {"id": str(exc.id), "agent_id": str(agent.id), "reason": exc.reason,
            "expires_at": exc.expires_at.isoformat(), "status": exc.status}


@router.get("/exceptions")
def list_exceptions(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    rows = db.scalars(select(GovernanceException)
                      .order_by(GovernanceException.created_at.desc())).all()
    return [{"id": str(e.id), "agent_id": str(e.agent_id), "reason": e.reason,
             "expires_at": e.expires_at.isoformat(), "status": e.status,
             "created_at": e.created_at.isoformat()} for e in rows]


@router.post("/exceptions/{exception_id}/revoke")
def revoke_exception(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.governance_reviewer, Role.platform_admin)),
):
    exc = db.get(GovernanceException, exception_id)
    if exc is None:
        raise HTTPException(status_code=404, detail="exception not found")
    exc.status = "revoked"
    audit(db, user, "governance_exception_revoked", "agent", str(exc.agent_id),
          {"exception_id": str(exc.id)})
    db.commit()
    return {"id": str(exc.id), "status": exc.status}


@router.get("/evidence/{agent_id}")
def list_evidence(agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    rows = db.scalars(select(EvidencePack).where(EvidencePack.agent_id == agent_id)
                      .order_by(EvidencePack.created_at.desc())).all()
    return [{"id": str(p.id), "content": p.content, "created_at": p.created_at.isoformat()}
            for p in rows]


@router.get("/config")
def get_config(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    config, version = policy.active_config(db)
    return {"version": version, "config": config}


class ConfigBody(BaseModel):
    config: dict


@router.put("/config")
def put_config(
    body: ConfigBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.platform_admin)),
):
    """New config VERSION (prior versions retained; decisions cite versions)."""
    unknown = set(body.config) - set(policy.DEFAULT_GOVERNANCE_CONFIG)
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown config keys: {sorted(unknown)}")
    latest = db.scalars(select(PolicyConfigRow).order_by(PolicyConfigRow.version.desc())).first()
    for row in db.scalars(select(PolicyConfigRow).where(PolicyConfigRow.active.is_(True))).all():
        row.active = False
    new = PolicyConfigRow(version=(latest.version + 1) if latest else 1,
                          config=body.config, created_by=user.id)
    db.add(new)
    db.flush()
    audit(db, user, "governance_config_updated", "policy_config", str(new.version),
          {"config": body.config})
    db.commit()
    return {"version": new.version, "config": {**policy.DEFAULT_GOVERNANCE_CONFIG, **body.config}}
