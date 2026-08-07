"""PolicyService — the single decision interface (Pass 4 decision).

Increment A shipped the transition role-matrix; Increment E extends the SAME
interface with the eval gate, the 30-day staleness guard, and the logged
exception override (Low/Medium only). Every decision carries the rule version
AND the governance-config version so audits can reconstruct exactly which
policy applied. An OPA adapter can replace the internals without touching
call sites.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AgentControlRecord, AssetStatus, EvalRun, GovernanceException,
    LifecycleStatus as LS, PolicyConfigRow, Role, ToolRecord, User,
    Workflow, WorkflowStatus, WorkflowVersion, WRITE_PERMISSION_TYPES, utcnow,
)

RULES_VERSION = "policy-v3-increment-e"

# Governance config defaults — seeded as policy_configs v1; admin edits create
# new versions. Eval gate: hard everywhere; Low/Medium may pass a FAILED gate
# only through a logged, unexpired governance exception (Decision 6/7.1).
DEFAULT_GOVERNANCE_CONFIG: dict = {
    "eval_gate": {"low": "hard", "medium": "hard", "high": "hard", "restricted": "hard"},
    "exception_allowed_tiers": ["low", "medium"],
    "staleness_days": 30,
    "scorecard_default_threshold": 70.0,
}

_GATED_TRANSITIONS = {LS.production_candidate, LS.production}


def active_config(db: Session) -> tuple[dict, int]:
    row = db.scalars(select(PolicyConfigRow).where(PolicyConfigRow.active.is_(True))
                     .order_by(PolicyConfigRow.version.desc())).first()
    if row is None:
        return DEFAULT_GOVERNANCE_CONFIG, 0
    merged = {**DEFAULT_GOVERNANCE_CONFIG, **(row.config or {})}
    return merged, row.version

# (from, to) -> roles allowed to perform the transition.
# Doctrine: friction proportional to risk; governance owns promotion gates.
TRANSITIONS: dict[tuple[LS, LS], set[Role]] = {
    (LS.draft, LS.sandbox): {Role.agent_creator, Role.agent_owner, Role.ai_engineer},
    (LS.sandbox, LS.candidate): {Role.agent_creator, Role.ai_engineer, Role.agent_owner},
    (LS.candidate, LS.sandbox): {Role.agent_creator, Role.ai_engineer},  # rework
    (LS.candidate, LS.approved_prototype): {Role.agent_owner},
    (LS.approved_prototype, LS.production_candidate): {Role.governance_reviewer},
    (LS.production_candidate, LS.production): {Role.governance_reviewer},
    (LS.production, LS.needs_review): {Role.governance_reviewer, Role.security_data_owner},
    (LS.needs_review, LS.production): {Role.governance_reviewer},
    (LS.production, LS.deprecated): {Role.agent_owner, Role.governance_reviewer},
    (LS.needs_review, LS.deprecated): {Role.agent_owner, Role.governance_reviewer},
    (LS.deprecated, LS.retired): {Role.governance_reviewer},
}


@dataclass
class Decision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    rules_version: str = RULES_VERSION


def _risk_of(agent: AgentControlRecord) -> str:
    tier = agent.confirmed_risk_tier or agent.draft_risk_tier
    return tier.value if tier else "low"


def _active_workflow_version(db: Session, agent: AgentControlRecord) -> WorkflowVersion | None:
    return db.scalars(
        select(WorkflowVersion).join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .where(Workflow.agent_id == agent.id, WorkflowVersion.status == WorkflowStatus.active)
    ).first()


def _active_exception(db: Session, agent: AgentControlRecord) -> GovernanceException | None:
    now = utcnow()
    for exc in db.scalars(select(GovernanceException).where(
            GovernanceException.agent_id == agent.id,
            GovernanceException.status == "active")).all():
        expires = exc.expires_at
        if expires.tzinfo is None:  # SQLite tz-loss
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > now:
            return exc
    return None


def _check_eval_gate(db: Session, agent: AgentControlRecord, decision: Decision,
                     config: dict) -> None:
    """Promotion gate: a PASSING eval run must exist on the CURRENT active
    workflow version, no older than staleness_days. Failure may be overridden
    only by a logged exception, only for the configured (Low/Medium) tiers."""
    risk = _risk_of(agent)
    failures: list[str] = []

    version = _active_workflow_version(db, agent)
    if version is None:
        failures.append("no active workflow version — build, approve, and activate one first")
    else:
        latest = db.scalars(select(EvalRun).where(
            EvalRun.agent_id == agent.id,
            EvalRun.workflow_version_id == version.id,
            EvalRun.status == "completed")
            .order_by(EvalRun.started_at.desc())).first()
        if latest is None:
            failures.append(f"no completed evaluation run on the active workflow version v{version.version}")
        else:
            if not (latest.scorecard or {}).get("overall_passed"):
                failures.append(
                    f"latest evaluation FAILED (score {(latest.scorecard or {}).get('score')} < "
                    f"threshold {(latest.scorecard or {}).get('threshold')})")
            started = latest.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age_days = (utcnow() - started).days
            if age_days > int(config["staleness_days"]):
                failures.append(
                    f"latest evaluation is {age_days} days old (> {config['staleness_days']} — staleness guard)")

    if not failures:
        return
    if risk in config["exception_allowed_tiers"]:
        exc = _active_exception(db, agent)
        if exc is not None:
            decision.reasons.append(
                f"eval gate failures ({'; '.join(failures)}) OVERRIDDEN by governance exception "
                f"{exc.id} ({exc.reason!r}, expires {exc.expires_at.date()})")
            return
    decision.allowed = False
    decision.reasons.extend(failures)
    if risk not in config["exception_allowed_tiers"]:
        decision.reasons.append(f"{risk} risk tier: eval gate is hard — no exception path exists")


def check_transition(db: Session, agent: AgentControlRecord, to: LS, user: User) -> Decision:
    key = (agent.lifecycle_status, to)
    allowed_roles = TRANSITIONS.get(key)
    if allowed_roles is None:
        return Decision(False, [f"no transition {agent.lifecycle_status.value} → {to.value}"])
    if not user.role_set().intersection(allowed_roles):
        return Decision(False, [
            f"transition {agent.lifecycle_status.value} → {to.value} requires one of "
            f"{sorted(r.value for r in allowed_roles)}"
        ])
    decision = Decision(True)
    if to in _GATED_TRANSITIONS:
        config, config_version = active_config(db)
        decision.reasons.append(f"governance-config v{config_version}")
        _check_eval_gate(db, agent, decision, config)
    return decision


def check_deploy_admission(db: Session, agent: AgentControlRecord,
                           version: WorkflowVersion, channel: str) -> Decision:
    """Deployment admission (Pass 7). Sandbox: active version suffices.
    Production channel: full admission — production lifecycle, passing
    non-stale eval on THIS version, evidence pack present, cost label set."""
    decision = Decision(True)
    config, config_version = active_config(db)
    decision.reasons.append(f"governance-config v{config_version}")

    if version.status != WorkflowStatus.active:
        decision.allowed = False
        decision.reasons.append(f"workflow version is {version.status.value} — only ACTIVE versions deploy")
    if channel == "sandbox":
        return decision

    if agent.lifecycle_status != LS.production:
        decision.allowed = False
        decision.reasons.append(
            f"production channel requires PRODUCTION lifecycle (agent is {agent.lifecycle_status.value})")
    latest = db.scalars(select(EvalRun).where(
        EvalRun.agent_id == agent.id,
        EvalRun.workflow_version_id == version.id,
        EvalRun.status == "completed").order_by(EvalRun.started_at.desc())).first()
    if latest is None or not (latest.scorecard or {}).get("overall_passed"):
        decision.allowed = False
        decision.reasons.append("no PASSING evaluation run on the deployed workflow version")
    else:
        started = latest.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if (utcnow() - started).days > int(config["staleness_days"]):
            decision.allowed = False
            decision.reasons.append("evaluation is stale (staleness guard)")
    from .models import EvidencePack
    if db.scalars(select(EvidencePack).where(EvidencePack.agent_id == agent.id)).first() is None:
        decision.allowed = False
        decision.reasons.append("no evidence pack on record for this agent")
    if not agent.cost_center:
        decision.allowed = False
        decision.reasons.append("agent has no cost_center — unlabeled deployments are rejected (FinOps rule)")
    return decision


def model_clamps(risk_tier: str) -> dict:
    """Model-call governance clamps applied at the adapter boundary (Pass 4/5).
    Higher risk → tighter sampling and bounded output."""
    if risk_tier in ("high", "restricted"):
        return {"max_temperature": 0.3, "max_tokens": 2048, "rules_version": RULES_VERSION}
    return {"max_temperature": 0.9, "max_tokens": 4096, "rules_version": RULES_VERSION}


def can_execute_tool(tool: ToolRecord) -> Decision:
    """Execution-layer gate (layer 3 of the write invariant): even a bound,
    approved write tool is refused at call time in the base phase."""
    if tool.permission_type in WRITE_PERMISSION_TYPES:
        return Decision(False, [
            f"tool {tool.slug!r} is write-class ({tool.permission_type.value}) — execution refused "
            "in the advisory-only base phase (Decision 0.3)"
        ])
    if tool.status != AssetStatus.approved:
        return Decision(False, [f"tool {tool.slug!r} v{tool.version} is {tool.status.value}, not approved"])
    return Decision(True)


def can_bind_tool(tool: ToolRecord) -> Decision:
    """Bind-time gate (Pass 4, layer 2 of the triple-layered write invariant).
    Base phase (Decision 0.3): write-class tools are NEVER bindable — even when
    approved. The dual sign-off approval exists so the machinery is real; the
    enable switch is a later governance increment."""
    if tool.permission_type in WRITE_PERMISSION_TYPES:
        return Decision(False, [
            f"tool {tool.slug!r} has write-class permission {tool.permission_type.value!r} — "
            "binding is disabled in the advisory-only base phase (Decision 0.3)"
        ])
    if tool.status != AssetStatus.approved:
        return Decision(False, [f"tool {tool.slug!r} v{tool.version} is {tool.status.value}, not approved"])
    return Decision(True)
