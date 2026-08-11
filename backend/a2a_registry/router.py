from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AgentCard, AgentCardVersion, AuditEvent, HandoffApprovalRequest
from .schemas import ApprovalDecision, CardInput, CardUpdate, EligibilityInput, HandoffValidationRequest
from .security import require_write_key
from .service import (
    attest_eligibility,
    card_response,
    change_status,
    create_card,
    decide_handoff_approval,
    get_card_or_404,
    handoff_approval_response,
    is_eligible,
    latest_attestation,
    publish_card,
    update_card,
    validate_handoff,
)

router = APIRouter(prefix="/a2a/v1", tags=["A2A agent cards"])


@router.post("/agent-cards", status_code=201)
def create(payload: CardInput, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    return card_response(db, create_card(db, payload, actor))


@router.patch("/agent-cards/{agent_id}")
def update(agent_id: str, payload: CardUpdate, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    return card_response(db, update_card(db, agent_id, payload, payload.expected_version, actor))


@router.post("/agent-cards/{agent_id}/eligibility-attestations", status_code=201)
def attest(agent_id: str, payload: EligibilityInput, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    record = attest_eligibility(db, agent_id, payload, actor)
    return {"agent_id": agent_id, "eligible_for_discovery": payload.is_eligible(), "observed_at": record.observed_at}


@router.get("/agent-cards/{agent_id}/eligibility")
def eligibility(agent_id: str, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    card = get_card_or_404(db, agent_id)
    latest = latest_attestation(db, agent_id)
    return {
        "agent_id": agent_id,
        "eligible_for_discovery": is_eligible(db, card),
        "latest_attestation": None if latest is None else {
            "a2a_enabled": latest.a2a_enabled,
            "capability_tier": latest.capability_tier,
            "lifecycle_status": latest.lifecycle_status,
            "registry_ready": latest.registry_ready,
            "runtime_ready": latest.runtime_ready,
            "content_ready": latest.content_ready,
            "source_version": latest.source_version,
            "observed_at": latest.observed_at,
            "received_at": latest.received_at,
        },
    }


@router.post("/agent-cards/{agent_id}/publish")
def publish(agent_id: str, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    card = publish_card(db, agent_id, actor)
    return {**card_response(db, card), "eligible_for_discovery": True}


@router.get("/agent-cards")
def discover(skill: str | None = Query(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"), db: Session = Depends(get_db)):
    cards = list(db.scalars(select(AgentCard).where(AgentCard.card_status == "published").order_by(AgentCard.name)))
    items = [card_response(db, card) for card in cards if is_eligible(db, card)]
    if skill:
        items = [item for item in items if skill in item["skills"]]
    return {"items": items, "total": len(items)}


@router.get("/agent-cards/{agent_id}")
def get_one(agent_id: str, db: Session = Depends(get_db)):
    card = get_card_or_404(db, agent_id)
    if card.card_status != "published" or not is_eligible(db, card):
        from .service import _error
        _error("A2A_CARD_NOT_FOUND", "No discoverable A2A card exists for this agent_id.", 404)
    return card_response(db, card)


@router.post("/agent-cards/{agent_id}/suspend")
def suspend(agent_id: str, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    return card_response(db, change_status(db, agent_id, "suspend", actor))


@router.post("/agent-cards/{agent_id}/retire")
def retire(agent_id: str, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    return card_response(db, change_status(db, agent_id, "retire", actor))


@router.get("/agent-cards/{agent_id}/versions")
def versions(agent_id: str, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    card = get_card_or_404(db, agent_id)
    rows = db.scalars(select(AgentCardVersion).where(AgentCardVersion.agent_card_id == card.id).order_by(AgentCardVersion.card_version.desc())).all()
    return {"agent_id": agent_id, "items": [{"card_version": r.card_version, "change_type": r.change_type, "created_at": r.created_at, "snapshot": r.snapshot} for r in rows]}


@router.get("/agent-cards/{agent_id}/audit-events")
def audit_events(agent_id: str, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    get_card_or_404(db, agent_id)
    rows = db.scalars(select(AuditEvent).where(AuditEvent.agent_id == agent_id).order_by(AuditEvent.occurred_at.desc())).all()
    return {"agent_id": agent_id, "items": [{"action": r.action, "actor_id": r.actor_id, "card_version": r.card_version, "detail": r.detail, "occurred_at": r.occurred_at} for r in rows]}


@router.post("/handoffs/validate")
def handoff_validate(payload: HandoffValidationRequest, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    return validate_handoff(db, payload, actor)


@router.get("/handoff-approval-requests/{approval_id}")
def handoff_approval_get(approval_id: UUID, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    request = db.get(HandoffApprovalRequest, approval_id)
    if request is None:
        from .service import _error
        _error("A2A_APPROVAL_NOT_FOUND", "No handoff approval request exists for this id.", 404)
    return handoff_approval_response(request)


@router.post("/handoff-approval-requests/{approval_id}/decision")
def handoff_approval_decide(approval_id: UUID, payload: ApprovalDecision, db: Session = Depends(get_db), actor: str = Depends(require_write_key)):
    return decide_handoff_approval(db, approval_id, payload, actor)
