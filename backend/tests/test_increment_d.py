"""Increment D acceptance: workflow lifecycle (fork-on-edit, validation gates
submission), and the REAL engine — compiled graphs, per-node spans, model
clamps, execution-layer write refusal, guardrail fails closed, and durable
HITL pause/resume across separate HTTP requests.
"""
from __future__ import annotations

import io
import json

import pytest
from conftest import login

from app.adapters import models as adapters


@pytest.fixture(autouse=True)
def _clear_adapter():
    yield
    adapters.set_adapter_override(None)


def _fake(*responses: str) -> adapters.FakeModelAdapter:
    fake = adapters.FakeModelAdapter(responses=list(responses))
    adapters.set_adapter_override(fake)
    return fake


# ---- fixtures via the real API ----------------------------------------------

def _agent(client, name: str) -> str:
    login(client, "creator@platform.local")
    return client.post("/api/agents", json={"name": name}).json()["id"]


def _approved_prompt(client, name: str, content: str) -> str:
    """→ pack slug with an APPROVED version."""
    login(client, "engineer@platform.local")
    pack = client.post("/api/prompts", json={"name": name, "prompt_type": "system", "content": content}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "prompt_version"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    return pack["slug"]


def _rag_pipeline(client, name: str) -> str:
    """Upload a source (fake embedder) + build a pipeline. → pipeline name."""
    login(client, "engineer@platform.local")
    content = ("Network incident runbook. Check the core router logs first. "
               "Then verify fiber links and escalate outages to the NOC lead.")
    src = client.post("/api/knowledge/upload",
                      files={"file": (f"{name}.txt", io.BytesIO(content.encode()), "text/plain")},
                      data={"name": name}).json()
    pipe = client.post("/api/rag", json={"name": name, "source_ids": [src["id"]],
                                         "score_threshold": 0.05}).json()
    return pipe["name"]


def _approve_and_activate(client, workflow_id: str, version: int = 1) -> None:
    login(client, "engineer@platform.local")
    r = client.post(f"/api/workflows/{workflow_id}/versions/{version}/validate")
    assert r.json()["status"] == "validated", r.json()["validation"]
    client.post(f"/api/workflows/{workflow_id}/versions/{version}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "workflow_version"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    login(client, "owner@platform.local")
    r = client.post(f"/api/workflows/{workflow_id}/versions/{version}/activate")
    assert r.json()["status"] == "active", r.text


def _simple_graph(prompt_slug: str, pipeline: str) -> dict:
    return {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "system", "config": {"pack_ref": prompt_slug}},
            {"id": "retrieve", "type": "rag", "label": "retrieve", "config": {"pipeline": pipeline}},
            {"id": "generate", "type": "llm", "label": "generate", "config": {"temperature": 0.9}},
            {"id": "guard", "type": "guardrail", "label": "guard", "config": {}},
            {"id": "out", "type": "output_format", "label": "out", "config": {"format": "text"}},
        ],
        "edges": [
            {"from": "sys", "to": "retrieve"}, {"from": "retrieve", "to": "generate"},
            {"from": "generate", "to": "guard"}, {"from": "guard", "to": "out"},
        ],
    }


# ---- validation -------------------------------------------------------------

def test_validation_rejects_unimplemented_unapproved_and_write_refs(client):
    aid = _agent(client, "WF Validation Agent")
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "bad wf", "graph": {
        "nodes": [
            {"id": "q", "type": "structured_query", "label": "", "config": {}},
            {"id": "p", "type": "prompt", "label": "", "config": {"pack_ref": "does-not-exist"}},
            {"id": "o", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [{"from": "q", "to": "p"}, {"from": "p", "to": "o"}],
    }}).json()
    r = client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json()
    assert r["status"] == "draft"  # validation failed → stays draft
    joined = " ".join(r["validation"]["violations"])
    assert "structured_query" in joined and "later increment" in joined
    assert "no APPROVED version" in joined


def test_validation_guardrail_autoinsert_for_high_risk(client):
    aid = _agent(client, "WF Guardrail Agent")
    login(client, "creator@platform.local")
    client.put(f"/api/agents/{aid}/intent/draft", json={"payload": {
        "identity_purpose": {"objective": "Summarize confidential customer contracts for the legal team"},
        "risk_governance": {"risk_tier": "high", "human_approval_requirement": "post_action",
                            "deployment_channel": "sandbox"},
    }})
    client.post(f"/api/agents/{aid}/intent/submit")  # sets draft_risk_tier=high
    prompt = _approved_prompt(client, "Guard Prompt", "Be careful.")
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "guarded", "graph": {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": prompt}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "out"}],
    }}).json()
    r = client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json()
    assert r["status"] == "validated"
    types = [n["type"] for n in r["graph"]["nodes"]]
    assert "guardrail" in types  # auto-inserted, persisted on the version
    assert r["validation"]["adjustments"]


def test_fork_on_edit_active_version(client):
    aid = _agent(client, "WF Fork Agent")
    prompt = _approved_prompt(client, "Fork Prompt", "You are terse.")
    pipeline = _rag_pipeline(client, "fork-pipe")
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows",
                     json={"name": "main", "graph": _simple_graph(prompt, pipeline)}).json()
    _approve_and_activate(client, wf["id"])

    login(client, "engineer@platform.local")
    r = client.put(f"/api/workflows/{wf['id']}/versions/1",
                   json={"graph": _simple_graph(prompt, pipeline)})
    assert r.status_code == 409  # active is immutable
    fork = client.post(f"/api/workflows/{wf['id']}/versions/1/fork").json()
    assert fork["version"] == 2 and fork["status"] == "draft"


# ---- engine runs ------------------------------------------------------------

def test_full_run_with_citations_spans_and_clamps(client):
    fake = _fake("Check the core router logs first [Source 1].")
    aid = _agent(client, "Engine Run Agent")
    prompt = _approved_prompt(client, "Runbook Prompt", "You are a NOC assistant.")
    pipeline = _rag_pipeline(client, "engine-pipe")
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows",
                     json={"name": "runbook", "graph": _simple_graph(prompt, pipeline)}).json()
    _approve_and_activate(client, wf["id"])

    login(client, "creator@platform.local")
    run = client.post(f"/api/agents/{aid}/runs", json={"input": "How do I triage a router outage?"}).json()
    assert run["status"] == "completed", run.get("error")
    assert "[Source 1]" in run["output"]["final_output"]
    assert run["output"]["citation_check"]["ok"] is True

    types = [s["node_type"] for s in run["steps"]]
    assert types == ["prompt", "rag", "llm", "guardrail", "output_format"]
    llm_step = next(s for s in run["steps"] if s["node_type"] == "llm")
    assert llm_step["tokens_in"] > 0 and llm_step["tokens_out"] > 0
    assert llm_step["detail"]["temperature"] <= 0.9  # clamp applied (low risk cap)
    assert run["totals"]["tokens_out"] > 0
    # the system prompt actually contained the approved pack content
    assert "NOC assistant" in fake.calls[0]["system"]


def test_guardrail_fails_closed_on_fabricated_citation(client):
    _fake("According to [Source 9], reboot everything.")
    aid = _agent(client, "Guardrail Fail Agent")
    prompt = _approved_prompt(client, "GF Prompt", "Cite sources.")
    pipeline = _rag_pipeline(client, "guardfail-pipe")
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows",
                     json={"name": "guardfail", "graph": _simple_graph(prompt, pipeline)}).json()
    _approve_and_activate(client, wf["id"])

    login(client, "creator@platform.local")
    run = client.post(f"/api/agents/{aid}/runs", json={"input": "what should I do?"}).json()
    assert run["status"] == "failed"
    assert "guardrail violation" in run["error"] and "invalid citations" in run["error"]
    guard_step = next(s for s in run["steps"] if s["node_type"] == "guardrail")
    assert guard_step["status"] == "failed"


def test_write_tool_refused_at_execution_layer(client):
    """Fresh-resolve hazard covered: tool was read-class at validation time,
    latest approved becomes write-class later → execution refuses (layer 3)."""
    _fake("Advisory summary complete.")
    aid = _agent(client, "Exec Refusal Agent")
    prompt = _approved_prompt(client, "ER Prompt", "Summarize.")

    # v1 read tool, approved
    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={"name": "Ticket Sync", "permission_type": "read"}).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})

    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": prompt}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "sync", "type": "tool_call", "label": "", "config": {"tool_ref": tool["slug"]}},
            {"id": "out", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "sync"}, {"from": "sync", "to": "out"}],
    }
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "exec-refusal", "graph": graph}).json()
    _approve_and_activate(client, wf["id"])

    # NOW the tool's latest approved version becomes write-class (dual sign-off)
    login(client, "engineer@platform.local")
    v2 = client.post(f"/api/tools/{tool['id']}/new-version").json()
    client.put(f"/api/tools/{v2['id']}", json={"name": "Ticket Sync", "permission_type": "update"})
    client.post(f"/api/tools/{v2['id']}/submit")
    login(client, "governance@platform.local")
    g = [a for a in client.get("/api/approvals").json() if a["resource_id"] == v2["id"]][0]
    client.post(f"/api/approvals/{g['id']}/decide", json={"approve": True})
    login(client, "security@platform.local")
    s = [a for a in client.get("/api/approvals").json() if a["resource_id"] == v2["id"]][0]
    client.post(f"/api/approvals/{s['id']}/decide", json={"approve": True})

    login(client, "creator@platform.local")
    run = client.post(f"/api/agents/{aid}/runs", json={"input": "sync my tickets"}).json()
    assert run["status"] == "completed"  # advisory continue — refusal is a result
    sync_step = next(s for s in run["steps"] if s["node_id"] == "sync")
    assert sync_step["status"] == "refused"
    assert "advisory-only base phase" in " ".join(sync_step["detail"]["policy"])


def test_hitl_pauses_durably_and_resumes(client):
    _fake("Draft outage notice ready for review.")
    aid = _agent(client, "HITL Agent")
    prompt = _approved_prompt(client, "HITL Prompt", "Draft notices.")
    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": prompt}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "approve", "type": "human_approval", "label": "", "config": {"requirement": "post_action"}},
            {"id": "out", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "approve"}, {"from": "approve", "to": "out"}],
    }
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "hitl", "graph": graph}).json()
    _approve_and_activate(client, wf["id"])

    login(client, "creator@platform.local")
    run = client.post(f"/api/agents/{aid}/runs", json={"input": "draft the outage notice"}).json()
    assert run["status"] == "paused_hitl"
    assert run["output"] == {}  # nothing fabricated while paused
    pending = [h for h in run["hitl"] if h["status"] == "pending"]
    assert len(pending) == 1
    assert "Draft outage notice" in pending[0]["payload"]["llm_output_preview"]

    # a SEPARATE request (fresh state) resumes from the durable checkpoint
    login(client, "owner@platform.local")
    resumed = client.post(f"/api/runs/{run['id']}/hitl/{pending[0]['id']}",
                          json={"approve": True, "note": "looks good"}).json()
    assert resumed["status"] == "completed", resumed.get("error")
    assert resumed["output"]["final_output"] == "Draft outage notice ready for review."
    hitl_spans = [s for s in resumed["steps"] if s["node_type"] == "human_approval"]
    assert [s["status"] for s in hitl_spans] == ["paused", "ok"]  # both moments traced


def test_hitl_denial_fails_run(client):
    _fake("Something to deny.")
    aid = _agent(client, "HITL Deny Agent")
    prompt = _approved_prompt(client, "Deny Prompt", "Draft things.")
    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": prompt}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "approve", "type": "human_approval", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "approve"}, {"from": "approve", "to": "out"}],
    }
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "deny", "graph": graph}).json()
    _approve_and_activate(client, wf["id"])
    login(client, "creator@platform.local")
    run = client.post(f"/api/agents/{aid}/runs", json={"input": "go"}).json()
    pending = [h for h in run["hitl"] if h["status"] == "pending"][0]
    login(client, "owner@platform.local")
    denied = client.post(f"/api/runs/{run['id']}/hitl/{pending['id']}",
                         json={"approve": False, "note": "not appropriate"}).json()
    assert denied["status"] == "failed"
    assert "denied" in denied["error"] and "not appropriate" in denied["error"]


def test_run_guards(client):
    aid = _agent(client, "Run Guard Agent")
    login(client, "creator@platform.local")
    r = client.post(f"/api/agents/{aid}/runs", json={"input": "hello"})
    assert r.status_code == 409  # no active workflow

    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "draft-only", "graph": {
        "nodes": [{"id": "o", "type": "output_format", "label": "", "config": {}}], "edges": [],
    }}).json()
    version_id = wf["versions"][0]["id"]
    login(client, "creator@platform.local")
    r2 = client.post(f"/api/agents/{aid}/runs",
                     json={"input": "hello", "workflow_version_id": version_id})
    assert r2.status_code == 409  # unvalidated draft not runnable
    assert "validate" in r2.json()["detail"]
