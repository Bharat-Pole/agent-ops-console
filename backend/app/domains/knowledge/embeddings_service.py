"""
Embeddings service — two real providers, no simulation:

  - "openai"          -> OpenAI text-embedding-3-small (1536-dim), needs OPENAI_API_KEY + credits.
  - "local_bge_small" -> BAAI/bge-small-en-v1.5 via sentence-transformers (384-dim), runs
                         entirely on-CPU in this process, no API key, no network calls
                         once the model weights are cached locally.

A source picks one provider at ingest time (`knowledge_sources.embedding_provider`) and
every chunk of that source is embedded with it. The two vector spaces are NOT comparable
(different dimensions, different models) — chunks from sources with different providers
must never be searched together in one query. That constraint is enforced by callers of
this module (see the /retrieve route), not here.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from openai import AsyncOpenAI

from app.env import env

LOCAL_MODEL_NAME = "BAAI/bge-small-en-v1.5"
# BGE v1.5's documented usage convention: prepend this instruction to QUERY text only.
# Passages/documents being indexed are embedded with no prefix. Skipping this on the
# query side measurably hurts retrieval quality for BGE models.
_LOCAL_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

EMBEDDING_DIMENSIONS: dict[str, int] = {
    "openai": 1536,
    "local_bge_small": 384,
}

_openai_client: Optional[AsyncOpenAI] = None
_local_model = None  # lazy-loaded sentence_transformers.SentenceTransformer singleton


def is_embeddings_configured(provider: str = "openai") -> bool:
    if provider == "local_bge_small":
        return is_local_embeddings_available()
    return bool(env.OPENAI_API_KEY)


def is_local_embeddings_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


# ── OpenAI ───────────────────────────────────────────────────────────────────

def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if not env.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured.")
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=env.OPENAI_API_KEY)
    return _openai_client


async def _embed_batch_openai(texts: list[str]) -> list[list[float]]:
    res = await _get_openai_client().embeddings.create(model=env.OPENAI_EMBEDDING_MODEL, input=texts)
    # Defensive re-sort — the API doesn't guarantee response order matches input order.
    ordered = sorted(res.data, key=lambda d: d.index)
    return [d.embedding for d in ordered]


# ── Local (BGE via sentence-transformers) ───────────────────────────────────

def _get_local_model():
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is required for the local embedding provider. "
                "Run: pip install sentence-transformers"
            )
        _local_model = SentenceTransformer(LOCAL_MODEL_NAME)
    return _local_model


def _encode_local_sync(texts: list[str], is_query: bool) -> list[list[float]]:
    model = _get_local_model()
    inputs = [f"{_LOCAL_QUERY_PREFIX}{t}" for t in texts] if is_query else texts
    vectors = model.encode(inputs, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


async def _embed_batch_local(texts: list[str], is_query: bool = False) -> list[list[float]]:
    # sentence-transformers is CPU-bound and synchronous — offload so it doesn't block
    # the event loop, same pattern used for the BigQuery sync client elsewhere.
    return await asyncio.to_thread(_encode_local_sync, texts, is_query)


# ── Dispatch ─────────────────────────────────────────────────────────────────

async def embed_batch(texts: list[str], provider: str = "openai", is_query: bool = False) -> list[list[float]]:
    if provider == "local_bge_small":
        return await _embed_batch_local(texts, is_query=is_query)
    if provider == "openai":
        return await _embed_batch_openai(texts)
    raise ValueError(f"Unknown embedding provider: {provider}")


async def embed_text(text: str, provider: str = "openai", is_query: bool = False) -> list[float]:
    return (await embed_batch([text], provider=provider, is_query=is_query))[0]
