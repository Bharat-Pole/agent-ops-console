"""Append-only audit writer + read API. The actor is ALWAYS the authenticated
user passed in by the caller (derived from the session) — there is no code path
that accepts a client-supplied actor.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, User


def audit(db: Session, actor: User | None, action: str, resource_type: str,
          resource_id: str, detail: dict | None = None) -> None:
    label = f"{actor.email} [{','.join(sorted(r.value for r in actor.role_set()))}]" if actor else "system"
    db.add(AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_label=label,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        detail=detail or {},
    ))


router = APIRouter(prefix="/api/audit", tags=["audit"])


# NOTE: session-auth is attached at include time in main.py
# (dependencies=[Depends(current_user_dep)]) — every route in this router
# requires a logged-in user.
@router.get("")
def list_audit(
    db: Session = Depends(get_db),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id, "at": r.at.isoformat(), "actor": r.actor_label, "action": r.action,
            "resource_type": r.resource_type, "resource_id": r.resource_id, "detail": r.detail,
        }
        for r in rows
    ]
