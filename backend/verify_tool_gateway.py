"""Backend verification for the policy-enforcing gateway — Phase 6.

The gateway is the first place this platform stands between an agent and a
system *at the moment of the call*. Everything before it governed configuration;
this governs execution. So the suite's job is to prove two things that are easy
to claim and hard to demonstrate:

  1. **Every checkpoint actually denies.** Not "the code has a branch for it" —
     a real call, refused, with the right checkpoint named and a row written.
     There are eleven, and each one gets its own denial here.

  2. **An allowed call is observed, not reported.** For a live connector the
     latency is measured over a real socket and the result is read off the wire.
     That is the measurement half of `CONCERNS.md` R7, and it is the difference
     between "governed tool-call trail" and "authoritative for every call that
     passes through the gateway".

Three properties the suite defends beyond the happy path:

  · **A denial is a 200 with a verdict, never a 4xx.** The moment denials become
    HTTP errors, the most valuable rows in the table become the ones a caller is
    encouraged to swallow.
  · **The two field sets are disjoint.** `PATCH /v1/connectors/:id` cannot touch
    a data boundary and `PATCH /v1/connectors/:id/policy` cannot touch an
    endpoint or a status. An author who could widen their own boundary is the
    hole the gateway exists to close.
  · **Undeclared is not deny-all.** An empty allowlist means nobody has written
    the policy, and the call records that gap rather than either enforcing a
    fiction or passing silently.

Layers, cheapest first:

  · [1] policy description        — no state, needs only the backend
  · [2] checkpoint denials        — mutates seeded connectors, restores them
  · [3] field-set isolation       — proves the two PATCH routes stay disjoint
  · [4] live invocation + boundary — needs the reference MCP server; skipped
                                     cleanly without it
  · [5] teardown

Run — backend up, and for layer 4 the reference server too:

    $env:PYTHONPATH="backend"
    backend\\.venv\\Scripts\\python.exe -m reference_mcp.server --port 9100   # separate shell
    backend\\.venv\\Scripts\\python.exe backend\\verify_tool_gateway.py

NOTE: this suite **creates a connector, discovered tools and an approval, binds
one tool to a seeded agent, and removes all of it** (asyncpg, teardown only). It
deliberately leaves the `tool_calls` rows it generates behind — an audit trail
that deletes its own evidence would be a strange thing to ship, and those rows
are the artefact the phase exists to produce. They are identifiable by
`principal` and by the `zz-verify` request ids.
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.connector_health import discovered_tool_id  # noqa: E402
from app.services.tool_gateway import CHECKPOINT_IDS  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"
REF_URL = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9100/mcp"

CONNECTOR_ID = "zz-verify-gateway"
CONNECTOR_NAME = "zz verify gateway"

# Seeded fixtures this suite leans on. Chosen because each is the *only* seeded
# row with the shape a particular checkpoint needs.
NOC_AGENT = "agt-noc-incident-summarizer-20260122-b2e7"      # live, standard, 1 bound tool
CRITICAL_AGENT = "agt-regulatory-filing-coordinator-20260320-1829"  # the only `critical` path
BOUND_TOOL = "incident_reader"        # bound to NOC, read-only, approved, served by gcp-ticketing
UNBOUND_TOOL = "confluence_reader"    # approved + read-only but NOT bound to NOC
WRITE_TOOL = "ticket_updater"         # write-capable
CRITICAL_TOOL = "filing_reader"       # bound to the critical agent
TOOL_CONNECTOR = "gcp-ticketing"      # serves BOUND_TOOL and WRITE_TOOL

PRINCIPAL = "platform_engineer"

failures = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{'' if cond else '  ' + extra}")
    if not cond:
        failures += 1


def _request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data, timeout=60) as resp:
        return json.loads(resp.read())


def get(path: str) -> dict:
    return _request("GET", path)


def post(path: str, body: dict | None = None) -> dict:
    return _request("POST", path, body)


def patch(path: str, body: dict) -> dict:
    return _request("PATCH", path, body)


def patch_rejected(path: str, body: dict) -> tuple[int, dict]:
    try:
        _request("PATCH", path, body)
        return 200, {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"message": raw}


def gateway_call(**payload) -> dict:
    """Every gateway call in the suite goes through here.

    `principal` is defaulted so a test that omits it is doing so on purpose —
    which is exactly what the `identity` denial needs.
    """
    body = {"consumer": "api", **payload}
    body.setdefault("principal", PRINCIPAL)
    if body["principal"] is None:
        body.pop("principal")
    return post("/v1/gateway/tool-call", body)


def _connector(connector_id: str) -> dict:
    for c in get("/v1/bootstrap")["connectors"]:
        if c["id"] == connector_id:
            return c
    raise AssertionError(f"connector {connector_id} missing from bootstrap")


def _tool(tool_id: str) -> dict:
    for t in get("/v1/bootstrap")["tools"]:
        if t["id"] == tool_id:
            return t
    raise AssertionError(f"tool {tool_id} missing from bootstrap")


def _pending_approval_for(tool_id: str) -> str | None:
    for item in get("/v1/bootstrap").get("approvals", []):
        if item.get("entity_id") == tool_id and item.get("status") == "pending":
            return item["id"]
    return None


def _denial(result: dict, checkpoint: str, label: str) -> None:
    """Assert one denial completely: verdict, checkpoint, and the row it wrote."""
    check(f"{label}: denied", result.get("allowed") is False, json.dumps(result)[:200])
    check(f"{label}: denied_by = {checkpoint}", result.get("deniedBy") == checkpoint, str(result.get("deniedBy")))
    call = result.get("toolCall") or {}
    check(f"{label}: row is a gateway row", call.get("gateway") is True)
    check(f"{label}: row records the decision", call.get("decision") == "deny")
    check(f"{label}: row names the checkpoint", call.get("denied_by") == checkpoint)
    check(f"{label}: nothing was invoked", call.get("invocation") == "none")
    check(f"{label}: result_status is blocked", call.get("result_status") == "blocked")
    check(f"{label}: latency is 0, not fabricated", call.get("latency_ms") == 0)
    check(f"{label}: a reason is recorded", bool(call.get("exception_detail")))


# ---------------------------------------------------------------------------
# Layer 1 — the policy description
# ---------------------------------------------------------------------------


def layer_policy() -> None:
    print("\n[1] Gateway policy description")

    policy = get("/v1/gateway/policy")
    ids = [c["id"] for c in policy["checkpoints"]]

    check("the chain is published", len(ids) == 11, str(ids))
    check("the published chain matches the enforced one", tuple(ids) == CHECKPOINT_IDS, str(ids))
    check(
        "write_capable is checked BEFORE approval",
        ids.index("write_capable") < ids.index("approval"),
        "approval must never launder the locked invariant",
    )
    check(
        "existence checks come before policy checks",
        max(ids.index("identity"), ids.index("catalog"), ids.index("agent")) < ids.index("write_capable"),
    )
    check(
        "rate_limit is the last check before invocation",
        ids[-1] == "rate_limit",
        "so a denied call never consumes another caller's budget",
    )
    check("every checkpoint cites its source", all(c.get("source") for c in policy["checkpoints"]))
    check("the four personas are the principals", len(policy["principals"]) == 4, str(policy["principals"]))
    check("the rate window is a minute", policy["rateWindowSeconds"] == 60)

    by_id = {p["connector_id"]: p for p in policy["policies"]}
    check("every connector has a policy row", len(by_id) >= 5, str(len(by_id)))
    seeded = by_id.get(TOOL_CONNECTOR)
    check("a seeded connector reports its undeclared fields", bool(seeded and seeded["undeclared"]))
    check("...including the data boundary", bool(seeded and "allowed_datasets" in seeded["undeclared"]))
    check("a seeded connector is not live", seeded is not None and seeded["live"] is False)


# ---------------------------------------------------------------------------
# Layer 2 — every checkpoint denies
# ---------------------------------------------------------------------------


def layer_denials() -> None:
    print("\n[2] Every checkpoint denies")

    # --- the allow baseline, so a later denial means something ---------------
    ok = gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL)
    check("a bound, approved, read-only tool is ALLOWED", ok.get("allowed") is True, json.dumps(ok)[:300])
    check("...and every checkpoint is traced", len(ok.get("checkpoints", [])) == 11, str(len(ok.get("checkpoints", []))))
    check("...and the row is a gateway row", (ok.get("toolCall") or {}).get("gateway") is True)
    check("...invoked on the simulated path (seeded connector)", (ok.get("result") or {}).get("invocation") == "simulated")
    check("...and the trail records that", (ok.get("toolCall") or {}).get("invocation") == "simulated")
    check("...with the principal on the row", (ok.get("toolCall") or {}).get("principal") == PRINCIPAL)
    check(
        "...and an undeclared boundary is surfaced as a warning, not silence",
        any("data boundary" in w for w in ok.get("warnings", [])),
        str(ok.get("warnings")),
    )

    # --- 1. identity --------------------------------------------------------
    _denial(gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL, principal=None), "identity", "no principal")
    _denial(
        gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL, principal="root"),
        "identity",
        "unknown principal",
    )

    # --- 2. catalog ---------------------------------------------------------
    _denial(gateway_call(agentId=NOC_AGENT, toolId="zz-not-a-tool"), "catalog", "uncatalogued tool")

    # --- 3. agent -----------------------------------------------------------
    _denial(gateway_call(agentId="agt-zz-not-registered", toolId=BOUND_TOOL), "agent", "unregistered agent")

    # --- 4. write-capable ---------------------------------------------------
    write = gateway_call(agentId=NOC_AGENT, toolId=WRITE_TOOL)
    _denial(write, "write_capable", "write-capable tool")
    check(
        "the write denial names advisory scope, not binding",
        "advisory" in (write.get("reason") or "").lower(),
        write.get("reason") or "",
    )

    # --- 5. approval --------------------------------------------------------
    pending = post(
        "/v1/tools",
        {
            "name": "zz gateway pending reader",
            "category": "verification",
            "description": "Created by verify_tool_gateway to exercise the approval checkpoint.",
            "permission_ceiling": "read",
            "write_capable": False,
        },
    )
    pending_id = pending["tool"]["id"]
    check("a console-created tool is pending", pending["tool"]["approval_state"] == "pending")
    _denial(gateway_call(agentId=NOC_AGENT, toolId=pending_id), "approval", "unapproved tool")

    # --- 6. allowlist -------------------------------------------------------
    # UNBOUND_TOOL is approved and read-only, so this can only fail on binding.
    _denial(gateway_call(agentId=NOC_AGENT, toolId=UNBOUND_TOOL), "allowlist", "tool not bound to the agent")

    # --- 7. connector health ------------------------------------------------
    post(f"/v1/connectors/{TOOL_CONNECTOR}/toggle-offline")
    try:
        offline = gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL)
        _denial(offline, "connector_health", "offline connector")
        check(
            "bind warns but a CALL blocks — health is a runtime fact",
            "offline" in (offline.get("reason") or "").lower(),
            offline.get("reason") or "",
        )
    finally:
        post(f"/v1/connectors/{TOOL_CONNECTOR}/toggle-offline")
    check(
        "the connector is restored to connected",
        _connector(TOOL_CONNECTOR)["status"] == "connected",
    )

    # --- 8. identity binding ------------------------------------------------
    patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"approved_identities": ["governance_officer"]})
    try:
        _denial(
            gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL),
            "identity_binding",
            "principal not an approved identity",
        )
        allowed = gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL, principal="governance_officer")
        check("an approved identity passes the same check", allowed.get("allowed") is True, json.dumps(allowed)[:200])
    finally:
        patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"approved_identities": []})

    # --- 9. data boundary ---------------------------------------------------
    patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"allowed_datasets": ["incidents_public"]})
    try:
        _denial(
            gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL),
            "data_boundary",
            "no dataset named against a bounded connector",
        )
        _denial(
            gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL, dataset="customer_pii"),
            "data_boundary",
            "dataset outside the boundary",
        )
        inside = gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL, dataset="incidents_public")
        check("a dataset inside the boundary is allowed", inside.get("allowed") is True, json.dumps(inside)[:200])
        check(
            "...and a declared boundary stops warning about itself",
            not any("data boundary" in w for w in inside.get("warnings", [])),
            str(inside.get("warnings")),
        )
    finally:
        patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"allowed_datasets": []})

    # --- 10. HITL -----------------------------------------------------------
    # Server-enforced from this phase on. The Playground's gate was client-side,
    # which meant it protected the UI rather than the system.
    _denial(
        gateway_call(agentId=CRITICAL_AGENT, toolId=CRITICAL_TOOL),
        "hitl",
        "critical agent without a human decision",
    )
    approved_call = gateway_call(agentId=CRITICAL_AGENT, toolId=CRITICAL_TOOL, hitlApproved=True)
    check("a human decision unblocks the critical path", approved_call.get("allowed") is True, json.dumps(approved_call)[:200])
    check(
        "a non-critical agent needs no per-call gate",
        any(e["checkpoint"] == "hitl" and e["status"] == "skipped" for e in ok.get("checkpoints", [])),
    )

    # --- 11. rate limit -----------------------------------------------------
    # The suite has already made several allowed calls for this pair, so a limit
    # of 1 is guaranteed to be exceeded — deterministic without sleeping.
    patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"rate_limit_per_min": 1})
    try:
        _denial(gateway_call(agentId=NOC_AGENT, toolId=BOUND_TOOL), "rate_limit", "over the rolling limit")
    finally:
        patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"rate_limit_per_min": 60})

    # --- denials are data, not HTTP errors ----------------------------------
    check(
        "a denied call still returns HTTP 200 with a verdict",
        gateway_call(agentId=NOC_AGENT, toolId="zz-not-a-tool").get("decision") == "deny",
        "a 4xx would make the most valuable rows the easiest to swallow",
    )

    # --- the trail separates observed from reported -------------------------
    rows = get("/v1/tool-calls?limit=500")["toolCalls"]
    gw = [r for r in rows if r.get("gateway")]
    check("gateway rows exist in the trail", len(gw) >= 10, str(len(gw)))
    check("every gateway row carries a decision", all(r.get("decision") in ("allow", "deny") for r in gw))
    filtered = get("/v1/tool-calls?gateway=true&limit=500")["toolCalls"]
    check("the trail can be filtered to observed rows", all(r["gateway"] for r in filtered))
    reported = get("/v1/tool-calls?gateway=false&limit=500")["toolCalls"]
    check(
        "client-reported rows stay distinguishable",
        all(r.get("decision") is None for r in reported),
        "a reported row must never acquire the markings of an observed one",
    )

    # A blocked-bind row is still the Phase 1 shape — the gateway did not
    # retroactively re-label the older evidence.
    check(
        "Phase 1 rows are untouched by Phase 6",
        all(r["gateway"] is False for r in reported),
    )


# ---------------------------------------------------------------------------
# Layer 3 — the two PATCH routes stay disjoint
# ---------------------------------------------------------------------------


def layer_isolation() -> None:
    print("\n[3] Authoring and policy are disjoint field sets")

    before = _connector(TOOL_CONNECTOR)

    # The authoring route ignores policy fields rather than applying them.
    patch(
        f"/v1/connectors/{TOOL_CONNECTOR}",
        {"allowed_datasets": ["everything"], "approved_identities": ["root"], "rate_limit_per_min": 9999},
    )
    after = _connector(TOOL_CONNECTOR)
    check("authoring cannot declare a data boundary", after["allowed_datasets"] == before["allowed_datasets"])
    check("authoring cannot declare approved identities", after["approved_identities"] == before["approved_identities"])
    check("authoring cannot change the rate limit", after["rate_limit_per_min"] == before["rate_limit_per_min"])

    # ...and the policy route ignores connectivity fields.
    patch(
        f"/v1/connectors/{TOOL_CONNECTOR}/policy",
        {"endpoint": "http://evil.example/mcp", "status": "connected", "name": "zz renamed", "transport": "stdio"},
    )
    after = _connector(TOOL_CONNECTOR)
    check("policy cannot move the endpoint", after["endpoint"] == before["endpoint"])
    check("policy cannot set status", after["status"] == before["status"])
    check("policy cannot rename the connector", after["name"] == before["name"])
    check("policy cannot change the transport", after["transport"] == before["transport"])

    # Validation.
    status, body = patch_rejected(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"allowed_datasets": "not-a-list"})
    check("a non-list boundary is rejected", status == 400, f"got {status}")
    status, _ = patch_rejected(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"rate_limit_per_min": 0})
    check("a rate limit of 0 is rejected", status == 400, "0 would be a deny-all wearing a limit's clothing")
    status, _ = patch_rejected(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"timeout_ms": 10})
    check("an absurd timeout is rejected", status == 400, f"got {status}")
    status, _ = patch_rejected("/v1/connectors/zz-nope/policy", {"allowed_datasets": []})
    check("an unknown connector is a 404", status == 404, f"got {status}")

    # A policy change is a governance act and is audited as one.
    result = patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"allowed_fields": ["id", "summary"]})
    check("a policy change is audited", result.get("auditEvent") is not None)
    check(
        "...by the Governance Officer, not the Platform Engineer",
        (result.get("auditEvent") or {}).get("actor_persona") == "Governance Officer",
        str((result.get("auditEvent") or {}).get("actor_persona")),
    )
    check("...naming what changed", result.get("changed") == ["allowed_fields"], str(result.get("changed")))
    unchanged = patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"allowed_fields": ["id", "summary"]})
    check("a no-op policy patch writes no audit event", unchanged.get("auditEvent") is None)
    patch(f"/v1/connectors/{TOOL_CONNECTOR}/policy", {"allowed_fields": []})


# ---------------------------------------------------------------------------
# Layer 4 — a real invocation over a real socket
# ---------------------------------------------------------------------------


def _reference_server_up() -> bool:
    """A TCP connect, deliberately not an HTTP request.

    A bare GET on a Streamable HTTP MCP endpoint can legitimately hold the
    connection open, so an HTTP probe times out against a *healthy* server and
    would skip layer 4 exactly when it should run. Whether the socket accepts is
    the question being asked here; whether it speaks MCP is what the layer
    itself proves.
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(REF_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def layer_live() -> None:
    print("\n[4] Live invocation — measured, not reported")

    created = post(
        "/v1/connectors",
        {"name": CONNECTOR_NAME, "transport": "streamable_http", "endpoint": REF_URL, "auth_mode": "none"},
    )
    connector_id = created["connector"]["id"]
    check("registered a live connector", connector_id == CONNECTOR_ID, connector_id)

    discovery = get(f"/v1/connectors/{connector_id}/tools")
    check("discovery is live", discovery.get("live") is True)
    tool_id = discovered_tool_id(connector_id, "jira_issue_reader")
    check("the read-only tool was discovered", any(t["id"] == tool_id for t in discovery["tools"]))

    # Discovery is not consent — so the gateway must refuse it before approval,
    # which is the same rule `bind_tool()` enforces, proven at call time.
    _denial(gateway_call(agentId=NOC_AGENT, toolId=tool_id), "approval", "freshly discovered tool")

    approval = _pending_approval_for(tool_id)
    check("discovery queued an approval", approval is not None)
    if approval is None:
        return
    post(f"/v1/approvals/{approval}/decide", {"decision": "approved", "note": "zz-verify-gateway"})

    # Approved but still not bound — the allowlist is a separate question from
    # consent, and the gateway asks both.
    _denial(gateway_call(agentId=NOC_AGENT, toolId=tool_id), "allowlist", "approved but unbound tool")

    bound = post(f"/v1/agents/{NOC_AGENT}/tools/bind", {"toolId": tool_id})
    check("the approved read-only tool binds", bound.get("ok") is True, json.dumps(bound)[:200])

    # --- the call that closes the measurement half of R7 --------------------
    live = gateway_call(agentId=NOC_AGENT, toolId=tool_id, arguments={"issue_key": "NOC-1042"})
    check("a live tool call is ALLOWED", live.get("allowed") is True, json.dumps(live)[:300])

    result = live.get("result") or {}
    call = live.get("toolCall") or {}
    check("the invocation is live, not simulated", result.get("invocation") == "live", str(result.get("invocation")))
    check("...and the trail says so", call.get("invocation") == "live")
    check(
        "LATENCY IS MEASURED, not reported",
        isinstance(call.get("latency_ms"), int) and call["latency_ms"] > 0,
        f"latency_ms={call.get('latency_ms')} — a real round trip cannot take 0ms",
    )
    check("the result came back over the wire", bool(result.get("content") or result.get("structured")))
    check("the trail records the system reached", call.get("system_accessed") == connector_id)
    check("result_status was observed", call.get("result_status") == "ok")

    structured = result.get("structured") or {}
    check("the reference server answered with the issue", structured.get("key") == "NOC-1042", json.dumps(structured)[:200])

    # --- a failure is observed too, not guessed -----------------------------
    missing = gateway_call(agentId=NOC_AGENT, toolId=tool_id, arguments={"issue_key": "NOPE-1"})
    check("an unknown key still completes (the tool decides, not us)", missing.get("allowed") is True)
    check(
        "...and its latency is measured as well",
        ((missing.get("toolCall") or {}).get("latency_ms") or 0) > 0,
    )

    # --- field-level redaction over a real payload --------------------------
    patch(f"/v1/connectors/{connector_id}/policy", {"allowed_fields": ["found", "key", "status"]})
    redacted_call = gateway_call(agentId=NOC_AGENT, toolId=tool_id, arguments={"issue_key": "NOC-1042"})
    redacted = redacted_call.get("redacted") or []
    kept = (redacted_call.get("result") or {}).get("structured") or {}
    check("declared fields survive the boundary", set(kept) <= {"found", "key", "status"}, str(sorted(kept)))
    check("undeclared fields are redacted", "summary" in redacted, str(redacted))
    check("...and the redaction is recorded on the row", "summary" in ((redacted_call.get("toolCall") or {}).get("redacted_fields") or []))
    check(
        "...and reported as a warning",
        any("redacted" in w for w in redacted_call.get("warnings", [])),
        str(redacted_call.get("warnings")),
    )

    # --- a timeout is a real outcome ----------------------------------------
    patch(f"/v1/connectors/{connector_id}/policy", {"allowed_fields": [], "timeout_ms": 100})
    # 100ms against a local server usually succeeds; the assertion is only that
    # whichever way it goes, the row is honest about it.
    timed = gateway_call(agentId=NOC_AGENT, toolId=tool_id, arguments={"issue_key": "NOC-1042"})
    tc = timed.get("toolCall") or {}
    check(
        "a tight timeout produces an honest row either way",
        tc.get("result_status") in ("ok", "error") and tc.get("invocation") == "live",
        json.dumps(tc)[:200],
    )
    patch(f"/v1/connectors/{connector_id}/policy", {"timeout_ms": 10000})

    # --- the write-capable discovered tool is still refused -----------------
    write_id = discovered_tool_id(connector_id, "jira_issue_commenter")
    _denial(gateway_call(agentId=NOC_AGENT, toolId=write_id), "write_capable", "undeclared-readonly remote tool")


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


async def teardown() -> None:
    print("\n[5] Teardown")
    try:
        import asyncpg
        from dotenv import load_dotenv

        load_dotenv()
        dsn = os.environ.get("DATABASE_URL", "postgres://postgres:postgres@localhost:5434/agent_ops")
        conn = await asyncpg.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN  could not connect for teardown ({exc}); zz-verify-gateway rows remain")
        return

    try:
        # Unbind first — a seeded agent left holding a ref to a deleted tool is
        # exactly the pollution the next suite would trip over.
        await conn.execute(
            """
            UPDATE agents SET config_json = jsonb_set(
                config_json, '{tooling,bound_tools,value}',
                COALESCE((
                    SELECT jsonb_agg(elem) FROM jsonb_array_elements(
                        config_json->'tooling'->'bound_tools'->'value') elem
                    WHERE elem::text NOT LIKE '%' || $1 || '%'
                ), '[]'::jsonb))
            WHERE config_json->'tooling'->'bound_tools'->>'value' LIKE '%' || $1 || '%'
            """,
            CONNECTOR_ID,
        )
        await conn.execute("DELETE FROM approvals WHERE entity_id LIKE $1", f"{CONNECTOR_ID}.%")
        await conn.execute("DELETE FROM approvals WHERE entity_id LIKE 'zz-gateway-pending%'")
        tools = await conn.execute("DELETE FROM tools WHERE connector_id = $1", CONNECTOR_ID)
        pend = await conn.execute("DELETE FROM tools WHERE id LIKE 'zz-gateway-pending%'")
        conns = await conn.execute("DELETE FROM connectors WHERE id = $1", CONNECTOR_ID)

        # Restore the seeded connector's policy to "undeclared" so a later run —
        # and the Phase 6 browser pass — starts from the shipped state.
        await conn.execute(
            """UPDATE connectors SET allowed_datasets_json = '[]', allowed_fields_json = '[]',
                   approved_identities_json = '[]', rate_limit_per_min = 60, timeout_ms = 10000
               WHERE id = $1""",
            TOOL_CONNECTOR,
        )
        print(f"  ok   removed discovered tools ({tools}), the pending tool ({pend}), the connector ({conns})")
        print(f"  ok   restored {TOOL_CONNECTOR} to an undeclared policy")
    finally:
        await conn.close()


async def main() -> int:
    print("=" * 68)
    print("verify_tool_gateway — Phase 6, the policy-enforcing gateway")
    print("=" * 68)

    layer_policy()
    layer_denials()
    layer_isolation()

    if _reference_server_up():
        try:
            layer_live()
        finally:
            await teardown()
    else:
        print("\n[4] SKIPPED — the live layer needs the reference MCP server:")
        print("      $env:PYTHONPATH=\"backend\"")
        print("      backend\\.venv\\Scripts\\python.exe -m reference_mcp.server --port 9100")
        await teardown()

    print("\n" + "=" * 68)
    print(f"{'PASS' if failures == 0 else 'FAIL'} — {failures} failure(s)")
    print("=" * 68)
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
