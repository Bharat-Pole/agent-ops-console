"""Workflow lifecycle (Pass 5): draft → validated → pending_approval →
approved → active → superseded. Only drafts are editable; editing anything
later forks a new draft. Validation gates submission — what reaches approval
is exactly what can execute.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import (
    AgentControlRecord, DesignRecommendation, Role, User, Workflow, WorkflowStatus,
    WorkflowVersion, utcnow,
)
from ..assets import workflow as approval_workflow
from .validation import validate_workflow

router = APIRouter(tags=["workflows"])

_EDIT_ROLES = (Role.agent_creator, Role.agent_owner, Role.ai_engineer)


def _risk_of(agent: AgentControlRecord) -> str:
    tier = agent.confirmed_risk_tier or agent.draft_risk_tier
    return tier.value if tier else "low"


def _version_payload(v: WorkflowVersion) -> dict:
    return {
        "id": str(v.id), "workflow_id": str(v.workflow_id), "version": v.version,
        "graph": v.graph, "status": v.status.value, "validation": v.validation,
        "notes": v.notes, "created_at": v.created_at.isoformat(), "updated_at": v.updated_at.isoformat(),
    }


def _workflow_payload(db: Session, w: Workflow) -> dict:
    versions = db.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == w.id)
                          .order_by(WorkflowVersion.version.desc())).all()
    return {
        "id": str(w.id), "agent_id": str(w.agent_id), "name": w.name,
        "created_at": w.created_at.isoformat(),
        "versions": [_version_payload(v) for v in versions],
        "active_version": next((v.version for v in versions if v.status == WorkflowStatus.active), None),
    }


def _get_agent(db: Session, agent_id: uuid.UUID) -> AgentControlRecord:
    agent = db.get(AgentControlRecord, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


def _get_version(db: Session, workflow_id: uuid.UUID, version: int) -> tuple[Workflow, WorkflowVersion]:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    row = db.scalars(select(WorkflowVersion).where(
        WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.version == version)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"version {version} not found")
    return workflow, row


class CreateWorkflowBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    from_recommendation: bool = False
    graph: dict | None = None


@router.post("/api/agents/{agent_id}/workflows", status_code=201)
def create_workflow(
    agent_id: uuid.UUID,
    body: CreateWorkflowBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    agent = _get_agent(db, agent_id)
    graph = body.graph or {"nodes": [], "edges": []}
    seeded_from = None
    if body.from_recommendation:
        if agent.design_recommendation_id is None:
            raise HTTPException(status_code=409, detail="no recommendation to seed from")
        rec = db.get(DesignRecommendation, agent.design_recommendation_id)
        flow_item = next((i for i in (rec.items or []) if i.get("kind") == "flow"), None)
        if not flow_item:
            raise HTTPException(status_code=409, detail="recommendation has no flow item")
        graph = (flow_item.get("detail") or {}).get("flow") or graph
        seeded_from = {
            "recommendation_id": str(rec.id),
            "flow_item_state": (rec.item_states or {}).get("flow", "pending"),
        }
    workflow = Workflow(agent_id=agent.id, name=body.name, created_by=user.id)
    db.add(workflow)
    db.flush()
    v1 = WorkflowVersion(workflow_id=workflow.id, version=1, graph=graph, created_by=user.id,
                         notes=f"seeded from recommendation {seeded_from}" if seeded_from else "")
    db.add(v1)
    db.flush()
    audit(db, user, "workflow_created", "workflow", str(workflow.id),
          {"agent_id": str(agent.id), "seeded_from": seeded_from})
    db.commit()
    payload = _workflow_payload(db, workflow)
    payload["seeded_from"] = seeded_from
    return payload


@router.get("/api/agents/{agent_id}/workflows")
def list_workflows(agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    _get_agent(db, agent_id)
    rows = db.scalars(select(Workflow).where(Workflow.agent_id == agent_id)).all()
    return [_workflow_payload(db, w) for w in rows]


@router.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return _workflow_payload(db, workflow)


class GraphBody(BaseModel):
    graph: dict
    notes: str = ""


@router.put("/api/workflows/{workflow_id}/versions/{version}")
def update_draft(
    workflow_id: uuid.UUID,
    version: int,
    body: GraphBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    workflow, row = _get_version(db, workflow_id, version)
    if row.status not in (WorkflowStatus.draft, WorkflowStatus.validated):
        raise HTTPException(status_code=409,
                            detail=f"version is {row.status.value} — fork a new draft to edit")
    row.graph = body.graph
    row.notes = body.notes or row.notes
    row.status = WorkflowStatus.draft  # any edit re-requires validation
    row.validation = {}
    row.updated_at = utcnow()
    audit(db, user, "workflow_draft_updated", "workflow", str(workflow.id), {"version": version})
    db.commit()
    return _version_payload(row)


@router.post("/api/workflows/{workflow_id}/versions/{version}/validate")
def validate_version(
    workflow_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    workflow, row = _get_version(db, workflow_id, version)
    if row.status not in (WorkflowStatus.draft, WorkflowStatus.validated):
        raise HTTPException(status_code=409, detail=f"cannot validate from {row.status.value}")
    agent = _get_agent(db, workflow.agent_id)
    outcome = validate_workflow(db, row.graph, _risk_of(agent))
    row.graph = outcome.graph  # guardrail auto-inserts persist
    row.validation = outcome.as_dict()
    row.status = WorkflowStatus.validated if outcome.ok else WorkflowStatus.draft
    row.updated_at = utcnow()
    audit(db, user, "workflow_validated", "workflow", str(workflow.id), {
        "version": version, "ok": outcome.ok,
        "violations": len(outcome.violations), "rules_version": outcome.rules_version,
    })
    db.commit()
    return _version_payload(row)


@router.post("/api/workflows/{workflow_id}/versions/{version}/submit")
def submit_version(
    workflow_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    workflow, row = _get_version(db, workflow_id, version)
    if row.status != WorkflowStatus.validated:
        raise HTTPException(status_code=409, detail="version must pass validation before submission")
    approval_workflow.request_approval(db, "workflow_version", row.id,
                                       [("governance_review", Role.governance_reviewer)])
    row.status = WorkflowStatus.pending_approval
    audit(db, user, "workflow_submitted_for_approval", "workflow", str(workflow.id), {"version": version})
    events.emit("asset.submitted", {"type": "workflow_version", "id": str(row.id)})
    db.commit()
    return _version_payload(row)


@router.post("/api/workflows/{workflow_id}/versions/{version}/activate")
def activate_version(
    workflow_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.agent_owner, Role.governance_reviewer, Role.platform_admin)),
):
    workflow, row = _get_version(db, workflow_id, version)
    if row.status != WorkflowStatus.approved:
        raise HTTPException(status_code=409, detail=f"only approved versions activate (is {row.status.value})")
    for prior in db.scalars(select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.status == WorkflowStatus.active)).all():
        prior.status = WorkflowStatus.superseded
    row.status = WorkflowStatus.active
    row.updated_at = utcnow()
    audit(db, user, "workflow_activated", "workflow", str(workflow.id), {"version": version})
    events.emit("workflow.activated", {"workflow_id": str(workflow.id), "version": version})
    db.commit()
    return _version_payload(row)


@router.post("/api/workflows/{workflow_id}/versions/{version}/fork", status_code=201)
def fork_version(
    workflow_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    workflow, row = _get_version(db, workflow_id, version)
    newest = db.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id)
                        .order_by(WorkflowVersion.version.desc())).first()
    draft = WorkflowVersion(
        workflow_id=workflow.id, version=newest.version + 1, graph=row.graph,
        notes=f"forked from v{version}", created_by=user.id,
    )
    db.add(draft)
    db.flush()
    audit(db, user, "workflow_forked", "workflow", str(workflow.id),
          {"from_version": version, "new_version": draft.version})
    db.commit()
    return _version_payload(draft)
