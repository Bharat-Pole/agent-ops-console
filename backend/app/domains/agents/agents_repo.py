from typing import Any, Callable, Optional

from app.db.connection import get_pool


def agent_id(agent: dict[str, Any]) -> str:
    return agent["config"]["identity"]["agent_id"]["value"]


def _row_to_agent(row: Any) -> dict[str, Any]:
    return {
        "config": row["config_json"],
        "capability_tier": row["capability_tier"],
        "governance_path": row["governance_path"],
        "tracks": row["tracks_json"],
        "signal_breakdown": row["signal_breakdown_json"],
        "review_card": row["review_card_json"],
        "evaluation_pack_id": row["evaluation_pack_id"],
        "approval_ids": row["approval_ids_json"],
        "fast_path_expiry_date": row["fast_path_expiry_date"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "demo_mode": row["demo_mode"],
    }


async def insert(agent: dict[str, Any]) -> None:
    pool = get_pool()
    cfg = agent["config"]
    await pool.execute(
        """INSERT INTO agents
           (id, agent_name, lifecycle_status, risk_tier, capability_tier, governance_path, demo_mode,
            config_json, tracks_json, signal_breakdown_json, review_card_json, evaluation_pack_id,
            approval_ids_json, fast_path_expiry_date, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)""",
        agent_id(agent),
        cfg["identity"]["agent_name"]["value"],
        cfg["lifecycle"]["lifecycle_status"]["value"],
        cfg["lifecycle"]["risk_tier"]["value"],
        agent["capability_tier"],
        agent["governance_path"],
        agent["demo_mode"],
        cfg,
        agent["tracks"],
        agent["signal_breakdown"],
        agent["review_card"],
        agent["evaluation_pack_id"],
        agent["approval_ids"],
        agent["fast_path_expiry_date"],
        agent["created_at"],
        agent["updated_at"],
    )


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM agents ORDER BY created_at ASC")
    return [_row_to_agent(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM agents WHERE id = $1", id_)
    return _row_to_agent(row) if row else None


async def patch(id_: str, updater: Callable[[dict[str, Any]], dict[str, Any]]) -> Optional[dict[str, Any]]:
    pool = get_pool()
    agent = await get_by_id(id_)
    if agent is None:
        return None
    nxt = updater(agent)
    cfg = nxt["config"]
    await pool.execute(
        """UPDATE agents SET
             agent_name=$2, lifecycle_status=$3, risk_tier=$4, capability_tier=$5, governance_path=$6,
             demo_mode=$7, config_json=$8, tracks_json=$9, signal_breakdown_json=$10, review_card_json=$11,
             evaluation_pack_id=$12, approval_ids_json=$13, fast_path_expiry_date=$14, updated_at=$15
           WHERE id=$1""",
        id_,
        cfg["identity"]["agent_name"]["value"],
        cfg["lifecycle"]["lifecycle_status"]["value"],
        cfg["lifecycle"]["risk_tier"]["value"],
        nxt["capability_tier"],
        nxt["governance_path"],
        nxt["demo_mode"],
        cfg,
        nxt["tracks"],
        nxt["signal_breakdown"],
        nxt["review_card"],
        nxt["evaluation_pack_id"],
        nxt["approval_ids"],
        nxt["fast_path_expiry_date"],
        nxt["updated_at"],
    )
    return nxt


async def merge_patch(id_: str, patch_: dict[str, Any]) -> Optional[dict[str, Any]]:
    return await patch(id_, lambda a: {**a, **patch_})


async def delete_by_id(id_: str) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # approvals/eval_packs FK-reference agents — clear them first.
            await conn.execute("DELETE FROM eval_packs WHERE agent_id = $1", id_)
            await conn.execute("DELETE FROM approvals WHERE agent_id = $1", id_)
            status = await conn.execute("DELETE FROM agents WHERE id = $1", id_)
    return status.split()[-1] != "0"
