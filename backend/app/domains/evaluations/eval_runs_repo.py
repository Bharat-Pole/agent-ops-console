from typing import Any, Optional

from app.db.connection import get_pool


def _row_to_run(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "pack_id": row["pack_id"],
        "agent_id": row["agent_id"],
        "score": row["score"],
        "results": row["results_json"],
        "model_used": row["model_used"],
        "error_msg": row["error_msg"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "actor_persona": row["actor_persona"],
    }


async def insert(run: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO eval_runs (id, pack_id, agent_id, score, results_json, model_used, error_msg, started_at, finished_at, actor_persona)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
        run["id"], run["pack_id"], run["agent_id"], run["score"], run["results"],
        run.get("model_used"), run.get("error_msg"), run["started_at"], run["finished_at"], run["actor_persona"],
    )


async def get_for_pack(pack_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM eval_runs WHERE pack_id = $1 ORDER BY finished_at DESC", pack_id)
    return [_row_to_run(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM eval_runs WHERE id = $1", id_)
    return _row_to_run(row) if row else None
