from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domains.evaluations import eval_runs_repo
from app.domains.evaluations import service as evaluation

router = APIRouter()


@router.post("/v1/evaluations/{pack_id}/run")
async def run_evaluation_route(pack_id: str, actorPersona: str = "Evaluator / QA Reviewer") -> JSONResponse:
    try:
        result = await evaluation.run_evaluation(pack_id, actorPersona)
        return JSONResponse(content=result)
    except ValueError as err:
        status = 409 if "suspended" in str(err) or "retired" in str(err) else 404
        return JSONResponse(status_code=status, content={"message": str(err)})


@router.post("/v1/evaluations/{pack_id}/regenerate")
async def regenerate_pack_route(pack_id: str, actorPersona: str = "Evaluator / QA Reviewer") -> JSONResponse:
    try:
        result = await evaluation.regenerate_pack(pack_id, actorPersona)
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})


@router.get("/v1/evaluations/{pack_id}/runs")
async def get_run_history(pack_id: str) -> JSONResponse:
    return JSONResponse(content={"runs": await eval_runs_repo.get_for_pack(pack_id)})


@router.get("/v1/evaluations/{pack_id}/evidence-pack")
async def get_evidence_pack(pack_id: str) -> JSONResponse:
    try:
        result = await evaluation.build_evidence_pack(pack_id)
        return JSONResponse(content=result)
    except ValueError as err:
        return JSONResponse(status_code=404, content={"message": str(err)})
