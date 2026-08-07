"""Declared tool capability beats the name heuristic (kills the DDG name-magic)."""
import json
from pathlib import Path

from agent_forge.loader import load_agent
from agent_forge.tools_lib import resolve_tools
from agent_forge.model_map import claude_model_id, map_model

FIX = Path(__file__).parent / "fixtures"


def _rec(tool_name: str, capability):
    rec = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    rec["config"]["tooling"]["bound_tools"]["value"] = [f"tools://{tool_name}@v1"]
    rec["_bound_tool_defs"] = [{"name": tool_name, "kind": "catalog", "capability": capability,
                                "permission": "read", "write_capable": False, "http": None,
                                "auth_secret_ref": None}]
    return rec


def test_declared_none_on_search_named_tool_is_honest_stub():
    # a tool NAMED like search but DECLARED not-connected must NOT get DDG
    ir = load_agent(_rec("web_searcher", "none"))
    assert ir.tools[0].capability == "none"
    lt = resolve_tools(ir.tools)
    out = lt[0].func("who won?")
    assert "not connected" in out


def test_declared_web_search_on_arbitrary_name_binds_real_search():
    # a tool named nothing like search but DECLARED web_search gets the real impl
    ir = load_agent(_rec("fact_finder", "web_search"))
    assert ir.tools[0].capability == "web_search"
    lt = resolve_tools(ir.tools)
    assert "web search" in (lt[0].description or "").lower()


def test_no_declaration_falls_back_to_name_heuristic():
    rec = _rec("web_searcher", None)
    rec["_bound_tool_defs"][0].pop("capability")
    ir = load_agent(rec)
    assert ir.tools[0].capability == "web_search"  # legacy behavior preserved


def test_claude_model_mapping():
    assert claude_model_id("vertex://gemini-1.5-flash") == "claude-opus-5"  # gemini id → default
    assert claude_model_id("claude://claude-sonnet-5") == "claude-sonnet-5"  # explicit claude wins
    assert claude_model_id(None) == "claude-opus-5"
    assert map_model("claude://claude-opus-5") == "claude-opus-5"


def test_claude_key_resolution_uses_anthropic_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FORGE_SECRETS", str(tmp_path / "s.json"))
    from agent_forge import secrets as vault
    vault.put("ANTHROPIC_DEFAULT", "anth-key")
    vault.put("GEMINI_DEFAULT", "gem-key")
    k, src = vault.resolve_model_key(None, provider="claude")
    assert (k, src) == ("anth-key", "vault_default")
    k2, _ = vault.resolve_model_key(None, provider="gemini")
    assert k2 == "gem-key"
