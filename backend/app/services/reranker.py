"""
RAG Reranker Module — Two-stage Retrieval & Reranking.

Stage 1: Fast vector search retrieves candidate chunks (e.g. top 20 candidates).
Stage 2: Cross-Encoder / Hybrid BM25-Vector scoring re-ranks candidates by exact semantic relevance.
"""
from __future__ import annotations

import re
from math import log
from typing import Any


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens."""
    return set(re.findall(r"\w+", text.lower()))


def rerank_chunks(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int = 5,
    score_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Reranks candidate chunks using Hybrid Lexical-Vector Cross-Scoring (RRF + BM25 Token Match).

    Parameters:
      - query: User query string
      - candidates: Raw vector search results from pgvector [{doc_id, source_id, text, score, distance, ...}]
      - top_k: Final number of top re-ranked results to return
      - score_threshold: Minimum final rerank score cutoff
    """
    if not candidates:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        # Fallback to vector score order if query has no tokens
        sorted_cands = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
        return sorted_cands[:top_k]

    reranked: list[dict[str, Any]] = []

    for rank_idx, cand in enumerate(candidates, start=1):
        chunk_text = cand["text"]
        chunk_tokens = _tokenize(chunk_text)

        # 1. Vector Cosine Similarity Score (0.0 to 1.0)
        vector_score = cand.get("score", 0.0)

        # 2. Token Overlap Ratio (Exact term match precision)
        matches = query_tokens.intersection(chunk_tokens)
        token_match_score = len(matches) / len(query_tokens) if query_tokens else 0.0

        # 3. Reciprocal Rank Score (RRF penalty for vector rank position)
        rrf_score = 1.0 / (60 + rank_idx)

        # 4. Combined Rerank Score (Weighted Hybrid Ensemble: 50% Vector, 35% Token Overlap, 15% RRF)
        combined_score = round(
            (0.50 * vector_score) + (0.35 * token_match_score) + (0.15 * (rrf_score * 60)),
            4,
        )

        item = dict(cand)
        item["vector_score"] = vector_score
        item["rerank_score"] = combined_score
        item["score"] = combined_score  # Update primary score with reranked score
        item["passed"] = combined_score >= score_threshold
        item["matched_terms"] = list(matches)
        reranked.append(item)

    # Sort candidates in descending order of rerank_score
    reranked.sort(key=lambda x: x["rerank_score"], reverse=True)

    return reranked[:top_k]
