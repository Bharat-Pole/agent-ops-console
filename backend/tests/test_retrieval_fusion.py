"""Retrieval fusion and source diversity.

These cover the two defects behind "questions referenced from different
documents don't retrieve properly":

1. the old merge concatenated vector+keyword then truncated to top_k, so the
   keyword list was discarded entirely whenever vector search returned a full
   page — the blend was a no-op in exactly the common case;
2. nothing reserved retrieval slots per source, so one verbose or lexically
   closer document could take every slot and a second document contributing
   half the answer was never seen.

The scoring scales are deliberately incompatible (cosine vs term overlap),
which is why fusion ranks by position rather than by score.
"""
from __future__ import annotations

import uuid

from app.adapters import vectors
from app.adapters.vectors import ChunkHit, diversify, fuse


class FakeChunk:
    """Stands in for KbChunk — fusion only touches id and source_id."""

    def __init__(self, source: uuid.UUID, label: str):
        self.id = uuid.uuid4()
        self.source_id = source
        self.text = label
        self.meta = {"location": label}


def _hits(chunks, scores) -> list[ChunkHit]:
    return [ChunkHit(chunk=c, score=s) for c, s in zip(chunks, scores)]


# ---- fusion ------------------------------------------------------------------

def test_keyword_hits_survive_a_full_vector_page():
    """The regression: a full vector page used to discard the keyword list."""
    src = uuid.uuid4()
    vec = [FakeChunk(src, f"v{i}") for i in range(5)]
    kw_only = FakeChunk(src, "keyword-exclusive")

    fused = fuse({
        "vector": _hits(vec, [0.9, 0.8, 0.7, 0.6, 0.5]),
        "keyword": _hits([kw_only], [1.0]),
    })
    ids = [h.chunk.id for h in fused]
    assert kw_only.id in ids, "a top keyword hit must reach the fused pool"
    # ranked first among its list, so it outranks the tail of the vector list
    assert ids.index(kw_only.id) < ids.index(vec[4].id)


def test_agreement_between_searchers_outranks_a_single_strong_list():
    """A chunk both searchers like beats one only the vector searcher likes."""
    src = uuid.uuid4()
    both = FakeChunk(src, "agreed")
    vector_favourite = FakeChunk(src, "vector-only")

    fused = fuse({
        "vector": _hits([vector_favourite, both], [0.95, 0.55]),
        "keyword": _hits([both], [0.9]),
    })
    assert fused[0].chunk.id == both.id
    assert fused[0].found_by == ("vector", "keyword")


def test_fusion_keeps_the_strongest_native_score_for_the_trace():
    src = uuid.uuid4()
    c = FakeChunk(src, "c")
    fused = fuse({"vector": _hits([c], [0.42]), "keyword": _hits([c], [0.80])})
    assert fused[0].retrieval_score == 0.80
    assert fused[0].fused_score > 1.0 / (vectors.RRF_DAMPING + 1)


def test_incompatible_scales_do_not_decide_order():
    """Keyword 1.0 must not beat cosine 0.9 merely by being a bigger number."""
    src = uuid.uuid4()
    strong_vector = FakeChunk(src, "cosine-0.9")
    weak_keyword = FakeChunk(src, "overlap-1.0")
    fused = fuse({
        "vector": _hits([strong_vector], [0.9]),
        "keyword": _hits([weak_keyword, strong_vector], [1.0, 0.2]),
    })
    # strong_vector is rank 0 in one list and rank 1 in the other; weak_keyword
    # is rank 0 in one list only. Summed contributions decide, not raw scores.
    assert fused[0].chunk.id == strong_vector.id


def test_empty_lists_fuse_to_nothing():
    assert fuse({"vector": [], "keyword": []}) == []


# ---- diversity ---------------------------------------------------------------

def test_a_second_document_is_represented_even_when_outranked():
    """The reported symptom: doc B holds part of the answer but never appears."""
    a, b = uuid.uuid4(), uuid.uuid4()
    doc_a = [FakeChunk(a, f"a{i}") for i in range(5)]
    doc_b = FakeChunk(b, "b0")

    fused = fuse({
        "vector": _hits([*doc_a, doc_b], [0.9, 0.88, 0.86, 0.84, 0.82, 0.60]),
        "keyword": [],
    })
    selected = diversify(fused, top_k=5)

    assert len(selected) == 5
    sources = {h.chunk.source_id for h in selected}
    assert sources == {a, b}, "both documents must be represented"
    assert sum(1 for h in selected if h.chunk.source_id == a) == 4


def test_single_source_behaviour_is_unchanged():
    """No regression for the single-document case that already worked."""
    src = uuid.uuid4()
    chunks = [FakeChunk(src, f"c{i}") for i in range(8)]
    fused = fuse({"vector": _hits(chunks, [0.9 - i * 0.05 for i in range(8)]), "keyword": []})
    selected = diversify(fused, top_k=5)
    assert [h.chunk.id for h in selected] == [c.id for c in chunks[:5]]


def test_reservation_never_exceeds_top_k():
    """More sources than slots: take the best sources, never overflow."""
    sources = [uuid.uuid4() for _ in range(8)]
    chunks = [FakeChunk(s, f"s{i}") for i, s in enumerate(sources)]
    fused = fuse({"vector": _hits(chunks, [0.9 - i * 0.01 for i in range(8)]), "keyword": []})
    selected = diversify(fused, top_k=3)
    assert len(selected) == 3
    assert len({h.chunk.source_id for h in selected}) == 3


def test_sources_with_no_candidates_divert_nothing():
    """A source that produced no above-threshold chunk costs no slot."""
    a, b = uuid.uuid4(), uuid.uuid4()
    doc_a = [FakeChunk(a, f"a{i}") for i in range(4)]
    fused = fuse({"vector": _hits(doc_a, [0.9, 0.8, 0.7, 0.6]), "keyword": []})
    selected = diversify(fused, top_k=4)
    assert len(selected) == 4
    assert all(h.chunk.source_id == a for h in selected)
    assert b not in {h.chunk.source_id for h in selected}


def test_result_is_presented_in_fused_rank_order():
    a, b = uuid.uuid4(), uuid.uuid4()
    top_a = FakeChunk(a, "a-top")
    mid_a = FakeChunk(a, "a-mid")
    low_b = FakeChunk(b, "b-low")
    fused = fuse({"vector": _hits([top_a, mid_a, low_b], [0.9, 0.7, 0.3]), "keyword": []})
    selected = diversify(fused, top_k=3)
    scores = [h.fused_score for h in selected]
    assert scores == sorted(scores, reverse=True)


def test_diversify_handles_degenerate_inputs():
    assert diversify([], top_k=5) == []
    src = uuid.uuid4()
    fused = fuse({"vector": _hits([FakeChunk(src, "c")], [0.5]), "keyword": []})
    assert diversify(fused, top_k=0) == []
