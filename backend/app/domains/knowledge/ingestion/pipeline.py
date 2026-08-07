"""
Async Ingestion Pipeline Orchestrator

Entry point: run_pipeline(source_id, run_id)
Called from FastAPI BackgroundTasks — runs fully in the background.

Stages:
  fetch    → read BYTEA or scrape URL
  parse    → extract plain text
  chunk    → recursive character split
  embed    → OpenAI text-embedding-3-small in batches
  store    → atomic swap (new chunks in, old chunks out)
  finalize → mark run success + update source status
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.domains.knowledge import knowledge_chunks_repo, knowledge_sources_repo, pipeline_runs_repo
from app.domains.knowledge.embeddings_service import embed_batch, is_embeddings_configured
from app.domains.knowledge.ingestion.chunker import chunk_text
from app.domains.knowledge.ingestion.parsers import fetch_url, parse_by_mime

EMBED_BATCH_SIZE = 100
EMBED_RETRY_DELAYS = [1.0, 2.0, 4.0]  # exponential backoff on rate-limit


async def _embed_with_retry(texts: list[str], provider: str) -> list[list[float]]:
    """Batch embed with exponential backoff on rate-limit errors (OpenAI only —
    the local provider runs on-CPU with no rate limits, so it just succeeds or
    raises immediately)."""
    last_err: Exception | None = None
    for attempt, delay in enumerate([0.0] + EMBED_RETRY_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await embed_batch(texts, provider=provider)
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if "rate" not in err_str and "429" not in err_str:
                raise  # Non-rate-limit errors → fail immediately
    raise last_err


async def run_pipeline(source_id: str, run_id: str) -> None:
    """
    Main pipeline entry point. All exceptions are caught and stored as
    run/stage errors so the frontend can surface them clearly.
    """
    try:
        await _execute_pipeline(source_id, run_id)
    except Exception as e:
        error_msg = str(e) or "Unknown pipeline error"
        print(f"[pipeline] ERROR source={source_id} run={run_id}: {error_msg}")
        await pipeline_runs_repo.fail_run(run_id, error_msg)
        await knowledge_sources_repo.update_status(source_id, "error", error_msg=error_msg)


async def _execute_pipeline(source_id: str, run_id: str) -> None:
    # ── Guard: verify source still exists ────────────────────────────────────
    source = await knowledge_sources_repo.get_by_id(source_id)
    if source is None:
        raise RuntimeError(f"Source {source_id} not found — was it deleted?")

    await knowledge_sources_repo.update_status(source_id, "indexing")

    # ── Stage 1: FETCH ────────────────────────────────────────────────────────
    await pipeline_runs_repo.start_stage(run_id, "fetch")
    try:
        raw_bytes, mime_type = await _fetch(source, source_id)
    except Exception as e:
        await pipeline_runs_repo.fail_stage(run_id, "fetch", str(e))
        raise

    await pipeline_runs_repo.finish_stage(run_id, "fetch", items_done=1)

    # ── Stage 2: PARSE ────────────────────────────────────────────────────────
    await pipeline_runs_repo.start_stage(run_id, "parse", items_total=1)
    try:
        # Use cached raw_text if available (skip re-parse on re-index)
        raw_text = source.get("has_raw_text") and await knowledge_sources_repo.get_raw_text(source_id)
        if not raw_text:
            raw_text = parse_by_mime(raw_bytes, mime_type)
            await knowledge_sources_repo.cache_raw_text(source_id, raw_text)
    except Exception as e:
        await pipeline_runs_repo.fail_stage(run_id, "parse", str(e))
        raise

    await pipeline_runs_repo.finish_stage(run_id, "parse", items_done=1)

    ingestion_mode = source.get("ingestion_mode", "hybrid")

    if ingestion_mode == "sql":
        # Pure SQL Mode: Skip vector chunking & OpenAI embedding completely!
        await pipeline_runs_repo.start_stage(run_id, "chunk", items_total=1)
        await pipeline_runs_repo.finish_stage(run_id, "chunk", items_done=0)
        await pipeline_runs_repo.start_stage(run_id, "embed", items_total=1)
        await pipeline_runs_repo.finish_stage(run_id, "embed", items_done=0)
        await pipeline_runs_repo.start_stage(run_id, "store", items_total=1)
        await pipeline_runs_repo.finish_stage(run_id, "store", items_done=0)
        await pipeline_runs_repo.start_stage(run_id, "finalize", items_total=1)
        await knowledge_sources_repo.update_status(source_id, "ready", chunk_count=0)
        await pipeline_runs_repo.finish_run(run_id, chunks_created=0)
        await pipeline_runs_repo.finish_stage(run_id, "finalize", items_done=1)
        print(f"[pipeline] DONE (Pure SQL Mode) source={source_id} run={run_id}")
        return

    # ── Stage 3: CHUNK ────────────────────────────────────────────────────────
    await pipeline_runs_repo.start_stage(run_id, "chunk", items_total=1)
    try:
        doc_id = source["uri"]
        chunks = chunk_text(
            raw_text,
            doc_id=doc_id,
            chunk_size=source.get("chunk_size") or 800,
            chunk_overlap=source.get("chunk_overlap") or 100,
        )
    except Exception as e:
        await pipeline_runs_repo.fail_stage(run_id, "chunk", str(e))
        raise

    await pipeline_runs_repo.finish_stage(run_id, "chunk", items_done=len(chunks))

    if not chunks:
        await pipeline_runs_repo.fail_stage(run_id, "chunk", "No text chunks produced — document may be empty or unreadable.")
        raise RuntimeError("No chunks produced")


    # ── Stage 4: EMBED ────────────────────────────────────────────────────────
    embedding_provider = source.get("embedding_provider", "openai")
    if not is_embeddings_configured(embedding_provider):
        detail = (
            "OPENAI_API_KEY not configured"
            if embedding_provider == "openai"
            else "sentence-transformers not installed — cannot use the local embedding provider"
        )
        await pipeline_runs_repo.fail_stage(run_id, "embed", detail)
        raise RuntimeError(detail)

    chunk_texts = [c.text for c in chunks]
    total = len(chunk_texts)
    await pipeline_runs_repo.start_stage(run_id, "embed", items_total=total)

    all_vectors: list[list[float]] = []
    try:
        for batch_start in range(0, total, EMBED_BATCH_SIZE):
            batch = chunk_texts[batch_start: batch_start + EMBED_BATCH_SIZE]
            vectors = await _embed_with_retry(batch, embedding_provider)
            all_vectors.extend(vectors)
            await pipeline_runs_repo.update_stage_progress(run_id, "embed", len(all_vectors))
    except Exception as e:
        await pipeline_runs_repo.fail_stage(run_id, "embed", str(e))
        raise

    await pipeline_runs_repo.finish_stage(run_id, "embed", items_done=total)

    # ── Stage 5: STORE (atomic swap) ──────────────────────────────────────────
    await pipeline_runs_repo.start_stage(run_id, "store", items_total=total)
    try:
        chunk_rows = [
            {
                "id": f"kc-{uuid.uuid4()}",
                "source_id": source_id,
                "run_id": run_id,
                "doc_id": c.doc_id,
                "chunk_index": c.chunk_index,
                "text": c.text,
                "embedding": vector,
                "metadata": c.metadata,
            }
            for c, vector in zip(chunks, all_vectors)
        ]
        stored = await knowledge_chunks_repo.atomic_swap(source_id, run_id, chunk_rows, provider=embedding_provider)
    except Exception as e:
        await pipeline_runs_repo.fail_stage(run_id, "store", str(e))
        raise

    await pipeline_runs_repo.finish_stage(run_id, "store", items_done=stored)

    # ── Stage 6: FINALIZE ─────────────────────────────────────────────────────
    await pipeline_runs_repo.start_stage(run_id, "finalize", items_total=1)
    await knowledge_sources_repo.update_status(source_id, "ready", chunk_count=stored)
    await pipeline_runs_repo.finish_run(run_id, chunks_created=stored)
    await pipeline_runs_repo.finish_stage(run_id, "finalize", items_done=1)

    print(f"[pipeline] DONE source={source_id} run={run_id} chunks={stored}")


async def _fetch(source: dict[str, Any], source_id: str) -> tuple[bytes, str]:
    """
    Returns (raw_bytes, mime_type) for the source.
    For 'text' type, returns encoded UTF-8 bytes.
    For 'url' type, performs HTTP fetch.
    For 'file' type, reads BYTEA from DB.
    """
    source_type = source["source_type"]

    if source_type == "text":
        # Raw text is already stored — fetch it directly
        raw_text = await knowledge_sources_repo.get_raw_text(source_id)
        if not raw_text:
            raise RuntimeError("Text source has no raw_text stored")
        return raw_text.encode("utf-8"), "text/plain"

    elif source_type == "url":
        uri = source["uri"]
        content, mime_type = await fetch_url(uri)
        return content, mime_type

    elif source_type == "database":
        from app.domains.knowledge.ingestion.db_fetcher import fetch_database_query
        content_bytes = await knowledge_sources_repo.get_file_content(source_id)
        if not content_bytes:
            raise RuntimeError("Database source missing config details")
        import json
        config = json.loads(content_bytes.decode("utf-8"))
        conn_url = config.get("connection_url", "")
        query = config.get("query", "")
        content, mime_type = await fetch_database_query(conn_url, query)
        return content, mime_type

    elif source_type == "file":
        content = await knowledge_sources_repo.get_file_content(source_id)
        if not content:
            raise RuntimeError("File source has no file_content stored")
        return content, source.get("mime_type") or "application/octet-stream"

    elif source_type == "confluence":
        from app.domains.knowledge.ingestion.confluence_fetcher import fetch_confluence
        config = await _load_connector_config(source_id)
        return await fetch_confluence(
            base_url=config.get("base_url", ""),
            email=config.get("email", ""),
            api_token=config.get("api_token", ""),
            page_id=config.get("page_id") or None,
            space_key=config.get("space_key") or None,
        )

    elif source_type == "jira":
        from app.domains.knowledge.ingestion.jira_fetcher import fetch_jira
        config = await _load_connector_config(source_id)
        return await fetch_jira(
            base_url=config.get("base_url", ""),
            email=config.get("email", ""),
            api_token=config.get("api_token", ""),
            jql=config.get("jql", ""),
        )

    elif source_type == "github":
        from app.domains.knowledge.ingestion.github_fetcher import fetch_github
        config = await _load_connector_config(source_id)
        return await fetch_github(
            owner=config.get("owner", ""),
            repo=config.get("repo", ""),
            path=config.get("path", ""),
            branch=config.get("branch") or None,
            token=config.get("token") or None,
        )

    elif source_type == "servicenow":
        from app.domains.knowledge.ingestion.servicenow_fetcher import fetch_servicenow
        config = await _load_connector_config(source_id)
        return await fetch_servicenow(
            instance_url=config.get("instance_url", ""),
            table=config.get("table", ""),
            username=config.get("username", ""),
            password=config.get("password", ""),
            query=config.get("query", ""),
        )

    elif source_type == "bigquery":
        from app.domains.knowledge.ingestion.bigquery_fetcher import fetch_bigquery
        config = await _load_connector_config(source_id)
        return await fetch_bigquery(
            service_account_json=config.get("service_account_json", ""),
            query=config.get("query", ""),
        )

    else:
        raise RuntimeError(f"Unknown source_type: {source_type}")


async def _load_connector_config(source_id: str) -> dict[str, Any]:
    import json
    content_bytes = await knowledge_sources_repo.get_file_content(source_id)
    if not content_bytes:
        raise RuntimeError("Connector source is missing its configuration.")
    return json.loads(content_bytes.decode("utf-8"))
