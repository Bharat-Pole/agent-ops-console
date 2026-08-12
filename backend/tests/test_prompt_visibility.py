"""Read-only visibility surfaces: prompt version comparison, computed prompt
usage, and paginated chunk browsing.

The defining property of all three is that they only READ. Each test group
asserts the absence of side effects as explicitly as it asserts the returned
data, because a "view" that quietly writes is how governed state rots.
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


# ---- helpers ----------------------------------------------------------------

def _pack(client, name: str, content: str = "v1 content") -> dict:
    login(client, "admin@platform.local")
    return client.post("/api/prompts", json={
        "name": name, "prompt_type": "system", "content": content,
        "variables": ["tone"],
    }).json()


def _approve_latest_prompt(client, pack_id: str, version: int) -> None:
    login(client, "admin@platform.local")
    client.post(f"/api/prompts/{pack_id}/versions/{version}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_type"] == "prompt_version" and a["status"] == "pending"][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})


# ---- Feature 1: version comparison ------------------------------------------

def test_compare_two_versions_reports_changed_fields(client):
    pack = _pack(client, "Compare Pack", "original body")
    login(client, "admin@platform.local")
    client.post(f"/api/prompts/{pack['id']}/versions",
                json={"content": "revised body", "variables": ["tone", "audience"],
                      "notes": "second pass"})

    r = client.get(f"/api/prompts/{pack['id']}/versions/1/compare/2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["a"]["version"] == 1 and body["b"]["version"] == 2
    assert body["a"]["content"] == "original body"
    assert body["b"]["content"] == "revised body"
    assert "content" in body["changed_fields"]
    assert "variables" in body["changed_fields"]   # variable differences visible
    assert "notes" in body["changed_fields"]
    assert body["identical"] is False


def test_compare_identical_versions(client):
    pack = _pack(client, "Identical Pack", "same body")
    login(client, "admin@platform.local")
    # rollback produces a version with identical content to v1
    client.post(f"/api/prompts/{pack['id']}/versions/1/rollback")
    body = client.get(f"/api/prompts/{pack['id']}/versions/1/compare/2").json()
    assert body["a"]["content"] == body["b"]["content"]
    assert "content" not in body["changed_fields"]


def test_compare_rejects_version_from_another_pack(client):
    pack_a = _pack(client, "Compare Scope A")
    pack_b = _pack(client, "Compare Scope B")
    login(client, "admin@platform.local")
    client.post(f"/api/prompts/{pack_b['id']}/versions", json={"content": "b v2"})
    # pack B has a version 2; pack A does not — the lookup is pack-scoped
    r = client.get(f"/api/prompts/{pack_a['id']}/versions/1/compare/2")
    assert r.status_code == 404
    assert "does not belong to this prompt pack" in r.json()["detail"]


def test_compare_rejects_nonexistent_version_and_pack(client):
    pack = _pack(client, "Compare Missing Pack")
    login(client, "admin@platform.local")
    assert client.get(f"/api/prompts/{pack['id']}/versions/1/compare/99").status_code == 404
    import uuid as uuid_mod
    assert client.get(
        f"/api/prompts/{uuid_mod.uuid4()}/versions/1/compare/2").status_code == 404


def test_compare_creates_no_version_and_moves_no_approval(client):
    pack = _pack(client, "Compare NoWrite Pack")
    login(client, "admin@platform.local")
    client.post(f"/api/prompts/{pack['id']}/versions", json={"content": "v2"})
    _approve_latest_prompt(client, pack["id"], 2)

    login(client, "admin@platform.local")
    before = client.get(f"/api/prompts/{pack['id']}").json()
    client.get(f"/api/prompts/{pack['id']}/versions/1/compare/2")
    after = client.get(f"/api/prompts/{pack['id']}").json()

    assert len(after["versions"]) == len(before["versions"]) == 2  # no new version
    assert [v["status"] for v in after["versions"]] == [v["status"] for v in before["versions"]]
    assert [v["updated_at"] if "updated_at" in v else v["created_at"] for v in after["versions"]] \
        == [v["updated_at"] if "updated_at" in v else v["created_at"] for v in before["versions"]]


def test_compare_requires_a_session(client):
    pack = _pack(client, "Compare Auth Pack")
    client.post("/api/auth/logout")
    assert client.get(f"/api/prompts/{pack['id']}/versions/1/compare/1").status_code == 401


# ---- Feature 2: computed usage ----------------------------------------------

def _agent_with_workflow_using(client, agent_name: str, pack_slug: str,
                              activate: bool = True) -> dict:
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": agent_name}).json()
    wf = client.post(f"/api/agents/{agent['id']}/workflows", json={
        "name": f"{agent_name} flow", "graph": {
            "nodes": [
                {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack_slug}},
                {"id": "gen", "type": "llm", "label": "", "config": {}},
                {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
            ],
            "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "out"}],
        }}).json()
    if activate:
        client.post(f"/api/workflows/{wf['id']}/versions/1/validate")
        client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
        login(client, "governance@platform.local")
        step = [a for a in client.get("/api/approvals").json()
                if a["resource_type"] == "workflow_version" and a["status"] == "pending"][0]
        client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
        login(client, "admin@platform.local")
        client.post(f"/api/workflows/{wf['id']}/versions/1/activate")
    return {"agent": agent, "workflow": wf}


def test_usage_detects_active_workflow_reference(client):
    pack = _pack(client, "Usage Workflow Pack")
    _approve_latest_prompt(client, pack["id"], 1)
    built = _agent_with_workflow_using(client, "Usage WF Agent", pack["slug"])

    login(client, "admin@platform.local")
    usage = client.get(f"/api/prompts/{pack['id']}/usage").json()
    active = usage["active"]["workflow_versions"]
    assert len(active) == 1
    assert active[0]["agent_id"] == built["agent"]["id"]
    assert active[0]["workflow_status"] == "active"
    assert active[0]["reference_type"] == "workflow_node"
    assert usage["historical"]["workflow_versions"] == []


def test_usage_separates_historical_from_active(client):
    """A draft workflow references the pack but is not live — it must not be
    presented as current usage."""
    pack = _pack(client, "Usage Draft Pack")
    _approve_latest_prompt(client, pack["id"], 1)
    _agent_with_workflow_using(client, "Usage Draft Agent", pack["slug"], activate=False)

    login(client, "admin@platform.local")
    usage = client.get(f"/api/prompts/{pack['id']}/usage").json()
    assert usage["active"]["workflow_versions"] == []
    assert len(usage["historical"]["workflow_versions"]) == 1
    assert usage["historical"]["workflow_versions"][0]["workflow_status"] == "draft"
    assert usage["totals"]["active"] == 0 and usage["totals"]["historical"] == 1


def test_usage_detects_asset_binding(client):
    pack = _pack(client, "Usage Binding Pack")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Usage Binding Agent"}).json()
    r = client.post(f"/api/agents/{agent['id']}/bindings",
                    json={"asset_type": "prompt", "asset_ref": pack["slug"]})
    assert r.status_code == 201, r.text

    usage = client.get(f"/api/prompts/{pack['id']}/usage").json()
    bindings = usage["active"]["bindings"]
    assert len(bindings) == 1
    assert bindings[0]["agent_id"] == agent["id"]
    assert bindings[0]["version_policy"] == "latest_approved"
    assert bindings[0]["reference_type"] == "binding"


def test_usage_reports_multiple_references_together(client):
    pack = _pack(client, "Usage Multi Pack")
    _approve_latest_prompt(client, pack["id"], 1)
    _agent_with_workflow_using(client, "Usage Multi WF Agent", pack["slug"])
    login(client, "admin@platform.local")
    other = client.post("/api/agents", json={"name": "Usage Multi Bind Agent"}).json()
    client.post(f"/api/agents/{other['id']}/bindings",
                json={"asset_type": "prompt", "asset_ref": pack["slug"]})

    usage = client.get(f"/api/prompts/{pack['id']}/usage").json()
    assert usage["totals"]["active"] == 2
    assert len(usage["active"]["workflow_versions"]) == 1
    assert len(usage["active"]["bindings"]) == 1


def test_unused_pack_reports_nothing(client):
    pack = _pack(client, "Usage Unused Pack")
    login(client, "admin@platform.local")
    usage = client.get(f"/api/prompts/{pack['id']}/usage").json()
    assert usage["totals"] == {"active": 0, "historical": 0}


def test_usage_persists_no_state_and_mutates_nothing(client):
    pack = _pack(client, "Usage NoWrite Pack")
    _approve_latest_prompt(client, pack["id"], 1)
    _agent_with_workflow_using(client, "Usage NoWrite Agent", pack["slug"])

    login(client, "admin@platform.local")
    before_pack = client.get(f"/api/prompts/{pack['id']}").json()
    before_audit = len(client.get(
        f"/api/audit?resource_type=prompt&resource_id={pack['id']}").json())

    client.get(f"/api/prompts/{pack['id']}/usage")
    client.get(f"/api/prompts/{pack['id']}/usage")  # twice — still no writes

    after_pack = client.get(f"/api/prompts/{pack['id']}").json()
    after_audit = len(client.get(
        f"/api/audit?resource_type=prompt&resource_id={pack['id']}").json())

    assert after_pack == before_pack          # no field changed, no timestamp moved
    assert after_audit == before_audit        # viewing is not an audited event
    # and no persisted usage field was introduced anywhere on the payload
    assert "used_by" not in str(after_pack)


def test_usage_requires_a_session_and_handles_missing_pack(client):
    import uuid as uuid_mod
    login(client, "admin@platform.local")
    assert client.get(f"/api/prompts/{uuid_mod.uuid4()}/usage").status_code == 404
    client.post("/api/auth/logout")
    assert client.get(f"/api/prompts/{uuid_mod.uuid4()}/usage").status_code == 401


# ---- Feature 3: paginated chunk browsing ------------------------------------

def _source_with_chunks(client, name: str, body: bytes, chunk_size: int = 40) -> dict:
    adapters.set_adapter_override(adapters.FakeModelAdapter())
    login(client, "admin@platform.local")
    return client.post("/api/knowledge/upload",
                       files={"file": (f"{name}.txt", io.BytesIO(body), "text/plain")},
                       data={"name": name, "chunk_size": str(chunk_size),
                             "chunk_overlap": "0"}).json()


def test_chunk_pages_are_deterministic_and_ordered(client):
    source = _source_with_chunks(client, "Chunk Browse Source", b"x" * 400, chunk_size=40)
    assert source["chunk_count"] == 10

    page1 = client.get(f"/api/knowledge/{source['id']}/chunks?offset=0&limit=4").json()
    assert page1["total"] == 10 and page1["offset"] == 0 and page1["limit"] == 4
    assert [c["ord"] for c in page1["items"]] == [0, 1, 2, 3]

    page2 = client.get(f"/api/knowledge/{source['id']}/chunks?offset=4&limit=4").json()
    assert [c["ord"] for c in page2["items"]] == [4, 5, 6, 7]

    last = client.get(f"/api/knowledge/{source['id']}/chunks?offset=8&limit=4").json()
    assert [c["ord"] for c in last["items"]] == [8, 9]   # partial final page

    # repeatable
    assert client.get(f"/api/knowledge/{source['id']}/chunks?offset=0&limit=4").json() == page1


def test_chunk_fields_include_text_location_and_embedding_state(client):
    source = _source_with_chunks(client, "Chunk Fields Source",
                                 b"Check the core router logs and verify fiber links.")
    item = client.get(f"/api/knowledge/{source['id']}/chunks").json()["items"][0]
    assert "router logs" in item["text"]
    assert item["location"].startswith("document, chars")
    assert item["has_embedding"] is True
    assert "embedding" not in item     # vectors themselves are not exposed


def test_chunk_limit_is_bounded(client):
    source = _source_with_chunks(client, "Chunk Limit Source", b"y" * 200, chunk_size=40)
    assert client.get(f"/api/knowledge/{source['id']}/chunks?limit=201").status_code == 422
    assert client.get(f"/api/knowledge/{source['id']}/chunks?limit=200").status_code == 200
    assert client.get(f"/api/knowledge/{source['id']}/chunks?limit=0").status_code == 422
    assert client.get(f"/api/knowledge/{source['id']}/chunks?offset=-1").status_code == 422


def test_chunk_browsing_beyond_the_end_is_empty_not_an_error(client):
    source = _source_with_chunks(client, "Chunk Past End Source", b"z" * 80, chunk_size=40)
    page = client.get(f"/api/knowledge/{source['id']}/chunks?offset=999&limit=10").json()
    assert page["items"] == [] and page["total"] == 2


def test_chunk_browsing_missing_source_and_auth(client):
    import uuid as uuid_mod
    login(client, "admin@platform.local")
    assert client.get(f"/api/knowledge/{uuid_mod.uuid4()}/chunks").status_code == 404
    client.post("/api/auth/logout")
    assert client.get(f"/api/knowledge/{uuid_mod.uuid4()}/chunks").status_code == 401


def test_chunk_browsing_mutates_nothing(client):
    source = _source_with_chunks(client, "Chunk NoWrite Source", b"w" * 120, chunk_size=40)
    login(client, "admin@platform.local")
    before = client.get(f"/api/knowledge/{source['id']}").json()
    client.get(f"/api/knowledge/{source['id']}/chunks?offset=0&limit=50")
    after = client.get(f"/api/knowledge/{source['id']}").json()
    assert after == before   # chunk_count, status, embedded, error all unchanged
