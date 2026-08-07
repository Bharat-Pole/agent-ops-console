"""KB ingestion (Pass 3): parse → chunk (ACTUALLY applied — carried lesson) →
embed via the model adapter when one is configured. No provider → chunks are
stored unembedded and the source is honestly marked keyword-only; nothing is
fabricated.
"""
from __future__ import annotations

import io

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..adapters import files as file_store
from ..adapters.models import ModelCallError, ModelUnavailable, get_model_adapter
from ..models import KbChunk, KnowledgeSource, utcnow


def extract_units(data: bytes, filename: str) -> list[tuple[str, str]]:
    """→ [(text, location_label)]. PDF = per page; MD/TXT = whole file."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        units: list[tuple[str, str]] = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                units.append((text, f"page {i}"))
        return units
    text = data.decode("utf-8", errors="replace").strip()
    return [(text, "document")] if text else []


def chunk_units(units: list[tuple[str, str]], size: int, overlap: int) -> list[tuple[str, dict]]:
    """Fixed-size + overlap chunking within each unit. → [(text, meta)]."""
    if size <= 0:
        raise ValueError("chunk size must be positive")
    overlap = min(overlap, size - 1) if size > 1 else 0
    out: list[tuple[str, dict]] = []
    for text, location in units:
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            piece = text[start:end].strip()
            if piece:
                out.append((piece, {"location": f"{location}, chars {start}-{end}"}))
            if end == len(text):
                break
            start = end - overlap
    return out


def ingest(db: Session, source: KnowledgeSource, chunk_size: int = 800, chunk_overlap: int = 120) -> None:
    """(Re)ingest a source: replaces its chunks. Chunks are drafts of derived
    data, not governed records — replacement is legitimate here."""
    source.status = "ingesting"
    db.flush()
    try:
        data = file_store.read_bytes(source.file_path)
        units = extract_units(data, source.filename)
        if not units:
            raise ValueError("no extractable text found in the file")
        chunks = chunk_units(units, chunk_size, chunk_overlap)
        if not chunks:
            raise ValueError("chunking produced no chunks")

        db.execute(delete(KbChunk).where(KbChunk.source_id == source.id))

        adapter = get_model_adapter()
        embeddings: list[list[float]] | None = None
        if adapter is not None:
            try:
                embeddings = adapter.embed([text for text, _ in chunks])
            except (ModelUnavailable, ModelCallError) as exc:
                embeddings = None
                source.error = f"embedding unavailable: {exc}"  # honest, non-fatal

        for i, (text, meta) in enumerate(chunks):
            db.add(KbChunk(
                source_id=source.id, ord=i, text=text, meta=meta,
                embedding=embeddings[i] if embeddings else None,
            ))
        source.chunk_count = len(chunks)
        source.embedded = embeddings is not None
        source.status = "ready"
        if embeddings is not None:
            source.error = None
    except Exception as exc:
        source.status = "failed"
        source.error = str(exc)[:500]
    db.flush()
