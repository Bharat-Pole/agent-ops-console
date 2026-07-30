from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.approvals import decide_approval

router = APIRouter()


@router.post("/v1/approvals/{approval_id}/decide")
async def decide(approval_id: str, body: dict[str, Any]) -> JSONResponse:
    decision = body.get("decision")
    note = body.get("note") or ""
    actor_persona = body.get("actorPersona") or "Governance Officer"
    result = await decide_approval(approval_id, decision, note, actor_persona)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Approval not found."})
    return JSONResponse(content=result)
