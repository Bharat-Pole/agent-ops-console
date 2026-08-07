"""Workflow validation (Pass 5): what saves must be executable and governed.

Layers:
1. structural — node vocabulary, id/edge integrity, reachability, guardrail-
   before-output for High/Restricted (reused from the deterministic validator)
2. executable — only node types with real handlers pass; unimplemented types
   (structured_query, evaluation) are rejected honestly, not stubbed
3. asset refs — rag pipelines must exist, prompts must have APPROVED versions,
   tools must be approved AND non-write (execution refuses write tools anyway;
   validation surfaces it before anything is approved)
4. cycles — back-edges are dropped with a recorded warning: v1 semantics are
   one execution per node in topological order (full LLM⇄tool loops arrive
   with function-calling in a later increment)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AssetStatus, PromptPack, PromptVersion, RagPipeline, ToolRecord,
    WRITE_PERMISSION_TYPES,
)
from ..recommender import deterministic
from ..recommender.engine import ensure_guardrail

RULES_VERSION = "workflow-validation-v1-increment-d"

IMPLEMENTED_TYPES = {
    "rag", "prompt", "llm", "tool_call", "mcp_call",
    "human_approval", "guardrail", "output_format",
}
# must match the kinds app/engine/handlers.run_tool_call can actually run
EXECUTABLE_IMPL_KINDS = {"http_api", "mcp", "none"}

UNIMPLEMENTED_NOTE = {
    "structured_query": "structured_query executes with data connectors (later increment)",
    "evaluation": "in-flow evaluation nodes land with the Evaluation Center (Increment E)",
}


@dataclass
class ValidationOutcome:
    graph: dict                      # possibly adjusted (guardrail auto-insert)
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)
    rules_version: str = RULES_VERSION

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict:
        return {"violations": self.violations, "warnings": self.warnings,
                "adjustments": self.adjustments, "rules_version": self.rules_version}


def topological_order(graph: dict) -> tuple[list[str], list[tuple[str, str]]]:
    """Kahn's algorithm; cycles resolved by dropping the offending back-edges.
    Returns (ordered_node_ids, dropped_edges)."""
    nodes = [n["id"] for n in graph.get("nodes", [])]
    edges = [(e["from"], e["to"]) for e in graph.get("edges", [])
             if e.get("from") in nodes and e.get("to") in nodes]
    indeg = {n: 0 for n in nodes}
    out: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        indeg[b] += 1
        out[a].append(b)
    order: list[str] = []
    queue = [n for n in nodes if indeg[n] == 0]
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in out[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    dropped: list[tuple[str, str]] = []
    if len(order) < len(nodes):  # cycle: drop back-edges among the remainder
        remaining = [n for n in nodes if n not in order]
        placed = set(order)
        while remaining:
            # place the remaining node with the fewest unplaced predecessors
            best = min(remaining, key=lambda n: sum(1 for a, b in edges if b == n and a not in placed))
            for a, b in edges:
                if b == best and a not in placed:
                    dropped.append((a, b))
            order.append(best)
            placed.add(best)
            remaining.remove(best)
    return order, dropped


def validate_workflow(db: Session, graph: dict, risk_tier: str) -> ValidationOutcome:
    graph, adjustments = ensure_guardrail(graph, risk_tier)
    outcome = ValidationOutcome(graph=graph, adjustments=list(adjustments))

    outcome.violations.extend(deterministic.validate_flow(graph, risk_tier))

    for node in graph.get("nodes", []):
        ntype = node.get("type")
        node_id = node.get("id")
        config = node.get("config") or {}
        if ntype in UNIMPLEMENTED_NOTE:
            outcome.violations.append(f'node "{node_id}": {UNIMPLEMENTED_NOTE[ntype]}')
            continue
        if ntype == "rag":
            ref = config.get("pipeline")
            if not ref:
                outcome.violations.append(f'rag node "{node_id}" has no config.pipeline')
            elif db.scalars(select(RagPipeline).where(RagPipeline.name == ref)).first() is None:
                outcome.violations.append(f'rag node "{node_id}": pipeline {ref!r} does not exist')
        elif ntype == "prompt":
            ref = config.get("pack_ref")
            if not ref:
                outcome.violations.append(f'prompt node "{node_id}" has no config.pack_ref')
            else:
                pack = db.scalars(select(PromptPack).where(PromptPack.slug == ref)).first()
                approved = pack and db.scalars(select(PromptVersion).where(
                    PromptVersion.pack_id == pack.id,
                    PromptVersion.status == AssetStatus.approved)).first()
                if not approved:
                    outcome.violations.append(
                        f'prompt node "{node_id}": pack {ref!r} has no APPROVED version')
        elif ntype in ("tool_call", "mcp_call"):
            ref = config.get("tool_ref")
            if not ref:
                if config.get("described_need") or config.get("unresolved_reference"):
                    outcome.warnings.append(
                        f'{ntype} node "{node_id}" is a described need — it will refuse at runtime '
                        "until a registered tool is referenced")
                else:
                    outcome.violations.append(f'{ntype} node "{node_id}" has no config.tool_ref')
            else:
                tool = db.scalars(select(ToolRecord).where(
                    ToolRecord.slug == ref, ToolRecord.status == AssetStatus.approved)
                    .order_by(ToolRecord.version.desc())).first()
                if tool is None:
                    outcome.violations.append(
                        f'{ntype} node "{node_id}": no APPROVED tool with slug {ref!r}')
                elif tool.permission_type in WRITE_PERMISSION_TYPES:
                    outcome.violations.append(
                        f'{ntype} node "{node_id}": tool {ref!r} is write-class — not executable in the '
                        "advisory-only base phase (Decision 0.3)")
                else:
                    kind = (tool.implementation or {}).get("kind")
                    if kind not in EXECUTABLE_IMPL_KINDS:
                        outcome.violations.append(
                            f'{ntype} node "{node_id}": tool {ref!r} has implementation kind {kind!r}, '
                            "which the engine cannot execute")
                    elif kind == "none":
                        outcome.warnings.append(
                            f'{ntype} node "{node_id}": tool {ref!r} has implementation "none" — it will '
                            "return an honest not-connected stub, not real data")

    _, dropped = topological_order(graph)
    for a, b in dropped:
        outcome.warnings.append(
            f"cycle: back-edge {a} → {b} is dropped at execution — nodes run once in topological "
            "order (v1 semantics; LLM⇄tool loops arrive with function-calling)")

    return outcome
