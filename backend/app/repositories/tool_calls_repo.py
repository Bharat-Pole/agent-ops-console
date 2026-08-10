from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.db.connection import get_pool

# Column order mirrors deck slide 21's field list, then Phase 6's trust columns.
# Kept in one place so the insert, the row mapper, and the verification suite
# cannot drift apart.
_COLUMNS = (
    "id, agent_id, request_id, consumer, tool_invoked, system_accessed, "
    "result_status, latency_ms, exception_detail, permission, at, "
    "gateway, decision, denied_by, invocation, principal, team, redacted_fields_json"
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
        # Phase 6. `gateway` is what separates an observed row from a reported
        # one — see db/migrate.py and CONCERNS R7.
        "gateway": row["gateway"],
        "decision": row["decision"],
        "denied_by": row["denied_by"],
        "invocation": row["invocation"],
        "principal": row["principal"],
        "team": row["team"],
        "redacted_fields": row["redacted_fields_json"],
    }


async def insert(call: dict[str, Any]) -> dict[str, Any]:
    """Insert one row.

    The Phase 6 columns are read with `.get()` so the Phase 1 client-reported
    path (`services/tool_call_log.record_tool_call`) needs no changes and keeps
    landing `gateway = FALSE`. A reported row must never accidentally acquire
    the markings of an observed one.
    """
    pool = get_pool()
    await pool.execute(
        f"INSERT INTO tool_calls ({_COLUMNS}) "
        f"VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)",
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
        bool(call.get("gateway", False)),
        call.get("decision"),
        call.get("denied_by"),
        call.get("invocation"),
        call.get("principal"),
        call.get("team"),
        call.get("redacted_fields") or [],
    )
    return call


async def count_recent(agent_id: str, tool_id: str, window_seconds: int) -> int:
    """Allowed gateway calls for this (agent, tool) inside a rolling window.

    Two filters, each load-bearing:

    `gateway = TRUE` — a client-reported row is a claim about something that
    happened elsewhere, so letting one consume a budget the gateway enforces
    would let a caller throttle itself out (or throttle a *different* caller) by
    posting to the Phase 1 endpoint.

    `decision = 'allow'` — a rate limit exists to bound load on the system at the
    far end, and a denied call never reached it. Counting denials would mean a
    caller that keeps hitting a governance rule eventually gets rate-limited for
    calls that were free, which turns one clear denial into a confusing one.

    `at` is TEXT holding an ISO-8601 UTC timestamp, so a lexical `>=` is a
    chronological `>=`. That is a property of the format, not a coincidence, and
    it is why the column can stay TEXT.
    """
    since = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")

    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT COUNT(*) AS n FROM tool_calls
           WHERE agent_id = $1 AND tool_invoked = $2
             AND gateway = TRUE AND decision = 'allow' AND at >= $3""",
        agent_id,
        tool_id,
        since,
    )
    return int(row["n"]) if row else 0


async def get_filtered(
    agent_id: Optional[str] = None,
    tool_id: Optional[str] = None,
    result_status: Optional[str] = None,
    limit: int = 200,
    gateway: Optional[bool] = None,
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
    if gateway is not None:
        args.append(gateway)
        clauses.append(f"gateway = ${len(args)}")

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    args.append(max(1, min(limit, 1000)))

    pool = get_pool()
    rows = await pool.fetch(
        f"SELECT * FROM tool_calls{where} ORDER BY at DESC LIMIT ${len(args)}", *args
    )
    return [_row_to_call(r) for r in rows]


async def get_all(limit: int = 200) -> list[dict[str, Any]]:
    return await get_filtered(limit=limit)


async def gateway_summary() -> dict[str, Any]:
    """Aggregate counts over gateway rows only — Phase 7's traffic overlay.

    Aggregated in SQL rather than by fetching rows and counting in Python: the
    view is a whole-platform read and `get_filtered` is capped at 1000, so a
    Python count would quietly become wrong exactly when the trail got
    interesting.

    `gateway = FALSE` rows are excluded throughout. The gateway view draws what
    the gateway did; a client-reported row is evidence about something that
    happened somewhere else, and mixing the two here would undo the distinction
    the whole phase rests on.
    """
    pool = get_pool()

    totals = await pool.fetchrow(
        """SELECT
               COUNT(*)                                            AS total,
               COUNT(*) FILTER (WHERE decision = 'allow')          AS allowed,
               COUNT(*) FILTER (WHERE decision = 'deny')           AS denied,
               COUNT(*) FILTER (WHERE invocation = 'live')         AS live,
               COUNT(*) FILTER (WHERE invocation = 'simulated')    AS simulated
           FROM tool_calls WHERE gateway = TRUE"""
    )

    by_checkpoint = await pool.fetch(
        """SELECT denied_by AS checkpoint, COUNT(*) AS n FROM tool_calls
           WHERE gateway = TRUE AND decision = 'deny' AND denied_by IS NOT NULL
           GROUP BY denied_by ORDER BY n DESC"""
    )

    by_connector = await pool.fetch(
        """SELECT system_accessed AS connector_id,
                  COUNT(*)                                   AS calls,
                  COUNT(*) FILTER (WHERE decision = 'deny')   AS denied,
                  COUNT(*) FILTER (WHERE invocation = 'live') AS live
           FROM tool_calls WHERE gateway = TRUE AND system_accessed IS NOT NULL
           GROUP BY system_accessed"""
    )

    by_agent = await pool.fetch(
        """SELECT agent_id, COUNT(*) AS calls,
                  COUNT(*) FILTER (WHERE decision = 'deny') AS denied
           FROM tool_calls WHERE gateway = TRUE GROUP BY agent_id"""
    )

    return {
        "total": int(totals["total"]),
        "allowed": int(totals["allowed"]),
        "denied": int(totals["denied"]),
        "live": int(totals["live"]),
        "simulated": int(totals["simulated"]),
        "by_checkpoint": {r["checkpoint"]: int(r["n"]) for r in by_checkpoint},
        "by_connector": {
            r["connector_id"]: {"calls": int(r["calls"]), "denied": int(r["denied"]), "live": int(r["live"])}
            for r in by_connector
        },
        "by_agent": {
            r["agent_id"]: {"calls": int(r["calls"]), "denied": int(r["denied"])} for r in by_agent
        },
    }
