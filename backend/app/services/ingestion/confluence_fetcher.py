"""
Confluence Cloud connector — real REST API v2 calls, no simulation.

Auth: HTTP Basic (account email + API token), per Atlassian Cloud's documented
scheme: https://developer.atlassian.com/cloud/confluence/basic-auth-for-rest-apis/

Ingestion modes:
  - page_id given   -> fetch that single page's storage-format body
  - space_key given -> CQL-search the space for pages, fetch each (bounded)
"""
from __future__ import annotations

from typing import Optional

from app.services.ingestion.atlassian_auth import basic_auth_header
from app.services.ingestion.parsers import parse_html

_MAX_PAGES = 25


async def _get(client, url: str, params: Optional[dict] = None) -> dict:
    resp = await client.get(url, params=params)
    if resp.status_code == 401:
        raise RuntimeError("Confluence authentication failed (401) — check email/API token.")
    if resp.status_code == 403:
        raise RuntimeError("Confluence access forbidden (403) — the account lacks permission for this space/page.")
    if resp.status_code == 404:
        raise RuntimeError("Confluence page/space not found (404) — check the base URL and ID/key.")
    resp.raise_for_status()
    return resp.json()


async def test_connection(base_url: str, email: str, api_token: str) -> tuple[bool, str]:
    """Cheap real auth check: list up to 1 space. No ingestion side effects."""
    import httpx
    try:
        headers = {**basic_auth_header(email, api_token), "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            data = await _get(client, f"{base_url.rstrip('/')}/wiki/api/v2/spaces", {"limit": 1})
        n = len(data.get("results", []))
        return True, f"Connected — Confluence API reachable ({n} space{'s' if n != 1 else ''} visible)."
    except Exception as e:
        return False, str(e)


async def fetch_confluence(
    base_url: str,
    email: str,
    api_token: str,
    page_id: Optional[str] = None,
    space_key: Optional[str] = None,
) -> tuple[bytes, str]:
    import httpx

    if not base_url:
        raise ValueError("Confluence base URL is required, e.g. https://yourcompany.atlassian.net")
    if not page_id and not space_key:
        raise ValueError("Provide either a Confluence page ID or a space key to ingest.")

    headers = {**basic_auth_header(email, api_token), "Accept": "application/json"}
    root = base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        if page_id:
            page = await _get(client, f"{root}/wiki/api/v2/pages/{page_id}", {"body-format": "storage"})
            pages = [page]
        else:
            search = await _get(
                client,
                f"{root}/wiki/rest/api/content/search",
                {"cql": f'type=page and space="{space_key}"', "limit": _MAX_PAGES, "expand": "body.storage"},
            )
            pages = search.get("results", [])
            if not pages:
                raise RuntimeError(f"No pages found in Confluence space '{space_key}'.")

    formatted: list[str] = []
    for p in pages:
        title = p.get("title", "Untitled")
        storage = (
            p.get("body", {}).get("storage", {}).get("value")  # v1 search shape
            or p.get("body", {}).get("storage", {}).get("representation")  # defensive
            or ""
        )
        # v2 single-page shape nests it slightly differently
        if not storage and "body" in p and isinstance(p["body"], dict) and "storage" in p["body"]:
            storage = p["body"]["storage"].get("value", "")
        text = parse_html(storage.encode("utf-8")) if storage else ""
        formatted.append(f"=== CONFLUENCE PAGE: {title} ===\n{text}")

    if not any(f.split("\n", 1)[-1].strip() for f in formatted):
        raise RuntimeError("Confluence page(s) returned no extractable body text.")

    return "\n\n".join(formatted).encode("utf-8"), "text/plain"
