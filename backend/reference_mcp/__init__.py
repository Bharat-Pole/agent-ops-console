"""Local reference MCP server for the POC.

This package is the **counterparty**, not the deliverable. It exists so the real
MCP client in `app/services/mcp_client.py` can be built and verified against a
genuine protocol exchange without a tenant, credentials, or any Brightspeed
dependency (`ROADMAP.md` §4.0, Phase 5A).

It must never be seeded into `connectors` as though it were a Brightspeed
system. It is registered explicitly, by a human or a suite, with an obviously
local endpoint.

Deliberately empty of imports: `python -m reference_mcp.server` warns about
double-importing the submodule if this module pulls it in first. Import from
`reference_mcp.server` directly.
"""
