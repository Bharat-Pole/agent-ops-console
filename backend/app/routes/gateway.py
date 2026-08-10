"""The gateway's HTTP surface — Phase 6.

Two routes, and the asymmetry between them is the design:

  POST /v1/gateway/tool-call   the only governed way to invoke a tool
  GET  /v1/gateway/policy      read-only description of the checkpoint chain

**A denied call is a 200.** It carries `allowed: false`, the checkpoint that
denied it, and the audit row that was written. Returning a 4xx would make the
gateway's own refusals look like client errors and would tempt a caller to
retry-until-quiet; worse, a caller could then tell a denial apart from a network
failure only by parsing prose. The verdict is data, so it comes back as data.
Only a request too malformed to attribute (no agent, no tool, unknown consumer)
is a 400 — there is nothing truthful to record for one of those.
"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.tool_gateway import call_tool, describe_graph, describe_policy

router = APIRouter()


@router.post("/v1/gateway/tool-call")
async def gateway_tool_call(body: dict[str, Any]) -> JSONResponse:
    try:
        return JSONResponse(content=await call_tool(body))
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    except Exception as err:  # noqa: BLE001
        print("[gateway:tool-call]", err)
        return JSONResponse(
            status_code=400, content={"message": str(err) or "The gateway could not process the call."}
        )


@router.get("/v1/gateway/policy")
async def gateway_policy() -> JSONResponse:
    try:
        return JSONResponse(content=await describe_policy())
    except Exception as err:  # noqa: BLE001
        print("[gateway:policy]", err)
        return JSONResponse(
            status_code=400, content={"message": str(err) or "Could not describe the gateway policy."}
        )


# Phase 7 — the gateway view's data. Pure derivation over agents, tools,
# connectors and aggregate tool-call counts: no new tables and no new
# enforcement, by design.
@router.get("/v1/gateway/graph")
async def gateway_graph() -> JSONResponse:
    try:
        return JSONResponse(content=await describe_graph())
    except Exception as err:  # noqa: BLE001
        print("[gateway:graph]", err)
        return JSONResponse(
            status_code=400, content={"message": str(err) or "Could not build the gateway graph."}
        )
