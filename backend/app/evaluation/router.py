"""Evaluation Center endpoints: packs, cases, runs, scorecards. LLM-generated
cases enter as review_status=pending and are excluded from runs until a human
marks them reviewed (spec A.3 doctrine).
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
    AgentControlRecord, EvalCase, EvalPack, EvalResult, EvalRun, Role, User,
    Workflow, WorkflowStatus, WorkflowVersion,
)
from . import engine as eval_engine

router = APIRouter(tags=["evaluation"])

_EDIT_ROLES = (Role.evaluator, Role.ai_engineer, Role.agent_creator, Role.agent_owner)

CATEGORIES = ("golden", "boundary", "refusal", "no_write", "data_boundary",
              "tool_call", "regression", "latency", "cost", "safety")

_KNOWN_EXPECTATIONS = {
    "must_contain", "must_not_contain", "must_cite", "must_refuse", "refusal_markers",
    "must_call_tool", "must_not_call_tool", "no_write", "must_pause_hitl",
    "latency_max_ms", "max_cost", "judge",
}


def _pack_payload(db: Session, pack: EvalPack) -> dict:
    cases = db.scalars(select(EvalCase).where(EvalCase.pack_id == pack.id)).all()
    return {
        "id": str(pack.id), "agent_id": str(pack.agent_id), "name": pack.name,
        "threshold": pack.threshold, "status": pack.status,
        "created_at": pack.created_at.isoformat(),
        "cases": [{
            "id": str(c.id), "name": c.name, "category": c.category, "input": c.input,
            "expectations": c.expectations, "weight": c.weight, "source": c.source,
            "review_status": c.review_status,
        } for c in cases],
    }


def _run_payload(db: Session, run: EvalRun) -> dict:
    results = db.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id)).all()
    cases = {str(c.id): c for c in db.scalars(
        select(EvalCase).where(EvalCase.id.in_([r.case_id for r in results]))).all()}
    return {
        "id": str(run.id), "agent_id": str(run.agent_id), "pack_id": str(run.pack_id),
        "workflow_version_id": str(run.workflow_version_id), "status": run.status,
        "scorecard": run.scorecard, "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "results": [{
            "case_id": str(r.case_id),
            "case_name": cases.get(str(r.case_id)).name if cases.get(str(r.case_id)) else "?",
            "category": cases.get(str(r.case_id)).category if cases.get(str(r.case_id)) else "?",
            "run_id": str(r.run_id) if r.run_id else None,
            "passed": r.passed, "checks": r.checks,
        } for r in results],
    }


class PackBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    threshold: float = Field(default=70.0, ge=0, le=100)


@router.post("/api/agents/{agent_id}/eval-packs", status_code=201)
def create_pack(
    agent_id: uuid.UUID,
    body: PackBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    if db.get(AgentControlRecord, agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    pack = EvalPack(agent_id=agent_id, name=body.name, threshold=body.threshold, created_by=user.id)
    db.add(pack)
    db.flush()
    audit(db, user, "eval_pack_created", "eval_pack", str(pack.id), {"agent_id": str(agent_id)})
    db.commit()
    return _pack_payload(db, pack)


@router.get("/api/agents/{agent_id}/eval-packs")
def list_packs(agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    rows = db.scalars(select(EvalPack).where(EvalPack.agent_id == agent_id)).all()
    return [_pack_payload(db, p) for p in rows]


class CaseBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    category: str = "golden"
    input: str = Field(min_length=1, max_length=8000)
    expectations: dict = Field(default_factory=dict)
    weight: float = Field(default=1.0, gt=0, le=10)


@router.post("/api/eval-packs/{pack_id}/cases", status_code=201)
def add_case(
    pack_id: uuid.UUID,
    body: CaseBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    pack = db.get(EvalPack, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="pack not found")
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {CATEGORIES}")
    unknown = set(body.expectations) - _KNOWN_EXPECTATIONS
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown expectation keys: {sorted(unknown)}")
    if not body.expectations:
        raise HTTPException(status_code=422, detail="a case needs at least one expectation")
    case = EvalCase(pack_id=pack.id, name=body.name, category=body.category,
                    input=body.input, expectations=body.expectations, weight=body.weight)
    db.add(case)
    db.flush()
    audit(db, user, "eval_case_added", "eval_pack", str(pack.id), {"case_id": str(case.id)})
    db.commit()
    return _pack_payload(db, pack)


class RunPackBody(BaseModel):
    workflow_version_id: uuid.UUID | None = None


@router.post("/api/eval-packs/{pack_id}/run", status_code=201)
def run_pack(
    pack_id: uuid.UUID,
    body: RunPackBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.evaluator, Role.ai_engineer, Role.agent_owner)),
):
    pack = db.get(EvalPack, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="pack not found")
    agent = db.get(AgentControlRecord, pack.agent_id)

    if body.workflow_version_id:
        version = db.get(WorkflowVersion, body.workflow_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="workflow version not found")
    else:
        version = db.scalars(
            select(WorkflowVersion).join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .where(Workflow.agent_id == agent.id, WorkflowVersion.status == WorkflowStatus.active)
        ).first()
        if version is None:
            raise HTTPException(status_code=409, detail="agent has no active workflow version")

    run = eval_engine.run_pack(db, agent, pack, version, user)
    audit(db, user, "eval_run_completed", "agent", str(agent.id), {
        "eval_run_id": str(run.id), "score": run.scorecard.get("score"),
        "overall_passed": run.scorecard.get("overall_passed"),
        "workflow_version": version.version,
    })
    db.commit()
    events.emit("eval.completed", {"agent_id": str(agent.id), "eval_run_id": str(run.id),
                                   "overall_passed": run.scorecard.get("overall_passed")})
    return _run_payload(db, run)


@router.get("/api/agents/{agent_id}/eval-runs")
def list_runs(agent_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    rows = db.scalars(select(EvalRun).where(EvalRun.agent_id == agent_id)
                      .order_by(EvalRun.started_at.desc())).all()
    return [{"id": str(r.id), "pack_id": str(r.pack_id), "status": r.status,
             "scorecard": r.scorecard, "started_at": r.started_at.isoformat()} for r in rows]


@router.get("/api/eval-runs/{run_id}")
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    run = db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    return _run_payload(db, run)
