import os

from dotenv import load_dotenv

load_dotenv(override=True)  # override=True ensures fresh env values on reload



class Env:
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/agent_ops")
    PORT = int(os.environ.get("PORT", "8787"))
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or None
    ANTHROPIC_MODEL_MINIMAL = os.environ.get("ANTHROPIC_MODEL_MINIMAL", "claude-haiku-4-5-20251001")
    ANTHROPIC_MODEL_STANDARDIZED = os.environ.get("ANTHROPIC_MODEL_STANDARDIZED", "claude-sonnet-5")
    ANTHROPIC_MODEL_ADVANCED = os.environ.get("ANTHROPIC_MODEL_ADVANCED", "claude-opus-5")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or None
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or None
    OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    OPENAI_EMBEDDING_DIMENSION = int(os.environ.get("OPENAI_EMBEDDING_DIMENSION", "1536"))
    # No default price is assumed — cost estimates only appear once this is explicitly set,
    # since a hardcoded price would silently go stale.
    OPENAI_EMBEDDING_COST_PER_1K = (
        float(os.environ["OPENAI_EMBEDDING_COST_PER_1K"])
        if os.environ.get("OPENAI_EMBEDDING_COST_PER_1K")
        else None
    )

    # ── External knowledge connectors (Phase D) ──────────────────────────────
    CONFLUENCE_BASE_URL = os.environ.get("CONFLUENCE_BASE_URL") or None
    CONFLUENCE_EMAIL = os.environ.get("CONFLUENCE_EMAIL") or None
    CONFLUENCE_API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN") or None
    JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL") or None
    JIRA_EMAIL = os.environ.get("JIRA_EMAIL") or None
    JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN") or None
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or None
    SERVICENOW_INSTANCE_URL = os.environ.get("SERVICENOW_INSTANCE_URL") or None
    SERVICENOW_USER = os.environ.get("SERVICENOW_USER") or None
    SERVICENOW_PASSWORD = os.environ.get("SERVICENOW_PASSWORD") or None
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or None


env = Env()
