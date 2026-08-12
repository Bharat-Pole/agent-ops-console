"""A2A endpoints: agent card CRUD/versioning, discovery, handoff validation.

Every mutation is session-authenticated, role-checked, and audited through the
platform's machinery — this module owns no identity, no audit table, and no
approval subsystem of its own.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..assets import workflow as approval_workflow
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import AgentCard, AgentControlRecord, AssetStatus, Role, User, utcnow
from . import service

router = APIRouter(prefix="/api/a2a", tags=["a2a"])

_EDIT_ROLES = (Role.agent_creator, Role.agent_owner, Role.ai_engineer, Role.platform_admin)
_TIERS = ("standardized", "advanced")
_FAILURE_BEHAVIORS = ("fail_fast", "retry", "escalate")


def _payload(db: Session, card: AgentCard, with_readiness: bool = True) -> dict:
    agent = db.get(AgentControlRecord, card.agent_id)
    out = {
        "id": str(card.id),
        "agent_id": str(card.agent_id),
        "agent_slug": agent.slug if agent else None,
        "agent_name": agent.name if agent else None,
        "version": card.version,
        "status": card.status.value,
        "description": card.description,
        "capability_tier": card.capability_tier,
        "discovery_only": card.discovery_only,
        "message_task_format": card.message_task_format,
        "artifact_exchange": card.artifact_exchange,
        "artifact_format": card.artifact_format,
        "supported_tasks": card.supported_tasks,
        "skills": card.skills,
        "input_schema": card.input_schema,
        "output_schema": card.output_schema,
        "handoff_rules": card.handoff_rules,
        "authn_methods": card.authn_methods,
        "authorized_callers": card.authorized_callers,
        "timeout_seconds": card.timeout_seconds,
        "failure_behavior": card.failure_behavior,
        "superseded_by": str(card.superseded_by) if card.superseded_by else None,
        "created_at": card.created_at.isoformat(),
        "updated_at": card.updated_at.isoformat(),
    }
    if with_readiness:
        out["readiness"] = service.compute_readiness(db, card).as_dict()
    return out


class CardBody(BaseModel):
    description: str = ""
    capability_tier: str = Field(default="standardized")
    discovery_only: bool = True
    message_task_format: str | None = None
    artifact_exchange: bool = False
    artifact_format: str | None = None
    supported_tasks: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    handoff_rules: dict = Field(default_factory=dict)
    authn_methods: list[str] = Field(default_factory=list)
    authorized_callers: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    failure_behavior: str = "fail_fast"


def _validate(body: CardBody) -> None:
    if body.capability_tier not in _TIERS:
        raise HTTPException(status_code=422, detail=f"capability_tier must be one of {_TIERS}")
    if body.failure_behavior not in _FAILURE_BEHAVIORS:
        raise HTTPException(status_code=422,
                            detail=f"failure_behavior must be one of {_FAILURE_BEHAVIORS}")
    # the source branch enforced this pairing as a DB CHECK; keeping it as an
    # application rule keeps the column types dialect-portable
    if body.capability_tier == "standardized" and not body.discovery_only:
        raise HTTPException(
            status_code=422,
            detail="standardized tier is discovery-only — set discovery_only=true or use the advanced tier")
    if body.artifact_exchange and body.discovery_only:
        raise HTTPException(
            status_code=422,
            detail="a discovery-only card cannot declare artifact_exchange")
    if body.artifact_exchange and not body.artifact_format:
        raise HTTPException(status_code=422,
                            detail="artifact_format is required when artifact_exchange is true")


def _get_agent(db: Session, agent_id: uuid.UUID) -> AgentControlRecord:
    agent = db.get(AgentControlRecord, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


@router.get("/agent-cards")
def list_cards(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    """Every card, any status — the operator view (not discovery)."""
    rows = db.scalars(select(AgentCard).order_by(
        AgentCard.agent_id, AgentCard.version.desc())).all()
    return [_payload(db, c) for c in rows]


@router.get("/discover")
def discover(
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
    skill: str | None = Query(default=None),
    task: str | None = Query(default=None),
):
    """Only approved cards whose agent is genuinely ready — readiness derived
    from lifecycle, workflow, and deployment state at request time."""
    return [
        {**_payload(db, card, with_readiness=False), "readiness": readiness.as_dict()}
        for card, readiness in service.discoverable_cards(db, skill=skill, task=task)
    ]


@router.post("/agents/{agent_id}/card", status_code=201)
def create_card(
    agent_id: uuid.UUID,
    body: CardBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    agent = _get_agent(db, agent_id)
    _validate(body)
    if service.current_card(db, agent.id) is not None:
        raise HTTPException(
            status_code=409,
            detail="this agent already has a card — create a new version instead")
    card = AgentCard(agent_id=agent.id, version=1, created_by=user.id, **body.model_dump())
    db.add(card)
    db.flush()
    audit(db, user, "a2a_card_created", "agent_card", str(card.id),
          {"agent_id": str(agent.id), "version": 1})
    db.commit()
    return _payload(db, card)


@router.get("/agents/{agent_id}/card")
def get_card(agent_id: uuid.UUID, db: Session = Depends(get_db),
             _: User = Depends(current_user_dep)):
    card = service.current_card(db, agent_id)
    if card is None:
        raise HTTPException(status_code=404, detail="no agent card for this agent")
    return _payload(db, card)


@router.put("/cards/{card_id}")
def update_card(
    card_id: uuid.UUID,
    body: CardBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    card = db.get(AgentCard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    if card.status not in (AssetStatus.draft, AssetStatus.rejected):
        raise HTTPException(
            status_code=409,
            detail=f"card is {card.status.value} — create a new version to change it")
    _validate(body)
    for key, value in body.model_dump().items():
        setattr(card, key, value)
    card.status = AssetStatus.draft
    card.updated_at = utcnow()
    audit(db, user, "a2a_card_updated", "agent_card", str(card.id), {"version": card.version})
    db.commit()
    return _payload(db, card)


@router.post("/cards/{card_id}/new-version", status_code=201)
def new_version(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    """Approved cards are immutable; changing one forks a new draft version."""
    card = db.get(AgentCard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    newest = service.current_card(db, card.agent_id)
    draft = AgentCard(
        agent_id=card.agent_id, version=newest.version + 1, created_by=user.id,
        description=card.description, capability_tier=card.capability_tier,
        discovery_only=card.discovery_only, message_task_format=card.message_task_format,
        artifact_exchange=card.artifact_exchange, artifact_format=card.artifact_format,
        supported_tasks=card.supported_tasks, skills=card.skills,
        input_schema=card.input_schema, output_schema=card.output_schema,
        handoff_rules=card.handoff_rules, authn_methods=card.authn_methods,
        authorized_callers=card.authorized_callers, timeout_seconds=card.timeout_seconds,
        failure_behavior=card.failure_behavior,
    )
    db.add(draft)
    db.flush()
    audit(db, user, "a2a_card_version_created", "agent_card", str(draft.id),
          {"agent_id": str(card.agent_id), "version": draft.version})
    db.commit()
    return _payload(db, draft)


@router.post("/cards/{card_id}/submit")
def submit_card(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    """Publication runs through the platform approval queue — approving the
    card is what 'published' means here."""
    card = db.get(AgentCard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    if card.status != AssetStatus.draft:
        raise HTTPException(status_code=409, detail=f"cannot submit from status {card.status.value}")
    approval_workflow.request_approval(
        db, "agent_card", card.id, [("governance_review", Role.governance_reviewer)])
    card.status = AssetStatus.pending_approval
    audit(db, user, "a2a_card_submitted_for_approval", "agent_card", str(card.id),
          {"version": card.version})
    events.emit("asset.submitted", {"type": "agent_card", "id": str(card.id)})
    db.commit()
    return _payload(db, card)


class HandoffQuery(BaseModel):
    source_agent_slug: str
    target_agent_slug: str
    task: str
    required_skill: str | None = None


@router.post("/handoffs/validate")
def validate_handoff(
    body: HandoffQuery,
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
):
    """READ-ONLY. Answers whether a handoff would be permitted and why.
    Nothing is executed, nothing is written — runtime A2A execution is
    deliberately out of scope."""
    return service.validate_handoff(
        db, body.source_agent_slug, body.target_agent_slug, body.task, body.required_skill,
    ).as_dict()
