from typing import Any, Optional

from app.db.connection import get_pool


# ---- Deployment records (environment promotion/rollback history) -----------

async def has_records(agent_id: str) -> bool:
    pool = get_pool()
    row = await pool.fetchrow("SELECT 1 FROM deployment_records WHERE agent_id = $1 LIMIT 1", agent_id)
    return row is not None


async def get_history(agent_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM deployment_records WHERE agent_id = $1 ORDER BY created_at DESC", agent_id
    )
    return [dict(r) for r in rows]


async def get_latest(agent_id: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM deployment_records WHERE agent_id = $1 ORDER BY created_at DESC LIMIT 1", agent_id
    )
    return dict(row) if row else None


async def get_latest_environments() -> dict[str, str]:
    """Latest to_environment per agent, one query — avoids an N+1 fetch when
    listing every agent (Agent Registry). config.deployment.environment.value
    alone is NOT enough for this: it's set once at registration and never
    updated by real promote()/rollback() calls, which only write here."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT DISTINCT ON (agent_id) agent_id, to_environment
           FROM deployment_records
           ORDER BY agent_id, created_at DESC"""
    )
    return {r["agent_id"]: r["to_environment"] for r in rows}


async def insert_record(rec: dict[str, Any]) -> dict[str, Any]:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO deployment_records
           (id, agent_id, action, from_environment, to_environment, strategy, status, reason, actor_persona, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
        rec["id"], rec["agent_id"], rec["action"], rec.get("from_environment"), rec["to_environment"],
        rec.get("strategy", "blue-green"), rec.get("status", "success"), rec.get("reason"),
        rec["actor_persona"], rec["created_at"],
    )
    row = await pool.fetchrow("SELECT * FROM deployment_records WHERE id = $1", rec["id"])
    return dict(row)


# ---- Access grants -----------------------------------------------------------

async def has_platform_grant() -> bool:
    pool = get_pool()
    row = await pool.fetchrow("SELECT 1 FROM access_grants WHERE agent_id IS NULL LIMIT 1")
    return row is not None


async def get_grants(agent_id: str) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT * FROM access_grants WHERE (agent_id = $1 OR agent_id IS NULL) AND status = 'active'
           ORDER BY (agent_id IS NULL), granted_at DESC""",
        agent_id,
    )
    return [dict(r) for r in rows]


async def get_grant(grant_id: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM access_grants WHERE id = $1", grant_id)
    return dict(row) if row else None


async def insert_grant(grant: dict[str, Any]) -> dict[str, Any]:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO access_grants
           (id, agent_id, grantee, role_label, scope, granted_by, status, granted_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
        grant["id"], grant.get("agent_id"), grant["grantee"], grant["role_label"],
        grant.get("scope", "owner"), grant["granted_by"], grant.get("status", "active"), grant["granted_at"],
    )
    return await get_grant(grant["id"])


async def revoke_grant(grant_id: str, revoked_by: str, revoked_at: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    existing = await get_grant(grant_id)
    if existing is None:
        return None
    await pool.execute(
        "UPDATE access_grants SET status = 'revoked', revoked_at = $2, revoked_by = $3 WHERE id = $1",
        grant_id, revoked_at, revoked_by,
    )
    return await get_grant(grant_id)
