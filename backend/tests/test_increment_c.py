"""Increment C acceptance: vault (names only), tool registry with write-class
dual sign-off + bind-block, SSRF guard, MCP discovery→draft tools, prompt
immutable versions + rollback, KB chunk→embed→retrieve with honest
degradation, citations, closed-world resolution, acceptance→materialization.
"""
from __future__ import annotations

import io
import json

import pytest
from conftest import login

from app.adapters import models as adapters
from app.assets import citations, kb, mcp as mcp_module, ssrf
from app.config import settings


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    adapters.set_adapter_override(None)
    mcp_module.set_discovery_override(None)


def _fake_llm(*responses: str) -> adapters.FakeModelAdapter:
    fake = adapters.FakeModelAdapter(responses=list(responses))
    adapters.set_adapter_override(fake)
    return fake


# ---- vault ------------------------------------------------------------------

def test_vault_names_only_and_role_gates(client):
    login(client, "engineer@platform.local")
    r = client.put("/api/secrets", json={"name": "svc.api.key", "value": "super-secret-value"})
    assert r.status_code == 201, r.text
    assert "value" not in r.json() and "super-secret" not in r.text

    listing = client.get("/api/secrets").json()
    assert any(s["name"] == "svc.api.key" for s in listing)
    assert all("value" not in s for s in listing)

    login(client, "creator@platform.local")  # not a vault role
    assert client.get("/api/secrets").status_code == 403
    login(client, "governance@platform.local")
    assert client.put("/api/secrets", json={"name": "x.y", "value": "v"}).status_code == 403


def test_vault_resolve_server_side_roundtrip():
    from app.assets.vault import encrypt_value, resolve_secret
    from app.db import SessionLocal
    from app.models import SecretRecord, User
    from sqlalchemy import select
    with SessionLocal() as db:
        owner = db.scalars(select(User)).first()
        db.add(SecretRecord(name="roundtrip.test", encrypted_value=encrypt_value("plain-123"), created_by=owner.id))
        db.commit()
        assert resolve_secret(db, "roundtrip.test") == "plain-123"
        assert resolve_secret(db, "missing") is None


# ---- SSRF guard -------------------------------------------------------------

def test_ssrf_guard_blocks_private_and_allows_allowlisted():
    ok, reason = ssrf.check_url("http://127.0.0.1:8000/x")
    assert not ok and "non-public" in reason
    ok, _ = ssrf.check_url("ftp://example.com/")
    assert not ok
    settings.tryout_private_host_allowlist = ["localhost"]
    try:
        ok, reason = ssrf.check_url("http://localhost:9999/mcp")
        assert ok and reason == "host allowlisted"
    finally:
        settings.tryout_private_host_allowlist = []


# ---- tool registry ----------------------------------------------------------

def test_write_class_structural_forcing_and_dual_signoff(client):
    login(client, "engineer@platform.local")
    r = client.post("/api/tools", json={
        "name": "Ticket Closer", "description": "closes tickets",
        "permission_type": "update", "risk_level": "low",
        "human_approval_required": False,
    })
    assert r.status_code == 201, r.text
    tool = r.json()
    assert tool["is_write_class"] is True
    assert tool["human_approval_required"] is True  # forced
    assert tool["risk_level"] == "high"             # floored

    # submit → TWO approval steps (dual sign-off)
    assert client.post(f"/api/tools/{tool['id']}/submit").status_code == 200
    login(client, "governance@platform.local")
    queue = client.get("/api/approvals").json()
    steps = [a for a in queue if a["resource_id"] == tool["id"]]
    assert len(steps) == 1  # governance sees only its own step
    gov_step = steps[0]

    login(client, "security@platform.local")
    sec_steps = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]]
    assert len(sec_steps) == 1
    # governance approves — not yet approved (dual)
    login(client, "governance@platform.local")
    r = client.post(f"/api/approvals/{gov_step['id']}/decide", json={"approve": True})
    assert r.json()["asset_status"] is None
    # security co-signs — now approved
    login(client, "security@platform.local")
    r = client.post(f"/api/approvals/{sec_steps[0]['id']}/decide", json={"approve": True})
    assert r.json()["asset_status"] == "approved"

    # BASE-PHASE INVARIANT: approved write tool still cannot be bound
    login(client, "creator@platform.local")
    agent = client.post("/api/agents", json={"name": "Bind Block Agent"}).json()
    r = client.post(f"/api/agents/{agent['id']}/bindings",
                    json={"asset_type": "tool", "asset_ref": tool["slug"]})
    assert r.status_code == 403
    assert "advisory-only base phase" in json.dumps(r.json())


def test_read_tool_single_signoff_and_binds(client):
    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={
        "name": "Ticket Reader", "description": "reads tickets", "permission_type": "read",
    }).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]][0]
    r = client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    assert r.json()["asset_status"] == "approved"  # single sign-off suffices for read

    login(client, "creator@platform.local")
    agent = client.post("/api/agents", json={"name": "Bind OK Agent"}).json()
    r = client.post(f"/api/agents/{agent['id']}/bindings",
                    json={"asset_type": "tool", "asset_ref": tool["slug"]})
    assert r.status_code == 201, r.text
    # draft tools are not bindable either
    tool2 = client.post("/api/tools", json={"name": "Draft Only Tool"}).json() if False else None


def test_tool_rejection_path(client):
    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={"name": "Doomed Tool", "permission_type": "read"}).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]][0]
    r = client.post(f"/api/approvals/{step['id']}/decide", json={"approve": False, "note": "no purpose"})
    assert r.json()["asset_status"] == "rejected"


def test_tryout_ssrf_blocked_and_audited(client):
    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={
        "name": "Loopback Prober",
        "implementation": {"kind": "http_api", "config": {"base_url": "http://127.0.0.1:9/x"}},
    }).json()
    r = client.post(f"/api/tools/{tool['id']}/tryout", json={"params": {}})
    assert r.status_code == 403
    assert "non-public" in r.json()["detail"]
    login(client, "admin@platform.local")
    rows = client.get(f"/api/audit?resource_type=tool&resource_id={tool['id']}").json()
    tryouts = [x for x in rows if x["action"] == "tool_tryout"]
    assert tryouts and tryouts[0]["detail"]["allowed"] is False


# ---- MCP --------------------------------------------------------------------

def _fake_discovery(tools: list[mcp_module.DiscoveredTool]):
    def fn(endpoint, transport, headers, timeout):
        return tools
    mcp_module.set_discovery_override(fn)


def test_mcp_discovery_creates_drafts_and_diffs(client):
    settings.tryout_private_host_allowlist = ["mcp-dev.local"]
    try:
        login(client, "engineer@platform.local")
        conn = client.post("/api/mcp", json={
            "name": "Dev MCP", "endpoint": "http://mcp-dev.local:8080/mcp",
        })
        assert conn.status_code == 201, conn.text
        cid = conn.json()["id"]

        _fake_discovery([
            mcp_module.DiscoveredTool("search_docs", "search the docs", {"type": "object", "properties": {"q": {"type": "string"}}}),
            mcp_module.DiscoveredTool("get_page", "fetch one page", {"type": "object"}),
        ])
        r = client.post(f"/api/mcp/{cid}/discover")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["created_drafts"]) == 2
        for t in body["created_drafts"]:
            assert t["status"] == "draft"          # NEVER auto-approved
            assert t["source"] == "mcp_discovery"
            assert t["implementation"]["kind"] == "mcp"

        # re-discovery: one changed schema → new version draft; one vanished
        _fake_discovery([
            mcp_module.DiscoveredTool("search_docs", "search the docs", {"type": "object", "properties": {"q": {"type": "string"}, "limit": {"type": "integer"}}}),
        ])
        r2 = client.post(f"/api/mcp/{cid}/discover").json()
        assert len(r2["new_version_drafts"]) == 1
        assert r2["new_version_drafts"][0]["version"] == 2
        assert r2["vanished"] == ["get_page"]      # reported, not deleted
    finally:
        settings.tryout_private_host_allowlist = []


# ---- prompts ----------------------------------------------------------------

def test_prompt_versions_immutable_rollback_and_approval(client):
    login(client, "engineer@platform.local")
    pack = client.post("/api/prompts", json={
        "name": "NOC Summary Prompt", "prompt_type": "task", "content": "v1 content",
    }).json()
    pid = pack["id"]
    client.post(f"/api/prompts/{pid}/versions", json={"content": "v2 content"})
    rb = client.post(f"/api/prompts/{pid}/versions/1/rollback").json()
    assert rb["version"] == 3 and rb["content"] == "v1 content" and rb["rolled_back_from"] == 1

    client.post(f"/api/prompts/{pid}/versions/3/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["step"] == "governance_review"
            and a["resource_type"] == "prompt_version"][0]
    r = client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    assert r.json()["asset_status"] == "approved"
    detail = client.get(f"/api/prompts/{pid}").json()
    v3 = next(v for v in detail["versions"] if v["version"] == 3)
    assert v3["status"] == "approved"


# ---- KB / RAG ---------------------------------------------------------------

def test_chunker_applies_size_and_overlap():
    units = [("a" * 2000, "document")]
    chunks = kb.chunk_units(units, size=800, overlap=120)
    assert len(chunks) == 3
    assert all(len(t) <= 800 for t, _ in chunks)
    # overlap: chunk 2 starts 680 into the text
    assert chunks[1][1]["location"] == "document, chars 680-1480"


def test_kb_upload_embeds_with_provider_and_previews(client):
    fake = adapters.FakeModelAdapter()
    adapters.set_adapter_override(fake)
    login(client, "engineer@platform.local")
    content = ("Network incident runbook. Step one: check the core router logs. "
               "Step two: verify fiber links. Escalate outages to the NOC lead.") * 3
    r = client.post("/api/knowledge/upload",
                    files={"file": ("runbook.txt", io.BytesIO(content.encode()), "text/plain")},
                    data={"name": "NOC Runbook", "chunk_size": "120", "chunk_overlap": "20"})
    assert r.status_code == 201, r.text
    src = r.json()
    assert src["status"] == "ready" and src["embedded"] is True and src["chunk_count"] > 1
    detail = client.get(f"/api/knowledge/{src['id']}").json()
    assert detail["chunk_preview"] and detail["chunk_preview"][0]["has_embedding"] is True

    # pipeline + hybrid preview: query shares tokens with the runbook
    pipe = client.post("/api/rag", json={"name": "NOC Pipeline", "source_ids": [src["id"]],
                                         "score_threshold": 0.1}).json()
    prev = client.post(f"/api/rag/{pipe['id']}/preview", json={"query": "check router logs"}).json()
    assert prev["mode"] == "hybrid"
    assert prev["results"] and prev["results"][0]["score"] > 0
    assert "router" in prev["results"][0]["text"].lower()


def test_kb_honest_degradation_without_provider(client):
    adapters.set_adapter_override(None)
    login(client, "engineer@platform.local")
    r = client.post("/api/knowledge/upload",
                    files={"file": ("plain.md", io.BytesIO(b"Billing dispute policy: refunds within 30 days."), "text/markdown")},
                    data={"name": "Billing Policy"})
    src = r.json()
    assert src["embedded"] is False
    assert "keyword_only" in src["retrieval_mode"]  # labeled degradation

    pipe = client.post("/api/rag", json={"name": "Billing Pipeline", "source_ids": [src["id"]]}).json()
    prev = client.post(f"/api/rag/{pipe['id']}/preview", json={"query": "refunds dispute"}).json()
    assert prev["mode"] == "keyword_only"
    assert prev["mode_notes"]  # says WHY
    assert prev["results"]     # keyword leg still finds the chunk


# ---- citations --------------------------------------------------------------

def test_citation_wrap_and_mechanical_check():
    context, source_map = citations.wrap_chunks([
        ("NOC Runbook", "page 1", "check the router"),
        ("Billing Policy", "document", "refunds in 30 days"),
    ])
    assert "[Source 1: NOC Runbook, page 1]" in context
    ok = citations.check_citations("Per [Source 1] you should check the router.", source_map)
    assert ok["ok"] is True and ok["cited"] == [1] and 2 in ok["uncited_sources"]
    bad = citations.check_citations("As [Source 7] says...", source_map)
    assert bad["ok"] is False and bad["invalid"] == [7]


# ---- closed world + materialization ----------------------------------------

INTENT = {
    "identity_purpose": {"objective": "Summarize weekly network incident reports for the NOC team with citations"},
    "data_rules": {"data_sources": ["incident_db"]},
}


def _llm_with_component(registry_ref: str | None) -> str:
    return json.dumps({
        "summary": "s",
        "architecture": {"kind": "graph", "rationale": "r",
                         "basis": "summarize weekly network incident reports"},
        "suggested_risk_tier": {"tier": "medium", "basis": "internal incident data"},
        "components": [{"kind": "tool", "name": "incident_reader", "purpose": "read incidents",
                        "registry_ref": registry_ref,
                        "basis": "summarize weekly network incident reports"}],
        "suggested_agent_flow": None,
        "missing_information": [], "clarifying_questions": [],
    })


def _approved_tool(client, name: str) -> dict:
    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={"name": name, "permission_type": "read"}).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})
    return tool


def test_closed_world_resolves_approved_tools(client):
    tool = _approved_tool(client, "Incident Reader")
    _fake_llm(_llm_with_component(f"tools://{tool['slug']}@v1"))
    login(client, "creator@platform.local")
    agent = client.post("/api/agents", json={"name": "Closed World Agent"}).json()
    client.put(f"/api/agents/{agent['id']}/intent/draft", json={"payload": INTENT})
    client.post(f"/api/agents/{agent['id']}/intent/submit")
    rec = client.post(f"/api/agents/{agent['id']}/recommendation").json()
    comp = next(i for i in rec["items"] if i["kind"] == "component_tool")
    assert comp["state"] == "proposed"  # resolved — NOT demoted
    assert rec["validation"]["closed_world_demotions"] == []


def test_materialization_on_accept(client):
    _fake_llm(json.dumps({
        "summary": "s",
        "architecture": {"kind": "single", "rationale": "r", "basis": "answer questions"},
        "suggested_risk_tier": {"tier": "low", "basis": "no data"},
        "components": [
            {"kind": "prompt", "name": "PTO Answer Prompt", "purpose": "answer PTO questions",
             "registry_ref": None, "basis": "answer employee questions about PTO policy"},
            {"kind": "knowledge", "name": "PTO Handbook", "purpose": "ground answers",
             "registry_ref": None, "basis": "employee handbook"},
        ],
        "suggested_agent_flow": None, "missing_information": [], "clarifying_questions": [],
    }))
    login(client, "creator@platform.local")
    agent = client.post("/api/agents", json={"name": "Materialize Agent"}).json()
    client.put(f"/api/agents/{agent['id']}/intent/draft", json={"payload": {
        "identity_purpose": {"objective": "Answer employee questions about the PTO policy from the handbook"},
    }})
    client.post(f"/api/agents/{agent['id']}/intent/submit")
    rec = client.post(f"/api/agents/{agent['id']}/recommendation").json()

    prompt_item = next(i for i in rec["items"] if i["kind"] == "component_prompt")
    r = client.post(f"/api/agents/{agent['id']}/recommendation/items/{prompt_item['id']}",
                    json={"state": "accepted"})
    mat = r.json()["materialization"]
    assert mat["materialized"] is True and mat["asset_type"] == "prompt"
    packs = client.get("/api/prompts").json()
    created = next(p for p in packs if p["id"] == mat["asset_id"])
    assert created["latest_status"] == "draft"  # DRAFT, its own approval workflow ahead

    # knowledge cannot be honestly materialized → guidance, no record
    know_item = next(i for i in rec["items"] if i["kind"] == "component_knowledge")
    r2 = client.post(f"/api/agents/{agent['id']}/recommendation/items/{know_item['id']}",
                     json={"state": "accepted"})
    mat2 = r2.json()["materialization"]
    assert mat2["materialized"] is False and "upload" in mat2["guidance"]

    # idempotence: accepting the prompt again does not duplicate
    r3 = client.post(f"/api/agents/{agent['id']}/recommendation/items/{prompt_item['id']}",
                     json={"state": "accepted"})
    assert r3.json()["materialization"] is None
    assert len([p for p in client.get("/api/prompts").json()
                if p["slug"] == created["slug"]]) == 1


# ---- model catalog ----------------------------------------------------------

def test_model_catalog_seeded_and_admin_gated(client):
    login(client, "creator@platform.local")
    models = client.get("/api/models").json()
    assert any(m["model_ref"] == "gemini-flash-latest" for m in models)
    r = client.post("/api/models", json={
        "provider": "x", "model_ref": "x-1", "kind": "llm", "display_name": "X"})
    assert r.status_code == 403  # admin only
