"""config → topology dispatch (locked precedence).

  1. coordinator+subagents (+ sub_agents non-empty) → pattern-refined:
       orchestration.pattern 'pipeline' → pipeline (sequential stages)
       orchestration.pattern 'parallel' → parallel (fan-out + join)
       else ('hub' / absent)            → supervisor (hub-spoke)
  2. explicit orchestration.graph, or orchestration_type == 'router' → dag
  3. rag_enabled → dag  (derived RAG retrieve→generate)
  4. else → single  (ReAct tool loop; binds any advisory tools)
"""
from __future__ import annotations

from enum import Enum

from .ir import AgentIR
from .loader import _v


class Topology(str, Enum):
    SINGLE = "single"
    DAG = "dag"
    SUPERVISOR = "supervisor"
    PIPELINE = "pipeline"
    PARALLEL = "parallel"


_PATTERN_TOPOLOGY = {"pipeline": Topology.PIPELINE, "parallel": Topology.PARALLEL}


def dispatch(agent: AgentIR) -> Topology:
    orch = agent.raw_config.get("config", {}).get("orchestration", {})
    otype = _v(orch.get("orchestration_type"))
    has_graph = bool(_v(orch.get("graph")))

    if otype == "coordinator+subagents" and agent.sub_agents:
        return _PATTERN_TOPOLOGY.get(agent.pattern, Topology.SUPERVISOR)
    if has_graph or otype == "router":
        return Topology.DAG
    if agent.rag.enabled:
        return Topology.DAG
    return Topology.SINGLE
