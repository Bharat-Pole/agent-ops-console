"""Vector search adapter (Pass 0 seam).

v1 implementation: embeddings stored as JSON float lists on kb_chunks and
searched with EXACT brute-force cosine in Python — correct on both Postgres
and SQLite at v1 scale. The pgvector-native column + ANN index (and later
Vertex Vector Search) slot in behind this same interface; recorded deviation,
not a behavior change (brute-force is exact, ANN is the approximation).
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KbChunk


@dataclass
class ChunkHit:
    chunk: KbChunk
    score: float  # cosine similarity in [-1, 1]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def vector_search(
    db: Session,
    query_vec: list[float],
    source_ids: list[uuid.UUID],
    top_k: int,
    score_threshold: float,
) -> list[ChunkHit]:
    """Exact cosine search over embedded chunks of the given sources.
    score_threshold is ENFORCED here — below-threshold chunks never surface."""
    stmt = select(KbChunk).where(KbChunk.source_id.in_(source_ids), KbChunk.embedding.is_not(None))
    hits = [
        ChunkHit(chunk=c, score=cosine(query_vec, c.embedding or []))
        for c in db.scalars(stmt).all()
    ]
    hits = [h for h in hits if h.score >= score_threshold]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


def keyword_search(
    db: Session,
    query: str,
    source_ids: list[uuid.UUID],
    top_k: int,
) -> list[ChunkHit]:
    """Keyword fallback/blend: token-overlap scoring in Python (portable).
    Postgres FTS is the native upgrade behind this same call."""
    terms = {t for t in query.lower().split() if len(t) >= 3}
    if not terms:
        return []
    stmt = select(KbChunk).where(KbChunk.source_id.in_(source_ids))
    hits: list[ChunkHit] = []
    for c in db.scalars(stmt).all():
        text = c.text.lower()
        matched = sum(1 for t in terms if t in text)
        if matched:
            hits.append(ChunkHit(chunk=c, score=matched / len(terms)))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
