from typing import Any, Optional

from app.db.connection import get_pool


def _row_to_prompt(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "version": row["version"],
        "name": row["name"],
        "kind": row["kind"],
        "category": row["category"],
        "source": row["source"],
        "generated_from": row["generated_from"],
        "body": row["body"],
        "status": row["status"],
        "owner": row["owner"],
        "used_by": row["used_by_json"],
        "history": row["history_json"],
    }


async def insert(p: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO prompts (id, version, name, kind, category, source, generated_from, body, status, owner, used_by_json, history_json)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
        p["id"],
        p["version"],
        p["name"],
        p["kind"],
        p["category"],
        p["source"],
        p.get("generated_from"),
        p["body"],
        p["status"],
        p["owner"],
        p["used_by"],
        p["history"],
    )


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM prompts ORDER BY name ASC")
    return [_row_to_prompt(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM prompts WHERE id = $1", id_)
    return _row_to_prompt(row) if row else None


async def update(id_: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    existing = await get_by_id(id_)
    if existing is None:
        return None
    merged = {**existing, **patch}
    pool = get_pool()
    await pool.execute(
        """UPDATE prompts SET version=$2, name=$3, kind=$4, category=$5, status=$6, body=$7, owner=$8,
               used_by_json=$9, history_json=$10
           WHERE id=$1""",
        id_,
        merged["version"],
        merged["name"],
        merged["kind"],
        merged["category"],
        merged["status"],
        merged["body"],
        merged["owner"],
        merged["used_by"],
        merged["history"],
    )
    return merged
