"""Backend verification for the MCP connector layer.

Covers what moved server-side when connectors became persisted, and which the
frontend `test/causality.ts` suite therefore can no longer exercise: the
connector -> tool health cascade, its persistence, and MCP tools/list.

Run against a live backend (default http://127.0.0.1:8787):

    backend\\.venv\\Scripts\\python.exe backend\\verify_connectors.py

Exits non-zero on the first failure. Safe to re-run: it restores every
connector it touches to the state it found.
"""

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"

# Seed agent whose 4 bound tools span both cases: 2 connector-served
# (incident_reader -> gcp-ticketing, jira_reader -> jira) and 2 local
# (log_reader, health_checker). See src/seed/agents.ts.
INCIDENT_AGENT = "agt-incident-response-coordinator-20260205-c3d9"
CONTRACT_AGENT = "agt-contract-clause-finder-20260218-d4c1"  # 1 local tool only

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


def tools_of(bootstrap: dict, connector_id: str) -> dict[str, str]:
    return {t["id"]: t["status"] for t in bootstrap["tools"] if t["connector_id"] == connector_id}


try:
    get("/v1/bootstrap")
except (urllib.error.URLError, TimeoutError) as err:
    print(f"Backend unreachable at {BASE} — start it first ({err}).")
    sys.exit(2)

print("\n== Bootstrap exposes connectors ==")
boot = get("/v1/bootstrap")
check("connectors key present", "connectors" in boot)
# Phase 2 added connector registration, so the count is no longer fixed. The
# invariant that actually matters is that the seed is intact — asserting
# `len == 5` encoded "connectors are seed-only", which is precisely what
# Phase 2 ended.
SEEDED = {"gcp-ticketing", "confluence", "jira", "crm-readonly", "filings-gateway"}
ids = {c["id"] for c in boot["connectors"]}
check("all 5 seeded connectors present", SEEDED <= ids, f"missing {sorted(SEEDED - ids)}")
check("jira seeded degraded", next(c for c in boot["connectors"] if c["id"] == "jira")["status"] == "degraded")

print("\n== MCP tools/list ==")
listing = get("/v1/connectors/gcp-ticketing/tools")
check("returns the connector's tools", len(listing["tools"]) == 3, str(len(listing["tools"])))
check("no undiscovered tools in a clean seed", listing["undiscovered"] == [], str(listing["undiscovered"]))
check("no orphaned tools in a clean seed", listing["orphaned"] == [], str(listing["orphaned"]))
try:
    get("/v1/connectors/does-not-exist/tools")
    check("unknown connector 404s", False, "expected HTTPError")
except urllib.error.HTTPError as e:
    check("unknown connector 404s", e.code == 404, str(e.code))

print("\n== Normalize starting state ==")
# The suite drives `gcp-ticketing` with toggle-offline, which *flips* rather
# than sets. A connector left offline by a UI click (or an interrupted run)
# therefore inverts every assertion below. Normalize first, and remember what
# we found so the Restore section can put it back.
GCP = "gcp-ticketing"


def gcp_status() -> str:
    return next(c for c in get("/v1/bootstrap")["connectors"] if c["id"] == GCP)["status"]


found_offline = gcp_status() == "offline"
if found_offline:
    post(f"/v1/connectors/{GCP}/toggle-offline")
    print(f"  ..   {GCP} was offline on entry — brought online for the run, will be restored")
# A healthcheck lands `degraded` ~18% of the time; retry a few times so the
# cascade assertions below start from a known-clean `available`.
for _ in range(6):
    if gcp_status() == "connected":
        break
    post(f"/v1/connectors/{GCP}/healthcheck")
check("gcp-ticketing connected at start", gcp_status() == "connected", gcp_status())

print("\n== Connector health cascades onto served tools ==")
before = tools_of(get("/v1/bootstrap"), "gcp-ticketing")
check("gcp-ticketing serves tools", len(before) == 3, str(before))
check("all available to start", all(v == "available" for v in before.values()), str(before))

off = post("/v1/connectors/gcp-ticketing/toggle-offline")
check("connector went offline", off["connector"]["status"] == "offline")
check("3 tools cascaded", len(off["changedTools"]) == 3, str(len(off["changedTools"])))
check("all cascaded to offline", all(t["status"] == "offline" for t in off["changedTools"]))
check("audit event written", off["auditEvent"] is not None and off["auditEvent"]["action"] == "toggle_connector")
check("audit mentions the cascade", "Cascaded to 3 tool(s)" in (off["auditEvent"] or {}).get("detail", ""))

print("\n== Cascade persists (survives a refetch, i.e. it is in Postgres) ==")
boot2 = get("/v1/bootstrap")
check("connector still offline", next(c for c in boot2["connectors"] if c["id"] == "gcp-ticketing")["status"] == "offline")
after = tools_of(boot2, "gcp-ticketing")
check("served tools still offline", all(v == "offline" for v in after.values()), str(after))
local = next(t for t in boot2["tools"] if t["id"] == "log_reader")
check("connectorless tool untouched", local["status"] == "available", local["status"])

print("\n== Healthcheck does not silently revive an offline connector ==")
hc = post("/v1/connectors/gcp-ticketing/healthcheck")
check("healthcheck skipped while offline", hc.get("skipped") is True)
check("still offline", hc["connector"]["status"] == "offline")

print("\n== Restore ==")
on = post("/v1/connectors/gcp-ticketing/toggle-offline")
check("connector back online", on["connector"]["status"] == "connected")
check("3 tools restored", len(on["changedTools"]) == 3, str(len(on["changedTools"])))
check("all restored to available", all(t["status"] == "available" for t in on["changedTools"]))

print("\n== Healthcheck on a live connector ==")
hc2 = post("/v1/connectors/confluence/healthcheck")
check("returns a valid status", hc2["connector"]["status"] in ("connected", "degraded"), hc2["connector"]["status"])
check("audit event written", hc2["auditEvent"] is not None and hc2["auditEvent"]["action"] == "healthcheck")

# ---------------------------------------------------------------------------
# Phase 0 — connector resolution. The tool -> connector edge is a fixed FK, so
# an agent's MCP dependency set is derivable and must be derived in exactly one
# place (services/connector_resolution.py).
# ---------------------------------------------------------------------------

print("\n== Agent -> connector resolution ==")
res = get(f"/v1/agents/{INCIDENT_AGENT}/connectors")
check("4 bound tools resolved", len(res["bound_tools"]) == 4, str(res["bound_tools"]))
check("refs stripped to bare ids", "incident_reader" in res["bound_tools"], str(res["bound_tools"]))
ids = sorted(c["id"] for c in res["connectors"])
check("resolves to 2 connectors", ids == ["gcp-ticketing", "jira"], str(ids))
check("2 local tools need no connector", res["local_tools"] == ["health_checker", "log_reader"], str(res["local_tools"]))
check("no unknown tools", res["unknown_tools"] == [], str(res["unknown_tools"]))
served = {c["id"]: c["tools"] for c in res["connectors"]}
check("gcp-ticketing serves incident_reader", served.get("gcp-ticketing") == ["incident_reader"], str(served))
check("jira serves jira_reader", served.get("jira") == ["jira_reader"], str(served))

print("\n== Local-only agent resolves to zero connectors ==")
local_only = get(f"/v1/agents/{CONTRACT_AGENT}/connectors")
check("no connectors required", local_only["connectors"] == [], str(local_only["connectors"]))
check("contract_reader reported local", local_only["local_tools"] == ["contract_reader"], str(local_only["local_tools"]))
check("nothing unhealthy", local_only["unhealthy"] == [] and local_only["offline"] == [])

try:
    get("/v1/agents/does-not-exist/connectors")
    check("unknown agent 404s", False, "expected HTTPError")
except urllib.error.HTTPError as e:
    check("unknown agent 404s", e.code == 404, str(e.code))

print("\n== Unhealthy connectors tracked through the resolver ==")
jira_status = next(c for c in get("/v1/bootstrap")["connectors"] if c["id"] == "jira")["status"]
check(
    f"jira ({jira_status}) reflected in unhealthy",
    ("jira" in res["unhealthy"]) == (jira_status in ("degraded", "offline")),
    str(res["unhealthy"]),
)
check("nothing offline while all connectors are up", res["offline"] == [], str(res["offline"]))

post("/v1/connectors/gcp-ticketing/toggle-offline")
res_off = get(f"/v1/agents/{INCIDENT_AGENT}/connectors")
check("offline connector surfaces as a hard blocker", res_off["offline"] == ["gcp-ticketing"], str(res_off["offline"]))
check("offline connector also unhealthy", "gcp-ticketing" in res_off["unhealthy"], str(res_off["unhealthy"]))
check("local tools unaffected by the outage", res_off["local_tools"] == ["health_checker", "log_reader"], str(res_off["local_tools"]))

print("\n== Bind warns on an unhealthy connector but never blocks ==")
# Re-binding an already-bound tool is idempotent (tool_binding.py returns the
# agent unchanged), so this exercises the warning without mutating the seed.
bind_off = post(f"/v1/agents/{INCIDENT_AGENT}/tools/bind", {"toolId": "incident_reader"})
check("bind still succeeds", bind_off.get("ok") is True, str(bind_off.get("message")))
check("warning returned", bool(bind_off.get("warning")), str(bind_off.get("warning")))
check("warning names the connector", "GCP Ticketing" in (bind_off.get("warning") or ""), str(bind_off.get("warning")))
check("warning recorded in the audit detail", "WARNING:" in bind_off["auditEvent"]["detail"], bind_off["auditEvent"]["detail"])

print("\n== Restore ==")
post("/v1/connectors/gcp-ticketing/toggle-offline")
res_on = get(f"/v1/agents/{INCIDENT_AGENT}/connectors")
check("no connectors offline again", res_on["offline"] == [], str(res_on["offline"]))
bind_on = post(f"/v1/agents/{INCIDENT_AGENT}/tools/bind", {"toolId": "incident_reader"})
check("healthy connector binds without a warning", bind_on.get("warning") is None, str(bind_on.get("warning")))

print("\n== Local tools carry no connector (never a placeholder) ==")
bind_local = post(f"/v1/agents/{INCIDENT_AGENT}/tools/bind", {"toolId": "log_reader"})
check("local tool binds cleanly", bind_local.get("ok") is True)
check("no warning for a connectorless tool", bind_local.get("warning") is None, str(bind_local.get("warning")))

if found_offline:
    # Put back the offline state the run inherited, per this suite's promise to
    # restore every connector it touches.
    post(f"/v1/connectors/{GCP}/toggle-offline")
    print(f"\n  ..   {GCP} returned to offline (the state found on entry)")

print("\n== Write-capable tools are still rejected (unchanged invariant) ==")
blocked = None
try:
    post(f"/v1/agents/{INCIDENT_AGENT}/tools/bind", {"toolId": "ticket_updater"})
    check("write-capable bind rejected", False, "expected HTTP 400")
except urllib.error.HTTPError as e:
    blocked = json.loads(e.read().decode("utf-8"))
    check("write-capable bind rejected", e.code == 400, str(e.code))
if blocked:
    check("rejection is advisory-block", blocked.get("ok") is False and "write-capable" in blocked.get("message", ""), str(blocked.get("message")))

print("\nALL CONNECTOR TESTS PASSED" if failures == 0 else f"\n{failures} CONNECTOR TEST(S) FAILED")
sys.exit(0 if failures == 0 else 1)
