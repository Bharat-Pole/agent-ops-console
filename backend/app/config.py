"""Backend settings. Local-first defaults; every external dependency is
overridable via environment so the same image runs under docker-compose or GCP.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SQLite default keeps the repo runnable with zero services; compose/CI set
    # DATABASE_URL=postgresql+psycopg://... (Postgres is the canonical target).
    database_url: str = "sqlite:///./platform.db"
    session_secret: str = "dev-only-change-me"  # compose/CI must override
    session_ttl_hours: int = 12
    # CORS allowlist — the frontend origin ONLY (never "*"; carried lesson).
    frontend_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # LLM provider seam (Pass 0). auto → gemini when a key is set, else none
    # (deterministic-only paths). "fake" is the labeled CI harness and must be
    # requested explicitly — it is never a silent fallback (Decision 10).
    llm_provider: str = "auto"  # auto | gemini | fake | none
    gemini_api_key: str | None = None
    # Rolling aliases: pinned model ids get retired for new API keys (verified
    # 2026-08-06: gemini-2.5-flash and text-embedding-004 both 404). Override
    # per-deployment if you need a pinned version.
    gemini_model: str = "gemini-flash-latest"
    gemini_embedding_model: str = "gemini-embedding-001"

    # Asset Studio (Increment C)
    file_store_dir: str = "./filestore"  # GCS bucket behind the same adapter later
    # Fernet key for secrets-at-rest; derived from session_secret when unset
    # (dev convenience) — set a dedicated PLATFORM_VAULT_KEY in real deployments.
    vault_key: str | None = None
    # SSRF allowlist for tool try-out targets resolving to private ranges
    tryout_private_host_allowlist: list[str] = []

    model_config = {"env_prefix": "PLATFORM_", "env_file": ".env"}


settings = Settings()
