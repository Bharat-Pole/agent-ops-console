"""
Recursive Character Text Splitter
Pure Python — no external dependencies.

Splits text by trying separators in priority order until chunks are small enough.
This produces semantically coherent chunks that respect paragraph and sentence
boundaries before falling back to character-level splits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Chunk:
    text: str
    chunk_index: int
    char_start: int
    char_end: int
    doc_id: str
    metadata: dict = field(default_factory=dict)


_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    Recursively split text using the best separator at each level.
    Falls back to the next separator when chunks are still too large.
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    for sep in _SEPARATORS:
        if sep == "":
            # Final fallback: hard character split
            return [
                text[i: i + chunk_size]
                for i in range(0, len(text), chunk_size - chunk_overlap)
                if text[i: i + chunk_size].strip()
            ]

        if sep not in text:
            continue

        parts = text.split(sep)
        chunks: list[str] = []
        current = ""

        for part in parts:
            candidate = current + (sep if current else "") + part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current.strip():
                    chunks.append(current)
                # If the part itself is too large, recurse
                if len(part) > chunk_size:
                    chunks.extend(_split_text(part, chunk_size, chunk_overlap))
                    current = ""
                else:
                    # Start fresh with overlap from end of previous chunk
                    overlap_start = max(0, len(current) - chunk_overlap)
                    current = current[overlap_start:] + sep + part if current else part

        if current.strip():
            chunks.append(current)

        return [c for c in chunks if c.strip()]

    return [text]


def chunk_text(
    text: str,
    doc_id: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> List[Chunk]:
    """
    Split text into Chunk objects with position metadata.

    Args:
        text:          Full plain text of the document.
        doc_id:        Logical document identifier (usually the source name/filename).
        chunk_size:    Max characters per chunk (~200 tokens for English).
        chunk_overlap: Characters to repeat between adjacent chunks to preserve context.

    Returns:
        Ordered list of Chunk objects.
    """
    raw_chunks = _split_text(text, chunk_size, chunk_overlap)
    result: List[Chunk] = []
    search_start = 0

    for idx, raw in enumerate(raw_chunks):
        start = text.find(raw[:50], search_start)
        if start == -1:
            start = search_start
        end = start + len(raw)
        result.append(
            Chunk(
                text=raw.strip(),
                chunk_index=idx,
                char_start=start,
                char_end=end,
                doc_id=doc_id,
                metadata={"char_start": start, "char_end": end},
            )
        )
        search_start = max(0, end - chunk_overlap)

    return result
