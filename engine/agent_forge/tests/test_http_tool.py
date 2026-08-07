"""Executable HTTP tools: GET binds & runs (secret injected), mutating disabled,
codegen twin, secret hygiene, /v1/tools/try."""
import json
from pathlib import Path

import pytest

from agent_forge.loader import load_agent
from agent_forge.tools_lib import resolve_tools, try_http_tool
from agent_forge import generate
from agent_forge import secrets as vault

FIX = Path(__file__).parent / "fixtures"


def _record_with_http(method="GET", secret_ref="WEATHER_KEY"):
    rec = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    rec["config"]["tooling"]["bound_tools"]["value"] = ["tools://weather_lookup@v1"]
    rec["_bound_tool_defs"] = [{
        "name": "weather_lookup",
        "kind": "http_api",
        "permission": "read",
        "write_capable": method != "GET",
        "http": {
            "method": method,
            "url_template": "https://api.example.com/w?q={query}",
            "query_params": {"units": "metric"},
            "headers": {"Accept": "application/json"},
            "auth_header": "Authorization: Bearer {secret}",
        },
        "auth_secret_ref": secret_ref,
    }]
    return rec


@pytest.fixture(autouse=True)
def tmp_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FORGE_SECRETS", str(tmp_path / "s.json"))
    yield


def test_get_http_tool_binds_and_calls(monkeypatch):
    vault.put("WEATHER_KEY", "sk-weather-123")
    ir = load_agent(_record_with_http("GET"))
    assert ir.tools[0].func == "weather_lookup"
    assert ir.tools[0].capability == "http_api"
    assert ir.secret_refs.get("weather_lookup") == "WEATHER_KEY"

    captured = {}

    def fake_request(method, url, params=None, headers=None, timeout=None):
        captured.update(method=method, url=url, params=params, headers=headers)
        class R:
            status_code = 200
            text = "sunny"
        return R()

    import httpx
    monkeypatch.setattr(httpx, "request", fake_request)

    lt = resolve_tools(ir.tools, secrets=vault.resolve_tool_secrets(ir.secret_refs))
    assert lt[0].name == "weather_lookup"
    out = lt[0].invoke({"query": "London"})
    assert out == "sunny"
    assert captured["url"] == "https://api.example.com/w?q=London"  # {query} rendered
    assert captured["headers"]["Authorization"] == "Bearer sk-weather-123"  # secret injected


def test_mutating_http_tool_is_disabled():
    ir = load_agent(_record_with_http("POST"))
    assert all(t.func != "weather_lookup" for t in ir.tools)  # not bound
    assert any(t.func == "weather_lookup" and t.write_capable for t in ir.disabled_tools)


def test_codegen_get_uses_httpx_and_getenv():
    res = generate(_record_with_http("GET"))
    toolspy = res.files[f"src/{res.agent.pkg}/tools.py"]
    assert 'httpx.request("GET"' in toolspy
    assert 'os.getenv("WEATHER_KEY")' in toolspy
    assert "sk-weather" not in toolspy  # never a secret value
    # advisory-bound, not disabled
    assert "ADVISORY_TOOLS = [weather_lookup]" in toolspy


def test_codegen_post_is_disabled_not_advisory():
    res = generate(_record_with_http("POST"))
    toolspy = res.files[f"src/{res.agent.pkg}/tools.py"]
    assert "ADVISORY_TOOLS = []" in toolspy
    assert '"weather_lookup"' in toolspy.split("DISABLED_WRITE_TOOLS")[1]
    assert "raise PermissionError" in toolspy


def test_http_codegen_deterministic():
    a = generate(_record_with_http("GET"))
    b = generate(_record_with_http("GET"))
    assert a.files == b.files and a.zip_bytes() == b.zip_bytes()


def test_try_http_tool_get_and_refuses_mutating(monkeypatch):
    vault.put("WEATHER_KEY", "sk-weather-123")

    def fake_request(method, url, params=None, headers=None, timeout=None):
        class R:
            status_code = 200
            text = "ok-body"
        return R()

    import httpx
    monkeypatch.setattr(httpx, "request", fake_request)

    getdef = {"name": "weather_lookup", "http": {"method": "GET", "url_template": "https://x/{query}", "auth_header": "Authorization: Bearer {secret}"}, "auth_secret_ref": "WEATHER_KEY"}
    r = try_http_tool(getdef, "London")
    assert r["ok"] and r["status"] == 200 and r["text"] == "ok-body"
    # response carries no auth header material
    assert "sk-weather" not in json.dumps(r)

    postdef = {"name": "x", "http": {"method": "POST", "url_template": "https://x"}}
    assert try_http_tool(postdef, "")["ok"] is False
