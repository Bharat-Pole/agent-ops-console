from datetime import datetime, timezone
from typing import Any, Optional

from app.db.connection import get_pool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row_to_model(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "provider": row["provider"],
        "roles": row["roles_json"],
        "context_window": row["context_window"],
        "cost_input_per_mtok": row["cost_input_per_mtok"],
        "cost_output_per_mtok": row["cost_output_per_mtok"],
        "latency_p50_ms": row["latency_p50_ms"],
        "approved_use_case": row["approved_use_case"],
        "risk_tier_mapping": row["risk_tier_mapping_json"],
        "owner": row["owner"],
        "deployment_status": row["deployment_status"],
        "access_policy": row["access_policy"],
        "fallback_of": row["fallback_of"],
        "routing_note": row["routing_note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def get_all() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM models ORDER BY provider ASC, name ASC")
    return [_row_to_model(r) for r in rows]


async def get_by_id(id_: str) -> Optional[dict[str, Any]]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM models WHERE id = $1", id_)
    return _row_to_model(row) if row else None


async def insert(model: dict[str, Any]) -> None:
    pool = get_pool()
    now = model.get("created_at") or _now_iso()
    await pool.execute(
        """INSERT INTO models
           (id, name, provider, roles_json, context_window, cost_input_per_mtok, cost_output_per_mtok,
            latency_p50_ms, approved_use_case, risk_tier_mapping_json, owner, deployment_status,
            access_policy, fallback_of, routing_note, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)""",
        model["id"],
        model["name"],
        model["provider"],
        model.get("roles", []),
        model.get("context_window", 0),
        model.get("cost_input_per_mtok", 0),
        model.get("cost_output_per_mtok", 0),
        model.get("latency_p50_ms", 0),
        model.get("approved_use_case", ""),
        model.get("risk_tier_mapping", []),
        model.get("owner"),
        model.get("deployment_status", "candidate"),
        model.get("access_policy", ""),
        model.get("fallback_of"),
        model.get("routing_note", ""),
        now,
        now,
    )


async def update_fields(id_: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    allowed = {
        "name", "provider", "context_window", "cost_input_per_mtok", "cost_output_per_mtok",
        "latency_p50_ms", "approved_use_case", "owner", "deployment_status", "access_policy",
        "fallback_of", "routing_note",
    }
    json_allowed = {"roles": "roles_json", "risk_tier_mapping": "risk_tier_mapping_json"}
    fields: dict[str, Any] = {k: v for k, v in patch.items() if k in allowed}
    for src, col in json_allowed.items():
        if src in patch:
            fields[col] = patch[src]
    if not fields:
        return await get_by_id(id_)
    pool = get_pool()
    set_clause = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(fields))
    await pool.execute(
        f"UPDATE models SET {set_clause}, updated_at = ${len(fields) + 2} WHERE id = $1",
        id_, *fields.values(), _now_iso(),
    )
    return await get_by_id(id_)


async def delete_by_id(id_: str) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM models WHERE id = $1", id_)
    return result.split()[-1] != "0"
