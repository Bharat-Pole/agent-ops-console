"""Version monotonicity across the shared approval queue.

The defect this pins down: `request_approval` supersedes pending steps only for
the SAME resource id, so a pending approval on v1 survives v2 being approved.
Deciding that stale item later ran `_flip_asset`, which deprecated *any* other
approved row of the family without comparing version numbers — letting an older
version supersede a newer one.

Approving must be monotonic. Rejecting a stale draft stays allowed, because
that is how a queue gets cleaned up.
"""
from __future__ import annotations

import pytest
from conftest import login

from app.adapters import models as adapters


@pytest.fixture(autouse=True)
def _clear_adapter():
    yield
    adapters.set_adapter_override(None)


def _pending_step(client, resource_id: str) -> dict:
    login(client, "governance@platform.local")
    steps = [a for a in client.get("/api/approvals").json()
             if a["resource_id"] == resource_id and a["status"] == "pending"]
    assert steps, f"no pending approval for {resource_id}"
    return steps[0]


def _decide(client, step_id: str, approve: bool = True):
    login(client, "governance@platform.local")
    return client.post(f"/api/approvals/{step_id}/decide", json={"approve": approve})


# ---- tools -------------------------------------------------------------------

def _tool_v1_v2(client, name: str) -> tuple[dict, dict, dict]:
    """v1 submitted (left pending), v2 created + submitted + approved."""
    login(client, "admin@platform.local")
    v1 = client.post("/api/tools", json={"name": name, "permission_type": "read"}).json()
    client.post(f"/api/tools/{v1['id']}/submit")
    stale_step = _pending_step(client, v1["id"])

    login(client, "admin@platform.local")
    v2 = client.post(f"/api/tools/{v1['id']}/new-version").json()
    client.post(f"/api/tools/{v2['id']}/submit")
    assert _decide(client, _pending_step(client, v2["id"])["id"]).json()["asset_status"] == "approved"
    return v1, v2, stale_step


def test_stale_tool_approval_cannot_regress_a_newer_version(client):
    v1, v2, stale = _tool_v1_v2(client, "Ordering Tool")

    r = _decide(client, stale["id"])
    assert r.status_code == 409, "approving a stale older version must be refused"
    assert "newer" in r.json()["detail"].lower()

    login(client, "admin@platform.local")
    tools = {t["id"]: t for t in client.get("/api/tools").json()}
    assert tools[v2["id"]]["status"] == "approved", "v2 must remain approved"
    assert tools[v2["id"]]["superseded_by"] is None, "v2 must not be superseded by v1"
    assert tools[v1["id"]]["status"] == "pending_approval", "v1 unchanged, still queued"


def test_stale_tool_request_can_still_be_rejected(client):
    """Rejecting an obsolete draft is how the queue gets cleaned up."""
    v1, v2, stale = _tool_v1_v2(client, "Ordering Reject Tool")
    r = _decide(client, stale["id"], approve=False)
    assert r.status_code == 200
    assert r.json()["asset_status"] == "rejected"

    login(client, "admin@platform.local")
    tools = {t["id"]: t for t in client.get("/api/tools").json()}
    assert tools[v2["id"]]["status"] == "approved"   # newer version untouched


# ---- prompts -----------------------------------------------------------------

def test_stale_prompt_version_approval_cannot_regress(client):
    login(client, "admin@platform.local")
    pack = client.post("/api/prompts", json={
        "name": "Ordering Prompt", "prompt_type": "system", "content": "v1"}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    v1_row = [v for v in client.get(f"/api/prompts/{pack['id']}").json()["versions"]
              if v["version"] == 1][0]
    stale = _pending_step(client, v1_row["id"])

    login(client, "admin@platform.local")
    client.post(f"/api/prompts/{pack['id']}/versions", json={"content": "v2"})
    client.post(f"/api/prompts/{pack['id']}/versions/2/submit")
    v2_row = [v for v in client.get(f"/api/prompts/{pack['id']}").json()["versions"]
              if v["version"] == 2][0]
    assert _decide(client, _pending_step(client, v2_row["id"])["id"]).json()["asset_status"] == "approved"

    assert _decide(client, stale["id"]).status_code == 409

    login(client, "admin@platform.local")
    versions = {v["version"]: v for v in client.get(f"/api/prompts/{pack['id']}").json()["versions"]}
    assert versions[2]["status"] == "approved"
    assert versions[1]["status"] == "pending_approval"


# ---- A2A cards ---------------------------------------------------------------

CARD = {"description": "ordering test", "capability_tier": "standardized",
        "discovery_only": True, "supported_tasks": ["t"], "skills": ["s"]}


def test_stale_agent_card_approval_cannot_regress(client):
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Ordering Card Agent"}).json()
    v1 = client.post(f"/api/a2a/agents/{agent['id']}/card", json=CARD).json()
    client.post(f"/api/a2a/cards/{v1['id']}/submit")
    stale = _pending_step(client, v1["id"])

    login(client, "admin@platform.local")
    v2 = client.post(f"/api/a2a/cards/{v1['id']}/new-version").json()
    client.post(f"/api/a2a/cards/{v2['id']}/submit")
    assert _decide(client, _pending_step(client, v2["id"])["id"]).json()["asset_status"] == "approved"

    assert _decide(client, stale["id"]).status_code == 409

    login(client, "admin@platform.local")
    cards = {c["id"]: c for c in client.get("/api/a2a/agent-cards").json()}
    assert cards[v2["id"]]["status"] == "approved"
    assert cards[v2["id"]]["superseded_by"] is None


# ---- workflows: verify their lifecycle is NOT affected ------------------------

def test_workflow_approval_is_not_version_regressive(client):
    """Workflow approval does not deprecate anything — superseding happens on
    ACTIVATE. Approving an older version is therefore legitimate (it is how a
    rollback candidate becomes activatable), so the guard must not block it."""
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Ordering WF Agent"}).json()
    pack = client.post("/api/prompts", json={
        "name": "Ordering WF Prompt", "prompt_type": "system", "content": "x"}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    _decide(client, _pending_step(client, [
        v for v in client.get(f"/api/prompts/{pack['id']}").json()["versions"]][0]["id"])["id"])

    graph = {"nodes": [
        {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack["slug"]}},
        {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}}],
        "edges": [{"from": "sys", "to": "out"}]}
    login(client, "admin@platform.local")
    wf = client.post(f"/api/agents/{agent['id']}/workflows",
                     json={"name": "ordering wf", "graph": graph}).json()
    client.post(f"/api/workflows/{wf['id']}/versions/1/validate")
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    v1_id = wf["versions"][0]["id"]
    stale = _pending_step(client, v1_id)

    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/fork")
    client.post(f"/api/workflows/{wf['id']}/versions/2/validate")
    client.post(f"/api/workflows/{wf['id']}/versions/2/submit")
    v2_id = [v for v in client.get(f"/api/workflows/{wf['id']}").json()["versions"]
             if v["version"] == 2][0]["id"]
    assert _decide(client, _pending_step(client, v2_id)["id"]).json()["asset_status"] == "approved"

    # still allowed: nothing is regressed by approving the older workflow version
    assert _decide(client, stale["id"]).status_code == 200
    login(client, "admin@platform.local")
    versions = {v["version"]: v for v in client.get(f"/api/workflows/{wf['id']}").json()["versions"]}
    assert versions[1]["status"] == "approved" and versions[2]["status"] == "approved"


# ---- normal progression must be untouched ------------------------------------

def test_normal_v1_then_v2_progression_still_works(client):
    login(client, "admin@platform.local")
    v1 = client.post("/api/tools", json={"name": "Ordering Normal Tool",
                                         "permission_type": "read"}).json()
    client.post(f"/api/tools/{v1['id']}/submit")
    assert _decide(client, _pending_step(client, v1["id"])["id"]).json()["asset_status"] == "approved"

    login(client, "admin@platform.local")
    v2 = client.post(f"/api/tools/{v1['id']}/new-version").json()
    client.post(f"/api/tools/{v2['id']}/submit")
    assert _decide(client, _pending_step(client, v2["id"])["id"]).json()["asset_status"] == "approved"

    login(client, "admin@platform.local")
    tools = {t["id"]: t for t in client.get("/api/tools").json()}
    assert tools[v2["id"]]["status"] == "approved"
    assert tools[v1["id"]]["status"] == "deprecated"          # normal superseding intact
    assert tools[v1["id"]]["superseded_by"] == v2["id"]


def test_rollback_as_a_higher_version_is_still_approvable(client):
    """Rollback creates a NEW higher version from older content — forward
    progression, so it must not be blocked."""
    login(client, "admin@platform.local")
    pack = client.post("/api/prompts", json={
        "name": "Ordering Rollback Prompt", "prompt_type": "system", "content": "good v1"}).json()
    client.post(f"/api/prompts/{pack['id']}/versions", json={"content": "bad v2"})
    client.post(f"/api/prompts/{pack['id']}/versions/2/submit")
    v2_row = [v for v in client.get(f"/api/prompts/{pack['id']}").json()["versions"]
              if v["version"] == 2][0]
    _decide(client, _pending_step(client, v2_row["id"])["id"])

    login(client, "admin@platform.local")
    v3 = client.post(f"/api/prompts/{pack['id']}/versions/1/rollback").json()
    assert v3["version"] == 3 and v3["content"] == "good v1"
    client.post(f"/api/prompts/{pack['id']}/versions/3/submit")
    assert _decide(client, _pending_step(client, v3["id"])["id"]).json()["asset_status"] == "approved"

    login(client, "admin@platform.local")
    versions = {v["version"]: v for v in client.get(f"/api/prompts/{pack['id']}").json()["versions"]}
    assert versions[3]["status"] == "approved"
    assert versions[2]["status"] == "deprecated"


def test_refused_stale_approval_writes_no_asset_mutation(client):
    v1, v2, stale = _tool_v1_v2(client, "Ordering NoMutate Tool")
    login(client, "admin@platform.local")
    before = client.get(f"/api/tools/{v2['id']}").json()
    _decide(client, stale["id"])
    after = client.get(f"/api/tools/{v2['id']}").json()
    assert after == before, "the refused decision must not touch the newer version"

    step = _pending_step(client, v1["id"])
    assert step["status"] == "pending", "the stale request remains queued, undecided"
