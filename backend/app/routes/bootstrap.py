import asyncio

from fastapi import APIRouter

from app.repositories import agents_repo, approvals_repo, audit_repo, eval_packs_repo, knowledge_sources_repo

router = APIRouter()


@router.get("/v1/bootstrap")
async def get_bootstrap() -> dict:
    agents, approvals, audit_log, eval_packs, sources = await asyncio.gather(
        agents_repo.get_all(),
        approvals_repo.get_all(),
        audit_repo.get_all(),
        eval_packs_repo.get_all(),
        knowledge_sources_repo.get_all(),
    )
    return {
        "agents": agents,
        "approvals": approvals,
        "auditLog": audit_log,
        "evalPacks": eval_packs,
        "knowledgeSources": sources,
    }
