"""A conformant, read-only, Jira-shaped MCP server for local development.

Why this exists
---------------
Phase 5A builds the first code in this project that actually speaks MCP. That
code is *protocol* code — it does not care whether the server is on localhost or
at a vendor's URL. Building it against a local server means Phase 5B only has to
supply an endpoint and an auth mode (`ROADMAP.md` §4.0).

Two things make this more than a stub:

1. **The tests exercise a real protocol exchange.** The SDK's in-memory
   transport lets a suite hold this server object directly, so assertions run
   against genuine `tools/list` traffic rather than a mock.
2. **One tool is deliberately non-conformant.** `bad_header_reader` carries an
   invalid ``x-mcp-header`` annotation. The MCP specification says a client MUST
   reject such definitions and exclude them from the discovery result while
   logging a warning — one malformed tool must not poison the whole listing.
   That rule is impossible to demonstrate against a well-behaved public server,
   and it is exactly the kind of failure a governance console should survive.

Everything served here is synthetic. There is no real Brightspeed data in this
file and none should ever be added to it.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

SERVER_NAME = "reference-jira"
SERVER_VERSION = "0.1.0"

# The deliberately-malformed tool. A conformant client must drop this and keep
# everything else. Suites assert on the name, so keep it stable.
MALFORMED_TOOL_NAME = "bad_header_reader"

# Declares no `readOnlyHint`, so our deny-by-default mapping marks it
# write-capable. It is served precisely to prove the advisory-only invariant
# survives the protocol boundary: catalogued and visible, but never bindable.
WRITE_CAPABLE_TOOL_NAME = "jira_issue_commenter"

# What a conformant client should surface as read-only and bindable.
REFERENCE_TOOLS = ("jira_issue_reader", "jira_search", "jira_project_reader")

# One listing exercises all three outcomes: accepted read-only, accepted but
# write-guarded, and rejected outright.
ALL_SERVED_TOOLS = REFERENCE_TOOLS + (WRITE_CAPABLE_TOOL_NAME, MALFORMED_TOOL_NAME)

_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)

# An `x-mcp-header` annotation must map header names to strings. A dict where a
# string is required is exactly the malformed shape the spec tells clients to
# reject and exclude.
_INVALID_HEADER_META = {"x-mcp-header": {"X-Tenant-Id": {"not": "a string"}}}

# ---------------------------------------------------------------------------
# Synthetic records. Deliberately small and obviously fake.
# ---------------------------------------------------------------------------

_ISSUES: dict[str, dict[str, Any]] = {
    "NOC-1042": {
        "key": "NOC-1042",
        "project": "NOC",
        "summary": "Fibre cut on the Dallas ring causing elevated latency",
        "status": "In Progress",
        "priority": "P1",
        "assignee": "network-ops",
        "updated": "2026-08-09T14:12:00Z",
    },
    "NOC-1043": {
        "key": "NOC-1043",
        "project": "NOC",
        "summary": "Capacity threshold breached on the Austin aggregation node",
        "status": "Open",
        "priority": "P2",
        "assignee": "capacity-planning",
        "updated": "2026-08-10T08:31:00Z",
    },
    "REG-207": {
        "key": "REG-207",
        "project": "REG",
        "summary": "Quarterly filing evidence pack awaiting sign-off",
        "status": "Blocked",
        "priority": "P2",
        "assignee": "regulatory",
        "updated": "2026-08-07T17:45:00Z",
    },
}

_PROJECTS: dict[str, dict[str, Any]] = {
    "NOC": {"key": "NOC", "name": "Network Operations", "lead": "network-ops", "issue_count": 2},
    "REG": {"key": "REG", "name": "Regulatory Affairs", "lead": "regulatory", "issue_count": 1},
}


def build_server() -> MCPServer:
    """Construct the reference server.

    Returned rather than module-level so a suite can hold its own instance and
    an in-memory client can attach to it without a port or a subprocess.
    """
    server = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions=(
            "Read-only reference server for local development of the Agent Ops "
            "Console MCP client. All records are synthetic."
        ),
    )

    @server.tool(annotations=_READ_ONLY)
    def jira_issue_reader(issue_key: str) -> dict[str, Any]:
        """Read a single Jira issue by key. Read-only."""
        issue = _ISSUES.get(issue_key.upper())
        if issue is None:
            return {"found": False, "issue_key": issue_key}
        return {"found": True, **issue}

    @server.tool(annotations=_READ_ONLY)
    def jira_search(query: str, limit: int = 10) -> dict[str, Any]:
        """Search issue summaries for a substring. Read-only."""
        needle = query.strip().lower()
        hits = [i for i in _ISSUES.values() if needle in i["summary"].lower()] if needle else []
        return {"query": query, "count": len(hits[:limit]), "issues": hits[:limit]}

    @server.tool(annotations=_READ_ONLY)
    def jira_project_reader(project_key: str) -> dict[str, Any]:
        """Read project metadata by key. Read-only."""
        project = _PROJECTS.get(project_key.upper())
        if project is None:
            return {"found": False, "project_key": project_key}
        return {"found": True, **project}

    # Deliberately declares no readOnlyHint. Our mapping is deny-by-default, so
    # this arrives write-capable and must be catalogued-but-unbindable. It is
    # here to prove the advisory-only invariant holds for tools we did not
    # author and cannot vouch for.
    @server.tool()
    def jira_issue_commenter(issue_key: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue. Not declared read-only."""
        return {"accepted": False, "reason": "reference server is read-only", "issue_key": issue_key}

    # Non-conformant on purpose. The body never runs — a conformant client
    # rejects the definition during discovery and never surfaces the tool.
    @server.tool(meta=_INVALID_HEADER_META)
    def bad_header_reader(anything: str) -> dict[str, Any]:
        """Deliberately malformed definition. A conformant client must drop this."""
        return {"unreachable": True, "echo": anything}

    return server


def main() -> None:
    """Run the reference server over Streamable HTTP.

    Streamable HTTP rather than stdio on purpose: it gives the healthcheck a
    real socket to probe, and it is the transport a remote connector would
    actually use, so the client exercises its production path.
    """
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Local reference MCP server (synthetic data).")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = build_server()
    print(f"[reference-mcp] Streamable HTTP on http://{args.host}:{args.port}/mcp", flush=True)
    # `stateless_http=True` matches spec 2026-07-28, whose core is stateless:
    # protocol-level sessions were removed, so holding per-session state here
    # would model a version of MCP that no longer exists.
    asyncio.run(
        server.run_streamable_http_async(host=args.host, port=args.port, stateless_http=True)
    )


if __name__ == "__main__":
    main()
