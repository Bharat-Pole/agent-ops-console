from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.governance import governance_repo
from app.domains.governance import service as governance

router = APIRouter()


@router.get("/v1/governance/policy")
async def get_policy() -> JSONResponse:
    rules, path_defs = await governance_repo.get_all_policy_rules(), await governance_repo.get_all_path_definitions()
    return JSONResponse(content={"policyRules": rules, "pathDefinitions": path_defs})


@router.patch("/v1/governance/policy-rule")
async def update_policy_rule_route(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await governance.update_policy_rule(
            body.get("capability_tier"), body.get("risk_tier"), body.get("governance_path"),
            body.get("actorPersona", "Platform Admin"),
        )
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.patch("/v1/governance/path-definition/{path}")
async def update_path_definition_route(path: str, body: dict[str, Any]) -> JSONResponse:
    result = await governance.update_path_definition(path, body, body.get("actorPersona", "Platform Admin"))
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Path definition not found."})
    return JSONResponse(content=result)


@router.get("/v1/governance/exceptions")
async def list_exceptions() -> JSONResponse:
    expired = await governance_repo.expire_due_exceptions()
    if expired:
        print(f"[governance] auto-expired {expired} exception(s) past their expiry date.")
    return JSONResponse(content={"exceptions": await governance_repo.get_all_exceptions()})


@router.post("/v1/governance/exceptions")
async def grant_exception_route(body: dict[str, Any]) -> JSONResponse:
    try:
        result = await governance.grant_exception(body, body.get("actorPersona", "Governance Officer"))
        return JSONResponse(status_code=201, content=result)
    except ValueError as err:
        return JSONResponse(status_code=400, content={"message": str(err)})


@router.post("/v1/governance/exceptions/{exception_id}/revoke")
async def revoke_exception_route(exception_id: str, body: dict[str, Any]) -> JSONResponse:
    result = await governance.revoke_exception(exception_id, body.get("actorPersona", "Governance Officer"))
    if result is None:
        return JSONResponse(status_code=404, content={"message": "Exception not found."})
    return JSONResponse(content=result)
