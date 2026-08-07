"""Shared asset approval workflow (Pass 3/4): draft → pending_approval →
approved | rejected. Approval steps are polymorphic Approval rows; the actor is
ALWAYS the session user (server-derived). Write-class tools structurally
require DUAL sign-off — Governance Reviewer AND Security/Data Owner.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Approval, ApprovalStatus, Role, User, utcnow


def open_steps(db: Session, resource_type: str, resource_id: uuid.UUID) -> list[Approval]:
    return list(db.scalars(
        select(Approval).where(
            Approval.resource_type == resource_type,
            Approval.resource_id == resource_id,
            Approval.status == ApprovalStatus.pending,
        )
    ).all())


def request_approval(
    db: Session, resource_type: str, resource_id: uuid.UUID,
    steps: list[tuple[str, Role]],
) -> list[Approval]:
    """Create pending approval rows (one per step). Existing pending steps for
    the resource are superseded by rejection-with-note to keep history honest."""
    for stale in open_steps(db, resource_type, resource_id):
        stale.status = ApprovalStatus.rejected
        stale.note = "superseded by a new approval request"
        stale.decided_at = utcnow()
    created = []
    for step, role in steps:
        row = Approval(resource_type=resource_type, resource_id=resource_id,
                       step=step, required_role=role)
        db.add(row)
        created.append(row)
    db.flush()
    return created


def decide(
    db: Session, approval: Approval, user: User, approve: bool, note: str | None,
) -> tuple[bool, bool]:
    """Record a decision. Returns (all_steps_approved, any_rejected) for the
    caller to flip the asset's status. Role + self-decision checks are the
    caller's (router's) responsibility so the HTTP error mapping stays there."""
    approval.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    approval.actor_user_id = user.id  # server-derived, never client-supplied
    approval.note = note
    approval.decided_at = utcnow()
    db.flush()

    siblings = db.scalars(
        select(Approval).where(
            Approval.resource_type == approval.resource_type,
            Approval.resource_id == approval.resource_id,
        )
    ).all()
    # only the current (non-superseded) round matters: pending or decided after
    # the newest request; simplest correct filter is status-based on live rows
    live = [s for s in siblings if s.status != ApprovalStatus.rejected or s.decided_at is None or s.note != "superseded by a new approval request"]
    any_rejected = any(s.status == ApprovalStatus.rejected for s in live)
    all_approved = all(s.status == ApprovalStatus.approved for s in live) and bool(live)
    return all_approved, any_rejected


def serialize(a: Approval) -> dict:
    return {
        "id": str(a.id), "resource_type": a.resource_type, "resource_id": str(a.resource_id),
        "step": a.step, "required_role": a.required_role.value, "status": a.status.value,
        "actor_user_id": str(a.actor_user_id) if a.actor_user_id else None,
        "note": a.note, "requested_at": a.requested_at.isoformat(),
        "decided_at": a.decided_at.isoformat() if isinstance(a.decided_at, datetime) else None,
    }
