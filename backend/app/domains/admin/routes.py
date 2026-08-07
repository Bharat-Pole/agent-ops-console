from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.admin import service as admin

router = APIRouter()


@router.patch("/v1/admin/feature-flags/{key}")
async def update_feature_flag_route(key: str, body: dict[str, Any]) -> JSONResponse:
    try:
        result = await admin.update_feature_flag(key, bool(body.get("enabled")), body.get("actorPersona", "Platform Admin"))
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
