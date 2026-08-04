from typing import Optional

from openai import AsyncOpenAI

from app.env import env

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_client: Optional[AsyncOpenAI] = None


def is_groq_configured() -> bool:
    return bool(env.GROQ_API_KEY)


def _get_client() -> AsyncOpenAI:
    global _client
    if not env.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured.")
    if _client is None:
        _client = AsyncOpenAI(api_key=env.GROQ_API_KEY, base_url=GROQ_BASE_URL)
    return _client


async def generate_text(prompt: str, max_tokens: int = 512) -> str:
    response = await _get_client().chat.completions.create(
        model=env.GROQ_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""
