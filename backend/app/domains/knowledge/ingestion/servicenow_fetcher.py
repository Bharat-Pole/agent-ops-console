"""
ServiceNow connector — real Table API calls, no simulation.

Auth: HTTP Basic (service account username/password), ServiceNow's standard
Table API auth: https://docs.servicenow.com/bundle/latest-release-notes/page/integrate/inbound-rest/concept/c_TableAPI.html
"""
from __future__ import annotations

_MAX_RECORDS = 200


async def test_connection(instance_url: str, username: str, password: str) -> tuple[bool, str]:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15, auth=(username, password)) as client:
            resp = await client.get(
                f"{instance_url.rstrip('/')}/api/now/table/sys_user",
                params={"sysparm_limit": 1},
                headers={"Accept": "application/json"},
            )
        if resp.status_code == 401:
            return False, "ServiceNow authentication failed (401) — check instance URL/username/password."
        resp.raise_for_status()
        return True, "Connected — ServiceNow Table API reachable."
    except Exception as e:
        return False, str(e)


async def fetch_servicenow(
    instance_url: str,
    table: str,
    username: str,
    password: str,
    query: str = "",
) -> tuple[bytes, str]:
    import httpx

    if not instance_url:
        raise ValueError("ServiceNow instance URL is required, e.g. https://yourinstance.service-now.com")
    if not table:
        raise ValueError("A ServiceNow table name is required, e.g. incident")

    params = {"sysparm_limit": _MAX_RECORDS}
    if query:
        params["sysparm_query"] = query

    async with httpx.AsyncClient(timeout=30, auth=(username, password)) as client:
        resp = await client.get(
            f"{instance_url.rstrip('/')}/api/now/table/{table}",
            params=params,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 401:
            raise RuntimeError("ServiceNow authentication failed (401) — check username/password.")
        if resp.status_code == 404:
            raise RuntimeError(f"ServiceNow table '{table}' not found.")
        resp.raise_for_status()
        records = resp.json().get("result", [])

    if not records:
        raise RuntimeError(f"ServiceNow table '{table}' returned 0 records for this query.")

    formatted: list[str] = []
    for idx, rec in enumerate(records, start=1):
        sys_id = rec.get("sys_id", f"ROW-{idx}")
        lines = [f"--- SERVICENOW {table.upper()} RECORD #{idx} | sys_id: {sys_id} ---"]
        for col, val in rec.items():
            if val not in (None, ""):
                lines.append(f"{col}: {val}")
        formatted.append("\n".join(lines))

    return (
        f"=== SERVICENOW TABLE: {table} ({len(records)} records) ===\n\n" + "\n\n".join(formatted)
    ).encode("utf-8"), "text/plain"
