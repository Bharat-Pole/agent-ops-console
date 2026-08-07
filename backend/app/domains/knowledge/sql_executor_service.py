"""
Universal SQL Executor & Schema Inspector Service.

Supports:
  1. Real SQL databases (PostgreSQL, SQLite) — the `database` source type
  2. Uploaded CSV & Excel files — auto-mounted as in-memory SQLite tables
  3. BigQuery — real google-cloud-bigquery client (read-only)

Every execution path enforces: read-only statements only (SELECT/WITH/EXPLAIN),
a hard row cap, and — for Postgres — a query timeout, since an LLM-generated
query running unbounded against a real database is a real safety gap, not a
hypothetical one.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import sqlite3
import urllib.parse
from typing import Any

from app.domains.knowledge import knowledge_sources_repo

MAX_ROWS = 500
POSTGRES_QUERY_TIMEOUT_MS = 15_000


def _guard_read_only(query: str) -> str:
    clean_query = query.strip().rstrip(";")
    if not clean_query:
        raise ValueError("Query cannot be empty.")
    # Reject any embedded statement separator, not just a trailing one — an
    # LLM-generated "SELECT 1; DROP TABLE agents" has first_word == SELECT and
    # would otherwise sail through this guard as a stacked-query injection.
    if ";" in clean_query:
        raise ValueError("Only a single read-only statement is permitted — no ';' allowed inside the query.")
    first_word = clean_query.split()[0].upper()
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        raise ValueError("Only read-only SELECT or WITH queries are permitted.")
    return clean_query


def _mount_csv_to_sqlite(csv_bytes: bytes, table_name: str = "data_table") -> sqlite3.Connection:
    """Mounts CSV bytes into an in-memory SQLite database connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    text_content = csv_bytes.decode("utf-8", errors="replace")
    lines = text_content.splitlines()
    if not lines:
        raise ValueError("CSV file is empty.")

    reader = csv.reader(lines)
    rows = list(reader)
    if not rows:
        raise ValueError("CSV file has no rows.")

    raw_headers = [h.strip() if h.strip() else f"col_{i}" for i, h in enumerate(rows[0])]
    clean_headers = [f"[{h}]" for h in raw_headers]

    create_sql = f"CREATE TABLE {table_name} ({', '.join(f'{h} TEXT' for h in clean_headers)});"
    cursor.execute(create_sql)

    placeholders = ", ".join(["?"] * len(clean_headers))
    insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders});"

    for row in rows[1:]:
        if any(row):
            padded = row + [""] * (len(raw_headers) - len(row))
            cursor.execute(insert_sql, padded[: len(raw_headers)])

    conn.commit()
    return conn


def _sanitize_table_name(name: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    return safe or "sheet"


def _mount_excel_to_sqlite(xlsx_bytes: bytes) -> sqlite3.Connection:
    """Mounts each worksheet of an Excel file as its own in-memory SQLite table."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl is required for Excel SQL querying.")

    wb = openpyxl.load_workbook(filename=io.BytesIO(xlsx_bytes), data_only=True)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    mounted_any = False

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        table_name = _sanitize_table_name(sheet_name)
        headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
        clean_headers = [f"[{h}]" for h in headers]

        cursor.execute(f"CREATE TABLE {table_name} ({', '.join(f'{h} TEXT' for h in clean_headers)});")
        placeholders = ", ".join(["?"] * len(headers))
        insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders});"
        for row in rows[1:]:
            if any(v is not None for v in row):
                padded = list(row) + [None] * (len(headers) - len(row))
                cursor.execute(insert_sql, [str(v) if v is not None else None for v in padded[: len(headers)]])
        mounted_any = True

    if not mounted_any:
        raise ValueError("Excel file has no non-empty worksheets.")

    conn.commit()
    return conn


async def _bigquery_schema(service_account_json: str) -> dict[str, list[dict[str, str]]]:
    from app.domains.knowledge.ingestion.bigquery_fetcher import _run_query_sync

    project_id = json.loads(service_account_json).get("project_id", "")
    query = f"""
        SELECT table_name, column_name, data_type
        FROM `{project_id}`.`region-us`.INFORMATION_SCHEMA.COLUMNS
        LIMIT 2000
    """
    try:
        rows = await asyncio.to_thread(_run_query_sync, service_account_json, query, 2000)
    except Exception as e:
        raise ValueError(f"BigQuery schema lookup failed: {e}")

    schema_map: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        t_name = r["table_name"]
        schema_map.setdefault(t_name, []).append({"column": r["column_name"], "type": r["data_type"]})
    return schema_map


async def get_database_schema(source_id: str) -> dict[str, Any]:
    """Inspect schema (table names, columns, data types) for Database, CSV, Excel, or BigQuery sources."""
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise ValueError(f"Source {source_id} not found.")

    source_type = source["source_type"]

    if source_type == "database":
        content_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not content_bytes:
            raise ValueError("Database configuration missing.")
        config = json.loads(content_bytes.decode("utf-8"))
        connection_url = config.get("connection_url", "")

        parsed = urllib.parse.urlparse(connection_url)
        scheme = parsed.scheme.lower()

        if scheme in ("postgres", "postgresql"):
            import asyncpg
            conn = await asyncpg.connect(connection_url)
            try:
                tables_rows = await conn.fetch(
                    """
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                    """
                )
                schema_map: dict[str, list[dict[str, str]]] = {}
                for r in tables_rows:
                    t_name = r["table_name"]
                    if t_name in ("knowledge_chunks", "pipeline_run_stages"):
                        continue
                    schema_map.setdefault(t_name, []).append({"column": r["column_name"], "type": r["data_type"]})
                return {"source_id": source_id, "tables": schema_map}
            finally:
                await conn.close()

        elif scheme in ("sqlite", "sqlite3"):
            conn = sqlite3.connect(parsed.path)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall()]
                schema_map = {}
                for t in tables:
                    cursor.execute(f"PRAGMA table_info({t});")
                    schema_map[t] = [{"column": col[1], "type": col[2]} for col in cursor.fetchall()]
                return {"source_id": source_id, "tables": schema_map}
            finally:
                conn.close()

        raise ValueError(f"Schema inspection is not supported for database scheme '{scheme}'.")

    elif source_type == "file" and "csv" in (source.get("mime_type") or "").lower():
        file_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not file_bytes:
            raise ValueError("CSV file content missing.")
        conn = _mount_csv_to_sqlite(file_bytes, "data_table")
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(data_table);")
            columns = [{"column": col[1], "type": col[2]} for col in cursor.fetchall()]
            return {"source_id": source_id, "tables": {"data_table": columns}}
        finally:
            conn.close()

    elif source_type == "file" and "spreadsheetml" in (source.get("mime_type") or "").lower():
        file_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not file_bytes:
            raise ValueError("Excel file content missing.")
        conn = _mount_excel_to_sqlite(file_bytes)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            schema_map = {}
            for t in tables:
                cursor.execute(f"PRAGMA table_info({t});")
                schema_map[t] = [{"column": col[1], "type": col[2]} for col in cursor.fetchall()]
            return {"source_id": source_id, "tables": schema_map}
        finally:
            conn.close()

    elif source_type == "bigquery":
        content_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not content_bytes:
            raise ValueError("BigQuery configuration missing.")
        config = json.loads(content_bytes.decode("utf-8"))
        schema_map = await _bigquery_schema(config.get("service_account_json", ""))
        return {"source_id": source_id, "tables": schema_map}

    raise ValueError(f"Source type '{source_type}' does not support SQL schema inspection.")


async def execute_structured_query(source_id: str, query: str) -> dict[str, Any]:
    """Execute a read-only SQL query against Database, CSV, Excel, or BigQuery sources.
    Always caps results at MAX_ROWS and applies a statement timeout on Postgres."""
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise ValueError(f"Source {source_id} not found.")

    clean_query = _guard_read_only(query)
    source_type = source["source_type"]

    if source_type == "database":
        content_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not content_bytes:
            raise ValueError("Database configuration missing.")
        config = json.loads(content_bytes.decode("utf-8"))
        connection_url = config.get("connection_url", "")

        parsed = urllib.parse.urlparse(connection_url)
        scheme = parsed.scheme.lower()

        if scheme in ("postgres", "postgresql"):
            import asyncpg
            conn = await asyncpg.connect(connection_url)
            try:
                rows = await conn.fetch(clean_query, timeout=POSTGRES_QUERY_TIMEOUT_MS / 1000)
                result_rows = [dict(r) for r in rows[:MAX_ROWS]]
                return {
                    "source_id": source_id, "row_count": len(result_rows),
                    "truncated": len(rows) > MAX_ROWS, "rows": result_rows,
                }
            except asyncio.TimeoutError:
                raise ValueError(f"Query exceeded the {POSTGRES_QUERY_TIMEOUT_MS}ms safety timeout.")
            finally:
                await conn.close()

        elif scheme in ("sqlite", "sqlite3"):
            conn = sqlite3.connect(parsed.path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.cursor()
                cursor.execute(clean_query)
                all_rows = cursor.fetchall()
                result_rows = [dict(r) for r in all_rows[:MAX_ROWS]]
                return {
                    "source_id": source_id, "row_count": len(result_rows),
                    "truncated": len(all_rows) > MAX_ROWS, "rows": result_rows,
                }
            finally:
                conn.close()

        raise ValueError(f"SQL execution is not supported for database scheme '{scheme}'.")

    elif source_type == "file" and "csv" in (source.get("mime_type") or "").lower():
        file_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not file_bytes:
            raise ValueError("CSV file content missing.")
        conn = _mount_csv_to_sqlite(file_bytes, "data_table")
        try:
            cursor = conn.cursor()
            cursor.execute(clean_query)
            all_rows = cursor.fetchall()
            result_rows = [dict(r) for r in all_rows[:MAX_ROWS]]
            return {
                "source_id": source_id, "row_count": len(result_rows),
                "truncated": len(all_rows) > MAX_ROWS, "rows": result_rows,
            }
        finally:
            conn.close()

    elif source_type == "file" and "spreadsheetml" in (source.get("mime_type") or "").lower():
        file_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not file_bytes:
            raise ValueError("Excel file content missing.")
        conn = _mount_excel_to_sqlite(file_bytes)
        try:
            cursor = conn.cursor()
            cursor.execute(clean_query)
            all_rows = cursor.fetchall()
            result_rows = [dict(r) for r in all_rows[:MAX_ROWS]]
            return {
                "source_id": source_id, "row_count": len(result_rows),
                "truncated": len(all_rows) > MAX_ROWS, "rows": result_rows,
            }
        finally:
            conn.close()

    elif source_type == "bigquery":
        from app.domains.knowledge.ingestion.bigquery_fetcher import _run_query_sync

        content_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not content_bytes:
            raise ValueError("BigQuery configuration missing.")
        config = json.loads(content_bytes.decode("utf-8"))
        try:
            rows = await asyncio.to_thread(_run_query_sync, config.get("service_account_json", ""), clean_query, MAX_ROWS)
        except Exception as e:
            raise ValueError(f"BigQuery query failed: {e}")
        return {"source_id": source_id, "row_count": len(rows), "truncated": len(rows) >= MAX_ROWS, "rows": rows}

    raise ValueError(f"Source '{source['name']}' ({source_type}) does not support structured SQL execution.")


def build_text_to_sql_prompt(schema_info: dict[str, Any], question: str) -> str:
    """Constructs an explicit Text-to-SQL system & instruction prompt incorporating
    the target schema, column data types, and safety rules."""
    tables_fmt = []
    for table_name, columns in schema_info.get("tables", {}).items():
        cols_str = ", ".join([f"{col['column']} ({col['type']})" for col in columns])
        tables_fmt.append(f"Table: {table_name}\nColumns: {cols_str}")

    schema_text = "\n\n".join(tables_fmt) if tables_fmt else "Table: data_table (Dynamic Columns)"

    return f"""You are an expert PostgreSQL / SQLite Text-to-SQL Translator.

Your task is to convert the user's natural language question into a valid, efficient, read-only SQL query based strictly on the schema provided below.

=== DATABASE SCHEMA ===
{schema_text}

=== RULES & CONSTRAINTS ===
1. Return ONLY the raw SQL query. Do NOT include markdown codeblocks, explanations, or quotes.
2. Only write read-only SELECT or WITH statements. Never output INSERT, UPDATE, DELETE, or DROP.
3. Use case-insensitive matching where appropriate (e.g. UPPER(col) = 'VAL' or ILIKE '%val%').
4. Cast numbers or dates appropriately if querying numeric or date columns.
5. Add a LIMIT clause (e.g. LIMIT 500) unless the question clearly asks for an aggregate (COUNT/SUM/AVG).

=== USER QUESTION ===
{question}

=== GENERATED SQL QUERY ===
"""


def _extract_sql(raw_text: str) -> str:
    """Strips markdown code fences if the model added them despite being told not to."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip().rstrip(";")


async def generate_sql_from_question(source_id: str, question: str) -> dict[str, Any]:
    """Builds the schema-aware prompt for a natural-language question. Returns the
    prompt and schema only — does not call an LLM or execute anything. Use
    `ask_question` for the full generate-and-execute flow."""
    schema_info = await get_database_schema(source_id)
    prompt = build_text_to_sql_prompt(schema_info, question)
    return {
        "source_id": source_id,
        "question": question,
        "schema": schema_info.get("tables", {}),
        "text_to_sql_prompt": prompt,
    }


LLM_PROVIDERS = ("anthropic", "groq")


async def _generate_sql_text(prompt: str, llm_provider: str) -> str:
    if llm_provider == "groq":
        from app.domains.chat.groq_service import is_groq_configured, generate_text

        if not is_groq_configured():
            raise RuntimeError("GROQ_API_KEY not configured — cannot generate SQL from a question.")
        return await generate_text(prompt, max_tokens=512)

    from app.domains.chat.claude_service import is_claude_configured, _get_client, MODEL_BY_TIER

    if not is_claude_configured():
        raise RuntimeError("ANTHROPIC_API_KEY not configured — cannot generate SQL from a question.")
    response = await _get_client().messages.create(
        model=MODEL_BY_TIER["minimal"],
        max_tokens=512,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    text_block = next((b for b in response.content if b.type == "text"), None)
    return text_block.text if text_block else ""


async def ask_question(source_id: str, question: str, llm_provider: str = "anthropic") -> dict[str, Any]:
    """
    The real end-to-end path: schema -> LLM-generated SQL -> executed read-only ->
    real rows back. This is what closes the gap where the platform could build a
    text-to-SQL prompt but nothing ever sent it to a model or ran the result.
    `llm_provider` selects which model generates the SQL — 'anthropic' (Claude) or
    'groq' (hosted open-source models, e.g. Llama 3.3 70B).
    """
    if not question.strip():
        raise ValueError("question is required")
    if llm_provider not in LLM_PROVIDERS:
        raise ValueError(f"Unknown llm_provider '{llm_provider}'. Must be one of {LLM_PROVIDERS}.")

    schema_info = await get_database_schema(source_id)
    prompt = build_text_to_sql_prompt(schema_info, question)

    raw_text = await _generate_sql_text(prompt, llm_provider)
    if not raw_text.strip():
        raise RuntimeError("Model returned no SQL.")

    sql = _extract_sql(raw_text)
    result = await execute_structured_query(source_id, sql)
    return {
        "source_id": source_id,
        "question": question,
        "llm_provider": llm_provider,
        "generated_sql": sql,
        "row_count": result["row_count"],
        "truncated": result["truncated"],
        "rows": result["rows"],
    }
