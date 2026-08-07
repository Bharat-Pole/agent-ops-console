from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.tools import mcp_connectors_repo, tools_repo
from app.domains.tools import mcp_service as mcp
from app.domains.tools import tools_service as tools

router = APIRouter()


@router.get("/v1/tools")
async def list_tools() -> JSONResponse:
    return JSONResponse(content={"tools": await tools_repo.get_all()})


@router.post("/v1/tools")
async def register_tool_route(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await tools.register_tool(body, body.get("actorPersona", "Platform Engineer"))
        return JSONResponse(status_code=201, content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.patch("/v1/tools/{tool_id}")
async def update_tool_route(tool_id: str, body: dict[str, Any]) -> JSONResponse:
    result = await tools.update_tool(tool_id, body, body.get("actorPersona", "Platform Engineer"))
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Tool not found."})
    return JSONResponse(content={"tool": result})


@router.delete("/v1/tools/{tool_id}")
async def delete_tool_route(tool_id: str, actorPersona: str = "Platform Engineer") -> JSONResponse:
    try:
        result = await tools.delete_tool(tool_id, actorPersona)
    except ValueError as err:
        return JSONResponse(status_code=409, content={"message": str(err)})
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Tool not found."})
    return JSONResponse(content=result)


@router.get("/v1/mcp/connectors")
async def list_connectors() -> JSONResponse:
    return JSONResponse(content={"connectors": await mcp_connectors_repo.get_all()})


@router.post("/v1/mcp/connectors")
async def register_connector_route(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await mcp.register_connector(body, body.get("actorPersona", "Platform Engineer"))
        return JSONResponse(status_code=201, content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.post("/v1/mcp/connectors/{connector_id}/healthcheck")
async def healthcheck_route(connector_id: str, actorPersona: str = "Platform Engineer") -> JSONResponse:
    result = await mcp.healthcheck_connector(connector_id, actorPersona)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Connector not found."})
    return JSONResponse(content=result)


@router.post("/v1/mcp/connectors/{connector_id}/toggle")
async def toggle_connector_route(connector_id: str, actorPersona: str = "Platform Engineer") -> JSONResponse:
    result = await mcp.toggle_connector(connector_id, actorPersona)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Connector not found."})
    return JSONResponse(content=result)


@router.delete("/v1/mcp/connectors/{connector_id}")
async def delete_connector_route(connector_id: str, actorPersona: str = "Platform Engineer") -> JSONResponse:
    try:
        result = await mcp.delete_connector(connector_id, actorPersona)
    except ValueError as err:
        return JSONResponse(status_code=409, content={"message": str(err)})
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Connector not found."})
    return JSONResponse(content=result)
