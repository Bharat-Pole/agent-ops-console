"""Registry: agent control records, lifecycle transitions, intent drafts &
immutable submissions. Every mutation is session-authenticated, role-checked
server-side, audited, and (for transitions) emits a domain event.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import events, policy
from ..audit import audit
from ..db import get_db
from ..intent import pii as intent_pii
from ..intent import schema as intent_schema
from ..models import (
    AgentControlRecord, AgentIntentDocument, AgentIntentDraft, IntentStatus,
    LifecycleStatus, RiskTier, Role, User, utcnow,
)
from ..auth.deps import current_user_dep, require_role

router = APIRouter(prefix="/api/agents", tags=["registry"])


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "agent"
    return f"{s}-{uuid.uuid4().hex[:6]}"


def _agent_payload(a: AgentControlRecord) -> dict:
    return {
        "id": str(a.id), "slug": a.slug, "name": a.name, "description": a.description,
        "intent_type": a.intent_type, "lifecycle_status": a.lifecycle_status.value,
        "business_owner": a.business_owner, "technical_owner": a.technical_owner,
        "governance_owner": a.governance_owner, "cost_center": a.cost_center,
        "draft_risk_tier": a.draft_risk_tier.value if a.draft_risk_tier else None,
        "confirmed_risk_tier": a.confirmed_risk_tier.value if a.confirmed_risk_tier else None,
        "current_intent_id": str(a.current_intent_id) if a.current_intent_id else None,
        "current_intent_version": a.current_intent_version,
        "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(),
    }


def _get_agent(db: Session, agent_id: uuid.UUID) -> AgentControlRecord:
    agent = db.get(AgentControlRecord, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


# ---- catalog ----------------------------------------------------------------

@router.get("")
def list_agents(
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    stmt = select(AgentControlRecord).order_by(AgentControlRecord.updated_at.desc())
    if status:
        stmt = stmt.where(AgentControlRecord.lifecycle_status == LifecycleStatus(status))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(AgentControlRecord.name).like(like))
    return [_agent_payload(a) for a in db.scalars(stmt).all()]


class CreateAgentBody(BaseModel):
    name: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _-]{2,79}$")
    description: str = ""


@router.post("", status_code=201)
def create_agent(
    body: CreateAgentBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.agent_creator, Role.agent_owner, Role.platform_admin)),
):
    # uniqueness re-verified transactionally (name, case-insensitive)
    exists = db.scalars(
        select(AgentControlRecord).where(func.lower(AgentControlRecord.name) == body.name.lower())
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="an agent with this name already exists")
    agent = AgentControlRecord(
        slug=_slugify(body.name), name=body.name, description=body.description, created_by=user.id,
    )
    db.add(agent)
    db.flush()
    audit(db, user, "agent_created", "agent", str(agent.id), {"name": agent.name})
    db.commit()
    return _agent_payload(agent)


@router.get("/{agent_id}")
def get_agent(agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    return _agent_payload(_get_agent(db, agent_id))


class UpdateAgentBody(BaseModel):
    description: str | None = None
    business_owner: str | None = None
    technical_owner: str | None = None
    governance_owner: str | None = None
    support_group: str | None = None
    cost_center: str | None = None


@router.patch("/{agent_id}")
def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.agent_creator, Role.agent_owner, Role.platform_admin)),
):
    """Ownership/metadata fields only — lifecycle, intent, and risk move
    through their own governed endpoints."""
    agent = _get_agent(db, agent_id)
    changed = {k: v for k, v in body.model_dump().items() if v is not None}
    for key, value in changed.items():
        setattr(agent, key, value)
    if changed:
        agent.updated_at = utcnow()
        audit(db, user, "agent_updated", "agent", str(agent.id), {"fields": sorted(changed)})
        db.commit()
    return _agent_payload(agent)


# ---- lifecycle --------------------------------------------------------------

class TransitionBody(BaseModel):
    to: LifecycleStatus
    note: str | None = None


@router.post("/{agent_id}/transition")
def transition(
    agent_id: uuid.UUID,
    body: TransitionBody,
    db: Session = Depends(get_db),
    user: User = Depends(current_user_dep),
):
    agent = _get_agent(db, agent_id)
    decision = policy.check_transition(db, agent, body.to, user)
    audit(db, user, "transition_checked", "agent", str(agent.id), {
        "from": agent.lifecycle_status.value, "to": body.to.value,
        "allowed": decision.allowed, "reasons": decision.reasons,
        "rules_version": decision.rules_version,
    })
    if not decision.allowed:
        db.commit()  # the DENY is audited even though the transition fails
        raise HTTPException(status_code=403, detail={"reasons": decision.reasons})
    prev = agent.lifecycle_status
    agent.lifecycle_status = body.to
    agent.row_version += 1
    audit(db, user, "lifecycle_transition", "agent", str(agent.id), {
        "from": prev.value, "to": body.to.value, "note": body.note,
    })
    if body.to == LifecycleStatus.production:
        from ..governance import assemble_evidence_pack
        pack = assemble_evidence_pack(db, agent, user)
        audit(db, user, "evidence_pack_assembled", "agent", str(agent.id),
              {"evidence_pack_id": str(pack.id)})
    events.emit("agent.lifecycle_changed", {
        "agent_id": str(agent.id), "from": prev.value, "to": body.to.value, "actor": str(user.id),
    })
    db.commit()
    return _agent_payload(agent)


# ---- intent: mutable draft vs immutable submission --------------------------

class DraftBody(BaseModel):
    payload: dict


@router.put("/{agent_id}/intent/draft")
def upsert_intent_draft(
    agent_id: uuid.UUID,
    body: DraftBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.agent_creator, Role.agent_owner, Role.ai_engineer)),
):
    agent = _get_agent(db, agent_id)
    draft = db.scalars(
        select(AgentIntentDraft).where(AgentIntentDraft.agent_id == agent.id)
    ).first()
    if draft is None:
        draft = AgentIntentDraft(agent_id=agent.id, created_by=user.id, payload=body.payload)
        db.add(draft)
    else:
        draft.payload = body.payload
        draft.updated_at = utcnow()
    db.commit()
    return {"draft_id": str(draft.id), "updated_at": draft.updated_at.isoformat()}


@router.post("/{agent_id}/intent/submit", status_code=201)
def submit_intent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.agent_creator, Role.agent_owner)),
):
    """Freeze the current draft as an immutable AgentIntentDocument version.
    Prior versions get status=superseded (status field only — payloads are
    never touched). Full 6-group cross-field validation (app.intent.schema)
    gates the freeze; PII flags (local detector, flag-only) are computed BEFORE
    any LLM ever sees the text and stored on the document."""
    agent = _get_agent(db, agent_id)
    draft = db.scalars(select(AgentIntentDraft).where(AgentIntentDraft.agent_id == agent.id)).first()
    if draft is None or not draft.payload:
        raise HTTPException(status_code=422, detail="no intent draft to submit")

    payload = draft.payload
    normalized = intent_schema.normalize(payload)
    verdict = intent_schema.validate(normalized)
    if not verdict.ok:
        raise HTTPException(status_code=422, detail="; ".join(verdict.errors))
    pii_flags = intent_pii.scan_fields(normalized.free_text())
    risk = normalized.risk_tier

    prior = db.scalars(
        select(AgentIntentDocument)
        .where(AgentIntentDocument.agent_id == agent.id)
        .order_by(AgentIntentDocument.version.desc())
    ).all()
    next_version = (prior[0].version + 1) if prior else 1
    doc = AgentIntentDocument(
        agent_id=agent.id, version=next_version, payload=payload, created_by=user.id,
        pii_flags=pii_flags,
        validation={"warnings": verdict.warnings, "rules_version": verdict.rules_version},
    )
    db.add(doc)
    db.flush()
    for p in prior:
        if p.status != IntentStatus.superseded:
            p.status = IntentStatus.superseded
            p.superseded_by = doc.id
    agent.current_intent_id = doc.id
    agent.current_intent_version = doc.version
    if risk in {t.value for t in RiskTier}:
        agent.draft_risk_tier = RiskTier(risk)
    audit(db, user, "intent_submitted", "agent", str(agent.id), {
        "version": doc.version, "warnings": len(verdict.warnings), "pii_flags": len(pii_flags),
    })
    events.emit("agent.intent_submitted", {"agent_id": str(agent.id), "version": doc.version})
    db.commit()
    return {
        "intent_id": str(doc.id), "version": doc.version, "status": doc.status.value,
        "warnings": verdict.warnings, "pii_flags": pii_flags,
    }


@router.get("/{agent_id}/intent/draft")
def get_intent_draft(
    agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep),
):
    agent = _get_agent(db, agent_id)
    draft = db.scalars(select(AgentIntentDraft).where(AgentIntentDraft.agent_id == agent.id)).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="no intent draft")
    return {"draft_id": str(draft.id), "payload": draft.payload, "updated_at": draft.updated_at.isoformat()}


@router.get("/{agent_id}/intent")
def get_current_intent(
    agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep),
):
    agent = _get_agent(db, agent_id)
    if agent.current_intent_id is None:
        raise HTTPException(status_code=404, detail="no submitted intent")
    doc = db.get(AgentIntentDocument, agent.current_intent_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="intent document not found")
    return {
        "intent_id": str(doc.id), "version": doc.version, "status": doc.status.value,
        "payload": doc.payload, "pii_flags": doc.pii_flags, "validation": doc.validation,
        "submitted_at": doc.submitted_at.isoformat(),
    }
