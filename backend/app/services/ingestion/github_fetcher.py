"""
GitHub docs connector — real REST API v3 calls, no simulation.

Auth: optional `Authorization: Bearer <PAT>`. Public repos work fully unauthenticated
at GitHub's standard unauthenticated rate limit (60 req/hr per IP) — this is the one
connector in this platform that can be verified end-to-end without any credentials.

Uses the documented "raw" media type (application/vnd.github.raw+json) on the
Contents API so a single GET returns file bytes directly instead of base64 JSON:
https://docs.github.com/en/rest/repos/contents
"""
from __future__ import annotations

from typing import Optional

_MAX_FILES = 30
_TEXTUAL_EXTENSIONS = {
    ".md": "text/markdown", ".txt": "text/plain", ".rst": "text/plain",
    ".html": "text/html", ".htm": "text/html", ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _guess_mime(path: str) -> str:
    for ext, mime in _TEXTUAL_EXTENSIONS.items():
        if path.lower().endswith(ext):
            return mime
    return "text/plain"


def _auth_headers(token: Optional[str]) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def test_connection(owner: str, repo: str, token: Optional[str] = None) -> tuple[bool, str]:
    import httpx
    try:
        headers = _auth_headers(token)
        headers["Accept"] = "application/vnd.github+json"  # JSON repo metadata, not raw
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
        if resp.status_code == 404:
            return False, f"Repository '{owner}/{repo}' not found or not accessible with the given token."
        if resp.status_code == 401:
            return False, "GitHub authentication failed (401) — check the personal access token."
        resp.raise_for_status()
        data = resp.json()
        visibility = "private" if data.get("private") else "public"
        return True, f"Connected — {owner}/{repo} is a {visibility} repo (default branch: {data.get('default_branch')})."
    except Exception as e:
        return False, str(e)


async def _fetch_one_file(client, owner: str, repo: str, path: str, ref: Optional[str]) -> str:
    params = {"ref": ref} if ref else {}
    resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}", params=params)
    if resp.status_code == 404:
        raise RuntimeError(f"GitHub path not found: {owner}/{repo}/{path}" + (f"@{ref}" if ref else ""))
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        # The raw media type only applies to files — a JSON body here means `path` is a directory.
        raise IsADirectoryError(resp.json())
    return resp.text


async def fetch_github(
    owner: str,
    repo: str,
    path: str = "",
    branch: Optional[str] = None,
    token: Optional[str] = None,
) -> tuple[bytes, str]:
    import httpx

    if not owner or not repo:
        raise ValueError("GitHub owner and repo are required, e.g. owner=anthropics repo=claude-code")

    headers = _auth_headers(token)
    clean_path = path.strip().lstrip("/")

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        try:
            text = await _fetch_one_file(client, owner, repo, clean_path, branch)
            return f"=== FILE: {clean_path or '(root)'} ===\n{text}".encode("utf-8"), _guess_mime(clean_path)
        except IsADirectoryError as e:
            entries = e.args[0]
            if not isinstance(entries, list):
                raise RuntimeError(f"Unexpected GitHub response for path '{clean_path}'.")
            file_entries = [en for en in entries if en.get("type") == "file"][:_MAX_FILES]
            if not file_entries:
                raise RuntimeError(f"No files found under '{clean_path}' in {owner}/{repo}.")

            formatted: list[str] = []
            for entry in file_entries:
                entry_path = entry["path"]
                try:
                    text = await _fetch_one_file(client, owner, repo, entry_path, branch)
                    formatted.append(f"=== FILE: {entry_path} ===\n{text}")
                except Exception as file_err:
                    formatted.append(f"=== FILE: {entry_path} (failed to fetch: {file_err}) ===")

            if len(entries) > _MAX_FILES:
                formatted.append(f"[... {len(entries) - _MAX_FILES} additional files in this directory were not ingested]")

            return "\n\n".join(formatted).encode("utf-8"), "text/plain"
