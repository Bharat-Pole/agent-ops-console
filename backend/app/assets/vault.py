"""Secrets vault — evolved from agent_forge's vault with the carried lessons:
values are encrypted at rest (Fernet, app key) and NEVER leave the server.
The API returns names + metadata only. Consumers (tool try-out, MCP discovery,
engine) resolve values server-side from persisted config — never from caller
input.
"""
from __future__ import annotations

import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth.deps import require_role
from ..config import settings
from ..db import get_db
from ..models import Role, SecretRecord, User, utcnow

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,63}$")

_VAULT_ROLES = (Role.ai_engineer, Role.platform_admin, Role.security_data_owner)


def _fernet() -> Fernet:
    if settings.vault_key:
        return Fernet(settings.vault_key.encode())
    # dev fallback: derive from session_secret (documented in config.py)
    digest = hashlib.sha256(f"vault:{settings.session_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(raw: str) -> str:
    return _fernet().encrypt(raw.encode()).decode()


def resolve_secret(db: Session, name: str) -> str | None:
    """Server-side only. No route returns this."""
    rec = db.scalars(select(SecretRecord).where(SecretRecord.name == name)).first()
    if rec is None:
        return None
    try:
        return _fernet().decrypt(rec.encrypted_value.encode()).decode()
    except InvalidToken:
        return None


router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class SecretBody(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    value: str = Field(min_length=1, max_length=8192)


def _meta(rec: SecretRecord) -> dict:
    return {
        "name": rec.name,
        "created_at": rec.created_at.isoformat(),
        "updated_at": rec.updated_at.isoformat(),
        # value intentionally absent — names only, always
    }


@router.get("")
def list_secrets(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(*_VAULT_ROLES)),
):
    rows = db.scalars(select(SecretRecord).order_by(SecretRecord.name)).all()
    return [_meta(r) for r in rows]


@router.put("", status_code=201)
def put_secret(
    body: SecretBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.ai_engineer, Role.platform_admin)),
):
    if not _NAME_RE.match(body.name):
        raise HTTPException(status_code=422, detail="name must match ^[a-z0-9][a-z0-9_.-]{1,63}$")
    rec = db.scalars(select(SecretRecord).where(SecretRecord.name == body.name)).first()
    action = "secret_rotated" if rec else "secret_created"
    if rec is None:
        rec = SecretRecord(name=body.name, encrypted_value=encrypt_value(body.value), created_by=user.id)
        db.add(rec)
    else:
        rec.encrypted_value = encrypt_value(body.value)
        rec.updated_at = utcnow()
    db.flush()
    audit(db, user, action, "secret", body.name)  # value never audited
    db.commit()
    return _meta(rec)


@router.delete("/{name}")
def delete_secret(
    name: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.platform_admin)),
):
    rec = db.scalars(select(SecretRecord).where(SecretRecord.name == name)).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="secret not found")
    db.delete(rec)
    audit(db, user, "secret_deleted", "secret", name)
    db.commit()
    return {"ok": True}
