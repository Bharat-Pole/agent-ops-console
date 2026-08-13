"""Conditional branching: drawn edges now route execution.

Before this, the engine compiled any graph to START → n0 → n1 → … → END in
topological order, so edges only implied an ORDER. A branching graph rendered
correctly and ran as a straight line through every node.

The tests that matter here are the ones asserting a branch NOT taken: it is
easy to make both arms run and call it success.
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
        "name": name, "prompt_type": "system", "content": "Be terse."}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    version = client.get(f"/api/prompts/{pack['id']}").json()["versions"][0]
    _decide_pending(client, version["id"])
    return pack


def _branching_graph(pack_slug: str) -> dict:
    """gen → (llm_output contains 'escalate') ? escalate_out : normal_out"""
    return {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack_slug}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "escalate_out", "type": "output_format", "label": "",
             "config": {"format": "text"}},
            {"id": "normal_out", "type": "output_format", "label": "",
             "config": {"format": "text"}},
        ],
        "edges": [
            {"from": "sys", "to": "gen"},
            {"from": "gen", "to": "escalate_out",
             "condition": {"field": "llm_output", "op": "contains", "value": "escalate"}},
            {"from": "gen", "to": "normal_out"},          # default
        ],
    }


def _validate(client, agent_id: str, graph: dict, name: str) -> dict:
    login(client, "admin@platform.local")
    wf = client.post(f"/api/agents/{agent_id}/workflows",
                     json={"name": name, "graph": graph}).json()
    return client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json(), wf


def _activate(client, wf: dict) -> None:
    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    _decide_pending(client, wf["versions"][0]["id"])
    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/activate")


def _run(client, agent_id: str, text: str) -> dict:
    login(client, "admin@platform.local")
    return client.post(f"/api/agents/{agent_id}/runs", json={"input": text}).json()


# ---- routing -----------------------------------------------------------------

@pytest.mark.parametrize("reply,expected,not_expected", [
    ("please escalate this now", "escalate_out", "normal_out"),
    ("all fine here", "normal_out", "escalate_out"),
])
def test_a_branch_routes_to_exactly_one_arm(client, reply, expected, not_expected):
    pack = _approved_prompt(client, f"Branch Prompt {expected}")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": f"Branch Agent {expected}"}).json()
    validated, wf = _validate(client, agent["id"], _branching_graph(pack["slug"]), "branch-wf")
    assert validated["status"] == "validated", validated["validation"]
    _activate(client, wf)

    adapters.set_adapter_override(adapters.FakeModelAdapter(responses=[reply]))
    run = _run(client, agent["id"], "hello")

    assert run["status"] == "completed", run
    visited = {s["node_id"] for s in run["steps"]}
    assert expected in visited
    assert not_expected not in visited, "the branch not taken must not execute"


def test_the_default_edge_is_taken_when_no_condition_matches(client):
    pack = _approved_prompt(client, "Branch Default Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Branch Default Agent"}).json()
    validated, wf = _validate(client, agent["id"], _branching_graph(pack["slug"]), "default-wf")
    assert validated["status"] == "validated"
    _activate(client, wf)

    adapters.set_adapter_override(adapters.FakeModelAdapter(responses=[""]))
    run = _run(client, agent["id"], "hello")
    assert run["status"] == "completed", run
    assert "normal_out" in {s["node_id"] for s in run["steps"]}


def test_the_routing_decision_is_recorded_in_the_trace(client):
    """Which way a run branched, and why, has to be inspectable afterwards."""
    pack = _approved_prompt(client, "Branch Trace Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Branch Trace Agent"}).json()
    validated, wf = _validate(client, agent["id"], _branching_graph(pack["slug"]), "trace-wf")
    assert validated["status"] == "validated"
    _activate(client, wf)

    adapters.set_adapter_override(adapters.FakeModelAdapter(responses=["escalate please"]))
    run = _run(client, agent["id"], "hello")

    edges = [s for s in run["steps"] if s["node_type"] == "edge"]
    assert edges, "a routing decision should appear in the trace"
    assert edges[0]["detail"]["routed_to"] == "escalate_out"
    assert "llm_output contains" in edges[0]["detail"]["matched"]


# ---- validation guards -------------------------------------------------------

def test_a_branch_without_a_default_is_rejected(client):
    """No else = a run can dead-end silently. Refuse at design time."""
    pack = _approved_prompt(client, "No Default Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "No Default Agent"}).json()
    graph = _branching_graph(pack["slug"])
    graph["edges"][2]["condition"] = {"field": "llm_output", "op": "contains", "value": "calm"}
    validated, _ = _validate(client, agent["id"], graph, "no-default-wf")
    assert validated["status"] != "validated"
    assert any("no default edge" in v for v in validated["validation"]["violations"])


def test_ambiguous_unconditional_edges_are_rejected(client):
    pack = _approved_prompt(client, "Ambiguous Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Ambiguous Agent"}).json()
    graph = _branching_graph(pack["slug"])
    del graph["edges"][1]["condition"]           # two unconditional edges out of gen
    validated, _ = _validate(client, agent["id"], graph, "ambiguous-wf")
    assert validated["status"] != "validated"
    assert any("no conditions" in v for v in validated["validation"]["violations"])


def test_a_malformed_condition_is_rejected_with_the_edge_named(client):
    pack = _approved_prompt(client, "Bad Condition Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Bad Condition Agent"}).json()
    graph = _branching_graph(pack["slug"])
    graph["edges"][1]["condition"] = {"field": "os.environ", "op": "eq", "value": "x"}
    validated, _ = _validate(client, agent["id"], graph, "bad-condition-wf")
    assert validated["status"] != "validated"
    assert any("gen → escalate_out" in v for v in validated["validation"]["violations"])


def test_a_recommender_annotation_warns_rather_than_pretending_to_route(client):
    """`when` is the recommendation's note about intent; `condition` executes.

    Hub-and-spoke recommendations emit when="route:<spoke>". That must not be
    mistaken for a working branch — nor rejected outright, since it is exactly
    the intent the author wants to make executable.
    """
    pack = _approved_prompt(client, "Annotation Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Annotation Agent"}).json()
    graph = _branching_graph(pack["slug"])
    del graph["edges"][1]["condition"]
    graph["edges"][1]["when"] = "route:escalation"

    validated, _ = _validate(client, agent["id"], graph, "annotation-wf")
    warnings = validated["validation"]["warnings"]
    assert any("route:escalation" in w and "no executable `condition`" in w for w in warnings), warnings


def test_cycles_are_now_rejected_rather_than_silently_dropped(client):
    """Edges route execution now, so a back-edge would loop without bound."""
    pack = _approved_prompt(client, "Cycle Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Cycle Agent"}).json()
    graph = _branching_graph(pack["slug"])
    graph["edges"].append({"from": "normal_out", "to": "gen"})
    validated, _ = _validate(client, agent["id"], graph, "cycle-wf")
    assert validated["status"] != "validated"
    assert any("loop without bound" in v for v in validated["validation"]["violations"])


# ---- guardrail coverage on every path ----------------------------------------
#
# ensure_guardrail already inserts a guardrail before EVERY output node and
# rewires incoming edges (verified in test_guardrail_autoinsert_covers_...),
# so in practice a bypass should never survive to this check. It is asserted
# directly because "a guardrail exists somewhere" stopped being proof the
# moment execution could take more than one path — and defence in depth is
# only worth having if it is tested.

def _coverage_violations(graph: dict, risk: str) -> list[str]:
    from app.engine.validation import ValidationOutcome, _check_branching
    outcome = ValidationOutcome(graph=graph)
    _check_branching(graph, risk, outcome)
    return [v for v in outcome.violations if "without passing a guardrail" in v]


def _bypass_graph() -> dict:
    """One arm guarded, the other wired straight to its own output."""
    return {
        "nodes": [
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "guard", "type": "guardrail", "label": "", "config": {}},
            {"id": "safe_out", "type": "output_format", "label": "", "config": {}},
            {"id": "raw_out", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [
            {"from": "gen", "to": "guard",
             "condition": {"field": "llm_output", "op": "is_not_empty"}},
            {"from": "gen", "to": "raw_out"},
            {"from": "guard", "to": "safe_out"},
        ],
    }


@pytest.mark.parametrize("risk", ["high", "restricted"])
def test_an_ungoverned_path_to_output_is_caught(risk):
    violations = _coverage_violations(_bypass_graph(), risk)
    assert violations, "a path reaching output without a guardrail must be refused"
    assert "raw_out" in violations[0]


def test_the_guarded_arm_is_not_flagged():
    violations = _coverage_violations(_bypass_graph(), "high")
    assert not any("safe_out" in v for v in violations)


@pytest.mark.parametrize("risk", ["low", "medium"])
def test_lower_tiers_do_not_require_guardrail_coverage(risk):
    assert _coverage_violations(_bypass_graph(), risk) == []


def test_guardrail_autoinsert_covers_every_arm_of_a_branch():
    """The primary mechanism: auto-insert guards both arms and keeps the
    condition on the rewired edge, so branching cannot smuggle output past it."""
    from app.recommender.engine import ensure_guardrail
    graph = {
        "nodes": [
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "a_out", "type": "output_format", "label": "", "config": {}},
            {"id": "b_out", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [
            {"from": "gen", "to": "a_out",
             "condition": {"field": "llm_output", "op": "contains", "value": "x"}},
            {"from": "gen", "to": "b_out"},
        ],
    }
    adjusted, adjustments = ensure_guardrail(graph, "high")
    assert len(adjustments) == 2, adjustments
    assert _coverage_violations(adjusted, "high") == []
    # the branch condition must survive the rewiring, or routing silently changes
    rerouted = [e for e in adjusted["edges"] if e.get("condition")]
    assert len(rerouted) == 1 and rerouted[0]["to"].startswith("guardrail_")


def test_linear_workflows_are_unaffected(client):
    """No conditions anywhere = the behaviour that already worked."""
    pack = _approved_prompt(client, "Linear Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Linear Agent"}).json()
    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack["slug"]}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "out"}],
    }
    validated, wf = _validate(client, agent["id"], graph, "linear-wf")
    assert validated["status"] == "validated", validated["validation"]
    _activate(client, wf)

    adapters.set_adapter_override(adapters.FakeModelAdapter(responses=["answer"]))
    run = _run(client, agent["id"], "hello")
    assert run["status"] == "completed", run
    assert {s["node_id"] for s in run["steps"] if s["node_type"] != "edge"} == {"sys", "gen", "out"}
