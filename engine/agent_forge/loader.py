"""Load a console AgentRecord JSON export into the flat AgentIR.

Reads inline Prov<T> leaves via `.value`; carries review_card.flagged_write_tools
at the RECORD level. Accepts either a full AgentRecord (has `config`) or a bare
AgentConfig.
"""
from __future__ import annotations

import json
import keyword
import re
from pathlib import Path
from typing import Any

from .ir import AgentIR, ToolIR, SubAgentIR, RagIR, HitlGateIR, ModelIR, HttpToolIR, GraphIR, GraphNodeIR, GraphEdgeIR
from .model_map import map_model
from .prompts_synth import synthesize_prompt
from .writedetect import tool_is_write_capable
from .tools_lib import detect_capability


def _v(node: Any, default: Any = None) -> Any:
    """Unwrap a Prov<T> leaf ({value,...}) → its value; pass through plain values."""
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node if node is not None else default


def _tool_name(ref: str) -> str:
    # "tools://incident_reader@v1" -> "incident_reader"
    m = re.match(r"^(?:tools://)?([^@]+)", ref.strip())
    return (m.group(1) if m else ref).strip()


def _func_name(name: str) -> str:
    """Sanitize a tool/display name into a valid Python identifier.
    'web search tool' -> 'web_search_tool'."""
    f = re.sub(r"\W+", "_", (name or "").strip()).strip("_").lower()
    if not f:
        f = "tool"
    if f[0].isdigit():
        f = "t_" + f
    if keyword.iskeyword(f):
        f = f + "_"
    return f


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:48] or "agent"


def load_agent(source: str | dict, *, llm_target: str = "aistudio") -> AgentIR:
    if isinstance(source, (str, Path)):
        raw = json.loads(Path(source).read_text(encoding="utf-8"))
    else:
        raw = source

    record: dict = raw if "config" in raw else {"config": raw, "review_card": None}
    cfg: dict = record["config"]
    review_card = record.get("review_card") or None

    ident = cfg.get("identity", {})
    model_g = cfg.get("model", {})
    prompt_g = cfg.get("prompt", {})
    data_g = cfg.get("data", {})
    tooling_g = cfg.get("tooling", {})
    orch_g = cfg.get("orchestration", {})
    ks_g = cfg.get("knowledge_sources", {})

    agent_id = _v(ident.get("agent_id")) or _slugify(_v(ident.get("agent_name"), "agent"))
    slug = _slugify(agent_id)
    pkg = re.sub(r"[^a-z0-9]+", "_", slug).strip("_") or "agent"

    # ---- tools (advisory, bindable) + flagged writes (disabled) ----
    flagged_names = set()
    if review_card and isinstance(review_card.get("flagged_write_tools"), list):
        flagged_names = {_tool_name(t) for t in review_card["flagged_write_tools"]}

    permission = _v(tooling_g.get("tool_permission"), "read")
    # executable tool defs transported alongside the record (name -> def); mirrors
    # the _knowledge_snippets pattern so run + generate both see them via load_agent.
    tool_defs = {d.get("name"): d for d in (record.get("_bound_tool_defs") or []) if isinstance(d, dict)}
    http_secret_refs: dict[str, str] = {}  # func -> vault secret name (GET http tools only)
    tools: list[ToolIR] = []
    disabled: list[ToolIR] = []
    for ref in _v(tooling_g.get("bound_tools"), []) or []:
        name = _tool_name(ref)
        func = _func_name(name)
        d = tool_defs.get(name)
        http_ir = None
        kind = "catalog"
        if d and d.get("kind") == "http_api" and isinstance(d.get("http"), dict):
            h = d["http"]
            kind = "http_api"
            http_ir = HttpToolIR(
                method=str(h.get("method", "GET")).upper(),
                url_template=h.get("url_template", ""),
                query_params=h.get("query_params") or {},
                headers=h.get("headers") or {},
                body_template=h.get("body_template"),
                auth_secret_ref=d.get("auth_secret_ref"),
                auth_header=h.get("auth_header") or "Authorization: Bearer {secret}",
            )
        mutating_http = bool(http_ir and http_ir.method != "GET")
        write = tool_is_write_capable(name) or name in flagged_names or mutating_http
        capability = None
        if not write:
            # DECLARED capability wins (from the console tool catalog — no name
            # guessing). 'none' is an explicit "not connected" → honest stub.
            # Only legacy tools with no declaration fall back to the heuristic.
            declared = d.get("capability") if d else None
            if declared == "web_search":
                capability = "web_search"
            elif declared == "none":
                capability = "none"
            elif http_ir:
                capability = "http_api"
            elif declared == "http_api":
                capability = "none"  # declared http but no config → not connected
            else:
                capability = detect_capability(name)  # legacy fallback
        reason = ("mutating HTTP method — write-capable" if mutating_http
                  else ("write-capable name heuristic / flagged" if write else ""))
        (disabled if write else tools).append(
            ToolIR(name=name, func=func, ref=ref, permission=permission, write_capable=write,
                   reason=reason, capability=capability, kind=kind, http=http_ir)
        )
        # GET http tool with an auth secret → register so resolve_tool_secrets injects it
        if http_ir and not write and http_ir.auth_secret_ref:
            http_secret_refs[func] = http_ir.auth_secret_ref
    # flagged-not-bound tools → emit as disabled stubs too (for HITL visibility)
    bound_names = {t.name for t in tools} | {t.name for t in disabled}
    for name in sorted(flagged_names - bound_names):
        disabled.append(ToolIR(name=name, func=_func_name(name), ref=f"tools://{name}", permission="draft",
                               write_capable=True, reason="flagged write tool (not bound)"))
    tools.sort(key=lambda t: t.name)
    disabled.sort(key=lambda t: t.name)

    # ---- sub-agents (config order preserved) ----
    per_sub = _v(prompt_g.get("per_sub_agent_prompts")) or {}
    sub_agents: list[SubAgentIR] = []
    for sa in _v(orch_g.get("sub_agents"), []) or []:
        nm = sa.get("name")
        sub_agents.append(SubAgentIR(
            name=nm,
            role=sa.get("role", ""),
            prompt=(per_sub.get(nm) or sa.get("prompt_hint") or f"Handle the {nm} step; advisory only."),
            tools=[_func_name(_tool_name(t)) for t in (sa.get("tools") or [])],
        ))

    # ---- HITL gates ----
    hitl = [HitlGateIR(placement=g.get("placement", ""), trigger=g.get("trigger", ""))
            for g in (_v(orch_g.get("hitl_gate_placement"), []) or [])]

    # ---- model ----
    primary = map_model(_v(model_g.get("model_primary")))
    fallback = map_model(_v(model_g.get("model_fallback"))) if _v(model_g.get("model_fallback")) else None
    if fallback == primary:
        # both aliased to the same current model — substitute a distinct fallback
        from .model_map import SECONDARY_FALLBACK
        fallback = SECONDARY_FALLBACK if primary != SECONDARY_FALLBACK else None
    model = ModelIR(
        primary=primary,
        fallback=fallback,
        temperature=float(_v(model_g.get("temperature"), 0.2)),
        max_output_tokens=int(_v(model_g.get("max_output_tokens"), 2048)),
        retries=int(_v(orch_g.get("retries"), 1)),
    )

    # ---- prompt synthesis ----
    prompt = synthesize_prompt(
        persona_role=_v(prompt_g.get("persona_role")),
        task_prompt=_v(prompt_g.get("task_prompt")),
        objective=_v(ident.get("objective")),
        system_prompt_ref=_v(prompt_g.get("system_prompt_ref")),
        safety_ref=_v(prompt_g.get("safety_instructions")),
        citation_ref=_v(prompt_g.get("citation_rules")),
        per_sub_agent=per_sub,
        tool_names=[t.func for t in tools],
    )

    # ---- RAG ----
    rag = RagIR(
        enabled=bool(_v(data_g.get("rag_enabled"), False)),
        retrieval_type=_v(data_g.get("retrieval_type")),
        top_k=_v(data_g.get("top_k")),
        score_threshold=_v(data_g.get("score_threshold")),
        chunk_size=_v(data_g.get("chunk_size")),
        chunk_overlap=_v(data_g.get("chunk_overlap")),
        embedding_model=map_model(_v(ks_g.get("embedding_model"))) if _v(ks_g.get("embedding_model")) else None,
        index_target=_v(ks_g.get("index_target")),
        knowledge_source_refs=list(_v(data_g.get("knowledge_source_refs"), []) or []),
        snippets=list(record.get("_knowledge_snippets") or []),  # optional, bundled by the service
    )

    # additive leaves (absent in old exports — defaults keep them loading unchanged)
    pattern = _v(orch_g.get("pattern"), "hub") or "hub"

    # ---- explicit graph spec (additive; None when absent) ----
    graph = None
    graph_raw = _v(orch_g.get("graph"))
    if isinstance(graph_raw, dict) and graph_raw.get("nodes"):
        nodes = [
            GraphNodeIR(id=str(n.get("id")), kind=str(n.get("kind", "llm")),
                       label=str(n.get("label", "")), sub_agent=n.get("sub_agent"))
            for n in graph_raw.get("nodes", []) if n.get("id")
        ]
        node_ids = {n.id for n in nodes}
        edges = [
            GraphEdgeIR(source=str(e.get("from")), target=str(e.get("to")), when=e.get("when"))
            for e in graph_raw.get("edges", [])
            if e.get("from") in node_ids and e.get("to") in node_ids
        ]
        if nodes:
            graph = GraphIR(nodes=nodes, edges=edges)
    secret_refs_raw = _v(tooling_g.get("secret_refs")) or {}
    secret_refs = {str(k): str(v) for k, v in secret_refs_raw.items()} if isinstance(secret_refs_raw, dict) else {}
    # merge per-tool http auth secret names (explicit config secret_refs win)
    for func, sname in http_secret_refs.items():
        secret_refs.setdefault(func, sname)

    return AgentIR(
        agent_id=agent_id, slug=slug, pkg=pkg,
        name=_v(ident.get("agent_name"), "Agent"),
        description=_v(ident.get("description"), ""),
        objective=_v(ident.get("objective"), ""),
        tier=record.get("capability_tier") or "standardized",
        llm_target=llm_target,
        model=model, prompt=prompt, tools=tools, disabled_tools=disabled,
        sub_agents=sub_agents, rag=rag, hitl=hitl,
        pattern=pattern, graph=graph, secret_refs=secret_refs,
        raw_config=record,
    )
