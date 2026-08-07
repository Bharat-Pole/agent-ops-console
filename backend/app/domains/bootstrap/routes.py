import asyncio

from fastapi import APIRouter

from app.domains.a2a import service as a2a
from app.domains.admin import feature_flags_repo
from app.domains.agents import agents_repo
from app.domains.approvals import approvals_repo
from app.domains.audit import audit_repo
from app.domains.deployment import service as deployment
from app.domains.evaluations import eval_packs_repo
from app.domains.governance import governance_repo
from app.domains.knowledge import knowledge_sources_repo
from app.domains.models import models_repo
from app.domains.monitoring import service as monitoring
from app.domains.prompts import prompts_repo
from app.domains.tools import mcp_connectors_repo, tools_repo

router = APIRouter()


@router.get("/v1/bootstrap")
async def get_bootstrap() -> dict:
    await governance_repo.expire_due_exceptions()
    (
        agents, approvals, audit_log, eval_packs, prompts, knowledge_sources, tools, connectors, models,
        policy_rules, path_definitions, exceptions, telemetry, feature_flags, a2a_cards, agent_environments,
    ) = await asyncio.gather(
        agents_repo.get_all(),
        approvals_repo.get_all(),
        audit_repo.get_all(),
        eval_packs_repo.get_all(),
        prompts_repo.get_all(),
        knowledge_sources_repo.get_all(),
        tools_repo.get_all(),
        mcp_connectors_repo.get_all(),
        models_repo.get_all(),
        governance_repo.get_all_policy_rules(),
        governance_repo.get_all_path_definitions(),
        governance_repo.get_all_exceptions(),
        monitoring.get_all_telemetry(),
        feature_flags_repo.get_all(),
        a2a.sync_cards(),
        deployment.get_all_environments(),
    )
    return {
        "agents": agents,
        "approvals": approvals,
        "auditLog": audit_log,
        "evalPacks": eval_packs,
        "prompts": prompts,
        "knowledgeSources": knowledge_sources,
        "tools": tools,
        "connectors": connectors,
        "models": models,
        "policyRules": policy_rules,
        "pathDefinitions": path_definitions,
        "governanceExceptions": exceptions,
        "telemetry": telemetry,
        "featureFlags": feature_flags,
        "a2aCards": a2a_cards,
        "agentEnvironments": agent_environments,
    }
