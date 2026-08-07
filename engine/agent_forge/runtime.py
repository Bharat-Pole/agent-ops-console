"""In-process live runtime — builds and RUNS the agent's LangGraph graph from a
console AgentRecord, so the console Playground can talk to the real agent.

Mirrors the generated templates (single / dag / supervisor) but constructs live
LangGraph objects. Real Gemini model + real tools (web_search via DuckDuckGo);
advisory-only is preserved (flagged/write tools are never bound). Needs a real
GOOGLE_API_KEY at run time (unless a `model` is injected, e.g. tests).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.types import Command
from langgraph.prebuilt import create_react_agent, ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .ir import AgentIR
from .loader import load_agent
from .dispatch import Topology, dispatch
from .tools_lib import resolve_tools
from . import secrets as vault


def _sys_prompt(ir: AgentIR) -> str:
    """System prompt + TODAY'S DATE, computed at run time. Without the date the
    model has no way to know its training data is stale, so it overrides fresh
    tool results with its prior ("X hasn't happened yet") — the exact failure
    seen with time-sensitive questions. Date injection happens here, never at
    generation time (codegen stays byte-deterministic)."""
    from datetime import datetime
    today = datetime.now().strftime("%A, %B %d, %Y")
    return (
        ir.prompt.system_prompt
        + f"\n\nToday's date is {today}. Your training data predates this — events you "
        "believe are in the future may already have happened. For anything time-sensitive, "
        "tool results are the ground truth: never claim an event has not occurred when "
        "search results say it has."
    )


# Conversation memory: one MemorySaver per (agent, llm_target), living for the
# life of the engine process. Threads inside it are isolated by thread_id.
# Without this, every message rebuilt a fresh MemorySaver → every turn was a
# cold start and the agent could not answer "what did you just do?".
_CHECKPOINTERS: dict[str, MemorySaver] = {}


def _checkpointer_for(ir: AgentIR, llm_target: str) -> MemorySaver:
    return _CHECKPOINTERS.setdefault(f"{ir.agent_id}:{llm_target}", MemorySaver())


def _build_model(ir: AgentIR, api_key: str | None = None, model_id: str | None = None):
    """Construct the real Gemini chat model. `api_key` (from the console UI) takes
    precedence over env credentials; Vertex uses ADC regardless. A MODEL env var on
    the engine overrides the config's (aliased) model id, same as generated code.

    IMPORTANT: return the plain chat model — no .with_retry()/.with_fallbacks()
    wrappers. Those return Runnables WITHOUT bind_tools/with_structured_output,
    which crashes create_react_agent and the supervisor. Retries use the client's
    max_retries; the fallback model is applied at run level (run_agent)."""
    import os
    if ir.llm_target == "claude":
        # Opt-in Claude runtime (langchain-anthropic wraps the official SDK).
        # NO sampling params: current Claude models (opus-4.7+) reject
        # temperature/top_p/top_k with a 400 — steering is via prompting.
        from langchain_anthropic import ChatAnthropic
        from .model_map import claude_model_id
        model_id = model_id or os.getenv("CLAUDE_MODEL") or claude_model_id(ir.model.primary)
        kw = {"api_key": api_key} if api_key else {}  # else SDK env: ANTHROPIC_API_KEY
        return ChatAnthropic(model=model_id, max_tokens=ir.model.max_output_tokens,
                             max_retries=ir.model.retries + 1, **kw)
    model_id = model_id or os.getenv("MODEL", ir.model.primary)
    if ir.llm_target == "vertex":
        from langchain_google_vertexai import ChatVertexAI
        return ChatVertexAI(model=model_id, temperature=ir.model.temperature,
                            max_output_tokens=ir.model.max_output_tokens,
                            max_retries=ir.model.retries + 1)
    from langchain_google_genai import ChatGoogleGenerativeAI
    kw = {"google_api_key": api_key} if api_key else {}
    return ChatGoogleGenerativeAI(model=model_id, temperature=ir.model.temperature,
                                  max_output_tokens=ir.model.max_output_tokens,
                                  max_retries=ir.model.retries + 1, **kw)


def _retriever_factory(ir: AgentIR, api_key: str | None = None):
    """Lazy InMemoryVectorStore from the bundled knowledge snippets (needs a key)."""
    @lru_cache(maxsize=1)
    def _store():
        from langchain_core.vectorstores import InMemoryVectorStore
        from langchain_core.documents import Document
        if ir.llm_target == "vertex":
            from langchain_google_vertexai import VertexAIEmbeddings
            emb = VertexAIEmbeddings(model_name=ir.rag.embedding_model or "text-embedding-004")
        else:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            kw = {"google_api_key": api_key} if api_key else {}
            emb = GoogleGenerativeAIEmbeddings(model="models/" + (ir.rag.embedding_model or "text-embedding-004"), **kw)
        vs = InMemoryVectorStore(embedding=emb)
        docs = [Document(page_content=s.get("text", ""), metadata={"doc_id": s.get("doc_id", "")})
                for s in ir.rag.snippets if s.get("text")]
        if docs:
            vs.add_documents(docs)
        return vs

    def get_retriever():
        return _store().as_retriever(search_kwargs={"k": ir.rag.top_k or 5})
    return get_retriever


def _build_from_ir(ir: AgentIR, topo: Topology, model=None, api_key: str | None = None, checkpointer=None):
    """`api_key` here is the ALREADY-RESOLVED key (callers run the vault chain)."""
    model = model if model is not None else _build_model(ir, api_key=api_key)
    tools = resolve_tools(ir.tools, secrets=vault.resolve_tool_secrets(ir.secret_refs))
    checkpointer = checkpointer if checkpointer is not None else MemorySaver()

    if topo is Topology.SINGLE:
        return create_react_agent(model, tools=tools, prompt=_sys_prompt(ir), checkpointer=checkpointer)

    if topo is Topology.SUPERVISOR:
        from pydantic import create_model
        names = [s.name for s in ir.sub_agents]
        by_name = {getattr(t, "name", ""): t for t in tools}
        Route = create_model("_Route", next=(Literal[tuple(names + ["FINISH"])], ...))  # type: ignore[valid-type]

        workers = {
            s.name: create_react_agent(
                model,
                tools=[by_name[t] for t in s.tools if t in by_name],
                prompt=ir.prompt.per_sub_agent.get(s.name, s.prompt),
            )
            for s in ir.sub_agents
        }

        def supervisor(state: MessagesState):
            decision = model.with_structured_output(Route).invoke(
                [SystemMessage(content=_sys_prompt(ir))] + state["messages"])
            nxt = getattr(decision, "next", "FINISH")
            return Command(goto=END if nxt == "FINISH" else nxt)

        g = StateGraph(MessagesState)
        g.add_node("supervisor", supervisor)
        for _name in names:
            def _node(state, _w=workers[_name]):
                out = _w.invoke(state)
                return Command(goto="supervisor", update={"messages": out["messages"][-1:]})
            g.add_node(_name, _node)
        g.add_edge(START, "supervisor")
        return g.compile(checkpointer=checkpointer)

    if topo is Topology.PIPELINE:
        # Sequential stages: START → s1 → … → sN → END (order = config order).
        by_name = {getattr(t, "name", ""): t for t in tools}
        g = StateGraph(MessagesState)
        prev: str = START
        for s in ir.sub_agents:
            worker = create_react_agent(
                model,
                tools=[by_name[t] for t in s.tools if t in by_name],
                prompt=ir.prompt.per_sub_agent.get(s.name, s.prompt),
            )

            def _stage(state, _w=worker):
                out = _w.invoke(state)
                return {"messages": out["messages"][-1:]}

            g.add_node(s.name, _stage)
            g.add_edge(prev, s.name)
            prev = s.name
        g.add_edge(prev, END)
        return g.compile(checkpointer=checkpointer)

    if topo is Topology.PARALLEL:
        # Fan-out to every branch, then a wait-for-ALL join into `aggregate`.
        by_name = {getattr(t, "name", ""): t for t in tools}
        g = StateGraph(MessagesState)
        names = [s.name for s in ir.sub_agents]
        for s in ir.sub_agents:
            worker = create_react_agent(
                model,
                tools=[by_name[t] for t in s.tools if t in by_name],
                prompt=ir.prompt.per_sub_agent.get(s.name, s.prompt),
            )

            def _branch(state, _w=worker, _n=s.name):
                out = _w.invoke(state)
                last = out["messages"][-1]
                # label the contribution so the join prompt + trace can attribute it
                return {"messages": [AIMessage(content=_content_to_text(getattr(last, "content", "")), name=_n)]}

            g.add_node(s.name, _branch)
            g.add_edge(START, s.name)  # fan-out (same superstep)

        def aggregate(state: MessagesState):
            merged = model.invoke(
                [SystemMessage(content=_sys_prompt(ir)
                               + "\n\nSynthesize the branch outputs above into one final advisory answer.")]
                + state["messages"]
            )
            return {"messages": [merged]}

        g.add_node("aggregate", aggregate)
        # VALIDATED (langgraph 1.2.10): list-form add_edge = wait-for-ALL barrier;
        # aggregate runs exactly once. MessagesState's add_messages reducer merges
        # concurrent branch writes in node-insertion (config) order → deterministic.
        # defer=True would only be needed if branches ever became multi-node.
        g.add_edge(names, "aggregate")
        g.add_edge("aggregate", END)
        return g.compile(checkpointer=checkpointer)

    # DAG — explicit graph spec (console orchestration.graph) when present…
    if ir.graph is not None and ir.graph.nodes:
        return _build_dag_from_spec(ir, model, tools, checkpointer, api_key)

    # …else the derived tool-aware RAG pipeline: (retrieve →) generate ⇄ tools.
    # The generate node binds the agent's advisory tools so a RAG agent can still
    # call e.g. web_search; retrieval runs first only when knowledge snippets exist.
    g = StateGraph(MessagesState)
    bound = model.bind_tools(tools) if tools else model

    def generate(state: MessagesState):
        return {"messages": [bound.invoke([SystemMessage(content=_sys_prompt(ir))] + state["messages"])]}

    g.add_node("generate", generate)
    if tools:
        g.add_node("tools", ToolNode(tools))
        g.add_conditional_edges("generate", tools_condition)
        g.add_edge("tools", "generate")
    else:
        g.add_edge("generate", END)

    if ir.rag.enabled and ir.rag.snippets:
        get_retriever = _retriever_factory(ir, api_key=api_key)

        def retrieve(state: MessagesState):
            try:
                docs = get_retriever().invoke(state["messages"][-1].content)
                ctx = "\n\n".join(getattr(d, "page_content", str(d)) for d in docs)
            except Exception:
                ctx = ""
            return {"messages": [SystemMessage(content="Retrieved context:\n" + ctx)]}

        g.add_node("retrieve", retrieve)
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", "generate")
    else:
        g.add_edge(START, "generate")
    return g.compile(checkpointer=checkpointer)


def _build_dag_from_spec(ir: AgentIR, model, tools, checkpointer, api_key: str | None):
    """Construct a StateGraph from the console's explicit orchestration.graph.
    Mirrors the generated dag/graph.py.j2 exactly (both drive off plan_dag_graph)."""
    from .graphplan import plan_dag_graph
    plan = plan_dag_graph(ir.graph, has_tools=bool(tools))
    g = StateGraph(MessagesState)
    bound = model.bind_tools(tools) if (tools and plan.bind_tools) else model

    get_retriever = None
    if plan.has_retrieve and ir.rag.enabled and ir.rag.snippets:
        get_retriever = _retriever_factory(ir, api_key=api_key)

    def _llm(state: MessagesState):
        return {"messages": [bound.invoke([SystemMessage(content=_sys_prompt(ir))] + state["messages"])]}

    def _retrieve(state: MessagesState):
        ctx = ""
        if get_retriever is not None:
            try:
                docs = get_retriever().invoke(state["messages"][-1].content)
                ctx = "\n\n".join(getattr(d, "page_content", str(d)) for d in docs)
            except Exception:
                ctx = ""
        return {"messages": [SystemMessage(content="Retrieved context:\n" + ctx)]}

    for nid, ek in plan.nodes:
        if ek == "tool":
            g.add_node(nid, ToolNode(tools))
        elif ek == "retrieve":
            g.add_node(nid, _retrieve)
        else:
            g.add_node(nid, _llm)

    g.add_edge(START, plan.entry)
    for src, tgt, conditional in plan.edges:
        if conditional:
            g.add_conditional_edges(src, tools_condition, {"tools": tgt, END: END})
        else:
            g.add_edge(src, tgt)
    for nid in plan.terminals:
        g.add_edge(nid, END)

    return g.compile(checkpointer=checkpointer)


def _content_to_text(content) -> str:
    """Normalize message content to a plain string. langchain-core 1.x models
    (incl. Gemini via langchain-google-genai 4.x) may return a LIST of content
    blocks ({'type':'text','text':...}, thinking blocks, etc.) — the UI needs text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                if b.get("type") not in (None, "text"):
                    continue  # skip thinking/tool-call blocks
                t = b.get("text")
                if isinstance(t, str) and t:
                    parts.append(t)
        return "\n".join(parts).strip()
    return str(content or "")


def _provider(llm_target: str) -> str:
    return "claude" if llm_target == "claude" else "gemini"


def build_live_graph(record: dict, llm_target: str = "aistudio", model=None, api_key: str | None = None):
    ir = load_agent(record, llm_target=llm_target)
    resolved, _src = vault.resolve_model_key(ir.secret_refs, api_key, provider=_provider(llm_target))
    return _build_from_ir(ir, dispatch(ir), model=model, api_key=resolved,
                          checkpointer=_checkpointer_for(ir, llm_target))


def run_agent(record: dict, message: str, thread_id: str = "default",
              llm_target: str = "aistudio", model=None, api_key: str | None = None) -> dict[str, Any]:
    ir = load_agent(record, llm_target=llm_target)
    topo = dispatch(ir)
    # vault resolution: request key > agent's named secret > provider default > env
    resolved_key, cred_source = vault.resolve_model_key(ir.secret_refs, api_key, provider=_provider(llm_target))
    # shared per-agent checkpointer → real multi-turn memory across calls
    saver = _checkpointer_for(ir, llm_target)
    graph = _build_from_ir(ir, topo, model=model, api_key=resolved_key, checkpointer=saver)
    payload = {"messages": [HumanMessage(content=message)]}
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        result = graph.invoke(payload, cfg)
    except Exception:
        # run-level fallback: rebuild on the fallback model (covers 404s/quota);
        # SAME checkpointer so the conversation thread survives the fallback.
        # (claude target has no gemini fallback — the config's fallback id is a
        # gemini model and would 404 on the Anthropic API)
        if model is not None or not ir.model.fallback or llm_target == "claude":
            raise
        fb = _build_model(ir, api_key=resolved_key, model_id=ir.model.fallback)
        graph = _build_from_ir(ir, topo, model=fb, api_key=resolved_key, checkpointer=saver)
        result = graph.invoke(payload, cfg)
    msgs = result.get("messages", [])
    reply = ""
    for m in reversed(msgs):
        if getattr(m, "type", "") == "ai":
            text = _content_to_text(getattr(m, "content", ""))
            if text:
                reply = text
                break
    if not reply and msgs:
        reply = _content_to_text(getattr(msgs[-1], "content", ""))

    # lightweight trace for the inspector
    tool_calls = []
    for m in msgs:
        for tc in (getattr(m, "tool_calls", None) or []):
            tool_calls.append(tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", ""))
    trace = {
        "topology": topo.value,
        "pattern": ir.pattern,
        "model": ir.model.primary,
        "llm_target": ir.llm_target,
        "credential_source": cred_source,  # request|agent_secret|vault_default|env — never values
        "bound_tools": [t.func for t in ir.tools],
        "disabled_tools": [t.func for t in ir.disabled_tools],
        "sub_agents": [s.name for s in ir.sub_agents],
        "tool_calls": tool_calls,
        "rag": ir.rag.enabled,
        "messages": len(msgs),
    }
    if topo is Topology.PARALLEL:
        branch_names = {s.name for s in ir.sub_agents}
        trace["branch_outputs"] = {
            m.name: _content_to_text(getattr(m, "content", ""))
            for m in msgs if getattr(m, "name", None) in branch_names
        }
    return {"reply": reply, "trace": trace}
