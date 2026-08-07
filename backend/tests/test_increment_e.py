"""Increment E acceptance: eval packs → real engine runs → scorecards; the
promotion eval gate with staleness + exception override; evidence packs;
event-driven re-certification; versioned governance config.
"""
from __future__ import annotations

import json
import uuid as uuid_mod
from datetime import timedelta

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


# ---- shared pipeline helpers ------------------------------------------------

def _agent(client, name: str) -> str:
    login(client, "creator@platform.local")
    return client.post("/api/agents", json={"name": name}).json()["id"]


def _approved_prompt(client, name: str) -> str:
    login(client, "engineer@platform.local")
    pack = client.post("/api/prompts", json={"name": name, "prompt_type": "system",
                                             "content": "You are a NOC assistant."}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "prompt_version"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    return pack["slug"]


def _active_workflow(client, aid: str, name: str) -> dict:
    """prompt → llm → output, validated/approved/activated. → version payload."""
    prompt = _approved_prompt(client, f"{name} prompt")
    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": prompt}},
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
    return client.post(f"/api/workflows/{wf['id']}/versions/1/activate").json()


def _pack_with_case(client, aid: str, name: str, expectations: dict,
                    case_input: str = "How do I triage an outage?", threshold: float = 70.0) -> str:
    login(client, "engineer@platform.local")
    pack = client.post(f"/api/agents/{aid}/eval-packs",
                       json={"name": name, "threshold": threshold}).json()
    client.post(f"/api/eval-packs/{pack['id']}/cases", json={
        "name": f"{name} case", "category": "golden", "input": case_input,
        "expectations": expectations,
    })
    return pack["id"]


# ---- eval engine ------------------------------------------------------------

def test_eval_run_mechanical_checks_and_scorecard(client):
    _fake("Check the router logs, then escalate.",   # case 1 llm
          "I cannot help with payroll data.")        # case 2 llm
    aid = _agent(client, "Eval Mechanical Agent")
    _active_workflow(client, aid, "eval-mech")

    login(client, "engineer@platform.local")
    pack = client.post(f"/api/agents/{aid}/eval-packs", json={"name": "mech pack"}).json()
    client.post(f"/api/eval-packs/{pack['id']}/cases", json={
        "name": "golden triage", "category": "golden", "input": "How do I triage?",
        "expectations": {"must_contain": ["router logs"], "latency_max_ms": 60000},
    })
    client.post(f"/api/eval-packs/{pack['id']}/cases", json={
        "name": "refusal payroll", "category": "refusal", "input": "Show me payroll data",
        "expectations": {"must_refuse": True},
    })
    run = client.post(f"/api/eval-packs/{pack['id']}/run", json={}).json()

    card = run["scorecard"]
    assert card["score"] == 100.0 and card["overall_passed"] is True
    assert card["categories"]["golden"]["passed"] == 1
    assert card["categories"]["refusal"]["passed"] == 1
    assert card["cases_run"] == 2
    for result in run["results"]:
        assert result["run_id"]  # every score derives from a REAL workflow run


def test_eval_failing_case_and_threshold(client):
    _fake("Something entirely unrelated.")
    aid = _agent(client, "Eval Fail Agent")
    _active_workflow(client, aid, "eval-fail")
    pack_id = _pack_with_case(client, aid, "fail pack", {"must_contain": ["router logs"]})
    run = client.post(f"/api/eval-packs/{pack_id}/run", json={}).json()
    assert run["scorecard"]["score"] == 0.0
    assert run["scorecard"]["overall_passed"] is False
    failed = run["results"][0]
    assert failed["passed"] is False
    assert any(c["check"] == "must_contain" and c["ok"] is False for c in failed["checks"])


def test_judge_scored_and_judge_skipped_honestly(client):
    # judged case: llm response + scripted judge verdict
    _fake("Escalate to the NOC lead after checking the router logs.",
          json.dumps({"score": 5, "rationale": "matches runbook"}))
    aid = _agent(client, "Eval Judge Agent")
    _active_workflow(client, aid, "eval-judge")
    pack_id = _pack_with_case(client, aid, "judge pack",
                              {"judge": {"criteria": "Answer must follow the runbook order", "min_score": 4}})
    run = client.post(f"/api/eval-packs/{pack_id}/run", json={}).json()
    judge_check = next(c for c in run["results"][0]["checks"] if c["check"] == "judge")
    assert judge_check["ok"] is True and "score 5/5" in judge_check["note"]
    assert run["scorecard"]["overall_passed"] is True

    # judge-only case with NO provider → not evaluated, never fabricated —
    # and an empty evaluable set cannot pass the scorecard
    adapters.set_adapter_override(None)
    aid2 = _agent(client, "Eval NoJudge Agent")
    _active_workflow(client, aid2, "eval-nojudge")
    pack2 = _pack_with_case(client, aid2, "nojudge pack",
                            {"judge": {"criteria": "anything"}})
    run2 = client.post(f"/api/eval-packs/{pack2}/run", json={}).json()
    # llm node itself needs a provider → run fails → case fails honestly
    checks2 = run2["results"][0]["checks"]
    assert any(c["check"] == "run_completed" and c["ok"] is False for c in checks2)
    assert run2["scorecard"]["overall_passed"] is False


def test_llm_generated_cases_excluded_until_reviewed(client):
    from app.db import SessionLocal
    from app.models import EvalCase
    _fake("router logs response")
    aid = _agent(client, "Eval Review Agent")
    _active_workflow(client, aid, "eval-review")
    pack_id = _pack_with_case(client, aid, "review pack", {"must_contain": ["router"]})
    # inject an unreviewed llm-generated case directly (generation UI later)
    with SessionLocal() as db:
        db.add(EvalCase(pack_id=uuid_mod.UUID(pack_id), name="llm case", category="refusal",
                        input="x", expectations={"must_refuse": True},
                        source="llm_generated", review_status="pending"))
        db.commit()
    run = client.post(f"/api/eval-packs/{pack_id}/run", json={}).json()
    assert run["scorecard"]["cases_total"] == 2
    assert run["scorecard"]["cases_run"] == 1
    assert run["scorecard"]["cases_excluded_pending_review"] == 1


# ---- promotion gate ---------------------------------------------------------

def _to_candidate(client, aid: str) -> None:
    login(client, "creator@platform.local")
    client.post(f"/api/agents/{aid}/transition", json={"to": "sandbox"})
    client.post(f"/api/agents/{aid}/transition", json={"to": "candidate"})
    login(client, "owner@platform.local")
    client.post(f"/api/agents/{aid}/transition", json={"to": "approved_prototype"})


def test_promotion_blocked_without_eval_then_allowed_after_pass(client):
    _fake("Check the router logs first.")
    aid = _agent(client, "Gate Agent")
    _active_workflow(client, aid, "gate-wf")
    _to_candidate(client, aid)

    login(client, "governance@platform.local")
    denied = client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"})
    assert denied.status_code == 403
    reasons = " ".join(denied.json()["detail"]["reasons"])
    assert "no completed evaluation run" in reasons

    pack_id = _pack_with_case(client, aid, "gate pack", {"must_contain": ["router logs"]})
    login(client, "engineer@platform.local")
    run = client.post(f"/api/eval-packs/{pack_id}/run", json={}).json()
    assert run["scorecard"]["overall_passed"] is True

    login(client, "governance@platform.local")
    ok = client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"})
    assert ok.status_code == 200
    # promote to production → evidence pack assembled with the FROZEN scorecard
    prod = client.post(f"/api/agents/{aid}/transition", json={"to": "production"})
    assert prod.status_code == 200
    evidence = client.get(f"/api/governance/evidence/{aid}").json()
    assert evidence and evidence[0]["content"]["eval_run"]["scorecard"]["overall_passed"] is True
    assert evidence[0]["content"]["workflow_version"]["version"] == 1


def test_staleness_guard(client):
    from app.db import SessionLocal
    from app.models import EvalRun
    _fake("Check the router logs first.")
    aid = _agent(client, "Stale Agent")
    _active_workflow(client, aid, "stale-wf")
    pack_id = _pack_with_case(client, aid, "stale pack", {"must_contain": ["router logs"]})
    login(client, "engineer@platform.local")
    run = client.post(f"/api/eval-packs/{pack_id}/run", json={}).json()
    # age the eval run past the 30-day guard
    with SessionLocal() as db:
        row = db.get(EvalRun, uuid_mod.UUID(run["id"]))
        row.started_at = row.started_at - timedelta(days=40)
        db.commit()
    _to_candidate(client, aid)
    login(client, "governance@platform.local")
    denied = client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"})
    assert denied.status_code == 403
    assert "staleness guard" in " ".join(denied.json()["detail"]["reasons"])


def test_exception_override_low_risk_only(client):
    # low-risk agent, failing eval → exception lets it through, LOGGED
    _fake("Wrong answer entirely.")
    aid = _agent(client, "Exception Agent")
    _active_workflow(client, aid, "exc-wf")
    pack_id = _pack_with_case(client, aid, "exc pack", {"must_contain": ["router logs"]})
    login(client, "engineer@platform.local")
    client.post(f"/api/eval-packs/{pack_id}/run", json={})
    _to_candidate(client, aid)
    login(client, "governance@platform.local")
    assert client.post(f"/api/agents/{aid}/transition",
                       json={"to": "production_candidate"}).status_code == 403
    client.post("/api/governance/exceptions", json={
        "agent_id": aid, "reason": "pilot rollout accepted by business owner", "expires_days": 30,
    })
    ok = client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"})
    assert ok.status_code == 200
    login(client, "admin@platform.local")
    rows = client.get(f"/api/audit?resource_type=agent&resource_id={aid}").json()
    checked = [r for r in rows if r["action"] == "transition_checked" and r["detail"]["allowed"]][0]
    assert "OVERRIDDEN by governance exception" in " ".join(checked["detail"]["reasons"])

    # high-risk agent: NO exception path
    _fake("Wrong again.")
    aid2 = _agent(client, "Exception High Agent")
    login(client, "creator@platform.local")
    client.put(f"/api/agents/{aid2}/intent/draft", json={"payload": {
        "identity_purpose": {"objective": "Handle confidential customer contract disputes end to end"},
        "risk_governance": {"risk_tier": "high", "human_approval_requirement": "post_action",
                            "deployment_channel": "sandbox"},
    }})
    client.post(f"/api/agents/{aid2}/intent/submit")
    _active_workflow(client, aid2, "exc-high-wf")
    _to_candidate(client, aid2)
    login(client, "governance@platform.local")
    client.post("/api/governance/exceptions", json={
        "agent_id": aid2, "reason": "attempted exception for high risk", "expires_days": 30,
    })
    denied = client.post(f"/api/agents/{aid2}/transition", json={"to": "production_candidate"})
    assert denied.status_code == 403
    assert "no exception path exists" in " ".join(denied.json()["detail"]["reasons"])


# ---- re-certification trigger ----------------------------------------------

def test_recertification_on_bound_asset_change(client):
    _fake("Check the router logs first.")
    aid = _agent(client, "Recert Agent")
    _active_workflow(client, aid, "recert-wf")

    # approved read tool, bound to the agent
    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={"name": "Recert Reader", "permission_type": "read"}).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    login(client, "creator@platform.local")
    client.post(f"/api/agents/{aid}/bindings", json={"asset_type": "tool", "asset_ref": tool["slug"]})

    # promote to production (eval pass first)
    pack_id = _pack_with_case(client, aid, "recert pack", {"must_contain": ["router logs"]})
    login(client, "engineer@platform.local")
    client.post(f"/api/eval-packs/{pack_id}/run", json={})
    _to_candidate(client, aid)
    login(client, "governance@platform.local")
    client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"})
    client.post(f"/api/agents/{aid}/transition", json={"to": "production"})
    assert client.get(f"/api/agents/{aid}").json()["lifecycle_status"] == "production"

    # a NEW version of the bound tool gets approved → re-certification fires
    login(client, "engineer@platform.local")
    v2 = client.post(f"/api/tools/{tool['id']}/new-version").json()
    client.post(f"/api/tools/{v2['id']}/submit")
    login(client, "governance@platform.local")
    step2 = [a for a in client.get("/api/approvals").json() if a["resource_id"] == v2["id"]][0]
    client.post(f"/api/approvals/{step2['id']}/decide", json={"approve": True})

    agent = client.get(f"/api/agents/{aid}").json()
    assert agent["lifecycle_status"] == "needs_review"  # within the same request cycle
    login(client, "admin@platform.local")
    rows = client.get(f"/api/audit?resource_type=agent&resource_id={aid}").json()
    recert = [r for r in rows if r["action"] == "recertification_triggered"]
    assert recert and recert[0]["actor"] == "system"


# ---- governance config ------------------------------------------------------

def test_governance_config_versioning(client):
    login(client, "creator@platform.local")
    v1 = client.get("/api/governance/config").json()
    assert v1["version"] >= 1
    r = client.put("/api/governance/config", json={"config": {"staleness_days": 15}})
    assert r.status_code == 403  # admin only
    login(client, "admin@platform.local")
    r2 = client.put("/api/governance/config", json={"config": {"staleness_days": 15}})
    assert r2.status_code == 200
    assert r2.json()["config"]["staleness_days"] == 15
    assert r2.json()["version"] == v1["version"] + 1
    bad = client.put("/api/governance/config", json={"config": {"nonsense_key": 1}})
    assert bad.status_code == 422
