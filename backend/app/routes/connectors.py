from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.connector_authoring import create_connector, update_connector
from app.services.connector_backlog import list_backlog, update_backlog_item
from app.services.connector_health import list_connector_tools, run_healthcheck, toggle_offline
from app.services.connector_policy import update_connector_policy

router = APIRouter()


# ---- Connector prioritization backlog (deck slide 21, element 7) -----------
# An *assessment* of candidate systems, distinct from `connectors`, which are
# servers we actually talk to. No POST: the candidate set is the SOW's seven
# systems of record and is not ours to extend — see services/connector_backlog.py.


@router.get("/v1/connector-backlog")
async def get_backlog() -> JSONResponse:
    try:
        return JSONResponse(content=await list_backlog())
    except Exception as err:
        print("[backlog:list]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Could not list the backlog."})


@router.patch("/v1/connector-backlog/{item_id}")
async def patch_backlog(item_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        return JSONResponse(content=await update_backlog_item(item_id, body))
    except LookupError:
        return JSONResponse(status_code=404, content={"message": "Backlog item not found."})
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    except Exception as err:
        print("[backlog:update]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Could not update the backlog."})


# ---- Connector CRUD (Blueprint §3.5 "Register MCP server") -----------------


@router.post("/v1/connectors")
async def create(body: dict[str, Any]) -> JSONResponse:
    try:
        return JSONResponse(status_code=201, content=await create_connector(body))
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    except Exception as err:
        print("[connectors:create]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Could not register the connector."})


@router.patch("/v1/connectors/{connector_id}")
async def update(connector_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        return JSONResponse(content=await update_connector(connector_id, body))
    except LookupError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    except Exception as err:
        print("[connectors:update]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Could not update the connector."})


# Phase 6 — the gateway policy fields (slide 21 elements 4 and 5). A separate
# route from the PATCH above on purpose: that one edits how we reach a server,
# this one declares what it may expose and to whom. See services/connector_policy.py.
@router.patch("/v1/connectors/{connector_id}/policy")
async def update_policy(connector_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        return JSONResponse(content=await update_connector_policy(connector_id, body))
    except LookupError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    except Exception as err:
        print("[connectors:policy]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Could not update the policy."})


@router.post("/v1/connectors/{connector_id}/healthcheck")
async def healthcheck(connector_id: str) -> JSONResponse:
    try:
        return JSONResponse(content=await run_healthcheck(connector_id))
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
    except Exception as err:
        print("[connectors:healthcheck]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Healthcheck failed."})


@router.post("/v1/connectors/{connector_id}/toggle-offline")
async def toggle(connector_id: str) -> JSONResponse:
    try:
        return JSONResponse(content=await toggle_offline(connector_id))
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
    except Exception as err:
        print("[connectors:toggle]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Toggle failed."})


# MCP tools/list — the discovery seam. Returns the connector's advertised tools
# plus a diff against the catalog (undiscovered / orphaned).
@router.get("/v1/connectors/{connector_id}/tools")
async def tools(connector_id: str) -> JSONResponse:
    try:
        return JSONResponse(content=await list_connector_tools(connector_id))
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
    except Exception as err:
        print("[connectors:tools]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "tools/list failed."})
