"""Agent Ops & Governance Platform — backend (modular monolith).

Increment A surface: auth, registry (control records + lifecycle + intent),
audit. CORS is an explicit allowlist (never "*" — carried lesson); every
router is session-authenticated.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import audit as audit_module
from .assets.approvals_router import router as approvals_router
from .assets.bindings_router import router as bindings_router
from .assets.kb_router import rag_router, router as kb_router
from .assets.mcp import router as mcp_router
from .assets.models_router import router as models_router
from .assets.prompts_router import router as prompts_router
from .assets.tools_router import router as tools_router
from .assets.vault import router as vault_router
from .auth.deps import current_user_dep
from .auth.router import router as auth_router
from .config import settings
from .engine.runs_router import router as runs_router
from .engine.workflows_router import router as workflows_router
from .deployment.router import router as deployment_router
from .evaluation.router import router as evaluation_router
from .governance import register_event_handlers, router as governance_router
from .telemetry import router as telemetry_router
from .recommender.router import router as recommender_router
from .registry.router import router as registry_router


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Ops & Governance Platform", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,  # explicit allowlist only
        allow_credentials=True,                   # session cookie
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(auth_router)
    app.include_router(registry_router)
    app.include_router(recommender_router)
    app.include_router(bindings_router)
    app.include_router(tools_router)
    app.include_router(mcp_router)
    app.include_router(prompts_router)
    app.include_router(kb_router)
    app.include_router(rag_router)
    app.include_router(models_router)
    app.include_router(vault_router)
    app.include_router(approvals_router)
    app.include_router(workflows_router)
    app.include_router(runs_router)
    app.include_router(evaluation_router)
    app.include_router(governance_router)
    app.include_router(deployment_router)
    app.include_router(telemetry_router)
    register_event_handlers()  # re-certification trigger (asset.approved → needs_review)
    app.include_router(audit_module.router, dependencies=[Depends(current_user_dep)])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "platform-backend", "version": app.version}

    return app


app = create_app()
