"""Tools for Incident Response Coordinator.

Advisory-only scope is LOCKED: only read/summarize/draft/recommend/validate tools
are bound (ADVISORY_TOOLS). Write-capable tools are emitted DISABLED below — defined
but intentionally NOT in ADVISORY_TOOLS — and raise on call. Read-tool bodies are
stubs; replace them with real integrations.
"""
from langchain_core.tools import tool

@tool
def health_checker(query: str = "") -> str:
    """read · tools://health_checker@v1 — advisory/read-only. Replace with a real integration."""
    return f"[stub:health_checker] no real integration bound yet (query={query!r})"

@tool
def incident_reader(query: str = "") -> str:
    """read · tools://incident_reader@v1 — advisory/read-only. Replace with a real integration."""
    return f"[stub:incident_reader] no real integration bound yet (query={query!r})"

@tool
def jira_reader(query: str = "") -> str:
    """read · tools://jira_reader@v1 — advisory/read-only. Replace with a real integration."""
    return f"[stub:jira_reader] no real integration bound yet (query={query!r})"

@tool
def log_reader(query: str = "") -> str:
    """read · tools://log_reader@v1 — advisory/read-only. Replace with a real integration."""
    return f"[stub:log_reader] no real integration bound yet (query={query!r})"

# Advisory (read-scope) tools bound to the agent:
ADVISORY_TOOLS = [health_checker, incident_reader, jira_reader, log_reader]

def email_sender(*args, **kwargs):  # DISABLED — flagged write tool (not bound)
    """DISABLED — write-capable (tools://email_sender). Advisory-only scope is LOCKED; this is
    intentionally NOT in ADVISORY_TOOLS. Enable only behind a human-in-the-loop gate
    after governance approval."""
    raise PermissionError(
        "email_sender is write-capable and was NOT bound (advisory-only). Requires HITL."
    )

def slack_notifier(*args, **kwargs):  # DISABLED — flagged write tool (not bound)
    """DISABLED — write-capable (tools://slack_notifier). Advisory-only scope is LOCKED; this is
    intentionally NOT in ADVISORY_TOOLS. Enable only behind a human-in-the-loop gate
    after governance approval."""
    raise PermissionError(
        "slack_notifier is write-capable and was NOT bound (advisory-only). Requires HITL."
    )

# Names flagged write-capable and intentionally excluded from ADVISORY_TOOLS:
DISABLED_WRITE_TOOLS = ["email_sender", "slack_notifier"]
