import uuid
from datetime import datetime, timezone
from typing import Any

from app.domains.a2a import a2a_repo
from app.domains.agents import agents_repo
from app.domains.audit import audit_repo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _build_card(agent: dict[str, Any]) -> dict[str, Any]:
    """Every field here comes from the agent's own persisted config — no new
    fabricated data, unlike the old client-side hardcoded schema stub that was
    identical for every agent regardless of its real capabilities."""
    cfg = agent["config"]
    identity = cfg["identity"]
    data_cfg = cfg["data"]
    tooling = cfg["tooling"]
    orch = cfg["orchestration"]

    skills = [f"{identity['use_case_category']['value']}-qa"]
    if data_cfg["rag_enabled"]["value"]:
        skills += ["grounded-answer", "summarization"]
    skills += [s["name"] for s in orch["sub_agents"]["value"]]

    input_schema: dict[str, Any] = {"query": "string"}
    if data_cfg["knowledge_source_refs"]["value"]:
        input_schema["context"] = "string?"

    output_schema: dict[str, Any] = {"answer": "string"}
    if data_cfg["rag_enabled"]["value"]:
        output_schema["citations"] = "string[]"
    if tooling["bound_tools"]["value"]:
        output_schema["tool_calls"] = "object[]"

    return {
        "agent_id": agents_repo.agent_id(agent),
        "name": identity["agent_name"]["value"],
        "description": identity["description"]["value"] or identity["objective"]["value"],
        "skills": skills,
        "discovery_only": not orch["artifact_exchange"]["value"],
        "message_task_format": orch["message_task_format"]["value"],
        "capability_tier": agent["capability_tier"],
        "model": cfg["model"]["model_primary"]["value"],
        "input_schema": input_schema,
        "output_schema": output_schema,
    }


async def sync_cards() -> list[dict[str, Any]]:
    """Re-derives every A2A-enabled agent's card fresh from its current config
    on every call, so the directory can never go stale — and removes cards for
    agents that turned a2a_enabled off, so the directory never shows a dead
    entry. A manually-set `endpoint` override survives a sync; every other
    field always reflects the agent's live config."""
    agents = await agents_repo.get_all()
    enabled = [a for a in agents if a["config"]["orchestration"]["a2a_enabled"]["value"]]
    enabled_ids = {agents_repo.agent_id(a) for a in enabled}

    existing_ids = await a2a_repo.get_all_agent_ids()
    for stale_id in existing_ids - enabled_ids:
        await a2a_repo.delete(stale_id)

    now = _now_iso()
    result: list[dict[str, Any]] = []
    for agent in enabled:
        built = _build_card(agent)
        prior = await a2a_repo.get_by_agent(built["agent_id"])
        if prior and prior["endpoint_overridden"]:
            built["endpoint"] = prior["endpoint"]
            built["endpoint_overridden"] = True
        else:
            built["endpoint"] = f"a2a://{built['agent_id']}"
            built["endpoint_overridden"] = False
        built["updated_at"] = now
        result.append(await a2a_repo.upsert(built))
    return result


async def update_endpoint(agent_id: str, endpoint: str, actor_persona: str = "Platform Admin") -> dict[str, Any]:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        raise ValueError("endpoint is required.")
    card = await a2a_repo.get_by_agent(agent_id)
    if card is None:
        raise ValueError("No A2A card for this agent — the agent may not be A2A-enabled.")
    updated = await a2a_repo.set_endpoint(agent_id, endpoint, _now_iso())
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "update_a2a_endpoint",
            "entity_type": "agent",
            "entity_id": agent_id,
            "detail": f"A2A card endpoint set to {endpoint}.",
        }
    )
    return {"card": updated, "auditEvent": audit_event}
