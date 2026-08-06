from typing import Any, Optional

from app.db.connection import get_pool


def _row_to_approval(row: Any) -> dict[str, Any]:
    return dict(row)


async def insert(item: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO approvals (id, agent_id, step, required_by_path, status, actor_persona, decided_at, note, requested_at, entity_type, entity_id)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
        item["id"],
        item.get("agent_id"),
        item["step"],
        item.get("required_by_path"),
        item["status"],
        item["actor_persona"],
        item["decided_at"],
        item["note"],
        item["requested_at"],
        # Phase 3.2 — the queue is shared across entity kinds. Callers that
        # predate it (registration.py, the seed snapshot) supply neither key and
        # are agent approvals whose subject is their agent.
        item.get("entity_type") or "agent",
        item.get("entity_id") or item.get("agent_id"),
    )


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM approvals ORDER BY requested_at ASC")
    return [_row_to_approval(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM approvals WHERE id = $1", id_)
    return _row_to_approval(row) if row else None


async def get_by_agent(agent_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM approvals WHERE agent_id = $1", agent_id)
    return [_row_to_approval(r) for r in rows]


async def count_pending(agent_id: str) -> int:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT COUNT(*)::int AS n FROM approvals WHERE agent_id = $1 AND status = 'pending'", agent_id
    )
    return row["n"]


async def patch(id_: str, status: str, actor_persona: Optional[str], decided_at: Optional[str], note: Optional[str]) -> Optional[dict[str, Any]]:
    pool = get_pool()
    existing = await get_by_id(id_)
    if existing is None:
        return None
    await pool.execute(
        "UPDATE approvals SET status=$2, actor_persona=$3, decided_at=$4, note=$5 WHERE id=$1",
        id_,
        status,
        actor_persona,
        decided_at,
        note,
    )
    return {**existing, "status": status, "actor_persona": actor_persona, "decided_at": decided_at, "note": note}
