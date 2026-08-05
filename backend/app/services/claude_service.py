import json
from typing import Any, Optional

from anthropic import AsyncAnthropic

from app.env import env
from app.repositories import knowledge_sources_repo

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


def _parse_source_id(ref: str) -> str:
    return ref.replace("kb://", "", 1).split("@")[0]


# Builds the ONLY tool defs this call will ever offer the model — both generated
# entirely server-side from the agent's own bound refs, never from client input.
# This is what keeps the advisory-only invariant intact under tool-use: the model
# can only ever be given a read-only search/query capability, restricted by a
# JSON-schema enum to exactly this agent's bound source_ids.
async def _build_tools_for_agent(agent: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    refs = agent["config"]["data"].get("knowledge_source_refs", {}).get("value") or []
    source_ids = [_parse_source_id(r) for r in refs]
    if not source_ids:
        return [], {}

    sources = [await knowledge_sources_repo.get_by_id(sid) for sid in source_ids]
    vector_sources = [s for s in sources if s and s["lifecycle"] != "retired" and s["ingestion_mode"] != "sql"]
    sql_sources = [s for s in sources if s and s["lifecycle"] != "retired" and s["ingestion_mode"] == "sql"]

    source_kind_by_id: dict[str, str] = {}
    for s in vector_sources:
        source_kind_by_id[s["id"]] = "vector"
    for s in sql_sources:
        source_kind_by_id[s["id"]] = "sql"

    tools: list[dict[str, Any]] = []
    if vector_sources:
        listing = ", ".join(f"{s['name']} ({s['id']})" for s in vector_sources)
        tools.append({
            "name": "search_knowledge",
            "description": (
                "Search the agent's bound knowledge base for relevant passages from "
                f"documents. Available sources: {listing}. Call once per source that "
                "might be relevant; call again with a different query if the first "
                "result doesn't answer the question."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "source_id": {"type": "string", "enum": [s["id"] for s in vector_sources]},
                },
                "required": ["query", "source_id"],
            },
        })
    if sql_sources:
        listing = ", ".join(f"{s['name']} ({s['id']})" for s in sql_sources)
        tools.append({
            "name": "query_structured_data",
            "description": (
                "Ask a natural-language question against a bound structured/tabular "
                f"data source (read-only). Available sources: {listing}. Use this for "
                "counts, aggregates, filters, or lookups over tabular data — not for "
                "prose documents."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to answer from this data source."},
                    "source_id": {"type": "string", "enum": [s["id"] for s in sql_sources]},
                },
                "required": ["question", "source_id"],
            },
        })

    return tools, source_kind_by_id


async def _execute_tool(
    name: str, input_: dict[str, Any], source_kind_by_id: dict[str, str], top_k: int, score_threshold: float
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Returns (tool_result_content, retrieval_entries, citations). Re-validates
    source_id server-side against the agent's actual bound set — the model's
    JSON-schema enum is a hint to the model, not a trust boundary."""
    source_id = input_.get("source_id")
    kind = source_kind_by_id.get(source_id)
    if kind is None:
        return f"Error: source_id '{source_id}' is not bound to this agent.", [], []

    if name == "search_knowledge" and kind == "vector":
        from app.services import retrieval
        try:
            results = await retrieval.retrieve_for_sources(
                [source_id], input_.get("query", ""), top_k, score_threshold
            )
        except ValueError as e:
            return f"Error: {e}", [], []
        citations = [f"[source: kb://{r['source_id']} · {r['doc_id']}]" for r in results if r["passed"]]
        return json.dumps({"source_id": source_id, "results": results}), results, citations

    if name == "query_structured_data" and kind == "sql":
        from app.services import sql_executor
        try:
            result = await sql_executor.ask_question(source_id, input_.get("question", ""))
        except (RuntimeError, ValueError) as e:
            return f"Error: {e}", [], []
        return json.dumps(result), [], [f"[source: kb://{source_id} · sql]"]

    return f"Error: '{name}' is not applicable to source_id '{source_id}'.", [], []


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
        tools, source_kind_by_id = await _build_tools_for_agent(agent)

    messages: list[dict[str, Any]] = [
        {"role": "assistant" if h["role"] == "agent" else "user", "content": h["text"]} for h in history
    ]
    messages.append({"role": "user", "content": message})

    system_prompt = _build_system_prompt(agent, sys_body, cite_body)

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
    all_retrieval: list[dict[str, Any]] = []
    all_citations: list[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await _get_client().messages.create(**_base_params())
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        if response.stop_reason != "tool_use":
            text_block = next((b for b in response.content if b.type == "text"), None)
            return {
                "text": text_block.text if text_block else "",
                "tokenCount": total_tokens,
                "model": model,
                "citations": all_citations,
                "retrieval": all_retrieval,
            }

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            content, retrieval_entries, citations = await _execute_tool(
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
    text_block = next((b for b in response.content if b.type == "text"), None)
    return {
        "text": text_block.text if text_block else "",
        "tokenCount": total_tokens,
        "model": model,
        "citations": all_citations,
        "retrieval": all_retrieval,
    }
