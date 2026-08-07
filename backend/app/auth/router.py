"""Auth routes: login/logout/me. User administration lands with the Admin
console (Increment F polish); seeding creates the first admin.
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import User
from .deps import current_user_dep
from .security import COOKIE_NAME, issue_session, revoke_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    # plain string by design: strict email validation on LOGIN only enables
    # user enumeration via validation errors (and rejects .local dev domains)
    email: str
    password: str


@router.post("/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.email == body.email.lower())).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        # identical error for unknown user vs bad password (no user enumeration)
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = issue_session(db, user)
    audit(db, user, "login", "user", str(user.id))
    db.commit()
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", path="/",
        # secure=True belongs in the GCP/TLS deployment profile
    )
    return _me_payload(user)


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user_dep),
    platform_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    revoke_session(db, platform_session)
    audit(db, user, "logout", "user", str(user.id))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user_dep)):
    return _me_payload(user)


def _me_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "roles": sorted(r.value for r in user.role_set()),
    }
