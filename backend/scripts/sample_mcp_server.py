"""A tiny, real MCP server for exercising the connector path end to end.

This exists so MCP can be tested without depending on anyone's private server.
It serves two READ-ONLY tools over streamable HTTP, which is the platform's
default transport.

    python backend/scripts/sample_mcp_server.py           # -> http://127.0.0.1:9000/mcp

Then in the console: MCP Connectors -> Register, endpoint http://127.0.0.1:9000/mcp,
transport streamable_http. Discovery creates DRAFT tools; they still need
approval before an agent may bind them, which is the point.

Note the platform's SSRF guard denies private address ranges by default. For
local testing add the host to `tryout_private_host_allowlist` in settings —
that allowlist exists precisely so loopback testing does not require weakening
the guard itself.

Works with both mcp SDK majors: v2 exposes MCPServer, v1 exposed FastMCP.
"""
from __future__ import annotations

import sys

HOST = "127.0.0.1"
PORT = 9000

CATALOG = {
    "onboarding": "New joiners get laptop, badge and system access on day one. "
                  "The buddy programme runs for the first four weeks.",
    "expenses": "Expenses under 100 are auto-approved. Anything above needs "
                "manager sign-off and a receipt within 30 days.",
    "leave": "25 days annual leave plus public holidays. Carry-over is capped "
             "at 5 days and must be used by the end of March.",
}


def build_server():
    """Return (server, kind) for whichever SDK major is installed."""
    try:                                    # SDK v2
        from mcp.server import MCPServer
        server = MCPServer(name="sample-policy-server", version="1.0.0")
        kind = "v2"
    except ImportError:                     # SDK v1
        from mcp.server.fastmcp import FastMCP
        server = FastMCP(name="sample-policy-server")
        kind = "v1"

    @server.tool()
    def lookup_policy(topic: str) -> str:
        """Look up a company policy by topic. Valid topics: onboarding, expenses, leave."""
        key = (topic or "").strip().lower()
        if key not in CATALOG:
            # An honest miss, not an invented answer — the platform's guardrails
            # assume tools do not fabricate.
            return f"No policy found for {topic!r}. Known topics: {', '.join(sorted(CATALOG))}."
        return CATALOG[key]

    @server.tool()
    def list_policies() -> str:
        """List every policy topic this server can answer questions about."""
        return ", ".join(sorted(CATALOG))

    return server, kind


def main() -> int:
    server, kind = build_server()
    print(f"sample MCP server ({kind} SDK) -> http://{HOST}:{PORT}/mcp")
    print("tools: lookup_policy, list_policies   (both read-only)")
    if kind == "v2":
        import uvicorn
        uvicorn.run(server.streamable_http_app(), host=HOST, port=PORT, log_level="warning")
    else:
        server.settings.host, server.settings.port = HOST, PORT
        server.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    sys.exit(main())
