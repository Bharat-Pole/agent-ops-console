"""Backend verification for the real MCP client — Phase 5A.

Everything before this phase simulated MCP. This suite defends the first code
that actually speaks the protocol, at **spec revision 2026-07-28**.

Four lines it holds:

  1. **Conformance.** A tool definition carrying an invalid ``x-mcp-header``
     annotation MUST be rejected and excluded from the listing, with the rest of
     the listing surviving. One malformed definition must not poison discovery.
  2. **Discovery is not consent.** A server can advertise whatever it likes; a
     discovered tool arrives `pending` and does not bind. Nothing on the wire
     may grant approval.
  3. **Deny-by-default on write.** A remote server must *explicitly* declare
     `readOnlyHint` for a tool to be treated as read-only. Silence means
     write-capable, which means catalogued-but-unbindable — the advisory-only
     invariant has to survive contact with a counterparty we do not control.
  4. **Real and simulated must be distinguishable in the data.** A connector
     that was genuinely probed carries `last_probe`; one that was not carries
     NULL. A fabricated green tick is worse than no tick.

Layers, cheapest first — the protocol assertions need no port and no database:

  · in-memory client against the reference server (no socket)
  · live Streamable HTTP against the reference server (needs it running)
  · persistence + governance through the API (needs the backend)

Run:

    backend\\.venv\\Scripts\\python.exe backend\\reference_mcp\\..\\..\\backend\\verify_mcp_client.py

more usefully, from the repo root with the reference server already up:

    $env:PYTHONPATH="backend"
    backend\\.venv\\Scripts\\python.exe -m reference_mcp.server --port 9100   # separate shell
    backend\\.venv\\Scripts\\python.exe backend\\verify_mcp_client.py

NOTE: this suite **creates a connector and discovered tools, and deletes both**
on the way out (asyncpg, teardown only) — the same discipline
`verify_bound_tools_guard.py` uses. Discovery writes real catalog rows, and
leaving four per run behind would pollute the Tool Catalog quickly.
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services import mcp_client  # noqa: E402
from app.services.connector_health import discovered_tool_id, is_live_connector  # noqa: E402
from reference_mcp.server import (  # noqa: E402
    MALFORMED_TOOL_NAME,
    REFERENCE_TOOLS,
    SERVER_NAME,
    WRITE_CAPABLE_TOOL_NAME,
    build_server,
)

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"
REF_URL = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9100/mcp"

CONNECTOR_ID = "zz-verify-mcp"
CONNECTOR_NAME = "zz verify mcp"

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


def post_rejected(path: str, body: dict) -> tuple[int, dict]:
    """POST expecting a 4xx. Returns (status, parsed body)."""
    try:
        _request("POST", path, body)
        return 200, {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"message": raw}


# ---------------------------------------------------------------------------
# Layer 1 — protocol + conformance, in memory. No socket, no database.
# ---------------------------------------------------------------------------


async def layer_protocol() -> None:
    print("\n[1] Protocol + conformance (in-memory, no socket)")

    listing = await mcp_client.list_remote_tools(build_server(), CONNECTOR_ID)

    check(
        "negotiates spec revision 2026-07-28",
        listing["protocol_version"] == mcp_client.TARGET_PROTOCOL_VERSION,
        f"got {listing['protocol_version']}",
    )
    check("server_info carries the reference server name", listing["server_info"]["name"] == SERVER_NAME)

    names = [t["name"] for t in listing["tools"]]
    check("accepted the three read-only tools", all(t in names for t in REFERENCE_TOOLS), str(names))
    check("accepted the undeclared tool (it is catalogued, not hidden)", WRITE_CAPABLE_TOOL_NAME in names)
    check("EXCLUDED the malformed definition from the listing", MALFORMED_TOOL_NAME not in names)

    rejected = {r["name"]: r for r in listing["rejected"]}
    check("reported the malformed tool as rejected", MALFORMED_TOOL_NAME in rejected)
    check(
        "rejection reason is invalid_x_mcp_header",
        rejected.get(MALFORMED_TOOL_NAME, {}).get("reason") == mcp_client.REJECT_INVALID_HEADER,
    )
    check(
        "one bad definition did not poison the rest",
        len(listing["tools"]) == 4 and len(listing["rejected"]) == 1,
        f"{len(listing['tools'])} accepted / {len(listing['rejected'])} rejected",
    )

    by_name = {t["name"]: t for t in listing["tools"]}
    for tool in REFERENCE_TOOLS:
        check(f"{tool}: readOnlyHint honoured → write_capable False", by_name[tool]["write_capable"] is False)
    check(
        f"{WRITE_CAPABLE_TOOL_NAME}: no readOnlyHint → write_capable True (deny-by-default)",
        by_name[WRITE_CAPABLE_TOOL_NAME]["write_capable"] is True,
    )
    check(
        "every discovered tool gets permission_ceiling='read'",
        all(t["permission_ceiling"] == "read" for t in listing["tools"]),
    )
    check(
        "input schema is mapped",
        [i["name"] for i in by_name["jira_issue_reader"]["schema"]["inputs"]] == ["issue_key"],
    )
    check(
        "remote_tool_id preserves the server's own name",
        by_name["jira_search"]["remote_tool_id"] == "jira_search",
    )


def layer_validator() -> None:
    """The header validator on its own — the cases a live server won't produce."""
    print("\n[2] x-mcp-header validator (unit)")
    v = mcp_client.validate_header_annotation

    check("no metadata is not an error", v(None) is None)
    check("empty metadata is not an error", v({}) is None)
    check("metadata without the annotation is not an error", v({"other": 1}) is None)
    check("well-formed annotation passes", v({"x-mcp-header": {"X-Tenant": "acme"}}) is None)
    check("annotation that is not an object is rejected", v({"x-mcp-header": "nope"}) is not None)
    check("non-string header value is rejected", v({"x-mcp-header": {"X": {"a": 1}}}) is not None)
    check("integer header value is rejected", v({"x-mcp-header": {"X": 7}}) is not None)
    check("empty header name is rejected", v({"x-mcp-header": {"   ": "v"}}) is not None)


async def layer_live() -> bool:
    """Real Streamable HTTP. Returns False if the reference server is absent."""
    print("\n[3] Live Streamable HTTP probe")

    probe = await mcp_client.probe(REF_URL)
    if not probe["ok"]:
        print(f"  SKIP  reference server not reachable at {REF_URL} — start it with:")
        print("        $env:PYTHONPATH='backend'; backend\\.venv\\Scripts\\python.exe -m reference_mcp.server --port 9100")
        return False

    check("probe over a real socket succeeds", probe["ok"] is True)
    check("probe measures latency", isinstance(probe["latency_ms"], int) and probe["latency_ms"] >= 0)
    check("probe reports the negotiated protocol", probe["protocol_version"] == mcp_client.TARGET_PROTOCOL_VERSION)
    check("probe counts what the server advertises (incl. the malformed one)", probe["tool_count"] == 5)

    dead = await mcp_client.probe("http://127.0.0.1:59999/mcp")
    check("probe of a dead endpoint reports not-ok", dead["ok"] is False)
    check("probe of a dead endpoint carries an error", bool(dead["error"]))
    check("probe of a dead endpoint claims no protocol", dead["protocol_version"] is None)

    check(
        "transport gate: streamable_http + http(s) is live",
        is_live_connector({"transport": "streamable_http", "endpoint": "http://x/mcp"}) is True,
    )
    check(
        "transport gate: a seeded sse connector is NOT probed",
        is_live_connector({"transport": "sse", "endpoint": "https://x/sse"}) is False,
    )
    check(
        "transport gate: a legacy http connector is NOT probed",
        is_live_connector({"transport": "http", "endpoint": "https://x/mcp"}) is False,
    )
    return True


# ---------------------------------------------------------------------------
# Layer 4 — persistence + governance through the API
# ---------------------------------------------------------------------------


def layer_api() -> None:
    print("\n[4] Discovery persistence + governance (via the API)")

    created = post(
        "/v1/connectors",
        {
            "name": CONNECTOR_NAME,
            "transport": "streamable_http",
            "endpoint": REF_URL,
            "auth_mode": "none",
        },
    )
    connector_id = created["connector"]["id"]
    check("registered a streamable_http connector", created["connector"]["transport"] == "streamable_http")
    check("a fresh connector advertises nothing", created["connector"]["tools_provided"] == [])
    check("a fresh connector has never been probed", created["connector"].get("last_probe") is None)

    # --- first discovery -------------------------------------------------
    first = get(f"/v1/connectors/{connector_id}/tools")
    check("discovery reports itself as live", first.get("live") is True)
    check("discovery reports the negotiated protocol", first.get("protocol_version") == "2026-07-28")
    check("discovery created four tools", len(first["created"]) == 4, str(first["created"]))
    check("discovery rejected exactly one definition", len(first.get("rejected", [])) == 1)
    check(
        "nothing is 'undiscovered' after a real listing",
        first["undiscovered"] == [],
        "we just wrote everything the server advertised",
    )

    expected_id = discovered_tool_id(connector_id, "jira_issue_reader")
    by_id = {t["id"]: t for t in first["tools"]}
    check("tool ids are namespaced by connector", expected_id in by_id, str(list(by_id)))
    check("discovered tools carry connector_id (D7)", all(t["connector_id"] == connector_id for t in first["tools"]))
    check("discovered tools carry remote_tool_id", all(t["remote_tool_id"] for t in first["tools"]))
    check("discovered tools carry discovered_at", all(t["discovered_at"] for t in first["tools"]))
    check(
        "DISCOVERY IS NOT CONSENT — every discovered tool is pending",
        all(t["approval_state"] == "pending" for t in first["tools"]),
        str([(t["id"], t["approval_state"]) for t in first["tools"]]),
    )
    check(
        "tools_provided became evidence from the listing",
        sorted(get("/v1/bootstrap")["connectors"] and _connector(connector_id)["tools_provided"])
        == sorted(t["id"] for t in first["tools"]),
    )

    # --- idempotency ------------------------------------------------------
    second = get(f"/v1/connectors/{connector_id}/tools")
    check("re-discovery creates nothing new", second["created"] == [], str(second["created"]))
    check("re-discovery still returns four tools", len(second["tools"]) == 4)
    check("re-discovery orphans nothing", second["orphaned"] == [])

    # --- the bind guard, against tools we did not author -------------------
    agent = _first_agent_id()
    read_only_id = discovered_tool_id(connector_id, "jira_issue_reader")
    write_id = discovered_tool_id(connector_id, WRITE_CAPABLE_TOOL_NAME)

    status, body = post_rejected(f"/v1/agents/{agent}/tools/bind", {"toolId": read_only_id})
    check("a pending discovered tool does not bind", status == 400, f"got {status}")
    check("...and the refusal names approval", "approv" in body.get("message", "").lower(), body.get("message", ""))

    status, body = post_rejected(f"/v1/agents/{agent}/tools/bind", {"toolId": write_id})
    check("a write-capable discovered tool does not bind", status == 400, f"got {status}")
    check(
        "...and write is refused on write-capability, not approval",
        "write" in body.get("message", "").lower(),
        body.get("message", ""),
    )

    # --- approval makes a read-only discovered tool bindable ---------------
    approval = _pending_approval_for(read_only_id)
    check("discovery raised an approval item for the read-only tool", approval is not None, "no queue item found")
    if approval is not None:
        post(f"/v1/approvals/{approval}/decide", {"decision": "approved", "note": "zz-verify"})
        tool = _tool(read_only_id)
        check("approving flips approval_state", tool["approval_state"] == "approved")
        bound = post(f"/v1/agents/{agent}/tools/bind", {"toolId": read_only_id})
        check("an approved read-only discovered tool BINDS", bound.get("ok") is True, json.dumps(bound))

    # --- write-capable flip returns a tool to pending ----------------------
    check(
        "a write-capable discovered tool stays unapproved",
        _tool(write_id)["approval_state"] == "pending",
    )

    # --- health: real vs simulated ----------------------------------------
    live_hc = post(f"/v1/connectors/{connector_id}/healthcheck")
    probe = live_hc["connector"].get("last_probe")
    check("a live connector's healthcheck stores probe evidence", probe is not None)
    if probe:
        check("probe evidence records the protocol", probe.get("protocol_version") == "2026-07-28")
        check("probe evidence records latency", isinstance(probe.get("latency_ms"), int))
        check("probe evidence is timestamped", bool(probe.get("at")))
    check("live healthcheck says so in the audit detail", "live probe" in (live_hc["auditEvent"]["detail"] or ""))

    sim = post("/v1/connectors/crm-readonly/healthcheck")
    if not sim.get("skipped"):
        check("a simulated connector stores NO probe evidence", sim["connector"].get("last_probe") is None)
        check(
            "simulated healthcheck says so in the audit detail",
            "simulated" in (sim["auditEvent"]["detail"] or ""),
            sim["auditEvent"]["detail"] or "",
        )

    # --- the cascade still owns tool status --------------------------------
    off = post(f"/v1/connectors/{connector_id}/toggle-offline")
    check("taking the connector offline cascades to discovered tools", len(off["changedTools"]) == 4)
    check("discovered tools are now offline", all(t["status"] == "offline" for t in off["changedTools"]))
    back = post(f"/v1/connectors/{connector_id}/toggle-offline")
    check("bringing it back restores them", all(t["status"] == "available" for t in back["changedTools"]))


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


def _first_agent_id() -> str:
    agent = get("/v1/bootstrap")["agents"][0]
    return agent["config"]["identity"]["agent_id"]["value"]


def _pending_approval_for(tool_id: str) -> str | None:
    for item in get("/v1/bootstrap").get("approvals", []):
        if item.get("entity_id") == tool_id and item.get("status") == "pending":
            return item["id"]
    return None


# ---------------------------------------------------------------------------
# Teardown — this suite creates real catalog rows, so it removes them.
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
        print(f"  WARN  could not connect for teardown ({exc}); zz-verify-mcp rows remain")
        return

    try:
        # Unbind before deleting, or an agent keeps a ref to a tool that is
        # gone. The column is `config_json`, and the guard's own rules would
        # strip these on the next sync anyway — but leaving a dangling ref for
        # another suite to trip over is exactly the pollution this teardown
        # exists to prevent.
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
        tools = await conn.execute("DELETE FROM tools WHERE connector_id = $1", CONNECTOR_ID)
        conns = await conn.execute("DELETE FROM connectors WHERE id = $1", CONNECTOR_ID)
        print(f"  ok   removed discovered tools ({tools}) and the connector ({conns})")
    finally:
        await conn.close()


async def main() -> int:
    print("=" * 68)
    print("verify_mcp_client — Phase 5A, MCP spec revision 2026-07-28")
    print("=" * 68)

    await layer_protocol()
    layer_validator()
    live = await layer_live()

    if live:
        try:
            layer_api()
        finally:
            await teardown()
    else:
        print("\n[4] SKIPPED — the API layer needs the reference server running")

    print("\n" + "=" * 68)
    print(f"{'PASS' if failures == 0 else 'FAIL'} — {failures} failure(s)")
    print("=" * 68)
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
