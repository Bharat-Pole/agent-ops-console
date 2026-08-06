"""Backend verification for the tool-call audit trail (deck slide 21, element 6).

Covers the two properties that make this a *trail* rather than a log: the
fields the client cannot forge (`system_accessed`, `permission`, `at` are all
resolved or stamped server-side), and the fact that blocked attempts are
recorded rather than silently dropped.

Run against a live backend (default http://127.0.0.1:8787):

    backend\\.venv\\Scripts\\python.exe backend\\verify_tool_calls.py

Exits non-zero on the first failure.

NOTE: an audit trail is append-only, so this suite **leaves rows behind** by
design — same as `audit_log`. It writes against real seed agents and never
mutates connector or tool state.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"

INCIDENT_AGENT = "agt-incident-response-coordinator-20260205-c3d9"
# Marks every row this run writes, so filter assertions can isolate them.
RUN = uuid.uuid4().hex[:8]

failures = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{'' if cond else '  ' + extra}")
    if not cond:
        failures += 1


def _request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    payload = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
    with urllib.request.urlopen(req, payload, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def get(path: str) -> dict:
    return _request("GET", path)


def post(path: str, body: dict | None = None) -> dict:
    return _request("POST", path, body)


def expect_400(path: str, body: dict, name: str) -> None:
    try:
        post(path, body)
        check(name, False, "expected HTTP 400")
    except urllib.error.HTTPError as e:
        check(name, e.code == 400, str(e.code))


def record(**kw) -> dict:
    body = {"agentId": INCIDENT_AGENT, "consumer": "playground", "latencyMs": 42, **kw}
    return post("/v1/tool-calls", body)["toolCall"]


try:
    get("/v1/bootstrap")
except (urllib.error.URLError, TimeoutError) as err:
    print(f"Backend unreachable at {BASE} — start it first ({err}).")
    sys.exit(2)

print("\n== Endpoint shape ==")
listing = get("/v1/tool-calls")
check("GET returns a toolCalls array", isinstance(listing.get("toolCalls"), list), str(type(listing.get("toolCalls"))))

print("\n== Slide 21's eight fields are all present ==")
call = record(toolInvoked="incident_reader", requestId=f"req-{RUN}-a")
for field in (
    "agent_id", "request_id", "consumer", "tool_invoked",
    "system_accessed", "result_status", "latency_ms", "exception_detail",
):
    check(f"field {field}", field in call, str(sorted(call)))
check("plus permission", "permission" in call)
check("plus at", "at" in call)

print("\n== system_accessed is resolved server-side, not supplied ==")
check("incident_reader → gcp-ticketing", call["system_accessed"] == "gcp-ticketing", str(call["system_accessed"]))
local = record(toolInvoked="log_reader", requestId=f"req-{RUN}-b")
check("local tool → null, not a placeholder", local["system_accessed"] is None, repr(local["system_accessed"]))
forged = record(toolInvoked="incident_reader", systemAccessed="totally-made-up", system_accessed="also-fake")
check("a client-supplied system is ignored", forged["system_accessed"] == "gcp-ticketing", str(forged["system_accessed"]))

print("\n== permission comes from the server's own tools table ==")
check("incident_reader → read", call["permission"] == "read", str(call["permission"]))
laundered = record(toolInvoked="incident_reader", permission="write")
check("a client-claimed permission is ignored", laundered["permission"] == "read", str(laundered["permission"]))

print("\n== Versioned refs are normalized ==")
ref = record(toolInvoked="tools://incident_reader@v1")
check("tools://…@v1 → bare id", ref["tool_invoked"] == "incident_reader", str(ref["tool_invoked"]))

print("\n== request_id is generated when absent ==")
gen = record(toolInvoked="incident_reader")
check("request_id present", bool(gen["request_id"]), str(gen["request_id"]))
check("request_id looks generated", gen["request_id"].startswith("req-"), str(gen["request_id"]))

print("\n== at is server-stamped ==")
stamped = record(toolInvoked="incident_reader", at="1999-01-01T00:00:00.000Z")
check("client timestamp ignored", not stamped["at"].startswith("1999"), str(stamped["at"]))

print("\n== An uncatalogued tool is logged, and says so ==")
ghost = record(toolInvoked="not_a_real_tool", requestId=f"req-{RUN}-ghost")
check("still recorded", ghost["tool_invoked"] == "not_a_real_tool")
check("no system invented", ghost["system_accessed"] is None, repr(ghost["system_accessed"]))
check("permission unknown", ghost["permission"] == "unknown", str(ghost["permission"]))
check("exception explains why", "not in the tool catalog" in (ghost["exception_detail"] or ""), str(ghost["exception_detail"]))

print("\n== Authority is re-derived server-side, not claimed ==")
# crm_reader is a real, healthy, read-only tool — but it is bound to the Churn
# agent, not this one. A claimed `ok` must not survive that.
unbound = record(toolInvoked="crm_reader", resultStatus="ok", requestId=f"req-{RUN}-unbound")
check("claimed ok overridden to blocked", unbound["result_status"] == "blocked", unbound["result_status"])
check("reason names the violation", "not bound to this agent" in (unbound["exception_detail"] or ""), str(unbound["exception_detail"]))
check("resolution still happened", unbound["system_accessed"] == "crm-readonly", str(unbound["system_accessed"]))
check("permission still from the catalog", unbound["permission"] == "read", str(unbound["permission"]))
check("row is still written, not rejected", bool(unbound["id"]))

bound_ok = record(toolInvoked="jira_reader", resultStatus="ok", requestId=f"req-{RUN}-bound")
check("a genuinely bound tool stays ok", bound_ok["result_status"] == "ok", bound_ok["result_status"])
check("and carries no violation note", bound_ok["exception_detail"] is None, str(bound_ok["exception_detail"]))

unknown_agent = post("/v1/tool-calls", {
    "agentId": "agt-does-not-exist", "toolInvoked": "incident_reader", "latencyMs": 5,
})["toolCall"]
check("unregistered agent cannot be authorized", unknown_agent["result_status"] == "blocked", unknown_agent["result_status"])
check("reason says so", "not registered" in (unknown_agent["exception_detail"] or ""), str(unknown_agent["exception_detail"]))

check("uncatalogued tool is also unauthorized", ghost["result_status"] == "blocked", ghost["result_status"])
check("both reasons recorded", "not bound to this agent" in (ghost["exception_detail"] or ""), str(ghost["exception_detail"]))

print("\n== Validation ==")
expect_400("/v1/tool-calls", {"toolInvoked": "incident_reader"}, "missing agentId 400s")
expect_400("/v1/tool-calls", {"agentId": INCIDENT_AGENT}, "missing toolInvoked 400s")
expect_400("/v1/tool-calls", {"agentId": INCIDENT_AGENT, "toolInvoked": "incident_reader", "consumer": "nope"}, "bad consumer 400s")
expect_400("/v1/tool-calls", {"agentId": INCIDENT_AGENT, "toolInvoked": "incident_reader", "resultStatus": "maybe"}, "bad resultStatus 400s")
expect_400("/v1/tool-calls", {"agentId": INCIDENT_AGENT, "toolInvoked": "incident_reader", "latencyMs": -5}, "negative latency 400s")

print("\n== A blocked result writes an audit event ==")
blocked_res = post("/v1/tool-calls", {
    "agentId": INCIDENT_AGENT,
    "toolInvoked": "incident_reader",
    "consumer": "playground",
    "resultStatus": "blocked",
    "latencyMs": 0,
    "requestId": f"req-{RUN}-blocked",
    "exceptionDetail": "Denied at the runtime HITL gate — no result executed.",
})
check("call recorded as blocked", blocked_res["toolCall"]["result_status"] == "blocked")
check("audit event written", blocked_res.get("auditEvent") is not None)
check("audit action is tool_call_blocked", (blocked_res.get("auditEvent") or {}).get("action") == "tool_call_blocked")
check("audit detail carries the reason", "HITL gate" in (blocked_res.get("auditEvent") or {}).get("detail", ""))
check("an ok result writes no audit event", post("/v1/tool-calls", {
    "agentId": INCIDENT_AGENT, "toolInvoked": "incident_reader", "latencyMs": 1,
}).get("auditEvent") is None)

print("\n== A rejected bind lands here as `blocked` (the invariant, as evidence) ==")
try:
    post(f"/v1/agents/{INCIDENT_AGENT}/tools/bind", {"toolId": "ticket_updater"})
    check("write-capable bind still rejected", False, "expected HTTP 400")
except urllib.error.HTTPError as e:
    check("write-capable bind still rejected", e.code == 400, str(e.code))

bind_rows = get("/v1/tool-calls?toolId=ticket_updater&status=blocked")["toolCalls"]
check("the rejection was logged", len(bind_rows) >= 1, str(len(bind_rows)))
if bind_rows:
    row = bind_rows[0]
    check("consumer is console, not playground", row["consumer"] == "console", str(row["consumer"]))
    check("reason recorded", "write-capable" in (row["exception_detail"] or ""), str(row["exception_detail"]))
    check("system still resolved", row["system_accessed"] == "gcp-ticketing", str(row["system_accessed"]))

print("\n== Filters ==")
by_agent = get(f"/v1/tool-calls?agentId={INCIDENT_AGENT}")["toolCalls"]
check("agentId filter applied", all(c["agent_id"] == INCIDENT_AGENT for c in by_agent), str(len(by_agent)))
by_tool = get("/v1/tool-calls?toolId=log_reader")["toolCalls"]
check("toolId filter applied", all(c["tool_invoked"] == "log_reader" for c in by_tool), str(len(by_tool)))
by_status = get("/v1/tool-calls?status=blocked")["toolCalls"]
check("status filter applied", all(c["result_status"] == "blocked" for c in by_status), str(len(by_status)))
combined = get(f"/v1/tool-calls?agentId={INCIDENT_AGENT}&status=blocked")["toolCalls"]
check("filters AND together", all(c["agent_id"] == INCIDENT_AGENT and c["result_status"] == "blocked" for c in combined))
check("unmatched filter returns empty", get("/v1/tool-calls?agentId=nobody")["toolCalls"] == [])

print("\n== Ordering and limit ==")
recent = get("/v1/tool-calls?limit=25")["toolCalls"]
check("limit respected", len(recent) <= 25, str(len(recent)))
ats = [c["at"] for c in recent]
check("newest first", ats == sorted(ats, reverse=True), str(ats[:3]))
check("limit=1 returns one row", len(get("/v1/tool-calls?limit=1")["toolCalls"]) == 1)

print("\nALL TOOL-CALL TESTS PASSED" if failures == 0 else f"\n{failures} TOOL-CALL TEST(S) FAILED")
sys.exit(0 if failures == 0 else 1)
