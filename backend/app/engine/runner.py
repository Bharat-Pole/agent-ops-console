"""Runner (Decision 5.1): the approved DAG compiles to a LangGraph chain in
topological order (v1 semantics — each node once; recorded in validation),
with a durable checkpointer so HumanApproval interrupts REALLY pause the run
across HTTP requests and process restarts. Every node writes a RunStep span —
the single telemetry source.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.models import get_model_adapter
from ..config import settings
from ..models import (
    AgentControlRecord, ModelCatalogEntry, RunHitl, RunStatus, RunStep, WorkflowRun, utcnow,
)
from .handlers import HANDLERS, EngineState, ExecCtx, NodeExecutionError
from . import conditions
from .validation import default_edge, outgoing, topological_order

_checkpointer_lock = threading.Lock()
_checkpointer = None


def get_checkpointer():
    """Durable checkpointer beside the platform DB: SqliteSaver locally,
    PostgresSaver under compose (same adapter seam as everything else)."""
    global _checkpointer
    with _checkpointer_lock:
        if _checkpointer is not None:
            return _checkpointer
        url = settings.database_url
        if url.startswith("sqlite"):
            db_path = url.split("///", 1)[-1]
            directory = os.path.dirname(db_path)
            target = os.path.join(directory, "engine_checkpoints.db") if directory else "engine_checkpoints.db"
            conn = sqlite3.connect(target, check_same_thread=False)
            _checkpointer = SqliteSaver(conn)
        else:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg import Connection
            conn = Connection.connect(url.replace("postgresql+psycopg://", "postgresql://"),
                                      autocommit=True)
            saver = PostgresSaver(conn)
            saver.setup()
            _checkpointer = saver
        return _checkpointer


def _cost_rates(db: Session) -> dict:
    return {m.model_ref: (m.cost_per_1k_in, m.cost_per_1k_out)
            for m in db.scalars(select(ModelCatalogEntry)).all()}


class _SpanWriter:
    def __init__(self, db: Session, run: WorkflowRun) -> None:
        self.db = db
        self.run = run
        self.ord = 0

    def write(self, node_id: str, node_type: str, status: str, duration_ms: int,
              detail: dict) -> None:
        self.ord += 1
        self.db.add(RunStep(
            run_id=self.run.id, ord=self.ord, node_id=node_id, node_type=node_type,
            status=status, duration_ms=duration_ms,
            tokens_in=int(detail.get("tokens_in") or 0),
            tokens_out=int(detail.get("tokens_out") or 0),
            cost=float(detail.get("cost") or 0.0),
            detail=detail,
        ))
        self.db.commit()  # trace survives whatever happens next


def _state_summary(state: EngineState) -> dict:
    return {
        "user_input": str(state.get("user_input", ""))[:500],
        "llm_output_preview": str(state.get("llm_output", ""))[:500],
        "tool_results": state.get("tool_results", [])[:5],
    }


def compile_graph(graph_dict: dict, ctx: ExecCtx, spans: _SpanWriter):
    order, _dropped = topological_order(graph_dict)
    nodes_by_id = {n["id"]: n for n in graph_dict.get("nodes", [])}

    builder = StateGraph(EngineState)

    def make_node(node: dict):
        node_id, node_type = node["id"], node["type"]
        config = node.get("config") or {}

        def run_node(state: EngineState) -> dict:
            if node_type == "human_approval":
                existing = ctx.db.scalars(select(RunHitl).where(
                    RunHitl.run_id == ctx.run.id, RunHitl.node_id == node_id)).first()
                if existing is None:
                    ctx.db.add(RunHitl(run_id=ctx.run.id, node_id=node_id,
                                       payload=_state_summary(state)))
                    ctx.db.commit()
                    spans.write(node_id, node_type, "paused", 0,
                                {"requirement": config.get("requirement", "approval")})
                decision = interrupt({"node_id": node_id, "summary": _state_summary(state)})
                if not decision.get("approved"):
                    spans.write(node_id, node_type, "failed", 0,
                                {"decision": decision, "note": "human approval DENIED"})
                    raise NodeExecutionError(
                        f"human approval denied at {node_id!r}: {decision.get('note') or 'no note'}")
                spans.write(node_id, node_type, "ok", 0, {"decision": decision})
                return {"hitl_decision": decision}

            handler = HANDLERS[node_type]
            t0 = time.monotonic()
            try:
                delta, detail = handler(state, config, ctx)
            except NodeExecutionError as exc:
                spans.write(node_id, node_type, "failed",
                            int((time.monotonic() - t0) * 1000), {"error": str(exc)})
                raise
            status = "refused" if detail.get("refused") else "ok"
            spans.write(node_id, node_type, status,
                        int((time.monotonic() - t0) * 1000), detail)
            return delta

        return run_node

    lg_ids = {node_id: f"n_{node_id}" for node_id in order}
    for node_id in order:
        builder.add_node(lg_ids[node_id], make_node(nodes_by_id[node_id]))

    if not order:
        return builder.compile(checkpointer=get_checkpointer())

    # Edges now ROUTE execution rather than merely implying an order. Before
    # this, the graph was wired START → order[0] → order[1] → … → END, so a
    # hub-and-spoke or branching graph rendered correctly and ran as a straight
    # line. Validation rejects cycles, so every path here terminates.
    out = outgoing(graph_dict)
    entry = order[0]
    builder.add_edge(START, lg_ids[entry])

    for node_id in order:
        edges = out.get(node_id, [])
        if not edges:
            builder.add_edge(lg_ids[node_id], END)
            continue

        conditional = [e for e in edges if e.get("condition")]
        if not conditional:
            # single unconditional successor (validation rejects the ambiguous
            # multi-edge-no-condition case)
            builder.add_edge(lg_ids[node_id], lg_ids[edges[0]["to"]])
            continue

        fallback = default_edge(edges)
        targets = {lg_ids[e["to"]] for e in edges}
        targets.add(END)

        def make_router(node_id: str, edges: list[dict], fallback: dict | None):
            def route(state: EngineState) -> str:
                # authored order decides precedence: first match wins
                for edge in edges:
                    when = edge.get("condition")
                    if when and conditions.evaluate(when, dict(state)):
                        spans.write(node_id, "edge", "ok", 0, {
                            "routed_to": edge["to"],
                            "matched": conditions.summarize(when)})
                        return lg_ids[edge["to"]]
                if fallback is not None:
                    spans.write(node_id, "edge", "ok", 0, {
                        "routed_to": fallback["to"], "matched": "default (no condition matched)"})
                    return lg_ids[fallback["to"]]
                # Validation requires a default, so this is defensive only —
                # end the run visibly rather than routing somewhere arbitrary.
                spans.write(node_id, "edge", "failed", 0, {
                    "error": "no condition matched and no default edge exists"})
                return END
            return route

        builder.add_conditional_edges(
            lg_ids[node_id], make_router(node_id, edges, fallback), sorted(targets))

    return builder.compile(checkpointer=get_checkpointer())


def _build_ctx(db: Session, run: WorkflowRun) -> ExecCtx:
    agent = db.get(AgentControlRecord, run.agent_id)
    risk = (agent.confirmed_risk_tier or agent.draft_risk_tier)
    return ExecCtx(
        db=db, adapter=get_model_adapter(db), run=run,
        risk_tier=risk.value if risk else "low",
        cost_rates=_cost_rates(db),
    )


def _apply_result(db: Session, run: WorkflowRun, result: dict) -> None:
    if result.get("__interrupt__"):
        run.status = RunStatus.paused_hitl
    else:
        run.status = RunStatus.completed
        run.output = {"final_output": result.get("final_output"),
                      "citation_check": result.get("citation_check")}
        run.finished_at = utcnow()
    db.commit()


def start_run(db: Session, run: WorkflowRun, graph_dict: dict, user_input: str) -> WorkflowRun:
    ctx = _build_ctx(db, run)
    compiled = compile_graph(graph_dict, ctx, _SpanWriter(db, run))
    config = {"configurable": {"thread_id": str(run.id)}}
    try:
        result = compiled.invoke({"user_input": user_input}, config)
        _apply_result(db, run, result)
    except NodeExecutionError as exc:
        run.status = RunStatus.failed
        run.error = str(exc)
        run.finished_at = utcnow()
        db.commit()
    return run


def resume_run(db: Session, run: WorkflowRun, graph_dict: dict, decision: dict) -> WorkflowRun:
    ctx = _build_ctx(db, run)
    compiled = compile_graph(graph_dict, ctx, _spans_continuing(db, run))
    config = {"configurable": {"thread_id": str(run.id)}}
    run.status = RunStatus.running
    db.commit()
    try:
        result = compiled.invoke(Command(resume=decision), config)
        _apply_result(db, run, result)
    except NodeExecutionError as exc:
        run.status = RunStatus.failed
        run.error = str(exc)
        run.finished_at = utcnow()
        db.commit()
    return run


def _spans_continuing(db: Session, run: WorkflowRun) -> _SpanWriter:
    writer = _SpanWriter(db, run)
    last = db.scalars(select(RunStep).where(RunStep.run_id == run.id)
                      .order_by(RunStep.ord.desc())).first()
    writer.ord = last.ord if last else 0
    return writer
