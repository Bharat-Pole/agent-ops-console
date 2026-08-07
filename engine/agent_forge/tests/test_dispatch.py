from pathlib import Path

from agent_forge import load_agent, dispatch, Topology

FIX = Path(__file__).parent / "fixtures"


def test_hr_is_single():
    assert dispatch(load_agent(str(FIX / "hr_policy_bot.json"))) is Topology.SINGLE


def test_noc_rag_is_dag():
    assert dispatch(load_agent(str(FIX / "noc_incident_summarizer.json"))) is Topology.DAG


def test_incident_is_supervisor():
    assert dispatch(load_agent(str(FIX / "incident_response_coordinator.json"))) is Topology.SUPERVISOR


def test_pattern_pipeline_and_parallel():
    assert dispatch(load_agent(str(FIX / "release_notes_pipeline.json"))) is Topology.PIPELINE
    assert dispatch(load_agent(str(FIX / "market_scan_parallel.json"))) is Topology.PARALLEL


def test_pattern_backcompat_and_scoping():
    import json
    rec = json.loads((FIX / "incident_response_coordinator.json").read_text(encoding="utf-8"))
    # explicit hub → supervisor
    rec["config"]["orchestration"]["pattern"] = {"value": "hub", "value_source": "default",
                                                 "verified_flag": True, "confidence": "high", "gap_note": None}
    assert dispatch(load_agent(rec)) is Topology.SUPERVISOR
    # pattern is ignored when orchestration_type is not coordinator+subagents
    rec2 = json.loads((FIX / "hr_policy_bot.json").read_text(encoding="utf-8"))
    rec2["config"]["orchestration"]["pattern"] = {"value": "parallel", "value_source": "user",
                                                  "verified_flag": True, "confidence": "high", "gap_note": None}
    assert dispatch(load_agent(rec2)) is Topology.SINGLE
