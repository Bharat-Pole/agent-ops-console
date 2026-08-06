"""Backend verification for the bound_tools guard — R8.

`bind_tool()` was the *governed* way a tool becomes bound to an agent, never the
*only* way. Three routes write `config.tooling.bound_tools` straight out of a
client-supplied config, and none of them validated it:

    POST  /v1/agents/register
    PATCH /v1/agents/:id                 (the provisioning config sync)
    POST  /v1/agents/:id/config-change   (groupKey=tooling, field=bound_tools)

So a write-capable or unapproved tool could be bound by going around the gate,
which also poisons the tool-call trail — `_binding_violation()` authorizes calls
*against* `bound_tools`, so a laundered bind makes a write call record `ok`.

This suite proves all three doors are shut, that the guard **strips rather than
rejects** (a bad ref does not fail the whole registration), and that every strip
leaves evidence: an audit event plus one `blocked` tool-call row per ref, the
same evidence a refused `bind_tool()` produces.

Run against a live backend (default http://127.0.0.1:8787):

    backend\\.venv\\Scripts\\python.exe backend\\verify_bound_tools_guard.py

Exits non-zero on the first failure.

CLEANUP: unlike the other suites this one **deletes what it creates**. It has to
register real agents, and there is no delete-agent endpoint — leftovers would
show up in the Registry and in the Home page counts, which is worse than a
leftover `zz-verify-*` tool nobody looks at. It therefore talks to Postgres
directly (asyncpg + DATABASE_URL) for teardown only; every assertion still goes
over HTTP. The one `zz-verify-guard-*` tool it catalogues is left behind, same
as the other suites.
"""

import asyncio
import json
import sys
import urllib.error
import urllib.request
import uuid
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"

RUN = uuid.uuid4().hex[:6]

failures = 0
created_agents: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{'' if cond else '  ' + extra}")
    if not cond:
        failures += 1


def _request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    payload = json.dumps(body or {}).encode("utf-8") if method in ("POST", "PATCH") else None
    with urllib.request.urlopen(req, payload, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def get(path: str) -> dict:
    return _request("GET", path)


def post(path: str, body: dict | None = None) -> dict:
    return _request("POST", path, body)


def patch(path: str, body: dict | None = None) -> dict:
    return _request("PATCH", path, body)


def agent_id_of(agent: dict) -> str:
    return agent["config"]["identity"]["agent_id"]["value"]


def fetch_agent(agent_id: str) -> dict | None:
    return next((a for a in get("/v1/bootstrap")["agents"] if agent_id_of(a) == agent_id), None)


def bound_of(agent: dict) -> list[str]:
    return agent["config"]["tooling"]["bound_tools"]["value"]


def register(name: str, refs: list[str]) -> dict:
    donor = get("/v1/bootstrap")["agents"][0]
    cfg = deepcopy(donor["config"])
    cfg["tooling"]["bound_tools"]["value"] = refs
    cfg["identity"]["agent_name"]["value"] = name
    result = post("/v1/agents/register", {
        "name": name,
        "synthesis": {
            "config": cfg, "capability_tier": "minimal", "risk_tier": "low",
            "signal_breakdown": donor.get("signal_breakdown") or {},
        },
    })
    created_agents.append(agent_id_of(result["agent"]))
    return result


def cleanup() -> None:
    """Delete the probe agents and their dependent rows. Teardown only."""
    if not created_agents:
        return
    try:
        import asyncpg
        from app.env import env
    except Exception as err:  # pragma: no cover
        print(f"\n  ..   CLEANUP SKIPPED ({err}) — remove agents named 'ZZ Verify Guard' by hand.")
        return

    async def _run() -> None:
        conn = await asyncpg.connect(dsn=env.DATABASE_URL)
        try:
            for aid in created_agents:
                # Order matters: approvals and eval_packs carry an FK to agents.
                await conn.execute("DELETE FROM approvals WHERE agent_id = $1", aid)
                await conn.execute("DELETE FROM eval_packs WHERE agent_id = $1", aid)
                await conn.execute("DELETE FROM scheduled_jobs WHERE entity_id = $1", aid)
                await conn.execute("DELETE FROM agents WHERE id = $1", aid)
        finally:
            await conn.close()

    asyncio.run(_run())
    print(f"\n  ..   cleaned up {len(created_agents)} probe agent(s); tool-call + audit rows kept as evidence")


try:
    get("/v1/bootstrap")
except (urllib.error.URLError, TimeoutError) as err:
    print(f"Backend unreachable at {BASE} — start it first ({err}).")
    sys.exit(2)

try:
    # A read-only tool that is genuinely pending — the seeded catalog is all
    # approved, so the `not_approved` path needs one made on purpose. Its
    # approval item is deliberately left undecided.
    PENDING = post("/v1/tools", {
        "name": f"zz_verify_guard_{RUN}", "category": "verification",
        "description": "Pending-approval probe for the bound_tools guard.",
        "permission_ceiling": "read", "write_capable": False,
        "schema": {"inputs": {"q": "string"}, "outputs": {"rows": "Row[]"}},
    })["tool"]["id"]

    GOOD = "tools://crm_reader@v1"          # approved, read-only
    WRITE = "tools://ticket_updater@v1"     # write-capable — locked invariant
    PENDING_REF = f"tools://{PENDING}@v1"   # pending — Phase 3.2 gate
    GHOST = "tools://zz_no_such_tool@v1"    # not in the catalog at all

    print("\n== Door 1: POST /v1/agents/register ==")
    res = register(f"ZZ Verify Guard {RUN} A", [GOOD, WRITE, PENDING_REF, GHOST])
    aid = agent_id_of(res["agent"])
    check("registration still succeeds (strip, don't reject)", bool(aid))
    check("only the legitimate ref is bound", bound_of(res["agent"]) == [GOOD], str(bound_of(res["agent"])))
    stripped = {s["tool_id"]: s["reason"] for s in res.get("strippedTools", [])}
    check("write-capable ref stripped", stripped.get("ticket_updater") == "write_capable", str(stripped))
    check("unapproved ref stripped", stripped.get(PENDING) == "not_approved", str(stripped))
    check("uncatalogued ref stripped", stripped.get("zz_no_such_tool") == "not_in_catalog", str(stripped))
    check("each strip carries a human reason", all(s["message"] for s in res["strippedTools"]))

    print("\n== ...and it is the PERSISTED row that is clean, not just the response ==")
    stored = fetch_agent(aid)
    check("persisted bound_tools sanitized", bound_of(stored) == [GOOD], str(bound_of(stored)))

    print("\n== Evidence: audit event + one blocked tool-call row per strip ==")
    audit_actions = [e["action"] for e in get("/v1/bootstrap")["auditLog"] if e["entity_id"] == aid]
    check("bind_stripped audit event written", "bind_stripped" in audit_actions, str(audit_actions))
    calls = get(f"/v1/tool-calls?agentId={aid}")["toolCalls"]
    check("three blocked rows", len([c for c in calls if c["result_status"] == "blocked"]) == 3, str(len(calls)))
    check("logged under consumer=console", all(c["consumer"] == "console" for c in calls), str([c["consumer"] for c in calls]))
    check("the legitimate tool produced no row", not any(c["tool_invoked"] == "crm_reader" for c in calls))

    print("\n== A clean registration is silent (no false positives) ==")
    clean = register(f"ZZ Verify Guard {RUN} B", [GOOD])
    check("nothing stripped", clean.get("strippedTools") == [], str(clean.get("strippedTools")))
    clean_id = agent_id_of(clean["agent"])
    check("tool still bound", bound_of(clean["agent"]) == [GOOD], str(bound_of(clean["agent"])))
    check("no bind_stripped event", "bind_stripped" not in [
        e["action"] for e in get("/v1/bootstrap")["auditLog"] if e["entity_id"] == clean_id])

    print("\n== Door 2: PATCH /v1/agents/:id (the provisioning config sync) ==")
    cfg = deepcopy(fetch_agent(clean_id)["config"])
    cfg["tooling"]["bound_tools"]["value"] = [GOOD, WRITE, PENDING_REF]
    synced = patch(f"/v1/agents/{clean_id}", {"config": cfg})
    check("sync cannot smuggle refs in", bound_of(synced["agent"]) == [GOOD], str(bound_of(synced["agent"])))
    reasons = {s["tool_id"]: s["reason"] for s in synced.get("strippedTools", [])}
    check("write-capable reported", reasons.get("ticket_updater") == "write_capable", str(reasons))
    check("unapproved reported", reasons.get(PENDING) == "not_approved", str(reasons))
    check("persisted row is clean", bound_of(fetch_agent(clean_id)) == [GOOD])

    print("\n== ...and the sync the client actually makes is silent ==")
    # `syncAgentToServer` re-sends whatever is in the store, and the store
    # adopted the server's sanitized agent at registration. So the real repeat
    # sync carries nothing to strip and writes no event — which is why the guard
    # needs no de-duplication. (Every *genuine* attempt is reported, above.)
    before = len([e for e in get("/v1/bootstrap")["auditLog"] if e["entity_id"] == clean_id and e["action"] == "bind_stripped"])
    sanitized_cfg = deepcopy(fetch_agent(clean_id)["config"])
    again = patch(f"/v1/agents/{clean_id}", {"config": sanitized_cfg})
    after = len([e for e in get("/v1/bootstrap")["auditLog"] if e["entity_id"] == clean_id and e["action"] == "bind_stripped"])
    check("re-syncing the sanitized config reports nothing", again.get("strippedTools") == [], str(again.get("strippedTools")))
    check("...and writes no audit event", after == before, f"{before} -> {after}")
    check("...and leaves the binding intact", bound_of(again["agent"]) == [GOOD], str(bound_of(again["agent"])))

    print("\n== A sync that touches nothing else still works ==")
    tracks_only = patch(f"/v1/agents/{clean_id}", {"demo_mode": True})
    check("non-config patch unaffected", tracks_only["agent"]["demo_mode"] is True)
    patch(f"/v1/agents/{clean_id}", {"demo_mode": False})

    print("\n== Door 3: POST /v1/agents/:id/config-change ==")
    changed = post(f"/v1/agents/{clean_id}/config-change", {
        "groupKey": "tooling", "field": "bound_tools", "newValue": [WRITE, PENDING_REF, GOOD],
    })
    check("config-change cannot smuggle refs in", bound_of(changed["agent"]) == [GOOD], str(bound_of(changed["agent"])))
    check("strips reported", len(changed.get("strippedTools", [])) == 2, str(changed.get("strippedTools")))
    check("persisted row is clean", bound_of(fetch_agent(clean_id)) == [GOOD])
    other = post(f"/v1/agents/{clean_id}/config-change", {
        "groupKey": "identity", "field": "business_owner", "newValue": "Verification Team",
    })
    check("other fields unaffected by the guard", other.get("strippedTools") == [], str(other.get("strippedTools")))
    check("...and still applied", other["agent"]["config"]["identity"]["business_owner"]["value"] == "Verification Team")

    print("\n== Approving the tool makes it bindable through the same doors ==")
    appr = next(a for a in get("/v1/bootstrap")["approvals"]
                if a["entity_type"] == "tool" and a["entity_id"] == PENDING)
    post(f"/v1/approvals/{appr['id']}/decide", {"decision": "approved", "note": "verify"})
    now_ok = post(f"/v1/agents/{clean_id}/config-change", {
        "groupKey": "tooling", "field": "bound_tools", "newValue": [GOOD, PENDING_REF],
    })
    check("approved tool now passes the guard", sorted(bound_of(now_ok["agent"])) == sorted([GOOD, PENDING_REF]),
          str(bound_of(now_ok["agent"])))
    check("nothing stripped this time", now_ok.get("strippedTools") == [], str(now_ok.get("strippedTools")))

    print("\n== Order: write-capability is decided before approval ==")
    # An approved write-capable tool must still be refused, and refused *as* a
    # write tool — approval is never an override for the locked invariant.
    wc = post("/v1/tools", {
        "name": f"zz_verify_guard_wc_{RUN}", "category": "verification", "description": "x",
        "permission_ceiling": "draft", "write_capable": True,
        "schema": {"inputs": {}, "outputs": {}},
    })
    wc_id = wc["tool"]["id"]
    post(f"/v1/approvals/{wc['approval']['id']}/decide", {"decision": "approved", "note": "verify"})
    res_wc = post(f"/v1/agents/{clean_id}/config-change", {
        "groupKey": "tooling", "field": "bound_tools", "newValue": [GOOD, f"tools://{wc_id}@v1"],
    })
    check("approved write tool still refused", bound_of(res_wc["agent"]) == [GOOD], str(bound_of(res_wc["agent"])))
    check("refused as write_capable, not not_approved",
          res_wc["strippedTools"][0]["reason"] == "write_capable", str(res_wc["strippedTools"]))

    print("\n== Duplicates collapse; order is preserved ==")
    dupes = register(f"ZZ Verify Guard {RUN} C", [GOOD, GOOD, "tools://log_reader@v1", GOOD])
    check("duplicate refs collapsed", bound_of(dupes["agent"]) == [GOOD, "tools://log_reader@v1"],
          str(bound_of(dupes["agent"])))
    check("a duplicate is not reported as stripped", dupes.get("strippedTools") == [], str(dupes.get("strippedTools")))

    print("\n== Seeded agents were never touched ==")
    noc = fetch_agent("agt-noc-incident-summarizer-20260122-b2e7")
    check("seeded agent keeps its bound tool", bound_of(noc) == ["tools://incident_reader@v1"], str(bound_of(noc)))

finally:
    cleanup()

print(f"\n  ..   left behind: zz-verify-guard-*-{RUN} tools (no tool delete endpoint, by design)")
print("\nALL BOUND_TOOLS GUARD TESTS PASSED" if failures == 0 else f"\n{failures} BOUND_TOOLS GUARD TEST(S) FAILED")
sys.exit(0 if failures == 0 else 1)
