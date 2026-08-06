"""Backend verification for the connector prioritization backlog — Phase 4.

Deck slide 21 element 7, SOW deliverable 3.3. What this suite is really
defending is one rule:

    **A system with no existing MCP server cannot be scheduled into the 90-day
    phase.**

That is not a preference — the SOW's boundaries table says *"Will install and
configure MCP servers only; building new MCP servers is out of scope"*, so a
90-day plan that includes ServiceNow is a plan that quietly assumes work the
contract excludes. It is enforced server-side, on every write, and validated
against the **merged** item so a two-step patch cannot walk around it.

The rest of the suite holds the lines that make this an assessment rather than a
list of opinions:

  · the seven candidates are the SOW's systems of record, seeded and ranked;
  · `recommended` is **derived** from the ranking, never stored, so the headline
    cannot drift from the table beneath it;
  · a rationale is mandatory — a ranking without a reason is not an assessment;
  · `unknown` is a legitimate value and is preserved, not coerced to `none`.

Run against a live backend (default http://127.0.0.1:8787):

    backend\\.venv\\Scripts\\python.exe backend\\verify_connector_backlog.py

Exits non-zero on the first failure.

NOTE: this suite **mutates seeded backlog rows and restores them** — it captures
each row it touches on entry and writes it back at the end, the same discipline
`verify_tool_governance.py` uses for the Incident Coordinator's config. It
creates nothing, so it leaves nothing behind.
"""

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"

# The SOW's systems of record: "Jira, GitHub, Confluence, ServiceNow, MDR, CCAI,
# and BigQuery remain authoritative systems."
SOW_SYSTEMS = {"jira", "github", "confluence", "servicenow", "mdr", "ccai", "bigquery"}

failures = 0
restore: dict[str, dict] = {}


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


def patch(path: str, body: dict) -> dict:
    return _request("PATCH", path, body)


def expect_400(item_id: str, body: dict, name: str, must_mention: str = "") -> None:
    try:
        _request("PATCH", f"/v1/connector-backlog/{item_id}", body)
        check(name, False, "expected HTTP 400")
    except urllib.error.HTTPError as e:
        if e.code != 400:
            check(name, False, f"got {e.code}")
            return
        msg = json.loads(e.read().decode("utf-8")).get("message", "")
        check(name, must_mention.lower() in msg.lower() if must_mention else True, msg)


def snapshot(item_id: str) -> dict:
    """Capture a row so the suite can put it back."""
    item = next(b for b in get("/v1/connector-backlog")["backlog"] if b["id"] == item_id)
    restore.setdefault(item_id, item)
    return item


try:
    get("/v1/bootstrap")
except (urllib.error.URLError, TimeoutError) as err:
    print(f"Backend unreachable at {BASE} — start it first ({err}).")
    sys.exit(2)

try:
    print("\n== The candidate set is the SOW's seven systems of record ==")
    data = get("/v1/connector-backlog")
    backlog = data["backlog"]
    ids = {b["id"] for b in backlog}
    check("seven systems assessed", len(backlog) == 7, str(len(backlog)))
    check("they are the SOW's systems of record", ids == SOW_SYSTEMS, str(sorted(ids)))
    check("returned in rank order", [b["rank"] for b in backlog] == sorted(b["rank"] for b in backlog),
          str([b["rank"] for b in backlog]))
    check("every system carries a rationale", all(b["rationale"].strip() for b in backlog))
    check("no candidate is left unphased", all(b["phase"] in ("day_90", "later") for b in backlog))

    print("\n== The summary is DERIVED, not stored ==")
    s = data["summary"]
    day_90 = [b for b in backlog if b["phase"] == "day_90"]
    check("day_90 count matches the rows", s["day_90"] == len(day_90), f"{s['day_90']} vs {len(day_90)}")
    check("later count matches the rows", s["later"] == len(backlog) - len(day_90))
    check("total matches", s["total"] == len(backlog))
    check("recommended is rank 1 of the 90-day set",
          s["recommended"] == min(day_90, key=lambda b: b["rank"])["id"], str(s["recommended"]))
    check("blocked_on_no_server lists exactly the serverless systems",
          set(s["blocked_on_no_server"]) == {b["id"] for b in backlog if b["mcp_server"] not in ("official", "community")},
          str(s["blocked_on_no_server"]))

    print("\n== The SOW boundary is enforced, not annotated (THE invariant) ==")
    # ServiceNow has no MCP server. Scheduling it into the 90 days would be
    # planning work the SOW excludes.
    sn = snapshot("servicenow")
    check("servicenow seeded with no server", sn["mcp_server"] == "none", sn["mcp_server"])
    check("...and therefore not in the 90-day phase", sn["phase"] == "later", sn["phase"])
    expect_400("servicenow", {"phase": "day_90"}, "cannot schedule a serverless system into 90 days", "out of scope")
    check("rejected patch did not persist",
          next(b for b in get("/v1/connector-backlog")["backlog"] if b["id"] == "servicenow")["phase"] == "later")

    print("\n== ...and it cannot be walked around in two steps ==")
    # Validation runs against the MERGED item, so flipping phase and server in
    # separate calls must fail at the first one that makes the pair invalid.
    expect_400("mdr", {"phase": "day_90"}, "unassessed system cannot be scheduled either", "out of scope")
    # The legitimate route: confirm a server exists, THEN schedule it.
    ok_patch = patch("/v1/connector-backlog/servicenow", {
        "mcp_server": "community", "mcp_server_note": "zz-verify probe", "phase": "day_90",
    })
    check("confirming a server unblocks the 90-day phase", ok_patch["item"]["phase"] == "day_90", str(ok_patch["item"]["phase"]))
    check("both fields reported as changed", set(ok_patch["changed"]) >= {"mcp_server", "phase"}, str(ok_patch["changed"]))
    check("audit event written", ok_patch["auditEvent"]["action"] == "update_connector_backlog")

    print("\n== ...and removing the server again cannot leave it stranded in the 90 days ==")
    expect_400("servicenow", {"mcp_server": "none"}, "cannot drop the server while phase is day_90", "out of scope")
    check("still community/day_90 after the rejected patch",
          next(b for b in get("/v1/connector-backlog")["backlog"] if b["id"] == "servicenow")["mcp_server"] == "community")

    print("\n== Field validation ==")
    snapshot("jira")
    expect_400("jira", {"phase": "someday"}, "bad phase 400s")
    expect_400("jira", {"mcp_server": "probably"}, "bad mcp_server 400s")
    expect_400("jira", {"status": "vibes"}, "bad status 400s")
    expect_400("jira", {"data_sensitivity": "spicy"}, "bad data_sensitivity 400s")
    expect_400("jira", {"transport": "carrier-pigeon"}, "bad transport 400s")
    expect_400("jira", {"auth_model": "trust-me"}, "bad auth_model 400s")
    expect_400("jira", {"rank": 0}, "rank below 1 400s")
    expect_400("jira", {"rationale": "   "}, "empty rationale 400s", "rationale")
    # The deprecated MCP binding must not be selectable here — this vocabulary
    # follows spec 2026-07-28, not our legacy McpTransport enum (CONCERNS D8).
    expect_400("jira", {"transport": "sse"}, "legacy sse transport is not a valid value", "transport")

    print("\n== `unknown` is a real state and is preserved ==")
    mdr = next(b for b in get("/v1/connector-backlog")["backlog"] if b["id"] == "mdr")
    check("mdr is unassessed, not asserted absent", mdr["mcp_server"] == "unknown", mdr["mcp_server"])
    check("mdr says why in its blockers", "not identified" in (mdr["blockers"] or "").lower(), str(mdr["blockers"]))
    check("unassessed systems are summarised", "mdr" in data["summary"]["unassessed"], str(data["summary"]["unassessed"]))

    print("\n== Editing works, and no-ops are honest ==")
    upd = patch("/v1/connector-backlog/jira", {"status": "access_requested", "access_owner": "zz-verify owner"})
    check("status updated", upd["item"]["status"] == "access_requested")
    check("owner updated", upd["item"]["access_owner"] == "zz-verify owner")
    check("updated_at stamped", bool(upd["item"]["updated_at"]))
    noop = patch("/v1/connector-backlog/jira", {"status": "access_requested"})
    check("no-op reports no changes", noop["changed"] == [], str(noop["changed"]))
    check("no-op writes no audit event", noop["auditEvent"] is None)

    print("\n== Identity fields are not editable ==")
    sneaky = patch("/v1/connector-backlog/jira", {"id": "not-jira", "system_name": "Not Jira"})
    check("id unchanged", sneaky["item"]["id"] == "jira", sneaky["item"]["id"])
    check("system_name unchanged", sneaky["item"]["system_name"] == "Jira", sneaky["item"]["system_name"])

    print("\n== Unknown item 404s; the set cannot be extended over the API ==")
    try:
        _request("PATCH", "/v1/connector-backlog/salesforce", {"phase": "later"})
        check("unknown system 404s", False, "expected 404")
    except urllib.error.HTTPError as e:
        check("unknown system 404s", e.code == 404, str(e.code))
    try:
        _request("POST", "/v1/connector-backlog", {"id": "salesforce"})
        check("no POST route — the candidate set is the SOW's", False, "expected 405")
    except urllib.error.HTTPError as e:
        check("no POST route — the candidate set is the SOW's", e.code in (404, 405), str(e.code))

finally:
    if restore:
        print("\n== Restore: seeded rows are left exactly as they were found ==")
        for item_id, original in restore.items():
            patch(f"/v1/connector-backlog/{item_id}", {
                k: original[k] for k in (
                    "rank", "phase", "mcp_server", "mcp_server_note", "transport", "auth_model",
                    "data_sensitivity", "candidate_tools", "access_owner", "status", "rationale",
                    "blockers", "existing_connector_id",
                )
            })
        now = {b["id"]: b for b in get("/v1/connector-backlog")["backlog"]}
        for item_id, original in restore.items():
            same = all(now[item_id][k] == original[k] for k in ("phase", "mcp_server", "status", "access_owner", "rank"))
            check(f"{item_id} restored", same, str(now[item_id]))

print("\nALL CONNECTOR BACKLOG TESTS PASSED" if failures == 0 else f"\n{failures} CONNECTOR BACKLOG TEST(S) FAILED")
sys.exit(0 if failures == 0 else 1)
