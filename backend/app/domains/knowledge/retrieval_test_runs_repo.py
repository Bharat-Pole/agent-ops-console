from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def insert(run: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO retrieval_test_runs
           (id, query, source_ids_json, top_k, score_threshold, rerank_enabled,
            result_count, passed_count, latency_ms, estimated_cost_usd, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
        run["id"], run["query"], run["source_ids"], run["top_k"], run["score_threshold"], run["rerank_enabled"],
        run["result_count"], run["passed_count"], run["latency_ms"], run.get("estimated_cost_usd"), _now_iso(),
    )


async def get_recent(limit: int = 20) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM retrieval_test_runs ORDER BY created_at DESC LIMIT $1", limit
    )
    return [
        {
            "id": r["id"], "query": r["query"], "source_ids": r["source_ids_json"],
            "top_k": r["top_k"], "score_threshold": r["score_threshold"], "rerank_enabled": r["rerank_enabled"],
            "result_count": r["result_count"], "passed_count": r["passed_count"],
            "latency_ms": r["latency_ms"], "estimated_cost_usd": r["estimated_cost_usd"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
