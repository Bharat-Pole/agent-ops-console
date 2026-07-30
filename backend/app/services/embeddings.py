from typing import Optional

from openai import AsyncOpenAI

from app.env import env

_client: Optional[AsyncOpenAI] = None


def is_embeddings_configured() -> bool:
    return bool(env.OPENAI_API_KEY)


def _get_client() -> AsyncOpenAI:
    global _client
    if not env.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured.")
    if _client is None:
        _client = AsyncOpenAI(api_key=env.OPENAI_API_KEY)
    return _client


async def embed_batch(texts: list[str]) -> list[list[float]]:
    res = await _get_client().embeddings.create(model=env.OPENAI_EMBEDDING_MODEL, input=texts)
    # Defensive re-sort — the API doesn't guarantee response order matches input order.
    ordered = sorted(res.data, key=lambda d: d.index)
    return [d.embedding for d in ordered]


async def embed_text(text: str) -> list[float]:
    return (await embed_batch([text]))[0]
