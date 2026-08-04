"""
BigQuery connector — real google-cloud-bigquery client calls, no simulation.

Auth: a service-account JSON key, pasted by the user and stored the same way the
`database` source type stores its connection string (JSON blob in the BYTEA column).

google-cloud-bigquery's client is synchronous — every call here runs via
asyncio.to_thread so it doesn't block the FastAPI event loop.
"""
from __future__ import annotations

import asyncio
import json


def _make_client(service_account_json: str):
    from google.cloud import bigquery
    from google.oauth2 import service_account

    try:
        info = json.loads(service_account_json)
    except json.JSONDecodeError:
        raise ValueError("Service account key is not valid JSON.")

    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
    )
    return bigquery.Client(credentials=credentials, project=info.get("project_id"))


def _run_query_sync(service_account_json: str, query: str, max_rows: int) -> list[dict]:
    client = _make_client(service_account_json)
    query_job = client.query(query)
    rows = list(query_job.result(max_results=max_rows))
    return [dict(row.items()) for row in rows]


async def test_connection(service_account_json: str) -> tuple[bool, str]:
    try:
        rows = await asyncio.to_thread(_run_query_sync, service_account_json, "SELECT 1 AS ok", 1)
        return True, f"Connected — BigQuery query executed successfully ({rows})."
    except Exception as e:
        return False, str(e)


async def fetch_bigquery(service_account_json: str, query: str) -> tuple[bytes, str]:
    if not service_account_json:
        raise ValueError("A BigQuery service-account JSON key is required.")
    clean_query = (query or "").strip()
    if not clean_query:
        raise ValueError("A SQL query is required, e.g. SELECT * FROM `project.dataset.table` LIMIT 1000")
    first_word = clean_query.split()[0].upper()
    if first_word not in ("SELECT", "WITH"):
        raise ValueError("Only read-only SELECT or WITH queries are permitted for ingestion.")

    try:
        rows = await asyncio.to_thread(_run_query_sync, service_account_json, clean_query, 5000)
    except Exception as e:
        raise RuntimeError(f"BigQuery query failed: {e}")

    if not rows:
        raise RuntimeError("BigQuery query returned 0 rows.")

    formatted: list[str] = []
    for idx, row in enumerate(rows, start=1):
        lines = [f"--- BIGQUERY ROW #{idx} ---"]
        for col, val in row.items():
            if val is not None:
                lines.append(f"{col}: {val}")
        formatted.append("\n".join(lines))

    header = f"=== BIGQUERY QUERY RESULT ({len(rows)} rows) ===\nQUERY: {clean_query}\n"
    return (header + "\n\n" + "\n\n".join(formatted)).encode("utf-8"), "text/plain"
