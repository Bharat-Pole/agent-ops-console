"""Resolve the MCP connectors an agent depends on.

The tool -> connector edge is a fixed foreign key on the tool row: a tool has
exactly one home system, decided when the tool is catalogued, never at bind or
run time. Nothing walked that edge, so an agent's *connector dependency set* --
the systems it will actually touch -- existed only as an implication of the
data, never as something the app could state.

This module materializes it once. Every gate that needs the answer reads it
here instead of re-deriving it:

  bind time     `services/tool_binding.py` -- warn when a bound tool's connector
                is degraded/offline (warn, never block: binding is a design-time
                declaration, connector health is a runtime condition)
  deploy time   Pre-Flight check #4 -- scope "MCP connectors available" to the
                connectors this agent actually needs
  run time      `tool_calls.system_accessed` (ROADMAP Phase 1) -- exactly
                `resolve_tool_connector()`, for one call
  gateway view  ROADMAP Phase 6 -- the same data, fanned out across all agents

Tools with `connector_id = NULL` are **local**: they need no MCP server at all
(5 of the 12 seeded tools). They are reported separately in `local_tools` --
never invent a placeholder connector for them.

Pure derivation over `agents` + `tools` + `connectors`. No schema, no writes.
"""

from typing import Any, Optional

from app.repositories import agents_repo, connectors_repo, tools_repo

# Connector statuses that make a served tool less than fully available. Mirrors
# the mapping in `connector_health.connector_health_to_tool_status`, from the
# other direction: `offline` is a hard blocker, `degraded` is a warning.
OFFLINE = "offline"
DEGRADED = "degraded"


def parse_tool_ref(ref: str) -> str:
    """`tools://incident_reader@v1` -> `incident_reader`.

    Agent configs store bound tools as versioned refs; the catalog is keyed by
    bare id. Tolerates a bare id so callers can pass either.
    """
    return ref.replace("tools://", "").split("@", 1)[0]


async def resolve_tool_connector(tool_id: str) -> Optional[str]:
    """The one system a tool reaches, or None if the tool is local/unknown.

    This is the whole "which MCP?" question. It is a lookup, not a choice --
    see the module docstring.
    """
    tool = await tools_repo.get_by_id(tool_id)
    return tool["connector_id"] if tool else None


async def resolve_connectors_for_tools(tool_ids: list[str]) -> dict[str, Any]:
    """Group a tool list into the connectors that serve it.

    Fetches the catalog once rather than per tool -- callers pass whole agent
    tool lists, and this runs on every Pre-Flight render.
    """
    wanted = [parse_tool_ref(t) for t in tool_ids]

    tools_by_id = {t["id"]: t for t in await tools_repo.get_all()}
    connectors_by_id = {c["id"]: c for c in await connectors_repo.get_all()}

    served: dict[str, list[str]] = {}
    local_tools: list[str] = []
    unknown_tools: list[str] = []

    for tid in wanted:
        tool = tools_by_id.get(tid)
        if tool is None:
            # A bound ref pointing at a tool that is no longer catalogued.
            # Surface it rather than dropping it silently.
            unknown_tools.append(tid)
            continue
        cid = tool["connector_id"]
        if cid is None:
            local_tools.append(tid)
        else:
            served.setdefault(cid, []).append(tid)

    connectors: list[dict[str, Any]] = []
    for cid, tids in served.items():
        connector = connectors_by_id.get(cid)
        if connector is None:
            # Referential integrity is enforced by the schema, so this is a
            # can't-happen. Reported rather than crashing the whole resolve.
            unknown_tools.extend(tids)
            continue
        connectors.append({**connector, "tools": sorted(tids)})

    # Stable order for the UI and for the verification suite.
    connectors.sort(key=lambda c: c["name"])

    return {
        "connectors": connectors,
        "local_tools": sorted(local_tools),
        "unknown_tools": sorted(unknown_tools),
        # `offline` is the deploy-time hard blocker; `unhealthy` is the
        # superset that also warns on `degraded`.
        "offline": sorted(c["id"] for c in connectors if c["status"] == OFFLINE),
        "unhealthy": sorted(c["id"] for c in connectors if c["status"] in (OFFLINE, DEGRADED)),
    }


async def resolve_agent_connectors(agent_id_str: str) -> Optional[dict[str, Any]]:
    """The MCP dependency set for one registered agent, or None if unknown."""
    agent = await agents_repo.get_by_id(agent_id_str)
    if agent is None:
        return None

    refs = agent["config"]["tooling"]["bound_tools"]["value"] or []
    resolved = await resolve_connectors_for_tools(refs)

    return {
        "agent_id": agent_id_str,
        "bound_tools": [parse_tool_ref(r) for r in refs],
        **resolved,
    }
