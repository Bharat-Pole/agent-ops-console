"""Seed the first platform admin + demo users (one per key role) so a fresh
local install is immediately usable. Idempotent. Run:
    python -m app.seed
Passwords come from env (PLATFORM_SEED_PASSWORD) or default to 'changeme!' for
local dev — the login page surfaces the seeded emails in dev builds only.
"""
from __future__ import annotations

import os

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import ModelCatalogEntry, Role, RoleAssignment, User
from .auth.security import hash_password

# Default model catalog (admin-editable afterwards). Prices are per-1k tokens
# and MUST be reviewed against current provider pricing before FinOps use.
DEFAULT_MODELS: list[dict] = [
    {"provider": "gemini", "model_ref": "gemini-flash-latest", "kind": "llm",
     "display_name": "Gemini Flash (latest)", "cost_per_1k_in": 0.0003, "cost_per_1k_out": 0.0025,
     "latency_note": "fast", "max_risk_tier": "high"},
    {"provider": "gemini", "model_ref": "gemini-embedding-001", "kind": "embedding",
     "display_name": "Gemini Embedding 001", "cost_per_1k_in": 0.00015, "cost_per_1k_out": 0.0,
     "latency_note": "fast", "max_risk_tier": "restricted"},
]

SEED_USERS: list[tuple[str, str, list[Role]]] = [
    # The admin account holds EVERY role so one person can drive the whole
    # journey without switching logins. Note what this does and does not
    # change: `require_role` still checks real role assignments — admin is not
    # special-cased anywhere — this account simply has them all. Dual sign-off
    # stays genuinely dual because approvals require two DISTINCT actors.
    ("admin@platform.local", "Platform Admin", list(Role)),
    ("creator@platform.local", "Agent Creator", [Role.agent_creator]),
    ("owner@platform.local", "Agent Owner", [Role.agent_owner]),
    ("engineer@platform.local", "AI Engineer", [Role.ai_engineer]),
    ("governance@platform.local", "Governance Reviewer", [Role.governance_reviewer]),
    ("security@platform.local", "Security / Data Owner", [Role.security_data_owner]),
]


def seed() -> None:
    Base.metadata.create_all(engine)
    password = os.getenv("PLATFORM_SEED_PASSWORD", "changeme!")
    with SessionLocal() as db:
        for email, name, roles in SEED_USERS:
            user = db.scalars(select(User).where(User.email == email)).first()
            if user is None:
                user = User(email=email, display_name=name, password_hash=hash_password(password))
                db.add(user)
                db.flush()
            for role in roles:
                if role not in user.role_set():
                    db.add(RoleAssignment(user_id=user.id, role=role))
        for spec in DEFAULT_MODELS:
            if db.scalars(select(ModelCatalogEntry).where(
                    ModelCatalogEntry.model_ref == spec["model_ref"])).first() is None:
                db.add(ModelCatalogEntry(**spec))
        # governance config v1 (Increment E) — admin edits create new versions
        from .models import PolicyConfigRow
        from .policy import DEFAULT_GOVERNANCE_CONFIG
        if db.scalars(select(PolicyConfigRow)).first() is None:
            db.add(PolicyConfigRow(version=1, config=DEFAULT_GOVERNANCE_CONFIG))
        db.commit()
    print(f"seeded {len(SEED_USERS)} users (password from PLATFORM_SEED_PASSWORD or default)")


if __name__ == "__main__":
    seed()
