from typing import Any, Optional

from anthropic import AsyncAnthropic

from app.env import env
from app.domains.chat.tool_execution import (
    anthropic_tool_defs,
    build_system_prompt,
    execute_tool,
    get_bound_sources,
)

MODEL_BY_TIER = {
    "minimal": env.ANTHROPIC_MODEL_MINIMAL,
    "standardized": env.ANTHROPIC_MODEL_STANDARDIZED,
    "advanced": env.ANTHROPIC_MODEL_ADVANCED,
}

MAX_TOOL_ITERATIONS = 4

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


async def chat_with_agent(
    agent: dict[str, Any],
    message: str,
    history: list[dict[str, Any]],
    sys_body: Optional[str],
    cite_body: Optional[str],
) -> dict[str, Any]:
    model = MODEL_BY_TIER[agent["capability_tier"]]
    max_output = agent["config"]["model"]["max_output_tokens"]["value"]
    max_tokens = min(max(max_output if max_output is not None else 1024, 256), 4096)

    data_cfg = agent["config"]["data"]
    rag_enabled = bool(data_cfg.get("rag_enabled", {}).get("value")) and bool(
        data_cfg.get("knowledge_source_refs", {}).get("value")
    )
    top_k = data_cfg.get("top_k", {}).get("value") or 5
    score_threshold = data_cfg.get("score_threshold", {}).get("value")
    if score_threshold is None:
        score_threshold = 0.35

    tools: list[dict[str, Any]] = []
    source_kind_by_id: dict[str, str] = {}
    if rag_enabled:
        vector_sources, sql_sources, source_kind_by_id = await get_bound_sources(agent)
        tools = anthropic_tool_defs(vector_sources, sql_sources)

    messages: list[dict[str, Any]] = [
        {"role": "assistant" if h["role"] == "agent" else "user", "content": h["text"]} for h in history
    ]
    messages.append({"role": "user", "content": message})

    system_prompt = build_system_prompt(agent, sys_body, cite_body)

    def _base_params() -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }
        # Adaptive thinking is Anthropic's recommended mode for agentic/tool-use
        # workflows (interleaved thinking between tool calls). Kept disabled when
        # no tools are offered, matching prior behavior for non-RAG agents exactly.
        params["thinking"] = {"type": "adaptive"} if tools else {"type": "disabled"}
        if tools:
            params["tools"] = tools
        # Opus 5 / Sonnet 5 reject non-default temperature/top_p/top_k. Only Haiku
        # 4.5 accepts the agent's configured temperature.
        if model.startswith("claude-haiku-4-5"):
            temp = agent["config"]["model"]["temperature"]["value"]
            params["temperature"] = min(max(temp if temp is not None else 0.5, 0), 1)
        return params

    total_tokens = 0
    total_tokens_in = 0
    total_tokens_out = 0
    all_retrieval: list[dict[str, Any]] = []
    all_citations: list[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await _get_client().messages.create(**_base_params())
        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        total_tokens_in += response.usage.input_tokens
        total_tokens_out += response.usage.output_tokens

        if response.stop_reason != "tool_use":
            text_block = next((b for b in response.content if b.type == "text"), None)
            return {
                "text": text_block.text if text_block else "",
                "tokenCount": total_tokens,
                "tokensIn": total_tokens_in,
                "tokensOut": total_tokens_out,
                "model": model,
                "citations": all_citations,
                "retrieval": all_retrieval,
            }

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            content, retrieval_entries, citations = await execute_tool(
                block.name, block.input, source_kind_by_id, top_k, score_threshold
            )
            all_retrieval.extend(retrieval_entries)
            all_citations.extend(citations)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
        messages.append({"role": "user", "content": tool_results})

    # Iteration cap hit — force a final tools-off answer rather than error out.
    final_params = _base_params()
    final_params.pop("tools", None)
    final_params["thinking"] = {"type": "disabled"}
    response = await _get_client().messages.create(**final_params)
    total_tokens += response.usage.input_tokens + response.usage.output_tokens
    total_tokens_in += response.usage.input_tokens
    total_tokens_out += response.usage.output_tokens
    text_block = next((b for b in response.content if b.type == "text"), None)
    return {
        "text": text_block.text if text_block else "",
        "tokenCount": total_tokens,
        "tokensIn": total_tokens_in,
        "tokensOut": total_tokens_out,
        "model": model,
        "citations": all_citations,
        "retrieval": all_retrieval,
    }


# Small standalone completion, reused by non-chat features (e.g. Prompt
# Repository "Generate with AI") that just need text back, not the full
# agent-chat message shaping above.
async def generate_text(system: str, user: str, max_tokens: int = 800) -> str:
    response = await _get_client().messages.create(
        model=env.ANTHROPIC_MODEL_STANDARDIZED,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text_block = next((b for b in response.content if b.type == "text"), None)
    return text_block.text if text_block else ""
