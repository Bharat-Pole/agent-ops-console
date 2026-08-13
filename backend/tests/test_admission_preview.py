"""The read-only admission preview behind the deployment card.

Deployment depends on evaluation, lifecycle, evidence and a cost label, but
none of that was visible until a deploy attempt came back 403 — so the two
pages had a real dependency and no link. The preview closes that.

The property that matters most is the LAST test: the preview must agree with
what deploy actually does. A preview that drifts from the rule is worse than no
preview, because people would trust it.
"""
from __future__ import annotations

import pytest
from conftest import login


def _decide_pending(client, resource_id: str) -> dict:
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_id"] == resource_id and a["status"] == "pending"][0]
    return client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True}).json()


def _agent_with_active_workflow(client, name: str) -> dict:
    login(client, "admin@platform.local")
    pack = client.post("/api/prompts", json={
        "name": f"{name} prompt", "prompt_type": "system", "content": "Be terse."}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    version = client.get(f"/api/prompts/{pack['id']}").json()["versions"][0]
    _decide_pending(client, version["id"])

    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": name}).json()
    graph = {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack["slug"]}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "out"}],
    }
    wf = client.post(f"/api/agents/{agent['id']}/workflows",
                     json={"name": f"{name}-wf", "graph": graph}).json()
    client.post(f"/api/workflows/{wf['id']}/versions/1/validate")
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    _decide_pending(client, wf["versions"][0]["id"])
    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/activate")
    return agent


def test_preview_requires_a_session(client):
    client.post("/api/auth/logout")
    agent_probe = client.get("/api/agents/00000000-0000-0000-0000-000000000000/deployments/admission")
    assert agent_probe.status_code in (401, 403)


def test_unknown_agent_is_404(client):
    login(client, "admin@platform.local")
    r = client.get("/api/agents/00000000-0000-0000-0000-000000000000/deployments/admission")
    assert r.status_code == 404


def test_invalid_channel_is_rejected(client):
    agent = _agent_with_active_workflow(client, "Preview Channel Agent")
    login(client, "admin@platform.local")
    r = client.get(f"/api/agents/{agent['id']}/deployments/admission?channel=staging")
    assert r.status_code == 422


def test_no_active_workflow_is_reported_not_crashed(client):
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Preview No Workflow"}).json()
    body = client.get(f"/api/agents/{agent['id']}/deployments/admission").json()
    assert body["allowed"] is False
    assert "no active workflow version" in " ".join(body["reasons"])
    assert body["evaluation"] is None


def test_sandbox_is_admissible_once_a_version_is_active(client):
    agent = _agent_with_active_workflow(client, "Preview Sandbox Agent")
    login(client, "admin@platform.local")
    body = client.get(
        f"/api/agents/{agent['id']}/deployments/admission?channel=sandbox").json()
    assert body["allowed"] is True, body["reasons"]


def test_production_names_every_unmet_requirement(client):
    """A draft agent should be told all of what's missing, not just the first."""
    agent = _agent_with_active_workflow(client, "Preview Production Agent")
    login(client, "admin@platform.local")
    body = client.get(
        f"/api/agents/{agent['id']}/deployments/admission?channel=production").json()
    assert body["allowed"] is False
    joined = " ".join(body["reasons"])
    assert "PRODUCTION lifecycle" in joined
    assert "no PASSING evaluation run" in joined
    assert "evidence pack" in joined
    assert "cost_center" in joined


def test_preview_is_read_only(client):
    """No deployment, and no audit row, may result from looking."""
    agent = _agent_with_active_workflow(client, "Preview ReadOnly Agent")
    login(client, "admin@platform.local")
    before = len(client.get(f"/api/audit?resource_id={agent['id']}").json())
    client.get(f"/api/agents/{agent['id']}/deployments/admission?channel=production")
    after = len(client.get(f"/api/audit?resource_id={agent['id']}").json())
    assert after == before, "the preview must not write audit rows"
    assert client.get(f"/api/agents/{agent['id']}/deployments").json() == []


def test_preview_reports_the_missing_evaluation_as_absent(client):
    agent = _agent_with_active_workflow(client, "Preview Eval Absent Agent")
    login(client, "admin@platform.local")
    body = client.get(
        f"/api/agents/{agent['id']}/deployments/admission?channel=production").json()
    assert body["evaluation"] is None, "absent must read as absent, never as a fabricated pass"
    assert body["workflow_version_id"] is not None


@pytest.mark.parametrize("channel", ["sandbox", "production"])
def test_preview_verdict_matches_what_deploy_actually_does(client, channel):
    """The anti-drift test: preview and deploy must not disagree."""
    agent = _agent_with_active_workflow(client, f"Preview Agreement {channel}")
    login(client, "admin@platform.local")
    group = client.post("/api/access-groups",
                        json={"name": f"pa-{channel}-{agent['slug'][:6]}"}).json()

    predicted = client.get(
        f"/api/agents/{agent['id']}/deployments/admission?channel={channel}").json()
    actual = client.post(f"/api/agents/{agent['id']}/deployments",
                         json={"channel": channel, "access_group_id": group["id"]})

    if predicted["allowed"]:
        assert actual.status_code == 201, actual.json()
    else:
        assert actual.status_code == 403, actual.json()
        assert set(actual.json()["detail"]["reasons"]) == set(predicted["reasons"]), \
            "preview reasons must be the deploy route's reasons, not a second copy of the rule"
