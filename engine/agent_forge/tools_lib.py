"""Real, advisory-only tool implementations shared by the live runtime and the
code generator. Recognized capabilities get a real body; everything else is a safe
read-only stub. No write actions ever (advisory scope is LOCKED).

Currently implemented for real: web_search (DuckDuckGo via `ddgs`, no API key).
"""
from __future__ import annotations

from typing import Any


def detect_capability(name: str) -> str | None:
    """Map a tool name to a known real capability, else None (stub)."""
    n = (name or "").lower()
    if "search" in n:  # web search / search / google_search / tavily_search / web_search_tool
        return "web_search"
    return None


def web_search(query: str = "") -> str:
    """Search the web with DuckDuckGo (no API key) and return the top results."""
    try:
        from ddgs import DDGS
    except Exception:  # pragma: no cover - dependency guard
        return "[web_search unavailable: pip install ddgs]"
    try:
        results = list(DDGS().text(query or "", max_results=5))
    except Exception as e:  # pragma: no cover - network guard
        return f"[web_search error: {e}]"
    if not results:
        return "No results."
    return "\n\n".join(
        f"- {r.get('title', '')}\n  {r.get('body', '')}\n  {r.get('href', '')}" for r in results
    )


def _stub_factory(display: str):
    def _stub(query: str = "") -> str:
        return (f"[stub:{display}] this tool is not connected to a real integration — "
                f"no live result is available (query={query!r})")
    return _stub


def _render(template: str, query: str) -> str:
    """Fill every {placeholder} in a template from the single query string."""
    import re
    return re.sub(r"\{[^}]+\}", query or "", template or "")


def _http_factory(http, secret_value: str | None):
    """Build a live HTTP GET caller. Secret value is injected into the auth header
    and never returned in the response."""
    import httpx

    def _call(query: str = "") -> str:
        url = _render(http.url_template, query)
        params = {k: _render(v, query) for k, v in (http.query_params or {}).items()}
        headers = dict(http.headers or {})
        if http.auth_secret_ref and secret_value:
            hdr, _, tmpl = (http.auth_header or "Authorization: Bearer {secret}").partition(":")
            headers[hdr.strip()] = (tmpl.strip().format(secret=secret_value)
                                    if "{secret}" in tmpl else f"Bearer {secret_value}")
        try:
            r = httpx.request(http.method, url, params=params, headers=headers, timeout=15)
            return r.text[:4000]
        except Exception as e:  # pragma: no cover - network guard
            return f"[http_api error: {e}]"

    return _call


def try_http_tool(tool_def: dict, query: str = "") -> dict:
    """Ad-hoc live test for an HTTP GET tool (wizard Test phase). GET only —
    mutating methods are refused (advisory-only). Never echoes the auth header."""
    from . import secrets as vault
    from .ir import HttpToolIR

    h = tool_def.get("http") or {}
    method = str(h.get("method", "GET")).upper()
    if method != "GET":
        return {"ok": False, "error": "mutating method refused (advisory-only)"}
    http = HttpToolIR(
        method="GET", url_template=h.get("url_template", ""),
        query_params=h.get("query_params") or {}, headers=h.get("headers") or {},
        auth_secret_ref=tool_def.get("auth_secret_ref"),
        auth_header=h.get("auth_header") or "Authorization: Bearer {secret}",
    )
    secret_value = vault.get(http.auth_secret_ref) if http.auth_secret_ref else None
    import httpx
    url = _render(http.url_template, query)
    params = {k: _render(v, query) for k, v in http.query_params.items()}
    headers = dict(http.headers)
    if http.auth_secret_ref and secret_value:
        hdr, _, tmpl = http.auth_header.partition(":")
        headers[hdr.strip()] = (tmpl.strip().format(secret=secret_value) if "{secret}" in tmpl else f"Bearer {secret_value}")
    try:
        r = httpx.request("GET", url, params=params, headers=headers, timeout=15)
        return {"ok": True, "status": r.status_code, "text": r.text[:4000]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def resolve_tools(ir_tools: list[Any], secrets: dict[str, str] | None = None):
    """IR advisory tools -> live langchain tools (real where a capability is known).

    `secrets` maps tool name -> resolved secret value (from the engine vault,
    per-agent secret_refs). web_search is keyless; future paid capabilities
    (e.g. tavily) consume their per-tool secret from here. Values never leave
    the engine process."""
    from langchain_core.tools import StructuredTool

    secrets = secrets or {}
    out = []
    for t in ir_tools:
        cap = getattr(t, "capability", None)
        if cap is None:
            cap = detect_capability(t.name)  # legacy fallback (no declaration)
        if cap == "none":
            cap = None  # explicit "not connected" → honest stub, NEVER a guessed impl
        http = getattr(t, "http", None)
        if cap == "http_api" and http is not None and http.method == "GET":
            out.append(StructuredTool.from_function(
                func=_http_factory(http, secrets.get(t.func) or secrets.get(t.name)),
                name=t.func,
                description=f"{t.name}: live HTTP GET ({http.url_template}).",
            ))
        elif cap == "web_search":
            out.append(StructuredTool.from_function(
                func=web_search, name=t.func,
                description=f"{t.name}: live web search (DuckDuckGo).",
            ))
        else:
            out.append(StructuredTool.from_function(
                func=_stub_factory(t.func), name=t.func,
                description=f"{t.permission} {t.name} (advisory/read-only stub).",
            ))
    return out
