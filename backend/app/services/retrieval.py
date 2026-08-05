from typing import Any

from app.repositories import knowledge_chunks_repo, knowledge_sources_repo
from app.services.embeddings import embed_text, is_embeddings_configured
from app.services.reranker import rerank_chunks


def _parse_source_ids(refs: list[str]) -> list[str]:
    return [r.replace("kb://", "", 1).split("@")[0] for r in refs]


async def retrieve_for_sources(
    source_ids: list[str],
    query: str,
    top_k: int,
    score_threshold: float,
    rerank_enabled: bool = True,
) -> list[dict[str, Any]]:
    """
    Provider-aware retrieval against an explicit set of source_ids — always resolves
    each source's embedding_provider and threads it through both the query embedding
    and the pgvector search, unlike the old retrieve_for_agent() which silently
    defaulted both to 'openai' regardless of what a source was actually embedded with.
    Also always passes is_query=True, since skipping the BGE query-prefix convention
    measurably hurts retrieval quality (see embeddings.py).
    """
    if not source_ids:
        return []

    providers = await knowledge_sources_repo.get_embedding_providers(source_ids)
    distinct = set(providers.values())
    if len(distinct) > 1:
        raise ValueError(f"Sources use different embedding providers ({sorted(distinct)}) — cannot search together.")
    provider = next(iter(distinct), "openai")

    if not is_embeddings_configured(provider):
        return []

    fetch_k = max(top_k * 4, 20) if rerank_enabled else top_k
    query_embedding = await embed_text(query, provider=provider, is_query=True)
    rows = await knowledge_chunks_repo.search_by_source_ids(query_embedding, source_ids, fetch_k, provider=provider)

    candidates = [
        {
            "doc_id": r["doc_id"],
            "source_id": r["source_id"],
            "chunk_index": r["chunk_index"],
            "text": r["text"],
            "score": round(1 - r["distance"], 4),
            "distance": r["distance"],
            "passed": round(1 - r["distance"], 4) >= score_threshold,
        }
        for r in rows
    ]

    if rerank_enabled:
        return rerank_chunks(query, candidates, top_k=top_k, score_threshold=score_threshold)
    else:
        filtered = [c for c in candidates if c["passed"]]
        return filtered[:top_k]


# Deprecated — kept as a thin wrapper for one release in case anything else still
# references it directly. New code (the tool-use loop in claude_service.py) calls
# retrieve_for_sources() with a single source_id per call, so the provider-mismatch
# bug this used to have can no longer occur on that path.
async def retrieve_for_agent(
    agent: dict[str, Any],
    query: str,
    top_k: int,
    score_threshold: float,
    rerank_enabled: bool = True,
) -> list[dict[str, Any]]:
    data_cfg = agent.get("config", {}).get("data", {})
    if data_cfg.get("rag_enabled", {}).get("value") is False:
        return []

    source_ids = _parse_source_ids(data_cfg.get("knowledge_source_refs", {}).get("value", []))
    if not source_ids:
        return []

    agent_rerank_toggle = data_cfg.get("rerank_enabled", {}).get("value")
    should_rerank = agent_rerank_toggle if agent_rerank_toggle is not None else rerank_enabled

    return await retrieve_for_sources(source_ids, query, top_k, score_threshold, should_rerank)


