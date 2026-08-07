"""FastAPI engine service — the console calls this to turn an AgentRecord into a
runnable LangGraph project.

  uvicorn service.app:app --port 8099 --reload      (run from engine/)

Endpoint names mirror the console's kernel/api.ts / services.ts façade:
  GET  /v1/health
  POST /v1/agents/validate   -> { topology, blockers, file_tree }
  POST /v1/agents/generate   -> { topology, blockers, file_tree, preview, artifact_b64, filename }
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# allow `import agent_forge` when running from the engine/ dir
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_forge import generate  # noqa: E402
from agent_forge.loader import load_agent  # noqa: E402
from agent_forge.dispatch import dispatch  # noqa: E402
from agent_forge.validator import build_blockers  # noqa: E402
from agent_forge.runtime import run_agent  # noqa: E402
from agent_forge.architecture_reco import recommend_architecture, NoKeyError  # noqa: E402
from agent_forge import secrets as vault  # noqa: E402

app = FastAPI(title="agent_forge engine", version="0.1.0")

# Dev CORS — the console runs on a different origin (Vite :5173).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PREVIEW_BASENAMES = ("graph.py", "tools.py", "prompts.py", "README.md", "requirements.txt")


class GenRequest(BaseModel):
    agent: dict[str, Any]            # the console AgentRecord export
    llm_target: str = "aistudio"     # aistudio | vertex
    tools: list[dict[str, Any]] = []  # executable tool defs (names-only auth)


class RunRequest(BaseModel):
    agent: dict[str, Any]
    message: str
    thread_id: str = "default"
    llm_target: str = "aistudio"
    knowledge_snippets: list[dict[str, str]] = []   # {doc_id, text} for real RAG
    tools: list[dict[str, Any]] = []                # executable tool defs (names-only auth)
    api_key: str | None = None                      # UI-provided Gemini key (beats env)


@app.get("/v1/health")
def health():
    import os
    has_env = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    return {
        "status": "ok",
        "service": "agent_forge",
        "version": app.version,
        "has_env_key": has_env,  # back-compat
        "secret_names": vault.list_names(),  # names only — never values
        "has_default_key": has_env or bool(vault.get(vault.DEFAULT_MODEL_SECRET)),
        # opt-in Claude runtime available? (ANTHROPIC_DEFAULT vault secret or env)
        "has_anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY") or vault.get(vault.ANTHROPIC_DEFAULT_SECRET)),
    }


# ---- secrets vault (names in, names out — values never returned) ----
class SecretPut(BaseModel):
    value: str


@app.get("/v1/secrets")
def secrets_list():
    return {"names": vault.list_names()}


@app.put("/v1/secrets/{name}")
def secrets_put(name: str, body: SecretPut):
    if not vault.valid_name(name):
        raise HTTPException(status_code=400, detail="invalid secret name (use letters/digits/_ , start with a letter)")
    if not body.value.strip():
        raise HTTPException(status_code=400, detail="secret value must be non-empty")
    vault.put(name, body.value.strip())
    return {"ok": True, "names": vault.list_names()}


@app.delete("/v1/secrets/{name}")
def secrets_delete(name: str):
    removed = vault.delete(name)
    return {"ok": removed, "names": vault.list_names()}


# ---- ad-hoc tool test (wizard "Try it") — GET only, never echoes the auth header ----
class ToolTryRequest(BaseModel):
    tool: dict[str, Any]
    query: str = ""


@app.post("/v1/tools/try")
def tool_try(req: ToolTryRequest):
    from agent_forge.tools_lib import try_http_tool
    return try_http_tool(req.tool, req.query)


class ArchRecoRequest(BaseModel):
    intent: dict[str, Any]
    nlu: dict[str, Any] = {}
    classification: dict[str, Any] = {}
    allowed_architectures: list[str] = []
    bound_tools: list[str] = []
    llm_target: str = "aistudio"
    api_key: str | None = None


@app.post("/v1/architecture/recommend")
def architecture_recommend(req: ArchRecoRequest):
    """LLM-first Stage-2b architecture recommendation. Returns
    { architecture, graph_spec, rationale, confidence }. The console re-validates
    the result with its own deterministic guardrails and falls back to its
    rule-based baseline on any non-200 (503 = no key, 502 = model error)."""
    try:
        return recommend_architecture(req.model_dump(), api_key=req.api_key or None, llm_target=req.llm_target)
    except NoKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # model/network/parse error
        raise HTTPException(status_code=502, detail=f"recommender error: {type(e).__name__}: {e}"[:300])


@app.post("/v1/agents/validate")
def validate(req: GenRequest):
    record = {**req.agent, "_bound_tool_defs": req.tools}
    agent = load_agent(record, llm_target=req.llm_target)
    topo = dispatch(agent)
    blockers = build_blockers(agent)
    # a dry file tree without rendering the whole project
    res = generate(agent)  # generate is cheap/deterministic; reuse for the tree
    return {"topology": topo.value, "blockers": blockers, "file_tree": res.tree}


@app.post("/v1/agents/generate")
def generate_project(req: GenRequest):
    record = {**req.agent, "_bound_tool_defs": req.tools}
    res = generate(record, llm_target=req.llm_target)
    preview = {
        path: content
        for path, content in res.files.items()
        if path.rsplit("/", 1)[-1] in PREVIEW_BASENAMES
    }
    return {
        "topology": res.topology.value,
        "blockers": res.blockers,
        "file_tree": res.tree,
        "preview": preview,
        "filename": f"{res.agent.slug}.zip",
        "artifact_b64": base64.b64encode(res.zip_bytes()).decode("ascii"),
    }


@app.post("/v1/agents/run")
def run(req: RunRequest):
    """Build + run the REAL agent graph and return its reply (+ a small trace).
    Needs a GOOGLE_API_KEY in the service environment. Errors are returned inline
    (200 with `error`) so the console can show them and fall back gracefully."""
    record = {**req.agent, "_knowledge_snippets": req.knowledge_snippets, "_bound_tool_defs": req.tools}
    try:
        out = run_agent(record, req.message, thread_id=req.thread_id,
                        llm_target=req.llm_target, api_key=req.api_key or None)
        return {"reply": out["reply"], "trace": out["trace"], "error": None}
    except Exception as e:  # missing key, quota, model error, etc.
        return {"reply": "", "trace": {}, "error": f"{type(e).__name__}: {e}"[:400]}
