"""Provider-agnostic pieces of agent chat: system-prompt assembly, the RAG
tool catalog derived from an agent's real bound sources, and tool execution.
Shared by every LLM provider's chat loop (claude_service.py, groq_service.py)
so the RAG capability offered to the model — and the advisory-only guarantee
that no write-capable tool can ever be exposed — is identical regardless of
which model answers the question."""

import json
from typing import Any, Optional

from app.domains.knowledge import knowledge_sources_repo


def build_system_prompt(agent: dict[str, Any], sys_body: Optional[str], cite_body: Optional[str]) -> str:
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


def parse_source_id(ref: str) -> str:
    return ref.replace("kb://", "", 1).split("@")[0]


async def get_citation_format(agent: dict[str, Any]) -> Optional[str]:
    """Real, mechanically-applied citation format from the agent's own bound
    citation_rules prompt (Blueprint 3.3 "configure citation rules") — looked
    up server-side from the backend's own prompts table, independent of
    whatever resolved body text the client forwarded. None = use the
    platform default bracket format."""
    ref = agent["config"]["prompt"].get("citation_rules", {}).get("value")
    if not ref or not ref.startswith("prompts://"):
        return None
    prompt_id = ref.replace("prompts://", "", 1).split("@")[0]
    from app.domains.prompts import prompts_repo
    prompt = await prompts_repo.get_by_id(prompt_id)
    return prompt.get("citation_format") if prompt else None


def render_citation(citation_format: Optional[str], source_name: str, source_id: str, doc_id: str, doc_title: str) -> str:
    default = f"[source: kb://{source_id} · {doc_id}]"
    if not citation_format:
        return default
    try:
        return citation_format.format(
            source_name=source_name, source_id=source_id, doc_id=doc_id, doc_title=doc_title,
        )
    except (KeyError, IndexError, ValueError):
        # Malformed template (typo'd placeholder, stray brace) — fail safe to
        # the platform default rather than break every citation in the chat.
        return default


def _estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except ImportError:
        return max(1, len(text) // 4)  # rough fallback, matches OpenAI's ~4 chars/token rule of thumb


# Builds the ONLY tool catalog this call will ever offer the model — generated
# entirely server-side from the agent's own bound refs, never from client input.
# This is what keeps the advisory-only invariant intact under tool-use: the
# model can only ever be given a read-only search/query capability, restricted
# by a JSON-schema enum to exactly this agent's bound source_ids.
async def get_bound_sources(agent: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    refs = agent["config"]["data"].get("knowledge_source_refs", {}).get("value") or []
    source_ids = [parse_source_id(r) for r in refs]
    if not source_ids:
        return [], [], {}

    sources = [await knowledge_sources_repo.get_by_id(sid) for sid in source_ids]
    vector_sources = [s for s in sources if s and s["lifecycle"] != "retired" and s["ingestion_mode"] != "sql"]
    sql_sources = [s for s in sources if s and s["lifecycle"] != "retired" and s["ingestion_mode"] == "sql"]

    source_kind_by_id: dict[str, str] = {}
    for s in vector_sources:
        source_kind_by_id[s["id"]] = "vector"
    for s in sql_sources:
        source_kind_by_id[s["id"]] = "sql"
    return vector_sources, sql_sources, source_kind_by_id


def _search_knowledge_spec(vector_sources: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]]:
    listing = ", ".join(f"{s['name']} ({s['id']})" for s in vector_sources)
    description = (
        "Search the agent's bound knowledge base for relevant passages from "
        f"documents. Available sources: {listing}. Call once per source that "
        "might be relevant; call again with a different query if the first "
        "result doesn't answer the question."
    )
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "source_id": {"type": "string", "enum": [s["id"] for s in vector_sources]},
            "domain": {
                "type": "string",
                "description": (
                    "Optional — if the question is clearly scoped to one governance "
                    "domain (e.g. 'network_ops', 'HR'), restrict the search to "
                    "documents tagged with that domain. Omit otherwise."
                ),
            },
        },
        "required": ["query", "source_id"],
    }
    return "search_knowledge", description, schema


def _query_structured_data_spec(sql_sources: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]]:
    listing = ", ".join(f"{s['name']} ({s['id']})" for s in sql_sources)
    description = (
        "Ask a natural-language question against a bound structured/tabular "
        f"data source (read-only). Available sources: {listing}. Use this for "
        "counts, aggregates, filters, or lookups over tabular data — not for "
        "prose documents."
    )
    schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question to answer from this data source."},
            "source_id": {"type": "string", "enum": [s["id"] for s in sql_sources]},
        },
        "required": ["question", "source_id"],
    }
    return "query_structured_data", description, schema


def anthropic_tool_defs(vector_sources: list[dict[str, Any]], sql_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools = []
    if vector_sources:
        name, description, schema = _search_knowledge_spec(vector_sources)
        tools.append({"name": name, "description": description, "input_schema": schema})
    if sql_sources:
        name, description, schema = _query_structured_data_spec(sql_sources)
        tools.append({"name": name, "description": description, "input_schema": schema})
    return tools


def openai_tool_defs(vector_sources: list[dict[str, Any]], sql_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same catalog, OpenAI/Groq function-calling shape: {"type": "function",
    "function": {name, description, parameters}} instead of Anthropic's flat
    {name, description, input_schema}."""
    tools = []
    if vector_sources:
        name, description, schema = _search_knowledge_spec(vector_sources)
        tools.append({"type": "function", "function": {"name": name, "description": description, "parameters": schema}})
    if sql_sources:
        name, description, schema = _query_structured_data_spec(sql_sources)
        tools.append({"type": "function", "function": {"name": name, "description": description, "parameters": schema}})
    return tools


async def execute_tool(
    name: str, input_: dict[str, Any], source_kind_by_id: dict[str, str], top_k: int, score_threshold: float,
    rerank_enabled: bool = True, agent_id: Optional[str] = None, citation_format: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Returns (tool_result_content, retrieval_entries, citations). Re-validates
    source_id server-side against the agent's actual bound set — the model's
    JSON-schema enum is a hint to the model, not a trust boundary."""
    source_id = input_.get("source_id")
    kind = source_kind_by_id.get(source_id)
    if kind is None:
        return f"Error: source_id '{source_id}' is not bound to this agent.", [], []

    if name == "search_knowledge" and kind == "vector":
        import time
        from app.domains.knowledge import retrieval_service as retrieval
        from app.domains.monitoring import service as monitoring

        query = input_.get("query", "")
        started = time.perf_counter()
        error: Optional[str] = None
        results: list[dict[str, Any]] = []
        try:
            results = await retrieval.retrieve_for_sources(
                [source_id], query, top_k, score_threshold,
                rerank_enabled=rerank_enabled, document_domain=input_.get("domain") or None,
            )
        except ValueError as e:
            error = str(e)

        if agent_id:
            latency_ms = (time.perf_counter() - started) * 1000
            providers = await knowledge_sources_repo.get_embedding_providers([source_id])
            provider = providers.get(source_id, "openai")
            model = "text-embedding-3-small" if provider == "openai" else "local_bge_small"
            await monitoring.record_event(
                agent_id, "retrieval", "error" if error else "ok", latency_ms,
                tokens_in=_estimate_tokens(query), model=model, error_msg=error,
            )

        if error:
            return f"Error: {error}", [], []

        citations: list[str] = []
        if any(r["passed"] for r in results):
            from app.domains.knowledge import knowledge_documents_repo
            source = await knowledge_sources_repo.get_by_id(source_id)
            source_name = source["name"] if source else source_id
            docs_by_id = {d["id"]: d for d in await knowledge_documents_repo.get_by_source(source_id)}
            for r in results:
                if not r["passed"]:
                    continue
                doc_title = docs_by_id.get(r["doc_id"], {}).get("title", r["doc_id"])
                citations.append(render_citation(citation_format, source_name, r["source_id"], r["doc_id"], doc_title))
        return json.dumps({"source_id": source_id, "results": results}), results, citations

    if name == "query_structured_data" and kind == "sql":
        from app.domains.knowledge import sql_executor_service as sql_executor
        try:
            result = await sql_executor.ask_question(source_id, input_.get("question", ""))
        except (RuntimeError, ValueError) as e:
            return f"Error: {e}", [], []
        return json.dumps(result), [], [f"[source: kb://{source_id} · sql]"]

    return f"Error: '{name}' is not applicable to source_id '{source_id}'.", [], []
