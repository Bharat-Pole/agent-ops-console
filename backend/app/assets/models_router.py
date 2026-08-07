"""Model catalog — providers/costs/risk mapping (feeds FinOps + routing).
Admin-managed; read for everyone authenticated.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import ModelCatalogEntry, Role, User

router = APIRouter(prefix="/api/models", tags=["models"])


def _payload(m: ModelCatalogEntry) -> dict:
    return {
        "id": str(m.id), "provider": m.provider, "model_ref": m.model_ref, "kind": m.kind,
        "display_name": m.display_name, "cost_per_1k_in": m.cost_per_1k_in,
        "cost_per_1k_out": m.cost_per_1k_out, "latency_note": m.latency_note,
        "max_risk_tier": m.max_risk_tier, "status": m.status, "fallback_ref": m.fallback_ref,
        "created_at": m.created_at.isoformat(),
    }


class ModelBody(BaseModel):
    provider: str = Field(min_length=2, max_length=40)
    model_ref: str = Field(min_length=2, max_length=120)
    kind: str = Field(pattern="^(llm|embedding|judge)$")
    display_name: str = Field(min_length=2, max_length=120)
    cost_per_1k_in: float = 0.0
    cost_per_1k_out: float = 0.0
    latency_note: str = ""
    max_risk_tier: str = Field(default="high", pattern="^(low|medium|high|restricted)$")
    status: str = Field(default="active", pattern="^(active|disabled)$")
    fallback_ref: str | None = None


@router.get("")
def list_models(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    return [_payload(m) for m in db.scalars(select(ModelCatalogEntry).order_by(ModelCatalogEntry.model_ref)).all()]


@router.post("", status_code=201)
def create_model(
    body: ModelBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.platform_admin)),
):
    exists = db.scalars(select(ModelCatalogEntry).where(ModelCatalogEntry.model_ref == body.model_ref)).first()
    if exists:
        raise HTTPException(status_code=409, detail="model_ref already in catalog")
    if body.fallback_ref:
        fb = db.scalars(select(ModelCatalogEntry).where(ModelCatalogEntry.model_ref == body.fallback_ref)).first()
        if fb is None:
            raise HTTPException(status_code=422, detail="fallback_ref must reference an existing catalog entry")
    entry = ModelCatalogEntry(**body.model_dump())
    db.add(entry)
    db.flush()
    audit(db, user, "model_catalog_added", "model", body.model_ref)
    db.commit()
    return _payload(entry)


@router.put("/{model_id}")
def update_model(
    model_id: uuid.UUID,
    body: ModelBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.platform_admin)),
):
    entry = db.get(ModelCatalogEntry, model_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="model not found")
    for key, value in body.model_dump().items():
        setattr(entry, key, value)
    audit(db, user, "model_catalog_updated", "model", entry.model_ref)
    db.commit()
    return _payload(entry)
