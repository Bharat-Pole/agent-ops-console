"""Node handlers (Pass 5). One engine, all modes — every governance control
runs in test and deployed alike. Handlers are honest end to end:
- tool_call refuses write-class tools at EXECUTION time (invariant layer 3)
- implementation kind 'none' returns a labeled not-connected result
- guardrail FAILS CLOSED: any check error is a violation
- a missing provider/asset fails the node with the real reason, never a stub
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import TypedDict

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import policy
from ..adapters import vectors
from ..adapters.models import ModelAdapter, ModelCallError, ModelUnavailable
from ..assets import citations, ssrf
from ..assets.vault import resolve_secret
from ..models import (
    AssetStatus, PromptPack, PromptVersion, RagPipeline, ToolRecord, WorkflowRun,
)


class EngineState(TypedDict, total=False):
    user_input: str
    prompt_parts: list[str]
    retrieved: list[dict]        # [{n, source, location, text}]
    context_block: str
    tool_results: list[dict]
    llm_output: str
    final_output: str | dict
    citation_check: dict
    hitl_decision: dict


class NodeExecutionError(Exception):
    """Node failed for a real, reportable reason — the run fails honestly."""


# Tool params/args may reference run state so a tool can act on THIS request
# (e.g. a search tool needs the user's question). Deliberately a closed set of
# placeholders — no arbitrary expressions, no code execution.
_TEMPLATE_RE = re.compile(r"\{\{\s*(user_input|llm_output)\s*\}\}")


def render_template_values(value, state: "EngineState", used: list[str]):
    """Recursively substitute {{user_input}} / {{llm_output}} in strings."""
    if isinstance(value, str):
        def _sub(match: re.Match) -> str:
            name = match.group(1)
            used.append(name)
            return str(state.get(name, "") or "")
        return _TEMPLATE_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: render_template_values(v, state, used) for k, v in value.items()}
    if isinstance(value, list):
        return [render_template_values(v, state, used) for v in value]
    return value


@dataclass
class ExecCtx:
    db: Session
    adapter: ModelAdapter | None
    run: WorkflowRun
    risk_tier: str
    cost_rates: dict  # model_ref -> (cost_per_1k_in, cost_per_1k_out)
    usage: dict = field(default_factory=dict)  # filled by handlers per call


def _cost(ctx: ExecCtx, model_id: str, tokens_in: int, tokens_out: int) -> float:
    rate_in, rate_out = ctx.cost_rates.get(model_id, (0.0, 0.0))
    return (tokens_in / 1000.0) * rate_in + (tokens_out / 1000.0) * rate_out


# ---- handlers ---------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def extract_response(payload: str, spec: dict) -> tuple[str | None, str | None]:
    """Turn an API's JSON body into text a model can actually use.

    Declarative and data-only (no expressions, no code): `path` walks dotted
    keys, `fields` selects what to render per item. Raw provider JSON fed
    straight to an LLM is both wasteful and destabilising — Gemini answers
    `MALFORMED_FUNCTION_CALL` on some API payloads — so tools declare their
    shape once, here. Returns (text, error): on failure the caller keeps the
    raw body and records the reason. Nothing is ever silently dropped.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, f"response is not JSON ({exc})"

    node = data
    for key in [p for p in str(spec.get("path", "")).split(".") if p]:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return None, f"path segment {key!r} not found in response"

    items = node if isinstance(node, list) else [node]
    if isinstance(node, list) and not node:
        # "the API found nothing" is a RESULT, not a misconfiguration — say
        # which it is so nobody debugs their extract spec for an empty search
        return None, "the API returned zero results for this query"
    limit = int(spec.get("limit", 10))
    fields = spec.get("fields") or []
    strip_html = bool(spec.get("strip_html", True))

    lines: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            selected = {k: item.get(k) for k in fields} if fields else item
            parts = [f"{k}: {v}" for k, v in selected.items() if v not in (None, "")]
            rendered = "\n  ".join(parts)
        else:
            rendered = str(item)
        if strip_html:
            rendered = _HTML_TAG_RE.sub("", rendered)
        if rendered.strip():
            lines.append(f"- {rendered}")
    if not lines:
        return None, "extraction produced no content"
    return "\n".join(lines), None


def run_rag(state: EngineState, config: dict, ctx: ExecCtx) -> tuple[dict, dict]:
    pipeline = ctx.db.scalars(select(RagPipeline).where(
        RagPipeline.name == config.get("pipeline"))).first()
    if pipeline is None:
        raise NodeExecutionError(f"rag pipeline {config.get('pipeline')!r} not found")
    query = state.get("user_input", "")
    source_ids = [uuid.UUID(s) for s in pipeline.source_ids]

    # Both searchers contribute a WIDER pool than top_k so that fusion and the
    # diversity pass have candidates to choose between; the pool is narrowed to
    # top_k only at the end.
    pool = max(pipeline.top_k, pipeline.top_k * vectors.CANDIDATE_MULTIPLIER)

    vector_hits: list[vectors.ChunkHit] = []
    embeddings_available = False
    if ctx.adapter is not None:
        try:
            qvec = ctx.adapter.embed([query])[0]
            vector_hits = vectors.vector_search(ctx.db, qvec, source_ids,
                                                pool, pipeline.score_threshold)
            embeddings_available = True
        except (ModelUnavailable, ModelCallError):
            embeddings_available = False
    keyword_hits = vectors.keyword_search(ctx.db, query, source_ids, pool)

    # mode reports what actually contributed. The previous label claimed
    # "hybrid" whenever an embedding call succeeded, even though the merge
    # discarded every keyword hit unless vector search underfilled.
    if vector_hits and keyword_hits:
        mode = "hybrid"
    elif vector_hits:
        mode = "vector_only"
    elif keyword_hits:
        mode = "keyword_only" if embeddings_available else "keyword_fallback"
    else:
        mode = "no_matches"

    hits = vectors.diversify(vectors.fuse({"vector": vector_hits, "keyword": keyword_hits}),
                             pipeline.top_k)

    from ..models import KnowledgeSource
    names = {s.id: s.name for s in ctx.db.scalars(
        select(KnowledgeSource).where(KnowledgeSource.id.in_(source_ids))).all()}
    triples = [(names.get(h.chunk.source_id, "?"),
                (h.chunk.meta or {}).get("location", "?"), h.chunk.text) for h in hits]
    context_block, source_map = citations.wrap_chunks(triples)
    retrieved = [{"n": e.n, "source": e.name, "location": e.location, "text": e.text}
                 for e in source_map]
    span = {"mode": mode, "chunks": len(retrieved), "pipeline": pipeline.name,
            "score_threshold": pipeline.score_threshold,
            "candidates": {"vector": len(vector_hits), "keyword": len(keyword_hits)},
            # how many of the pipeline's sources are actually represented — the
            # number to look at when an answer misses a document
            "sources_represented": len({h.chunk.source_id for h in hits}),
            "sources_configured": len(source_ids)}
    return {"retrieved": retrieved, "context_block": context_block}, span


def run_prompt(state: EngineState, config: dict, ctx: ExecCtx) -> tuple[dict, dict]:
    # deployment manifests pin exact content — the snapshot boundary
    if config.get("pinned_content") is not None:
        parts = list(state.get("prompt_parts", []))
        parts.append(str(config["pinned_content"]))
        return ({"prompt_parts": parts},
                {"pack": config.get("pack_ref"), "pinned_version": config.get("pinned_version"),
                 "pinned": True, "chars": len(str(config["pinned_content"]))})
    ref = config.get("pack_ref")
    pack = ctx.db.scalars(select(PromptPack).where(PromptPack.slug == ref)).first()
    approved = pack and ctx.db.scalars(select(PromptVersion).where(
        PromptVersion.pack_id == pack.id, PromptVersion.status == AssetStatus.approved)
        .order_by(PromptVersion.version.desc())).first()
    if not approved:
        raise NodeExecutionError(f"prompt pack {ref!r} has no APPROVED version")
    parts = list(state.get("prompt_parts", []))
    parts.append(approved.content)
    return ({"prompt_parts": parts},
            {"pack": ref, "version": approved.version, "chars": len(approved.content)})


def render_tool_results(results: list[dict]) -> str:
    """Readable blocks, not nested JSON. Refusals and not-connected stubs are
    stated in words so the model can say so rather than invent around them."""
    blocks: list[str] = []
    for result in results:
        name = result.get("tool", "tool")
        if result.get("refused"):
            blocks.append(f"--- {name}: REFUSED BY POLICY ---\n"
                          + "; ".join(result.get("reasons") or []))
        elif result.get("connected") is False:
            blocks.append(f"--- {name}: NOT CONNECTED ---\n{result.get('note', '')}")
        elif result.get("extracted"):
            blocks.append(f"--- {name} (results) ---\n{result['extracted'][:4000]}")
        elif result.get("content"):
            blocks.append(f"--- {name} ---\n{str(result['content'])[:4000]}")
        else:
            body = str(result.get("body_preview", ""))[:4000]
            note = f" [extraction failed: {result['extract_error']}]" if result.get("extract_error") else ""
            blocks.append(f"--- {name} (raw response{note}) ---\n{body}")
    return "\n\n".join(blocks)


_CITATION_INSTRUCTION = (
    "Ground your answer in the provided sources and cite them inline as [Source N]. "
    "Only cite source numbers that appear in the context. If the context does not "
    "cover the question, say so explicitly."
)


def run_llm(state: EngineState, config: dict, ctx: ExecCtx) -> tuple[dict, dict]:
    if ctx.adapter is None:
        raise NodeExecutionError("no model provider configured (PLATFORM_LLM_PROVIDER)")
    clamps = policy.model_clamps(ctx.risk_tier)
    temperature = min(float(config.get("temperature", 0.2)), clamps["max_temperature"])

    system_parts = list(state.get("prompt_parts", []))
    # Per-node instruction: without this every LLM node in a flow would share
    # one system prompt, which makes multi-step flows (derive a query → call a
    # tool → answer) impossible to express.
    instruction = str(config.get("instruction") or "").strip()
    if instruction:
        system_parts.append(instruction)
    if state.get("retrieved"):
        system_parts.append(_CITATION_INSTRUCTION)
    system = "\n\n".join(system_parts) or "You are a helpful, honest enterprise assistant."

    user_parts = [state.get("user_input", "")]
    if state.get("context_block"):
        user_parts.append("CONTEXT:\n" + state["context_block"])
    # a node can opt out of prior tool output — the query-derivation step must
    # not see results it is supposed to be fetching
    if state.get("tool_results") and not config.get("ignore_tool_results"):
        user_parts.append("TOOL RESULTS:\n" + render_tool_results(state["tool_results"]))

    try:
        result = ctx.adapter.generate(system, "\n\n".join(p for p in user_parts if p),
                                      temperature=temperature,
                                      max_tokens=clamps["max_tokens"])
    except (ModelUnavailable, ModelCallError) as exc:
        raise NodeExecutionError(f"model call failed: {exc}") from exc

    span = {"model_id": result.model_id, "temperature": temperature,
            "clamps": clamps, "tokens_in": result.tokens_in, "tokens_out": result.tokens_out,
            "cost": _cost(ctx, result.model_id, result.tokens_in, result.tokens_out)}
    if instruction:
        span["instruction"] = instruction[:200]
    source = getattr(ctx.adapter, "credential_source", None)
    if source:
        span["credential_source"] = source  # secret NAME or "env:…", never a value
    return {"llm_output": result.text.strip()}, span


def run_tool_call(state: EngineState, config: dict, ctx: ExecCtx) -> tuple[dict, dict]:
    ref = config.get("tool_ref")
    if not ref:
        raise NodeExecutionError(
            "tool node is a described need (no tool_ref) — register and reference a real tool")
    if config.get("pinned_tool_id"):
        # manifest pin: this exact version — the runtime policy check below
        # STILL applies (the write invariant survives the snapshot)
        tool = ctx.db.get(ToolRecord, uuid.UUID(str(config["pinned_tool_id"])))
        if tool is None:
            raise NodeExecutionError(f"pinned tool {config['pinned_tool_id']} no longer exists")
    else:
        tool = ctx.db.scalars(select(ToolRecord).where(
            ToolRecord.slug == ref, ToolRecord.status == AssetStatus.approved)
            .order_by(ToolRecord.version.desc())).first()
        if tool is None:
            raise NodeExecutionError(f"no APPROVED tool with slug {ref!r}")

    decision = policy.can_execute_tool(tool)
    if not decision.allowed:
        # refusal is a RESULT, not an exception: the run continues advisorily,
        # and the span proves the invariant held
        result = {"tool": ref, "refused": True, "reasons": decision.reasons}
        return ({"tool_results": state.get("tool_results", []) + [result]},
                {"tool": ref, "refused": True, "policy": decision.reasons,
                 "permission_type": tool.permission_type.value,
                 "rules_version": decision.rules_version})

    impl = tool.implementation or {}
    kind = impl.get("kind")
    placeholders: list[str] = []
    extract_note: str | None = None
    if kind == "none":
        result = {"tool": ref, "connected": False,
                  "note": "tool has implementation 'none' — honest not-connected stub"}
    elif kind == "http_api":
        url = (impl.get("config") or {}).get("base_url")
        if not url:
            raise NodeExecutionError(f"tool {ref!r}: implementation.config.base_url missing")
        allowed, reason = ssrf.check_url(url)
        if not allowed:
            raise NodeExecutionError(f"tool {ref!r}: SSRF guard denied target ({reason})")
        # static headers from PERSISTED config (e.g. User-Agent, Accept).
        # Auth headers are applied after, so config can never spoof a credential.
        headers: dict[str, str] = {
            str(k): str(v) for k, v in ((impl.get("config") or {}).get("headers") or {}).items()
        }
        auth = tool.auth or {}
        if auth.get("method") in ("api_key_header", "bearer"):
            secret = resolve_secret(ctx.db, auth.get("credential_ref") or "")
            if secret is None:
                raise NodeExecutionError(f"tool {ref!r}: credential {auth.get('credential_ref')!r} not in vault")
            if auth["method"] == "bearer":
                headers["Authorization"] = f"Bearer {secret}"
            else:
                headers[auth.get("header_name") or "X-API-Key"] = secret
        params = render_template_values(config.get("params") or {}, state, placeholders)
        try:
            response = httpx.get(url, params=params, headers=headers,
                                 timeout=min(tool.timeout_seconds, 30), follow_redirects=False)
            if response.status_code >= 400:
                # a broken API must not look like a successful step: an agent
                # answering "around" a 403 is worse than a failed run
                raise NodeExecutionError(
                    f"tool {ref!r}: HTTP {response.status_code} from {httpx.URL(url).host} "
                    f"— {response.text[:300]}")
            result = {"tool": ref, "status_code": response.status_code}
            spec = config.get("response_extract") or (impl.get("config") or {}).get("response_extract")
            if spec:
                text, err = extract_response(response.text, spec)
                if text is not None:
                    result["extracted"] = text
                else:
                    # extraction failed — say so and keep the raw body
                    result["extract_error"] = err
                    result["body_preview"] = response.text[:4000]
                    extract_note = err
            else:
                result["body_preview"] = response.text[:4000]
        except httpx.HTTPError as exc:
            raise NodeExecutionError(f"tool {ref!r}: outbound call failed: {exc}") from exc
    elif kind == "mcp":
        args = render_template_values(config.get("args") or {}, state, placeholders)
        result = _call_mcp_tool(ctx.db, tool, args)
    else:
        raise NodeExecutionError(f"tool {ref!r}: implementation kind {kind!r} not executable")

    span = {"tool": ref, "implementation": kind, "refused": False,
            "permission_type": tool.permission_type.value,
            "state_placeholders": sorted(set(placeholders))}
    if extract_note:
        span["extract_error"] = extract_note
    return ({"tool_results": state.get("tool_results", []) + [result]}, span)


def _call_mcp_tool(db: Session, tool: ToolRecord, args: dict) -> dict:
    import asyncio

    from ..models import McpConnector
    connector_id = (tool.implementation.get("config") or {}).get("connector_id")
    tool_name = (tool.implementation.get("config") or {}).get("tool_name")
    conn = db.get(McpConnector, uuid.UUID(connector_id)) if connector_id else None
    if conn is None or conn.status != "active":
        raise NodeExecutionError(f"tool {tool.slug!r}: MCP connector unavailable")
    if (conn.health or {}).get("consecutive_failures", 0) >= 3:
        raise NodeExecutionError(
            f"tool {tool.slug!r}: connector {conn.name!r} is unhealthy — short-circuited")
    allowed, reason = ssrf.check_url(conn.endpoint)
    if not allowed:
        raise NodeExecutionError(f"connector endpoint denied: {reason}")

    headers: dict[str, str] = {}
    ref = (conn.auth or {}).get("credential_ref")
    if ref:
        secret = resolve_secret(db, ref)
        if secret is None:
            raise NodeExecutionError(f"connector credential {ref!r} not in vault")
        headers[(conn.auth or {}).get("header_name") or "Authorization"] = secret

    async def _run() -> dict:
        from mcp import ClientSession

        # shared with discovery so both speak the same SDK dialect (see
        # assets.mcp.open_transport — the v1/v2 client rename lives there)
        from ..assets.mcp import open_transport, sdk_attr
        async with open_transport(conn.endpoint, conn.transport, headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=args)
                texts = [c.text for c in result.content if getattr(c, "text", None)]
                return {"tool": tool.slug, "mcp_tool": tool_name,
                        "is_error": bool(sdk_attr(result, "is_error", "isError", default=False)),
                        "content": "\n".join(texts)[:2000]}

    try:
        return asyncio.run(asyncio.wait_for(_run(), timeout=30))
    except NodeExecutionError:
        raise
    except Exception as exc:
        from ..assets.mcp import explain_exc
        raise NodeExecutionError(f"MCP call failed: {explain_exc(exc)}") from exc


def run_guardrail(state: EngineState, config: dict, ctx: ExecCtx) -> tuple[dict, dict]:
    """FAILS CLOSED (spec §3.5): any violation or check error stops the run."""
    violations: list[str] = []
    try:
        output = str(state.get("llm_output", ""))
        if not output.strip():
            violations.append("empty model output")
        source_map = [citations.SourceEntry(n=r["n"], name=r["source"],
                                            location=r["location"], text=r["text"])
                      for r in state.get("retrieved", [])]
        # unconditional: citing sources that were never provided is fabrication,
        # whether or not any context was retrieved
        check = citations.check_citations(output, source_map)
        if not check.get("ok", False):
            violations.append(f"invalid citations: {check.get('invalid')} do not exist in the provided context")
        for topic in config.get("blocked_topics", []):
            if re.search(rf"\b{re.escape(str(topic).lower())}\b", output.lower()):
                violations.append(f"blocked topic {topic!r} present in output")
    except Exception as exc:  # fail closed — a broken check is a violation
        violations.append(f"guardrail check error (fails closed): {exc}")
        check = {"ok": False}

    if violations:
        raise NodeExecutionError("guardrail violation: " + "; ".join(violations))
    return {"citation_check": check}, {"checks": ["output_nonempty", "citations", "blocked_topics"],
                                       "citation_check": check}


def run_output_format(state: EngineState, config: dict, ctx: ExecCtx) -> tuple[dict, dict]:
    fmt = config.get("format", "text")
    output = str(state.get("llm_output", ""))
    if fmt == "structured_json":
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", output.strip())
        try:
            return {"final_output": json.loads(cleaned)}, {"format": fmt, "parsed": True}
        except json.JSONDecodeError as exc:
            raise NodeExecutionError(f"output is not valid JSON ({exc}) — structured_json contract violated")
    return {"final_output": output}, {"format": fmt, "chars": len(output)}


HANDLERS = {
    "rag": run_rag,
    "prompt": run_prompt,
    "llm": run_llm,
    "tool_call": run_tool_call,
    "mcp_call": run_tool_call,  # same executor; the tool's implementation decides
    "guardrail": run_guardrail,
    "output_format": run_output_format,
    # human_approval is special-cased in the runner (interrupt machinery)
}
