"""
Knowledge & RAG API Routes
All endpoints under /v1/knowledge/*
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.env import env
from app.repositories import knowledge_chunks_repo, knowledge_sources_repo, pipeline_runs_repo
from app.services.ingestion.pipeline import run_pipeline
from app.services.embeddings import embed_text, is_embeddings_configured


router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _shared_meta_from_body(body: dict[str, Any]) -> dict[str, Any]:
    """Extract the tagging/chunking fields shared across every source-creation endpoint."""
    tags = body.get("tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []
    return {
        "domain": body.get("domain") or None,
        "owner": body.get("owner") or None,
        "tags": tags,
        "valid_until": body.get("valid_until") or None,
        "chunk_size": int(body.get("chunk_size", 800)),
        "chunk_overlap": int(body.get("chunk_overlap", 100)),
        "embedding_provider": body.get("embedding_provider") or "openai",
        "ingestion_mode": body.get("ingestion_mode") or "hybrid",
    }


# ── Sources ───────────────────────────────────────────────────────────────────

@router.get("/sources")
async def list_sources() -> JSONResponse:
    sources = await knowledge_sources_repo.get_all()
    return JSONResponse(content={"sources": sources})


@router.get("/sources/{source_id}")
async def get_source(source_id: str) -> JSONResponse:
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    runs = await pipeline_runs_repo.get_runs_for_source(source_id)
    return JSONResponse(content={"source": source, "runs": runs})


@router.post("/sources/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    sensitivity: str = Form("internal"),
    ingestion_mode: str = Form("hybrid"),
    domain: Optional[str] = Form(None),
    owner: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    valid_until: Optional[str] = Form(None),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(100),
    embedding_provider: str = Form("openai"),
) -> JSONResponse:
    """Upload a file (PDF, DOCX, TXT, MD, CSV, XLSX). Stored as BYTEA in Postgres."""
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    source_id = _new_id("ks")
    display_name = name or file.filename or source_id
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    source = await knowledge_sources_repo.insert(
        {
            "id": source_id,
            "name": display_name,
            "source_type": "file",
            "mime_type": file.content_type or "application/octet-stream",
            "uri": file.filename or display_name,
            "sensitivity": sensitivity,
            "ingestion_mode": ingestion_mode,
            "size_bytes": len(content),
            "domain": domain or None,
            "owner": owner or None,
            "tags": tag_list,
            "valid_until": valid_until or None,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "embedding_provider": embedding_provider,
        },
        file_content=content,
    )

    run = await pipeline_runs_repo.create_run(source_id, trigger="manual")
    background_tasks.add_task(run_pipeline, source_id, run["id"])


    return JSONResponse(
        status_code=202,
        content={"source": source, "run_id": run["id"], "status": "pending"},
    )


@router.post("/sources/url")
async def add_url_source(
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
) -> JSONResponse:
    """Add a URL source. The pipeline will fetch and parse it."""
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    source_id = _new_id("ks")
    name = body.get("name") or url
    sensitivity = body.get("sensitivity", "internal")

    source = await knowledge_sources_repo.insert(
        {
            "id": source_id,
            "name": name,
            "source_type": "url",
            "uri": url,
            "sensitivity": sensitivity,
            **_shared_meta_from_body(body),
        }
    )

    run = await pipeline_runs_repo.create_run(source_id, trigger="manual")
    background_tasks.add_task(run_pipeline, source_id, run["id"])

    return JSONResponse(
        status_code=202,
        content={"source": source, "run_id": run["id"], "status": "pending"},
    )


@router.post("/sources/database")
async def add_database_source(
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
) -> JSONResponse:
    """Add a SQL Database source (PostgreSQL, SQLite)."""
    from app.services.ingestion.db_fetcher import mask_connection_url
    import json

    connection_url = body.get("connection_url", "").strip()
    query = body.get("query", "").strip()
    name = body.get("name", "").strip()
    sensitivity = body.get("sensitivity", "internal")

    if not connection_url:
        raise HTTPException(status_code=400, detail="connection_url is required")
    if not name:
        name = f"DB: {mask_connection_url(connection_url)}"


    source_id = _new_id("ks")
    safe_uri = mask_connection_url(connection_url)

    # Store credentials in encrypted/BYTEA payload
    config_bytes = json.dumps({"connection_url": connection_url, "query": query}).encode("utf-8")

    source = await knowledge_sources_repo.insert(
        {
            "id": source_id,
            "name": name,
            "source_type": "database",
            "uri": safe_uri,
            "sensitivity": sensitivity,
            "size_bytes": len(config_bytes),
            "connector_config_masked": safe_uri,
            **_shared_meta_from_body(body),
        },
        file_content=config_bytes,
    )

    run = await pipeline_runs_repo.create_run(source_id, trigger="manual")
    background_tasks.add_task(run_pipeline, source_id, run["id"])

    return JSONResponse(
        status_code=202,
        content={"source": source, "run_id": run["id"], "status": "pending"},
    )



@router.post("/sources/text")
async def add_text_source(
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
) -> JSONResponse:
    """Add raw text directly. No file needed."""
    text = body.get("text", "").strip()
    name = body.get("name", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    source_id = _new_id("ks")
    sensitivity = body.get("sensitivity", "internal")

    # For text sources, store raw_text immediately — fetch stage reads it back
    source = await knowledge_sources_repo.insert(
        {
            "id": source_id,
            "name": name,
            "source_type": "text",
            "uri": name,
            "sensitivity": sensitivity,
            "size_bytes": len(text.encode("utf-8")),
            **_shared_meta_from_body(body),
        }
    )
    await knowledge_sources_repo.cache_raw_text(source_id, text)

    run = await pipeline_runs_repo.create_run(source_id, trigger="manual")
    background_tasks.add_task(run_pipeline, source_id, run["id"])

    return JSONResponse(
        status_code=202,
        content={"source": source, "run_id": run["id"], "status": "pending"},
    )


async def _create_connector_source(
    background_tasks: BackgroundTasks,
    source_type: str,
    name: str,
    uri: str,
    config: dict[str, Any],
    sensitivity: str,
    body: dict[str, Any],
) -> JSONResponse:
    """Shared creation path for every real external connector (Confluence/Jira/GitHub/
    ServiceNow/BigQuery): stores credentials as a JSON blob exactly like the `database`
    source type already does, then kicks off the same ingestion pipeline."""
    import json

    source_id = _new_id("ks")
    config_bytes = json.dumps(config).encode("utf-8")

    source = await knowledge_sources_repo.insert(
        {
            "id": source_id,
            "name": name,
            "source_type": source_type,
            "uri": uri,
            "sensitivity": sensitivity,
            "size_bytes": len(config_bytes),
            "connector_config_masked": uri,
            **_shared_meta_from_body(body),
        },
        file_content=config_bytes,
    )

    run = await pipeline_runs_repo.create_run(source_id, trigger="manual")
    background_tasks.add_task(run_pipeline, source_id, run["id"])

    return JSONResponse(
        status_code=202,
        content={"source": source, "run_id": run["id"], "status": "pending"},
    )


@router.post("/sources/confluence")
async def add_confluence_source(background_tasks: BackgroundTasks, body: dict[str, Any]) -> JSONResponse:
    base_url = body.get("base_url", "").strip()
    email = body.get("email", "").strip()
    api_token = body.get("api_token", "").strip()
    page_id = body.get("page_id", "").strip()
    space_key = body.get("space_key", "").strip()
    if not base_url or not email or not api_token:
        raise HTTPException(status_code=400, detail="base_url, email, and api_token are required")
    if not page_id and not space_key:
        raise HTTPException(status_code=400, detail="Provide either page_id or space_key")

    name = body.get("name", "").strip() or f"Confluence: {space_key or page_id}"
    uri = f"{base_url.rstrip('/')} ({space_key or ('page ' + page_id)})"
    config = {"base_url": base_url, "email": email, "api_token": api_token, "page_id": page_id, "space_key": space_key}
    return await _create_connector_source(background_tasks, "confluence", name, uri, config, body.get("sensitivity", "internal"), body)


@router.post("/sources/jira")
async def add_jira_source(background_tasks: BackgroundTasks, body: dict[str, Any]) -> JSONResponse:
    base_url = body.get("base_url", "").strip()
    email = body.get("email", "").strip()
    api_token = body.get("api_token", "").strip()
    jql = body.get("jql", "").strip()
    if not base_url or not email or not api_token or not jql:
        raise HTTPException(status_code=400, detail="base_url, email, api_token, and jql are required")

    name = body.get("name", "").strip() or f"Jira: {jql[:40]}"
    uri = f"{base_url.rstrip('/')} ({jql})"
    config = {"base_url": base_url, "email": email, "api_token": api_token, "jql": jql}
    return await _create_connector_source(background_tasks, "jira", name, uri, config, body.get("sensitivity", "internal"), body)


@router.post("/sources/github")
async def add_github_source(background_tasks: BackgroundTasks, body: dict[str, Any]) -> JSONResponse:
    # NOTE: the wire field is `repo_owner`, not `owner` — `owner` is reserved for the
    # shared tagging field (document owner/team) parsed by _shared_meta_from_body.
    repo_owner = body.get("repo_owner", "").strip()
    repo = body.get("repo", "").strip()
    path = body.get("path", "").strip()
    branch = body.get("branch", "").strip()
    token = body.get("token", "").strip()
    if not repo_owner or not repo:
        raise HTTPException(status_code=400, detail="repo_owner and repo are required")

    name = body.get("name", "").strip() or f"GitHub: {repo_owner}/{repo}"
    uri = f"github.com/{repo_owner}/{repo}/{path}".rstrip("/") + (f"@{branch}" if branch else "")
    config = {"owner": repo_owner, "repo": repo, "path": path, "branch": branch, "token": token}
    return await _create_connector_source(background_tasks, "github", name, uri, config, body.get("sensitivity", "internal"), body)


@router.post("/sources/servicenow")
async def add_servicenow_source(background_tasks: BackgroundTasks, body: dict[str, Any]) -> JSONResponse:
    instance_url = body.get("instance_url", "").strip()
    table = body.get("table", "").strip()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    query = body.get("query", "").strip()
    if not instance_url or not table or not username or not password:
        raise HTTPException(status_code=400, detail="instance_url, table, username, and password are required")

    name = body.get("name", "").strip() or f"ServiceNow: {table}"
    uri = f"{instance_url.rstrip('/')}/{table}"
    config = {"instance_url": instance_url, "table": table, "username": username, "password": password, "query": query}
    return await _create_connector_source(background_tasks, "servicenow", name, uri, config, body.get("sensitivity", "internal"), body)


@router.post("/sources/bigquery")
async def add_bigquery_source(background_tasks: BackgroundTasks, body: dict[str, Any]) -> JSONResponse:
    import json as _json
    service_account_json = body.get("service_account_json", "").strip()
    query = body.get("query", "").strip()
    if not service_account_json or not query:
        raise HTTPException(status_code=400, detail="service_account_json and query are required")
    try:
        project_id = _json.loads(service_account_json).get("project_id", "unknown-project")
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="service_account_json is not valid JSON")

    name = body.get("name", "").strip() or f"BigQuery: {project_id}"
    uri = f"bigquery://{project_id}"
    config = {"service_account_json": service_account_json, "query": query}
    return await _create_connector_source(background_tasks, "bigquery", name, uri, config, body.get("sensitivity", "internal"), body)


@router.post("/sources/test-connection")
async def test_source_connection(body: dict[str, Any]) -> JSONResponse:
    """
    Makes one real call to the target system before the user commits to creating a
    source. Never returns a fabricated success — a real failure (bad auth, wrong URL,
    unreachable host) comes back as ok=False with the actual upstream error message.
    """
    source_type = body.get("source_type", "")
    config = body.get("config", {})

    try:
        if source_type == "confluence":
            from app.services.ingestion.confluence_fetcher import test_connection
            ok, detail = await test_connection(config.get("base_url", ""), config.get("email", ""), config.get("api_token", ""))
        elif source_type == "jira":
            from app.services.ingestion.jira_fetcher import test_connection
            ok, detail = await test_connection(config.get("base_url", ""), config.get("email", ""), config.get("api_token", ""))
        elif source_type == "github":
            from app.services.ingestion.github_fetcher import test_connection
            ok, detail = await test_connection(config.get("repo_owner", ""), config.get("repo", ""), config.get("token") or None)
        elif source_type == "servicenow":
            from app.services.ingestion.servicenow_fetcher import test_connection
            ok, detail = await test_connection(config.get("instance_url", ""), config.get("username", ""), config.get("password", ""))
        elif source_type == "bigquery":
            from app.services.ingestion.bigquery_fetcher import test_connection
            ok, detail = await test_connection(config.get("service_account_json", ""))
        else:
            raise HTTPException(status_code=400, detail=f"No test-connection check exists for source_type '{source_type}'")
    except HTTPException:
        raise
    except Exception as e:
        ok, detail = False, str(e)

    return JSONResponse(content={"ok": ok, "detail": detail})


@router.post("/sources/{source_id}/reindex")
async def reindex_source(
    source_id: str,
    background_tasks: BackgroundTasks,
    body: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    """Re-run the ingestion pipeline. Uses cached raw_text if available.
    Optional body {chunk_size, chunk_overlap} updates chunking settings before the re-run."""
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if body and ("chunk_size" in body or "chunk_overlap" in body):
        await knowledge_sources_repo.update_chunk_settings(
            source_id,
            chunk_size=int(body.get("chunk_size", source["chunk_size"])),
            chunk_overlap=int(body.get("chunk_overlap", source["chunk_overlap"])),
        )

    # If re-indexing a file/url, keep cached raw_text (fast re-index).
    # Clear it only if explicitly requested via body param in future.
    await knowledge_sources_repo.update_status(source_id, "pending")
    run = await pipeline_runs_repo.create_run(source_id, trigger="manual")
    background_tasks.add_task(run_pipeline, source_id, run["id"])

    return JSONResponse(
        status_code=202,
        content={"run_id": run["id"], "status": "pending"},
    )


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str) -> JSONResponse:
    deleted = await knowledge_sources_repo.delete(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    return JSONResponse(status_code=200, content={"deleted": source_id})


@router.patch("/sources/{source_id}/metadata")
async def update_source_metadata(source_id: str, body: dict[str, Any]) -> JSONResponse:
    """Update domain/owner/tags/valid_until tagging fields for an existing source."""
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    meta = _shared_meta_from_body(body)
    await knowledge_sources_repo.update_metadata(
        source_id, domain=meta["domain"], owner=meta["owner"], tags=meta["tags"], valid_until=meta["valid_until"],
    )
    return JSONResponse(content={"source": await knowledge_sources_repo.get_by_id(source_id)})


@router.post("/sources/{source_id}/retire")
async def retire_source(source_id: str) -> JSONResponse:
    """Soft-retire a source: excluded from Retrieval Test by default but not deleted."""
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await knowledge_sources_repo.set_lifecycle(source_id, "retired")
    return JSONResponse(content={"source": await knowledge_sources_repo.get_by_id(source_id)})


@router.post("/sources/{source_id}/reactivate")
async def reactivate_source(source_id: str) -> JSONResponse:
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await knowledge_sources_repo.set_lifecycle(source_id, "active")
    return JSONResponse(content={"source": await knowledge_sources_repo.get_by_id(source_id)})


# ── Config / Health ───────────────────────────────────────────────────────────

@router.get("/config")
async def get_knowledge_config() -> JSONResponse:
    """
    Real backend configuration — not a static UI claim. Used to surface a health
    banner instead of letting a user discover a missing OPENAI_API_KEY via a raw
    error after they've already tried to upload or search.
    """
    from app.services.embeddings import EMBEDDING_DIMENSIONS, LOCAL_MODEL_NAME, is_local_embeddings_available
    from app.services.claude_service import is_claude_configured
    from app.services.groq_service import is_groq_configured
    return JSONResponse(content={
        "embeddings_configured": is_embeddings_configured("openai"),
        "embedding_model": env.OPENAI_EMBEDDING_MODEL,
        "embedding_dimension": env.OPENAI_EMBEDDING_DIMENSION,
        "vector_store": "pgvector (HNSW, cosine)",
        "reranker": "hybrid lexical+vector (50% vector / 35% token overlap / 15% RRF)",
        "cost_per_1k_tokens_usd": env.OPENAI_EMBEDDING_COST_PER_1K,
        "local_embeddings_available": is_local_embeddings_available(),
        "local_embedding_model": LOCAL_MODEL_NAME,
        "local_embedding_dimension": EMBEDDING_DIMENSIONS["local_bge_small"],
        "text_to_sql_providers": {
            "anthropic": {"configured": is_claude_configured(), "model": env.ANTHROPIC_MODEL_MINIMAL},
            "groq": {"configured": is_groq_configured(), "model": env.GROQ_MODEL},
        },
    })


# ── Chunks preview ────────────────────────────────────────────────────────────

@router.get("/sources/{source_id}/chunks")
async def get_chunks(source_id: str, limit: int = 20) -> JSONResponse:
    source = await knowledge_sources_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    chunks = await knowledge_chunks_repo.get_preview(source_id, limit=min(limit, 100))
    return JSONResponse(content={"chunks": chunks, "total": source["chunk_count"]})


# ── Structured DB Schema & Direct SQL Query ───────────────────────────────────

@router.get("/sources/{source_id}/schema")
async def get_db_schema(source_id: str) -> JSONResponse:
    from app.services.sql_executor import get_database_schema
    try:
        schema_data = await get_database_schema(source_id)
        return JSONResponse(content=schema_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/{source_id}/query")
async def query_db_source(source_id: str, body: dict[str, Any]) -> JSONResponse:
    from app.services.sql_executor import execute_structured_query
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    try:
        result = await execute_structured_query(source_id, query)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/{source_id}/text-to-sql")
async def get_text_to_sql_prompt(source_id: str, body: dict[str, Any]) -> JSONResponse:

    from app.services.sql_executor import generate_sql_from_question
    question = body.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    try:
        result = await generate_sql_from_question(source_id, question)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sources/{source_id}/ask")
async def ask_structured_source(source_id: str, body: dict[str, Any]) -> JSONResponse:
    """
    The real end-to-end 'ask my data' flow: natural-language question -> schema-aware
    LLM-generated SQL -> executed read-only against the real source -> real rows back.
    Unlike /text-to-sql (which only returns the prompt), this actually answers the question.
    """
    from app.services.sql_executor import ask_question
    question = body.get("question", "").strip()
    llm_provider = body.get("llm_provider") or "anthropic"
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    try:
        result = await ask_question(source_id, question, llm_provider=llm_provider)
        return JSONResponse(content=result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))




# ── Pipeline Runs ─────────────────────────────────────────────────────────────

@router.get("/pipeline-runs")
async def list_pipeline_runs() -> JSONResponse:
    runs = await pipeline_runs_repo.get_all_runs()
    return JSONResponse(content={"runs": runs})


@router.get("/pipeline-runs/{run_id}")
async def get_pipeline_run(run_id: str) -> JSONResponse:
    run = await pipeline_runs_repo.get_run_with_stages(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return JSONResponse(content={"run": run})


# ── Retrieval Test ────────────────────────────────────────────────────────────

@router.post("/retrieve")
async def test_retrieval(body: dict[str, Any]) -> JSONResponse:
    """
    Test retrieval directly without going through an agent.
    Used by the Retrieval Test panel in the UI.
    """
    query = body.get("query", "").strip()
    source_ids = body.get("source_ids", [])
    top_k = min(int(body.get("top_k", 5)), 20)
    score_threshold = float(body.get("score_threshold", 0.0))
    rerank_enabled = bool(body.get("rerank_enabled", True))

    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if not source_ids:
        raise HTTPException(status_code=400, detail="source_ids is required")

    # A 1536-dim OpenAI vector and a 384-dim BGE vector are not comparable — every
    # selected source must share one embedding provider for the search to be valid.
    providers_by_source = await knowledge_sources_repo.get_embedding_providers(source_ids)
    distinct_providers = set(providers_by_source.values())
    if len(distinct_providers) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "Selected sources use different embedding providers "
                f"({', '.join(sorted(distinct_providers))}) — search sources embedded "
                "with the same provider together."
            ),
        )
    provider = next(iter(distinct_providers), "openai")

    if not is_embeddings_configured(provider):
        detail = "OPENAI_API_KEY not configured" if provider == "openai" else "Local embedding model not available on this server"
        raise HTTPException(status_code=503, detail=detail)

    from app.services.reranker import rerank_chunks

    started = time.perf_counter()

    fetch_k = max(top_k * 4, 20) if rerank_enabled else top_k
    try:
        query_embedding = await embed_text(query, provider=provider, is_query=True)
    except Exception as e:
        # Surface the real upstream error (rate limit, quota, network) instead of a bare 500.
        raise HTTPException(status_code=502, detail=f"Embedding request failed: {e}")
    rows = await knowledge_chunks_repo.search_by_source_ids(query_embedding, source_ids, fetch_k, provider=provider)

    candidates = [
        {
            "doc_id": r["doc_id"],
            "source_id": r["source_id"],
            "text": r["text"],
            "chunk_index": r["chunk_index"],
            "score": round(1 - r["distance"], 4),
            "distance": r["distance"],
            "passed": round(1 - r["distance"], 4) >= score_threshold,
        }
        for r in rows
    ]

    if rerank_enabled:
        results = rerank_chunks(query, candidates, top_k=top_k, score_threshold=score_threshold)
    else:
        results = [c for c in candidates if c["passed"]][:top_k]

    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    token_count: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        token_count = len(encoder.encode(query))
        if provider == "local_bge_small":
            estimated_cost_usd = 0.0  # on-CPU inference, no per-token API cost
        elif env.OPENAI_EMBEDDING_COST_PER_1K is not None:
            estimated_cost_usd = round((token_count / 1000) * env.OPENAI_EMBEDDING_COST_PER_1K, 8)
    except ImportError:
        pass  # tiktoken not installed — latency is still real, cost/token fields stay null

    hit_source_ids = list({r["source_id"] for r in results})
    await knowledge_sources_repo.touch_last_queried(hit_source_ids)

    return JSONResponse(content={
        "results": results,
        "query": query,
        "rerank_enabled": rerank_enabled,
        "latency_ms": latency_ms,
        "query_tokens": token_count,
        "estimated_cost_usd": estimated_cost_usd,
        "embedding_provider": provider,
    })


