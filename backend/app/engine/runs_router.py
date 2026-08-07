"""Run endpoints: start (interactive/test mode), trace inspection, and the
HITL decide-and-resume path. A paused run resumes from its durable checkpoint
— the decision is recorded server-side (actor from session) before resuming.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..models import (
    AgentControlRecord, Role, RunHitl, RunStatus, RunStep, User, Workflow,
    WorkflowRun, WorkflowStatus, WorkflowVersion, utcnow,
)
from . import runner

router = APIRouter(tags=["runs"])

_RUN_ROLES = (Role.agent_creator, Role.agent_owner, Role.ai_engineer)
_HITL_ROLES = (Role.agent_owner, Role.governance_reviewer, Role.platform_admin)
_RUNNABLE = (WorkflowStatus.validated, WorkflowStatus.approved, WorkflowStatus.active)


def _run_payload(db: Session, run: WorkflowRun, with_steps: bool = True) -> dict:
    out = {
        "id": str(run.id), "agent_id": str(run.agent_id),
        "workflow_version_id": str(run.workflow_version_id),
        "mode": run.mode, "status": run.status.value,
        "input": run.input, "output": run.output, "error": run.error,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    if with_steps:
        steps = db.scalars(select(RunStep).where(RunStep.run_id == run.id)
                           .order_by(RunStep.ord)).all()
        out["steps"] = [{
            "ord": s.ord, "node_id": s.node_id, "node_type": s.node_type,
            "status": s.status, "duration_ms": s.duration_ms,
            "tokens_in": s.tokens_in, "tokens_out": s.tokens_out, "cost": s.cost,
            "detail": s.detail, "at": s.at.isoformat(),
        } for s in steps]
        out["totals"] = {
            "tokens_in": sum(s.tokens_in for s in steps),
            "tokens_out": sum(s.tokens_out for s in steps),
            "cost": round(sum(s.cost for s in steps), 6),
            "duration_ms": sum(s.duration_ms for s in steps),
        }
        hitl = db.scalars(select(RunHitl).where(RunHitl.run_id == run.id)).all()
        out["hitl"] = [{
            "id": str(h.id), "node_id": h.node_id, "status": h.status,
            "payload": h.payload, "requested_at": h.requested_at.isoformat(),
            "note": h.note,
        } for h in hitl]
    return out


class StartRunBody(BaseModel):
    input: str = Field(min_length=1, max_length=8000)
    workflow_version_id: uuid.UUID | None = None
    mode: str = Field(default="interactive", pattern="^(interactive|evaluation)$")


@router.post("/api/agents/{agent_id}/runs", status_code=201)
def start_run(
    agent_id: uuid.UUID,
    body: StartRunBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_RUN_ROLES)),
):
    agent = db.get(AgentControlRecord, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    if body.workflow_version_id:
        version = db.get(WorkflowVersion, body.workflow_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="workflow version not found")
        workflow = db.get(Workflow, version.workflow_id)
        if workflow is None or workflow.agent_id != agent.id:
            raise HTTPException(status_code=422, detail="version does not belong to this agent")
    else:
        version = db.scalars(
            select(WorkflowVersion).join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .where(Workflow.agent_id == agent.id, WorkflowVersion.status == WorkflowStatus.active)
        ).first()
        if version is None:
            raise HTTPException(status_code=409, detail="agent has no active workflow version")

    if version.status not in _RUNNABLE:
        raise HTTPException(
            status_code=409,
            detail=f"version is {version.status.value} — validate the draft first (runnable: "
                   f"{', '.join(s.value for s in _RUNNABLE)})")

    run = WorkflowRun(agent_id=agent.id, workflow_version_id=version.id,
                      mode=body.mode, input={"text": body.input}, created_by=user.id)
    db.add(run)
    db.flush()
    audit(db, user, "run_started", "run", str(run.id), {
        "agent_id": str(agent.id), "workflow_version": version.version, "mode": body.mode,
    })
    db.commit()

    runner.start_run(db, run, version.graph, body.input)
    audit(db, user, "run_finished" if run.status in (RunStatus.completed, RunStatus.failed)
          else "run_paused", "run", str(run.id), {"status": run.status.value, "error": run.error})
    events.emit("run.finished", {"run_id": str(run.id), "status": run.status.value})
    db.commit()
    return _run_payload(db, run)


@router.get("/api/agents/{agent_id}/runs")
def list_runs(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
    limit: int = Query(default=50, le=200),
):
    rows = db.scalars(select(WorkflowRun).where(WorkflowRun.agent_id == agent_id)
                      .order_by(WorkflowRun.started_at.desc()).limit(limit)).all()
    return [_run_payload(db, r, with_steps=False) for r in rows]


@router.get("/api/runs/{run_id}")
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _run_payload(db, run)


class HitlDecisionBody(BaseModel):
    approve: bool
    note: str | None = None


@router.post("/api/runs/{run_id}/hitl/{hitl_id}")
def decide_hitl(
    run_id: uuid.UUID,
    hitl_id: uuid.UUID,
    body: HitlDecisionBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_HITL_ROLES)),
):
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    hitl = db.get(RunHitl, hitl_id)
    if hitl is None or hitl.run_id != run.id:
        raise HTTPException(status_code=404, detail="HITL request not found")
    if hitl.status != "pending":
        raise HTTPException(status_code=409, detail=f"already decided ({hitl.status})")
    if run.status != RunStatus.paused_hitl:
        raise HTTPException(status_code=409, detail=f"run is {run.status.value}, not paused")

    hitl.status = "approved" if body.approve else "denied"
    hitl.decided_by = user.id  # server-derived, as everywhere
    hitl.decided_at = utcnow()
    hitl.note = body.note
    audit(db, user, "run_hitl_decided", "run", str(run.id), {
        "hitl_id": str(hitl.id), "node_id": hitl.node_id, "approve": body.approve,
    })
    db.commit()

    version = db.get(WorkflowVersion, run.workflow_version_id)
    runner.resume_run(db, run, version.graph, {"approved": body.approve, "note": body.note})
    audit(db, user, "run_finished" if run.status in (RunStatus.completed, RunStatus.failed)
          else "run_paused", "run", str(run.id), {"status": run.status.value, "error": run.error})
    events.emit("run.finished", {"run_id": str(run.id), "status": run.status.value})
    db.commit()
    return _run_payload(db, run)
