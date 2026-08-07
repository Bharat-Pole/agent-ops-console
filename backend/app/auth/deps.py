"""FastAPI dependencies: current user from session cookie, role gating.
Every mutating route in the platform uses these — enforcement is server-side;
the UI merely reflects policy (carried lesson).
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Role, User
from .security import COOKIE_NAME, resolve_session


def current_user_dep(
    db: Session = Depends(get_db),
    platform_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    user = resolve_session(db, platform_session)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def require_role(*roles: Role):
    """Route dependency: the user must hold at least one of the given roles.
    platform_admin does NOT bypass governance-specific roles — admin manages the
    platform, it does not approve agents (separation of duties)."""
    def _dep(user: User = Depends(current_user_dep)) -> User:
        held = user.role_set()
        if not held.intersection(roles):
            raise HTTPException(
                status_code=403,
                detail=f"requires one of roles: {sorted(r.value for r in roles)}",
            )
        return user
    return _dep
