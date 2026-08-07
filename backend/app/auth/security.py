"""Password hashing + server-side sessions with a signed httpOnly cookie.

The cookie carries only a signed session id; the session row (user, expiry,
revocation) lives in the DB — logout and revocation are real, not cookie-side.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import bcrypt
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuthSession, User, utcnow

_signer = URLSafeSerializer(settings.session_secret, salt="platform-session")

COOKIE_NAME = "platform_session"


def hash_password(raw: str) -> str:
    # bcrypt operates on the first 72 bytes; explicit truncation, not silent
    return bcrypt.hashpw(raw.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8")[:72], hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def issue_session(db: Session, user: User) -> str:
    sess = AuthSession(
        user_id=user.id,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(sess)
    db.flush()
    return _signer.dumps(str(sess.id))


def resolve_session(db: Session, cookie_value: str | None) -> User | None:
    if not cookie_value:
        return None
    try:
        sess_id = uuid.UUID(_signer.loads(cookie_value))
    except (BadSignature, ValueError):
        return None
    sess = db.get(AuthSession, sess_id)
    if sess is None or sess.revoked:
        return None
    expires = sess.expires_at
    if expires.tzinfo is None:  # SQLite loses tz info
        from datetime import timezone
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < utcnow():
        return None
    user = db.get(User, sess.user_id)
    return user if user and user.is_active else None


def revoke_session(db: Session, cookie_value: str | None) -> None:
    if not cookie_value:
        return
    try:
        sess_id = uuid.UUID(_signer.loads(cookie_value))
    except (BadSignature, ValueError):
        return
    sess = db.get(AuthSession, sess_id)
    if sess:
        sess.revoked = True
