"""Live-runtime build + run with a fake model (no API key)."""
import json
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent_forge.runtime import run_agent, build_live_graph

FIX = Path(__file__).parent / "fixtures"


class _StructuredOut:
    def invoke(self, *a, **k):
        class R:
            next = "FINISH"
        return R()


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        return _StructuredOut()


@pytest.mark.parametrize("fx,topo", [
    ("hr_policy_bot", "single"),
    ("noc_incident_summarizer", "dag"),
    ("incident_response_coordinator", "supervisor"),
])
def test_run_agent_with_fake_model(fx, topo):
    rec = json.loads((FIX / f"{fx}.json").read_text(encoding="utf-8"))
    out = run_agent(rec, "hello there", thread_id="t1", model=FakeChatModel())
    assert isinstance(out["reply"], str) and out["reply"]  # got some reply
    assert out["trace"]["topology"] == topo


def test_build_live_graph_compiles_with_fake():
    rec = json.loads((FIX / "incident_response_coordinator.json").read_text(encoding="utf-8"))
    g = build_live_graph(rec, model=FakeChatModel())
    nodes = set(g.get_graph().nodes)
    assert {"supervisor", "log_analyzer", "notification_router"}.issubset(nodes)


def test_pipeline_runs_stages_in_order():
    rec = json.loads((FIX / "release_notes_pipeline.json").read_text(encoding="utf-8"))
    out = run_agent(rec, "make release notes", thread_id="tp", model=FakeChatModel())
    assert out["trace"]["topology"] == "pipeline"
    assert out["trace"]["pattern"] == "pipeline"
    assert out["reply"] == "ok"


def test_parallel_aggregate_runs_once_with_labeled_branches():
    rec = json.loads((FIX / "market_scan_parallel.json").read_text(encoding="utf-8"))
    out = run_agent(rec, "scan the market", thread_id="tq", model=FakeChatModel())
    t = out["trace"]
    assert t["topology"] == "parallel" and t["pattern"] == "parallel"
    # every branch contributed a labeled output, deterministic key set
    assert sorted(t["branch_outputs"]) == ["competitor_analyst", "pricing_analyst", "sentiment_analyst"]
    assert all(v == "ok" for v in t["branch_outputs"].values())
    assert out["reply"] == "ok"  # aggregate's merged reply


def test_parallel_graph_nodes():
    rec = json.loads((FIX / "market_scan_parallel.json").read_text(encoding="utf-8"))
    g = build_live_graph(rec, model=FakeChatModel())
    nodes = set(g.get_graph().nodes)
    assert {"pricing_analyst", "competitor_analyst", "sentiment_analyst", "aggregate"}.issubset(nodes)


def test_resolution_chain_used_by_runtime(tmp_path, monkeypatch):
    # agent's named model secret is picked up (trace reports agent_secret, no values)
    monkeypatch.setenv("AGENT_FORGE_SECRETS", str(tmp_path / "s.json"))
    from agent_forge import secrets as vault
    vault.put("GEMINI_PROD", "prod-key-value")
    rec = json.loads((FIX / "market_scan_parallel.json").read_text(encoding="utf-8"))
    out = run_agent(rec, "hi", thread_id="ts", model=FakeChatModel())
    assert out["trace"]["credential_source"] == "agent_secret"
    assert "prod-key-value" not in json.dumps(out)  # value never leaks into the response


def test_resolve_tools_old_signature_still_works():
    from agent_forge.loader import load_agent
    from agent_forge.tools_lib import resolve_tools
    ir = load_agent(json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8")))
    assert isinstance(resolve_tools(ir.tools), list)  # no secrets arg → fine


class BlockContentFakeModel(FakeChatModel):
    """Returns content as a LIST of blocks, like Gemini via langchain-core 1.x."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = AIMessage(content=[
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "block reply"},
        ])
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_reply_is_plain_string_even_for_block_content():
    # regression: list-of-blocks content reached the UI and crashed React
    rec = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    out = run_agent(rec, "hello", thread_id="tb", model=BlockContentFakeModel())
    assert isinstance(out["reply"], str)
    assert out["reply"] == "block reply"  # thinking block skipped, text extracted


def test_build_model_supports_tool_binding():
    # regression: retry/fallback wrappers (RunnableRetry/RunnableWithFallbacks)
    # lack bind_tools/with_structured_output and crash create_react_agent.
    # _build_model must return the plain chat model.
    from agent_forge.loader import load_agent
    from agent_forge.runtime import _build_model
    ir = load_agent(json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8")))
    m = _build_model(ir, api_key="dummy-key-for-constructor")
    assert hasattr(m, "bind_tools")
    assert hasattr(m, "with_structured_output")


def test_web_search_agent_binds_real_tool_no_stub():
    # a tool named with 'search' → real web_search bound (not a stub); never disabled
    rec = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    rec["config"]["tooling"]["bound_tools"]["value"] = ["tools://web search tool@v1"]
    from agent_forge.loader import load_agent
    ir = load_agent(rec)
    assert ir.tools[0].func == "web_search_tool"
    assert ir.tools[0].capability == "web_search"
    from agent_forge.tools_lib import resolve_tools
    lt = resolve_tools(ir.tools)
    assert lt[0].name == "web_search_tool"
