"""Increment F acceptance: deployment admission, immutable manifests (asset
pins survive later approvals), keyed REST channel with rate limits, rollback,
telemetry from real runs with honest empty states, budgets + feedback.
"""
from __future__ import annotations

import uuid as uuid_mod

import pytest
from conftest import login
from fastapi.testclient import TestClient

from app.adapters import models as adapters
from app.main import app


@pytest.fixture(autouse=True)
def _clear_adapter():
    yield
    adapters.set_adapter_override(None)


def _fake(*responses: str) -> adapters.FakeModelAdapter:
    fake = adapters.FakeModelAdapter(responses=list(responses))
    adapters.set_adapter_override(fake)
    return fake


# ---- shared pipeline (mirrors E helpers) ------------------------------------

def _agent(client, name: str) -> str:
    login(client, "creator@platform.local")
    return client.post("/api/agents", json={"name": name}).json()["id"]


def _approved_prompt(client, name: str, content: str = "You are a NOC assistant.") -> dict:
    login(client, "engineer@platform.local")
    pack = client.post("/api/prompts", json={"name": name, "prompt_type": "system",
                                             "content": content}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "prompt_version"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    return pack


def _active_workflow(client, aid: str, name: str, prompt_slug: str) -> dict:
    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": prompt_slug}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "out"}],
    }
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": name, "graph": graph}).json()
    client.post(f"/api/workflows/{wf['id']}/versions/1/validate")
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "workflow_version"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    login(client, "owner@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/activate")
    return wf


def _pass_eval(client, aid: str, name: str) -> None:
    login(client, "engineer@platform.local")
    pack = client.post(f"/api/agents/{aid}/eval-packs", json={"name": name}).json()
    client.post(f"/api/eval-packs/{pack['id']}/cases", json={
        "name": f"{name} case", "category": "golden", "input": "How do I triage?",
        "expectations": {"must_contain": ["router"]},
    })
    run = client.post(f"/api/eval-packs/{pack['id']}/run", json={}).json()
    assert run["scorecard"]["overall_passed"], run["scorecard"]


def _to_production(client, aid: str) -> None:
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


def _group_and_key(client) -> tuple[str, str]:
    login(client, "engineer@platform.local")
    group = client.post("/api/access-groups",
                        json={"name": f"grp-{uuid_mod.uuid4().hex[:6]}"}).json()
    key = client.post(f"/api/access-groups/{group['id']}/keys", json={"name": "test key"}).json()
    assert key["api_key"].startswith("pk_")
    return group["id"], key["api_key"]


# ---- admission --------------------------------------------------------------

def test_production_admission_denies_with_reasons(client):
    _fake("Check the router logs.")
    aid = _agent(client, "Admission Agent")
    prompt = _approved_prompt(client, "Admission Prompt")
    _active_workflow(client, aid, "adm-wf", prompt["slug"])

    login(client, "owner@platform.local")
    denied = client.post(f"/api/agents/{aid}/deployments", json={"channel": "production"})
    assert denied.status_code == 403
    reasons = " ".join(denied.json()["detail"]["reasons"])
    assert "PRODUCTION lifecycle" in reasons
    assert "no PASSING evaluation" in reasons
    assert "cost_center" in reasons  # FinOps rule

    # sandbox channel deploys with just an active version
    ok = client.post(f"/api/agents/{aid}/deployments", json={"channel": "sandbox"})
    assert ok.status_code == 201
    assert ok.json()["admission"]["allowed"] is True


def test_manifest_pins_survive_later_prompt_approval_and_rollback(client):
    _fake("Check the router logs first.",  # eval case
          "Pinned-manifest response.")     # deployed invocation
    aid = _agent(client, "Pin Agent")
    prompt = _approved_prompt(client, "Pin Prompt", "PROMPT VERSION ONE")
    _active_workflow(client, aid, "pin-wf", prompt["slug"])
    _pass_eval(client, aid, "pin eval")
    login(client, "creator@platform.local")
    client.patch(f"/api/agents/{aid}", json={"cost_center": "noc-ops"})
    _to_production(client, aid)
    group_id, api_key = _group_and_key(client)

    login(client, "owner@platform.local")
    dep1 = client.post(f"/api/agents/{aid}/deployments",
                       json={"channel": "production", "access_group_id": group_id}).json()
    assert dep1["asset_pins"]["prompts"][prompt["slug"]]["version"] == 1

    # a NEW prompt version gets approved AFTER deployment
    login(client, "engineer@platform.local")
    client.post(f"/api/prompts/{prompt['id']}/versions", json={"content": "PROMPT VERSION TWO"})
    client.post(f"/api/prompts/{prompt['id']}/versions/2/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "prompt_version" and a["status"] == "pending"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})

    # re-certification moved the agent to needs_review — but the FROZEN
    # deployment keeps serving version ONE (snapshot doctrine)
    assert client.get(f"/api/agents/{aid}").json()["lifecycle_status"] == "needs_review"
    anon = TestClient(app)
    r = anon.post(f"/api/deployed/{dep1['slug']}/invoke",
                  json={"input": "triage please"}, headers={"X-API-Key": api_key})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    run = client.get(f"/api/runs/{r.json()['run_id']}").json()
    prompt_span = next(s for s in run["steps"] if s["node_type"] == "prompt")
    assert prompt_span["detail"]["pinned"] is True
    assert prompt_span["detail"]["pinned_version"] == 1  # NOT the newly approved v2

    # redeploy → pins v2; rollback → v1 manifest again as a NEW record
    login(client, "governance@platform.local")
    client.post(f"/api/agents/{aid}/transition", json={"to": "production"})  # recertify
    login(client, "owner@platform.local")
    dep2 = client.post(f"/api/agents/{aid}/deployments",
                       json={"channel": "production", "access_group_id": group_id}).json()
    assert dep2["asset_pins"]["prompts"][prompt["slug"]]["version"] == 2
    restored = client.post(f"/api/deployments/{dep1['id']}/rollback").json()
    assert restored["asset_pins"]["prompts"][prompt["slug"]]["version"] == 1
    assert restored["id"] not in (dep1["id"], dep2["id"])  # new record, history intact


def test_invoke_auth_and_rate_limit(client):
    _fake("resp one")
    aid = _agent(client, "Channel Agent")
    prompt = _approved_prompt(client, "Channel Prompt")
    _active_workflow(client, aid, "chan-wf", prompt["slug"])
    group_id, api_key = _group_and_key(client)
    login(client, "owner@platform.local")
    dep = client.post(f"/api/agents/{aid}/deployments",
                      json={"channel": "sandbox", "access_group_id": group_id,
                            "rate_limit_per_min": 1}).json()
    anon = TestClient(app)  # no session cookie — the channel is key-auth only

    assert anon.post(f"/api/deployed/{dep['slug']}/invoke", json={"input": "x"}).status_code == 401
    assert anon.post(f"/api/deployed/{dep['slug']}/invoke", json={"input": "x"},
                     headers={"X-API-Key": "pk_wrong"}).status_code == 401

    # wrong group's key
    other_group, other_key = _group_and_key(client)
    assert anon.post(f"/api/deployed/{dep['slug']}/invoke", json={"input": "x"},
                     headers={"X-API-Key": other_key}).status_code == 401

    ok = anon.post(f"/api/deployed/{dep['slug']}/invoke", json={"input": "triage"},
                   headers={"X-API-Key": api_key})
    assert ok.status_code == 200 and ok.json()["status"] == "completed"
    # rate limit 1/min → second call rejected
    limited = anon.post(f"/api/deployed/{dep['slug']}/invoke", json={"input": "again"},
                        headers={"X-API-Key": api_key})
    assert limited.status_code == 429

    # revoked key stops working
    login(client, "engineer@platform.local")
    groups = client.get("/api/access-groups").json()
    key_id = next(k["id"] for g in groups if g["id"] == group_id for k in g["keys"])
    client.post(f"/api/api-keys/{key_id}/revoke")
    assert anon.post(f"/api/deployed/{dep['slug']}/invoke", json={"input": "x"},
                     headers={"X-API-Key": api_key}).status_code == 401


# ---- telemetry + finops -----------------------------------------------------

def test_telemetry_honest_empty_then_real(client):
    _fake("telemetry response about router logs")
    aid = _agent(client, "Telemetry Agent")
    login(client, "creator@platform.local")
    empty = client.get(f"/api/telemetry/summary?agent_id={aid}").json()
    assert empty["runs"] == 0 and "no traffic yet" in empty["note"]  # honest empty state

    prompt = _approved_prompt(client, "Telemetry Prompt")
    _active_workflow(client, aid, "tel-wf", prompt["slug"])
    login(client, "creator@platform.local")
    run = client.post(f"/api/agents/{aid}/runs", json={"input": "triage the outage"}).json()
    assert run["status"] == "completed"

    summary = client.get(f"/api/telemetry/summary?agent_id={aid}").json()
    assert summary["runs"] == 1
    assert summary["by_status"]["completed"] == 1
    assert summary["tokens"]["out"] > 0
    assert summary["latency_ms"]["p50"] >= 0

    # feedback flows into the same summary
    client.post(f"/api/runs/{run['id']}/feedback", json={"rating": 1, "note": "good"})
    assert client.get(f"/api/telemetry/summary?agent_id={aid}").json()["feedback"]["positive"] == 1


def test_budget_alert(client):
    _fake("costly response")
    aid = _agent(client, "Budget Agent")
    prompt = _approved_prompt(client, "Budget Prompt")
    _active_workflow(client, aid, "bud-wf", prompt["slug"])
    login(client, "creator@platform.local")
    assert client.put(f"/api/agents/{aid}/budget", json={"monthly_usd": 5}).status_code == 403
    login(client, "admin@platform.local")
    assert client.put(f"/api/agents/{aid}/budget", json={"monthly_usd": 5}).status_code == 200
    rows = client.get("/api/telemetry/costs").json()
    mine = next(r for r in rows if r["agent_id"] == aid)
    assert mine["budget"]["monthly_usd"] == 5
    assert mine["budget"]["alert"] is False  # fake model has no catalog price → cost 0, honest
