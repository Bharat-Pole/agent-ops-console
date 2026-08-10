"""Knowledge Base + RAG endpoints (Decision 3.2: file upload only in v1).
Retrieval preview is honest about its mode: hybrid when embeddings exist and a
provider is configured; keyword-only (labeled) otherwise.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters import files as file_store
from ..adapters import vectors
from ..adapters.models import ModelCallError, ModelUnavailable, get_model_adapter
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..config import settings
from ..db import get_db
from ..models import KbChunk, KnowledgeSource, RagPipeline, Role, User
from . import kb

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
rag_router = APIRouter(prefix="/api/rag", tags=["rag"])

_EDIT_ROLES = (Role.ai_engineer, Role.agent_creator, Role.platform_admin)
_ALLOWED_EXT = (".pdf", ".md", ".txt")


def _source_payload(s: KnowledgeSource) -> dict:
    return {
        "id": str(s.id), "name": s.name, "filename": s.filename, "mime": s.mime,
        "sensitivity": s.sensitivity, "status": s.status, "bytes": s.bytes,
        "chunk_count": s.chunk_count, "embedded": s.embedded,
        "retrieval_mode": "vector+keyword" if s.embedded else "keyword_only (no embedding provider at ingest)",
        "error": s.error, "created_at": s.created_at.isoformat(),
    }


@router.get("")
def list_sources(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    return [_source_payload(s) for s in db.scalars(
        select(KnowledgeSource).order_by(KnowledgeSource.created_at.desc())).all()]


@router.post("/upload", status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    name: str = Form(...),
    sensitivity: str = Form("internal"),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(120),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    filename = file.filename or "upload.txt"
    if not filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(status_code=422, detail=f"only {', '.join(_ALLOWED_EXT)} are supported in v1")
    if sensitivity not in ("public", "internal", "confidential", "restricted"):
        raise HTTPException(status_code=422, detail="invalid sensitivity")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="empty file")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="file exceeds the 20MB v1 limit")

    key = file_store.save_bytes(data, filename)
    source = KnowledgeSource(
        name=name, filename=filename, mime=file.content_type or "text/plain",
        sensitivity=sensitivity, file_path=key, bytes=len(data), owner_id=user.id,
    )
    db.add(source)
    db.flush()
    kb.ingest(db, source, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    audit(db, user, "knowledge_uploaded", "knowledge", str(source.id), {
        "filename": filename, "bytes": len(data), "status": source.status,
        "chunks": source.chunk_count, "embedded": source.embedded,
    })
    db.commit()
    return _source_payload(source)


@router.get("/{source_id}")
def get_source(source_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    source = db.get(KnowledgeSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    chunks = db.scalars(
        select(KbChunk).where(KbChunk.source_id == source.id).order_by(KbChunk.ord).limit(5)
    ).all()
    out = _source_payload(source)
    out["chunk_preview"] = [
        {"ord": c.ord, "text": c.text[:400], "meta": c.meta, "has_embedding": c.embedding is not None}
        for c in chunks
    ]
    return out


@router.post("/{source_id}/reingest")
def reingest_source(
    source_id: uuid.UUID,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    source = db.get(KnowledgeSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    kb.ingest(db, source, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    audit(db, user, "knowledge_reingested", "knowledge", str(source.id),
          {"status": source.status, "chunks": source.chunk_count, "embedded": source.embedded})
    db.commit()
    return _source_payload(source)


# ---- RAG pipelines ----------------------------------------------------------

def _pipeline_payload(p: RagPipeline) -> dict:
    return {
        "id": str(p.id), "name": p.name, "source_ids": p.source_ids,
        "chunk_size": p.chunk_size, "chunk_overlap": p.chunk_overlap,
        "embedding_model_ref": p.embedding_model_ref, "top_k": p.top_k,
        "score_threshold": p.score_threshold, "hybrid_alpha": p.hybrid_alpha,
        "status": p.status, "created_at": p.created_at.isoformat(),
    }


class PipelineBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    source_ids: list[uuid.UUID]
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    hybrid_alpha: float = Field(default=0.7, ge=0.0, le=1.0)


@rag_router.get("")
def list_pipelines(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    return [_pipeline_payload(p) for p in db.scalars(select(RagPipeline).order_by(RagPipeline.name)).all()]


@rag_router.post("", status_code=201)
def create_pipeline(
    body: PipelineBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*_EDIT_ROLES)),
):
    if db.scalars(select(RagPipeline).where(RagPipeline.name == body.name)).first():
        raise HTTPException(status_code=409, detail="pipeline name exists")
    for sid in body.source_ids:
        if db.get(KnowledgeSource, sid) is None:
            raise HTTPException(status_code=422, detail=f"unknown knowledge source {sid}")
    pipeline = RagPipeline(
        name=body.name, source_ids=[str(s) for s in body.source_ids],
        top_k=body.top_k, score_threshold=body.score_threshold,
        hybrid_alpha=body.hybrid_alpha, created_by=user.id,
    )
    db.add(pipeline)
    db.flush()
    audit(db, user, "rag_pipeline_created", "rag", str(pipeline.id), {"sources": len(body.source_ids)})
    db.commit()
    return _pipeline_payload(pipeline)


class PreviewBody(BaseModel):
    query: str = Field(min_length=2)


@rag_router.post("/{pipeline_id}/preview")
def preview_retrieval(
    pipeline_id: uuid.UUID,
    body: PreviewBody,
    db: Session = Depends(get_db),
    _: User = Depends(current_user_dep),
):
    """Hybrid retrieval preview. score_threshold ENFORCED on the vector leg;
    the mode label tells the truth about what actually ran."""
    pipeline = db.get(RagPipeline, pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="pipeline not found")
    source_ids = [uuid.UUID(s) for s in pipeline.source_ids]

    adapter = get_model_adapter(db, settings.gemini_embedding_model)
    vector_hits: list[vectors.ChunkHit] = []
    mode_notes: list[str] = []
    if adapter is None:
        mode_notes.append("no embedding provider configured")
    else:
        try:
            qvec = adapter.embed([body.query])[0]
            vector_hits = vectors.vector_search(db, qvec, source_ids, pipeline.top_k, pipeline.score_threshold)
        except (ModelUnavailable, ModelCallError) as exc:
            mode_notes.append(f"embedding failed: {exc}")

    keyword_hits = vectors.keyword_search(db, body.query, source_ids, pipeline.top_k)

    # hybrid blend (alpha × vector + (1-alpha) × keyword), keyed by chunk id
    alpha = pipeline.hybrid_alpha if vector_hits else 0.0
    blended: dict[uuid.UUID, dict] = {}
    for h in vector_hits:
        blended[h.chunk.id] = {"chunk": h.chunk, "vector_score": h.score, "keyword_score": 0.0}
    for h in keyword_hits:
        entry = blended.setdefault(h.chunk.id, {"chunk": h.chunk, "vector_score": 0.0, "keyword_score": 0.0})
        entry["keyword_score"] = h.score
    rows = []
    sources = {str(s.id): s for s in db.scalars(
        select(KnowledgeSource).where(KnowledgeSource.id.in_(source_ids))).all()}
    for entry in blended.values():
        chunk: KbChunk = entry["chunk"]
        score = alpha * entry["vector_score"] + (1 - alpha) * entry["keyword_score"]
        src = sources.get(str(chunk.source_id))
        rows.append({
            "chunk_id": str(chunk.id), "source": src.name if src else "?",
            "location": (chunk.meta or {}).get("location"),
            "text": chunk.text[:400],
            "score": round(score, 4),
            "vector_score": round(entry["vector_score"], 4),
            "keyword_score": round(entry["keyword_score"], 4),
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    mode = "hybrid" if vector_hits else "keyword_only"
    return {
        "mode": mode,
        "mode_notes": mode_notes,  # honest about degradation
        "alpha": alpha,
        "results": rows[: pipeline.top_k],
    }
