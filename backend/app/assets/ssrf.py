"""SSRF guard for outbound test calls (tool try-out, MCP health/discovery).
Carried lesson from the /v1/tools/try hole: the server must never be a proxy
into private address space. Hostnames are RESOLVED and every address checked —
DNS-rebinding-style names that resolve private are denied unless explicitly
allowlisted (settings.tryout_private_host_allowlist, e.g. for local MCP dev).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from ..config import settings


def check_url(url: str) -> tuple[bool, str]:
    """(allowed, reason). Reasons are safe to surface to the client."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "unparseable URL"
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme {parsed.scheme!r} not allowed (http/https only)"
    host = parsed.hostname
    if not host:
        return False, "URL has no host"
    if host in settings.tryout_private_host_allowlist:
        return True, "host allowlisted"
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        return False, f"host does not resolve: {exc}"
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, (f"host resolves to non-public address {addr} — denied "
                           "(add to PLATFORM_TRYOUT_PRIVATE_HOST_ALLOWLIST for local development)")
    return True, "ok"
