from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.deployment import service as deployment

router = APIRouter()


@router.get("/v1/agents/{agent_id}/deployment/history")
async def get_deployment_history(agent_id: str) -> JSONResponse:
    try:
        result = await deployment.get_history(agent_id)
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})


@router.post("/v1/agents/{agent_id}/deployment/promote")
async def promote_deployment(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        result = await deployment.promote(agent_id, body.get("actorPersona", "Platform Admin"), body.get("reason"))
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.post("/v1/agents/{agent_id}/deployment/rollback")
async def rollback_deployment(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        result = await deployment.rollback(agent_id, body.get("actorPersona", "Platform Admin"), body.get("reason"))
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.get("/v1/agents/{agent_id}/access-grants")
async def get_access_grants(agent_id: str) -> JSONResponse:
    try:
        grants = await deployment.get_grants(agent_id)
        return JSONResponse(content={"grants": grants})
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})


@router.post("/v1/access-grants")
async def grant_access(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await deployment.grant_access(body, body.get("actorPersona", "Platform Admin"))
        return JSONResponse(status_code=201, content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.post("/v1/access-grants/{grant_id}/revoke")
async def revoke_access(grant_id: str, body: dict[str, Any]) -> JSONResponse:
    result = await deployment.revoke_access(grant_id, body.get("actorPersona", "Platform Admin"))
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Grant not found."})
    return JSONResponse(content=result)
