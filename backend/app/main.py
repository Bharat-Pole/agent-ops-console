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
from app.routes.agents import router as agents_router
from app.routes.approvals import router as approvals_router
from app.routes.bootstrap import router as bootstrap_router
from app.routes.chat import router as chat_router
from app.services.scheduler import start_scheduler

_ROOT_DIR = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_pool()
    await run_migrations()
    await seed_if_empty()
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

if os.environ.get("NODE_ENV") == "production":
    dist_dir = _ROOT_DIR / "dist"
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        return FileResponse(dist_dir / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=env.PORT, reload=True)
