from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def count() -> int:
    pool = get_pool()
    row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM knowledge_chunks")
    return row["n"]


async def insert(chunk: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO knowledge_chunks
           (id, source_id, run_id, doc_id, chunk_index, text, embedding, metadata, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,$9)""",
        chunk["id"],
        chunk["source_id"],
        chunk.get("run_id"),
        chunk["doc_id"],
        chunk.get("chunk_index", 0),
        chunk["text"],
        to_vector_literal(chunk["embedding"]),
        chunk.get("metadata", {}),
        _now_iso(),
    )


async def insert_batch(chunks: list[dict[str, Any]]) -> None:
    """Bulk insert via a transaction — faster than N individual inserts."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for chunk in chunks:
                await conn.execute(
                    """INSERT INTO knowledge_chunks
                       (id, source_id, run_id, doc_id, chunk_index, text, embedding, metadata, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,$9)""",
                    chunk["id"],
                    chunk["source_id"],
                    chunk.get("run_id"),
                    chunk["doc_id"],
                    chunk.get("chunk_index", 0),
                    chunk["text"],
                    to_vector_literal(chunk["embedding"]),
                    chunk.get("metadata", {}),
                    _now_iso(),
                )


async def atomic_swap(
    source_id: str,
    new_run_id: str,
    new_chunks: list[dict[str, Any]],
    provider: str = "openai",
) -> int:
    """
    Insert new chunks and delete all OLD chunks for this source in a single
    transaction. Ensures agents always have a complete set of chunks — never
    a partial state. Returns the number of new chunks stored.

    `provider` picks which vector column the embedding is written into —
    "openai" -> embedding (1536-dim), "local_bge_small" -> embedding_local (384-dim).
    The other column is left NULL for these rows.
    """
    vector_col = "embedding_local" if provider == "local_bge_small" else "embedding"
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Delete old chunks (any run_id that isn't the new one)
            await conn.execute(
                "DELETE FROM knowledge_chunks WHERE source_id=$1 AND (run_id IS NULL OR run_id != $2)",
                source_id, new_run_id,
            )
            # 2. Insert all new chunks
            for chunk in new_chunks:
                await conn.execute(
                    f"""INSERT INTO knowledge_chunks
                       (id, source_id, run_id, doc_id, chunk_index, text, {vector_col}, metadata, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,$9)""",
                    chunk["id"],
                    source_id,
                    new_run_id,
                    chunk["doc_id"],
                    chunk.get("chunk_index", 0),
                    chunk["text"],
                    to_vector_literal(chunk["embedding"]),
                    chunk.get("metadata", {}),
                    _now_iso(),
                )
    return len(new_chunks)


async def get_preview(source_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return first N chunks for UI preview — no embeddings."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT id, doc_id, chunk_index, text, metadata, created_at
           FROM knowledge_chunks
           WHERE source_id=$1
           ORDER BY chunk_index ASC
           LIMIT $2""",
        source_id, limit,
    )
    return [dict(r) for r in rows]


async def search_by_source_ids(
    query_embedding: list[float],
    source_ids: list[str],
    limit: int,
    provider: str = "openai",
    document_domain: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Cosine similarity search scoped to a set of source IDs.
    The source_id = ANY(...) uses the B-tree index to scope the vector scan
    to only the relevant sources, not the full table.

    `provider` picks which vector column to search — callers must ensure all
    `source_ids` were embedded with this same provider (see /retrieve route),
    since a 1536-dim OpenAI vector and a 384-dim BGE vector are not comparable.

    `document_domain` — real per-document metadata filter (Blueprint 3.3
    "configure metadata filters"): when given, only searches chunks whose
    knowledge_documents row is tagged with this exact domain.
    """
    vector_col = "embedding_local" if provider == "local_bge_small" else "embedding"
    pool = get_pool()
    domain_clause = "AND doc_id IN (SELECT id FROM knowledge_documents WHERE domain = $4)" if document_domain else ""
    params: list[Any] = [to_vector_literal(query_embedding), source_ids, limit]
    if document_domain:
        params.append(document_domain)
    rows = await pool.fetch(
        f"""SELECT doc_id, source_id, text, chunk_index, metadata,
                  {vector_col} <=> $1::vector AS distance
           FROM knowledge_chunks
           WHERE source_id = ANY($2::text[]) AND {vector_col} IS NOT NULL
             AND doc_id NOT IN (SELECT id FROM knowledge_documents WHERE lifecycle = 'retired')
             {domain_clause}
           ORDER BY {vector_col} <=> $1::vector
           LIMIT $3""",
        *params,
    )
    return [dict(r) for r in rows]


async def delete_by_source(source_id: str) -> int:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM knowledge_chunks WHERE source_id=$1", source_id
    )
    return int(result.split()[-1])
