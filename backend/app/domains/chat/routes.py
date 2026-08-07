import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.agents import agents_repo
from app.domains.audit import audit_repo
from app.domains.monitoring import service as monitoring
from app.domains.chat.llm_gateway import chat_with_agent, is_llm_configured
from app.domains.chat.safety import REFUSAL_TEXT, looks_like_write_intent

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@router.post("/v1/agents/{agent_id}/chat")
async def chat(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    agent = await agents_repo.get_by_id(agent_id)
    if agent is None:
        return JSONResponse(status_code=404, content={"message": "Agent not found."})

    message = body.get("message")
    history = body.get("history")
    resolved_system_prompt_body = body.get("resolvedSystemPromptBody")
    resolved_citation_rules_body = body.get("resolvedCitationRulesBody")

    if not isinstance(message, str) or not message.strip():
        return JSONResponse(status_code=400, content={"message": "message is required."})

    # Real lifecycle gate — a suspended/retired agent must not still answer as
    # if nothing happened. Was previously just a status label with no
    # enforcement anywhere in the runtime path.
    lifecycle_status = agent["config"]["lifecycle"]["lifecycle_status"]["value"]
    if lifecycle_status in ("suspended", "retired"):
        text = (
            "This agent is currently suspended and cannot respond. Contact a Governance Officer to reactivate it."
            if lifecycle_status == "suspended"
            else "This agent has been retired and is no longer in service."
        )
        return JSONResponse(
            content={"kind": "refusal", "text": text, "citations": [], "retrieval": [], "tokenCount": 0, "model": None}
        )

    # Independent re-check — overrides whatever the client classified this as.
    if looks_like_write_intent(message):
        return JSONResponse(
            content={"kind": "refusal", "text": REFUSAL_TEXT, "citations": [], "retrieval": [], "tokenCount": 0, "model": None}
        )

    if not is_llm_configured():
        return JSONResponse(status_code=503, content={"message": "Neither ANTHROPIC_API_KEY nor GROQ_API_KEY is configured."})

    t0 = time.monotonic()
    try:
        # Retrieval is no longer precomputed here — chat_with_agent() offers the
        # model a real search_knowledge/query_structured_data tool (built from the
        # agent's bound knowledge_source_refs) and decides for itself whether to
        # call it, matching how OpenAI/Azure/Bedrock/Vertex agent platforms expose
        # knowledge access. `retrieval`/`citations` below are now OUTPUTS of that call.
        result = await chat_with_agent(
            agent,
            message,
            history if isinstance(history, list) else [],
            resolved_system_prompt_body if isinstance(resolved_system_prompt_body, str) else None,
            resolved_citation_rules_body if isinstance(resolved_citation_rules_body, str) else None,
        )
        await monitoring.record_event(
            agent_id, "chat", "ok", (time.monotonic() - t0) * 1000,
            result.get("tokensIn", 0), result.get("tokensOut", 0), result["model"],
        )
        retrieval = result["retrieval"]
        citations = result["citations"]
        kind = "grounded_answer" if citations else "general_answer"

        audit_event = await audit_repo.insert(
            {
                "id": f"aud-{uuid.uuid4()}",
                "at": _now_iso(),
                "actor_persona": "Team Lead / Consumer",
                "action": "chat_message",
                "entity_type": "agent",
                "entity_id": agent_id,
                "detail": f"Playground chat via {result['model']} ({result['tokenCount']} tokens).",
            }
        )

        return JSONResponse(
            content={
                "kind": kind,
                "text": result["text"],
                "citations": citations,
                "retrieval": retrieval,
                "tokenCount": result["tokenCount"],
                "model": result["model"],
                "auditEvent": audit_event,
            }
        )
    except Exception as err:
        await monitoring.record_event(agent_id, "chat", "error", (time.monotonic() - t0) * 1000, error_msg=str(err))
        print("[chat]", err)
        return JSONResponse(status_code=502, content={"message": str(err) or "Chat failed."})
