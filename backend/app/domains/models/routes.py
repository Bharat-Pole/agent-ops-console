from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.models import models_repo
from app.domains.models import service as models

router = APIRouter()


@router.get("/v1/models")
async def list_models() -> JSONResponse:
    return JSONResponse(content={"models": await models_repo.get_all()})


@router.post("/v1/models")
async def register_model_route(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await models.register_model(body, body.get("actorPersona", "Platform Admin"))
        return JSONResponse(status_code=201, content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.patch("/v1/models/{model_id}")
async def update_model_route(model_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        result = await models.update_model(model_id, body, body.get("actorPersona", "Platform Admin"))
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Model not found."})
    return JSONResponse(content={"model": result})


@router.delete("/v1/models/{model_id}")
async def delete_model_route(model_id: str, actorPersona: str = "Platform Admin") -> JSONResponse:
    result = await models.delete_model(model_id, actorPersona)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Model not found."})
    return JSONResponse(content=result)
