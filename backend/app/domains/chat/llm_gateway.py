"""The ONLY place that decides which LLM provider actually answers a real
call. Every feature that needs a real completion (agent chat/RAG, eval
judging, prompt generation, source suggestions) goes through here instead of
calling Anthropic directly, so one fallback policy governs the whole app:
try Anthropic if configured; if it's unconfigured OR the call itself fails
for any reason (including exhausted credits), fall back to Groq's free tier
automatically. Raise the real combined error only if neither is usable."""

from typing import Any, Optional

from app.env import env
from app.domains.chat import claude_service, groq_service


def is_llm_configured() -> bool:
    return claude_service.is_claude_configured() or groq_service.is_groq_configured()


async def chat_with_agent(
    agent: dict[str, Any],
    message: str,
    history: list[dict[str, Any]],
    sys_body: Optional[str],
    cite_body: Optional[str],
) -> dict[str, Any]:
    if claude_service.is_claude_configured():
        try:
            return await claude_service.chat_with_agent(agent, message, history, sys_body, cite_body)
        except Exception as anthropic_err:
            if not groq_service.is_groq_configured():
                raise
            try:
                return await groq_service.chat_with_agent(agent, message, history, sys_body, cite_body)
            except Exception as groq_err:
                raise RuntimeError(
                    f"Anthropic failed ({anthropic_err}); Groq fallback also failed ({groq_err})."
                ) from groq_err
    if groq_service.is_groq_configured():
        return await groq_service.chat_with_agent(agent, message, history, sys_body, cite_body)
    raise RuntimeError("Neither ANTHROPIC_API_KEY nor GROQ_API_KEY is configured.")


async def _complete_anthropic(system: str, user: str, max_tokens: int, model: str) -> dict[str, Any]:
    response = await claude_service._get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text_block = next((b for b in response.content if b.type == "text"), None)
    return {
        "text": text_block.text if text_block else "",
        "model": model,
        "tokens_in": response.usage.input_tokens,
        "tokens_out": response.usage.output_tokens,
    }


async def _complete_groq(system: str, user: str, max_tokens: int) -> dict[str, Any]:
    response = await groq_service._get_client().chat.completions.create(
        model=env.GROQ_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    usage = response.usage
    return {
        "text": response.choices[0].message.content or "",
        "model": env.GROQ_MODEL,
        "tokens_in": usage.prompt_tokens if usage else 0,
        "tokens_out": usage.completion_tokens if usage else 0,
    }


async def complete(
    system: str, user: str, max_tokens: int = 800, anthropic_model: Optional[str] = None
) -> dict[str, Any]:
    """Returns {text, model, tokens_in, tokens_out} — the real model/tokens
    that actually answered, whichever provider it was. anthropic_model lets
    cheap-task callers (judging, ranking) request Haiku-tier instead of the
    default standardized-tier model."""
    model = anthropic_model or env.ANTHROPIC_MODEL_STANDARDIZED
    if claude_service.is_claude_configured():
        try:
            return await _complete_anthropic(system, user, max_tokens, model)
        except Exception as anthropic_err:
            if not groq_service.is_groq_configured():
                raise
            try:
                return await _complete_groq(system, user, max_tokens)
            except Exception as groq_err:
                raise RuntimeError(
                    f"Anthropic failed ({anthropic_err}); Groq fallback also failed ({groq_err})."
                ) from groq_err
    if groq_service.is_groq_configured():
        return await _complete_groq(system, user, max_tokens)
    raise RuntimeError("Neither ANTHROPIC_API_KEY nor GROQ_API_KEY is configured.")


async def complete_text(system: str, user: str, max_tokens: int = 800, anthropic_model: Optional[str] = None) -> str:
    result = await complete(system, user, max_tokens, anthropic_model)
    return result["text"]
