"""Secrets vault: CRUD, resolution chain, endpoint hygiene (values never returned)."""
import json

import pytest

from agent_forge import secrets as vault


@pytest.fixture(autouse=True)
def tmp_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FORGE_SECRETS", str(tmp_path / "secrets.json"))
    yield


def test_crud_roundtrip():
    assert vault.list_names() == []
    vault.put("GEMINI_DEFAULT", "sk-default")
    vault.put("TAVILY_KEY", "tv-123")
    assert vault.list_names() == ["GEMINI_DEFAULT", "TAVILY_KEY"]  # sorted
    assert vault.get("TAVILY_KEY") == "tv-123"
    assert vault.delete("TAVILY_KEY") is True
    assert vault.delete("TAVILY_KEY") is False
    assert vault.list_names() == ["GEMINI_DEFAULT"]


def test_name_validation_and_empty_value():
    with pytest.raises(ValueError):
        vault.put("1bad", "x")
    with pytest.raises(ValueError):
        vault.put("has space", "x")
    with pytest.raises(ValueError):
        vault.put("OK_NAME", "")


def test_corrupt_file_recovers(tmp_path, monkeypatch):
    p = tmp_path / "secrets.json"
    monkeypatch.setenv("AGENT_FORGE_SECRETS", str(p))
    p.write_text("{not json", encoding="utf-8")
    assert vault.list_names() == []
    vault.put("A_KEY", "v")  # write repairs the file
    assert vault.get("A_KEY") == "v"


def test_resolution_chain_precedence():
    vault.put("GEMINI_DEFAULT", "vault-default")
    vault.put("GEMINI_TEAM_A", "team-a-key")
    # 1. request key wins
    assert vault.resolve_model_key({"model": "GEMINI_TEAM_A"}, "req-key") == ("req-key", "request")
    # 2. agent's named secret
    assert vault.resolve_model_key({"model": "GEMINI_TEAM_A"}, None) == ("team-a-key", "agent_secret")
    # 3. vault default when ref missing/unresolvable
    assert vault.resolve_model_key({"model": "NOPE"}, None) == ("vault-default", "vault_default")
    assert vault.resolve_model_key({}, None) == ("vault-default", "vault_default")
    # 4. env fallthrough
    vault.delete("GEMINI_DEFAULT")
    assert vault.resolve_model_key({}, None) == (None, "env")


def test_tool_secret_resolution():
    vault.put("TAVILY_KEY", "tv-999")
    refs = {"model": "GEMINI_DEFAULT", "tavily": "TAVILY_KEY", "other": "MISSING"}
    assert vault.resolve_tool_secrets(refs) == {"tavily": "tv-999"}


def test_endpoints_never_return_values():
    from fastapi.testclient import TestClient
    from service.app import app

    client = TestClient(app)
    r = client.put("/v1/secrets/GEMINI_DEFAULT", json={"value": "super-secret-value"})
    assert r.status_code == 200
    # scan every endpoint response for the value
    for resp in (r, client.get("/v1/secrets"), client.get("/v1/health")):
        assert "super-secret-value" not in resp.text
    assert client.get("/v1/secrets").json()["names"] == ["GEMINI_DEFAULT"]
    h = client.get("/v1/health").json()
    assert h["has_default_key"] is True and "GEMINI_DEFAULT" in h["secret_names"]
    # invalid names / empty values rejected
    assert client.put("/v1/secrets/9bad", json={"value": "x"}).status_code == 400
    assert client.put("/v1/secrets/OK_NAME", json={"value": "  "}).status_code == 400
    assert client.delete("/v1/secrets/GEMINI_DEFAULT").json()["ok"] is True
