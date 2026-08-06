"""Backend verification for connector CRUD — Phase 2 (Blueprint §3.5).

The point of this suite is the two invariants an authoring path could quietly
break:

  1. **Status is owned by the health cascade**, never by an author. A supplied
     `status` is ignored on both create and update.
  2. **`tools_provided` is discovered, not typed.** A new connector advertises
     nothing, so `Discover tools` shows a real `undiscovered` diff — and
     registering a connector never creates tools.

Run against a live backend (default http://127.0.0.1:8787):

    backend\\.venv\\Scripts\\python.exe backend\\verify_connector_crud.py

Exits non-zero on the first failure.

NOTE: this suite **creates connectors and leaves them behind** — there is no
delete endpoint by design (a connector other rows may reference should not
vanish). Every row it makes is named `zz-verify-*` so they sort last in the UI
and are obvious. It does not touch the 5 seeded connectors.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"

RUN = uuid.uuid4().hex[:6]
NAME = f"zz-verify-{RUN}"

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


def expect_status(method: str, path: str, body: dict, code: int, name: str) -> None:
    try:
        _request(method, path, body)
        check(name, False, f"expected HTTP {code}")
    except urllib.error.HTTPError as e:
        check(name, e.code == code, f"got {e.code}")


try:
    get("/v1/bootstrap")
except (urllib.error.URLError, TimeoutError) as err:
    print(f"Backend unreachable at {BASE} — start it first ({err}).")
    sys.exit(2)

seeded = len(get("/v1/bootstrap")["connectors"])

print("\n== Register an MCP server ==")
created = post("/v1/connectors", {
    "name": NAME, "transport": "http",
    "endpoint": "https://mcp.verify.brightspeed.internal/v1", "auth_mode": "secret_manager",
})
c = created["connector"]
cid = c["id"]
check("id slugified from the name", cid == NAME, cid)
check("name persisted", c["name"] == NAME)
check("transport persisted", c["transport"] == "http")
check("auth_mode persisted", c["auth_mode"] == "secret_manager")
check("seeds as connected", c["status"] == "connected", c["status"])
check("advertises nothing yet", c["tools_provided"] == [], str(c["tools_provided"]))
check("last_healthcheck stamped", bool(c["last_healthcheck"]))
check("audit event written", created.get("auditEvent", {}).get("action") == "create_connector")

print("\n== It persists (i.e. it is in Postgres, not memory) ==")
boot = get("/v1/bootstrap")
check("appears in bootstrap", any(x["id"] == cid for x in boot["connectors"]))
check("connector count grew by 1", len(boot["connectors"]) == seeded + 1, str(len(boot["connectors"])))

print("\n== A new connector creates no tools (tools_provided is a claim) ==")
listing = get(f"/v1/connectors/{cid}/tools")
check("serves no tools", listing["tools"] == [], str(listing["tools"]))
check("nothing undiscovered yet", listing["undiscovered"] == [], str(listing["undiscovered"]))
check("nothing orphaned", listing["orphaned"] == [], str(listing["orphaned"]))

print("\n== Status is NOT author-settable (invariant 1) ==")
forged = post("/v1/connectors", {
    "name": f"{NAME}-forged", "transport": "http", "endpoint": "https://mcp.verify2.internal/v1",
    "auth_mode": "none", "status": "offline", "tools_provided": ["made_up_tool"],
})["connector"]
check("supplied status ignored", forged["status"] == "connected", forged["status"])
check("supplied tools_provided ignored", forged["tools_provided"] == [], str(forged["tools_provided"]))

print("\n== Validation ==")
bad = {"name": "x", "transport": "http", "endpoint": "https://ok.internal/v1", "auth_mode": "secret_manager"}
expect_status("POST", "/v1/connectors", {**bad, "name": ""}, 400, "missing name 400s")
expect_status("POST", "/v1/connectors", {**bad, "transport": "carrier-pigeon"}, 400, "bad transport 400s")
expect_status("POST", "/v1/connectors", {**bad, "auth_mode": "vibes"}, 400, "bad auth_mode 400s")
expect_status("POST", "/v1/connectors", {**bad, "endpoint": ""}, 400, "missing endpoint 400s")
expect_status("POST", "/v1/connectors", {**bad, "endpoint": "ftp://nope/v1"}, 400, "http endpoint must be http(s) 400s")
expect_status("POST", "/v1/connectors", {**bad, "transport": "sse", "endpoint": "ftp://nope/v1"}, 400, "sse endpoint scheme enforced 400s")
ok_stdio = post("/v1/connectors", {
    "name": f"{NAME}-stdio", "transport": "stdio",
    "endpoint": "npx -y @acme/mcp-server", "auth_mode": "none",
})["connector"]
check("stdio accepts a command, not a URL", ok_stdio["transport"] == "stdio" and ok_stdio["endpoint"].startswith("npx"))

print("\n== Duplicate names get a unique id, not a collision ==")
dupe = post("/v1/connectors", {
    "name": NAME, "transport": "http",
    "endpoint": "https://mcp.verify-dupe.internal/v1", "auth_mode": "oauth",
})["connector"]
check("id differs from the first", dupe["id"] != cid, f"{dupe['id']} vs {cid}")
check("id still derived from the name", dupe["id"].startswith(NAME), dupe["id"])

print("\n== Edit ==")
upd = patch(f"/v1/connectors/{cid}", {"name": f"{NAME}-renamed", "auth_mode": "oauth"})
check("name updated", upd["connector"]["name"] == f"{NAME}-renamed", upd["connector"]["name"])
check("auth_mode updated", upd["connector"]["auth_mode"] == "oauth")
check("untouched field preserved", upd["connector"]["transport"] == "http")
check("changed list reported", sorted(upd["changed"]) == ["auth_mode", "name"], str(upd["changed"]))
check("audit event written", upd.get("auditEvent", {}).get("action") == "update_connector")

print("\n== Edit cannot bend the invariants either ==")
sneaky = patch(f"/v1/connectors/{cid}", {"status": "offline", "tools_provided": ["nope"], "last_healthcheck": "1999-01-01"})
check("status unchanged by patch", sneaky["connector"]["status"] == "connected", sneaky["connector"]["status"])
check("tools_provided unchanged", sneaky["connector"]["tools_provided"] == [], str(sneaky["connector"]["tools_provided"]))
check("no-op patch reports no changes", sneaky["changed"] == [], str(sneaky["changed"]))
check("no-op patch writes no audit event", sneaky.get("auditEvent") is None)

print("\n== Partial patches are validated against the merged result ==")
# MCP's SSE transport IS an HTTP endpoint that streams events, so switching an
# https:// connector to `sse` is legitimate and must be allowed.
to_sse = patch(f"/v1/connectors/{cid}", {"transport": "sse"})
check("https endpoint is valid for sse (SSE runs over HTTP)", to_sse["connector"]["transport"] == "sse", str(to_sse.get("changed")))

# ...but a partial patch whose *merged* result is invalid must be rejected. An
# sse:// endpoint under `http` transport is the clean case: neither field is
# invalid alone, only the pair.
patch(f"/v1/connectors/{cid}", {"endpoint": "sse://mcp.verify.brightspeed.internal/v1"})
expect_status("PATCH", f"/v1/connectors/{cid}", {"transport": "http"}, 400, "sse:// endpoint + http transport rejected")
current = next(x for x in get("/v1/bootstrap")["connectors"] if x["id"] == cid)
check("rejected patch did not persist", current["transport"] == "sse", current["transport"])
expect_status("PATCH", f"/v1/connectors/{cid}", {"endpoint": "ftp://nope/v1"}, 400, "bad endpoint scheme rejected on patch")
expect_status("PATCH", "/v1/connectors/does-not-exist", {"name": "x"}, 404, "unknown connector 404s")

print("\n== The health cascade still owns status on a registered connector ==")
off = post(f"/v1/connectors/{cid}/toggle-offline")
check("cascade can set offline", off["connector"]["status"] == "offline")
check("no tools to cascade to", off["changedTools"] == [], str(off["changedTools"]))
on = post(f"/v1/connectors/{cid}/toggle-offline")
check("and back online", on["connector"]["status"] == "connected")

print(f"\n  ..   left behind: {NAME}-renamed, {NAME}-forged, {NAME}-stdio, {dupe['id']} (no delete endpoint by design)")
print("\nALL CONNECTOR CRUD TESTS PASSED" if failures == 0 else f"\n{failures} CONNECTOR CRUD TEST(S) FAILED")
sys.exit(0 if failures == 0 else 1)
