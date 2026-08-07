"""build_blockers — mirror of agent_onboard's inline blocker dict, adapted to the
console AgentRecord input. Blockers warn + annotate; the write-tool guardrail is
also enforced structurally in codegen (flagged tools are never bound).

Categories (agent_onboard parity): write_tools, required_config_unresolved,
unverified_permissions, hardcoded_credentials. Plus a console-specific
`unreviewed_write_adjacent` (null review_card on a write-adjacent config).
"""
from __future__ import annotations

from typing import Any

from .ir import AgentIR
from .loader import _v, _tool_name
from .writedetect import tool_is_write_capable, objective_has_write_intent

# profiles.json blocking_fields + the console's GOVERNANCE_CRITICAL_FIELDS
BLOCKING_FIELDS = ("system_prompt_ref", "model_primary", "tool_permission")
GOVERNANCE_CRITICAL = ("risk_tier", "tool_permission", "sensitivity")


def _leaf(cfg: dict, group: str, field: str) -> dict | None:
    node = cfg.get(group, {}).get(field)
    return node if isinstance(node, dict) else None


def build_blockers(agent: AgentIR) -> dict[str, Any]:
    record = agent.raw_config
    cfg = record.get("config", {})
    review_card = record.get("review_card") or None

    # (a) write-capable tools actually bound (advisory violation — should be none)
    bound_refs = _v(cfg.get("tooling", {}).get("bound_tools"), []) or []
    write_tools = sorted({_tool_name(r) for r in bound_refs if tool_is_write_capable(_tool_name(r))})

    # (b) required fields present?
    group_of = {"system_prompt_ref": "prompt", "model_primary": "model", "tool_permission": "tooling"}
    required_unresolved = [
        f for f in BLOCKING_FIELDS if not _v((_leaf(cfg, group_of[f], f) or {}), None)
    ]

    # (c) governance-critical leaves unverified / low-confidence (warnings)
    gc_group = {"risk_tier": "lifecycle", "tool_permission": "tooling", "sensitivity": "knowledge_sources"}
    unverified: list[str] = []
    for f in GOVERNANCE_CRITICAL:
        leaf = _leaf(cfg, gc_group[f], f)
        if leaf is None:
            continue
        if not leaf.get("verified_flag") or leaf.get("confidence") == "low":
            unverified.append(f)

    # console-specific: null review_card on a write-adjacent config
    write_adjacent = bool(write_tools) or objective_has_write_intent(agent.objective)
    unreviewed_write_adjacent = write_adjacent and review_card is None

    blockers = {
        "write_tools": write_tools,
        "required_config_unresolved": required_unresolved,
        "unverified_permissions": sorted(unverified),
        "hardcoded_credentials": [],  # console configs carry no secrets
        "unreviewed_write_adjacent": unreviewed_write_adjacent,
    }
    hard = bool(write_tools) or bool(required_unresolved) or unreviewed_write_adjacent
    blockers["has_hard_blockers"] = hard
    return blockers
