"""Explicit orchestration.graph → DAG rendering (generator + live runtime)."""
import json
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent_forge import generate, load_agent
from agent_forge.runtime import run_agent, build_live_graph
from agent_forge.graphplan import plan_dag_graph

FIX = Path(__file__).parent / "fixtures"


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def bind_tools(self, tools, **kwargs):
        return self


def _with_graph(fixture: str, spec: dict, bound_tools=None) -> dict:
    rec = json.loads((FIX / fixture).read_text(encoding="utf-8"))
    rec["config"]["orchestration"]["graph"] = {"value": spec, "value_source": "inferred",
                                               "verified_flag": False, "confidence": "low", "gap_note": None}
    rec["config"]["orchestration"]["orchestration_type"]["value"] = "router"
    if bound_tools is not None:
        rec["config"]["tooling"]["bound_tools"]["value"] = bound_tools
    return rec


RAG_GRAPH = {
    "nodes": [{"id": "retrieve", "kind": "retrieve", "label": "Retrieve"},
              {"id": "generate", "kind": "llm", "label": "Generate"}],
    "edges": [{"from": "retrieve", "to": "generate"}],
}
ROUTER_GRAPH = {
    "nodes": [{"id": "agent", "kind": "llm", "label": "Agent"},
              {"id": "tools", "kind": "tool", "label": "Tools"}],
    "edges": [{"from": "agent", "to": "tools", "when": "tool_calls"},
              {"from": "tools", "to": "agent"}],
}


def _compiles(src: str):
    compile(src, "graph.py", "exec")  # syntax check on the generated module


def test_explicit_rag_graph_rendered():
    res = generate(_with_graph("noc_incident_summarizer.json", RAG_GRAPH))
    assert res.topology.value == "dag"
    g = res.files[f"src/{res.agent.pkg}/graph.py"]
    _compiles(g)
    assert 'explicit orchestration.graph' in g
    assert 'g.add_edge(START, "retrieve")' in g
    assert 'g.add_node("retrieve", _retrieve)' in g
    assert 'g.add_node("generate", _llm)' in g
    assert 'g.add_edge("retrieve", "generate")' in g
    assert 'g.add_edge("generate", END)' in g       # generate is terminal
    # no tool node in this spec → llm node does not bind tools
    assert "ToolNode(" not in g


def test_explicit_router_graph_conditional_edges():
    res = generate(_with_graph("hr_policy_bot.json", ROUTER_GRAPH, bound_tools=["tools://incident_reader@v1"]))
    assert res.topology.value == "dag"
    g = res.files[f"src/{res.agent.pkg}/graph.py"]
    _compiles(g)
    assert 'g.add_edge(START, "agent")' in g
    assert 'g.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})' in g
    assert 'g.add_edge("tools", "agent")' in g
    assert 'ToolNode(ADVISORY_TOOLS)' in g


def test_tool_node_dropped_when_no_tools():
    # router graph but the agent has zero advisory tools → tool node dropped, agent → END
    res = generate(_with_graph("hr_policy_bot.json", ROUTER_GRAPH, bound_tools=[]))
    g = res.files[f"src/{res.agent.pkg}/graph.py"]
    _compiles(g)
    assert 'g.add_node("tools"' not in g
    assert 'g.add_edge("agent", END)' in g


def test_explicit_graph_determinism_bytes():
    rec = _with_graph("noc_incident_summarizer.json", RAG_GRAPH)
    a, b = generate(rec), generate(rec)
    assert a.files == b.files and a.zip_bytes() == b.zip_bytes()


def test_expected_nodes_follow_spec():
    # loader threaded the graph; expected nodes follow the spec order
    ir = load_agent(_with_graph("noc_incident_summarizer.json", RAG_GRAPH))
    assert ir.graph is not None and [n.id for n in ir.graph.nodes] == ["retrieve", "generate"]
    res = generate(_with_graph("noc_incident_summarizer.json", RAG_GRAPH))
    tc = res.files["tests/test_compiles.py"]
    assert "retrieve" in tc and "generate" in tc


def test_runtime_builds_explicit_graph_with_fake():
    rec = _with_graph("noc_incident_summarizer.json", RAG_GRAPH)
    g = build_live_graph(rec, model=FakeChatModel())
    nodes = set(g.get_graph().nodes)
    assert {"retrieve", "generate"}.issubset(nodes)
    out = run_agent(rec, "summarize incidents", thread_id="tg", model=FakeChatModel())
    assert out["trace"]["topology"] == "dag"
    assert isinstance(out["reply"], str) and out["reply"]


def test_graphplan_drops_tool_without_tools():
    ir = load_agent(_with_graph("hr_policy_bot.json", ROUTER_GRAPH, bound_tools=[]))
    plan = plan_dag_graph(ir.graph, has_tools=False)
    ids = {nid for nid, _ in plan.nodes}
    assert ids == {"agent"}                 # tool node dropped
    assert plan.terminals == ["agent"]      # agent → END
    assert plan.bind_tools is False
