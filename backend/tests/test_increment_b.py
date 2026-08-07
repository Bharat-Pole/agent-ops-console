"""Increment B acceptance: intent validation + PII flags, the deterministic
recommender (LOCKED rules), and the honesty machinery — basis overlap,
closed-world demotion, risk contradiction, malformed-retry, flow gating.

LLM behavior is tested through the FakeModelAdapter — the explicit, labeled
test harness (Decision 10). Its model_id ("fake:scripted") is asserted ON the
stored record: a fake run is visible, by design.
"""
from __future__ import annotations

import json

import pytest
from conftest import login

from app.adapters import models as adapters
from app.intent import pii as intent_pii
from app.intent import schema as intent_schema
from app.recommender import deterministic, engine as reco_engine


@pytest.fixture(autouse=True)
def _clear_adapter_override():
    yield
    adapters.set_adapter_override(None)


def _fake(*responses: str) -> adapters.FakeModelAdapter:
    fake = adapters.FakeModelAdapter(responses=list(responses))
    adapters.set_adapter_override(fake)
    return fake


# ---- intent validation & PII ------------------------------------------------

def test_validation_hard_rules():
    intent = intent_schema.normalize({
        "identity_purpose": {"objective": "too short"},
        "tools_interaction": {"mcp_connectors_required": True},
        "risk_governance": {"deployment_channel": "rest_api"},
    })
    verdict = intent_schema.validate(intent)
    assert not verdict.ok
    joined = " ".join(verdict.errors)
    assert "min 20 characters" in joined
    assert "mcp_connectors_required" in joined
    assert "expected_volume_per_day" in joined


def test_validation_warnings_do_not_block():
    intent = intent_schema.normalize({
        "identity_purpose": {"objective": "Draft summaries of confidential contract clauses for legal review"},
        "data_rules": {"data_sensitivity": "confidential"},
        "risk_governance": {"write_actions_expected": True, "deployment_channel": "sandbox"},
    })
    verdict = intent_schema.validate(intent)
    assert verdict.ok
    joined = " ".join(verdict.warnings)
    assert "advisory-only" in joined  # phased write doctrine surfaced


def test_prov_envelopes_unwrap():
    intent = intent_schema.normalize({
        "identity_purpose": {"objective": {"value": "Answer HR benefits questions from the employee handbook", "source": "user"}},
        "data_rules": {"data_sources": {"value": ["employee_handbook"], "source": "engine"}},
    })
    assert intent.objective.startswith("Answer HR")
    assert intent.data_sources == ["employee_handbook"]


def test_pii_flags_masked_and_flag_only():
    flags = intent_pii.scan_fields({
        "identity_purpose.objective": "Contact jane.doe@example.com or 555-123-4567; SSN 123-45-6789",
    })
    kinds = {f["kind"] for f in flags}
    assert {"email", "phone", "ssn"} <= kinds
    for f in flags:
        assert "jane.doe@example.com" not in f["preview"]  # masked, never copied out
        assert f["detector"] == "regex-v1"  # labeled heuristic


# ---- deterministic recommender (ported LOCKED rules) ------------------------

def _det(payload: dict) -> dict:
    return deterministic.run(intent_schema.normalize(payload))


def test_minimal_single_agent():
    out = _det({"identity_purpose": {"objective": "Answer employee questions about the PTO policy in a friendly tone"}})
    assert out["classification"]["proposed_tier"] == "minimal"
    assert out["recommendation"]["architecture"] == "single"
    assert out["violations"] == []


def test_retrieval_floors_to_standardized_rag_graph():
    out = _det({
        "identity_purpose": {"objective": "Answer questions grounded in the network runbook documents"},
        "data_rules": {"data_sources": ["network_runbooks"]},
    })
    assert out["classification"]["signals"]["S1"]["fired"] is True
    assert out["classification"]["proposed_tier"] == "standardized"
    assert out["recommendation"]["architecture"] == "graph"
    node_types = [n["type"] for n in out["recommendation"]["flow"]["nodes"]]
    assert "rag" in node_types


def test_multi_agent_language_forces_advanced():
    out = _det({"identity_purpose": {
        "objective": "A coordinator agent orchestrating sub-agents to triage incidents, "
                     "assess impact, and route notifications to the on-call team",
    }})
    cls = out["classification"]
    assert cls["signals"]["S6"]["fired"] is True and cls["forced"] is True
    assert cls["proposed_tier"] == "advanced"
    assert out["recommendation"]["architecture"] in ("hub_and_spoke", "sequential_pipeline")
    assert out["recommendation"]["sub_agents"]  # decomposed


def test_write_intent_raises_risk_floor_and_guardrail_inserted():
    out = _det({
        "identity_purpose": {"objective": "Send outage notification emails to affected customers automatically"},
        "data_rules": {"data_sources": ["outage_db"]},
    })
    assert out["write_detection"]["write_intents"]
    assert out["risk"]["risk_tier"] in ("high", "restricted")
    flow = out["recommendation"]["flow"]
    types = [n["type"] for n in flow["nodes"]]
    assert "guardrail" in types  # auto-inserted before output for high risk
    assert out["violations"] == []  # the sketch itself validates clean


def test_declared_tools_become_unresolved_tool_nodes():
    out = _det({
        "identity_purpose": {"objective": "Check ticket status and summarize open incidents for support leads"},
        "tools_interaction": {"tools_required": [{"name": "ticket_reader", "purpose": "read tickets"}]},
    })
    tool_nodes = [n for n in out["recommendation"]["flow"]["nodes"] if n["type"] == "tool_call"]
    assert tool_nodes and tool_nodes[0]["config"]["unresolved_reference"] is True


def test_entry_point_comes_from_topology_not_array_order():
    """A correctly wired flow must validate no matter what order the nodes
    were added on the canvas — the runner sorts topologically, so a validator
    that trusted array position rejected graphs the engine runs fine."""
    # tool_call listed FIRST but wired LAST: prompt -> llm -> tool -> output
    flow = {
        "nodes": [
            {"id": "tool_1", "type": "tool_call", "label": ""},
            {"id": "prompt_1", "type": "prompt", "label": ""},
            {"id": "llm_1", "type": "llm", "label": ""},
            {"id": "out_1", "type": "output_format", "label": ""},
        ],
        "edges": [{"from": "prompt_1", "to": "llm_1"}, {"from": "llm_1", "to": "tool_1"},
                  {"from": "tool_1", "to": "out_1"}],
    }
    assert deterministic.validate_flow(flow, "low") == []

    # genuinely orphaned nodes are still caught, with an actionable message
    orphaned = {
        "nodes": [
            {"id": "a", "type": "prompt", "label": ""},
            {"id": "b", "type": "llm", "label": ""},
            {"id": "stray", "type": "llm", "label": ""},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    violations = deterministic.validate_flow(orphaned, "low")
    assert len(violations) == 1
    assert "stray" in violations[0] and "not connected" in violations[0]


def test_flow_validator_rejects_unknown_types_and_unreachable():
    violations = deterministic.validate_flow({
        "nodes": [
            {"id": "a", "type": "llm", "label": ""},
            {"id": "b", "type": "teleport", "label": ""},
            {"id": "c", "type": "llm", "label": ""},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }, "low")
    joined = " ".join(violations)
    assert "unknown type" in joined and "not connected" in joined


# ---- engine honesty machinery (FakeModelAdapter — labeled harness) ----------

INTENT_OK = {
    "identity_purpose": {"objective": "Summarize weekly network incident reports for the NOC team with citations"},
    "data_rules": {"data_sources": ["incident_db"], "data_sensitivity": "internal"},
    "risk_governance": {"risk_tier": "medium", "human_approval_requirement": "none",
                        "deployment_channel": "sandbox"},
}


def _llm_json(**overrides) -> str:
    base = {
        "summary": "A grounded summarizer.",
        "architecture": {"kind": "graph",
                         "rationale": "retrieval-grounded summarization",
                         "basis": "summarize weekly network incident reports with citations"},
        "suggested_risk_tier": {"tier": "medium", "basis": "internal incident data, no write actions"},
        "components": [],
        "suggested_agent_flow": None,
        "missing_information": [],
        "clarifying_questions": [],
    }
    base.update(overrides)
    return json.dumps(base)


def test_no_provider_means_labeled_deterministic_baseline():
    adapters.set_adapter_override(None)  # provider resolution → none in tests
    result = reco_engine.generate(INTENT_OK)
    assert result["engine"] == "deterministic"
    assert result["model_id"] is None
    assert result["status"] == "ready"
    assert all(i["verification"] == "deterministic" for i in result["items"])


def test_grounded_vs_fabricated_basis():
    _fake(_llm_json(
        components=[
            {"kind": "knowledge", "name": "incident_kb",
             "purpose": "ground summaries",
             "registry_ref": None,
             "basis": "summarize weekly network incident reports"},
            {"kind": "tool", "name": "crm_updater",
             "purpose": "update CRM records",
             "registry_ref": None,
             "basis": "synchronize customer relationship pipelines quarterly"},  # fabricated
        ],
    ))
    result = reco_engine.generate(INTENT_OK)
    by_id = {i["id"]: i for i in result["items"]}
    kb = next(i for k, i in by_id.items() if "incident-kb" in k)
    fabricated = next(i for k, i in by_id.items() if "crm-updater" in k)
    assert kb["verification"] == "grounded"
    assert fabricated["verification"] == "unverified"
    assert result["model_id"] == "fake:scripted"  # the harness is visible in the record


def test_closed_world_demotes_invented_registry_refs():
    _fake(_llm_json(
        components=[{
            "kind": "tool", "name": "incident_reader",
            "purpose": "read incidents",
            "registry_ref": "tools://incident-reader@v1",  # invented — registry is empty
            "basis": "summarize weekly network incident reports",
        }],
    ))
    result = reco_engine.generate(INTENT_OK)
    item = next(i for i in result["items"] if i["kind"] == "component_tool")
    assert item["state"] == "described_need"
    assert item["detail"]["registry_ref"] is None
    assert result["validation"]["closed_world_demotions"][0]["ref"] == "tools://incident-reader@v1"


def test_risk_contradiction_flagged_never_silently_resolved():
    _fake(_llm_json(suggested_risk_tier={"tier": "low", "basis": "simple summaries"}))
    result = reco_engine.generate(INTENT_OK)  # deterministic says medium (data sources)
    contras = result["validation"]["contradictions"]
    assert contras and contras[0]["field"] == "risk_tier"
    assert contras[0]["llm"] == "low" and contras[0]["deterministic"] == "medium"
    risk_item = next(i for i in result["items"] if i["kind"] == "risk_tier")
    assert risk_item["detail"]["contradiction"] is True


def test_malformed_output_retried_once_then_deterministic():
    fake = _fake("not json at all", _llm_json())
    result = reco_engine.generate(INTENT_OK)
    assert len(fake.calls) == 2  # one corrective retry
    assert result["engine"] == "llm+deterministic"

    fake2 = _fake("still not json", "also { broken")
    result2 = reco_engine.generate(INTENT_OK)
    assert len(fake2.calls) == 2
    assert result2["engine"] == "deterministic"  # honest fallback, error recorded
    assert "MalformedOutput" in result2["validation"]["llm_error"]
    assert result2["status"] == "ready"


def test_invalid_llm_flow_gated_to_deterministic():
    _fake(_llm_json(suggested_agent_flow={
        "nodes": [{"id": "x", "type": "teleport", "label": "bad"}],
        "edges": [],
        "basis": "made up",
    }))
    result = reco_engine.generate(INTENT_OK)
    assert result["validation"]["flow"]["source"] == "deterministic"
    assert result["validation"]["flow"]["violations"]


def test_valid_llm_flow_accepted_with_guardrail_autoinsert():
    high_intent = {
        "identity_purpose": {"objective": "Summarize confidential customer contract disputes for the legal team"},
        "data_rules": {"data_sources": ["contract_db"], "data_sensitivity": "confidential"},
    }
    _fake(_llm_json(
        architecture={"kind": "graph", "rationale": "grounded", "basis": "summarize confidential customer contract disputes"},
        suggested_risk_tier={"tier": "high", "basis": "confidential customer contract data"},
        suggested_agent_flow={
            "nodes": [
                {"id": "retrieve", "type": "rag", "label": "retrieve contracts"},
                {"id": "generate", "type": "llm", "label": "summarize"},
                {"id": "out", "type": "output_format", "label": "format"},
            ],
            "edges": [{"from": "retrieve", "to": "generate"}, {"from": "generate", "to": "out"}],
            "basis": "summarize contract disputes for legal team",
        },
    ))
    result = reco_engine.generate(high_intent)
    flow_v = result["validation"]["flow"]
    assert flow_v["source"] == "llm"
    assert flow_v["adjustments"]  # guardrail auto-inserted (spec §3.5)
    flow_item = next(i for i in result["items"] if i["kind"] == "flow")
    types = [n["type"] for n in flow_item["detail"]["flow"]["nodes"]]
    assert "guardrail" in types


# ---- API path ---------------------------------------------------------------

def _create_with_intent(client, name: str) -> str:
    login(client, "creator@platform.local")
    agent = client.post("/api/agents", json={"name": name}).json()
    client.put(f"/api/agents/{agent['id']}/intent/draft", json={"payload": INTENT_OK})
    r = client.post(f"/api/agents/{agent['id']}/intent/submit")
    assert r.status_code == 201, r.text
    return agent["id"]


def test_api_generate_requires_submitted_intent(client):
    login(client, "creator@platform.local")
    agent = client.post("/api/agents", json={"name": "No Intent Reco Agent"}).json()
    r = client.post(f"/api/agents/{agent['id']}/recommendation")
    assert r.status_code == 409


def test_api_recommendation_roundtrip_and_item_decisions(client):
    _fake(_llm_json())
    aid = _create_with_intent(client, "Reco Roundtrip Agent")

    r = client.post(f"/api/agents/{aid}/recommendation")
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["engine"] == "llm+deterministic"
    assert rec["model_id"] == "fake:scripted"  # labeled harness, visible
    item_ids = {i["id"] for i in rec["items"]}
    assert {"architecture", "risk_tier", "flow"} <= item_ids
    assert all(s == "pending" for s in rec["item_states"].values())

    # per-item decision (no bulk endpoint exists, by design)
    r2 = client.post(f"/api/agents/{aid}/recommendation/items/architecture", json={"state": "accepted"})
    assert r2.status_code == 200
    assert r2.json()["item_states"]["architecture"] == "accepted"

    r3 = client.post(f"/api/agents/{aid}/recommendation/items/nonexistent", json={"state": "accepted"})
    assert r3.status_code == 404

    # intent doc reflects recommendation_ready; audit trail has the generation
    intent = client.get(f"/api/agents/{aid}/intent").json()
    assert intent["status"] == "recommendation_ready"
    login(client, "admin@platform.local")
    rows = client.get(f"/api/audit?resource_type=agent&resource_id={aid}").json()
    actions = [row["action"] for row in rows]
    assert "recommendation_generated" in actions and "recommendation_item_decided" in actions


def test_api_regeneration_creates_new_version(client):
    _fake(_llm_json(), _llm_json())
    aid = _create_with_intent(client, "Reco Regen Agent")
    first = client.post(f"/api/agents/{aid}/recommendation").json()
    second = client.post(f"/api/agents/{aid}/recommendation").json()
    assert first["id"] != second["id"]  # new row, prior retained
    assert client.get(f"/api/agents/{aid}/recommendation").json()["id"] == second["id"]


def test_api_role_gate_on_generation(client):
    _fake(_llm_json())
    aid = _create_with_intent(client, "Reco Role Gate Agent")
    login(client, "governance@platform.local")  # reviewer can read, not generate
    assert client.post(f"/api/agents/{aid}/recommendation").status_code == 403
