from typing import Any, Optional

from app.db.connection import get_pool


def _row_to_card(row: Any) -> dict[str, Any]:
    return {
        "agent_id": row["agent_id"],
        "name": row["name"],
        "description": row["description"],
        "skills": row["skills_json"],
        "endpoint": row["endpoint"],
        "endpoint_overridden": row["endpoint_overridden"],
        "discovery_only": row["discovery_only"],
        "message_task_format": row["message_task_format"],
        "capability_tier": row["capability_tier"],
        "model": row["model"],
        "input_schema": row["input_schema_json"],
        "output_schema": row["output_schema_json"],
        "updated_at": row["updated_at"],
    }


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM agent_cards ORDER BY name")
    return [_row_to_card(r) for r in rows]


async def get_by_agent(agent_id: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM agent_cards WHERE agent_id = $1", agent_id)
    return _row_to_card(row) if row else None


async def upsert(card: dict[str, Any]) -> dict[str, Any]:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO agent_cards
           (agent_id, name, description, skills_json, endpoint, endpoint_overridden, discovery_only,
            message_task_format, capability_tier, model, input_schema_json, output_schema_json, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
           ON CONFLICT (agent_id) DO UPDATE SET
             name = $2, description = $3, skills_json = $4, endpoint = $5, endpoint_overridden = $6,
             discovery_only = $7, message_task_format = $8, capability_tier = $9, model = $10,
             input_schema_json = $11, output_schema_json = $12, updated_at = $13""",
        card["agent_id"], card["name"], card.get("description"), card.get("skills", []), card["endpoint"],
        card.get("endpoint_overridden", False), card.get("discovery_only", True), card.get("message_task_format"),
        card["capability_tier"], card.get("model"), card.get("input_schema", {}), card.get("output_schema", {}),
        card["updated_at"],
    )
    return await get_by_agent(card["agent_id"])  # type: ignore[return-value]


async def set_endpoint(agent_id: str, endpoint: str, updated_at: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE agent_cards SET endpoint = $2, endpoint_overridden = TRUE, updated_at = $3 WHERE agent_id = $1",
        agent_id, endpoint, updated_at,
    )
    if result.split()[-1] == "0":
        return None
    return await get_by_agent(agent_id)


async def delete(agent_id: str) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM agent_cards WHERE agent_id = $1", agent_id)


async def get_all_agent_ids() -> set[str]:
    pool = get_pool()
    rows = await pool.fetch("SELECT agent_id FROM agent_cards")
    return {r["agent_id"] for r in rows}
