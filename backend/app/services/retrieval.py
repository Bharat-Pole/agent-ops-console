from typing import Any

from app.repositories import knowledge_chunks_repo
from app.services.embeddings import embed_text, is_embeddings_configured
from app.services.reranker import rerank_chunks


def _parse_source_ids(refs: list[str]) -> list[str]:
    return [r.replace("kb://", "", 1).split("@")[0] for r in refs]


# Two-Stage RAG Retrieval with Feature Toggles:
#  - rag_enabled: toggle RAG on/off
#  - rerank_enabled: toggle 2-stage hybrid reranker on/off
#  - top_k: number of chunks
#  - score_threshold: minimum similarity cutoff
async def retrieve_for_agent(
    agent: dict[str, Any],
    query: str,
    top_k: int,
    score_threshold: float,
    rerank_enabled: bool = True,
) -> list[dict[str, Any]]:
    if not is_embeddings_configured():
        return []
    
    # Check if agent has rag_enabled toggle in config
    data_cfg = agent.get("config", {}).get("data", {})
    if data_cfg.get("rag_enabled", {}).get("value") is False:
        return []

    source_ids = _parse_source_ids(data_cfg.get("knowledge_source_refs", {}).get("value", []))
    if not source_ids:
        return []

    # Check if rerank_enabled is configured on agent or passed as override
    agent_rerank_toggle = data_cfg.get("rerank_enabled", {}).get("value")
    should_rerank = agent_rerank_toggle if agent_rerank_toggle is not None else rerank_enabled

    fetch_k = max(top_k * 4, 20) if should_rerank else top_k
    query_embedding = await embed_text(query)
    rows = await knowledge_chunks_repo.search_by_source_ids(query_embedding, source_ids, fetch_k)

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

    if should_rerank:
        return rerank_chunks(query, candidates, top_k=top_k, score_threshold=score_threshold)
    else:
        # Standard vector-only ranking without 2-stage cross-scoring
        filtered = [c for c in candidates if c["passed"]]
        return filtered[:top_k]


