from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---- Policy rules (capability_tier × risk_tier -> governance_path) ---------

async def get_all_policy_rules() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM policy_rules ORDER BY capability_tier, risk_tier")
    return [dict(r) for r in rows]


async def governance_path_for(tier: str, risk: str) -> Optional[str]:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT governance_path FROM policy_rules WHERE capability_tier = $1 AND risk_tier = $2", tier, risk
    )
    return row["governance_path"] if row else None


async def upsert_policy_rule(tier: str, risk: str, path: str, updated_by: str) -> dict[str, Any]:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO policy_rules (capability_tier, risk_tier, governance_path, updated_at, updated_by)
           VALUES ($1,$2,$3,$4,$5)
           ON CONFLICT (capability_tier, risk_tier)
           DO UPDATE SET governance_path = $3, updated_at = $4, updated_by = $5""",
        tier, risk, path, _now_iso(), updated_by,
    )
    row = await pool.fetchrow("SELECT * FROM policy_rules WHERE capability_tier = $1 AND risk_tier = $2", tier, risk)
    return dict(row)


# ---- Path definitions -------------------------------------------------------

def _row_to_path_def(row: Any) -> dict[str, Any]:
    return {
        "path": row["path"],
        "label": row["label"],
        "approvals": row["approvals_json"],
        "hitl_gates": row["hitl_gates"],
        "desc": row["description"],
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
    }


async def get_all_path_definitions() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM path_definitions ORDER BY path")
    return [_row_to_path_def(r) for r in rows]


async def get_path_definition(path: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM path_definitions WHERE path = $1", path)
    return _row_to_path_def(row) if row else None


async def insert_path_definition(pd: dict[str, Any]) -> None:
    pool = get_pool()
    now = _now_iso()
    await pool.execute(
        """INSERT INTO path_definitions (path, label, approvals_json, hitl_gates, description, updated_at, updated_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7)""",
        pd["path"], pd["label"], pd.get("approvals", []), pd.get("hitl_gates", 0), pd.get("description", ""), now, None,
    )


async def update_path_definition(path: str, patch: dict[str, Any], updated_by: str) -> Optional[dict[str, Any]]:
    allowed = {"label": "label", "hitl_gates": "hitl_gates", "description": "description"}
    fields = {allowed[k]: v for k, v in patch.items() if k in allowed}
    if "approvals" in patch:
        fields["approvals_json"] = patch["approvals"]
    if not fields:
        return await get_path_definition(path)
    pool = get_pool()
    set_clause = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(fields))
    await pool.execute(
        f"UPDATE path_definitions SET {set_clause}, updated_at = ${len(fields) + 2}, updated_by = ${len(fields) + 3} WHERE path = $1",
        path, *fields.values(), _now_iso(), updated_by,
    )
    return await get_path_definition(path)


# ---- Exception register -----------------------------------------------------

async def get_all_exceptions() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM governance_exceptions ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def get_exception(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM governance_exceptions WHERE id = $1", id_)
    return dict(row) if row else None


async def insert_exception(exc: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO governance_exceptions (id, agent_id, reason, granted_by, status, expires_at, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7)""",
        exc["id"], exc["agent_id"], exc["reason"], exc["granted_by"], exc.get("status", "active"),
        exc["expires_at"], exc.get("created_at") or _now_iso(),
    )


async def revoke_exception(id_: str, revoked_by: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    existing = await get_exception(id_)
    if existing is None:
        return None
    await pool.execute(
        "UPDATE governance_exceptions SET status = 'revoked', revoked_at = $2, revoked_by = $3 WHERE id = $1",
        id_, _now_iso(), revoked_by,
    )
    return await get_exception(id_)


async def expire_due_exceptions() -> int:
    """Flips any still-'active' exception whose expires_at has passed to 'expired'.
    Called on bootstrap read — cheap, and keeps the register honest without a
    background scheduler for something this low-frequency."""
    pool = get_pool()
    result = await pool.execute(
        "UPDATE governance_exceptions SET status = 'expired' WHERE status = 'active' AND expires_at < $1",
        _now_iso(),
    )
    return int(result.split()[-1])
