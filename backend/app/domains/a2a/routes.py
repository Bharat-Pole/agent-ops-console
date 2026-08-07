from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.a2a import service as a2a

router = APIRouter()


@router.get("/v1/a2a/cards")
async def list_cards() -> JSONResponse:
    return JSONResponse(content={"cards": await a2a.sync_cards()})


@router.patch("/v1/a2a/cards/{agent_id}")
async def update_card_endpoint(agent_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        result = await a2a.update_endpoint(agent_id, body.get("endpoint", ""), body.get("actorPersona", "Platform Admin"))
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
