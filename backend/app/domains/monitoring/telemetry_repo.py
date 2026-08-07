from typing import Any

from app.db.connection import get_pool


async def insert_event(evt: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO request_telemetry
           (id, agent_id, source, status, model, latency_ms, tokens_in, tokens_out, error_msg, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
        evt["id"], evt["agent_id"], evt["source"], evt["status"], evt.get("model"),
        evt["latency_ms"], evt.get("tokens_in", 0), evt.get("tokens_out", 0), evt.get("error_msg"), evt["created_at"],
    )


async def get_all_series(since_iso: str) -> dict[str, list[dict[str, Any]]]:
    """One grouped query across every agent — avoids an N+1 fetch per agent
    on the bootstrap path. Returns {agent_id: [TelemetryPoint, ...]} ordered
    by day, real requests/day since since_iso."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT agent_id, substring(created_at from 1 for 10) as day,
                  count(*) as requests,
                  coalesce(sum(tokens_in), 0)::int as tokens_in,
                  coalesce(sum(tokens_out), 0)::int as tokens_out,
                  coalesce(percentile_cont(0.95) within group (order by latency_ms), 0)::int as p95_ms,
                  count(*) filter (where status = 'error') as errors
           FROM request_telemetry
           WHERE created_at >= $1
           GROUP BY agent_id, day
           ORDER BY agent_id, day""",
        since_iso,
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["agent_id"], []).append(
            {
                "day": r["day"],
                "requests": r["requests"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "p95_ms": r["p95_ms"],
                "errors": r["errors"],
            }
        )
    return out


async def get_model_usage(since_iso: str) -> list[dict[str, Any]]:
    """Tokens grouped by (agent, day, model) — the real per-model breakdown
    FinOps cost needs (different models bill at different rates; get_all_series
    above only has enough granularity for requests/latency/errors)."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT agent_id, substring(created_at from 1 for 10) as day, model,
                  coalesce(sum(tokens_in), 0)::int as tokens_in,
                  coalesce(sum(tokens_out), 0)::int as tokens_out
           FROM request_telemetry
           WHERE created_at >= $1 AND model IS NOT NULL
           GROUP BY agent_id, day, model""",
        since_iso,
    )
    return [dict(r) for r in rows]
