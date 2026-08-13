"""Workflow validation (Pass 5): what saves must be executable and governed.

Layers:
1. structural — node vocabulary, id/edge integrity, reachability, guardrail-
   before-output for High/Restricted (reused from the deterministic validator)
2. executable — only node types with real handlers pass; unimplemented types
   (structured_query, evaluation) are rejected honestly, not stubbed
3. asset refs — rag pipelines must exist, prompts must have APPROVED versions,
   tools must be approved AND non-write (execution refuses write tools anyway;
   validation surfaces it before anything is approved)
4. branching — edges ROUTE execution: `condition` objects are checked against
   the closed vocabulary in engine/conditions.py, every branch point needs a
   default edge, and guardrail-before-output must hold on EVERY path, not
   merely somewhere in a linear order
5. cycles — rejected. They were previously dropped with a warning, which was
   survivable only because edges did not route; now they would loop without
   bound. Governed loops (iteration cap + per-iteration policy) are the next
   increment.

Note the two distinct edge fields: `when` is the recommender's human-readable
annotation of intent, `condition` is the executable predicate. An annotated
edge with no condition warns rather than routes — it must not look like it
branches when it does not.
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
from . import conditions

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


def outgoing(graph: dict) -> dict[str, list[dict]]:
    """node id -> its outgoing edges, in authored order (which decides
    condition precedence at runtime: first match wins)."""
    node_ids = {n["id"] for n in graph.get("nodes", [])}
    out: dict[str, list[dict]] = {n: [] for n in node_ids}
    for edge in graph.get("edges", []):
        if edge.get("from") in node_ids and edge.get("to") in node_ids:
            out[edge["from"]].append(edge)
    return out


def default_edge(edges: list[dict]) -> dict | None:
    """The unconditional edge among a node's outgoing edges, if any.
    This is the `else` branch — where a run goes when no condition matches."""
    for edge in edges:
        if not edge.get("condition"):
            return edge
    return None


def _reachable_avoiding(graph: dict, entry: str, avoid_types: set[str]) -> set[str]:
    """Nodes reachable from entry WITHOUT passing through the given node types.

    Used to prove guardrail coverage: if an output node is still reachable once
    every guardrail is removed, some path reaches output ungoverned.
    """
    types = {n["id"]: n.get("type") for n in graph.get("nodes", [])}
    out = outgoing(graph)
    seen: set[str] = set()
    stack = [entry]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if types.get(current) in avoid_types:
            continue          # path stops here — the guardrail governs it
        for edge in out.get(current, []):
            if edge["to"] not in seen:
                stack.append(edge["to"])
    return seen


def _check_branching(graph: dict, risk_tier: str, outcome: ValidationOutcome) -> None:
    """Rules that only exist once edges actually route execution."""
    node_ids = {n["id"] for n in graph.get("nodes", [])}
    types = {n["id"]: n.get("type") for n in graph.get("nodes", [])}
    out = outgoing(graph)

    for edge in graph.get("edges", []):
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            continue
        # `when` is the RECOMMENDER's plain-language note about intent
        # ("route:refunds", "tool_calls"). It documents a branch; it does not
        # execute one. Saying so is the difference between a graph that looks
        # like it routes and one that does.
        annotation = edge.get("when")
        if isinstance(annotation, str) and annotation and not edge.get("condition"):
            outcome.warnings.append(
                f'edge {edge["from"]} → {edge["to"]} is annotated "{annotation}" by the '
                "recommendation but has no executable `condition` — it will be followed "
                "unconditionally until one is set")

        condition = edge.get("condition")
        if condition is None:
            continue
        for error in conditions.condition_errors(condition):
            outcome.violations.append(
                f'edge {edge["from"]} → {edge["to"]}: {error}')

    # A branch point needs an else. Without one, a run whose conditions all
    # miss would stop mid-workflow and produce no output — a silent dead end,
    # which is exactly the failure mode this platform refuses elsewhere.
    for node_id, edges in out.items():
        if len(edges) <= 1:
            continue
        conditional = [e for e in edges if e.get("condition")]
        if not conditional:
            outcome.violations.append(
                f'node "{node_id}" has {len(edges)} outgoing edges but no conditions — '
                "execution cannot choose between them; add a `condition` to all but one")
        elif default_edge(edges) is None:
            outcome.violations.append(
                f'node "{node_id}" branches on conditions with no default edge — add one '
                "unconditional edge so a run cannot dead-end when no condition matches")

    # Guardrail-before-output must hold on EVERY path, not merely somewhere in
    # a linear order. With branching, "a guardrail exists" stops being proof.
    if str(risk_tier).lower() in ("high", "restricted"):
        entries = [n for n in node_ids if not any(
            e["to"] == n for e in graph.get("edges", []) if e.get("from") in node_ids)]
        outputs = {n for n in node_ids if types.get(n) == "output_format"}
        guardrails = {n for n in node_ids if types.get(n) == "guardrail"}
        if outputs and guardrails:
            for entry in entries:
                ungoverned = _reachable_avoiding(graph, entry, {"guardrail"}) & outputs
                for node_id in sorted(ungoverned):
                    outcome.violations.append(
                        f'{risk_tier} risk: output node "{node_id}" is reachable from "{entry}" '
                        "without passing a guardrail — every path to output must be governed")


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

    _check_branching(graph, risk_tier, outcome)

    # Cycles are now a VIOLATION, not a warning. Previously edges only decided
    # ordering, so a back-edge could be dropped and the graph still ran once
    # through — misleading, but bounded. Now that edges route execution, a
    # cycle would loop until something else stopped it. Rejecting at design
    # time is the honest failure: an agentic loop needs an iteration cap and
    # per-iteration policy checks, which is the next increment, not a side
    # effect of drawing an arrow backwards.
    _, dropped = topological_order(graph)
    for a, b in dropped:
        outcome.violations.append(
            f"cycle: back-edge {a} → {b} would loop without bound — the engine routes edges now, "
            "so cycles are rejected until governed loops land (iteration cap + per-iteration "
            "policy checks)")

    return outcome
