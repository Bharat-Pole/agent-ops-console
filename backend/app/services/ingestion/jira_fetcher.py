"""
Jira Cloud connector — real REST API v3 calls, no simulation.

Auth: HTTP Basic (account email + API token), same scheme as Confluence Cloud.
"""
from __future__ import annotations

from app.services.ingestion.atlassian_auth import basic_auth_header

_MAX_ISSUES = 100
_FIELDS = "summary,description,status,priority,assignee,reporter,created,updated,issuetype"


def _adf_to_text(node) -> str:
    """Jira v3 'description' is Atlassian Document Format (nested JSON), not plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    parts: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        for child in node.get("content", []) or []:
            parts.append(_adf_to_text(child))
    return " ".join(p for p in parts if p)


async def test_connection(base_url: str, email: str, api_token: str) -> tuple[bool, str]:
    import httpx
    try:
        headers = {**basic_auth_header(email, api_token), "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/rest/api/3/myself")
        if resp.status_code == 401:
            return False, "Jira authentication failed (401) — check email/API token."
        resp.raise_for_status()
        who = resp.json().get("displayName", "unknown user")
        return True, f"Connected — authenticated as {who}."
    except Exception as e:
        return False, str(e)


async def fetch_jira(base_url: str, email: str, api_token: str, jql: str) -> tuple[bytes, str]:
    import httpx

    if not base_url:
        raise ValueError("Jira base URL is required, e.g. https://yourcompany.atlassian.net")
    if not jql:
        raise ValueError("A JQL query is required, e.g. project = OPS ORDER BY created DESC")

    headers = {**basic_auth_header(email, api_token), "Accept": "application/json"}
    root = base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        resp = await client.get(
            f"{root}/rest/api/3/search",
            params={"jql": jql, "maxResults": _MAX_ISSUES, "fields": _FIELDS},
        )
        if resp.status_code == 401:
            raise RuntimeError("Jira authentication failed (401) — check email/API token.")
        if resp.status_code == 400:
            raise RuntimeError(f"Jira rejected the JQL query: {resp.text}")
        resp.raise_for_status()
        data = resp.json()

    issues = data.get("issues", [])
    if not issues:
        raise RuntimeError(f"JQL query returned 0 issues: {jql}")

    formatted: list[str] = []
    for issue in issues:
        f = issue.get("fields", {})
        key = issue.get("key", "?")
        summary = f.get("summary", "")
        status = (f.get("status") or {}).get("name", "")
        priority = (f.get("priority") or {}).get("name", "")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        issuetype = (f.get("issuetype") or {}).get("name", "")
        description = _adf_to_text(f.get("description"))

        lines = [
            f"--- JIRA ISSUE {key} | TYPE: {issuetype} | STATUS: {status} | PRIORITY: {priority} ---",
            f"SUMMARY: {summary}",
            f"ASSIGNEE: {assignee}",
            f"CREATED: {f.get('created', '')}",
            f"UPDATED: {f.get('updated', '')}",
        ]
        if description:
            lines.append(f"DESCRIPTION: {description}")
        formatted.append("\n".join(lines))

    return "\n\n".join(formatted).encode("utf-8"), "text/plain"
