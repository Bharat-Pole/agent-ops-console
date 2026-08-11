from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings, redacted_database_url
from .database import SessionLocal
from .router import router

app = FastAPI(title="Internal A2A Agent Card Registry", version="1.0.0")
app.include_router(router)


@app.exception_handler(HTTPException)
async def a2a_http_exception_handler(_: Request, exc: HTTPException):
    """Keep A2A domain failures in the versioned API error envelope."""
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    settings = get_settings()
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            version = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        return {"status": "ok", "database": redacted_database_url(settings.database_url), "migration_version": version}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": redacted_database_url(settings.database_url),
                "error_type": exc.__class__.__name__,
                "error": str(exc).splitlines()[0],
            },
        )
