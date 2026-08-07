"""Tool execution details that make a real tool-using agent possible:
state templating in params/args, static headers from persisted config, and
fail-at-validation (not at run time) for implementation kinds the engine
cannot execute.
"""
from __future__ import annotations

import pytest
from conftest import login

from app.adapters import models as adapters
from app.engine.handlers import extract_response, render_template_values, render_tool_results


def test_response_extraction_shapes_api_json_for_the_model():
    payload = ('{"query": {"pages": [{"title": "A", "extract": "<b>alpha</b> text", "ns": 0},'
               ' {"title": "B", "extract": "beta text"}]}}')
    text, err = extract_response(payload, {"path": "query.pages",
                                           "fields": ["title", "extract"], "limit": 5})
    assert err is None
    assert "title: A" in text and "alpha text" in text  # html stripped
    assert "ns: 0" not in text                          # unselected fields dropped
    assert "title: B" in text


def test_extraction_failures_are_reported_not_swallowed():
    text, err = extract_response("not json at all", {"path": "a"})
    assert text is None and "not JSON" in err
    text, err = extract_response('{"a": 1}', {"path": "missing.key"})
    assert text is None and "not found" in err


def test_zero_results_is_distinguished_from_a_broken_extract_spec():
    """An empty search must not read as a config error — that sends people
    debugging their extract spec when the API simply found nothing."""
    text, err = extract_response('{"items": []}', {"path": "items", "fields": ["title"]})
    assert text is None
    assert "zero results" in err
    # a genuinely unrenderable item is still reported as such
    text, err = extract_response('{"items": [{"other": "x"}]}',
                                 {"path": "items", "fields": ["title"]})
    assert text is None and "no content" in err


def test_tool_results_render_states_in_words():
    rendered = render_tool_results([
        {"tool": "writer", "refused": True, "reasons": ["write-class refused"]},
        {"tool": "stub", "connected": False, "note": "implementation 'none'"},
        {"tool": "search", "extracted": "- title: A"},
        {"tool": "raw", "body_preview": "{...}", "extract_error": "path not found"},
    ])
    assert "REFUSED BY POLICY" in rendered and "write-class refused" in rendered
    assert "NOT CONNECTED" in rendered
    assert "- title: A" in rendered
    assert "extraction failed: path not found" in rendered


@pytest.fixture(autouse=True)
def _clear_adapter():
    yield
    adapters.set_adapter_override(None)


def test_template_rendering_is_a_closed_set():
    state = {"user_input": "who won?", "llm_output": "nobody"}
    used: list[str] = []
    rendered = render_template_values(
        {"q": "{{user_input}}", "n": 5, "nested": {"a": "x {{llm_output}}"},
         "untouched": "{{secret_env}}"},
        state, used,
    )
    assert rendered["q"] == "who won?"
    assert rendered["nested"]["a"] == "x nobody"
    assert rendered["n"] == 5                       # non-strings pass through
    assert rendered["untouched"] == "{{secret_env}}"  # unknown names are NOT substituted
    assert sorted(set(used)) == ["llm_output", "user_input"]


def test_registry_rejects_non_executable_implementation_kind(client):
    login(client, "engineer@platform.local")
    r = client.post("/api/tools", json={
        "name": "Vaporware Tool",
        "implementation": {"kind": "builtin:web_search", "config": {}},
    })
    assert r.status_code == 422
    assert "implementation.kind must be one of" in r.json()["detail"]


def test_workflow_validation_flags_stub_tool_as_warning(client):
    """A tool with implementation 'none' is legal but must be labeled: it
    returns a not-connected stub, and the builder is told so before approval."""
    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={"name": "Unwired Tool", "permission_type": "read"}).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})

    login(client, "engineer@platform.local")
    pack = client.post("/api/prompts", json={"name": "Stub Warn Prompt", "prompt_type": "system",
                                             "content": "You are terse."}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    pstep = [a for a in client.get("/api/approvals").json()
             if a["resource_type"] == "prompt_version"][0]
    client.post(f"/api/approvals/{pstep['id']}/decide", json={"approve": True})

    login(client, "creator@platform.local")
    aid = client.post("/api/agents", json={"name": "Stub Warning Agent"}).json()["id"]
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "stub-wf", "graph": {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack["slug"]}},
            {"id": "call", "type": "tool_call", "label": "", "config": {"tool_ref": tool["slug"]}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {}},
        ],
        "edges": [{"from": "sys", "to": "call"}, {"from": "call", "to": "gen"},
                  {"from": "gen", "to": "out"}],
    }}).json()
    result = client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json()
    assert result["status"] == "validated"  # legal
    assert any("not-connected stub" in w for w in result["validation"]["warnings"])


def test_tool_params_carry_the_users_question(client, monkeypatch):
    """The whole point of a search agent: the live request's text reaches the
    tool. Outbound HTTP is stubbed so the assertion is about OUR wiring."""
    import httpx

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = '{"results": [{"title": "Answer article", "snippet": "the answer is 42"}]}'
        headers = {"content-type": "application/json"}

    def fake_get(url, params=None, headers=None, timeout=None, follow_redirects=False):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    adapters.set_adapter_override(adapters.FakeModelAdapter(
        responses=["Based on the search results, the answer is 42."]))

    login(client, "engineer@platform.local")
    tool = client.post("/api/tools", json={
        "name": "Search Params Tool", "permission_type": "read",
        "implementation": {"kind": "http_api", "config": {
            "base_url": "https://example.com/search",
            "headers": {"User-Agent": "AgentOpsPlatform/0.1"},
        }},
    }).json()
    client.post(f"/api/tools/{tool['id']}/submit")
    login(client, "governance@platform.local")
    step = [a for a in client.get("/api/approvals").json() if a["resource_id"] == tool["id"]][0]
    client.post(f"/api/approvals/{step['id']}/decide", json={"approve": True})

    login(client, "engineer@platform.local")
    pack = client.post("/api/prompts", json={"name": "Search Params Prompt", "prompt_type": "system",
                                             "content": "Answer using the search results."}).json()
    client.post(f"/api/prompts/{pack['id']}/versions/1/submit")
    login(client, "governance@platform.local")
    pstep = [a for a in client.get("/api/approvals").json()
             if a["resource_type"] == "prompt_version"][0]
    client.post(f"/api/approvals/{pstep['id']}/decide", json={"approve": True})

    login(client, "creator@platform.local")
    aid = client.post("/api/agents", json={"name": "Search Params Agent"}).json()["id"]
    login(client, "engineer@platform.local")
    wf = client.post(f"/api/agents/{aid}/workflows", json={"name": "search-wf", "graph": {
        "nodes": [
            {"id": "sys", "type": "prompt", "label": "", "config": {"pack_ref": pack["slug"]}},
            {"id": "search", "type": "tool_call", "label": "", "config": {
                "tool_ref": tool["slug"], "params": {"q": "{{user_input}}", "limit": 3}}},
            {"id": "gen", "type": "llm", "label": "", "config": {}},
            {"id": "out", "type": "output_format", "label": "", "config": {"format": "text"}},
        ],
        "edges": [{"from": "sys", "to": "search"}, {"from": "search", "to": "gen"},
                  {"from": "gen", "to": "out"}],
    }}).json()
    assert client.post(f"/api/workflows/{wf['id']}/versions/1/validate").json()["status"] == "validated"

    login(client, "creator@platform.local")
    run = client.post(f"/api/agents/{aid}/runs", json={
        "input": "what is the ultimate answer?",
        "workflow_version_id": wf["versions"][0]["id"],
    }).json()
    assert run["status"] == "completed", run.get("error")

    # the user's question reached the tool, and the static header was sent
    assert captured["params"] == {"q": "what is the ultimate answer?", "limit": 3}
    assert captured["headers"]["User-Agent"] == "AgentOpsPlatform/0.1"
    # the tool's response reached the model, and the answer came back
    search_span = next(s for s in run["steps"] if s["node_id"] == "search")
    assert search_span["detail"]["state_placeholders"] == ["user_input"]
    assert "42" in run["output"]["final_output"]
