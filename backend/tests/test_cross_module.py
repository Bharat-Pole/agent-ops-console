"""Cross-module invariants that per-domain tests cannot see.

Each one checks a claim the architecture makes about how two subsystems relate:
that a disabled connector stops execution before any remote call; that A2A
readiness is genuinely derived rather than cached; that a deployment manifest
stays frozen when its assets move on; and that prompt usage sees deployment
pins, not only bindings and workflow graphs.
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


def _decide_pending(client, resource_id: str, approve: bool = True) -> dict:
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json()
            if a["resource_id"] == resource_id and a["status"] == "pending"][0]
    return client.post(f"/api/approvals/{step['id']}/decide", json={"approve": approve}).json()


def _approved_prompt(client, name: str, content: str = "You are terse.") -> dict:
    login(client, "admin@platform.local")
    pack = client.post("/api/prompts", json={
        "name": name, "prompt_type": "system", "content": content}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    version = client.get(f"/api/prompts/{pack['id']}").json()["versions"][0]
    _decide_pending(client, version["id"])
    return pack


def _approved_tool(client, name: str) -> dict:
    login(client, "admin@platform.local")
    tool = client.post("/api/tools", json={"name": name, "permission_type": "read"}).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    _decide_pending(client, tool["id"])
    return tool


def _active_workflow(client, agent_id: str, name: str, graph: dict) -> dict:
    login(client, "admin@platform.local")
    wf = client.post(f"/api/agents/{agent_id}/workflows",
                     json={"name": name, "graph": graph}).json()
    validated = client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json()
    assert validated["status"] == "validated", validated["validation"]
    client.post(f"/api/workflows/{wf['id']}/versions/1/submit")
    _decide_pending(client, wf["versions"][0]["id"])
    login(client, "admin@platform.local")
    client.post(f"/api/workflows/{wf['id']}/versions/1/activate")
    return wf


def _simple_graph(pack_slug: str) -> dict:
    return {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack_slug}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
        ],
        "edges": [{"from": "sys", "to": "gen"}, {"from": "gen", "to": "out"}],
    }


def _to_production(client, agent_id: str) -> None:
    login(client, "admin@platform.local")
    for target in ("sandbox", "candidate", "approved_prototype"):
        client.post(f"/api/agents/{agent_id}/transition", json={"to": target})
    login(client, "governance@platform.local")
    client.post("/api/governance/exceptions", json={
        "agent_id": agent_id, "reason": "cross-module integration test agent", "expires_days": 7})
    client.post(f"/api/agents/{agent_id}/transition", json={"to": "production_candidate"})
    client.post(f"/api/agents/{agent_id}/transition", json={"to": "production"})


# ---- 1. disabled MCP connector stops execution before the remote call --------

def test_disabled_mcp_connector_blocks_execution_before_any_remote_call(client, monkeypatch):
    """A disabled connector must be refused by OUR code, not by the network."""
    from app.assets import mcp as mcp_module
    from app.config import settings
    from app.db import SessionLocal
    from app.models import McpConnector
    import uuid as uuid_mod

    calls: list[str] = []
    settings.tryout_private_host_allowlist = ["mcp-x.local"]
    try:
        mcp_module.set_discovery_override(lambda *a, **k: [
            mcp_module.DiscoveredTool("echo", "echoes input", {"type": "object"})])

        login(client, "admin@platform.local")
        conn = client.post("/api/mcp", json={
            "name": "Disabled Conn Test", "endpoint": "http://mcp-x.local:9000/mcp"}).json()
        discovered = client.post(f"/api/mcp/{conn['id']}/discover").json()
        tool = discovered["created_drafts"][0]
        client.post(f"/api/tools/{tool['id']}/submit")
        _decide_pending(client, tool["id"])

        # count any attempt to reach the remote server
        import app.engine.handlers as handlers
        original = handlers._call_mcp_tool

        def spy(db, tool_rec, args):
            calls.append(tool_rec.slug)
            return original(db, tool_rec, args)
        monkeypatch.setattr(handlers, "_call_mcp_tool", spy)

        pack = _approved_prompt(client, "Disabled Conn Prompt")
        login(client, "admin@platform.local")
        agent = client.post("/api/agents", json={"name": "Disabled Conn Agent"}).json()
        graph = _simple_graph(pack["slug"])
        graph["nodes"].insert(2, {"id": "call", "type": "mcp_call", "label": "",
                                  "config": {"tool_ref": tool["slug"]}})
        graph["edges"] = [{"from": "sys", "to": "call"}, {"from": "call", "to": "gen"},
                          {"from": "gen", "to": "out"}]
        wf = _active_workflow(client, agent["id"], "disabled-conn-wf", graph)

        # disable the connector directly (no disable endpoint exists yet)
        with SessionLocal() as db:
            row = db.get(McpConnector, uuid_mod.UUID(conn["id"]))
            row.status = "disabled"
            db.commit()

        adapters.set_adapter_override(adapters.FakeModelAdapter(responses=["answer"]))
        login(client, "admin@platform.local")
        run = client.post(f"/api/agents/{agent['id']}/runs", json={"input": "hello"}).json()

        assert run["status"] == "failed"
        step = next(s for s in run["steps"] if s["node_id"] == "call")
        assert step["status"] == "failed"
        # the refusal came from OUR status check, before any network attempt
        assert "connector unavailable" in step["detail"]["error"]
        assert calls, "the MCP handler should have been entered and then refused"
        assert not any(s["node_type"] == "llm" for s in run["steps"]), \
            "execution must stop at the disabled connector"
    finally:
        settings.tryout_private_host_allowlist = []
        mcp_module.set_discovery_override(None)


# ---- 2. A2A readiness is derived, not cached --------------------------------

CARD = {"description": "cross-module", "capability_tier": "advanced",
        "discovery_only": False, "artifact_exchange": True, "artifact_format": "json",
        "supported_tasks": ["summarize"], "skills": ["ops"]}


def test_a2a_readiness_follows_deployment_state(client):
    """Same approved card; discoverability must change when deployment does."""
    pack = _approved_prompt(client, "Readiness Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Readiness Agent"}).json()
    client.patch(f"/api/agents/{agent['id']}", json={"cost_center": "ops"})
    _active_workflow(client, agent["id"], "readiness-wf", _simple_graph(pack["slug"]))

    login(client, "admin@platform.local")
    card = client.post(f"/api/a2a/agents/{agent['id']}/card", json=CARD).json()
    client.post(f"/api/a2a/cards/{card['id']}/submit")
    _decide_pending(client, card["id"])
    _to_production(client, agent["id"])

    # a non-discovery-only card needs a live deployment
    login(client, "admin@platform.local")
    before = client.get(f"/api/a2a/agents/{agent['id']}/card").json()["readiness"]
    assert before["discoverable"] is False
    assert any("no active deployment" in r for r in before["reasons"])

    group = client.post("/api/access-groups", json={"name": f"rd-{agent['slug'][:8]}"}).json()
    deployment = client.post(f"/api/agents/{agent['id']}/deployments", json={
        "channel": "sandbox", "access_group_id": group["id"]}).json()

    after = client.get(f"/api/a2a/agents/{agent['id']}/card").json()["readiness"]
    assert after["discoverable"] is True, after["reasons"]
    assert any(c["agent_id"] == agent["id"] for c in client.get("/api/a2a/discover").json())

    # superseding the deployment flips readiness back — nothing was cached
    from app.db import SessionLocal
    from app.models import Deployment
    import uuid as uuid_mod
    with SessionLocal() as db:
        row = db.get(Deployment, uuid_mod.UUID(deployment["id"]))
        row.status = "superseded"
        db.commit()

    final = client.get(f"/api/a2a/agents/{agent['id']}/card").json()["readiness"]
    assert final["discoverable"] is False, "readiness must be recomputed, not cached"
    assert final["card_approved"] is True, "the card itself is untouched"


# ---- 3. deployment manifests are immutable snapshots -------------------------

def test_tool_superseding_does_not_alter_an_existing_deployment(client):
    pack = _approved_prompt(client, "Snapshot Prompt")
    tool = _approved_tool(client, "Snapshot Tool")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Snapshot Agent"}).json()
    client.patch(f"/api/agents/{agent['id']}", json={"cost_center": "ops"})

    graph = _simple_graph(pack["slug"])
    graph["nodes"].insert(1, {"id": "call", "type": "tool_call", "label": "",
                              "config": {"tool_ref": tool["slug"]}})
    graph["edges"] = [{"from": "sys", "to": "call"}, {"from": "call", "to": "gen"},
                      {"from": "gen", "to": "out"}]
    _active_workflow(client, agent["id"], "snapshot-wf", graph)

    login(client, "admin@platform.local")
    group = client.post("/api/access-groups", json={"name": f"sn-{agent['slug'][:8]}"}).json()
    deployment = client.post(f"/api/agents/{agent['id']}/deployments", json={
        "channel": "sandbox", "access_group_id": group["id"]}).json()
    pinned_v1 = deployment["asset_pins"]["tools"][tool["slug"]]["version"]
    assert pinned_v1 == 1

    # approve tool v2 — the live registry moves on
    login(client, "admin@platform.local")
    v2 = client.post(f"/api/tools/{tool['id']}/new-version").json()
    client.post(f"/api/tools/{v2['id']}/submit")
    assert _decide_pending(client, v2["id"])["asset_status"] == "approved"

    login(client, "admin@platform.local")
    current = [d for d in client.get(f"/api/agents/{agent['id']}/deployments").json()
               if d["id"] == deployment["id"]][0]
    assert current["asset_pins"]["tools"][tool["slug"]]["version"] == 1, \
        "an existing manifest must not be rewritten when an asset is superseded"
    assert current["status"] == "active"


# ---- 4. prompt usage sees deployment pins ------------------------------------

def test_prompt_usage_reports_deployment_pin(client):
    pack = _approved_prompt(client, "Usage Pin Prompt")
    login(client, "admin@platform.local")
    agent = client.post("/api/agents", json={"name": "Usage Pin Agent"}).json()
    client.patch(f"/api/agents/{agent['id']}", json={"cost_center": "ops"})
    _active_workflow(client, agent["id"], "usage-pin-wf", _simple_graph(pack["slug"]))

    login(client, "admin@platform.local")
    group = client.post("/api/access-groups", json={"name": f"up-{agent['slug'][:8]}"}).json()
    deployment = client.post(f"/api/agents/{agent['id']}/deployments", json={
        "channel": "sandbox", "access_group_id": group["id"]}).json()

    usage = client.get(f"/api/prompts/{pack['id']}/usage").json()
    pins = usage["active"]["deployments"]
    assert len(pins) == 1, "the deployment pin must appear as active usage"
    assert pins[0]["deployment_id"] == deployment["id"]
    assert pins[0]["reference_type"] == "deployment_pin"
    assert pins[0]["pinned_version"] == 1
    assert pins[0]["deployment_status"] == "active"

    # a superseded deployment must fall to historical, not vanish
    from app.db import SessionLocal
    from app.models import Deployment
    import uuid as uuid_mod
    with SessionLocal() as db:
        row = db.get(Deployment, uuid_mod.UUID(deployment["id"]))
        row.status = "superseded"
        db.commit()

    usage2 = client.get(f"/api/prompts/{pack['id']}/usage").json()
    assert usage2["active"]["deployments"] == []
    assert len(usage2["historical"]["deployments"]) == 1
    assert usage2["historical"]["deployments"][0]["deployment_status"] == "superseded"
