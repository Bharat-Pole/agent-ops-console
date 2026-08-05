from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.repositories import agents_repo
from app.services.lifecycle import enable_demo_mode, propose_config_change, recertify, set_lifecycle
from app.services.registration import register_agent
from app.services.tool_binding import bind_tool
from app.services.knowledge_binding import bind_knowledge_source

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@router.post("/v1/agents/register")
async def register(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await register_agent(body)
        return JSONResponse(status_code=201, content=result)
    except Exception as err:
        print("[register]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Registration failed."})


# Generic sync endpoint used by the client's still-simulated provision()/
# triggerPipeline() job callbacks to keep server state consistent with the
# locally-animated tracks/lifecycle progression.
@router.patch("/v1/agents/{agent_id}")
async def patch_agent(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    agent = await agents_repo.merge_patch(agent_id, {**body, "updated_at": _now_iso()})
    if agent is None:
        return JSONResponse(status_code=404, content={"message": "Agent not found."})
    return JSONResponse(content={"agent": agent})


@router.post("/v1/agents/{agent_id}/lifecycle")
async def lifecycle(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    result = await set_lifecycle(agent_id, body.get("status"))
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Agent not found."})
    return JSONResponse(content=result)


@router.post("/v1/agents/{agent_id}/recertify")
async def recertify_route(agent_id: str) -> JSONResponse:
    result = await recertify(agent_id)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Agent not found."})
    return JSONResponse(content=result)


@router.post("/v1/agents/{agent_id}/demo-mode")
async def demo_mode_route(agent_id: str) -> JSONResponse:
    result = await enable_demo_mode(agent_id)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Agent not found."})
    return JSONResponse(content=result)


@router.post("/v1/agents/{agent_id}/config-change")
async def config_change(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    result = await propose_config_change(agent_id, body.get("groupKey"), body.get("field"), body.get("newValue"))
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Agent not found."})
    return JSONResponse(content=result)


@router.post("/v1/agents/{agent_id}/tools/bind")
async def bind_tool_route(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    result = await bind_tool(agent_id, body.get("toolId"))
    return JSONResponse(status_code=200 if result.get("ok") else 400, content=result)


@router.post("/v1/agents/{agent_id}/knowledge/bind")
async def bind_knowledge_route(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    result = await bind_knowledge_source(agent_id, body.get("sourceId"))
    return JSONResponse(status_code=200 if result.get("ok") or result.get("pending") else 400, content=result)
