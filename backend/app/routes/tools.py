from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.claude_service import is_claude_configured
from app.services.tool_authoring import create_tool, suggest_tool, update_tool_policy
from app.services.tool_call_log import list_tool_calls, record_tool_call

router = APIRouter()


@router.post("/v1/tools")
async def create(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await create_tool(body)
        return JSONResponse(status_code=201, content=result)
    except Exception as err:
        print("[tools:create]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Tool creation failed."})


# Phase 3.3 — policy fields only (owner, risk_level). Everything governance
# depends on (permission_ceiling, write_capable, status, approval_state) is
# unreachable from here by design; see services/tool_authoring.py.
@router.patch("/v1/tools/{tool_id}")
async def update_policy(tool_id: str, body: dict[str, Any]) -> JSONResponse:
    try:
        return JSONResponse(content=await update_tool_policy(tool_id, body))
    except LookupError:
        return JSONResponse(status_code=404, content={"message": "Tool not found."})
    except Exception as err:
        print("[tools:update_policy]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Tool update failed."})


@router.post("/v1/tools/suggest")
async def suggest(body: dict[str, Any]) -> JSONResponse:
    description = body.get("description")
    if not isinstance(description, str) or not description.strip():
        return JSONResponse(status_code=400, content={"message": "description is required."})

    if not is_claude_configured():
        return JSONResponse(status_code=503, content={"message": "ANTHROPIC_API_KEY not configured."})

    try:
        result = await suggest_tool(description)
        return JSONResponse(content=result)
    except Exception as err:
        print("[tools:suggest]", err)
        return JSONResponse(status_code=502, content={"message": str(err) or "Suggestion failed."})


# ---- Tool-call audit trail (deck slide 21, element 6) ----------------------


@router.post("/v1/tool-calls")
async def create_tool_call(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await record_tool_call(body)
        return JSONResponse(status_code=201, content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    except Exception as err:
        print("[tool-calls:create]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Could not record the tool call."})


# `gateway=true` narrows to rows the Phase 6 gateway produced — the ones whose
# result and latency were observed here rather than reported by a client.
@router.get("/v1/tool-calls")
async def get_tool_calls(
    agentId: Optional[str] = None,
    toolId: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
    gateway: Optional[bool] = None,
) -> JSONResponse:
    try:
        return JSONResponse(content=await list_tool_calls(agentId, toolId, status, limit, gateway))
    except Exception as err:
        print("[tool-calls:list]", err)
        return JSONResponse(status_code=400, content={"message": str(err) or "Could not list tool calls."})
