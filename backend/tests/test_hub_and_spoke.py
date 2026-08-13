"""What the hub-and-spoke shape can and cannot do after the branching increment.

The honest boundary: a hub can ROUTE to one spoke on a declarative condition,
and paths can reconverge on a shared output. It cannot loop back to the hub,
cannot visit a second spoke, and cannot let the model pick the spoke by calling
a function — that needs tool-calling in the adapter and an iteration cap.
"""
from __future__ import annotations

import pytest
from conftest import login

from app.adapters import models as adapters


@pytest.fixture(autouse=True)
def _clear_adapter():
    yield
    adapters.set_adapter_override(None)


def _decide_pending(client, resource_id: str) -> dict:
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_id"] == resource_id and a["status"] == "pending"][0]
    return client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True}).json()


def _approved_prompt(client, name: str) -> dict:
    login(client, "admin@platform.local")
    pack = client.post("/api/prompts", json={
        "name": name, "prompt_type": "system", "content": "Route the request."}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    version = client.get(f"/api/prompts/{pack['id']}").json()["versions"][0]
    _decide_pending(client, version["id"])
    return pack


def _hub_graph(pack_slug: str) -> dict:
    """hub (llm) routes to one of two spokes; both reconverge on one output."""
    return {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack_slug}},
            {"id": "hub", "type": "llm", "label": "", "config": {}},
            {"id": "spoke_refund", "type": "llm", "label": "", "config": {}},
            {"id": "spoke_status", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
        ],
        "edges": [
            {"from": "sys", "to": "hub"},
            {"from": "hub", "to": "spoke_refund",
             "condition": {"field": "llm_output", "op": "contains", "value": "refund"}},
            {"from": "hub", "to": "spoke_status"},          # default spoke
            {"from": "spoke_refund", "to": "out"},
            {"from": "spoke_status", "to": "out"},          # reconvergence
        ],
    }


def _build(client, name: str, graph: dict):
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": name}).json()
    wf = client.post(f"/api/agents/{agent['id']}/workflows",
                     json={"name": f"{name}-wf", "graph": graph}).json()
    validated = client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json()
    return agent, wf, validated


def _activate_and_run(client, agent, wf, replies: list[str]) -> dict:
    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    _decide_pending(client, wf["versions"][0]["id"])
    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/activate")
    adapters.set_adapter_override(adapters.FakeModelAdapter(responses=replies))
    login(client, "admin@platform.local")
    return client.post(f"/api/agents/{agent['id']}/runs", json={"input": "hello"}).json()


# ---- what DOES work ----------------------------------------------------------

def test_a_hub_routes_to_one_spoke_and_paths_reconverge(client):
    pack = _approved_prompt(client, "Hub Prompt A")
    agent, wf, validated = _build(client, "Hub Agent A", _hub_graph(pack["slug"]))
    assert validated["status"] == "validated", validated["validation"]

    run = _activate_and_run(client, agent, wf, ["please issue a refund", "refund handled"])
    assert run["status"] == "completed", run

    visited = [s["node_id"] for s in run["steps"] if s["node_type"] != "edge"]
    assert "spoke_refund" in visited
    assert "spoke_status" not in visited, "only the matched spoke runs"
    assert visited.count("out") == 1, "reconvergence must not run output twice"


def test_the_default_spoke_takes_unmatched_requests(client):
    pack = _approved_prompt(client, "Hub Prompt B")
    agent, wf, validated = _build(client, "Hub Agent B", _hub_graph(pack["slug"]))
    assert validated["status"] == "validated"

    run = _activate_and_run(client, agent, wf, ["where is my order", "status given"])
    assert run["status"] == "completed", run
    visited = {s["node_id"] for s in run["steps"]}
    assert "spoke_status" in visited and "spoke_refund" not in visited


# ---- what does NOT work ------------------------------------------------------

def test_returning_to_the_hub_is_refused(client):
    """The loop half of hub-and-spoke: spoke → hub → another spoke."""
    pack = _approved_prompt(client, "Hub Prompt C")
    graph = _hub_graph(pack["slug"])
    graph["edges"].append({"from": "spoke_refund", "to": "hub"})
    _, _, validated = _build(client, "Hub Agent C", graph)

    assert validated["status"] != "validated"
    assert any("loop without bound" in v for v in validated["validation"]["violations"])


def test_a_spoke_cannot_be_visited_twice_in_one_run(client):
    """Each node executes at most once; there is no iteration construct."""
    pack = _approved_prompt(client, "Hub Prompt D")
    agent, wf, validated = _build(client, "Hub Agent D", _hub_graph(pack["slug"]))
    assert validated["status"] == "validated"

    run = _activate_and_run(client, agent, wf, ["refund refund refund", "done"])
    counts: dict[str, int] = {}
    for step in run["steps"]:
        if step["node_type"] != "edge":
            counts[step["node_id"]] = counts.get(step["node_id"], 0) + 1
    assert all(c == 1 for c in counts.values()), counts


def test_routing_reads_state_not_a_model_tool_choice(client):
    """Branching is DECLARATIVE: it matches state the model produced, it does
    not let the model name the next node. Function-calling is the missing
    piece, and this test documents which mechanism is actually in play."""
    from app.engine import conditions
    assert "next_node" not in conditions.CONDITION_ROOTS
    assert "tool_choice" not in conditions.CONDITION_ROOTS
    # only EngineState is readable — the model influences routing solely by
    # what it writes into llm_output
    assert "llm_output" in conditions.CONDITION_ROOTS
