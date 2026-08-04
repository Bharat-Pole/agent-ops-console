from typing import Any, Optional

from anthropic import AsyncAnthropic

from app.env import env

MODEL_BY_TIER = {
    "minimal": env.ANTHROPIC_MODEL_MINIMAL,
    "standardized": env.ANTHROPIC_MODEL_STANDARDIZED,
    "advanced": env.ANTHROPIC_MODEL_ADVANCED,
}

_client: Optional[AsyncAnthropic] = None


def is_claude_configured() -> bool:
    return bool(env.ANTHROPIC_API_KEY)


def _get_client() -> AsyncAnthropic:
    global _client
    if not env.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not configured.")
    if _client is None:
        _client = AsyncAnthropic(api_key=env.ANTHROPIC_API_KEY)
    return _client


# System prompt assembled from the agent's own config groups — persona,
# system prompt body (resolved from its prompts:// ref client-side), task
# instructions, safety instructions, citation rules, and a hard advisory-only
# clause. `tools` is never set on the request below, so write-capable
# exposure to the model is impossible by construction, not by instruction.
def _build_system_prompt(agent: dict[str, Any], sys_body: Optional[str], cite_body: Optional[str]) -> str:
    cfg = agent["config"]
    pieces = [
        f"You are {cfg['prompt']['persona_role']['value']}.",
        sys_body,
        f"Task instructions: {cfg['prompt']['task_prompt']['value']}" if cfg["prompt"]["task_prompt"]["value"] else None,
        f"Safety instructions: {cfg['prompt']['safety_instructions']['value']}",
        f"Citation rules: {cite_body}" if cite_body else None,
        "You are strictly advisory-only: you cannot send, approve, deploy, update, delete, execute, or otherwise take write action in any system. If asked to, decline and offer a draft for human review instead.",
        f"Response format: {cfg['prompt']['response_format_contract']['value']}"
        if cfg["prompt"]["response_format_contract"]["value"]
        else None,
    ]
    return "\n\n".join(p for p in pieces if p)


async def chat_with_agent(
    agent: dict[str, Any],
    message: str,
    history: list[dict[str, Any]],
    retrieval_snippets: list[dict[str, Any]],
    sys_body: Optional[str],
    cite_body: Optional[str],
) -> dict[str, Any]:
    model = MODEL_BY_TIER[agent["capability_tier"]]
    max_output = agent["config"]["model"]["max_output_tokens"]["value"]
    max_tokens = min(max(max_output if max_output is not None else 1024, 256), 4096)

    if retrieval_snippets:
        context = "\n".join(f"[{s['source_id']} · {s['doc_id']}]: {s['text']}" for s in retrieval_snippets)
        user_content = f"{message}\n\n---\nRetrieved context (cite using [source: kb://<source_id> · <doc_id>]):\n{context}"
    else:
        user_content = message

    messages = [
        {"role": "assistant" if h["role"] == "agent" else "user", "content": h["text"]} for h in history
    ]
    messages.append({"role": "user", "content": user_content})

    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
        "system": _build_system_prompt(agent, sys_body, cite_body),
        "messages": messages,
        # No `tools` param — write-capable exposure to the model is structurally impossible.
    }

    # Opus 5 / Sonnet 5 reject non-default temperature/top_p/top_k. Only Haiku
    # 4.5 accepts the agent's configured temperature.
    if model.startswith("claude-haiku-4-5"):
        temp = agent["config"]["model"]["temperature"]["value"]
        params["temperature"] = min(max(temp if temp is not None else 0.5, 0), 1)

    response = await _get_client().messages.create(**params)
    text_block = next((b for b in response.content if b.type == "text"), None)
    return {
        "text": text_block.text if text_block else "",
        "tokenCount": response.usage.input_tokens + response.usage.output_tokens,
        "model": model,
    }
