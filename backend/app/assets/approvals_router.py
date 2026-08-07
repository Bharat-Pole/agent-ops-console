"""Approval queue (Pass 4 mechanics landing with the assets that need them).
Decisions are role-gated per step, actor server-derived, every decision
audited, and NO bulk endpoint exists. Asset status flips only when every step
of the current round is approved; any rejection rejects the asset.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..audit import audit
from ..auth.deps import current_user_dep
from ..db import get_db
from ..models import (
    Approval, ApprovalStatus, AssetStatus, PromptVersion, ToolRecord, User,
    WorkflowStatus, WorkflowVersion, utcnow,
)
from . import workflow

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    db: Session = Depends(get_db),
    user: User = Depends(current_user_dep),
    status: str = Query(default="pending"),
    mine: bool = Query(default=True, description="only steps my roles can decide"),
):
    stmt = select(Approval).order_by(Approval.requested_at.desc()).limit(200)
    if status:
        stmt = stmt.where(Approval.status == ApprovalStatus(status))
    rows = db.scalars(stmt).all()
    if mine:
        my_roles = user.role_set()
        rows = [r for r in rows if r.required_role in my_roles]
    return [workflow.serialize(r) for r in rows]


class DecisionBody(BaseModel):
    approve: bool
    note: str | None = None


def _flip_asset(db: Session, resource_type: str, resource_id: uuid.UUID,
                all_approved: bool, any_rejected: bool) -> str | None:
    """Apply the round outcome to the asset. Returns the new status value."""
    if resource_type == "tool":
        tool = db.get(ToolRecord, resource_id)
        if tool is None:
            return None
        if any_rejected:
            tool.status = AssetStatus.rejected
        elif all_approved:
            tool.status = AssetStatus.approved
            # supersede previously-approved versions of the same slug
            for prior in db.scalars(select(ToolRecord).where(
                    ToolRecord.slug == tool.slug, ToolRecord.id != tool.id,
                    ToolRecord.status == AssetStatus.approved)).all():
                prior.status = AssetStatus.deprecated
                prior.superseded_by = tool.id
        tool.updated_at = utcnow()
        return tool.status.value
    if resource_type == "workflow_version":
        version = db.get(WorkflowVersion, resource_id)
        if version is None:
            return None
        if any_rejected:
            version.status = WorkflowStatus.rejected
        elif all_approved:
            version.status = WorkflowStatus.approved
        version.updated_at = utcnow()
        return version.status.value
    if resource_type == "prompt_version":
        version = db.get(PromptVersion, resource_id)
        if version is None:
            return None
        if any_rejected:
            version.status = AssetStatus.rejected
        elif all_approved:
            version.status = AssetStatus.approved
            for prior in db.scalars(select(PromptVersion).where(
                    PromptVersion.pack_id == version.pack_id, PromptVersion.id != version.id,
                    PromptVersion.status == AssetStatus.approved)).all():
                prior.status = AssetStatus.deprecated
        return version.status.value
    return None


@router.post("/{approval_id}/decide")
def decide_approval(
    approval_id: uuid.UUID,
    body: DecisionBody,
    db: Session = Depends(get_db),
    user: User = Depends(current_user_dep),
):
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status_code=409, detail=f"already decided ({approval.status.value})")
    if approval.required_role not in user.role_set():
        raise HTTPException(status_code=403, detail=f"requires role {approval.required_role.value}")

    # Dual sign-off means two PEOPLE, not two roles held by one person. A
    # multi-role account (e.g. the all-roles admin) can decide any single step,
    # but cannot be both signatures on the same resource.
    already_signed = db.scalars(select(Approval).where(
        Approval.resource_type == approval.resource_type,
        Approval.resource_id == approval.resource_id,
        Approval.id != approval.id,
        Approval.status == ApprovalStatus.approved,
        Approval.actor_user_id == user.id)).first()
    if already_signed is not None:
        raise HTTPException(
            status_code=403,
            detail=(f"you already signed the {already_signed.step!r} step — dual sign-off "
                    "requires a second, distinct approver"),
        )

    all_approved, any_rejected = workflow.decide(db, approval, user, body.approve, body.note)
    new_status = None
    if all_approved or any_rejected:
        new_status = _flip_asset(db, approval.resource_type, approval.resource_id,
                                 all_approved, any_rejected)

    audit(db, user, "approval_decided", approval.resource_type, str(approval.resource_id), {
        "approval_id": str(approval.id), "step": approval.step,
        "approve": body.approve, "asset_status": new_status,
    })
    db.commit()
    if new_status == "approved":
        # emitted AFTER commit: the re-certification handler opens its own
        # session and must see the approved state (and avoid SQLite lock races)
        events.emit("asset.approved", {"type": approval.resource_type, "id": str(approval.resource_id)})
    result = workflow.serialize(approval)
    result["asset_status"] = new_status
    return result
