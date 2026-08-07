"""Model adapter seam (Pass 0: adapters at every external dependency).

Providers:
- gemini  — Google Gemini via google-genai (primary per the Blueprint docs)
- fake    — labeled test harness (Decision 10: fake-LLM exists ONLY as the
            explicit test/CI harness, never a silent fallback)
- none    — no provider; callers must take their honest no-LLM path

Selection: PLATFORM_LLM_PROVIDER = auto|gemini|fake|none. `auto` resolves to
gemini when a key is configured, else none. `fake` must be asked for by name —
and every result carries model_id, so a fake run is visible in the record.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import settings


class ModelUnavailable(Exception):
    """Provider not configured/reachable — callers take the no-LLM path."""


class ModelCallError(Exception):
    """The provider call itself failed (quota, network, server error)."""


@dataclass
class ModelResult:
    text: str
    model_id: str
    tokens_in: int = 0   # 0 = provider did not report usage
    tokens_out: int = 0


class ModelAdapter(Protocol):
    model_id: str

    def generate_json(self, system: str, user: str, temperature: float = 0.2) -> ModelResult:
        """Generate a JSON-object response (provider-enforced where supported)."""
        ...

    def generate(self, system: str, user: str, temperature: float = 0.2,
                 max_tokens: int | None = None) -> ModelResult:
        """Generate free text with usage metadata (engine LLM nodes)."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts. Raises ModelUnavailable/ModelCallError on failure."""
        ...


class GeminiAdapter:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self.model_id = model

    def generate_json(self, system: str, user: str, temperature: float = 0.2) -> ModelResult:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # dependency present in requirements; belt-and-braces
            raise ModelUnavailable(f"google-genai not installed: {exc}") from exc
        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model_id,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            text = response.text or ""
        except Exception as exc:  # SDK raises provider-specific exceptions
            raise ModelCallError(str(exc)) from exc
        if not text.strip():
            raise ModelCallError("empty response from model")
        return ModelResult(text=text, model_id=self.model_id)

    def generate(self, system: str, user: str, temperature: float = 0.2,
                 max_tokens: int | None = None) -> ModelResult:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ModelUnavailable(f"google-genai not installed: {exc}") from exc
        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model_id,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            text = response.text or ""
            usage = getattr(response, "usage_metadata", None)
            tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
            tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)
            thoughts = int(getattr(usage, "thoughts_token_count", 0) or 0)
            finishes = [str(getattr(c, "finish_reason", "")) for c in (response.candidates or [])]
        except Exception as exc:
            raise ModelCallError(str(exc)) from exc
        if not text.strip():
            # never a bare "empty response": the provider's finish reason is the
            # actionable fact (MAX_TOKENS, SAFETY, MALFORMED_FUNCTION_CALL, …)
            raise ModelCallError(
                f"model returned no text (finish_reason={finishes or 'unknown'}; "
                f"thinking_tokens={thoughts}, answer_tokens={tokens_out}, "
                f"max_output_tokens={max_tokens})"
            )
        return ModelResult(text=text, model_id=self.model_id,
                           tokens_in=tokens_in, tokens_out=tokens_out)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            from google import genai
        except ImportError as exc:
            raise ModelUnavailable(f"google-genai not installed: {exc}") from exc
        try:
            client = genai.Client(api_key=self._api_key)
            result = client.models.embed_content(
                model=settings.gemini_embedding_model, contents=texts,
            )
            return [list(e.values) for e in result.embeddings]
        except Exception as exc:
            raise ModelCallError(str(exc)) from exc


class FakeModelAdapter:
    """Explicit, labeled test harness. Tests inject the scripted responses;
    each call pops the next one. Never instantiated unless asked for by name."""

    model_id = "fake:scripted"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict] = []  # visible to tests: what was asked

    def generate_json(self, system: str, user: str, temperature: float = 0.2) -> ModelResult:
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        if not self.responses:
            raise ModelCallError("FakeModelAdapter has no scripted responses left")
        return ModelResult(text=self.responses.pop(0), model_id=self.model_id)

    def generate(self, system: str, user: str, temperature: float = 0.2,
                 max_tokens: int | None = None) -> ModelResult:
        self.calls.append({"system": system, "user": user, "temperature": temperature,
                           "max_tokens": max_tokens})
        if not self.responses:
            raise ModelCallError("FakeModelAdapter has no scripted responses left")
        text = self.responses.pop(0)
        # word counts as labeled pseudo-usage — deterministic for cost tests
        return ModelResult(text=text, model_id=self.model_id,
                           tokens_in=len((system + " " + user).split()),
                           tokens_out=len(text.split()))

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Deterministic pseudo-embeddings (token-hash buckets, L2-normalized).
        Labeled fake: same word overlap → similar vectors, which is exactly what
        retrieval tests need — never used outside the explicit harness."""
        import hashlib
        import math
        dims = 64
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * dims
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vec[h % dims] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


# Test seam: tests set this to a FakeModelAdapter; get_model_adapter returns it
# regardless of provider config. Cleared by the fixture that set it.
_override: ModelAdapter | None = None


def set_adapter_override(adapter: ModelAdapter | None) -> None:
    global _override
    _override = adapter


def get_model_adapter() -> ModelAdapter | None:
    """Resolve the configured adapter, or None → callers take the honest
    deterministic-only path (never a hidden fake)."""
    if _override is not None:
        return _override
    provider = settings.llm_provider
    if provider == "auto":
        provider = "gemini" if settings.gemini_api_key else "none"
    if provider == "gemini":
        if not settings.gemini_api_key:
            return None
        return GeminiAdapter(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if provider == "fake":
        # explicit opt-in only (CI); visibly labeled in every stored model_id
        return FakeModelAdapter(responses=[])
    return None
