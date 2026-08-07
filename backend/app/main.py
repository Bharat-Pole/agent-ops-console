import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.connection import close_pool, connect_pool
from app.db.migrate import run_migrations
from app.db.seed import seed_if_empty
from app.env import env
from app.domains.a2a.routes import router as a2a_router
from app.domains.admin.routes import router as admin_router
from app.domains.agents.routes import router as agents_router
from app.domains.approvals.routes import router as approvals_router
from app.domains.bootstrap.routes import router as bootstrap_router
from app.domains.chat.routes import router as chat_router
from app.domains.deployment.routes import router as deployment_router
from app.domains.evaluations.routes import router as evaluations_router
from app.domains.governance.routes import router as governance_router
from app.domains.knowledge.routes import router as knowledge_router
from app.domains.models.routes import router as models_router
from app.domains.prompts.routes import router as prompts_router
from app.domains.tools.routes import router as tools_router
from app.domains.deployment.service import backfill_deployment_state
from app.domains.scheduler.service import start_scheduler

_ROOT_DIR = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_pool()
    await run_migrations()
    await seed_if_empty()
    await backfill_deployment_state()
    start_scheduler()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bootstrap_router)
app.include_router(agents_router)
app.include_router(approvals_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(prompts_router)
app.include_router(tools_router)
app.include_router(models_router)
app.include_router(governance_router)
app.include_router(evaluations_router)
app.include_router(deployment_router)
app.include_router(admin_router)
app.include_router(a2a_router)

if os.environ.get("NODE_ENV") == "production":
    dist_dir = _ROOT_DIR / "dist"
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        return FileResponse(dist_dir / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=env.PORT, reload=True)
