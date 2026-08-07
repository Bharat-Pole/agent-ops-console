"""Map free-text hitl_gate_placement → LangGraph interrupt points.

LangGraph interrupt_before/after take NODE names, but the console placements are
free text. Rules (pinned in the plan):
  - edge form 'X → Y' / 'X -> Y'      → interrupt_before Y (the destination node)
  - node/sub-agent name form           → interrupt_before that node
  - 'per-tool-call (runtime)'          → interrupt before the ToolNode ('tools')
  - non-node lifecycle gates (e.g.
    'pre-deploy') / unresolvable target → NOT a graph interrupt; surfaced as a
    human-process note (README + a graph.py comment)

PARALLEL footgun (validated on langgraph 1.2.10): `interrupt_before` on a SINGLE
parallel branch pauses the ENTIRE fan-out superstep — no sibling branch runs
until resume. For parallel agents prefer gating the `aggregate` join node
(edge form 'X → aggregate' or bare 'aggregate').
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .ir import HitlGateIR


@dataclass
class HitlMapping:
    interrupt_before: list[str]        # node names to interrupt before
    tool_call_interrupt: bool          # interrupt before every tool execution
    process_gates: list[str]           # human-process gates (not graph interrupts)


_EDGE_RE = re.compile(r"([A-Za-z0-9_]+)\s*(?:->|→|to)\s*([A-Za-z0-9_]+)")


def map_hitl(gates: list[HitlGateIR], node_names: set[str]) -> HitlMapping:
    interrupt_before: list[str] = []
    tool_call = False
    process: list[str] = []

    for g in gates:
        p = (g.placement or "").strip()
        low = p.lower()
        if "per-tool-call" in low or "per tool call" in low or ("runtime" in low and "tool" in low):
            tool_call = True
            continue
        m = _EDGE_RE.search(p)
        if m and m.group(2) in node_names:
            if m.group(2) not in interrupt_before:
                interrupt_before.append(m.group(2))
            continue
        # bare node/sub-agent name?
        matched = next((n for n in sorted(node_names) if n in low.replace(" ", "_")), None)
        if matched:
            if matched not in interrupt_before:
                interrupt_before.append(matched)
            continue
        # otherwise a human-process / lifecycle gate (e.g. pre-deploy)
        process.append(f"{p} — {g.trigger}" if g.trigger else p)

    return HitlMapping(interrupt_before=interrupt_before, tool_call_interrupt=tool_call, process_gates=process)
