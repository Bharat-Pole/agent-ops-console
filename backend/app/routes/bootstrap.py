import asyncio

from fastapi import APIRouter

from app.repositories import (
    agents_repo,
    approvals_repo,
    audit_repo,
    connectors_repo,
    eval_packs_repo,
    tools_repo,
)

router = APIRouter()


# The connector backlog is deliberately NOT here. It is served by
# `GET /v1/connector-backlog` alongside a **server-derived summary** (which
# system is recommended, which are blocked for lack of a server). Putting the
# rows in the store would force the client to re-derive that summary — the same
# mistake as re-deriving `system_accessed` client-side. One tab consumes it;
# it fetches it, like the Tool Calls tab does.
@router.get("/v1/bootstrap")
async def get_bootstrap() -> dict:
    agents, approvals, audit_log, eval_packs, tools, connectors = await asyncio.gather(
        agents_repo.get_all(),
        approvals_repo.get_all(),
        audit_repo.get_all(),
        eval_packs_repo.get_all(),
        tools_repo.get_all(),
        connectors_repo.get_all(),
    )
    return {
        "agents": agents,
        "approvals": approvals,
        "auditLog": audit_log,
        "evalPacks": eval_packs,
        "tools": tools,
        "connectors": connectors,
    }
