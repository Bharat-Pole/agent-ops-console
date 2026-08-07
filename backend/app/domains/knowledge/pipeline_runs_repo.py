import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool

STAGES = ["fetch", "parse", "chunk", "embed", "store", "finalize"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row_to_run(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source_id": row["source_id"],
        "trigger": row["trigger"],
        "status": row["status"],
        "chunks_created": row["chunks_created"],
        "error_msg": row["error_msg"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "created_at": row["created_at"],
    }


def _row_to_stage(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "stage_name": row["stage_name"],
        "status": row["status"],
        "items_total": row["items_total"],
        "items_done": row["items_done"],
        "error_msg": row["error_msg"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


async def create_run(source_id: str, trigger: str = "manual") -> dict[str, Any]:
    """Create a pipeline run and pre-insert all 6 stages as 'pending'."""
    pool = get_pool()
    now = _now_iso()
    run_id = f"pr-{uuid.uuid4()}"

    await pool.execute(
        """INSERT INTO pipeline_runs
           (id, source_id, trigger, status, chunks_created, started_at, created_at)
           VALUES ($1,$2,$3,'running',0,$4,$5)""",
        run_id, source_id, trigger, now, now,
    )

    # Pre-insert all 6 stages as pending so frontend can see the full pipeline
    for stage in STAGES:
        stage_id = f"prs-{uuid.uuid4()}"
        await pool.execute(
            """INSERT INTO pipeline_run_stages
               (id, run_id, stage_name, status, items_total, items_done)
               VALUES ($1,$2,$3,'pending',0,0)""",
            stage_id, run_id, stage,
        )

    return await get_run_with_stages(run_id)


async def get_all_runs() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT 100"
    )
    return [_row_to_run(r) for r in rows]


async def get_runs_for_source(source_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM pipeline_runs WHERE source_id=$1 ORDER BY created_at DESC",
        source_id,
    )
    return [_row_to_run(r) for r in rows]


async def get_stages(run_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM pipeline_run_stages WHERE run_id=$1 ORDER BY id ASC",
        run_id,
    )
    return [_row_to_stage(r) for r in rows]


async def get_run_with_stages(run_id: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM pipeline_runs WHERE id=$1", run_id)
    if row is None:
        return None
    stages = await get_stages(run_id)
    return {**_row_to_run(row), "stages": stages}


async def start_stage(run_id: str, stage_name: str, items_total: int = 0) -> None:
    now = _now_iso()
    pool = get_pool()
    await pool.execute(
        """UPDATE pipeline_run_stages
           SET status='running', items_total=$3, started_at=$4
           WHERE run_id=$1 AND stage_name=$2""",
        run_id, stage_name, items_total, now,
    )


async def update_stage_progress(run_id: str, stage_name: str, items_done: int) -> None:
    pool = get_pool()
    await pool.execute(
        """UPDATE pipeline_run_stages
           SET items_done=$3
           WHERE run_id=$1 AND stage_name=$2""",
        run_id, stage_name, items_done,
    )


async def finish_stage(run_id: str, stage_name: str, items_done: Optional[int] = None) -> None:
    now = _now_iso()
    pool = get_pool()
    if items_done is not None:
        await pool.execute(
            """UPDATE pipeline_run_stages
               SET status='done', items_done=$3, finished_at=$4
               WHERE run_id=$1 AND stage_name=$2""",
            run_id, stage_name, items_done, now,
        )
    else:
        await pool.execute(
            """UPDATE pipeline_run_stages
               SET status='done', finished_at=$3
               WHERE run_id=$1 AND stage_name=$2""",
            run_id, stage_name, now,
        )


async def fail_stage(run_id: str, stage_name: str, error_msg: str) -> None:
    now = _now_iso()
    pool = get_pool()
    await pool.execute(
        """UPDATE pipeline_run_stages
           SET status='error', error_msg=$3, finished_at=$4
           WHERE run_id=$1 AND stage_name=$2""",
        run_id, stage_name, error_msg, now,
    )


async def finish_run(run_id: str, chunks_created: int) -> None:
    now = _now_iso()
    pool = get_pool()
    await pool.execute(
        """UPDATE pipeline_runs
           SET status='success', chunks_created=$2, finished_at=$3
           WHERE id=$1""",
        run_id, chunks_created, now,
    )


async def fail_run(run_id: str, error_msg: str) -> None:
    now = _now_iso()
    pool = get_pool()
    await pool.execute(
        """UPDATE pipeline_runs
           SET status='error', error_msg=$2, finished_at=$3
           WHERE id=$1""",
        run_id, error_msg, now,
    )
