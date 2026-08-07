"""Framework-agnostic intermediate representation the templates consume.

The loader unwraps the console's Prov<T> leaves into these flat dataclasses so
templates never touch envelopes or console-specific shapes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HttpToolIR:
    method: str                       # GET|POST|PUT|DELETE|PATCH
    url_template: str                 # {param} placeholders filled from the query arg
    query_params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body_template: str | None = None
    auth_secret_ref: str | None = None  # vault secret NAME only
    auth_header: str = "Authorization: Bearer {secret}"


@dataclass
class ToolIR:
    name: str            # display id from the config, e.g. "incident_reader" or "web search tool"
    func: str            # sanitized Python identifier, e.g. "web_search_tool"
    ref: str             # "tools://incident_reader@v1"
    permission: str      # advisory scope: read|summarize|draft|recommend|validate
    write_capable: bool  # True → emitted DISABLED, never bound
    reason: str = ""     # why flagged (for the disabled stub docstring)
    capability: str | None = None  # known real capability, e.g. "web_search" | "http_api" (else stub)
    kind: str = "catalog"           # catalog | http_api
    http: "HttpToolIR | None" = None


@dataclass
class SubAgentIR:
    name: str
    role: str
    prompt: str          # per_sub_agent_prompts[name] or prompt_hint
    tools: list[str] = field(default_factory=list)  # short tool names (may be empty)


@dataclass
class RagIR:
    enabled: bool = False
    retrieval_type: str | None = None
    top_k: int | None = None
    score_threshold: float | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    embedding_model: str | None = None       # mapped (vertex:// stripped)
    index_target: str | None = None          # vector://alloydb-…
    knowledge_source_refs: list[str] = field(default_factory=list)
    snippets: list[dict[str, str]] = field(default_factory=list)  # optional {doc_id,text}


@dataclass
class GraphNodeIR:
    id: str
    kind: str            # llm | tool | retrieve | route | aggregate
    label: str = ""
    sub_agent: str | None = None


@dataclass
class GraphEdgeIR:
    source: str          # console 'from'
    target: str          # console 'to'
    when: str | None = None  # conditional-edge guard (e.g. 'tool_calls')


@dataclass
class GraphIR:
    nodes: list[GraphNodeIR] = field(default_factory=list)
    edges: list[GraphEdgeIR] = field(default_factory=list)

    @property
    def entry(self) -> str | None:
        return self.nodes[0].id if self.nodes else None


@dataclass
class HitlGateIR:
    placement: str       # raw free-text placement
    trigger: str


@dataclass
class ModelIR:
    primary: str                 # mapped model id (vertex:// stripped)
    fallback: str | None
    temperature: float
    max_output_tokens: int
    retries: int


@dataclass
class PromptIR:
    system_prompt: str           # synthesized prose (persona + task + advisory reminder)
    provenance_comments: list[str] = field(default_factory=list)  # referenced refs as comments
    per_sub_agent: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentIR:
    agent_id: str
    slug: str                    # filesystem slug, e.g. "incident-response-coordinator-…"
    pkg: str                     # python package name, e.g. "incident_response_coordinator_…"
    name: str
    description: str
    objective: str
    tier: str                    # minimal|standardized|advanced
    llm_target: str              # aistudio|vertex

    model: ModelIR
    prompt: PromptIR
    tools: list[ToolIR]          # advisory (bindable) tools
    disabled_tools: list[ToolIR] # flagged write-capable (emitted disabled)
    sub_agents: list[SubAgentIR]
    rag: RagIR
    hitl: list[HitlGateIR]

    # hub|pipeline|parallel — refines the coordinator+subagents topology
    pattern: str = "hub"
    # explicit renderable graph (nodes+edges); None → DAG uses the derived shape
    graph: "GraphIR | None" = None
    # named secret references: {'model': <secret name>, <tool name>: <secret name>}
    secret_refs: dict[str, str] = field(default_factory=dict)
    # the raw console AgentRecord, re-embedded verbatim for provenance
    raw_config: dict[str, Any] = field(default_factory=dict)
