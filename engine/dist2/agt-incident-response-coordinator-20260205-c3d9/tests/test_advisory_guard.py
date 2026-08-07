"""Advisory-only guardrail — write-capable tools are never bound."""
import pytest

from agt_incident_response_coordinator_20260205_c3d9 import tools as T


def test_no_write_tool_is_bound():
    bound = {getattr(t, "name", getattr(t, "__name__", "")) for t in T.ADVISORY_TOOLS}
    for name in T.DISABLED_WRITE_TOOLS:
        assert name not in bound, f"write-capable tool {name!r} must not be bound"


@pytest.mark.parametrize("name", T.DISABLED_WRITE_TOOLS if False else ["email_sender", "slack_notifier"])
def test_disabled_write_tools_raise(name):
    fn = getattr(T, name)
    with pytest.raises(PermissionError):
        fn()
