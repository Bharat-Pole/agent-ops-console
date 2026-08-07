"""Telemetry + FinOps (Pass 8). ONE source of truth: workflow_runs +
run_steps. No second pipeline, no seeded data — an empty system reports
exactly that.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import audit
from .auth.deps import current_user_dep, require_role
from .db import get_db
from .models import (
    AgentControlRecord, Budget, FeedbackRecord, Role, RunStep, User, WorkflowRun, utcnow,
)

router = APIRouter(tags=["telemetry"])


def _percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    index = min(int(len(sorted_values) * pct), len(sorted_values) - 1)
    return sorted_values[index]


@router.get("/api/telemetry/summary")
def summary(
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
    agent_id: uuid.UUID | None = Query(default=None),
):
    stmt = select(WorkflowRun)
    if agent_id:
        stmt = stmt.where(WorkflowRun.agent_id == agent_id)
    runs = db.scalars(stmt).all()
    if not runs:
        return {"runs": 0, "note": "no traffic yet — this system reports only real runs"}

    run_ids = [r.id for r in runs]
    steps = db.scalars(select(RunStep).where(RunStep.run_id.in_(run_ids))).all()
    duration_by_run: dict[uuid.UUID, int] = {}
    tokens_in = tokens_out = 0
    cost = 0.0
    for s in steps:
        duration_by_run[s.run_id] = duration_by_run.get(s.run_id, 0) + s.duration_ms
        tokens_in += s.tokens_in
        tokens_out += s.tokens_out
        cost += s.cost
    durations = sorted(duration_by_run.values())

    by_status: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    for r in runs:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        by_mode[r.mode] = by_mode.get(r.mode, 0) + 1
    finished = by_status.get("completed", 0) + by_status.get("failed", 0)

    feedback = db.scalars(select(FeedbackRecord).where(FeedbackRecord.run_id.in_(run_ids))).all()

    return {
        "runs": len(runs),
        "by_status": by_status,
        "by_mode": by_mode,
        "error_rate": round(by_status.get("failed", 0) / finished, 3) if finished else None,
        "latency_ms": {"p50": _percentile(durations, 0.5), "p95": _percentile(durations, 0.95)},
        "tokens": {"in": tokens_in, "out": tokens_out},
        "cost_usd": round(cost, 6),
        "feedback": {"count": len(feedback),
                     "positive": sum(1 for f in feedback if f.rating > 0),
                     "negative": sum(1 for f in feedback if f.rating < 0)},
    }


@router.get("/api/telemetry/costs")
def costs(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    """Per-agent rollup + month-to-date vs budget. Costs = Σ step costs
    (tokens × catalog prices) — nothing else."""
    agents = db.scalars(select(AgentControlRecord)).all()
    month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    for agent in agents:
        runs = db.scalars(select(WorkflowRun).where(WorkflowRun.agent_id == agent.id)).all()
        if not runs:
            budget = db.scalars(select(Budget).where(Budget.agent_id == agent.id)).first()
            out.append({"agent_id": str(agent.id), "agent": agent.name,
                        "cost_center": agent.cost_center, "runs": 0, "cost_usd": 0.0,
                        "mtd_cost_usd": 0.0,
                        "budget": {"monthly_usd": budget.monthly_usd, "alert": False,
                                   "utilization": 0.0} if budget else None})
            continue
        run_ids = [r.id for r in runs]
        mtd_ids = {r.id for r in runs
                   if (r.started_at.replace(tzinfo=month_start.tzinfo)
                       if r.started_at.tzinfo is None else r.started_at) >= month_start}
        steps = db.scalars(select(RunStep).where(RunStep.run_id.in_(run_ids))).all()
        total = sum(s.cost for s in steps)
        mtd = sum(s.cost for s in steps if s.run_id in mtd_ids)
        budget = db.scalars(select(Budget).where(Budget.agent_id == agent.id)).first()
        out.append({
            "agent_id": str(agent.id), "agent": agent.name, "cost_center": agent.cost_center,
            "runs": len(runs), "cost_usd": round(total, 6), "mtd_cost_usd": round(mtd, 6),
            "budget": {
                "monthly_usd": budget.monthly_usd,
                "alert": mtd > budget.monthly_usd,
                "utilization": round(mtd / budget.monthly_usd, 3) if budget.monthly_usd else None,
            } if budget else None,
        })
    return out


class BudgetBody(BaseModel):
    monthly_usd: float = Field(gt=0)


@router.put("/api/agents/{agent_id}/budget")
def set_budget(
    agent_id: uuid.UUID,
    body: BudgetBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.finops_admin, Role.platform_admin)),
):
    if db.get(AgentControlRecord, agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    budget = db.scalars(select(Budget).where(Budget.agent_id == agent_id)).first()
    if budget is None:
        budget = Budget(agent_id=agent_id, monthly_usd=body.monthly_usd, created_by=user.id)
        db.add(budget)
    else:
        budget.monthly_usd = body.monthly_usd
    audit(db, user, "budget_set", "agent", str(agent_id), {"monthly_usd": body.monthly_usd})
    db.commit()
    return {"agent_id": str(agent_id), "monthly_usd": budget.monthly_usd}


class FeedbackBody(BaseModel):
    rating: int = Field(ge=-1, le=1)
    note: str = ""


@router.post("/api/runs/{run_id}/feedback", status_code=201)
def add_feedback(
    run_id: uuid.UUID,
    body: FeedbackBody,
    db: Session = Depends(get_db),
    user: User = Depends(current_user_dep),
):
    if body.rating == 0:
        raise HTTPException(status_code=422, detail="rating must be -1 or +1")
    if db.get(WorkflowRun, run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    record = FeedbackRecord(run_id=run_id, rating=body.rating, note=body.note, created_by=user.id)
    db.add(record)
    db.commit()
    return {"id": str(record.id), "run_id": str(run_id), "rating": body.rating}
