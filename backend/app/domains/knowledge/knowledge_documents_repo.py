from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def document_id(source_id: str, doc_ref: str) -> str:
    return f"{source_id}::{doc_ref}"


def _row_to_document(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source_id": row["source_id"],
        "doc_ref": row["doc_ref"],
        "title": row["title"],
        "domain": row["domain"],
        "owner": row["owner"],
        "sensitivity": row["sensitivity"],
        "valid_until": row["valid_until"],
        "lifecycle": row["lifecycle"],
        "last_queried_at": row["last_queried_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def get_by_source(source_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM knowledge_documents WHERE source_id = $1 ORDER BY title ASC", source_id
    )
    return [_row_to_document(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM knowledge_documents WHERE id = $1", id_)
    return _row_to_document(row) if row else None


async def upsert_from_ingestion(
    source_id: str,
    doc_ref: str,
    title: str,
    defaults: dict[str, Any],
) -> None:
    """Called once per real fetched document on every (re)index. Inserts a new
    row with the parent source's current tags as sane real defaults; on an
    existing row it only refreshes the title (a page/issue can be renamed
    upstream) and NEVER overwrites tags a governance owner already set."""
    pool = get_pool()
    now = _now_iso()
    id_ = document_id(source_id, doc_ref)
    await pool.execute(
        """INSERT INTO knowledge_documents
             (id, source_id, doc_ref, title, domain, owner, sensitivity, valid_until, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$9)
           ON CONFLICT (source_id, doc_ref) DO UPDATE SET title = EXCLUDED.title""",
        id_, source_id, doc_ref, title,
        defaults.get("domain"), defaults.get("owner"), defaults.get("sensitivity", "internal"),
        defaults.get("valid_until"), now,
    )


async def update_metadata(
    id_: str,
    domain: Optional[str] = None,
    owner: Optional[str] = None,
    sensitivity: Optional[str] = None,
    valid_until: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    existing = await get_by_id(id_)
    if existing is None:
        return None
    pool = get_pool()
    await pool.execute(
        """UPDATE knowledge_documents
           SET domain=$2, owner=$3, sensitivity=$4, valid_until=$5, updated_at=$6
           WHERE id=$1""",
        id_, domain, owner, sensitivity or existing["sensitivity"], valid_until, _now_iso(),
    )
    return await get_by_id(id_)


async def set_lifecycle(id_: str, lifecycle: str) -> Optional[dict[str, Any]]:
    existing = await get_by_id(id_)
    if existing is None:
        return None
    pool = get_pool()
    await pool.execute(
        "UPDATE knowledge_documents SET lifecycle=$2, updated_at=$3 WHERE id=$1",
        id_, lifecycle, _now_iso(),
    )
    return await get_by_id(id_)


async def get_retired_ids(document_ids: list[str]) -> set[str]:
    """Given a set of chunk doc_ids possibly belonging to retired documents,
    return which ones are retired — used to filter them out of retrieval."""
    if not document_ids:
        return set()
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id FROM knowledge_documents WHERE id = ANY($1::text[]) AND lifecycle = 'retired'",
        document_ids,
    )
    return {r["id"] for r in rows}


async def touch_last_queried(document_ids: list[str]) -> None:
    if not document_ids:
        return
    pool = get_pool()
    await pool.execute(
        "UPDATE knowledge_documents SET last_queried_at=$2 WHERE id = ANY($1::text[])",
        document_ids, _now_iso(),
    )
