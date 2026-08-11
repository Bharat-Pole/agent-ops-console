from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.prompts import prompts_repo
from app.domains.prompts import service as prompts_service

router = APIRouter()


@router.get("/v1/prompts")
async def list_prompts() -> JSONResponse:
    return JSONResponse(content={"prompts": await prompts_repo.get_all()})


@router.get("/v1/prompts/approved-pack")
async def approved_pack_route(domain: str | None = None, agent_type: str | None = None) -> JSONResponse:
    pack = await prompts_service.export_approved_pack(domain, agent_type)
    return JSONResponse(content=pack)


@router.post("/v1/prompts")
async def create(body: dict[str, Any]) -> JSONResponse:
    prompt = await prompts_service.create_prompt(body)
    return JSONResponse(status_code=201, content={"prompt": prompt})


@router.post("/v1/prompts/generate")
async def generate(body: dict[str, Any]) -> JSONResponse:
    prompt = await prompts_service.generate_prompt(body)
    return JSONResponse(status_code=201, content={"prompt": prompt})


# Preview-only draft — returns a suggested name + body without persisting a
# new prompt row. Used by the "Generate with AI" review dialog (Phase 4 create
# flow) and by the in-place regenerate button on an existing draft's editor.
@router.post("/v1/prompts/generate-body")
async def generate_body_route(body: dict[str, Any]) -> JSONResponse:
    kind = body.get("kind") or "template"
    category = body.get("category") or "agent"
    context = body.get("context") or {}
    draft = await prompts_service.generate_draft(kind, category, context)
    return JSONResponse(content=draft)


@router.patch("/v1/prompts/{prompt_id}")
async def patch(prompt_id: str, body: dict[str, Any]) -> JSONResponse:
    prompt = await prompts_service.update_fields(prompt_id, body)
    if prompt is None:
        return JSONResponse(status_code=404, content={"message": "Prompt not found."})
    return JSONResponse(content={"prompt": prompt})


@router.post("/v1/prompts/{prompt_id}/new-version")
async def new_version_route(prompt_id: str) -> JSONResponse:
    prompt = await prompts_service.new_version(prompt_id)
    if prompt is None:
        return JSONResponse(status_code=404, content={"message": "Prompt not found."})
    return JSONResponse(content={"prompt": prompt})


@router.get("/v1/prompts/{prompt_id}/compare")
async def compare_route(prompt_id: str, a: str, b: str) -> JSONResponse:
    try:
        result = await prompts_service.compare_versions(prompt_id, a, b)
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
    return JSONResponse(content=result)


@router.post("/v1/prompts/{prompt_id}/rollback")
async def rollback_route(prompt_id: str, body: dict[str, Any]) -> JSONResponse:
    target_version = body.get("version")
    actor_persona = body.get("actorPersona") or "Governance Officer"
    if not target_version:
        return JSONResponse(status_code=400, content={"message": "version is required."})
    try:
        result = await prompts_service.rollback_to(prompt_id, target_version, actor_persona)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Prompt not found."})
    return JSONResponse(content=result)


@router.delete("/v1/prompts/{prompt_id}")
async def delete_route(prompt_id: str, actorPersona: str = "Governance Officer") -> JSONResponse:
    try:
        result = await prompts_service.delete_prompt(prompt_id, actorPersona)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Prompt not found."})
    return JSONResponse(content=result)


@router.post("/v1/prompts/{prompt_id}/decide")
async def decide_route(prompt_id: str, body: dict[str, Any]) -> JSONResponse:
    decision = body.get("decision") or "approved"
    actor_persona = body.get("actorPersona") or "Governance Officer"
    result = await prompts_service.decide(prompt_id, decision, actor_persona)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Prompt not found."})
    return JSONResponse(content=result)


@router.post("/v1/prompts/{prompt_id}/deprecate")
async def deprecate_route(prompt_id: str, body: dict[str, Any]) -> JSONResponse:
    actor_persona = body.get("actorPersona") or "Governance Officer"
    result = await prompts_service.deprecate(prompt_id, actor_persona)
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Prompt not found."})
    return JSONResponse(content=result)
