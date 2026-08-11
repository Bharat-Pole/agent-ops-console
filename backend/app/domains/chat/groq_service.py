import json
from typing import Any, Optional

from openai import AsyncOpenAI

from app.env import env
from app.domains.chat.tool_execution import (
    build_system_prompt,
    execute_tool,
    get_bound_sources,
    get_citation_format,
    openai_tool_defs,
)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_TOOL_ITERATIONS = 4

_client: Optional[AsyncOpenAI] = None


def is_groq_configured() -> bool:
    return bool(env.GROQ_API_KEY)


def _get_client() -> AsyncOpenAI:
    global _client
    if not env.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured.")
    if _client is None:
        _client = AsyncOpenAI(api_key=env.GROQ_API_KEY, base_url=GROQ_BASE_URL)
    return _client


async def generate_text(prompt: str, max_tokens: int = 512, system: Optional[str] = None) -> str:
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = await _get_client().chat.completions.create(
        model=env.GROQ_MODEL,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content or ""


# Same external contract as claude_service.chat_with_agent (text/tokenCount/
# tokensIn/tokensOut/model/citations/retrieval) and the same real RAG tool
# catalog (tool_execution.py) — this is the free-tier fallback used when
# Anthropic is unconfigured or fails, not a lesser/simulated substitute.
async def chat_with_agent(
    agent: dict[str, Any],
    message: str,
    history: list[dict[str, Any]],
    sys_body: Optional[str],
    cite_body: Optional[str],
) -> dict[str, Any]:
    model = env.GROQ_MODEL
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
    rerank_enabled = data_cfg.get("rerank_enabled", {}).get("value")
    if rerank_enabled is None:
        rerank_enabled = True
    agent_id_str = agent["config"]["identity"]["agent_id"]["value"]
    citation_format = await get_citation_format(agent)

    tools: list[dict[str, Any]] = []
    source_kind_by_id: dict[str, str] = {}
    if rag_enabled:
        vector_sources, sql_sources, source_kind_by_id = await get_bound_sources(agent)
        tools = openai_tool_defs(vector_sources, sql_sources)

    system_prompt = build_system_prompt(agent, sys_body, cite_body)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": "assistant" if h["role"] == "agent" else "user", "content": h["text"]})
    messages.append({"role": "user", "content": message})

    def _base_params() -> dict[str, Any]:
        params: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if tools:
            params["tools"] = tools
        return params

    total_tokens = 0
    total_tokens_in = 0
    total_tokens_out = 0
    all_retrieval: list[dict[str, Any]] = []
    all_citations: list[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await _get_client().chat.completions.create(**_base_params())
        usage = response.usage
        if usage:
            total_tokens += usage.total_tokens
            total_tokens_in += usage.prompt_tokens
            total_tokens_out += usage.completion_tokens
        choice_message = response.choices[0].message

        if not choice_message.tool_calls:
            return {
                "text": choice_message.content or "",
                "tokenCount": total_tokens,
                "tokensIn": total_tokens_in,
                "tokensOut": total_tokens_out,
                "model": model,
                "citations": all_citations,
                "retrieval": all_retrieval,
            }

        messages.append(choice_message.model_dump(exclude_unset=True))
        for tc in choice_message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            content, retrieval_entries, citations = await execute_tool(
                tc.function.name, args, source_kind_by_id, top_k, score_threshold,
                rerank_enabled=rerank_enabled, agent_id=agent_id_str, citation_format=citation_format,
            )
            all_retrieval.extend(retrieval_entries)
            all_citations.extend(citations)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    # Iteration cap hit — force a final tools-off answer rather than error out.
    final_params = _base_params()
    final_params.pop("tools", None)
    response = await _get_client().chat.completions.create(**final_params)
    usage = response.usage
    if usage:
        total_tokens += usage.total_tokens
        total_tokens_in += usage.prompt_tokens
        total_tokens_out += usage.completion_tokens
    return {
        "text": response.choices[0].message.content or "",
        "tokenCount": total_tokens,
        "tokensIn": total_tokens_in,
        "tokensOut": total_tokens_out,
        "model": model,
        "citations": all_citations,
        "retrieval": all_retrieval,
    }
