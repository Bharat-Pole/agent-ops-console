import json
from pathlib import Path

import pytest

from agent_forge import generate, load_agent
from agent_forge.hitl_map import map_hitl

FIX = Path(__file__).parent / "fixtures"
ALL = ["hr_policy_bot.json", "noc_incident_summarizer.json", "incident_response_coordinator.json"]


@pytest.mark.parametrize("name", ALL)
def test_generates_without_crashing(name):
    res = generate(str(FIX / name))
    assert res.files
    # every value is a string; config embedded verbatim & sorted
    assert all(isinstance(v, str) for v in res.files.values())
    cfg_path = f"config/agent.config.json"
    assert cfg_path in res.files
    json.loads(res.files[cfg_path])  # valid JSON


def test_hr_exact_file_set():
    res = generate(str(FIX / "hr_policy_bot.json"))
    pkg = res.agent.pkg
    expected = {
        ".env.example", ".gitignore", "README.md", "conftest.py",
        "config/agent.config.json", "pyproject.toml", "requirements.txt",
        f"src/{pkg}/__init__.py", f"src/{pkg}/graph.py", f"src/{pkg}/memory.py",
        f"src/{pkg}/model.py", f"src/{pkg}/prompts.py", f"src/{pkg}/tools.py",
        f"src/{pkg}/runtime/__init__.py", f"src/{pkg}/runtime/cli.py", f"src/{pkg}/runtime/server.py",
        "tests/_fakes.py", "tests/test_advisory_guard.py", "tests/test_compiles.py",
    }
    assert set(res.files) == expected
    # single topology → no rag/ files
    assert not any("/rag/" in p for p in res.files)
    assert "create_react_agent" in res.files[f"src/{pkg}/graph.py"]


def test_noc_has_rag_files():
    res = generate(str(FIX / "noc_incident_summarizer.json"))
    pkg = res.agent.pkg
    assert f"src/{pkg}/rag/retriever.py" in res.files
    assert f"src/{pkg}/rag/ingest.py" in res.files
    assert any(p.startswith(f"src/{pkg}/rag/sample_docs/") for p in res.files)
    assert "retrieve" in res.files[f"src/{pkg}/graph.py"]


def test_determinism_bytes():
    a = generate(str(FIX / "hr_policy_bot.json"))
    b = generate(str(FIX / "hr_policy_bot.json"))
    assert a.files == b.files
    assert a.zip_bytes() == b.zip_bytes()  # byte-identical


def test_advisory_guardrail_incident():
    res = generate(str(FIX / "incident_response_coordinator.json"))
    pkg = res.agent.pkg
    advisory = {t.name for t in res.agent.tools}
    disabled = {t.name for t in res.agent.disabled_tools}
    # flagged write tools present but never bound
    assert {"slack_notifier", "email_sender"} <= disabled
    assert advisory.isdisjoint({"slack_notifier", "email_sender"})
    toolspy = res.files[f"src/{pkg}/tools.py"]
    assert "raise PermissionError" in toolspy
    assert "slack_notifier" in toolspy and "email_sender" in toolspy
    # supervisor has 4 sub-agent nodes
    assert len(res.agent.sub_agents) == 4
    graph = res.files[f"src/{pkg}/graph.py"]
    for sa in ("log_analyzer", "impact_assessor", "comms_drafter", "notification_router"):
        assert sa in graph
    # comms_drafter is a zero-tool sub-agent
    assert next(s for s in res.agent.sub_agents if s.name == "comms_drafter").tools == []


def test_hitl_mapping_incident():
    agent = load_agent(str(FIX / "incident_response_coordinator.json"))
    node_names = {"supervisor"} | {s.name for s in agent.sub_agents}
    m = map_hitl(agent.hitl, node_names)
    # 'on comms_drafter → notification_router edge' → interrupt before notification_router
    assert "notification_router" in m.interrupt_before
    # 'pre-deploy' has no node → human-process gate, not a graph interrupt
    assert any("pre-deploy" in g.lower() for g in m.process_gates)
    res = generate(str(FIX / "incident_response_coordinator.json"))
    assert 'interrupt_before=["notification_router"]' in res.files[f"src/{res.agent.pkg}/graph.py"]


def test_blockers_incident_reviewed_ok():
    res = generate(str(FIX / "incident_response_coordinator.json"))
    b = res.blockers
    # review_card is populated → not a write-adjacent blocker; no write tool is bound
    assert b["unreviewed_write_adjacent"] is False
    assert b["write_tools"] == []


def test_blocker_null_review_card_write_adjacent():
    # write-intent objective + null review_card → hard blocker (reviewed-record rule)
    record = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    record["review_card"] = None
    record["config"]["identity"]["objective"]["value"] = "Send an email to every employee about the new policy."
    res = generate(record)
    assert res.blockers["unreviewed_write_adjacent"] is True
    assert res.blockers["has_hard_blockers"] is True


def test_pipeline_generation():
    res = generate(str(FIX / "release_notes_pipeline.json"))
    assert res.topology.value == "pipeline"
    graph = res.files[f"src/{res.agent.pkg}/graph.py"]
    assert 'STAGES = ["research", "draft", "review"]' in graph  # config order
    # HITL: 'on draft -> review edge' → interrupt before review
    assert 'interrupt_before=["review"]' in graph


def test_parallel_generation_with_secret_names():
    res = generate(str(FIX / "market_scan_parallel.json"))
    assert res.topology.value == "parallel"
    graph = res.files[f"src/{res.agent.pkg}/graph.py"]
    assert 'g.add_edge(BRANCHES, "aggregate")' in graph  # validated join barrier
    assert 'interrupt_before=["aggregate"]' in graph      # 'review -> aggregate' gate
    # .env.example lists referenced secret NAMES with empty values, never values
    env = res.files[".env.example"]
    assert "GEMINI_PROD=" in env and "TAVILY_KEY=" in env
    # determinism on the new topology
    res2 = generate(str(FIX / "market_scan_parallel.json"))
    assert res.files == res2.files and res.zip_bytes() == res2.zip_bytes()


def test_retired_models_aliased_to_current():
    # gemini-1.5-* was removed from the API (404s); must alias to a served model
    from agent_forge.model_map import map_model
    assert map_model("vertex://gemini-1.5-flash") == "gemini-3.6-flash"
    assert map_model("vertex://gemini-1.5-pro") == "gemini-3.6-flash"
    assert map_model("gemini-3.6-flash") == "gemini-3.6-flash"  # current ids pass through
    # loader: primary+fallback that alias to the same id get a distinct fallback
    from agent_forge.loader import load_agent
    ir = load_agent(str(FIX / "noc_incident_summarizer.json"))  # 1.5-flash + 1.5-pro fallback
    assert ir.model.primary == "gemini-3.6-flash"
    assert ir.model.fallback == "gemini-3.5-flash"
    # generated model.py carries the aliased ids
    res = generate(str(FIX / "noc_incident_summarizer.json"))
    mp = res.files[f"src/{res.agent.pkg}/model.py"]
    assert '"gemini-3.6-flash"' in mp and "gemini-1.5" not in mp


def test_tool_name_sanitized_to_valid_identifier():
    # a free-text tool name with spaces must become a valid Python identifier
    record = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    record["config"]["tooling"]["bound_tools"]["value"] = ["tools://web search tool@v1"]
    res = generate(record)
    toolspy = res.files[f"src/{res.agent.pkg}/tools.py"]
    assert "def web_search_tool(" in toolspy
    assert "def web search" not in toolspy  # the invalid form must be gone
    assert "ADVISORY_TOOLS = [web_search_tool]" in toolspy


def test_blocker_write_tool_bound_is_disabled():
    # a write-capable tool sneaked into bound_tools → flagged as a blocker AND never bound
    record = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    record["config"]["tooling"]["bound_tools"]["value"] = ["tools://ticket_updater@v1"]
    res = generate(record)
    assert "ticket_updater" in res.blockers["write_tools"]
    assert "ticket_updater" not in {t.name for t in res.agent.tools}
    assert "ticket_updater" in {t.name for t in res.agent.disabled_tools}
