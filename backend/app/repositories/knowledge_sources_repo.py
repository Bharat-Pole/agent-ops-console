from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool

_COLS_NO_BLOB = (
    "id, name, source_type, mime_type, uri, status, sensitivity, ingestion_mode, "
    "chunk_count, size_bytes, error_msg, domain, owner, tags, valid_until, lifecycle, "
    "last_queried_at, chunk_size, chunk_overlap, connector_config_masked, embedding_provider, "
    "used_by_json, created_at, updated_at, "
    "CASE WHEN raw_text IS NOT NULL THEN TRUE ELSE FALSE END AS has_raw_text"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row_to_source(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "source_type": row["source_type"],
        "mime_type": row["mime_type"],
        "uri": row["uri"],
        "status": row["status"],
        "sensitivity": row["sensitivity"],
        "ingestion_mode": row.get("ingestion_mode", "hybrid"),
        "chunk_count": row["chunk_count"],
        "size_bytes": row["size_bytes"],
        "error_msg": row["error_msg"],
        "domain": row["domain"],
        "owner": row["owner"],
        "tags": row["tags"] or [],
        "valid_until": row["valid_until"],
        "lifecycle": row["lifecycle"],
        "last_queried_at": row["last_queried_at"],
        "chunk_size": row["chunk_size"],
        "chunk_overlap": row["chunk_overlap"],
        "connector_config_masked": row["connector_config_masked"],
        "embedding_provider": row.get("embedding_provider", "openai"),
        "used_by": row["used_by_json"] or [],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "has_raw_text": row["has_raw_text"],
    }


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT {_COLS_NO_BLOB} FROM knowledge_sources ORDER BY created_at DESC"
    )
    return [_row_to_source(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow(
        f"SELECT {_COLS_NO_BLOB} FROM knowledge_sources WHERE id = $1", id_
    )
    return _row_to_source(row) if row else None


async def get_embedding_providers(source_ids: list[str]) -> dict[str, str]:
    """Map of source_id -> embedding_provider, used to enforce that a single
    retrieval query only ever searches sources embedded with the same provider."""
    if not source_ids:
        return {}
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, embedding_provider FROM knowledge_sources WHERE id = ANY($1::text[])",
        source_ids,
    )
    return {r["id"]: r["embedding_provider"] for r in rows}


async def get_file_content(id_: str) -> Optional[bytes]:
    """Fetch raw BYTEA for ingestion pipeline — not included in list/get responses."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT file_content FROM knowledge_sources WHERE id = $1", id_
    )
    if row is None:
        return None
    return bytes(row["file_content"]) if row["file_content"] else None


async def get_raw_text(id_: str) -> Optional[str]:
    """Fetch cached parsed text — used by re-index to skip re-parse."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT raw_text FROM knowledge_sources WHERE id = $1", id_
    )
    return row["raw_text"] if row else None


async def insert(source: dict[str, Any], file_content: Optional[bytes] = None) -> dict[str, Any]:
    pool = get_pool()
    now = _now_iso()
    await pool.execute(
        """INSERT INTO knowledge_sources
           (id, name, source_type, mime_type, file_content, uri, status,
            sensitivity, ingestion_mode, chunk_count, size_bytes,
            domain, owner, tags, valid_until, chunk_size, chunk_overlap,
            connector_config_masked, embedding_provider, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)""",
        source["id"],
        source["name"],
        source["source_type"],
        source.get("mime_type"),
        file_content,
        source["uri"],
        source.get("status", "pending"),
        source.get("sensitivity", "internal"),
        source.get("ingestion_mode", "hybrid"),
        0,
        source.get("size_bytes", 0),
        source.get("domain"),
        source.get("owner"),
        source.get("tags", []),
        source.get("valid_until"),
        source.get("chunk_size", 800),
        source.get("chunk_overlap", 100),
        source.get("connector_config_masked"),
        source.get("embedding_provider", "openai"),
        now,
        now,
    )
    return await get_by_id(source["id"])


async def update_metadata(
    id_: str,
    domain: Optional[str] = None,
    owner: Optional[str] = None,
    tags: Optional[list[str]] = None,
    valid_until: Optional[str] = None,
) -> None:
    pool = get_pool()
    await pool.execute(
        """UPDATE knowledge_sources
           SET domain=$2, owner=$3, tags=$4, valid_until=$5, updated_at=$6
           WHERE id=$1""",
        id_, domain, owner, (tags if tags is not None else []), valid_until, _now_iso(),
    )


async def update_chunk_settings(id_: str, chunk_size: int, chunk_overlap: int) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE knowledge_sources SET chunk_size=$2, chunk_overlap=$3, updated_at=$4 WHERE id=$1",
        id_, chunk_size, chunk_overlap, _now_iso(),
    )


async def mark_used_by(id_: str, used_by: list[str]) -> None:
    pool = get_pool()
    await pool.execute("UPDATE knowledge_sources SET used_by_json = $2 WHERE id = $1", id_, used_by)


async def set_lifecycle(id_: str, lifecycle: str) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE knowledge_sources SET lifecycle=$2, updated_at=$3 WHERE id=$1",
        id_, lifecycle, _now_iso(),
    )


async def touch_last_queried(source_ids: list[str]) -> None:
    """Marks sources as recently used — called after a real /retrieve hit."""
    if not source_ids:
        return
    pool = get_pool()
    await pool.execute(
        "UPDATE knowledge_sources SET last_queried_at=$2 WHERE id = ANY($1::text[])",
        source_ids, _now_iso(),
    )



async def update_status(
    id_: str,
    status: str,
    error_msg: Optional[str] = None,
    chunk_count: Optional[int] = None,
) -> None:
    pool = get_pool()
    now = _now_iso()
    if chunk_count is not None:
        await pool.execute(
            """UPDATE knowledge_sources
               SET status=$2, error_msg=$3, chunk_count=$4, updated_at=$5
               WHERE id=$1""",
            id_, status, error_msg, chunk_count, now,
        )
    else:
        await pool.execute(
            """UPDATE knowledge_sources
               SET status=$2, error_msg=$3, updated_at=$4
               WHERE id=$1""",
            id_, status, error_msg, now,
        )


async def cache_raw_text(id_: str, raw_text: str) -> None:
    """Store parsed text so re-index skips re-parse."""
    pool = get_pool()
    await pool.execute(
        "UPDATE knowledge_sources SET raw_text=$2, updated_at=$3 WHERE id=$1",
        id_, raw_text, _now_iso(),
    )


async def invalidate_raw_text(id_: str) -> None:
    """Force re-parse on next index by clearing cached text."""
    pool = get_pool()
    await pool.execute(
        "UPDATE knowledge_sources SET raw_text=NULL, updated_at=$2 WHERE id=$1",
        id_, _now_iso(),
    )


async def delete(id_: str) -> bool:
    """Deletes source and cascades to pipeline_runs + their stages via FK."""
    pool = get_pool()
    # knowledge_chunks don't have FK so we delete them explicitly first.
    await pool.execute("DELETE FROM knowledge_chunks WHERE source_id=$1", id_)
    result = await pool.execute("DELETE FROM knowledge_sources WHERE id=$1", id_)
    return result == "DELETE 1"
