from typing import Any

from app.db.connection import get_pool


async def insert(job: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO scheduled_jobs (id, kind, entity_id, run_at, status, created_at) VALUES ($1,$2,$3,$4,$5,$6)",
        job["id"],
        job["kind"],
        job["entity_id"],
        job["run_at"],
        job["status"],
        job["created_at"],
    )


async def list_due(now_iso: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM scheduled_jobs WHERE status = 'pending' AND run_at <= $1", now_iso
    )
    return [dict(r) for r in rows]


async def mark_done(id_: str) -> None:
    pool = get_pool()
    await pool.execute("UPDATE scheduled_jobs SET status = 'done' WHERE id = $1", id_)
