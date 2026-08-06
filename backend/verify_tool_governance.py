"""Backend verification for Phase 3 — tool approval + tool policy fields.

Phase 3 adds a second governance gate to a path that already had one, so most
of this suite exists to prove the two gates are *independent* and that neither
can be talked around from the client:

  1. **Cataloguing is not consent.** A tool created through the console is
     `pending` and `bind_tool()` rejects it — even though it is read-only,
     available, and otherwise perfectly bindable. A supplied `approval_state`
     is ignored, not merged.
  2. **Approval is not a write exemption.** Approving a write-capable tool does
     NOT make it bindable. The advisory-only invariant is checked first and
     independently (ROADMAP Q6 — loosening that is a governance decision).
  3. **Consent and health are separate columns.** Approving a tool cannot move
     `status`, and the connector health cascade cannot move `approval_state`.
     Either direction would let one launder itself into the other.
  4. **The approval queue is shared, not duplicated** (Blueprint §11) — a tool
     item lands in the same `approvals` table, and deciding it through the same
     endpoint flips the tool.
  5. **The policy PATCH is policy-only** — owner and risk_level, nothing that
     governance depends on.

Run against a live backend (default http://127.0.0.1:8787):

    backend\\.venv\\Scripts\\python.exe backend\\verify_tool_governance.py

Exits non-zero on the first failure.

NOTE: like the other suites this **leaves rows behind** — tools named
`zz_verify_*` (there is no tool delete endpoint, same reasoning as connectors)
plus their approval items and audit events. It does not touch the 12 seeded
tools, and it restores any connector state it changes.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"

RUN = uuid.uuid4().hex[:6]

failures = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{'' if cond else '  ' + extra}")
    if not cond:
        failures += 1


def _request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    payload = json.dumps(body or {}).encode("utf-8") if method in ("POST", "PATCH") else None
    with urllib.request.urlopen(req, payload, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def get(path: str) -> dict:
    return _request("GET", path)


def post(path: str, body: dict | None = None) -> dict:
    return _request("POST", path, body)


def patch(path: str, body: dict | None = None) -> dict:
    return _request("PATCH", path, body)


def post_rejected(path: str, body: dict) -> dict:
    """A refused bind is HTTP 400 *with a body* — the rejection reason and its
    audit event are the thing under test, so the body is read, not discarded."""
    try:
        result = _request("POST", path, body)
        return {"ok": True, **result}
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def expect_status(method: str, path: str, body: dict, code: int, name: str) -> None:
    try:
        _request(method, path, body)
        check(name, False, f"expected HTTP {code}")
    except urllib.error.HTTPError as e:
        check(name, e.code == code, f"got {e.code}")


def make_tool(suffix: str, **overrides) -> dict:
    body = {
        "name": f"zz_verify_{suffix}_{RUN}",
        "category": "verification",
        "description": "Created by verify_tool_governance.py.",
        "permission_ceiling": "read",
        "write_capable": False,
        "schema": {"inputs": {"q": "string"}, "outputs": {"rows": "Row[]"}},
    }
    body.update(overrides)
    return post("/v1/tools", body)


def find_tool(tool_id: str) -> dict | None:
    return next((t for t in get("/v1/bootstrap")["tools"] if t["id"] == tool_id), None)


def find_approval(approval_id: str) -> dict | None:
    return next((a for a in get("/v1/bootstrap")["approvals"] if a["id"] == approval_id), None)


try:
    get("/v1/bootstrap")
except (urllib.error.URLError, TimeoutError) as err:
    print(f"Backend unreachable at {BASE} — start it first ({err}).")
    sys.exit(2)

AGENT = "agt-incident-response-coordinator-20260205-c3d9"

# This suite has to prove that an *approved* tool actually binds, which mutates
# a seeded agent's bound_tools — and `verify_connectors.py` asserts that agent
# has exactly 4. So capture the config on entry and put it back on exit, the
# same normalize-and-restore discipline verify_connectors.py uses for the
# gcp-ticketing toggle. Without this the two suites fight over shared state and
# the failure looks like a code defect when it is test pollution.
_agent_row = next(a for a in get("/v1/bootstrap")["agents"] if a["config"]["identity"]["agent_id"]["value"] == AGENT)
ORIGINAL_CONFIG = _agent_row["config"]
# Self-healing: an earlier run of this suite (or one interrupted before its
# restore) may have left its own tools bound. Strip them from the baseline so
# pollution is corrected rather than captured and written back forever.
ORIGINAL_CONFIG["tooling"]["bound_tools"]["value"] = [
    ref for ref in ORIGINAL_CONFIG["tooling"]["bound_tools"]["value"]
    if not ref.startswith("tools://zz-verify-")
]
ORIGINAL_BOUND = list(ORIGINAL_CONFIG["tooling"]["bound_tools"]["value"])


def restore_agent() -> None:
    patch(f"/v1/agents/{AGENT}", {"config": ORIGINAL_CONFIG})

print("\n== The seeded catalog is grandfathered, not retro-queued ==")
boot = get("/v1/bootstrap")
# The id is slugified from the name, so `zz_verify_x` is catalogued as
# `zz-verify-x` — match the id form, not the name form, or previous runs of
# this suite look like seeded tools.
seeded = [t for t in boot["tools"] if not t["id"].startswith("zz-verify-")]
check("seeded tools are all approved", all(t["approval_state"] == "approved" for t in seeded),
      str([t["id"] for t in seeded if t["approval_state"] != "approved"]))
check("seeded tools carry no fabricated owner", all(t["owner"] is None for t in seeded))
check("seeded tools carry no fabricated risk_level", all(t["risk_level"] is None for t in seeded))
check("no seeded tool raised an approval item",
      not any(a["entity_type"] == "tool" and a["entity_id"] in {t["id"] for t in seeded} for a in boot["approvals"]))

print("\n== Pre-existing agent approvals survived the widening ==")
agent_items = [a for a in boot["approvals"] if a["entity_type"] == "agent"]
check("seeded approvals are entity_type=agent", len(agent_items) >= 15, str(len(agent_items)))
check("entity_id backfilled from agent_id", all(a["entity_id"] == a["agent_id"] for a in agent_items))
check("required_by_path still set for agent items", all(a["required_by_path"] for a in agent_items))

print("\n== Cataloguing is not consent (invariant 1) ==")
created = make_tool("pending")
tool = created["tool"]
tid = tool["id"]
check("new tool is pending", tool["approval_state"] == "pending", tool["approval_state"])
check("new tool is still operationally available", tool["status"] == "available", tool["status"])
check("an approval item was raised", bool(created.get("approval")))
approval = created["approval"]
check("item is a tool item", approval["entity_type"] == "tool", str(approval.get("entity_type")))
check("item points at the tool", approval["entity_id"] == tid, str(approval.get("entity_id")))
check("item has no agent", approval["agent_id"] is None, str(approval.get("agent_id")))
check("item has no governance path", approval["required_by_path"] is None, str(approval.get("required_by_path")))
check("item is pending", approval["status"] == "pending")
check("audit says not yet bindable", "not yet bindable" in created["auditEvent"]["detail"], created["auditEvent"]["detail"])

print("\n== A supplied approval_state is ignored, not merged ==")
forged = make_tool("forged", approval_state="approved", status="offline")["tool"]
check("client cannot self-approve", forged["approval_state"] == "pending", forged["approval_state"])
check("client cannot set status either", forged["status"] == "available", forged["status"])

print("\n== bind_tool() rejects a pending tool (the second server-side gate) ==")
bind = post_rejected(f"/v1/agents/{AGENT}/tools/bind", {"toolId": tid})
check("bind refused", bind["ok"] is False, str(bind))
check("reason names approval", "approval" in bind["message"].lower(), bind["message"])
check("rejection audited", bind["auditEvent"]["action"] == "bind_rejected", bind["auditEvent"]["action"])
after = find_tool(tid)
check("tool did not acquire a user", after["used_by"] == [], str(after["used_by"]))

print("\n== ...and the rejected bind is logged as evidence (slide 21 element 6) ==")
calls = get(f"/v1/tool-calls?toolId={tid}")["toolCalls"]
check("a blocked row exists", any(c["result_status"] == "blocked" for c in calls), str(len(calls)))
check("consumer is console", all(c["consumer"] == "console" for c in calls), str([c["consumer"] for c in calls]))
check("reason recorded on the row", any("approval" in (c["exception_detail"] or "").lower() for c in calls))

print("\n== Deciding it on the SHARED queue flips the tool (invariant 4) ==")
decided = post(f"/v1/approvals/{approval['id']}/decide", {"decision": "approved", "note": "verify"})
check("same endpoint serves tool items", decided["approval"]["status"] == "approved")
check("response carries the tool", decided.get("tool", {}).get("id") == tid, str(decided.get("tool")))
check("no agent in a tool decision", decided["agent"] is None, str(decided["agent"]))
check("tool is now approved", decided["tool"]["approval_state"] == "approved", decided["tool"]["approval_state"])
check("decision persisted", find_tool(tid)["approval_state"] == "approved")
check("queue item persisted", find_approval(approval["id"])["status"] == "approved")

print("\n== Approval does not move health, and health does not move approval (invariant 3) ==")
check("approving did not touch status", find_tool(tid)["status"] == "available", find_tool(tid)["status"])
# gcp-ticketing serves incident_reader/slack_notifier/ticket_updater. Toggle it
# offline and confirm the cascade moves `status` only. Restored below.
off = post("/v1/connectors/gcp-ticketing/toggle-offline")
check("cascade set served tools offline", any(t["status"] == "offline" for t in off["changedTools"]), str(off["changedTools"]))
served = [t for t in get("/v1/bootstrap")["tools"] if t["connector_id"] == "gcp-ticketing"]
check("cascade left approval_state alone", all(t["approval_state"] == "approved" for t in served),
      str([(t["id"], t["approval_state"]) for t in served]))
back = post("/v1/connectors/gcp-ticketing/toggle-offline")
check("connector restored", back["connector"]["status"] == "connected", back["connector"]["status"])

print("\n== An approved read-only tool binds normally ==")
bind_ok = post(f"/v1/agents/{AGENT}/tools/bind", {"toolId": tid})
check("bind succeeds once approved", bind_ok["ok"] is True, str(bind_ok.get("message")))
check("bind audited", bind_ok["auditEvent"]["action"] == "bind_tool")
check("tool records the agent", AGENT in find_tool(tid)["used_by"])

print("\n== Approval is NOT a write exemption (invariant 2) ==")
wc = make_tool("writer", write_capable=True, permission_ceiling="draft")
wc_tool, wc_appr = wc["tool"], wc["approval"]
check("write-capable tool is catalogued", wc_tool["write_capable"] is True)
check("...and still queued for approval", wc_tool["approval_state"] == "pending")
approved_wc = post(f"/v1/approvals/{wc_appr['id']}/decide", {"decision": "approved", "note": "verify"})
check("a write tool can be approved (visibility)", approved_wc["tool"]["approval_state"] == "approved")
wc_bind = post_rejected(f"/v1/agents/{AGENT}/tools/bind", {"toolId": wc_tool['id']})
check("but it STILL does not bind", wc_bind["ok"] is False, str(wc_bind))
check("rejected on write-capability, not approval", "write-capable" in wc_bind["message"], wc_bind["message"])

print("\n== A rejected tool stays catalogued and unbindable ==")
rej = make_tool("rejected")
rej_tool, rej_appr = rej["tool"], rej["approval"]
rejected = post(f"/v1/approvals/{rej_appr['id']}/decide", {"decision": "rejected", "note": "verify"})
check("tool marked rejected", rejected["tool"]["approval_state"] == "rejected", rejected["tool"]["approval_state"])
check("still in the catalog", find_tool(rej_tool["id"]) is not None)
rej_bind = post_rejected(f"/v1/agents/{AGENT}/tools/bind", {"toolId": rej_tool["id"]})
check("rejected tool does not bind", rej_bind["ok"] is False, str(rej_bind))
check("reason names the rejection", "rejected" in rej_bind["message"], rej_bind["message"])

print("\n== Policy fields: owner + risk_level (Phase 3.3) ==")
policy = make_tool("policy", owner="Verification Team", risk_level="medium")["tool"]
check("owner persisted on create", policy["owner"] == "Verification Team", str(policy["owner"]))
check("risk_level persisted on create", policy["risk_level"] == "medium", str(policy["risk_level"]))
upd = patch(f"/v1/tools/{policy['id']}", {"owner": "Platform Engineering", "risk_level": "high"})
check("owner updated", upd["tool"]["owner"] == "Platform Engineering")
check("risk_level updated", upd["tool"]["risk_level"] == "high")
check("changed list reported", sorted(upd["changed"]) == ["owner", "risk_level"], str(upd["changed"]))
check("update audited", upd["auditEvent"]["action"] == "update_tool_policy")
noop = patch(f"/v1/tools/{policy['id']}", {"owner": "Platform Engineering"})
check("no-op patch reports no changes", noop["changed"] == [], str(noop["changed"]))
check("no-op patch writes no audit event", noop["auditEvent"] is None)
cleared = patch(f"/v1/tools/{policy['id']}", {"owner": "", "risk_level": ""})
check("owner can be cleared to unassigned", cleared["tool"]["owner"] is None, str(cleared["tool"]["owner"]))
check("risk can be cleared to unclassified", cleared["tool"]["risk_level"] is None, str(cleared["tool"]["risk_level"]))

print("\n== The write-capable risk floor ==")
floored = make_tool("floor", write_capable=True, permission_ceiling="draft")["tool"]
check("omitted risk_level is raised to the floor", floored["risk_level"] == "high", str(floored["risk_level"]))
expect_status("POST", "/v1/tools", {
    "name": f"zz_verify_low_{RUN}", "category": "verification", "description": "x",
    "permission_ceiling": "draft", "write_capable": True, "risk_level": "low",
}, 400, "write-capable below the floor 400s")
expect_status("PATCH", f"/v1/tools/{floored['id']}", {"risk_level": "medium"}, 400,
              "patching a write tool below the floor 400s")
check("rejected patch did not persist", find_tool(floored["id"])["risk_level"] == "high")
expect_status("POST", "/v1/tools", {
    "name": f"zz_verify_badrisk_{RUN}", "category": "verification", "description": "x",
    "permission_ceiling": "read", "write_capable": False, "risk_level": "spicy",
}, 400, "unknown risk_level 400s")

print("\n== The policy PATCH cannot reach anything governance depends on (invariant 5) ==")
sneaky = patch(f"/v1/tools/{policy['id']}", {
    "approval_state": "approved", "status": "offline", "write_capable": True,
    "permission_ceiling": "validate", "connector_id": "gcp-ticketing", "used_by": ["nope"],
})
t = sneaky["tool"]
check("approval_state unreachable", t["approval_state"] == "pending", t["approval_state"])
check("status unreachable", t["status"] == "available", t["status"])
check("write_capable unreachable", t["write_capable"] is False)
check("permission_ceiling unreachable", t["permission_ceiling"] == "read", t["permission_ceiling"])
check("connector_id unreachable", t["connector_id"] is None, str(t["connector_id"]))
check("no-op reported for a patch of only unreachable fields", sneaky["changed"] == [], str(sneaky["changed"]))
expect_status("PATCH", "/v1/tools/does-not-exist", {"owner": "x"}, 404, "unknown tool 404s")

print("\n== Restore: the agent is left exactly as it was found ==")
restore_agent()
restored = next(a for a in get("/v1/bootstrap")["agents"] if a["config"]["identity"]["agent_id"]["value"] == AGENT)
check("bound_tools restored", restored["config"]["tooling"]["bound_tools"]["value"] == ORIGINAL_BOUND,
      str(restored["config"]["tooling"]["bound_tools"]["value"]))

print(f"\n  ..   left behind: zz-verify-*-{RUN} tools + their approval items (no delete endpoint by design)")
print("\nALL TOOL GOVERNANCE TESTS PASSED" if failures == 0 else f"\n{failures} TOOL GOVERNANCE TEST(S) FAILED")
sys.exit(0 if failures == 0 else 1)
