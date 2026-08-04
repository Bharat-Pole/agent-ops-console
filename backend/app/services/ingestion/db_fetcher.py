"""
Database Ingestion Fetcher — Connects to SQL databases, inspects schema, and ingests tables into formatted text.

Supported engines:
  - PostgreSQL (postgresql:// or postgres://)
  - SQLite (sqlite://)
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Optional


def mask_connection_url(url: str) -> str:
    """Mask password in connection string for safe UI display/storage in metadata."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urllib.parse.urlunparse(parsed._replace(netloc=netloc))
        return url
    except Exception:
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


async def fetch_database_query(connection_url: str, query: Optional[str] = None, allowed_tables: Optional[list[str]] = None) -> tuple[bytes, str]:
    """
    Connects to the database using connection_url.
    If query is provided, executes that query.
    If query is None or empty, automatically introspects and ingests ALL user tables (or allowed_tables).
    """
    parsed = urllib.parse.urlparse(connection_url)
    scheme = parsed.scheme.lower()
    clean_query = (query or "").strip()

    if clean_query:
        # Guard against destructive queries if a query was explicitly provided
        first_word = clean_query.split()[0].upper()
        if first_word not in ("SELECT", "WITH", "EXPLAIN"):
            raise ValueError("Only read-only SELECT or WITH queries are permitted for ingestion.")

    if scheme in ("postgres", "postgresql"):
        text_content = await _fetch_postgres(connection_url, clean_query, allowed_tables=allowed_tables)
    elif scheme in ("mysql", "mariadb"):
        text_content = await _fetch_mysql(connection_url, clean_query, allowed_tables=allowed_tables)
    elif scheme in ("sqlite", "sqlite3"):
        text_content = await _fetch_sqlite(parsed.path, clean_query, allowed_tables=allowed_tables)
    else:
        raise ValueError(
            f"Unsupported database scheme '{scheme}'. Supported schemes: postgresql://, mysql://, mariadb://, sqlite://"
        )

    return text_content.encode("utf-8"), "text/plain"



async def _fetch_postgres(connection_url: str, custom_query: str, allowed_tables: Optional[list[str]] = None) -> str:
    try:
        import asyncpg
    except ImportError:
        raise RuntimeError("asyncpg is required for PostgreSQL ingestion.")

    try:
        conn = await asyncpg.connect(connection_url)
    except Exception as e:
        raise RuntimeError(f"Database connection failed: {e}")

    try:
        if custom_query:
            tables_data = [("custom_query", await conn.fetch(custom_query))]
        else:
            # Automatic full-DB ingestion: find all base tables in 'public' schema
            table_rows = await conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
            tables = [r["table_name"] for r in table_rows]
            if allowed_tables:
                tables = [t for t in tables if t in allowed_tables]
            if not tables:
                raise RuntimeError("No user tables found in database schema 'public'.")

            tables_data = []
            for t_name in tables:
                # Exclude internal system migration/indexing tables if any
                if t_name in ("knowledge_chunks", "pipeline_run_stages"):
                    continue
                rows = await conn.fetch(f'SELECT * FROM "{t_name}" LIMIT 5000')
                tables_data.append((t_name, rows))

        formatted_output: list[str] = []
        for table_name, rows in tables_data:
            if not rows:
                continue

            # Special formatting for Incident Log tables vs generic tables
            is_incident_table = any(
                term in table_name.lower() for term in ("incident", "log", "ticket", "outage", "event")
            )
            table_header = f"=== {'INCIDENT LOG STORE' if is_incident_table else 'TABLE'}: {table_name} ({len(rows)} records) ==="
            formatted_output.append(table_header)

            for idx, row in enumerate(rows, start=1):
                row_dict = dict(row)
                
                # Check for standard Incident Log metadata fields
                ticket_id = row_dict.get("ticket_id") or row_dict.get("incident_id") or row_dict.get("id") or f"LOG-{idx}"
                severity = row_dict.get("severity") or row_dict.get("priority") or "INFO"
                component = row_dict.get("component") or row_dict.get("service") or row_dict.get("system") or "Core System"
                timestamp = row_dict.get("timestamp") or row_dict.get("created_at") or row_dict.get("at") or ""

                lines = [f"--- INCIDENT RECORD #{idx} | ID: {ticket_id} | SEVERITY: {severity} | COMPONENT: {component} ---"]
                if timestamp:
                    lines.append(f"TIMESTAMP: {timestamp}")

                for col, val in row_dict.items():
                    if val is not None:
                        lines.append(f"{col}: {val}")
                formatted_output.append("\n".join(lines))

        if not formatted_output:
            raise RuntimeError("Database contains 0 records across tables.")

        return "\n\n".join(formatted_output)
    finally:
        await conn.close()


async def _fetch_sqlite(db_path: str, custom_query: str, allowed_tables: Optional[list[str]] = None) -> str:
    import sqlite3

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if custom_query:
            cursor.execute(custom_query)
            tables_data = [("custom_query", cursor.fetchall())]
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            table_rows = cursor.fetchall()
            tables = [r["name"] for r in table_rows]
            if allowed_tables:
                tables = [t for t in tables if t in allowed_tables]
            if not tables:
                raise RuntimeError("No user tables found in SQLite database.")

            tables_data = []
            for t_name in tables:
                cursor.execute(f'SELECT * FROM "{t_name}" LIMIT 5000;')
                tables_data.append((t_name, cursor.fetchall()))

        formatted_output: list[str] = []
        for table_name, rows in tables_data:
            if not rows:
                continue
            formatted_output.append(f"=== TABLE: {table_name} ({len(rows)} rows) ===")
            for idx, row in enumerate(rows, start=1):
                row_dict = dict(row)
                lines = [f"--- [{table_name}] RECORD {idx} ---"]
                for col, val in row_dict.items():
                    if val is not None:
                        lines.append(f"{col}: {val}")
                formatted_output.append("\n".join(lines))

        if not formatted_output:
            raise RuntimeError("Database contains 0 records across all tables.")

        return "\n\n".join(formatted_output)
    finally:
        conn.close()


async def _fetch_mysql(connection_url: str, custom_query: str, allowed_tables: Optional[list[str]] = None) -> str:
    """Fetch records from MySQL / MariaDB databases."""
    try:
        import aiomysql
    except ImportError:
        raise RuntimeError("aiomysql is required for MySQL ingestion.")

    parsed = urllib.parse.urlparse(connection_url)
    try:
        conn = await aiomysql.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "root",
            password=parsed.password or "",
            db=parsed.path.lstrip("/") or "",
            cursorclass=aiomysql.DictCursor,
        )
    except Exception as e:
        raise RuntimeError(f"MySQL connection failed: {e}")

    try:
        async with conn.cursor() as cursor:
            if custom_query:
                await cursor.execute(custom_query)
                tables_data = [("custom_query", await cursor.fetchall())]
            else:
                await cursor.execute("SHOW TABLES")
                table_rows = await cursor.fetchall()
                if not table_rows:
                    raise RuntimeError("No user tables found in MySQL database.")
                tables = [list(r.values())[0] for r in table_rows]
                if allowed_tables:
                    tables = [t for t in tables if t in allowed_tables]

                tables_data = []
                for t_name in tables:
                    await cursor.execute(f"SELECT * FROM `{t_name}` LIMIT 5000")
                    tables_data.append((t_name, await cursor.fetchall()))

        formatted_output: list[str] = []
        for table_name, rows in tables_data:
            if not rows:
                continue
            formatted_output.append(f"=== TABLE: {table_name} ({len(rows)} records) ===")
            for idx, row in enumerate(rows, start=1):
                row_dict = dict(row)
                lines = [f"--- [{table_name}] RECORD {idx} ---"]
                for col, val in row_dict.items():
                    if val is not None:
                        lines.append(f"{col}: {val}")
                formatted_output.append("\n".join(lines))

        return "\n\n".join(formatted_output)
    finally:
        conn.close()

