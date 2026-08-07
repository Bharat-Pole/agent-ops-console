"""Deterministic plan for building a DAG from an explicit GraphIR.

Shared by the live runtime (`runtime.py`) and the generated `dag/graph.py.j2`
so both construct the *same* StateGraph from a console `orchestration.graph`.

Node kinds collapse to three buildable kinds: retrieve | tool | llm (route /
aggregate / generate all render as an llm-invoke node). Tool nodes are dropped
when the agent has no advisory tools (a tool node with nothing to run is inert),
and edges into a dropped/absent node are elided (their source may become an END
terminal). Entry is nodes[0]; llm nodes bind tools only when a tool node exists.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DagPlan:
    entry: str
    nodes: list[tuple[str, str]]              # (id, eff_kind) eff_kind ∈ retrieve|tool|llm
    edges: list[tuple[str, str, bool]]        # (source, target, conditional?)
    terminals: list[str]                      # nodes wired straight to END
    bind_tools: bool                          # llm nodes bind ADVISORY_TOOLS?
    has_retrieve: bool


def _eff(kind: str) -> str:
    if kind == "retrieve":
        return "retrieve"
    if kind == "tool":
        return "tool"
    return "llm"  # llm | route | aggregate | generate | anything else


def plan_dag_graph(graph, has_tools: bool) -> DagPlan:
    kinds = {n.id: n.kind for n in graph.nodes}
    keep: list[tuple[str, str]] = []
    dropped: set[str] = set()
    for n in graph.nodes:
        ek = _eff(n.kind)
        if ek == "tool" and not has_tools:
            dropped.add(n.id)
            continue
        keep.append((n.id, ek))
    kept_ids = {i for i, _ in keep}

    entry = graph.entry
    if entry not in kept_ids and keep:
        entry = keep[0][0]

    edges: list[tuple[str, str, bool]] = []
    outgoing: set[str] = set()
    for e in graph.edges:
        if e.source not in kept_ids or e.target in dropped or e.target not in kept_ids:
            continue
        outgoing.add(e.source)
        edges.append((e.source, e.target, kinds.get(e.target) == "tool"))

    terminals = [i for i, ek in keep if i not in outgoing and ek != "tool"]
    bind_tools = has_tools and any(ek == "tool" for _, ek in keep)
    has_retrieve = any(ek == "retrieve" for _, ek in keep)
    return DagPlan(entry=entry, nodes=keep, edges=edges, terminals=terminals,
                   bind_tools=bind_tools, has_retrieve=has_retrieve)
