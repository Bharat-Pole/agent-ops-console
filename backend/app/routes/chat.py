import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.repositories import agents_repo, audit_repo
from app.services.claude_service import chat_with_agent, is_claude_configured
from app.services.retrieval import retrieve_for_agent

router = APIRouter()

# Same detection rules as the client's classify() (src/kernel/playground.ts),
# duplicated here because the server never trusts the client's own
# classification for the write/refusal decision — the backend is the real
# trust boundary now, same principle as the bind_tool guard.
WRITE_VERBS = [
    "send", "approve", "deploy", "update", "create", "delete", "close", "assign",
    "notify", "post", "execute", "modify", "file", "submit", "remove", "email",
]
ADVISORY_FRAMES = ["draft", "summarize", "recommend", "what", "how", "explain", "show", "list"]

REFUSAL_TEXT = (
    "I'm advisory-only. I can draft this for you, but I can't send, update, delete, or otherwise act. "
    "Would you like a draft you can review and act on yourself?"
)


def _looks_like_write_intent(message: str) -> bool:
    t = message.lower()
    has_write = any(re.search(rf"\b{re.escape(v)}\b", t) for v in WRITE_VERBS)
    advisory = any(f in t for f in ADVISORY_FRAMES)
    return has_write and not advisory


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

    # Independent re-check — overrides whatever the client classified this as.
    if _looks_like_write_intent(message):
        return JSONResponse(
            content={"kind": "refusal", "text": REFUSAL_TEXT, "citations": [], "retrieval": [], "tokenCount": 0, "model": None}
        )

    if not is_claude_configured():
        return JSONResponse(status_code=503, content={"message": "ANTHROPIC_API_KEY not configured."})

    try:
        data_cfg = agent["config"]["data"]
        rag_enabled = data_cfg["rag_enabled"]["value"] and len(data_cfg["knowledge_source_refs"]["value"]) > 0
        top_k = data_cfg["top_k"]["value"] if data_cfg["top_k"]["value"] is not None else 5
        score_threshold = data_cfg["score_threshold"]["value"] if data_cfg["score_threshold"]["value"] is not None else 0.35

        retrieval = await retrieve_for_agent(agent, message, top_k, score_threshold) if rag_enabled else []
        passed = [r for r in retrieval if r["passed"]][:3]
        citations = [f"[source: kb://{r['source_id']} · {r['doc_id']}]" for r in passed]
        kind = "grounded_answer" if passed else "general_answer"

        result = await chat_with_agent(
            agent,
            message,
            history if isinstance(history, list) else [],
            [{"doc_id": r["doc_id"], "source_id": r["source_id"], "text": r["text"]} for r in passed],
            resolved_system_prompt_body if isinstance(resolved_system_prompt_body, str) else None,
            resolved_citation_rules_body if isinstance(resolved_citation_rules_body, str) else None,
        )

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
        print("[chat]", err)
        return JSONResponse(status_code=502, content={"message": str(err) or "Chat failed."})
