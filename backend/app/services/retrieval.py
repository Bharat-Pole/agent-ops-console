from typing import Any

from app.repositories import knowledge_chunks_repo
from app.services.embeddings import embed_text, is_embeddings_configured


def _parse_source_ids(refs: list[str]) -> list[str]:
    return [r.replace("kb://", "", 1).split("@")[0] for r in refs]


# Real cosine-similarity retrieval over the embedded seed snippets, scoped to
# the agent's knowledge_source_refs. Replaces the old client-side fake hash
# scorer, which re-scored differently per message even for semantically
# identical follow-ups.
async def retrieve_for_agent(agent: dict[str, Any], query: str, top_k: int, score_threshold: float) -> list[dict[str, Any]]:
    if not is_embeddings_configured():
        return []
    source_ids = _parse_source_ids(agent["config"]["data"]["knowledge_source_refs"]["value"])
    if not source_ids:
        return []

    query_embedding = await embed_text(query)
    rows = await knowledge_chunks_repo.search_by_source_ids(query_embedding, source_ids, max(top_k, 1))

    results = []
    for r in rows:
        score = round(1 - r["distance"], 4)
        results.append(
            {
                "doc_id": r["doc_id"],
                "source_id": r["source_id"],
                "text": r["text"],
                "score": score,
                "passed": score >= score_threshold,
            }
        )
    return results
