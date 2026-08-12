"""A2A domain logic: readiness, discovery, and read-only handoff validation.

Readiness is DERIVED, never stored. The source branch persisted an eligibility
attestation because a standalone service could not see whether an agent was in
production or deployed; this platform owns those facts, so a stored copy would
only be a less trustworthy duplicate that can drift.

Nothing here executes a handoff. Validation answers "is this permitted?" and
returns the per-check reasoning; actually calling another agent is deliberately
out of scope.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AgentCard, AgentControlRecord, Approval, ApprovalStatus, AssetStatus,
    Deployment, LifecycleStatus, Workflow, WorkflowStatus, WorkflowVersion,
)

RULES_VERSION = "a2a-validation-v1"


@dataclass
class Readiness:
    """Every input is a live platform fact — nothing here is persisted."""
    card_approved: bool
    agent_in_production: bool
    has_active_workflow: bool
    has_active_deployment: bool
    discoverable: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def compute_readiness(db: Session, card: AgentCard) -> Readiness:
    agent = db.get(AgentControlRecord, card.agent_id)
    card_approved = card.status == AssetStatus.approved
    in_production = agent is not None and agent.lifecycle_status == LifecycleStatus.production
    active_workflow = db.scalars(
        select(WorkflowVersion).join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .where(Workflow.agent_id == card.agent_id,
               WorkflowVersion.status == WorkflowStatus.active)
    ).first() is not None
    active_deployment = db.scalars(select(Deployment).where(
        Deployment.agent_id == card.agent_id, Deployment.status == "active")).first() is not None

    reasons: list[str] = []
    if not card_approved:
        reasons.append(f"card is {card.status.value}, not approved")
    if not in_production:
        reasons.append(
            f"agent lifecycle is {agent.lifecycle_status.value if agent else 'missing'}, not production")
    if not active_workflow:
        reasons.append("agent has no active workflow version")
    # A discovery-only card advertises a contract without claiming to be
    # callable, so a live deployment is only REQUIRED once it claims exchange.
    if not card.discovery_only and not active_deployment:
        reasons.append("card is not discovery-only but the agent has no active deployment")

    return Readiness(
        card_approved=card_approved,
        agent_in_production=in_production,
        has_active_workflow=active_workflow,
        has_active_deployment=active_deployment,
        discoverable=not reasons,
        reasons=reasons,
    )


def current_card(db: Session, agent_id: uuid.UUID) -> AgentCard | None:
    """Newest version for an agent, whatever its status."""
    return db.scalars(select(AgentCard).where(AgentCard.agent_id == agent_id)
                      .order_by(AgentCard.version.desc())).first()


def approved_card(db: Session, agent_id: uuid.UUID) -> AgentCard | None:
    return db.scalars(select(AgentCard).where(
        AgentCard.agent_id == agent_id, AgentCard.status == AssetStatus.approved)
        .order_by(AgentCard.version.desc())).first()


def discoverable_cards(db: Session, skill: str | None = None,
                       task: str | None = None) -> list[tuple[AgentCard, Readiness]]:
    """Approved cards whose agent is genuinely ready. Filtering happens in
    Python: JSON list membership has no portable SQL form across SQLite and
    Postgres, and the catalogue is small (same rationale as brute-force vector
    search in adapters/vectors.py)."""
    rows = db.scalars(select(AgentCard).where(AgentCard.status == AssetStatus.approved)).all()
    out: list[tuple[AgentCard, Readiness]] = []
    for card in rows:
        if skill and skill not in (card.skills or []):
            continue
        if task and task not in (card.supported_tasks or []):
            continue
        readiness = compute_readiness(db, card)
        if readiness.discoverable:
            out.append((card, readiness))
    return out


# ---- handoff validation (read-only) -----------------------------------------

@dataclass
class HandoffDecision:
    """Local verdict shape, deliberately NOT policy.Decision: forcing this into
    the lifecycle decision type would mean editing policy.py for no behavioural
    gain. Same spirit — allow/deny plus reasons plus a rules version."""
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    target: dict | None = None
    rules_version: str = RULES_VERSION

    def as_dict(self) -> dict:
        return asdict(self)


def _fail(decision: HandoffDecision, check: str, reason: str) -> None:
    decision.allowed = False
    decision.checks[check] = False
    decision.reasons.append(reason)


def validate_handoff(db: Session, source_slug: str, target_slug: str, task: str,
                     required_skill: str | None = None) -> HandoffDecision:
    decision = HandoffDecision(allowed=True)

    source_agent = db.scalars(select(AgentControlRecord).where(
        AgentControlRecord.slug == source_slug)).first()
    target_agent = db.scalars(select(AgentControlRecord).where(
        AgentControlRecord.slug == target_slug)).first()

    if source_agent is None:
        _fail(decision, "source_agent", f"no agent with slug {source_slug!r}")
    if target_agent is None:
        _fail(decision, "target_agent", f"no agent with slug {target_slug!r}")
    if source_agent is None or target_agent is None:
        return decision

    source_card = approved_card(db, source_agent.id)
    target_card = approved_card(db, target_agent.id)
    if source_card is None:
        _fail(decision, "source_agent", f"agent {source_slug!r} has no approved agent card")
    else:
        decision.checks["source_agent"] = True
    if target_card is None:
        _fail(decision, "target_agent", f"agent {target_slug!r} has no approved agent card")
        return decision
    decision.checks["target_agent"] = True

    readiness = compute_readiness(db, target_card)
    if readiness.discoverable:
        decision.checks["target_status"] = True
    else:
        _fail(decision, "target_status",
              "target is not ready: " + "; ".join(readiness.reasons))

    if task in (target_card.supported_tasks or []):
        decision.checks["supported_task"] = True
    else:
        _fail(decision, "supported_task",
              f"target does not declare support for task {task!r}")

    rules = target_card.handoff_rules or {}
    needed = list(rules.get("required_skills") or [])
    if required_skill:
        needed.append(required_skill)
    missing = [s for s in needed if s not in (target_card.skills or [])]
    if missing:
        _fail(decision, "required_skill", f"target is missing required skills: {missing}")
    else:
        decision.checks["required_skill"] = True

    allowed_callers = target_card.authorized_callers or []
    if allowed_callers and source_slug not in allowed_callers:
        _fail(decision, "caller_authorization",
              f"{source_slug!r} is not in the target's authorized_callers")
    else:
        decision.checks["caller_authorization"] = True

    if rules.get("require_human_approval"):
        granted = db.scalars(select(Approval).where(
            Approval.resource_type == "a2a_handoff",
            Approval.resource_id == target_card.id,
            Approval.status == ApprovalStatus.approved)).first()
        if granted is None:
            _fail(decision, "approval",
                  "target requires human approval for handoffs and no approved "
                  "'a2a_handoff' approval exists for this card")
        else:
            decision.checks["approval"] = True
    else:
        decision.checks["approval"] = True

    if decision.allowed:
        # contract the caller would need — reported, never acted on
        decision.target = {
            "agent_slug": target_slug,
            "card_version": target_card.version,
            "task": task,
            "timeout_seconds": target_card.timeout_seconds,
            "failure_behavior": target_card.failure_behavior,
            "artifact_exchange": target_card.artifact_exchange,
            "artifact_format": target_card.artifact_format,
            "authn_methods": target_card.authn_methods,
            "message_task_format": target_card.message_task_format,
        }
    return decision
