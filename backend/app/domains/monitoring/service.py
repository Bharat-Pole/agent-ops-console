import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.domains.agents import agents_repo
from app.domains.evaluations import eval_runs_repo
from app.domains.models import models_repo
from app.domains.monitoring import telemetry_repo


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def record_event(
    agent_id: str,
    source: str,
    status: str,
    latency_ms: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    model: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> None:
    await telemetry_repo.insert_event(
        {
            "id": f"tel-{uuid.uuid4()}",
            "agent_id": agent_id,
            "source": source,
            "status": status,
            "model": model,
            "latency_ms": round(latency_ms),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "error_msg": error_msg,
            "created_at": _now_iso(),
        }
    )


async def get_all_telemetry(days: int = 30) -> list[dict[str, Any]]:
    """Real per-agent telemetry for the Monitoring & FinOps pages — replaces
    kernel/telemetry.ts's fabricated PRNG series. series[] is built from real
    request_telemetry rows (empty for an agent with no real chat/eval calls
    yet, which is the honest state rather than a fabricated chart).
    eval_score_history is likewise real, read from eval_runs (module 5).
    Each day's `cost` is real too — tokens actually used that day, priced at
    the real per-model rate from the Model Repository (module 3), not a flat
    per-token estimate. A day mixing e.g. a Haiku chat call and a Haiku judge
    call is priced per-model then summed, so mixed-model days stay accurate."""
    agents = await agents_repo.get_all()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    series_by_agent = await telemetry_repo.get_all_series(since)
    model_usage = await telemetry_repo.get_model_usage(since)
    models = await models_repo.get_all()
    price_by_model = {m["id"]: (m["cost_input_per_mtok"], m["cost_output_per_mtok"]) for m in models}

    cost_by_agent_day: dict[tuple[str, str], float] = {}
    for row in model_usage:
        rate_in, rate_out = price_by_model.get(row["model"], (0.0, 0.0))
        cost = (row["tokens_in"] / 1_000_000) * rate_in + (row["tokens_out"] / 1_000_000) * rate_out
        key = (row["agent_id"], row["day"])
        cost_by_agent_day[key] = cost_by_agent_day.get(key, 0.0) + cost

    result: list[dict[str, Any]] = []
    for agent in agents:
        aid = agents_repo.agent_id(agent)
        pack_id = agent.get("evaluation_pack_id")
        eval_history: list[dict[str, Any]] = []
        if pack_id:
            runs = await eval_runs_repo.get_for_pack(pack_id)
            eval_history = [{"date": r["finished_at"][:10], "score": r["score"]} for r in reversed(runs)]
        series = series_by_agent.get(aid, [])
        for point in series:
            point["cost"] = round(cost_by_agent_day.get((aid, point["day"]), 0.0), 6)
        result.append({"agent_id": aid, "series": series, "eval_score_history": eval_history})
    return result
