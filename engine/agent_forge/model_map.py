"""Map console model refs to concrete, currently-served model ids.

Strips the `vertex://` scheme, then applies a retirement alias table: the console's
spec-era configs name `gemini-1.5-*`, which Google removed from the API — requests
404 (`models/gemini-1.5-flash is not found for API version v1beta`). Alias them to
the current known-good family (the same one agent_onboard runs on).
"""
from __future__ import annotations

# Retired families → current equivalents (see agent_onboard/config.py: default
# gemini-3.6-flash, fallbacks gemini-3.5-flash / gemini-3.1-flash-lite).
MODEL_ALIASES: dict[str, str] = {
    "gemini-1.5-flash": "gemini-3.6-flash",
    "gemini-1.5-flash-8b": "gemini-3.6-flash",
    "gemini-1.5-pro": "gemini-3.6-flash",
    "gemini-1.0-pro": "gemini-3.6-flash",
    "gemini-pro": "gemini-3.6-flash",
    "gemini-2.0-flash": "gemini-3.6-flash",
}

# Used ONLY when model_primary is absent (also raises a build blocker in validator).
MISSING_FALLBACK = "gemini-3.6-flash"

# Fallback used when the config's model_fallback aliases to the same id as primary.
SECONDARY_FALLBACK = "gemini-3.5-flash"

# Default model for the opt-in Claude runtime target (exact id, no date suffix).
CLAUDE_DEFAULT = "claude-opus-5"


def map_model(ref: str | None) -> str:
    """'vertex://gemini-1.5-pro' -> 'gemini-3.6-flash'; current ids pass through."""
    if not ref:
        return MISSING_FALLBACK
    ref = ref.strip()
    for scheme in ("vertex://", "aistudio://", "genai://", "claude://", "models/"):
        if ref.startswith(scheme):
            ref = ref[len(scheme):]
    return MODEL_ALIASES.get(ref, ref)


def claude_model_id(primary: str | None) -> str:
    """Model id for a Claude run. A config whose model_primary is already a
    claude model (claude://… or claude-…) wins; a Gemini id maps to the default."""
    mapped = map_model(primary)
    return mapped if mapped.startswith("claude-") else CLAUDE_DEFAULT
