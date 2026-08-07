"""Engine-side secrets vault.

Named secrets live in engine/.secrets.json (gitignored; path overridable via the
AGENT_FORGE_SECRETS env var — tests point it at a tmp file). The console manages
entries by NAME through /v1/secrets; secret VALUES never leave the engine — they
are resolved here at run time and injected into model/tool clients only.

Resolution chain for the model key (locked):
  per-request api_key (legacy UI override)  >  agent's secret_refs["model"]
  >  vault "GEMINI_DEFAULT"  >  None (client falls through to env GOOGLE_API_KEY)
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
DEFAULT_MODEL_SECRET = "GEMINI_DEFAULT"
# Vault default for the opt-in Claude runtime target (same flow as GEMINI_DEFAULT).
ANTHROPIC_DEFAULT_SECRET = "ANTHROPIC_DEFAULT"


def vault_path() -> Path:
    override = os.getenv("AGENT_FORGE_SECRETS")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / ".secrets.json"


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.fullmatch(name or ""))


def _load() -> dict[str, str]:
    p = vault_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        secrets = data.get("secrets", data) if isinstance(data, dict) else {}
        return {k: v for k, v in secrets.items() if isinstance(k, str) and isinstance(v, str)}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _save(secrets: dict[str, str]) -> None:
    p = vault_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # atomic write: tmp file in the same dir, then replace
    fd, tmp = tempfile.mkstemp(prefix=".secrets-", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"secrets": secrets}, f, indent=2, sort_keys=True)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def list_names() -> list[str]:
    return sorted(_load())


def get(name: str | None) -> str | None:
    if not name:
        return None
    return _load().get(name)


def put(name: str, value: str) -> None:
    if not valid_name(name):
        raise ValueError(f"invalid secret name: {name!r}")
    if not value:
        raise ValueError("secret value must be non-empty")
    secrets = _load()
    secrets[name] = value
    _save(secrets)


def delete(name: str) -> bool:
    secrets = _load()
    if name not in secrets:
        return False
    del secrets[name]
    _save(secrets)
    return True


def resolve_model_key(secret_refs: dict[str, str] | None, request_key: str | None = None,
                      provider: str = "gemini") -> tuple[str | None, str]:
    """Resolve the LLM api key. Returns (key_or_None, credential_source).

    provider selects the vault default: 'claude' → ANTHROPIC_DEFAULT, else
    GEMINI_DEFAULT. The per-agent secret_refs['model'] binding wins either way
    (the user bound it deliberately for that agent)."""
    if request_key:
        return request_key, "request"
    ref = (secret_refs or {}).get("model")
    if ref:
        v = get(ref)
        if v:
            return v, "agent_secret"
    default_name = ANTHROPIC_DEFAULT_SECRET if provider == "claude" else DEFAULT_MODEL_SECRET
    v = get(default_name)
    if v:
        return v, "vault_default"
    return None, "env"  # client falls through to GOOGLE_API_KEY / ANTHROPIC_API_KEY / ADC


def resolve_tool_secrets(secret_refs: dict[str, str] | None) -> dict[str, str]:
    """{tool_name: secret_value} for every non-'model' ref that resolves."""
    out: dict[str, str] = {}
    for tool_name, secret_name in (secret_refs or {}).items():
        if tool_name == "model":
            continue
        v = get(secret_name)
        if v:
            out[tool_name] = v
    return out
