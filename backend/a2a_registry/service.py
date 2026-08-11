from datetime import datetime, timezone
import uuid
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AgentCard, AgentCardVersion, AgentSkill, AuditEvent, EligibilityAttestation, HandoffApprovalRequest
from .schemas import ApprovalDecision, CardInput, EligibilityInput, HandoffValidationRequest


def _error(code: str, message: str, http_status: int, details: list[dict] | None = None) -> None:
    payload = {"code": code, "message": message}
    if details:
        payload["details"] = details
    raise HTTPException(status_code=http_status, detail=payload)


def _card_snapshot(card: AgentCard, skills: list[str]) -> dict:
    return {
        "contract_version": card.contract_version, "agent_id": card.agent_id, "name": card.name,
        "description": card.description, "owner_team": card.owner_team, "endpoint": card.endpoint,
        "skills": skills, "supported_tasks": card.supported_tasks,
        "input_schema": card.input_schema, "output_schema": card.output_schema,
        "capability_tier": card.capability_tier, "discovery_only": card.discovery_only,
        "message_task_format": card.message_task_format, "artifact_exchange": card.artifact_exchange,
        "artifact_format": card.artifact_format, "handoff_rules": card.handoff_rules,
        "timeout_seconds": card.timeout_seconds, "failure_behavior": card.failure_behavior,
        "authn_methods": card.authn_methods, "authorized_callers": card.authorized_callers,
        "card_status": card.card_status, "card_version": card.card_version,
    }


def _record_history(session: Session, card: AgentCard, action: str, actor_id: str) -> None:
    skills = list(session.scalars(select(AgentSkill.skill).where(AgentSkill.agent_card_id == card.id).order_by(AgentSkill.skill)))
    session.add(AgentCardVersion(agent_card_id=card.id, card_version=card.card_version, snapshot=_card_snapshot(card, skills), change_type=action, actor_id=actor_id))
    session.add(AuditEvent(agent_id=card.agent_id, action=action, actor_id=actor_id, actor_type="service", card_version=card.card_version, detail={"card_status": card.card_status}))


def _set_card_fields(session: Session, card: AgentCard, payload: CardInput) -> None:
    parsed = urlparse(str(payload.endpoint))
    settings = get_settings()
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in settings.internal_endpoint_hosts:
        _error("A2A_ENDPOINT_NOT_INTERNAL", "The endpoint must use HTTPS and an approved internal host.", status.HTTP_422_UNPROCESSABLE_ENTITY)
    for field in (
        "contract_version", "name", "description", "owner_team", "capability_tier",
        "discovery_only", "message_task_format", "artifact_exchange", "artifact_format",
        "timeout_seconds", "failure_behavior",
    ):
        setattr(card, field, getattr(payload, field))
    card.endpoint = str(payload.endpoint)
    card.supported_tasks = payload.supported_tasks
    card.input_schema = payload.input_schema
    card.output_schema = payload.output_schema
    card.handoff_rules = payload.handoff_rules.model_dump()
    card.authn_methods = payload.authn_methods
    card.authorized_callers = payload.authorized_callers
    session.query(AgentSkill).filter(AgentSkill.agent_card_id == card.id).delete(synchronize_session=False)
    session.add_all([AgentSkill(agent_card_id=card.id, skill=skill) for skill in payload.skills])


def get_card_or_404(session: Session, agent_id: str) -> AgentCard:
    card = session.scalar(select(AgentCard).where(AgentCard.agent_id == agent_id))
    if card is None:
        _error("A2A_CARD_NOT_FOUND", "No A2A card exists for this agent_id.", status.HTTP_404_NOT_FOUND)
    return card


def create_card(session: Session, payload: CardInput, actor_id: str) -> AgentCard:
    if session.scalar(select(AgentCard.id).where(AgentCard.agent_id == payload.agent_id)):
        _error("A2A_AGENT_ID_EXISTS", "An A2A card already exists for this agent_id.", status.HTTP_409_CONFLICT)
    # Generate the UUID before child skill rows are built; SQLAlchemy's column
    # default otherwise runs only during flush, after the skill objects exist.
    card = AgentCard(id=uuid.uuid4(), agent_id=payload.agent_id)
    _set_card_fields(session, card, payload)
    session.add(card)
    session.flush()
    _record_history(session, card, "created", actor_id)
    session.commit()
    session.refresh(card)
    return card


def update_card(session: Session, agent_id: str, payload: CardInput, expected_version: int, actor_id: str) -> AgentCard:
    card = get_card_or_404(session, agent_id)
    if card.card_status != "draft":
        _error("A2A_INVALID_STATE_TRANSITION", "Only draft cards can be updated.", status.HTTP_409_CONFLICT)
    if card.card_version != expected_version:
        _error("A2A_VERSION_CONFLICT", "The card was changed by another request. Fetch the latest version and retry.", status.HTTP_409_CONFLICT)
    _set_card_fields(session, card, payload)
    card.card_version += 1
    session.flush()
    _record_history(session, card, "updated", actor_id)
    session.commit()
    session.refresh(card)
    return card


def attest_eligibility(session: Session, agent_id: str, payload: EligibilityInput, actor_id: str) -> EligibilityAttestation:
    get_card_or_404(session, agent_id)
    if payload.source_agent_id != agent_id:
        _error("A2A_CARD_INVALID", "source_agent_id must match the path agent_id.", status.HTTP_422_UNPROCESSABLE_ENTITY)
    record = EligibilityAttestation(**payload.model_dump(), actor_id=actor_id)
    session.add(record)
    session.add(AuditEvent(agent_id=agent_id, action="eligibility_attested", actor_id=actor_id, actor_type="service", card_version=None, detail={"eligible_for_discovery": payload.is_eligible()}))
    session.commit()
    session.refresh(record)
    return record


def latest_attestation(session: Session, agent_id: str) -> EligibilityAttestation | None:
    return session.scalar(select(EligibilityAttestation).where(EligibilityAttestation.source_agent_id == agent_id).order_by(EligibilityAttestation.observed_at.desc(), EligibilityAttestation.received_at.desc()))


def is_eligible(session: Session, card: AgentCard) -> bool:
    latest = latest_attestation(session, card.agent_id)
    if latest is None:
        return False
    return (latest.a2a_enabled and latest.capability_tier == card.capability_tier and latest.lifecycle_status == "live" and latest.registry_ready and latest.runtime_ready and latest.content_ready)


def publish_card(session: Session, agent_id: str, actor_id: str) -> AgentCard:
    card = get_card_or_404(session, agent_id)
    if card.card_status not in {"draft", "suspended"}:
        _error("A2A_INVALID_STATE_TRANSITION", "Only draft or suspended cards can be published.", status.HTTP_409_CONFLICT)
    if not is_eligible(session, card):
        _error("A2A_CARD_NOT_ELIGIBLE", "The agent cannot be published because it is not LIVE and A2A-eligible.", status.HTTP_422_UNPROCESSABLE_ENTITY)
    card.card_status = "published"
    card.published_at = datetime.now(timezone.utc)
    card.card_version += 1
    session.flush()
    _record_history(session, card, "published", actor_id)
    session.commit()
    session.refresh(card)
    return card


def change_status(session: Session, agent_id: str, new_status: str, actor_id: str) -> AgentCard:
    card = get_card_or_404(session, agent_id)
    allowed = {"suspend": ({"published"}, "suspended"), "retire": ({"draft", "published", "suspended"}, "retired")}
    current, target = allowed[new_status]
    if card.card_status not in current:
        _error("A2A_INVALID_STATE_TRANSITION", f"Cannot {new_status} a {card.card_status} card.", status.HTTP_409_CONFLICT)
    card.card_status = target
    card.card_version += 1
    session.flush()
    _record_history(session, card, f"{target}", actor_id)
    session.commit()
    session.refresh(card)
    return card


def card_response(session: Session, card: AgentCard) -> dict:
    skills = list(session.scalars(select(AgentSkill.skill).where(AgentSkill.agent_card_id == card.id).order_by(AgentSkill.skill)))
    return _card_snapshot(card, skills)


def _assert_discoverable_for_handoff(session: Session, agent_id: str, role: str) -> AgentCard:
    card = get_card_or_404(session, agent_id)
    if card.card_status != "published" or not is_eligible(session, card):
        _error("A2A_HANDOFF_AGENT_NOT_READY", f"The {role} agent is not published and A2A-eligible.", status.HTTP_422_UNPROCESSABLE_ENTITY)
    return card


def validate_handoff(session: Session, payload: HandoffValidationRequest, actor_id: str) -> dict:
    source = _assert_discoverable_for_handoff(session, payload.source_agent_id, "source")
    target = _assert_discoverable_for_handoff(session, payload.target_agent_id, "target")
    if payload.task not in target.supported_tasks:
        _error("A2A_TASK_NOT_SUPPORTED", "The target agent does not declare support for this task.", status.HTTP_422_UNPROCESSABLE_ENTITY)

    target_skills = set(session.scalars(select(AgentSkill.skill).where(AgentSkill.agent_card_id == target.id)))
    allowed_skills = set((target.handoff_rules or {}).get("allowed_target_skills", []))
    if allowed_skills and not target_skills.intersection(allowed_skills):
        _error("A2A_HANDOFF_RULE_BLOCKED", "The target agent does not satisfy its declared handoff skill rules.", status.HTTP_422_UNPROCESSABLE_ENTITY)

    requires_approval = bool((target.handoff_rules or {}).get("require_human_approval"))
    if requires_approval:
        if payload.approval_request_id is None:
            request = HandoffApprovalRequest(
                id=uuid.uuid4(),
                source_agent_id=source.agent_id,
                target_agent_id=target.agent_id,
                task=payload.task,
                trace_correlation_id=payload.trace_correlation_id,
                request_payload=payload.model_dump(mode="json"),
                requested_by=actor_id,
            )
            session.add(request)
            session.add(AuditEvent(agent_id=target.agent_id, action="handoff_approval_requested", actor_id=actor_id, actor_type="service", card_version=target.card_version, detail={"trace_correlation_id": payload.trace_correlation_id, "source_agent_id": source.agent_id, "task": payload.task}))
            session.commit()
            return {"status": "approval_required", "trace_correlation_id": payload.trace_correlation_id, "approval_request_id": request.id}

        request = session.get(HandoffApprovalRequest, payload.approval_request_id)
        if request is None or request.trace_correlation_id != payload.trace_correlation_id or request.source_agent_id != source.agent_id or request.target_agent_id != target.agent_id:
            _error("A2A_APPROVAL_NOT_FOUND", "No matching handoff approval request exists for this trace.", status.HTTP_404_NOT_FOUND)
        if request.status != "approved":
            _error("A2A_APPROVAL_REQUIRED", "Human approval is required before this handoff can proceed.", status.HTTP_409_CONFLICT, [{"approval_status": request.status}])

    session.add(AuditEvent(agent_id=target.agent_id, action="handoff_validated", actor_id=actor_id, actor_type="service", card_version=target.card_version, detail={"trace_correlation_id": payload.trace_correlation_id, "source_agent_id": source.agent_id, "task": payload.task}))
    session.commit()
    return {
        "status": "ready_for_handoff",
        "trace_correlation_id": payload.trace_correlation_id,
        "target_agent_id": target.agent_id,
        "task": payload.task,
        "timeout_seconds": target.timeout_seconds,
        "failure_behavior": target.failure_behavior,
        "artifact_exchange": target.artifact_exchange,
        "artifact_format": target.artifact_format,
        "authn_methods": target.authn_methods,
    }


def decide_handoff_approval(session: Session, approval_id: uuid.UUID, payload: ApprovalDecision, actor_id: str) -> dict:
    request = session.get(HandoffApprovalRequest, approval_id)
    if request is None:
        _error("A2A_APPROVAL_NOT_FOUND", "No handoff approval request exists for this id.", status.HTTP_404_NOT_FOUND)
    if request.status != "pending":
        _error("A2A_APPROVAL_ALREADY_DECIDED", "This handoff approval request has already been decided.", status.HTTP_409_CONFLICT)
    request.status = payload.decision
    request.decided_by = actor_id
    request.decision_note = payload.note
    request.decided_at = datetime.now(timezone.utc)
    session.add(AuditEvent(agent_id=request.target_agent_id, action=f"handoff_approval_{payload.decision}", actor_id=actor_id, actor_type="service", card_version=None, detail={"trace_correlation_id": request.trace_correlation_id, "source_agent_id": request.source_agent_id, "task": request.task}))
    session.commit()
    return handoff_approval_response(request)


def handoff_approval_response(request: HandoffApprovalRequest) -> dict:
    return {
        "approval_request_id": request.id,
        "source_agent_id": request.source_agent_id,
        "target_agent_id": request.target_agent_id,
        "task": request.task,
        "trace_correlation_id": request.trace_correlation_id,
        "status": request.status,
        "requested_by": request.requested_by,
        "decided_by": request.decided_by,
        "decision_note": request.decision_note,
        "created_at": request.created_at,
        "decided_at": request.decided_at,
    }
