# agent_forge — spec → code engine

Turns a Brightspeed **agent-ops-console** canonical `AgentRecord` export into a
**runnable LangGraph Python project**. The deterministic mirror of `agent_onboard`
(which does code → spec): **no LLM is used to generate code** — templates only. The
*generated* agent uses Gemini at runtime.

## Topologies (config → generated shape)

| config | generated topology |
|---|---|
| `orchestration_type == coordinator+subagents` (+ sub-agents) | **supervisor** — hand-written supervisor routes to one `create_react_agent` sub-graph per sub-agent via `Command(goto)` |
| explicit `orchestration.graph`, or `orchestration_type == router` | **dag** — explicit `StateGraph` of nodes/edges |
| `rag_enabled` | **dag** — derived RAG `retrieve → generate` |
| else (`single`) | **single** — dynamic ReAct tool loop (`create_react_agent`) |

**Advisory-only scope is LOCKED:** only read/summarize/draft/recommend/validate tools
are bound. Write-capable / `review_card.flagged_write_tools` are emitted **disabled**
(raise `PermissionError`) and never bound. HITL gate placements are mapped to LangGraph
`interrupt_before` where a node target resolves; lifecycle gates (e.g. `pre-deploy`)
become README human-process notes.

## Setup

```bash
python -m venv .venv && ./.venv/Scripts/python -m pip install jinja2 pytest \
  "langgraph>=0.2.62,<0.3" "langchain-core>=0.3,<0.4" "langchain-google-genai>=2,<3" \
  fastapi uvicorn pydantic
```

## CLI

```bash
python -m agent_forge <AgentRecord.json> --out dist/ [--zip] [--llm-target=aistudio|vertex]
```

Generates a full project under `dist/<agent-slug>/`: `pyproject.toml` + pinned
`requirements.txt`, `src/<pkg>/{model,prompts,tools,graph,memory}.py`, a
`runtime/{cli,server}.py` (CLI + FastAPI `/converse`), optional `rag/`
(pure-Python `InMemoryVectorStore`, no native deps), `tests/` (no-key compile +
advisory-guard), README, and the source config embedded at `config/agent.config.json`.

Determinism: identical input → **byte-identical** zip.

## Service (used by the console)

```bash
uvicorn service.app:app --port 8099
```

- `GET  /v1/health`
- `POST /v1/agents/validate` → `{ topology, blockers, file_tree }`
- `POST /v1/agents/generate` → `{ topology, blockers, file_tree, preview, filename, artifact_b64 }`
- `POST /v1/architecture/recommend` → `{ architecture, graph_spec, rationale, confidence }`

The console (Onboarding Phase 7 · Deploy, and each agent's Registry → Deployment tab)
calls **generate** via **Generate runnable project**; set `VITE_ENGINE_URL` (default
`http://localhost:8099`). It degrades gracefully with a toast when the service is down.

### Architecture recommender (LLM-first, Stage 2b)

`POST /v1/architecture/recommend` takes `{ intent, nlu, classification, allowed_architectures, bound_tools }`
and asks Gemini (`with_structured_output`, model = `ARCHITECTURE_MODEL` env, default
`gemini-3.6-flash`) to pick one **generatable** shape — `single`, `sequential_pipeline`,
`hub_and_spoke`, `graph`. `graph_spec` is returned `null` on purpose: the console renders
the concrete graph deterministically for the chosen kind. The console re-validates every
result with its own guardrails (`validateArchitecture`) and **falls back to its rule-based
baseline** on any non-200 — `503` = no Gemini key, `502` = model/parse error. The LLM is
never trusted blindly, and the wizard proposal still works with the service offline.

## Tests

```bash
python -m pytest agent_forge/tests -q      # engine: dispatch, file set, determinism, guardrail, HITL, blockers
# generated-project no-key compile:
(cd dist/<slug> && python -m pytest -q)    # build_graph(FakeChatModel()) compiles; write tools disabled
```

## SDK target

`--llm-target=aistudio` (default) emits `ChatGoogleGenerativeAI` (`GOOGLE_API_KEY`,
`vertex://` prefix stripped). `--llm-target=vertex` emits `ChatVertexAI`
(`langchain-google-vertexai`, `GOOGLE_CLOUD_PROJECT` + ADC).
