from typing import Any, Optional

from app.db.connection import get_pool

# Column order mirrors deck slide 21's field list. Kept in one place so the
# insert, the row mapper, and the verification suite cannot drift apart.
_COLUMNS = (
    "id, agent_id, request_id, consumer, tool_invoked, system_accessed, "
    "result_status, latency_ms, exception_detail, permission, at"
)


def _row_to_call(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "request_id": row["request_id"],
        "consumer": row["consumer"],
        "tool_invoked": row["tool_invoked"],
        "system_accessed": row["system_accessed"],
        "result_status": row["result_status"],
        "latency_ms": row["latency_ms"],
        "exception_detail": row["exception_detail"],
        "permission": row["permission"],
        "at": row["at"],
    }


async def insert(call: dict[str, Any]) -> dict[str, Any]:
    pool = get_pool()
    await pool.execute(
        f"INSERT INTO tool_calls ({_COLUMNS}) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
        call["id"],
        call["agent_id"],
        call["request_id"],
        call["consumer"],
        call["tool_invoked"],
        call["system_accessed"],
        call["result_status"],
        call["latency_ms"],
        call["exception_detail"],
        call["permission"],
        call["at"],
    )
    return call


async def get_filtered(
    agent_id: Optional[str] = None,
    tool_id: Optional[str] = None,
    result_status: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Newest first. Filters are ANDed; any omitted filter is ignored.

    Parameters are numbered dynamically because asyncpg has no named-parameter
    support and the optional filters change the placeholder positions.
    """
    clauses: list[str] = []
    args: list[Any] = []

    if agent_id:
        args.append(agent_id)
        clauses.append(f"agent_id = ${len(args)}")
    if tool_id:
        args.append(tool_id)
        clauses.append(f"tool_invoked = ${len(args)}")
    if result_status:
        args.append(result_status)
        clauses.append(f"result_status = ${len(args)}")

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    args.append(max(1, min(limit, 1000)))

    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT * FROM tool_calls{where} ORDER BY at DESC LIMIT ${len(args)}", *args
    )
    return [_row_to_call(r) for r in rows]


async def get_all(limit: int = 200) -> list[dict[str, Any]]:
    return await get_filtered(limit=limit)
