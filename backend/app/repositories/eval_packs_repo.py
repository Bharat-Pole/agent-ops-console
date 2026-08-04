from typing import Any, Optional

from app.db.connection import get_pool


def _row_to_pack(row: Any) -> dict[str, Any]:
    pack_json = row["pack_json"]
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "generated_by": "engine",
        "cases": pack_json["cases"],
        "last_run": pack_json["last_run"],
    }


async def insert(pack: dict[str, Any]) -> None:
    pool = get_pool()
    pack_json = {"cases": pack["cases"], "last_run": pack["last_run"]}
    await pool.execute(
        "INSERT INTO eval_packs (id, agent_id, pack_json) VALUES ($1,$2,$3)",
        pack["id"],
        pack["agent_id"],
        pack_json,
    )


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM eval_packs")
    return [_row_to_pack(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM eval_packs WHERE id = $1", id_)
    return _row_to_pack(row) if row else None
