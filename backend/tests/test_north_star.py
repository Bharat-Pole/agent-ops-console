"""THE north-star e2e (Pass 0 acceptance): one continuous journey through the
real stack — intent → recommendation → per-item acceptance + materialization →
assets → workflow (seeded from the recommendation's machinery) → role-gated
approvals → REAL evaluation gating promotion → evidence pack → deployment
manifest → keyed REST invocation with NO session → real trace + cost telemetry.

Deterministic fake-LLM mode (the labeled harness); the same journey runs live
with a Gemini key. If this test is green, v1 is functional.
"""
from __future__ import annotations

import io
import json

import pytest
from conftest import login
from fastapi.testclient import TestClient

from app.adapters import models as adapters
from app.main import app


@pytest.fixture(autouse=True)
def _clear_adapter():
    yield
    adapters.set_adapter_override(None)


RECO_JSON = json.dumps({
    "summary": "Retrieval-grounded incident summarizer for the NOC team.",
    "architecture": {"kind": "graph", "rationale": "retrieval-grounded summarization",
                     "basis": "summarize weekly network incident reports with citations"},
    "suggested_risk_tier": {"tier": "medium", "basis": "internal incident data, advisory only"},
    "components": [
        {"kind": "prompt", "name": "NOC Summarizer Prompt", "purpose": "summarize incidents with citations",
         "registry_ref": None, "basis": "summarize weekly network incident reports"},
        {"kind": "knowledge", "name": "Incident Runbook", "purpose": "grounding corpus",
         "registry_ref": None, "basis": "network incident reports"},
    ],
    "suggested_agent_flow": {
        "nodes": [
            {"id": "retrieve", "type": "rag", "label": "Retrieve incidents", "config": {}},
            {"id": "generate", "type": "llm", "label": "Summarize", "config": {}},
            {"id": "format", "type": "output_format", "label": "Format", "config": {"format": "text"}},
        ],
        "edges": [{"from": "retrieve", "to": "generate"}, {"from": "generate", "to": "format"}],
        "basis": "summarize weekly network incident reports for the NOC team",
    },
    "missing_information": [], "clarifying_questions": [],
})


def test_north_star_end_to_end(client):
    fake = adapters.FakeModelAdapter(responses=[
        RECO_JSON,                                                    # recommendation
        "Check the core router logs first [Source 1], then escalate.",  # eval case run
        "Live answer: check the core router logs [Source 1].",          # deployed invocation
    ])
    adapters.set_adapter_override(fake)

    # 1 — intent capture (validated server-side, PII-scanned, frozen immutable)
    login(client, "creator@platform.local")
    agent = client.post("/api/agents", json={
        "name": "NOC Incident Digest", "description": "north-star agent"}).json()
    aid = agent["id"]
    client.patch(f"/api/agents/{aid}", json={"cost_center": "noc-ops", "business_owner": "NOC Lead"})
    client.put(f"/api/agents/{aid}/intent/draft", json={"payload": {
        "identity_purpose": {"objective": "Summarize weekly network incident reports for the NOC team with citations"},
        "data_rules": {"data_sources": ["incident_runbook"], "data_sensitivity": "internal"},
        "risk_governance": {"risk_tier": "medium", "human_approval_requirement": "none",
                            "deployment_channel": "rest_api"},
        "volume_evidence": {"expected_volume_per_day": 20, "latency_target": "batch",
                            "evidence_requirement": "standard"},
    }})
    submitted = client.post(f"/api/agents/{aid}/intent/submit").json()
    assert submitted["version"] == 1

    # 2 — LLM recommendation with honesty machinery; per-item acceptance
    reco = client.post(f"/api/agents/{aid}/recommendation").json()
    assert reco["engine"] == "llm+deterministic"
    assert reco["validation"]["contradictions"] == []  # llm and deterministic agree: medium
    prompt_item = next(i for i in reco["items"] if i["kind"] == "component_prompt")
    assert prompt_item["verification"] == "grounded"
    materialized = client.post(
        f"/api/agents/{aid}/recommendation/items/{prompt_item['id']}",
        json={"state": "accepted"}).json()["materialization"]
    assert materialized["materialized"] is True  # DRAFT prompt pack created
    client.post(f"/api/agents/{aid}/recommendation/items/flow", json={"state": "accepted"})

    # 3 — assets: author + approve the materialized prompt; upload knowledge
    login(client, "engineer@platform.local")
    pack_id = materialized["asset_id"]
    client.post(f"/api/prompts/{pack_id}/versions",
                json={"content": "You are the NOC incident summarizer. Always cite sources."})
    client.post(f"/api/prompts/{pack_id}/versions/2/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "prompt_version"][0]
    assert client.post(f"/api/approvals/{step['id']}/decide",
                       json={"approve": True}).json()["asset_status"] == "approved"

    login(client, "engineer@platform.local")
    source = client.post("/api/knowledge/upload",
                         files={"file": ("runbook.txt", io.BytesIO(
                             b"Network incident runbook. Check the core router logs first. "
                             b"Then verify fiber links and escalate outages to the NOC lead."), "text/plain")},
                         data={"name": "Incident Runbook"}).json()
    assert source["status"] == "ready" and source["embedded"] is True
    pipeline = client.post("/api/rag", json={"name": "north-star-pipe",
                                             "source_ids": [source["id"]],
                                             "score_threshold": 0.05}).json()
    prompt_slug = next(p["slug"] for p in client.get("/api/prompts").json() if p["id"] == pack_id)

    # 4 — workflow built on the recommendation's shape, validated + governed
    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "system", "config": {"pack_ref": prompt_slug}},
            {"id": "retrieve", "type": "rag", "label": "retrieve", "config": {"pipeline": pipeline["name"]}},
            {"id": "generate", "type": "llm", "label": "summarize", "config": {}},
            {"id": "guard", "type": "guardrail", "label": "guard", "config": {}},
            {"id": "format", "type": "output_format", "label": "format", "config": {"format": "text"}},
        ],
        "edges": [{"from": "sys", "to": "retrieve"}, {"from": "retrieve", "to": "generate"},
                  {"from": "generate", "to": "guard"}, {"from": "guard", "to": "format"}],
    }
    wf = client.post(f"/api/agents/{aid}/workflows",
                     json={"name": "digest-flow", "graph": graph}).json()
    validated = client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json()
    assert validated["status"] == "validated", validated["validation"]
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    wf_step = [a for a in client.get("/api/approvals").json()
               if a["resource_type"] == "workflow_version"][0]
    client.post(f"/api/approvals/{wf_step['id']}/decide", json={"approve": True})
    login(client, "owner@platform.local")
    assert client.post(f"/api/workflows/{wf['id']}/versions/1/activate").json()["status"] == "active"

    # 5 — REAL evaluation gates promotion
    login(client, "engineer@platform.local")
    epack = client.post(f"/api/agents/{aid}/eval-packs", json={"name": "north-star pack"}).json()
    client.post(f"/api/eval-packs/{epack['id']}/cases", json={
        "name": "grounded triage", "category": "golden",
        "input": "How do I triage a router outage?",
        "expectations": {"must_contain": ["router logs"], "must_cite": True, "no_write": True},
    })
    erun = client.post(f"/api/eval-packs/{epack['id']}/run", json={}).json()
    assert erun["scorecard"]["overall_passed"] is True

    # 6 — promotion through the role + eval gates; evidence pack frozen
    login(client, "creator@platform.local")
    client.post(f"/api/agents/{aid}/transition", json={"to": "sandbox"})
    client.post(f"/api/agents/{aid}/transition", json={"to": "candidate"})
    login(client, "owner@platform.local")
    client.post(f"/api/agents/{aid}/transition", json={"to": "approved_prototype"})
    login(client, "governance@platform.local")
    assert client.post(f"/api/agents/{aid}/transition",
                       json={"to": "production_candidate"}).status_code == 200
    assert client.post(f"/api/agents/{aid}/transition",
                       json={"to": "production"}).status_code == 200
    evidence = client.get(f"/api/governance/evidence/{aid}").json()
    assert evidence[0]["content"]["eval_run"]["scorecard"]["overall_passed"] is True

    # 7 — deployment: admission passes, manifest freezes assets
    login(client, "engineer@platform.local")
    group = client.post("/api/access-groups", json={"name": "north-star-consumers"}).json()
    key = client.post(f"/api/access-groups/{group['id']}/keys", json={"name": "ci key"}).json()
    login(client, "owner@platform.local")
    deployment = client.post(f"/api/agents/{aid}/deployments", json={
        "channel": "production", "access_group_id": group["id"]}).json()
    assert deployment["admission"]["allowed"] is True
    assert deployment["asset_pins"]["prompts"][prompt_slug]["version"] == 2

    # 8 — invoke over the REST channel with ONLY the API key (no session)
    anon = TestClient(app)
    result = anon.post(deployment["invoke_path"], json={"input": "What do I check first in an outage?"},
                       headers={"X-API-Key": key["api_key"]})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "completed"
    assert "[Source 1]" in body["output"]

    # 9 — the trace is real: spans, citation check, pinned prompt, tokens
    login(client, "creator@platform.local")
    trace = client.get(f"/api/runs/{body['run_id']}").json()
    assert trace["mode"] == "deployed"
    assert [s["node_type"] for s in trace["steps"]] == ["prompt", "rag", "llm", "guardrail", "output_format"]
    assert trace["output"]["citation_check"]["ok"] is True
    assert next(s for s in trace["steps"] if s["node_type"] == "prompt")["detail"]["pinned"] is True
    assert trace["totals"]["tokens_out"] > 0

    # 10 — telemetry reflects ONLY what actually happened
    summary = client.get(f"/api/telemetry/summary?agent_id={aid}").json()
    assert summary["runs"] == 2  # 1 evaluation + 1 deployed invocation
    assert summary["by_mode"] == {"evaluation": 1, "deployed": 1}
    assert summary["by_status"]["completed"] == 2
    client.post(f"/api/runs/{body['run_id']}/feedback", json={"rating": 1, "note": "correct answer"})
    assert client.get(f"/api/telemetry/summary?agent_id={aid}").json()["feedback"]["positive"] == 1

    # every scripted fake response was consumed — nothing extra was fabricated
    assert fake.responses == []
