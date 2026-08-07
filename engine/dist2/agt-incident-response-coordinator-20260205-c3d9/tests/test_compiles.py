"""Structural smoke test — the graph compiles with a fake model (no API key)."""
from _fakes import FakeChatModel

from agt_incident_response_coordinator_20260205_c3d9.graph import build_graph


def test_graph_compiles_without_api_key():
    g = build_graph(model=FakeChatModel())
    assert g is not None
    nodes = set(g.get_graph().nodes)
    expected = set(["comms_drafter", "impact_assessor", "log_analyzer", "notification_router", "supervisor"])
    assert expected.issubset(nodes), f"missing nodes {expected - nodes}; got {sorted(nodes)}"
