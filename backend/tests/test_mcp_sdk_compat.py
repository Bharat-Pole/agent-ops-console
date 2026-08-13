"""Guards against the MCP SDK moving under us.

The connector path broke silently once already: our pin is `mcp>=1.0`, a fresh
install resolved to v2, and v2 renamed the streamable-http client
(`streamablehttp_client` -> `streamable_http_client`), moved auth headers onto
an httpx client, and switched model fields from camelCase to snake_case
(`inputSchema` -> `input_schema`, `isError` -> `is_error`).

Every failure surfaced as "unhandled errors in a TaskGroup (1 sub-exception)",
which told nobody anything — so the flattening of that message is covered here
too. The tests below assert against the INSTALLED SDK, so the next rename fails
here rather than in someone's browser.

The live end-to-end test is opt-in (MCP_LIVE_TEST=1) because it binds a port.
"""
from __future__ import annotations

import importlib
import os
import socket
import threading
import time

import pytest

from app.assets.mcp import DiscoveryError, explain_exc, open_transport, sdk_attr


# ---- the symbols open_transport depends on still exist -----------------------

def test_streamable_http_client_resolves_under_the_installed_sdk():
    """One of the two spellings must exist, or the default transport is dead."""
    module = importlib.import_module("mcp.client.streamable_http")
    legacy = getattr(module, "streamablehttp_client", None)      # v1
    modern = getattr(module, "streamable_http_client", None)     # v2
    assert legacy is not None or modern is not None, (
        "installed mcp SDK exposes no streamable-http client under either name")


def test_v2_header_injection_path_exists_when_v2_is_installed():
    """v2 carries auth headers on an httpx client; that factory must be there."""
    module = importlib.import_module("mcp.client.streamable_http")
    if getattr(module, "streamablehttp_client", None) is not None:
        pytest.skip("v1 SDK installed — headers are passed directly")
    assert hasattr(module, "create_mcp_http_client"), (
        "v2 SDK without create_mcp_http_client: authenticated connectors would break")


def test_sse_client_still_takes_headers_directly():
    import inspect

    from mcp.client.sse import sse_client
    assert "headers" in inspect.signature(sse_client).parameters


def test_client_session_is_importable_from_the_package_root():
    from mcp import ClientSession
    assert ClientSession is not None


def test_unknown_transport_falls_through_to_streamable_http():
    """Only 'sse' is special-cased; anything else takes the default path."""
    import inspect
    source = inspect.getsource(open_transport)
    assert 'transport == "sse"' in source


# ---- cross-version attribute reads -------------------------------------------

class _V1Tool:
    inputSchema = {"type": "object"}
    isError = True


class _V2Tool:
    input_schema = {"type": "object"}
    is_error = True


@pytest.mark.parametrize("obj", [_V1Tool(), _V2Tool()])
def test_sdk_attr_reads_both_naming_conventions(obj):
    assert sdk_attr(obj, "input_schema", "inputSchema", default={}) == {"type": "object"}
    assert sdk_attr(obj, "is_error", "isError", default=False) is True


def test_sdk_attr_falls_back_when_no_name_matches():
    assert sdk_attr(object(), "nope", "also_nope", default="fallback") == "fallback"


def test_installed_sdk_tool_model_is_covered_by_sdk_attr():
    """Whatever the SDK calls it today, our accessor must find it."""
    from mcp.types import Tool
    fields = set(getattr(Tool, "model_fields", {}))
    assert fields & {"input_schema", "inputSchema"}, (
        f"Tool exposes neither spelling of the input schema: {sorted(fields)}")


# ---- error legibility --------------------------------------------------------

def test_exception_groups_are_flattened_to_the_real_cause():
    """The bug that hid every MCP failure behind a useless TaskGroup message."""
    group = ExceptionGroup("unhandled errors in a TaskGroup", [
        ExceptionGroup("inner", [AttributeError("'Tool' object has no attribute 'inputSchema'")]),
    ])
    message = explain_exc(group)
    assert "TaskGroup" not in message
    assert "inputSchema" in message
    assert "AttributeError" in message


def test_multiple_causes_are_all_reported():
    group = ExceptionGroup("boom", [ValueError("first"), KeyError("second")])
    message = explain_exc(group)
    assert "first" in message and "second" in message


def test_a_plain_exception_keeps_its_type_and_message():
    assert explain_exc(ConnectionRefusedError("connection refused")) == \
        "ConnectionRefusedError: connection refused"


def test_an_empty_message_still_names_the_type():
    assert explain_exc(TimeoutError()) == "TimeoutError"


# ---- live round trip (opt-in) ------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(os.environ.get("MCP_LIVE_TEST") != "1",
                    reason="binds a port; set MCP_LIVE_TEST=1 to run")
def test_live_discovery_and_call_against_a_real_server():
    """Full protocol round trip through the platform's own client code."""
    import sys
    from pathlib import Path

    import uvicorn
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from sample_mcp_server import build_server

    from app.assets.mcp import discover

    server, _kind = build_server()
    port = _free_port()
    config = uvicorn.Config(server.streamable_http_app(), host="127.0.0.1",
                            port=port, log_level="error")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not uv.started and time.time() < deadline:
        time.sleep(0.1)
    assert uv.started, "sample MCP server did not start"

    try:
        endpoint = f"http://127.0.0.1:{port}/mcp"
        tools = discover(endpoint, "streamable_http", {}, timeout=20.0)
        names = {t.name for t in tools}
        assert {"lookup_policy", "list_policies"} <= names
        schema = next(t.input_schema for t in tools if t.name == "lookup_policy")
        assert "topic" in (schema.get("properties") or {}), schema
    finally:
        uv.should_exit = True
        thread.join(timeout=10)


@pytest.mark.skipif(os.environ.get("MCP_LIVE_TEST") != "1",
                    reason="binds a port; set MCP_LIVE_TEST=1 to run")
def test_a_refused_connection_reports_something_actionable():
    port = _free_port()   # nothing listening
    with pytest.raises(DiscoveryError) as excinfo:
        discover_mod = importlib.import_module("app.assets.mcp")
        discover_mod.discover(f"http://127.0.0.1:{port}/mcp", "streamable_http", {}, timeout=5.0)
    assert "TaskGroup" not in str(excinfo.value)
