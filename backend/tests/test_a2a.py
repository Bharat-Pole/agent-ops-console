"""A2A agent cards: governed metadata tied to a real agent, discovery gated on
platform-derived readiness, and READ-ONLY handoff validation.

The invariants under test are the ones that made this integration safe: the
card is bound to a governed agent by FK, publication runs through the existing
approval queue, readiness is computed (never asserted), and validating a
handoff executes nothing.
"""
from __future__ import annotations

import io

import pytest
from conftest import login

from app.adapters import models as adapters


@pytest.fixture(autouse=True)
def _clear_adapter():
    yield
    adapters.set_adapter_override(None)


CARD = {
    "description": "Summarizes network incidents for other agents",
    "capability_tier": "standardized",
    "discovery_only": True,
    "supported_tasks": ["summarize_incident"],
    "skills": ["incident-summary", "network-ops"],
    "authn_methods": ["api_key"],
    "timeout_seconds": 30,
}


def _agent(client, name: str) -> dict:
    login(client, "admin@platform.local")
    return client.post("/api/agents", json={"name": name}).json()


def _card(client, agent_id: str, **overrides) -> dict:
    login(client, "admin@platform.local")
    body = {**CARD, **overrides}
    r = client.post(f"/api/a2a/agents/{agent_id}/card", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _approve_card(client, card_id: str) -> str:
    login(client, "admin@platform.local")
    client.post(f"/api/a2a/cards/{card_id}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "agent_card" and a["resource_id"] == card_id][0]
    return client.post(f"/api/approvals/{step['id']}/decide",
                       json={"approve": True}).json()["asset_status"]


def _make_production(client, agent_id: str) -> None:
    """Drive an agent to production through the REAL gates (exception path for
    the eval gate, as an eval-less agent legitimately cannot promote)."""
    login(client, "admin@platform.local")
    client.post(f"/api/agents/{agent_id}/transition", json={"to": "sandbox"})
    client.post(f"/api/agents/{agent_id}/transition", json={"to": "candidate"})
    client.post(f"/api/agents/{agent_id}/transition", json={"to": "approved_prototype"})
    login(client, "governance@platform.local")
    client.post("/api/governance/exceptions", json={
        "agent_id": agent_id, "reason": "a2a test agent — no evaluation pack", "expires_days": 7})
    client.post(f"/api/agents/{agent_id}/transition", json={"to": "production_candidate"})
    client.post(f"/api/agents/{agent_id}/transition", json={"to": "production"})


def _active_workflow(client, agent_id: str, name: str) -> None:
    login(client, "admin@platform.local")
    pack = client.post("/api/prompts", json={
        "name": f"{name} prompt", "prompt_type": "system", "content": "Be terse."}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "prompt_version" and a["status"] == "pending"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})

    login(client, "admin@platform.local")
    wf = client.post(f"/api/agents/{agent_id}/workflows", json={"name": name, "graph": {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack["slug"]}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "out"}],
    }}).json()
    client.post(f"/api/workflows/{wf['id']}/versions/1/validate")
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "workflow_version" and a["status"] == "pending"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/activate")


def _discoverable_agent(client, name: str, **card_overrides) -> dict:
    """Agent + approved card + production + active workflow = discoverable."""
    agent = _agent(client, name)
    card = _card(client, agent["id"], **card_overrides)
    _approve_card(client, card["id"])
    _active_workflow(client, agent["id"], f"{name} flow")
    _make_production(client, agent["id"])
    return agent


# ---- card is bound to a real governed agent ---------------------------------

def test_card_requires_an_existing_agent(client):
    import uuid as uuid_mod
    login(client, "admin@platform.local")
    r = client.post(f"/api/a2a/agents/{uuid_mod.uuid4()}/card", json=CARD)
    assert r.status_code == 404


def test_card_is_tied_to_the_agent_by_fk(client):
    agent = _agent(client, "A2A FK Agent")
    card = _card(client, agent["id"])
    assert card["agent_id"] == agent["id"]
    assert card["agent_slug"] == agent["slug"]  # resolved through the FK
    assert card["version"] == 1 and card["status"] == "draft"


def test_one_card_per_agent_then_versions(client):
    agent = _agent(client, "A2A Version Agent")
    card = _card(client, agent["id"])
    login(client, "admin@platform.local")
    assert client.post(f"/api/a2a/agents/{agent['id']}/card", json=CARD).status_code == 409

    v2 = client.post(f"/api/a2a/cards/{card['id']}/new-version").json()
    assert v2["version"] == 2 and v2["status"] == "draft"


def test_tier_and_exchange_rules_are_enforced(client):
    agent = _agent(client, "A2A Rules Agent")
    login(client, "admin@platform.local")
    bad = client.post(f"/api/a2a/agents/{agent['id']}/card",
                      json={**CARD, "capability_tier": "standardized", "discovery_only": False})
    assert bad.status_code == 422 and "discovery-only" in bad.json()["detail"]

    bad2 = client.post(f"/api/a2a/agents/{agent['id']}/card", json={
        **CARD, "capability_tier": "advanced", "discovery_only": False,
        "artifact_exchange": True})
    assert bad2.status_code == 422 and "artifact_format" in bad2.json()["detail"]


# ---- lifecycle rides the existing approval queue ----------------------------

def test_publication_uses_the_platform_approval_queue(client):
    agent = _agent(client, "A2A Publish Agent")
    card = _card(client, agent["id"])
    assert _approve_card(client, card["id"]) == "approved"

    login(client, "admin@platform.local")
    detail = client.get(f"/api/a2a/agents/{agent['id']}/card").json()
    assert detail["status"] == "approved"


def test_approved_card_is_immutable_until_a_new_version(client):
    agent = _agent(client, "A2A Immutable Agent")
    card = _card(client, agent["id"])
    _approve_card(client, card["id"])
    login(client, "admin@platform.local")
    r = client.put(f"/api/a2a/cards/{card['id']}", json={**CARD, "description": "changed"})
    assert r.status_code == 409 and "new version" in r.json()["detail"]


def test_approving_a_new_version_supersedes_the_previous(client):
    agent = _agent(client, "A2A Supersede Agent")
    v1 = _card(client, agent["id"])
    _approve_card(client, v1["id"])
    login(client, "admin@platform.local")
    v2 = client.post(f"/api/a2a/cards/{v1['id']}/new-version").json()
    _approve_card(client, v2["id"])

    login(client, "admin@platform.local")
    cards = {c["id"]: c for c in client.get("/api/a2a/agent-cards").json()}
    assert cards[v2["id"]]["status"] == "approved"
    assert cards[v1["id"]]["status"] == "deprecated"
    assert cards[v1["id"]]["superseded_by"] == v2["id"]


# ---- readiness is DERIVED, and gates discovery ------------------------------

def test_unready_agent_is_excluded_from_discovery(client):
    agent = _agent(client, "A2A Unready Agent")
    card = _card(client, agent["id"])
    login(client, "admin@platform.local")

    # draft card: not discoverable, and the reason says so
    assert client.get("/api/a2a/discover").json() == [] or all(
        c["agent_id"] != agent["id"] for c in client.get("/api/a2a/discover").json())
    readiness = client.get(f"/api/a2a/agents/{agent['id']}/card").json()["readiness"]
    assert readiness["discoverable"] is False
    assert any("not approved" in r for r in readiness["reasons"])

    # approved but still in draft lifecycle with no workflow
    _approve_card(client, card["id"])
    login(client, "admin@platform.local")
    readiness = client.get(f"/api/a2a/agents/{agent['id']}/card").json()["readiness"]
    assert readiness["card_approved"] is True
    assert readiness["agent_in_production"] is False
    assert readiness["has_active_workflow"] is False
    assert readiness["discoverable"] is False
    assert all(c["agent_id"] != agent["id"] for c in client.get("/api/a2a/discover").json())


def test_ready_agent_is_discoverable_and_filterable_by_skill(client):
    agent = _discoverable_agent(client, "A2A Ready Agent")
    login(client, "admin@platform.local")

    found = client.get("/api/a2a/discover").json()
    mine = [c for c in found if c["agent_id"] == agent["id"]]
    assert len(mine) == 1
    assert mine[0]["readiness"]["discoverable"] is True

    by_skill = client.get("/api/a2a/discover?skill=incident-summary").json()
    assert any(c["agent_id"] == agent["id"] for c in by_skill)
    assert client.get("/api/a2a/discover?skill=no-such-skill").json() == []

    by_task = client.get("/api/a2a/discover?task=summarize_incident").json()
    assert any(c["agent_id"] == agent["id"] for c in by_task)


# ---- handoff validation (read-only) -----------------------------------------

def test_handoff_allowed_between_two_ready_agents(client):
    source = _discoverable_agent(client, "A2A Source Agent")
    target = _discoverable_agent(client, "A2A Target Agent")
    login(client, "admin@platform.local")
    decision = client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": source["slug"], "target_agent_slug": target["slug"],
        "task": "summarize_incident"}).json()

    assert decision["allowed"] is True, decision["reasons"]
    assert all(decision["checks"][c] for c in
               ("source_agent", "target_agent", "target_status", "supported_task",
                "required_skill", "caller_authorization", "approval"))
    assert decision["target"]["timeout_seconds"] == 30
    assert decision["rules_version"]


def test_unsupported_task_is_rejected(client):
    source = _discoverable_agent(client, "A2A Task Source")
    target = _discoverable_agent(client, "A2A Task Target")
    login(client, "admin@platform.local")
    decision = client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": source["slug"], "target_agent_slug": target["slug"],
        "task": "delete_everything"}).json()
    assert decision["allowed"] is False
    assert decision["checks"]["supported_task"] is False
    assert any("does not declare support" in r for r in decision["reasons"])


def test_unready_target_blocks_the_handoff(client):
    source = _discoverable_agent(client, "A2A Unready Source")
    target = _agent(client, "A2A Unready Target")
    card = _card(client, target["id"])
    _approve_card(client, card["id"])  # approved card, but agent never promoted
    login(client, "admin@platform.local")
    decision = client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": source["slug"], "target_agent_slug": target["slug"],
        "task": "summarize_incident"}).json()
    assert decision["allowed"] is False
    assert decision["checks"]["target_status"] is False
    assert any("not production" in r or "no active workflow" in r for r in decision["reasons"])


def test_authorized_callers_are_enforced(client):
    source = _discoverable_agent(client, "A2A Caller Source")
    target = _discoverable_agent(client, "A2A Caller Target",
                                 authorized_callers=["some-other-agent"])
    login(client, "admin@platform.local")
    decision = client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": source["slug"], "target_agent_slug": target["slug"],
        "task": "summarize_incident"}).json()
    assert decision["allowed"] is False
    assert decision["checks"]["caller_authorization"] is False


def test_required_skill_is_enforced(client):
    source = _discoverable_agent(client, "A2A Skill Source")
    target = _discoverable_agent(client, "A2A Skill Target")
    login(client, "admin@platform.local")
    decision = client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": source["slug"], "target_agent_slug": target["slug"],
        "task": "summarize_incident", "required_skill": "quantum-tunnelling"}).json()
    assert decision["allowed"] is False
    assert decision["checks"]["required_skill"] is False


def test_handoff_requiring_human_approval_is_blocked_until_granted(client):
    source = _discoverable_agent(client, "A2A Approval Source")
    target = _discoverable_agent(client, "A2A Approval Target",
                                 handoff_rules={"require_human_approval": True})
    login(client, "admin@platform.local")
    decision = client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": source["slug"], "target_agent_slug": target["slug"],
        "task": "summarize_incident"}).json()
    assert decision["allowed"] is False
    assert decision["checks"]["approval"] is False
    assert any("human approval" in r for r in decision["reasons"])


def test_missing_agents_are_reported_not_crashed(client):
    login(client, "admin@platform.local")
    decision = client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": "ghost-a", "target_agent_slug": "ghost-b",
        "task": "anything"}).json()
    assert decision["allowed"] is False
    assert decision["checks"]["source_agent"] is False
    assert decision["checks"]["target_agent"] is False


def test_validation_executes_nothing(client):
    """The whole point of validation-only: no run, no write."""
    source = _discoverable_agent(client, "A2A NoExec Source")
    target = _discoverable_agent(client, "A2A NoExec Target")
    login(client, "admin@platform.local")
    before = len(client.get(f"/api/agents/{target['id']}/runs").json())
    client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": source["slug"], "target_agent_slug": target["slug"],
        "task": "summarize_incident"})
    after = client.get(f"/api/agents/{target['id']}/runs").json()
    assert len(after) == before  # no workflow run was created


# ---- audit + auth ------------------------------------------------------------

def test_audit_actor_is_session_derived(client):
    agent = _agent(client, "A2A Audit Agent")
    card = _card(client, agent["id"])
    login(client, "admin@platform.local")
    rows = client.get(f"/api/audit?resource_type=agent_card&resource_id={card['id']}").json()
    created = [r for r in rows if r["action"] == "a2a_card_created"]
    assert created
    assert "admin@platform.local" in created[0]["actor"]


def test_card_mutations_are_role_gated(client):
    agent = _agent(client, "A2A Role Agent")
    login(client, "governance@platform.local")  # reviewer may read, not author
    r = client.post(f"/api/a2a/agents/{agent['id']}/card", json=CARD)
    assert r.status_code == 403


def test_discovery_requires_a_session(client):
    client.post("/api/auth/logout")
    assert client.get("/api/a2a/discover").status_code == 401
    assert client.post("/api/a2a/handoffs/validate", json={
        "source_agent_slug": "a", "target_agent_slug": "b", "task": "t"}).status_code == 401
