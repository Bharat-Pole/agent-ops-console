import os

from dotenv import load_dotenv

load_dotenv()


class Env:
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/agent_ops")
    PORT = int(os.environ.get("PORT", "8787"))
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or None
    ANTHROPIC_MODEL_MINIMAL = os.environ.get("ANTHROPIC_MODEL_MINIMAL", "claude-haiku-4-5-20251001")
    ANTHROPIC_MODEL_STANDARDIZED = os.environ.get("ANTHROPIC_MODEL_STANDARDIZED", "claude-sonnet-5")
    ANTHROPIC_MODEL_ADVANCED = os.environ.get("ANTHROPIC_MODEL_ADVANCED", "claude-opus-5")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or None
    OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


env = Env()
