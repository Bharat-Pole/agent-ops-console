"""The admin account holds every role so one person can drive the whole
journey — WITHOUT that quietly collapsing dual sign-off into one signature.
"""
from __future__ import annotations

from conftest import login


def test_admin_holds_every_role(client):
    login(client, "admin@platform.local")
    me = client.get("/api/auth/me").json()
    assert len(me["roles"]) == 9
    for role in ("agent_creator", "ai_engineer", "governance_reviewer",
                 "agent_owner", "security_data_owner", "evaluator", "finops_admin"):
        assert role in me["roles"]


def test_admin_can_drive_the_whole_single_signoff_journey(client):
    """Create → tool → approve → prompt → approve, all as one account."""
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Admin Solo Agent"})
    assert agent.status_code == 201  # agent_creator

    tool = client.post("/api/tools", json={"name": "Admin Solo Tool",
                                           "permission_type": "read"})
    assert tool.status_code == 201  # ai_engineer
    tool_id = tool.json()["id"]
    assert client.post(f"/api/tools/{tool_id}/submit").status_code == 200

    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool_id][0]
    decided = client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    assert decided.json()["asset_status"] == "approved"  # governance_reviewer


def test_admin_cannot_be_both_signatures_of_a_dual_signoff(client):
    """A write-class tool needs governance AND security. Admin holds both
    roles, but a second human is still required."""
    login(client, "admin@platform.local")
    tool = client.post("/api/tools", json={"name": "Admin Dual Tool",
                                           "permission_type": "update"}).json()
    assert tool["is_write_class"] is True
    client.post(f"/api/tools/{tool['id']}/submit")

    steps = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]]
    assert len(steps) == 2  # governance_review + security_signoff

    first = client.post(f"/api/approvals/{steps[0]['id']}/decide", json={"approve": True})
    assert first.status_code == 200
    assert first.json()["asset_status"] is None  # not approved on one signature

    second = client.post(f"/api/approvals/{steps[1]['id']}/decide", json={"approve": True})
    assert second.status_code == 403
    assert "distinct approver" in second.json()["detail"]

    # a genuinely different person completes it
    remaining = next(s for s in steps if s["id"] != steps[0]["id"])
    login(client, "security@platform.local" if remaining["required_role"] == "security_data_owner"
          else "governance@platform.local")
    final = client.post(f"/api/approvals/{remaining['id']}/decide", json={"approve": True})
    assert final.status_code == 200
    assert final.json()["asset_status"] == "approved"
