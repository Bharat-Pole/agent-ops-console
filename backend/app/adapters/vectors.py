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


@dataclass
class FusedHit:
    """A chunk after fusion. `retrieval_score` keeps the original searcher's
    score so traces stay meaningful; `fused_score` decides ORDER only."""
    chunk: KbChunk
    retrieval_score: float
    fused_score: float
    found_by: tuple[str, ...]


# How many candidates each searcher contributes per requested chunk. Fusion and
# the diversity pass both need more material than top_k to work with: at 1x,
# every candidate is already a winner and there is nothing left to reorder.
CANDIDATE_MULTIPLIER = 4

# Standard RRF damping. Large enough that a top-1 hit does not overwhelm the
# sum, small enough that rank still dominates.
RRF_DAMPING = 60


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


def fuse(ranked: dict[str, list[ChunkHit]], damping: int = RRF_DAMPING) -> list[FusedHit]:
    """Reciprocal-rank fusion of several ranked candidate lists.

    Cosine similarity and keyword overlap are on incompatible scales — 0.4
    cosine and 0.4 term-overlap say nothing comparable — so their scores can be
    neither compared nor averaged. RRF ranks by POSITION instead, which needs no
    calibration between searchers. Contributions SUM, so a chunk both searchers
    rank highly outranks one that only a single searcher likes.

    This replaces a concatenate-and-truncate merge that silently discarded the
    keyword list whenever vector search returned a full page.
    """
    fused: dict[uuid.UUID, FusedHit] = {}
    for name, hits in ranked.items():
        for rank, hit in enumerate(hits):
            contribution = 1.0 / (damping + rank + 1)
            existing = fused.get(hit.chunk.id)
            if existing is None:
                fused[hit.chunk.id] = FusedHit(
                    chunk=hit.chunk, retrieval_score=hit.score,
                    fused_score=contribution, found_by=(name,))
            else:
                existing.fused_score += contribution
                existing.found_by = (*existing.found_by, name)
                # keep the strongest native score seen for this chunk
                existing.retrieval_score = max(existing.retrieval_score, hit.score)
    return sorted(fused.values(), key=lambda h: h.fused_score, reverse=True)


def diversify(hits: list[FusedHit], top_k: int) -> list[FusedHit]:
    """Take top_k, but reserve the first slot of each source before filling.

    Straight rank truncation lets one verbose or lexically-close document take
    every slot, so a question spanning two documents only ever sees one of them.
    Reserving one slot per represented source bounds that: at most
    (sources - 1) slots are diverted, and only when the other sources actually
    produced a candidate. With a single source the result is unchanged.

    Sources here are the ones deliberately attached to the pipeline, so
    representation is a reasonable default; below-threshold chunks were already
    dropped by vector_search and never reach this point.
    """
    if top_k <= 0 or not hits:
        return []
    selected: list[FusedHit] = []
    claimed: set[uuid.UUID] = set()
    for hit in hits:                      # pass 1 — best chunk of each source
        if len(selected) >= top_k:
            break
        if hit.chunk.source_id in claimed:
            continue
        claimed.add(hit.chunk.source_id)
        selected.append(hit)
    chosen = {h.chunk.id for h in selected}
    for hit in hits:                      # pass 2 — fill the rest by fused rank
        if len(selected) >= top_k:
            break
        if hit.chunk.id not in chosen:
            selected.append(hit)
    selected.sort(key=lambda h: h.fused_score, reverse=True)
    return selected
