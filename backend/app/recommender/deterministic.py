"""Layer 1 — deterministic recommender (Decision 2.2: always-computed baseline
and offline/failure fallback; the validator that gates every LLM proposal).

Faithful Python port of the console engine (src/kernel/engine/*): NLU cues,
S1–S6 signals with the LOCKED Section 7.2 weights/formula/overrides, write
detection, risk inference, architecture selection, and graph synthesis.
Adaptations from the TS original:
- input is the normalized intent document (6 field groups), not the kernel shape
- console risk tier 'critical' maps to the Blueprint's 'restricted'
- output adds a workflow-DAG sketch in the platform's 10-node vocabulary
  (Pass 5) so the Builder canvas has a starting draft even with no LLM
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..intent.schema import NormalizedIntent

RULES_VERSION = "recommender-deterministic-v1"

# ---- Section 7.2 weights — EXACT and LOCKED ---------------------------------

WEIGHTS: dict[str, tuple[int, int, int]] = {  # (minimal, standardized, advanced)
    "S1": (0, 10, 5),
    "S2": (0, 3, 10),
    "S3": (0, 5, 10),
    "S4": (5, 5, 5),
    "S5": (0, 2, 10),
    "S6": (0, 0, 15),
}
BASE_MINIMAL = 20

TIERS = ("minimal", "standardized", "advanced")
ARCHITECTURES = ("single", "sequential_pipeline", "hub_and_spoke", "graph")
RISK_ORDER = ("low", "medium", "high", "restricted")

# Pass 5 node vocabulary — the workflow-DAG sketch is drawn from this set only.
NODE_TYPES = (
    "rag", "prompt", "llm", "tool_call", "mcp_call", "structured_query",
    "human_approval", "evaluation", "output_format", "guardrail",
)

# ---- NLU cues (ported verbatim from nlu.ts) ---------------------------------

_TASK_VERBS: list[tuple[str, re.Pattern[str]]] = [
    ("coordinate", re.compile(r"\b(coordinat|orchestrat)")),
    ("route", re.compile(r"\b(route|escalate|assign|hand[- ]?off|dispatch|notify)")),
    ("draft", re.compile(r"\b(draft|compose|write)\b")),
    ("analyze", re.compile(r"\b(analyze|assess|evaluate|investigate|research)")),
    ("summarize", re.compile(r"\b(summariz|summarise|digest|recap)")),
    ("answer", re.compile(r"\b(answer|respond|explain|help)\b")),
]

_DOMAINS: list[tuple[str, re.Pattern[str]]] = [
    ("HR", re.compile(r"\b(hr|human resources|employee|benefits|payroll|pto)\b")),
    ("network_ops", re.compile(r"\b(noc|incident|network|outage|capacity|routing|telemetry|fiber)\b")),
    ("finance", re.compile(r"\b(finance|financial|invoice|payment|revenue|billing)\b")),
    ("legal", re.compile(r"\b(legal|contract|clause|nda|msa|counsel)\b")),
    ("support", re.compile(r"\b(support|ticket|help ?desk|faq|technician|field)\b")),
    ("sales", re.compile(r"\b(sales|crm|churn|retention|account|pipeline)\b")),
    ("compliance", re.compile(r"\b(regulat|compliance|filing|fcc|puc|attestation)\b")),
]

_SYSTEM_FAMILIES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bslack\b"), "slack"),
    (re.compile(r"\bemail\b"), "email"),
    (re.compile(r"\bjira\b"), "ticketing"),
    (re.compile(r"\bservicenow\b"), "ticketing"),
    (re.compile(r"\bzendesk\b"), "ticketing"),
    (re.compile(r"\bticketing\b"), "ticketing"),
    (re.compile(r"\bconfluence\b"), "docs"),
    (re.compile(r"\bsharepoint\b"), "docs"),
    (re.compile(r"\bgithub\b"), "github"),
    (re.compile(r"\bsalesforce\b"), "crm"),
    (re.compile(r"\bcrm\b"), "crm"),
    (re.compile(r"\bdatabase\b"), "database"),
    (re.compile(r"\bdb\b"), "database"),
    (re.compile(r"\bs3\b"), "storage"),
    (re.compile(r"\bgcs\b"), "storage"),
    (re.compile(r"\bbigquery\b"), "storage"),
]

ACTION_VERBS = [
    "summarize", "summarise", "analyze", "analyse", "draft", "check", "notify", "alert",
    "review", "classify", "extract", "answer", "route", "assess", "generate", "compare",
    "flag", "monitor", "coordinate", "triage", "research", "recommend", "watch",
]

_RETRIEVAL_CUES = [
    "document", "knowledge base", "knowledge", "based on", "using data", "grounded in",
    "retrieve", "look up", "search the", "from the docs", "cited", "citation", "repository",
    "reports", "records", "database",
]

_ROUTING_CUES = ["route to", "route ", "escalate", "assign to", "hand off", "hand-off",
                 "notify", "on-call", "on call", "page ", "dispatch"]
_MULTI_AGENT_CUES = ["coordinator", "orchestrat", "team of agents", "sub-agent", "subagent",
                     "multi-agent", "multi agent", "pipeline of"]
_TOOL_CUES = ["tool", "api", "query", "read from", "check ", "call ", "connector"]

# writeDetect.ts, verbatim
_WRITE_VERBS = ["send", "approve", "deploy", "update", "create", "delete", "close", "assign",
                "notify", "post", "execute", "modify", "file", "submit", "remove", "email"]
_WRITE_TOOL_FRAGMENTS = ["notifier", "sender", "updater", "writer", "poster", "creator",
                         "deleter", "approver", "deployer"]
_ADVISORY_FRAMES = ["draft", "recommend", "suggest", "propose", "summarize", "summarise",
                    "prepare a draft", "review"]
_OBJECT_NOUNS = ["email", "message", "ticket", "record", "notification", "notifications",
                 "comms", "update", "filing", "report", "slack", "alert", "account"]

# risk.ts cues (console 'critical' → platform 'restricted')
_RESTRICTED_CUES = ["cross-border", "financial", "payment", "trading", "hipaa", "phi",
                    "regulat", "filing", "fcc", "attestation"]
_HIGH_CUES = ["customer", "pii", "personal", "ssn", "salary", "medical", "contract", "confidential"]


# ---- stage results ----------------------------------------------------------

@dataclass
class Nlu:
    task_type: str
    domain: str
    action_verbs: list[str]
    systems: list[str]
    gaps: list[str]


@dataclass
class Signal:
    fired: bool
    why: str


@dataclass
class Classification:
    proposed_tier: str
    signals: dict[str, Signal]
    scores: dict[str, int]
    reasoning: list[str]
    forced: bool
    capability_floor_note: str | None


@dataclass
class WriteDetection:
    flagged_tools: list[str]
    write_intents: list[dict]
    risk_floor: str | None


@dataclass
class RiskResult:
    risk_tier: str
    why: str


@dataclass
class GraphSpec:
    nodes: list[dict]  # {id, kind, label, sub_agent?}
    edges: list[dict]  # {from, to, when?}


@dataclass
class Recommendation:
    architecture: str
    sub_agents: list[dict]
    graph: GraphSpec | None
    flow: dict  # workflow-DAG sketch in the 10-node vocabulary
    rationale: list[str]
    confidence: str
    source: str  # 'deterministic' | 'llm'


# ---- Stage 1: NLU -----------------------------------------------------------

def _first_match(text: str, table: list[tuple[str, re.Pattern[str]]], fallback: str) -> str:
    for label, pattern in table:
        if pattern.search(text):
            return label
    return fallback


def _families_in(s: str, into: set[str]) -> None:
    s = s.lower().replace("_", " ").replace("-", " ")
    for pattern, fam in _SYSTEM_FAMILIES:
        if pattern.search(s):
            into.add(fam)


def _count_action_verbs(text: str) -> list[str]:
    found: set[str] = set()
    for v in ACTION_VERBS:
        if re.search(rf"\b{v}", text):
            found.add(v.replace("summarise", "summarize").replace("analyse", "analyze"))
    return sorted(found)


def _fires_retrieval(text: str, data_sources: list[str]) -> bool:
    return bool(data_sources) or any(c in text for c in _RETRIEVAL_CUES)


def detect_nlu(intent: NormalizedIntent) -> Nlu:
    text = intent.objective.lower()
    fams: set[str] = set()
    _families_in(text, fams)
    for s in intent.data_sources:
        _families_in(s, fams)
    for t in intent.tool_names():
        _families_in(t, fams)
    for s in intent.external_systems:
        _families_in(s, fams)

    gaps: list[str] = []
    if not intent.target_users:
        gaps.append("identity_purpose.target_users")
    if not intent.data_sources and _fires_retrieval(text, []):
        gaps.append("data_rules.data_sources")

    return Nlu(
        task_type=_first_match(text, _TASK_VERBS, "answer"),
        domain=_first_match(text, _DOMAINS, "general"),
        action_verbs=_count_action_verbs(text),
        systems=sorted(fams),
        gaps=gaps,
    )


# ---- Stage 2: classification (LOCKED formula) -------------------------------

def classify(intent: NormalizedIntent, nlu: Nlu) -> Classification:
    text = intent.objective.lower()
    tools = intent.tool_names()

    s1 = _fires_retrieval(text, intent.data_sources)
    s2 = len(nlu.action_verbs) >= 2
    s3 = len(nlu.systems) >= 2
    s4 = bool(tools) or any(c in text for c in _TOOL_CUES)
    s5 = any(c in text for c in _ROUTING_CUES)
    s6 = any(c in text for c in _MULTI_AGENT_CUES) or len(re.findall(r"\b(agent|bot)s?\b", text)) >= 2

    signals = {
        "S1": Signal(s1, "data source / retrieval language present" if s1 else "no retrieval cue"),
        "S2": Signal(s2, f"{len(nlu.action_verbs)} distinct action verbs" if s2 else "single skill"),
        "S3": Signal(s3, f"{len(nlu.systems)} distinct systems ({', '.join(nlu.systems)})" if s3 else "single or no system"),
        "S4": Signal(s4, "tool / API / action language" if s4 else "no tool cue"),
        "S5": Signal(s5, "routing / notify language" if s5 else "no hand-off cue"),
        "S6": Signal(s6, "explicit multi-agent language" if s6 else "no multi-agent cue"),
    }

    std = sum(WEIGHTS[k][1] for k in ("S1", "S2", "S3", "S4", "S5") if signals[k].fired)
    adv = sum(WEIGHTS[k][2] for k in ("S2", "S3", "S4", "S5", "S6") if signals[k].fired)
    scores = {"minimal": BASE_MINIMAL, "standardized": std, "advanced": adv}

    if adv >= std and adv >= BASE_MINIMAL:
        winner = "advanced"
    elif std >= BASE_MINIMAL:
        winner = "standardized"
    else:
        winner = "minimal"

    reasoning = [f"argmax(minimal={BASE_MINIMAL}, standardized={std}, advanced={adv}) → {winner}"]
    forced = False
    if signals["S6"].fired:
        winner, forced = "advanced", True
        reasoning.append("OVERRIDE: explicit multi-agent (S6) → force Advanced review")
    if len(tools) >= 4:
        winner, forced = "advanced", True
        reasoning.append(f"OVERRIDE: {len(tools)} tools (≥4) → force Advanced review")
    if not signals["S1"].fired and not signals["S2"].fired and not signals["S3"].fired and not forced:
        winner = "minimal"
        reasoning.append("OVERRIDE: no S1/S2/S3 → default lowest sufficient (Minimal)")

    floor_note: str | None = None
    if signals["S1"].fired and TIERS.index(winner) < TIERS.index("standardized") and not forced:
        winner = "standardized"
        floor_note = ("CAPABILITY FLOOR: retrieval need (S1) requires RAG, which Minimal "
                      "cannot do → floored to Standardized")
        reasoning.append(floor_note)

    return Classification(
        proposed_tier=winner, signals=signals, scores=scores,
        reasoning=reasoning, forced=forced, capability_floor_note=floor_note,
    )


# ---- Stage 3b: write detection (advisory-only guardrail) --------------------

def detect_write_actions(intent: NormalizedIntent) -> WriteDetection:
    text = intent.objective.lower()
    tools = intent.tool_names()

    flagged = sorted({
        t for t in tools
        if any(f in t.lower() for f in _WRITE_TOOL_FRAGMENTS)
        or any(v in t.lower() for v in _WRITE_VERBS)
    })

    write_intents: list[dict] = []
    for verb in _WRITE_VERBS:
        m = re.search(rf"\b{verb}\w*\b", text)
        if not m:
            continue
        before = text[max(0, m.start() - 20):m.start()]
        after = text[m.start():m.start() + 40]
        advisory = any(f in before for f in _ADVISORY_FRAMES)
        has_object = any(n in after for n in _OBJECT_NOUNS)
        if not advisory and has_object:
            write_intents.append({
                "phrase": m.group(0), "verb": verb,
                "note": f'Write phrasing "{m.group(0)}" paired with an object noun — advisory-only enforced.',
            })

    # the declared expectation is itself a write signal — no NLU guessing needed
    if intent.write_actions_expected and not write_intents:
        write_intents.append({
            "phrase": "(declared)", "verb": "(declared)",
            "note": "risk_governance.write_actions_expected=true — advisory-only enforced this phase.",
        })

    any_write = bool(flagged or write_intents)
    return WriteDetection(
        flagged_tools=flagged,
        write_intents=write_intents,
        risk_floor="high" if any_write else None,
    )


# ---- risk inference ---------------------------------------------------------

def _max_risk(a: str, b: str) -> str:
    return a if RISK_ORDER.index(a) >= RISK_ORDER.index(b) else b


def infer_risk(intent: NormalizedIntent, write: WriteDetection) -> RiskResult:
    text = " ".join([
        intent.objective.lower(),
        " ".join(intent.data_sources).lower(),
        intent.data_sensitivity.lower(),
        intent.compliance_notes.lower(),
    ])

    if any(c in text for c in _RESTRICTED_CUES):
        tier, why = "restricted", "financial / regulated / cross-border data cues"
    elif any(c in text for c in _HIGH_CUES):
        tier, why = "high", "customer / PII / confidential cues"
    elif intent.data_sources:
        tier, why = "medium", "internal data sources present"
    else:
        tier, why = "low", "no data sources; advisory-only"

    if intent.data_sensitivity == "restricted":
        tier = _max_risk(tier, "restricted")
    elif intent.data_sensitivity == "confidential":
        tier = _max_risk(tier, "high")

    if write.risk_floor:
        floored = _max_risk(tier, write.risk_floor)
        if floored != tier:
            why = f"{why}; write intent detected → risk floor {write.risk_floor}"
        tier = floored

    return RiskResult(risk_tier=tier, why=why)


# ---- architecture selection + graph synthesis -------------------------------

_PATTERN_LIBRARY: list[tuple[re.Pattern[str], list[dict]]] = [
    (re.compile(r"\b(incident|outage|triage)\b"), [
        {"name": "log_analyzer", "role": "Analyze logs and telemetry.", "tools": []},
        {"name": "impact_assessor", "role": "Assess customer/service impact.", "tools": []},
        {"name": "comms_drafter", "role": "Draft incident communications (advisory).", "tools": []},
        {"name": "notification_router", "role": "Recommend recipients; route for human sign-off.", "tools": []},
    ]),
    (re.compile(r"\b(filing|regulat|compliance)\b"), [
        {"name": "filing_researcher", "role": "Research filing requirements.", "tools": []},
        {"name": "compliance_checker", "role": "Validate draft vs. rules.", "tools": []},
        {"name": "filing_drafter", "role": "Draft the submission (advisory).", "tools": []},
        {"name": "submission_router", "role": "Route for human filing.", "tools": []},
    ]),
]


def _decompose_sub_agents(intent: NormalizedIntent, nlu: Nlu) -> list[dict]:
    text = intent.objective.lower()
    for pattern, subs in _PATTERN_LIBRARY:
        if pattern.search(text):
            return [dict(s) for s in subs]
    verbs = nlu.action_verbs[:4]
    if not verbs:
        return [{"name": "worker", "role": "Perform the task.", "tools": []}]
    return [{"name": f"{v}_agent", "role": f'Handle the "{v}" step.', "tools": []} for v in verbs]


def _infer_pattern(objective: str) -> str:
    t = objective.lower()
    if re.search(r"(in parallel|simultaneous|concurrent|at the same time)", t):
        return "parallel"
    if re.search(r"( then |steps? |stage|first .* then|after that|sequential)", t):
        return "pipeline"
    return "hub"


def _pick_kind(intent: NormalizedIntent, cls: Classification) -> tuple[str, list[str]]:
    if cls.proposed_tier == "advanced":
        if _infer_pattern(intent.objective) == "pipeline":
            return "sequential_pipeline", ["Advanced tier with sequential/staged language → sequential pipeline."]
        forced = " (multi-agent forced by S6 / ≥4 tools)" if cls.forced else ""
        return "hub_and_spoke", [f"Advanced tier{forced} → hub & spoke coordinator."]
    if cls.proposed_tier != "minimal":
        return "graph", ["Retrieval-grounded (Standardized) → explicit retrieve→generate graph."]
    return "single", ["Single skill, no retrieval or multi-agent signals → single agent."]


def synthesize_graph(kind: str, sub_agents: list[dict], rag: bool) -> GraphSpec | None:
    if kind == "single":
        return None
    if kind == "sequential_pipeline":
        nodes = [{"id": s["name"], "kind": "llm", "label": s["role"], "sub_agent": s["name"]} for s in sub_agents]
        edges = [{"from": nodes[i]["id"], "to": nodes[i + 1]["id"]} for i in range(len(nodes) - 1)]
        return GraphSpec(nodes=nodes, edges=edges)
    if kind == "hub_and_spoke":
        nodes = [{"id": "coordinator", "kind": "route", "label": "Coordinator (routes + aggregates)"}]
        edges: list[dict] = []
        for s in sub_agents:
            nodes.append({"id": s["name"], "kind": "llm", "label": s["role"], "sub_agent": s["name"]})
            edges.append({"from": "coordinator", "to": s["name"], "when": f"route:{s['name']}"})
            edges.append({"from": s["name"], "to": "coordinator"})
        return GraphSpec(nodes=nodes, edges=edges)
    if kind == "graph":
        if rag:
            return GraphSpec(
                nodes=[
                    {"id": "retrieve", "kind": "retrieve", "label": "Retrieve grounding context"},
                    {"id": "generate", "kind": "llm", "label": "Generate grounded answer"},
                ],
                edges=[{"from": "retrieve", "to": "generate"}],
            )
        return GraphSpec(
            nodes=[
                {"id": "agent", "kind": "llm", "label": "Agent"},
                {"id": "tools", "kind": "tool", "label": "Advisory tools"},
            ],
            edges=[{"from": "agent", "to": "tools", "when": "tool_calls"}, {"from": "tools", "to": "agent"}],
        )
    return None


# ---- workflow-DAG sketch (Pass 5 vocabulary) --------------------------------

def synthesize_flow(intent: NormalizedIntent, kind: str, sub_agents: list[dict],
                    rag: bool, risk_tier: str) -> dict:
    """Deterministic starting draft for the Builder canvas. Node ids stable,
    types drawn ONLY from NODE_TYPES; Guardrail auto-inserted before output for
    High/Restricted (spec §3.5)."""
    nodes: list[dict] = []
    edges: list[dict] = []

    def add(node_id: str, node_type: str, label: str, config: dict | None = None) -> str:
        nodes.append({"id": node_id, "type": node_type, "label": label, "config": config or {}})
        return node_id

    def link(a: str, b: str, when: str | None = None) -> None:
        edges.append({"from": a, "to": b, **({"when": when} if when else {})})

    if rag:
        add("retrieve_context", "rag", "Retrieve grounding context",
            {"described_need": "knowledge base from declared data sources", "sources": intent.data_sources})

    if kind == "sequential_pipeline" and sub_agents:
        prev = "retrieve_context" if rag else None
        for s in sub_agents:
            nid = add(f"llm_{s['name']}", "llm", s["role"], {"sub_agent": s["name"]})
            if prev:
                link(prev, nid)
            prev = nid
        tail = prev
    elif kind == "hub_and_spoke" and sub_agents:
        hub = add("coordinator", "llm", "Coordinator: route and aggregate", {"router": True})
        if rag:
            link("retrieve_context", hub)
        agg = add("aggregate", "llm", "Aggregate spoke outputs", {})
        for s in sub_agents:
            nid = add(f"llm_{s['name']}", "llm", s["role"], {"sub_agent": s["name"]})
            link(hub, nid, when=f"route:{s['name']}")
            link(nid, agg)
        tail = agg
    else:
        main = add("generate", "llm", "Generate the response", {})
        if rag:
            link("retrieve_context", main)
        tail = main

    # declared tool needs surface as tool_call nodes marked unresolved — the
    # registries are the closed world; nothing is invented on their behalf
    for t in intent.tools_required:
        name = str(t.get("name") or "tool")
        nid = add(f"tool_{re.sub(r'[^a-z0-9]+', '_', name.lower())}", "tool_call",
                  f"Tool: {name} (described need — not yet in registry)",
                  {"described_need": t.get("purpose") or name, "unresolved_reference": True})
        link(tail, nid, when="tool_needed")
        link(nid, tail)

    if intent.human_approval_requirement != "none":
        ha = add("human_approval", "human_approval",
                 f"Human approval ({intent.human_approval_requirement})",
                 {"requirement": intent.human_approval_requirement})
        link(tail, ha)
        tail = ha

    if risk_tier in ("high", "restricted"):
        g = add("guardrail_output", "guardrail", "Output guardrail (fails closed)",
                {"auto_inserted": True, "reason": f"{risk_tier} risk tier (spec §3.5)"})
        link(tail, g)
        tail = g

    out = add("format_output", "output_format",
              f"Format output ({intent.output_format})", {"format": intent.output_format})
    link(tail, out)

    return {"nodes": nodes, "edges": edges}


# ---- validators -------------------------------------------------------------

def disconnected_nodes(node_ids: list[str], edge_pairs: list[tuple[str, str]]) -> list[str]:
    """Nodes not wired into the same component as the rest of the flow.

    The property that matters is weak connectivity, not directed reachability
    from a chosen entry. An earlier version walked forward from `nodes[0]` —
    array position, i.e. the order someone happened to drop nodes on the
    canvas — which rejected correctly-wired graphs whose first array element
    sat late in the chain, even though the runner (which sorts topologically)
    executes them fine. Multiple entry nodes are legal here: two sources
    feeding one join is a normal shape.
    """
    if not node_ids:
        return []
    undirected: dict[str, set[str]] = {nid: set() for nid in node_ids}
    for src, dst in edge_pairs:
        if src in undirected and dst in undirected:
            undirected[src].add(dst)
            undirected[dst].add(src)
    seen: set[str] = set()
    stack = [node_ids[0]]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        stack.extend(undirected[nid])
    return [nid for nid in node_ids if nid not in seen]


def validate_graph(graph: GraphSpec) -> list[str]:
    v: list[str] = []
    if not graph.nodes:
        return ["Graph has no nodes."]
    ids: set[str] = set()
    for n in graph.nodes:
        if n["id"] in ids:
            v.append(f'Duplicate graph node id "{n["id"]}".')
        ids.add(n["id"])
    adj: dict[str, list[str]] = {n["id"]: [] for n in graph.nodes}
    for e in graph.edges:
        if e["from"] not in ids:
            v.append(f'Edge references missing node "{e["from"]}".')
        if e["to"] not in ids:
            v.append(f'Edge references missing node "{e["to"]}".')
        if e["from"] in ids and e["to"] in ids:
            adj[e["from"]].append(e["to"])
    for nid in disconnected_nodes([n["id"] for n in graph.nodes],
                                  [(e["from"], e["to"]) for e in graph.edges]):
        v.append(f'Node "{nid}" is not connected to the rest of the graph.')
    return v


def validate_flow(flow: dict, risk_tier: str) -> list[str]:
    """Workflow-DAG sketch validation: vocabulary, integrity, reachability,
    Guardrail-before-output for High/Restricted."""
    v: list[str] = []
    nodes = flow.get("nodes") or []
    edges = flow.get("edges") or []
    if not nodes:
        return ["Flow has no nodes."]
    ids: set[str] = set()
    for n in nodes:
        if n.get("type") not in NODE_TYPES:
            v.append(f'Node "{n.get("id")}" has unknown type "{n.get("type")}" (not in the platform vocabulary).')
        if n.get("id") in ids:
            v.append(f'Duplicate flow node id "{n.get("id")}".')
        ids.add(n.get("id"))
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes if n.get("id")}
    for e in edges:
        if e.get("from") not in ids:
            v.append(f'Flow edge references missing node "{e.get("from")}".')
        if e.get("to") not in ids:
            v.append(f'Flow edge references missing node "{e.get("to")}".')
        if e.get("from") in ids and e.get("to") in ids:
            adj[e["from"]].append(e["to"])
    edge_pairs = [(e["from"], e["to"]) for e in edges
                  if e.get("from") in ids and e.get("to") in ids]
    for nid in disconnected_nodes([n["id"] for n in nodes if n.get("id")], edge_pairs):
        v.append(f'Flow node "{nid}" is not connected to the flow — '
                 "join it with an edge or delete it.")

    if risk_tier in ("high", "restricted"):
        by_id = {n["id"]: n for n in nodes}
        outputs = [n for n in nodes if n.get("type") == "output_format"]
        for out in outputs:
            feeders = [e["from"] for e in edges if e.get("to") == out["id"]]
            if not any(by_id.get(f, {}).get("type") == "guardrail" for f in feeders):
                v.append(
                    f'{risk_tier} risk requires a guardrail node immediately before output "{out["id"]}" (spec §3.5).'
                )
    return v


def validate_architecture(rec: Recommendation, cls: Classification) -> list[str]:
    v: list[str] = []
    if rec.architecture not in ARCHITECTURES:
        v.append(f'Unknown architecture "{rec.architecture}" (not in the generatable subset).')
    if cls.forced and rec.architecture == "single":
        v.append('Explicit multi-agent (S6) or ≥4 tools forces a multi-agent architecture; "single" is not allowed.')
    for sa in rec.sub_agents:
        if len(sa.get("tools") or []) > 3:
            v.append(f'Sub-agent "{sa.get("name")}" binds {len(sa["tools"])} tools (>3).')
        # Increment B closed world: the tool registry is empty by construction,
        # so ANY bound tool is an unknown reference (Increment C wires resolution)
        for t in sa.get("tools") or []:
            v.append(f'Sub-agent "{sa.get("name")}" binds unknown tool "{t}" (not in registry).')
    if rec.graph:
        v.extend(validate_graph(rec.graph))
    return v


# ---- top-level --------------------------------------------------------------

def run(intent: NormalizedIntent) -> dict:
    """Full deterministic pass. Returns a JSON-serializable trace + baseline
    recommendation — always computed, stored on every DesignRecommendation."""
    nlu = detect_nlu(intent)
    cls = classify(intent, nlu)
    write = detect_write_actions(intent)
    risk = infer_risk(intent, write)

    kind, rationale = _pick_kind(intent, cls)
    multi = kind in ("sequential_pipeline", "hub_and_spoke")
    sub_agents = _decompose_sub_agents(intent, nlu) if multi else []
    rag = cls.proposed_tier != "minimal"
    graph = synthesize_graph(kind, sub_agents, rag)
    flow = synthesize_flow(intent, kind, sub_agents, rag, risk.risk_tier)

    rec = Recommendation(
        architecture=kind, sub_agents=sub_agents, graph=graph, flow=flow,
        rationale=rationale,
        confidence="high" if (cls.forced and multi) else "medium",
        source="deterministic",
    )
    violations = validate_architecture(rec, cls) + validate_flow(flow, risk.risk_tier)

    return {
        "rules_version": RULES_VERSION,
        "nlu": asdict(nlu),
        "classification": {
            "proposed_tier": cls.proposed_tier,
            "signals": {k: asdict(s) for k, s in cls.signals.items()},
            "scores": cls.scores,
            "reasoning": cls.reasoning,
            "forced": cls.forced,
            "capability_floor_note": cls.capability_floor_note,
        },
        "write_detection": asdict(write),
        "risk": asdict(risk),
        "recommendation": {
            "architecture": rec.architecture,
            "sub_agents": rec.sub_agents,
            "graph": asdict(rec.graph) if rec.graph else None,
            "flow": rec.flow,
            "rationale": rec.rationale,
            "confidence": rec.confidence,
            "source": rec.source,
        },
        "violations": violations,
    }
