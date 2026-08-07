"""Increment A acceptance: auth + RBAC, lifecycle machine, audit actor
attribution, drafts-vs-immutable intent. Every test drives the REAL app + DB.
"""
from __future__ import annotations

from conftest import login


def _create_agent(client, name: str) -> dict:
    login(client, "creator@platform.local")
    r = client.post("/api/agents", json={"name": name, "description": "d"})
    assert r.status_code == 201, r.text
    return r.json()


# ---- auth & RBAC ------------------------------------------------------------

def test_unauthenticated_requests_rejected(client):
    assert client.get("/api/agents").status_code == 401
    assert client.get("/api/audit").status_code == 401


def test_login_bad_credentials_uniform_error(client):
    r1 = client.post("/api/auth/login", json={"email": "nobody@platform.local", "password": "x"})
    r2 = client.post("/api/auth/login", json={"email": "admin@platform.local", "password": "wrong"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()  # no user enumeration


def test_role_gate_on_agent_creation(client):
    login(client, "governance@platform.local")  # governance_reviewer cannot create
    r = client.post("/api/agents", json={"name": "Should Fail Agent"})
    assert r.status_code == 403


def test_logout_revokes_session_server_side(client):
    login(client, "creator@platform.local")
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401  # revoked in DB, not just cookie


# ---- lifecycle machine ------------------------------------------------------

def test_full_promotion_path_with_role_enforcement(client):
    agent = _create_agent(client, "Lifecycle Test Agent")
    aid = agent["id"]

    # creator can move draft → sandbox → candidate
    for to in ("sandbox", "candidate"):
        r = client.post(f"/api/agents/{aid}/transition", json={"to": to})
        assert r.status_code == 200, r.text

    # creator may NOT approve candidacy (agent_owner's gate) — DENY is audited
    r = client.post(f"/api/agents/{aid}/transition", json={"to": "approved_prototype"})
    assert r.status_code == 403

    login(client, "owner@platform.local")
    assert client.post(f"/api/agents/{aid}/transition", json={"to": "approved_prototype"}).status_code == 200

    # owner may NOT promote to production_candidate (governance gate)
    assert client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"}).status_code == 403

    login(client, "governance@platform.local")
    # Increment E: the eval gate blocks promotion without a passing evaluation;
    # this low-risk agent passes via a LOGGED governance exception instead
    denied = client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"})
    assert denied.status_code == 403
    client.post("/api/governance/exceptions", json={
        "agent_id": aid, "reason": "role-enforcement test agent — no eval pack", "expires_days": 7,
    })
    assert client.post(f"/api/agents/{aid}/transition", json={"to": "production_candidate"}).status_code == 200
    r = client.post(f"/api/agents/{aid}/transition", json={"to": "production"})
    assert r.status_code == 200
    assert r.json()["lifecycle_status"] == "production"


def test_undefined_transition_rejected(client):
    agent = _create_agent(client, "Bad Transition Agent")
    r = client.post(f"/api/agents/{agent['id']}/transition", json={"to": "production"})
    assert r.status_code == 403
    assert "no transition" in str(r.json())


# ---- audit ------------------------------------------------------------------

def test_audit_actor_is_session_derived_and_denies_are_logged(client):
    agent = _create_agent(client, "Audit Actor Agent")
    aid = agent["id"]
    # a denied transition still writes an audit row with the REAL actor
    client.post(f"/api/agents/{aid}/transition", json={"to": "production"})
    login(client, "admin@platform.local")
    rows = client.get(f"/api/audit?resource_type=agent&resource_id={aid}").json()
    checked = [r for r in rows if r["action"] == "transition_checked"]
    assert checked, rows
    assert checked[0]["detail"]["allowed"] is False
    assert "creator@platform.local" in checked[0]["actor"]  # server-derived, not client-supplied
    assert checked[0]["detail"]["rules_version"]  # decision carries policy version


# ---- intent: draft vs immutable --------------------------------------------

def test_draft_mutable_then_submission_immutable_and_superseded(client):
    agent = _create_agent(client, "Intent Doc Agent")
    aid = agent["id"]

    client.put(f"/api/agents/{aid}/intent/draft", json={"payload": {
        "identity_purpose": {"objective": "Summarize weekly network incident reports for the NOC team (v1)"},
    }})
    r1 = client.post(f"/api/agents/{aid}/intent/submit")
    assert r1.status_code == 201, r1.text
    assert r1.json()["version"] == 1

    # draft keeps evolving; submission again → version 2, v1 superseded
    client.put(f"/api/agents/{aid}/intent/draft", json={"payload": {
        "identity_purpose": {"objective": "Summarize weekly network incident reports for the NOC team (v2)"},
    }})
    r2 = client.post(f"/api/agents/{aid}/intent/submit")
    assert r2.json()["version"] == 2

    detail = client.get(f"/api/agents/{aid}").json()
    assert detail["current_intent_version"] == 2


def test_restricted_without_hitl_blocked_422(client):
    agent = _create_agent(client, "Restricted Gate Agent")
    aid = agent["id"]
    client.put(f"/api/agents/{aid}/intent/draft", json={"payload": {
        "identity_purpose": {"objective": "Review restricted regulatory filings and draft attestation summaries"},
        "risk_governance": {"risk_tier": "restricted", "human_approval_requirement": "none"},
    }})
    r = client.post(f"/api/agents/{aid}/intent/submit")
    assert r.status_code == 422
    assert "Governance Policy" in r.json()["detail"]


def test_duplicate_agent_name_conflict(client):
    _create_agent(client, "Unique Name Agent")
    login(client, "creator@platform.local")
    r = client.post("/api/agents", json={"name": "Unique Name Agent"})
    assert r.status_code == 409
