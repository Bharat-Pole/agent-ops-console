from datetime import datetime, timezone
from typing import Any

from app.db.connection import get_pool


def to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def count() -> int:
    pool = get_pool()
    row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM knowledge_chunks")
    return row["n"]


async def insert(chunk: dict[str, Any]) -> None:
    pool = get_pool()
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await pool.execute(
        "INSERT INTO knowledge_chunks (id, source_id, doc_id, text, embedding, created_at) VALUES ($1,$2,$3,$4,$5::vector,$6)",
        chunk["id"],
        chunk["source_id"],
        chunk["doc_id"],
        chunk["text"],
        to_vector_literal(chunk["embedding"]),
        created_at,
    )


async def search_by_source_ids(query_embedding: list[float], source_ids: list[str], limit: int) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT doc_id, source_id, text, embedding <=> $1::vector AS distance
           FROM knowledge_chunks WHERE source_id = ANY($2::text[])
           ORDER BY embedding <=> $1::vector LIMIT $3""",
        to_vector_literal(query_embedding),
        source_ids,
        limit,
    )
    return [dict(r) for r in rows]
