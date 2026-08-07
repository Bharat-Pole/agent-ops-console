"""Recommendation endpoints. Generation is role-gated, audited, and versioned:
regeneration creates a NEW DesignRecommendation row and repoints the control
record (create→version doctrine — prior runs are retained, never overwritten).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..audit import audit
from ..db import get_db
from ..models import (
    AgentControlRecord, AgentIntentDocument, DesignRecommendation, IntentStatus, Role, User,
)
from ..auth.deps import require_role
from . import engine as reco_engine
from . import materialize

router = APIRouter(prefix="/api/agents/{agent_id}/recommendation", tags=["recommendation"])

_GENERATE_ROLES = (Role.agent_creator, Role.agent_owner, Role.ai_engineer)


def _get_agent(db: Session, agent_id: uuid.UUID) -> AgentControlRecord:
    agent = db.get(AgentControlRecord, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


def _payload(rec: DesignRecommendation) -> dict:
    return {
        "id": str(rec.id),
        "intent_id": str(rec.intent_id),
        "status": rec.status,
        "engine": rec.engine,
        "items": rec.items,
        "item_states": rec.item_states,
        "validation": rec.validation,
        "summary": (rec.raw_output or {}).get("summary"),
        "missing_information": (rec.raw_output or {}).get("missing_information", []),
        "clarifying_questions": (rec.raw_output or {}).get("clarifying_questions", []),
        "model_id": rec.model_id,
        "prompt_version": rec.prompt_version,
        "created_at": rec.created_at.isoformat(),
    }


@router.post("", status_code=201)
def generate_recommendation(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_GENERATE_ROLES)),
):
    agent = _get_agent(db, agent_id)
    if agent.current_intent_id is None:
        raise HTTPException(status_code=409, detail="no submitted intent — submit the intent document first")
    doc = db.get(AgentIntentDocument, agent.current_intent_id)
    if doc is None:
        raise HTTPException(status_code=409, detail="current intent document not found")

    result = reco_engine.generate(doc.payload, db=db)

    rec = DesignRecommendation(
        intent_id=doc.id,
        status=result["status"],
        engine=result["engine"],
        raw_output=result["raw_output"],
        items=result["items"],
        validation=result["validation"],
        item_states=result["item_states"],
        model_id=result["model_id"],
        prompt_version=result["prompt_version"],
    )
    db.add(rec)
    db.flush()

    agent.design_recommendation_id = rec.id
    doc.status = (
        IntentStatus.recommendation_ready if result["status"] == "ready"
        else IntentStatus.recommendation_failed
    )
    audit(db, user, "recommendation_generated", "agent", str(agent.id), {
        "recommendation_id": str(rec.id), "engine": rec.engine, "status": rec.status,
        "model_id": rec.model_id, "intent_version": doc.version,
        "contradictions": len(rec.validation.get("contradictions", [])),
        "llm_error": rec.validation.get("llm_error"),
    })
    events.emit("agent.recommendation_ready", {"agent_id": str(agent.id), "recommendation_id": str(rec.id)})
    db.commit()
    return _payload(rec)


@router.get("")
def get_recommendation(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_GENERATE_ROLES, Role.governance_reviewer, Role.platform_admin)),
):
    agent = _get_agent(db, agent_id)
    if agent.design_recommendation_id is None:
        raise HTTPException(status_code=404, detail="no recommendation generated yet")
    rec = db.get(DesignRecommendation, agent.design_recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return _payload(rec)


class ItemStateBody(BaseModel):
    state: str  # accepted | rejected | pending


@router.post("/items/{item_id:path}")
def set_item_state(
    agent_id: uuid.UUID,
    item_id: str,
    body: ItemStateBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_GENERATE_ROLES)),
):
    if body.state not in ("accepted", "rejected", "pending"):
        raise HTTPException(status_code=422, detail="state must be accepted | rejected | pending")
    agent = _get_agent(db, agent_id)
    if agent.design_recommendation_id is None:
        raise HTTPException(status_code=404, detail="no recommendation generated yet")
    rec = db.get(DesignRecommendation, agent.design_recommendation_id)
    if rec is None or item_id not in (rec.item_states or {}):
        raise HTTPException(status_code=404, detail=f"unknown recommendation item {item_id!r}")

    # per-item decisions only — there is deliberately no bulk-accept endpoint
    states = dict(rec.item_states)
    states[item_id] = body.state
    rec.item_states = states

    # acceptance → DRAFT materialization (idempotent: recorded on the item)
    materialization: dict | None = None
    if body.state == "accepted" and item_id.startswith("component:"):
        items = [dict(i) for i in rec.items]
        item = next((i for i in items if i["id"] == item_id), None)
        if item is not None and not (item.get("detail") or {}).get("materialized_asset_id"):
            materialization = materialize.materialize_component(db, item, user)
            if materialization.get("materialized"):
                detail = dict(item.get("detail") or {})
                detail["materialized_asset_id"] = materialization["asset_id"]
                detail["materialized_asset_type"] = materialization["asset_type"]
                item["detail"] = detail
                rec.items = items
                audit(db, user, "recommendation_item_materialized", "agent", str(agent.id), {
                    "item_id": item_id, **{k: v for k, v in materialization.items() if k != "materialized"},
                })
                events.emit("asset.materialized", {"agent_id": str(agent.id), **materialization})

    audit(db, user, "recommendation_item_decided", "agent", str(agent.id), {
        "recommendation_id": str(rec.id), "item_id": item_id, "state": body.state,
    })
    db.commit()
    return {"item_id": item_id, "state": body.state, "item_states": rec.item_states,
            "materialization": materialization}
