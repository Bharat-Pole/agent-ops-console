"""
Shared Atlassian Cloud auth helper — Confluence and Jira Cloud both authenticate
the same way: HTTP Basic auth using the account email + an API token
(https://id.atlassian.com/manage-profile/security/api-tokens), not a password.
"""
from __future__ import annotations

import base64


def basic_auth_header(email: str, api_token: str) -> dict[str, str]:
    if not email or not api_token:
        raise ValueError("Confluence/Jira require both an account email and an API token.")
    raw = f"{email}:{api_token}".encode("utf-8")
    return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}
