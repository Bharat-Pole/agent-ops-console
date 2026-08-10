"""The policy-enforcing MCP gateway — Phase 6.

Deck slide 21's headline element: *"Standard architecture for routing agent
requests to approved tools, systems, and data sources"*, whose stated purpose is
to prevent *"each agent from creating separate point-to-point integrations"*.
This module is that architecture. It closes elements **1 (MCP Gateway Pattern)**,
**4 (Data Boundary Controls)** and **5 (Identity & Access Pattern)** — the last
three unbuilt cells of the seven.

What changes here, and why it matters more than it looks
-------------------------------------------------------
Every governance rule this project has was, until now, enforced at *design time*:
`bind_tool()` decides what an agent may be configured to use, and the Phase 1
audit trail records what a client *said* it then did. There was no point at which
the platform stood between an agent and a system at the moment of the call.

This is that point, and it is deny-by-default: a call reaches a tool only by
passing every checkpoint in `CHECKPOINTS`, in order. Because the gateway performs
the invocation itself, it starts its own clock and reads its own response —
so `result_status` and `latency_ms` stop being claims. That is the measurement
half of `CONCERNS.md` **R7**, and it is only reachable because Phase 5A gave us a
real socket to call.

**The honest claim after this phase** is *"authoritative for every call that
passes through the gateway"* — not "tamper-proof runtime evidence" full stop.
Two asterisks stay, and both are stated in the data rather than in a footnote:

  - `tool_calls.gateway = FALSE` rows are client-reported (the Phase 1 path,
    still live). Observed and reported must never be shown as one number.
  - `invocation = 'simulated'` means the *policy decision* was real but the tool
    body was not — a local tool has no MCP server to call. Only
    `invocation = 'live'` carries a latency that measures a real system.

The identity asterisk
---------------------
`principal` is a persona from the console's own switcher, not a federated IdP
subject. **The enforcement is real and the principal is simulated**, and saying
only the first half would be the most misleading sentence in this workstream.
Building a real identity store is explicitly out of scope — the SOW's boundary
table says *"will not build a separate user management or identity store …
integrate with Brightspeed SSO / IdP"*. `CONCERNS.md` R6.

Why a denial returns 200
------------------------
A denied call is the single most valuable row this table holds, so the gateway
**always writes a row and always returns a verdict**. Refusing with a 4xx would
mean the better-behaved a caller is, the more evidence exists about it — exactly
backwards. Only a malformed *request* (no agent, no tool) raises, because there
is then nothing truthful to record. Same principle as
`tool_call_log.record_tool_call()` recording rather than rejecting an
unauthorized call.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from app.repositories import agents_repo, connectors_repo, tool_calls_repo, tools_repo  # noqa: F401
from app.services import mcp_client
from app.services.connector_health import is_live_connector
from app.services.connector_resolution import parse_tool_ref
from app.services.tool_call_log import CONSUMERS, record_gateway_call

# The persona switcher is the identity source. Enforcement is real; the
# principal is simulated — see the module docstring.
PRINCIPALS = ("business_owner", "platform_engineer", "governance_officer", "team_lead")

# Rolling window for the rate limit, in seconds. `rate_limit_per_min` is named
# for this window, so the two must move together.
RATE_WINDOW_SECONDS = 60

# A governance path that requires a human on the call itself, not just on the
# agent's configuration. Mirrors the Playground's runtime HITL gate — which was
# client-side only until this module made it server-enforced.
HITL_GOVERNANCE_PATHS = ("critical",)


# ---------------------------------------------------------------------------
# The checkpoint chain
# ---------------------------------------------------------------------------
#
# Ordered, and the order is load-bearing:
#
#   · existence before policy — you cannot evaluate a rule about a tool that is
#     not in the catalog, and "not found" is a more useful denial than a
#     downstream rule failing for a confusing reason;
#   · `write_capable` before `approval`, mirroring `bind_tool()` exactly. An
#     approved write-capable tool must be denied *on write-capability*, or
#     approval becomes a laundering path for the locked invariant
#     (`CONCERNS.md` Q6 is the decision to change that; it is not a code tweak);
#   · policy before invocation, obviously — but also `rate_limit` last among the
#     policy checks, so a caller cannot burn another caller's budget by making
#     calls that were going to be denied on governance grounds anyway.
#
# Exposed through `GET /v1/gateway/policy` so the console renders this list
# rather than restating it. A second copy in TypeScript would be a second thing
# to keep in step with the enforcement.
CHECKPOINTS: tuple[dict[str, str], ...] = (
    {
        "id": "identity",
        "label": "Identity",
        "source": "slide 21 element 5 · Blueprint §8.1",
        "description": "The caller presents a known principal. Enforcement is real; the principal is a console persona, not an IdP subject.",
    },
    {
        "id": "catalog",
        "label": "Tool in catalog",
        "source": "Tool Registry",
        "description": "The tool exists in the governed catalog. An uncatalogued capability has no policy attached to it and so cannot be called.",
    },
    {
        "id": "agent",
        "label": "Agent registered",
        "source": "Agent Registry",
        "description": "The calling agent exists in the registry, so the call can be attributed to an owned, risk-tiered subject.",
    },
    {
        "id": "write_capable",
        "label": "Advisory-only scope",
        "source": "slide 25 · SOW boundary",
        "description": "Write-capable tools are catalogued but never callable. Checked before approval so consent can never widen it.",
    },
    {
        "id": "approval",
        "label": "Tool approved",
        "source": "Blueprint §11 · Phase 3.2",
        "description": "The tool has been through the shared approval queue. Discovery and cataloguing are not consent.",
    },
    {
        "id": "allowlist",
        "label": "Bound to this agent",
        "source": "R8 guard · bound_tools",
        "description": "The tool is on this agent's bound_tools — the per-agent allowlist, already guarded on all four write paths.",
    },
    {
        "id": "connector_health",
        "label": "Connector reachable",
        "source": "Phase 0 resolver",
        "description": "The serving connector is not offline. Bind warns and deploy blocks; a call blocks, because health is now a runtime fact.",
    },
    {
        "id": "identity_binding",
        "label": "Approved identity",
        "source": "slide 21 element 5",
        "description": "When a connector declares approved identities, the principal must be one of them. Undeclared is recorded as a gap.",
    },
    {
        "id": "data_boundary",
        "label": "Data boundary",
        "source": "slide 21 element 4",
        "description": "When a connector declares allowed datasets, the call must name one of them. Declared fields redact the response.",
    },
    {
        "id": "hitl",
        "label": "Human in the loop",
        "source": "slide 22 · Governance & HITL",
        "description": "A critical-path agent needs a human decision on the call itself, not only on its configuration.",
    },
    {
        "id": "rate_limit",
        "label": "Rate limit",
        "source": "Blueprint §3.4 · D6",
        "description": "Per agent, per tool, over a rolling minute, counted from the audit trail rather than a second source of truth.",
    },
)

CHECKPOINT_IDS = tuple(c["id"] for c in CHECKPOINTS)


class _Trace:
    """Records the outcome of each checkpoint so the console can show the chain.

    The trace is what turns the gateway from a boolean into an explanation —
    which is the difference between an operator trusting a denial and filing a
    bug about it.
    """

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def add(self, checkpoint: str, status: str, detail: Optional[str] = None) -> None:
        self.entries.append({"checkpoint": checkpoint, "status": status, "detail": detail})

    def pass_(self, checkpoint: str, detail: Optional[str] = None) -> None:
        self.add(checkpoint, "pass", detail)

    def warn(self, checkpoint: str, detail: str) -> None:
        self.add(checkpoint, "warn", detail)

    def skip(self, checkpoint: str, detail: str) -> None:
        self.add(checkpoint, "skipped", detail)

    def deny(self, checkpoint: str, detail: str) -> None:
        self.add(checkpoint, "deny", detail)


async def call_tool(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the checkpoint chain and, if it passes end to end, invoke the tool.

    Raises ValueError only for a request too malformed to record.
    """
    agent_id = payload.get("agentId") or payload.get("agent_id")
    tool_raw = payload.get("toolId") or payload.get("tool_id") or payload.get("toolInvoked")

    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agentId is required.")
    if not isinstance(tool_raw, str) or not tool_raw.strip():
        raise ValueError("toolId is required.")

    consumer = payload.get("consumer") or "playground"
    if consumer not in CONSUMERS:
        raise ValueError(f"consumer must be one of {', '.join(CONSUMERS)}.")

    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object.")

    agent_id = agent_id.strip()
    tool_id = parse_tool_ref(tool_raw.strip())
    principal = payload.get("principal")
    team = payload.get("team")
    dataset = payload.get("dataset")
    hitl_approved = payload.get("hitlApproved")
    request_id = payload.get("requestId") or payload.get("request_id")

    trace = _Trace()
    warnings: list[str] = []

    # -- 1. identity ---------------------------------------------------------
    if not isinstance(principal, str) or principal not in PRINCIPALS:
        trace.deny("identity", f"Unknown principal {principal!r}.")
        return await _deny(
            agent_id, tool_id, "identity",
            f"No approved identity presented — {principal!r} is not a known principal.",
            trace, consumer, request_id, principal, team, warnings,
        )
    trace.pass_("identity", f"principal={principal}")

    # -- 2. catalog ----------------------------------------------------------
    tool = await tools_repo.get_by_id(tool_id)
    if tool is None:
        trace.deny("catalog", f"{tool_id} is not in the tool catalog.")
        return await _deny(
            agent_id, tool_id, "catalog",
            f"{tool_id} is not in the tool catalog — no policy exists for it.",
            trace, consumer, request_id, principal, team, warnings,
        )
    trace.pass_("catalog", f"permission={tool['permission_ceiling']}")

    permission = tool["permission_ceiling"]
    connector_id = tool["connector_id"]

    # -- 3. agent ------------------------------------------------------------
    agent = await agents_repo.get_by_id(agent_id)
    if agent is None:
        trace.deny("agent", f"{agent_id} is not registered.")
        return await _deny(
            agent_id, tool_id, "agent",
            f"Agent {agent_id} is not registered — the call cannot be attributed.",
            trace, consumer, request_id, principal, team, warnings,
            permission=permission, system_accessed=connector_id,
        )
    trace.pass_("agent", f"governance_path={agent['governance_path']}")

    deny = _denier(
        agent_id, tool_id, trace, consumer, request_id, principal, team, warnings,
        permission, connector_id,
    )

    # -- 4. write-capable ----------------------------------------------------
    # The locked invariant, and the only checkpoint whose answer is the same for
    # every agent, every principal and every connector.
    if tool["write_capable"]:
        trace.deny("write_capable", f"{tool_id} is write-capable.")
        return await deny(
            "write_capable",
            f"{tool_id} is write-capable — advisory-only scope. Catalogued, never callable.",
        )
    trace.pass_("write_capable", "read-only")

    # -- 5. approval ---------------------------------------------------------
    if tool["approval_state"] != "approved":
        state = tool["approval_state"]
        trace.deny("approval", f"approval_state={state}")
        return await deny("approval", f"{tool_id} is {state} approval — not callable until approved.")
    trace.pass_("approval", "approved")

    # -- 6. per-agent allowlist ----------------------------------------------
    # `bound_tools` is the allowlist. A second `allowed_agents` list on the tool
    # would be a second thing that has to agree with this one, and the two would
    # drift the first time anyone edited either (CONCERNS Q7).
    bound = {parse_tool_ref(r) for r in (agent["config"]["tooling"]["bound_tools"]["value"] or [])}
    if tool_id not in bound:
        trace.deny("allowlist", f"{tool_id} not in bound_tools")
        return await deny("allowlist", f"{tool_id} is not bound to this agent — unauthorized tool call.")
    trace.pass_("allowlist", f"{len(bound)} tool(s) bound")

    # -- 7-9. connector-scoped policy ----------------------------------------
    connector: Optional[dict[str, Any]] = None
    if connector_id is None:
        # A local tool serves itself. Skipping is correct, not a gap: there is
        # no server to be unreachable, no identity to bind, no dataset to bound.
        for cp in ("connector_health", "identity_binding", "data_boundary"):
            trace.skip(cp, "local tool — no MCP connector")
    else:
        connector = await connectors_repo.get_by_id(connector_id)
        if connector is None:
            trace.deny("connector_health", f"{connector_id} not found")
            return await deny("connector_health", f"Connector {connector_id} is not registered.")

        if connector["status"] == "offline":
            trace.deny("connector_health", f"{connector['name']} is offline")
            return await deny(
                "connector_health",
                f"{connector['name']} is offline — the call cannot reach {tool_id}.",
            )
        if connector["status"] == "degraded":
            warnings.append(f"{connector['name']} is degraded — the call may be slow or partial.")
            trace.warn("connector_health", f"{connector['name']} is degraded")
        else:
            trace.pass_("connector_health", connector["status"])

        # identity binding — slide 21 element 5
        approved_identities = connector["approved_identities"] or []
        if approved_identities:
            if principal not in approved_identities:
                trace.deny("identity_binding", f"{principal} not approved for {connector['name']}")
                return await deny(
                    "identity_binding",
                    f"{principal} is not an approved identity for {connector['name']}.",
                )
            trace.pass_("identity_binding", f"{principal} approved for {connector['name']}")
        else:
            # Undeclared is a real governance gap, so it is recorded on the call
            # rather than passing silently — the same treatment a NULL
            # `tools.owner` gets. Silence here would be the gateway's easiest
            # way to look more governed than it is.
            warnings.append(f"{connector['name']} declares no approved identities.")
            trace.warn("identity_binding", "no approved identities declared")

        # data boundary — slide 21 element 4
        allowed_datasets = connector["allowed_datasets"] or []
        if allowed_datasets:
            if not isinstance(dataset, str) or not dataset.strip():
                trace.deny("data_boundary", "no dataset named")
                return await deny(
                    "data_boundary",
                    f"{connector['name']} enforces a data boundary — the call must name a dataset.",
                )
            if dataset not in allowed_datasets:
                trace.deny("data_boundary", f"{dataset} outside the boundary")
                return await deny(
                    "data_boundary",
                    f"Dataset {dataset!r} is outside {connector['name']}'s declared boundary.",
                )
            trace.pass_("data_boundary", f"dataset={dataset}")
        else:
            warnings.append(f"{connector['name']} declares no data boundary.")
            trace.warn("data_boundary", "no allowed datasets declared")

    # -- 10. HITL ------------------------------------------------------------
    if agent["governance_path"] in HITL_GOVERNANCE_PATHS:
        if hitl_approved is not True:
            trace.deny("hitl", "critical path, no human decision on the call")
            return await deny(
                "hitl",
                f"{agent_id} is on the critical governance path — this call needs a human decision.",
            )
        trace.pass_("hitl", "human approved this call")
    else:
        trace.skip("hitl", f"governance_path={agent['governance_path']} needs no per-call gate")

    # -- 11. rate limit ------------------------------------------------------
    limit = (connector or {}).get("rate_limit_per_min") or 60
    recent = await tool_calls_repo.count_recent(agent_id, tool_id, RATE_WINDOW_SECONDS)
    if recent >= limit:
        trace.deny("rate_limit", f"{recent}/{limit} in the last {RATE_WINDOW_SECONDS}s")
        return await deny(
            "rate_limit",
            f"Rate limit reached — {recent} calls to {tool_id} in the last "
            f"{RATE_WINDOW_SECONDS}s (limit {limit}).",
        )
    trace.pass_("rate_limit", f"{recent}/{limit} in the last {RATE_WINDOW_SECONDS}s")

    # -- invoke --------------------------------------------------------------
    outcome = await _invoke(tool, connector, arguments)

    redacted: list[str] = []
    if outcome["structured"] is not None and connector is not None:
        outcome["structured"], redacted = _apply_field_boundary(
            outcome["structured"], connector["allowed_fields"] or []
        )
    if redacted:
        warnings.append(f"{len(redacted)} field(s) redacted by the data boundary.")

    written = await record_gateway_call(
        {
            "agent_id": agent_id,
            "tool_id": tool_id,
            "request_id": request_id,
            "consumer": consumer,
            "principal": principal,
            "team": team if isinstance(team, str) else None,
            "decision": "allow",
            "denied_by": None,
            "reason": outcome["error"] or (" ".join(warnings) if warnings else None),
            "invocation": outcome["invocation"],
            "result_status": outcome["result_status"],
            "latency_ms": outcome["latency_ms"],
            "system_accessed": connector_id,
            "permission": permission,
            "redacted_fields": redacted,
        }
    )

    return {
        "allowed": True,
        "decision": "allow",
        "deniedBy": None,
        "reason": None,
        "checkpoints": trace.entries,
        "warnings": warnings,
        "result": {
            "invocation": outcome["invocation"],
            "content": outcome["content"],
            "structured": outcome["structured"],
            "error": outcome["error"],
            "latencyMs": outcome["latency_ms"],
        },
        "redacted": redacted,
        **written,
    }


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------


async def _invoke(
    tool: dict[str, Any], connector: Optional[dict[str, Any]], arguments: dict[str, Any]
) -> dict[str, Any]:
    """Run the tool and report what was observed.

    Two paths, and the difference is recorded on the row rather than smoothed
    over:

      **live** — the connector speaks Streamable HTTP at a reachable endpoint, so
      this is a real `tools/call`. The latency is a real system's latency and the
      result status is a real outcome. This is the only case in which the audit
      row is runtime evidence.

      **simulated** — a local tool, or a connector that was never meant to
      resolve (the five seeded ones). The *policy decision above was still fully
      enforced*; only the tool body is stand-in. The row says so.

    A failed live call is deliberately **not** cascaded into connector health.
    One call failing is not a health verdict — the healthcheck owns that column,
    and letting any timeout mark a connector offline would make the catalog
    flap under load.
    """
    if connector is not None and is_live_connector(connector):
        timeout_s = max(0.1, (connector.get("timeout_ms") or 10000) / 1000)
        remote_name = tool["remote_tool_id"] or tool["id"]
        try:
            # The SDK enforces a per-round-trip timeout; this outer guard catches
            # a server that accepts the socket and then goes quiet, which the
            # inner one does not.
            result = await asyncio.wait_for(
                mcp_client.call_remote_tool(
                    connector["endpoint"], remote_name, arguments, timeout_s
                ),
                timeout=timeout_s + 0.5,
            )
        except asyncio.TimeoutError:
            return {
                "invocation": "live",
                "result_status": "error",
                "latency_ms": int(timeout_s * 1000),
                "content": None,
                "structured": None,
                "error": f"Timed out after {timeout_s:.1f}s calling {remote_name}.",
            }

        return {
            "invocation": "live",
            "result_status": "ok" if (result["ok"] and not result["is_error"]) else "error",
            "latency_ms": result["latency_ms"],
            "content": result["content"],
            "structured": result["structured"],
            "error": result["error"],
        }

    # Simulated. A canned fixture if the catalog has one; otherwise a string that
    # says plainly what it is. Never a fabricated failure — inventing an error
    # would be inventing evidence just as much as inventing a success.
    fixtures = tool.get("result_fixtures") or []
    content = fixtures[0] if fixtures else f"[simulated] {tool['id']} returned no fixture."
    return {
        "invocation": "simulated",
        "result_status": "ok",
        "latency_ms": 0,
        "content": content,
        "structured": None,
        "error": None,
    }


def _apply_field_boundary(
    structured: Any, allowed_fields: list[str]
) -> tuple[Any, list[str]]:
    """Drop top-level response fields the connector has not declared.

    Top-level only, and that limit is deliberate rather than lazy: a recursive
    filter over an arbitrary tool's output would silently reshape payloads whose
    structure we do not own, and a boundary nobody can predict is worse than one
    with a stated edge. Declaring no fields means no redaction — the same
    "undeclared, not deny-all" reading as `allowed_datasets`.
    """
    if not allowed_fields or not isinstance(structured, dict):
        return structured, []

    keep = {k: v for k, v in structured.items() if k in allowed_fields}
    removed = sorted(k for k in structured if k not in allowed_fields)
    return keep, removed


# ---------------------------------------------------------------------------
# Denial
# ---------------------------------------------------------------------------


def _denier(
    agent_id: str,
    tool_id: str,
    trace: _Trace,
    consumer: str,
    request_id: Optional[str],
    principal: Optional[str],
    team: Optional[str],
    warnings: list[str],
    permission: str,
    connector_id: Optional[str],
):
    """Bind the call's context so each checkpoint's denial is one short line."""

    async def deny(checkpoint: str, reason: str) -> dict[str, Any]:
        return await _deny(
            agent_id, tool_id, checkpoint, reason, trace, consumer, request_id,
            principal, team, warnings, permission=permission, system_accessed=connector_id,
        )

    return deny


async def _deny(
    agent_id: str,
    tool_id: str,
    checkpoint: str,
    reason: str,
    trace: _Trace,
    consumer: str,
    request_id: Optional[str],
    principal: Optional[str],
    team: Optional[str],
    warnings: list[str],
    permission: str = "unknown",
    system_accessed: Optional[str] = None,
) -> dict[str, Any]:
    """Record the denial and return the verdict.

    `latency_ms = 0` and `invocation = 'none'` because nothing was called — a
    denial that reported a latency would be describing work that never happened.

    Note the coercion below: the `identity` checkpoint denies precisely when
    `principal` is not a string, and that value still has to be written to a TEXT
    column. Recording it as NULL is the honest rendering of "no usable identity
    was presented" — the reason string carries what was actually sent.
    """
    written = await record_gateway_call(
        {
            "agent_id": agent_id,
            "tool_id": tool_id,
            "request_id": request_id,
            "consumer": consumer,
            "principal": principal if isinstance(principal, str) else None,
            "team": team if isinstance(team, str) else None,
            "decision": "deny",
            "denied_by": checkpoint,
            "reason": reason,
            "invocation": "none",
            "result_status": "blocked",
            "latency_ms": 0,
            "system_accessed": system_accessed,
            "permission": permission,
            "redacted_fields": [],
        }
    )

    return {
        "allowed": False,
        "decision": "deny",
        "deniedBy": checkpoint,
        "reason": reason,
        "checkpoints": trace.entries,
        "warnings": warnings,
        "result": None,
        "redacted": [],
        **written,
    }


# ---------------------------------------------------------------------------
# Policy description (read-only)
# ---------------------------------------------------------------------------


async def describe_policy() -> dict[str, Any]:
    """The checkpoint chain plus each connector's declared policy.

    Read-only, and the source of truth for the console's rendering of the
    gateway. `undeclared` is computed here so the UI cannot disagree with the
    enforcement about what counts as a gap.
    """
    connectors = await connectors_repo.get_all()

    policies = []
    for c in connectors:
        undeclared = [
            name
            for name, declared in (
                ("approved_identities", bool(c["approved_identities"])),
                ("allowed_datasets", bool(c["allowed_datasets"])),
                ("allowed_fields", bool(c["allowed_fields"])),
                ("service_account", bool(c["service_account"])),
                ("iam_principal", bool(c["iam_principal"])),
            )
            if not declared
        ]
        policies.append(
            {
                "connector_id": c["id"],
                "name": c["name"],
                "status": c["status"],
                "allowed_datasets": c["allowed_datasets"],
                "allowed_fields": c["allowed_fields"],
                "approved_identities": c["approved_identities"],
                "service_account": c["service_account"],
                "iam_principal": c["iam_principal"],
                "rate_limit_per_min": c["rate_limit_per_min"],
                "timeout_ms": c["timeout_ms"],
                "live": is_live_connector(c),
                "undeclared": undeclared,
            }
        )

    return {
        "checkpoints": list(CHECKPOINTS),
        "principals": list(PRINCIPALS),
        "rateWindowSeconds": RATE_WINDOW_SECONDS,
        "policies": policies,
    }


async def describe_graph() -> dict[str, Any]:
    """Agents → gateway → connectors → systems, as data — Phase 7.

    Slide 21's headline element, and the one an executive looks for: *"prevents
    each agent from creating separate point-to-point integrations."* The picture
    only means something once the checkpoints it draws are real, which is why
    this is built after Phase 6 rather than before it.

    **Strictly a derivation.** No new tables, no new enforcement, no new
    persisted state — every field here comes from `connector_resolution`, the
    connector rows, `CHECKPOINTS`, and aggregate counts over `tool_calls`. If
    this function ever needs to *store* something, the phase before it was left
    unfinished.

    Two modelling choices worth keeping:

    - **Local tools are counted, never given a fake connector node.** Five of the
      twelve seeded tools reach no MCP server at all. Drawing a placeholder box
      for them would make the diagram tidier and would misrepresent the estate —
      the whole point of the picture is which systems are actually reached.
    - **Agents with no bound tools still appear**, with zero edges. An agent that
      touches nothing is a real and interesting state (two seeded agents are in
      it), and dropping it would quietly overstate how connected the platform is.
    """
    agents = await agents_repo.get_all()
    connectors = await connectors_repo.get_all()
    tools = {t["id"]: t for t in await tools_repo.get_all()}
    traffic = await tool_calls_repo.gateway_summary()

    connectors_by_id = {c["id"]: c for c in connectors}

    agent_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for agent in agents:
        aid = agent["config"]["identity"]["agent_id"]["value"]
        refs = agent["config"]["tooling"]["bound_tools"]["value"] or []
        bound = [parse_tool_ref(r) for r in refs]

        served: dict[str, list[str]] = {}
        local: list[str] = []
        unknown: list[str] = []
        for tid in bound:
            tool = tools.get(tid)
            if tool is None:
                unknown.append(tid)
            elif tool["connector_id"] is None:
                local.append(tid)
            else:
                served.setdefault(tool["connector_id"], []).append(tid)

        for cid, tids in sorted(served.items()):
            connector = connectors_by_id.get(cid)
            edges.append(
                {
                    "agent_id": aid,
                    "connector_id": cid,
                    "tools": sorted(tids),
                    # Carried on the edge so the view can colour a line without
                    # re-joining to the connector list — the same reason
                    # `connector_resolution` returns `offline`/`unhealthy`.
                    "status": connector["status"] if connector else "unknown",
                }
            )

        agent_nodes.append(
            {
                "agent_id": aid,
                "name": agent["config"]["identity"]["agent_name"]["value"],
                "lifecycle_status": agent["config"]["lifecycle"]["lifecycle_status"]["value"],
                "governance_path": agent["governance_path"],
                # A critical agent needs a human on every call — worth seeing on
                # the diagram, because it is the one per-agent fact that changes
                # what the gateway does.
                "requires_hitl": agent["governance_path"] in HITL_GOVERNANCE_PATHS,
                "bound_tools": sorted(bound),
                "connector_ids": sorted(served),
                "local_tools": sorted(local),
                "unknown_tools": sorted(unknown),
                "calls": traffic["by_agent"].get(aid, {"calls": 0, "denied": 0}),
            }
        )

    connector_nodes = []
    for c in connectors:
        served_tools = [t["id"] for t in tools.values() if t["connector_id"] == c["id"]]
        connector_nodes.append(
            {
                "connector_id": c["id"],
                "name": c["name"],
                "status": c["status"],
                "transport": c["transport"],
                "live": is_live_connector(c),
                "tools": sorted(served_tools),
                "boundary_declared": bool(c["allowed_datasets"]),
                "identities_declared": bool(c["approved_identities"]),
                "rate_limit_per_min": c["rate_limit_per_min"],
                "calls": traffic["by_connector"].get(c["id"], {"calls": 0, "denied": 0, "live": 0}),
            }
        )

    agent_nodes.sort(key=lambda a: a["name"])
    connector_nodes.sort(key=lambda c: c["name"])

    return {
        "agents": agent_nodes,
        "connectors": connector_nodes,
        "edges": edges,
        "checkpoints": list(CHECKPOINTS),
        "traffic": traffic,
        "summary": {
            "agents": len(agent_nodes),
            "connectors": len(connector_nodes),
            "edges": len(edges),
            # The number the diagram exists to make obvious: without a gateway
            # these would be point-to-point integrations, one per edge.
            "point_to_point_avoided": len(edges),
            "local_only_tools": sorted(t["id"] for t in tools.values() if t["connector_id"] is None),
            "unrouted_agents": sorted(a["agent_id"] for a in agent_nodes if not a["connector_ids"]),
        },
    }
