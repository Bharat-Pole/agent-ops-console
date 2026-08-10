# Architecture — Agent Ops & Governance Console

This document is the deep-dive companion to `README.md` (product framing, demo
script) and `CLAUDE.md` (session conventions + current status). It exists so a
new contributor — human or Claude — can understand *how the system is built*
without re-deriving it from scratch.

## 0. Scope — this is a local POC, and the boundary is deliberate

**Everything below describes a proof of concept that runs on one machine.** The
boundary is not accidental, and knowing where it sits is the difference between
reading this document correctly and overestimating the system.

**The governing rule:** *never simulate the thing being demonstrated; simulate
only what sits on the far side of it.* Our half of every interaction — the data
model, the governance checks, the persistence, the audit writer, the MCP client
— is real code that would not change when a production endpoint replaces a local
one. What may be local is the **counterparty**: whether a conformant MCP server
answers on `localhost` or at a vendor's URL changes an endpoint and an auth mode,
not the protocol code that talks to it.

This yields a test you can apply to any part of the system: **a fake healthcheck
that always returns green is dishonest, because health is the thing being shown.
A local MCP server answering a genuine `tools/list` is not, because the exchange
is real and the server is merely nearby.**

| | Status in the POC |
|---|---|
| Data model, governance rules, persistence | **Real.** Enforced server-side, re-validated independently of client input |
| MCP protocol code (client, discovery, health probing) | **Real.** Spec revision 2026-07-28 via the official SDK |
| Counterparty MCP servers | **Local.** A reference server under `backend/reference_mcp/` |
| Business data behind those servers | **Synthetic.** No real customer or client data, by design |
| Identity | **Enforcement real, principal simulated** — persona switcher, not an IdP |
| Auth layer, CORS, network perimeter | **Absent.** Deployment-layer concern; localhost only |
| Model layer | **Stand-in.** Not the engagement's approved stack |

Two consequences worth carrying:

1. **The seam must stay a single, obvious, swappable boundary** — one endpoint,
   one auth mode, one transport. If POC-only assumptions leak past it into the
   client or the gateway, the "implementation-ready" claim stops being true, and
   that is the only promise this codebase actually makes.
2. **Simulated parts must stay labelled in the UI and in the data**, never
   silently indistinguishable from real ones. A connector with a real endpoint
   and one without must not display identical evidence of health.

## 1. The big picture

This is a **hybrid** app: a fully-featured client-side simulation that is
gradually growing real backend persistence around its edges.

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  React SPA (Vite, :5173)    │  /v1/*  │  FastAPI backend (:8787)     │
│  Zustand store = "kernel"   │ ──────▶ │  dict-in/dict-out routes     │
│  seeded from src/seed/*.ts  │ ◀────── │  repositories → Postgres     │
└─────────────────────────────┘  proxy  └──────────────────────────────┘
                                              │
                                              ▼
                                     Postgres 16 + pgvector
                                     (docker-compose, port 5434 — see §6)
```

**Most of the app's data never leaves the browser.** `src/seed/*.ts` seeds a
Zustand store (`src/kernel/store.ts`) with agents, tools, connectors, prompts,
knowledge sources, eval packs, etc. Most mutations (provisioning animations,
pipeline runs, telemetry, eval scoring) are deterministic client-side
simulations driven by a seeded `mulberry32` PRNG — there is no server
round-trip at all for most of the app's day-to-day interactions.

A **subset of entities** has been (and is being) moved to real backend
persistence, one vertical slice at a time. As of now, those are:
**agents, approvals, audit log, eval packs, tools, and MCP connectors**
(tools joined in the tool-authoring session — §7; connectors joined in the
MCP session — §8). Everything else (knowledge sources, prompts, onboarding
drafts, jobs/telemetry) is still purely client-side.

Connectors had to follow tools rather than stay client-side, because **tool
status is derived from connector health**. With tools in Postgres and
connectors in browser memory, a connector going offline could not durably
affect the tools it serves — the catalog's `status` column would drift from
the connectors tab and reset on refresh. See §8.

This split is visible in two places:
- `src/kernel/store.ts` → `hydrateFromServer()` — only overwrites the
  server-owned slices; everything else keeps its local-seed value.
- `src/App.tsx` → calls `api.bootstrapWorkspace()` (`GET /v1/bootstrap`) once
  on load. The client keeps its local seed data until this resolves — **there
  is no loading gate**, so the UI is always immediately interactive, then
  quietly reconciles with server truth.

## 2. Frontend layout (`src/`)

```
types/       canonical schema: 13 config groups + Prov<T> provenance envelope + entities
kernel/      store (Zustand) · api.ts/services.ts façade · jobs · rng · telemetry
  engine/    7-stage deterministic synthesis engine (nlu, signals, templates, writeDetect, …)
seed/        static seed data — the ONLY source of truth for client-only entities
components/  primitives (Button, Modal, Drawer, DataTable, …) · domain · shell
modules/     one folder per left-nav item (home, registry, onboarding, tools, …)
```

### `kernel/api.ts` + `kernel/services.ts` — the façade

`api.ts` is a thin re-export of `services.ts` functions — it exists so
components never import `services.ts` directly, and so the whole surface is
visible in one file. **Every new backend-calling function should be added to
`services.ts` and re-exported through `api.ts`**, following the existing
naming (`createTool`, `bindTool`, `register`, …).

`services.ts` has exactly one low-level HTTP helper, `postJson()`, and one
convention, used by *every* server call:
```ts
const { ok, data } = await postJson<ResponseShape>(path, body);
if (!ok || !data) { store.pushToast('err', 'Could not reach the server — X failed.'); return fallback; }
if (!data.ok /* or a message field */) { store.pushToast('err', data.message ?? '...'); return fallback; }
// success: patch the store from the SERVER's returned canonical object,
// never optimistically — the server response is the source of truth.
store.patchX(...) / store.addX(...);
store.pushToast('ok'|'info', '...');
```

### Two different "this takes time" UX patterns — don't mix them

This distinction matters and is easy to get wrong:

1. **`kernel/jobs.ts` (`startJob`/`startSimpleJob`)** — a client-only
   simulated job queue. It walks a fixed `setTimeout` duration (e.g.
   `latency(600, 1400)`ms from the seeded RNG) and then synchronously calls
   `onComplete`. It has **no concept of awaiting a real network promise**.
   Used for: healthcheck, provisioning animations, pipeline runs, the
   onboarding "synthesis" (which is itself 100% local rule-based logic, not a
   real AI call, despite the ✨ Sparkles icon).
2. **A plain local `useState` boolean around an `await api.someRealCall()`**
   — used by every call that hits a *real* backend endpoint with genuine
   variable latency: `register()`, `chatWithAgent()` (Playground), and now
   `createTool()`/`suggestTool()`. See `Phase3Register.tsx` or
   `PlaygroundPage.tsx` for the pattern.

**Rule of thumb: if it's a real `fetch` to the FastAPI backend, use pattern 2.
Only use `jobs.ts` for purely-simulated, fixed-duration client animations.**

### No shared form-input primitives

There's no `Input`/`Textarea`/`Select` component. Every form (onboarding
phases, the tool-creation modal) uses raw `<input>`/`<textarea>`/`<select>`
styled with the same repeated Tailwind string:
```
className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring"
```
`TagInput` (`src/modules/onboarding/TagInput.tsx`) is the one reusable
input — a chip-list editor for `string[]` fields. It's been reused outside
onboarding (tool schema editor) by importing it directly; it isn't in
`components/primitives` even though it probably should be one day.

`Modal` vs `Drawer` (both in `components/primitives`): `Modal` is a centered
dialog with a `footer` slot — use it for action/create forms. `Drawer` is a
right-side slide-over — this codebase's convention is to reserve it for
**read-only detail views** (e.g. clicking a table row).

## 3. Backend layout (`backend/app/`)

```
main.py          FastAPI app, lifespan (connect→migrate→seed→scheduler), router registration
routes/          thin HTTP layer — dict-in/dict-out, no Pydantic models anywhere
services/        business logic — the actual trust boundary + audit logging
repositories/    raw asyncpg queries, one module per table
db/
  connection.py  pool + JSONB type codec registration
  migrate.py     ONE big idempotent DDL string — no migration framework
  seed.py        seeds from seed_data/seed_snapshot.json only if tables are empty
seed_data/       snapshot.py loads seed_snapshot.json (mirrors src/seed/*.ts by hand)
```

### Route conventions (every route follows this — match it exactly for new ones)

- **dict-in/dict-out**: `async def handler(body: dict[str, Any]) -> JSONResponse`.
  No Pydantic request/response models exist anywhere in this codebase.
- **Error shape is always `{"message": "<string>"}`** — the frontend's
  `postJson` callers read `data.message` for toasts, so any new endpoint must
  follow this exactly or the UI silently shows a generic error.
- **Status codes**: `201` create success, `200` default success, `400`
  validation/domain failure, `404` entity not found, `503` external service
  not configured (e.g. `is_claude_configured()` guard — see `chat.py`,
  `tools.py`), `502` upstream call failed (Claude error, JSON parse failure).
- Every mutating action writes an **audit event** via `audit_repo.insert()`
  (`id: f"aud-{uuid.uuid4()}"`, `actor_persona`, `action`, `entity_type`,
  `entity_id`, `detail`) and returns it in the response so the frontend can
  `store.addAuditEvent(...)` immediately without a refetch.

### The governance trust boundary (the single most important invariant)

The whole product's premise is: **agents are advisory-only.** `ToolPermission`
is a **locked 5-value enum** (`read | summarize | draft | recommend |
validate`) — `write` is not a member of that type at all. Separately,
`write_capable: boolean` flags a tool as needing a real write action; such
tools are catalogued for visibility but **can never be bound to an agent**.

This is enforced **server-side**, independent of whatever the client sends:
- `services/tool_binding.py::bind_tool()` re-reads the tool from its own
  `tools` table and rejects the bind if `write_capable` is true — it never
  trusts a client-supplied claim.
- `routes/chat.py::_looks_like_write_intent()` independently re-classifies
  every chat message for write-intent verbs and returns a canned refusal,
  overriding whatever the client's own (identical, duplicated-on-purpose)
  classifier in `src/kernel/playground.ts` decided.
- `services/tool_authoring.py::create_tool()` validates `permission_ceiling`
  against the same 5-value set server-side before insert — a client can't
  create a tool with an invalid ceiling by crafting a raw request.

**Any new feature that touches tool permissions or write actions must
re-validate server-side, not just rely on frontend type safety.**

### DB / JSONB gotcha

`db/connection.py` registers a `jsonb` type codec
(`encoder=json.dumps, decoder=json.loads`) on every connection. This means
**repository code passes and receives plain Python dicts/lists for JSONB
columns — never call `json.dumps`/`json.loads` yourself** in a `_repo.py`
file, or you'll double-encode/decode. (`tools_repo.py` is the reference
example after this session's changes.)

### No migration framework — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`

`db/migrate.py` is one big `CREATE TABLE IF NOT EXISTS ...` string executed
on every boot. `CREATE TABLE IF NOT EXISTS` does **not** retroactively add
columns to an already-existing dev database. The established fix (added this
session, first precedent for it) is to follow the `CREATE TABLE` block with
explicit `ALTER TABLE tools ADD COLUMN IF NOT EXISTS ... DEFAULT ...`
statements — idempotent, safe to run on every boot, no framework needed.

## 4. The synthesis engine (`kernel/engine/`)

This is **100% deterministic, local, rule/regex-based logic** — despite the
onboarding UI showing a "✨ Generate proposal" button with a spinner that
*looks* like an AI call. It takes a free-text objective, classifies it
(`nlu.ts`, `signals.ts`, `classification`), proposes a capability tier and
risk tier, decomposes sub-agents from a small pattern library
(`templates.ts`), and detects write-intent verbs to auto-flag tools
(`writeDetect.ts`). **Do not confuse this with a real Claude call** — the
only two places that call the real Anthropic API are Playground chat
(`chatWithAgent`) and, as of this session, tool suggestion (`suggestTool`).

## 5. Real Claude integration (`backend/app/services/claude_service.py`)

- `is_claude_configured()` — `bool(env.ANTHROPIC_API_KEY)`, used as a guard
  before any Claude call; missing key → `503`, not a crash.
- `MODEL_BY_TIER` maps `minimal|standardized|advanced` → Haiku/Sonnet/Opus 5
  model IDs (env-overridable).
- `chat_with_agent()` builds the system prompt from the agent's own config
  groups, **never passes a `tools` param to the Anthropic request** — write
  exposure to the model is structurally impossible, not instruction-only.
- `tool_authoring.py::suggest_tool()` (new this session) reuses this same
  client/model-tier machinery for a one-shot structured-JSON draft — see §7.

## 6. Local environment gotcha: Postgres port conflict

This machine has a **native Windows PostgreSQL service**
(`postgresql-x64-18`) already bound to port 5432, which silently wins over
the project's `docker-compose` Postgres container trying to bind the same
host port. Symptom: `start.ps1`'s `pg_isready` check (run *inside* the
container via `docker compose exec`) passes fine, but the backend itself
crashes on boot with `asyncpg.exceptions.InvalidPasswordError` — because from
the host, `localhost:5432` was actually reaching the native service with
different credentials, not the Docker container.

**Fix applied this session**: `docker-compose.yml` and `.env` both now map/
point Postgres at **port 5434** instead of 5432. If you ever see this same
`InvalidPasswordError` again, that's the first thing to check — either the
port mapping drifted back, or a fresh clone still has the old `.env.example`
default.

## 7. This session's feature: Tool Catalog creation + AI suggestion

**Before**: `/tools` (Tool Catalog tab) was 100% read-only — a fixed seed,
no create flow, and the backend `tools` table only stored 6 of 11
`ToolAsset` fields and was never even read by the frontend (a "shadow copy"
that only existed for `bind_tool`'s server-side check).

**Now**: users can create a new tool from the Tool Catalog tab, optionally
drafting its fields from a plain-language description via a real Claude
call, and the new tool persists through the backend DB and survives a page
refresh.

### Files touched

| Layer | File | What changed |
|---|---|---|
| DB schema | `backend/app/db/migrate.py` | Widened `tools` table via `ALTER TABLE ADD COLUMN IF NOT EXISTS` (description, category, connector_id, schema_json, status, result_fixtures_json) |
| Repo | `backend/app/repositories/tools_repo.py` | `_row_to_tool`/`insert` now round-trip all fields; added `get_all()` |
| Service (new) | `backend/app/services/tool_authoring.py` | `create_tool()` (validates + inserts + audits), `suggest_tool()` (real Claude call, strict-JSON-only prompt, `ADVISORY_PERMISSIONS` guard) |
| Route (new) | `backend/app/routes/tools.py` | `POST /v1/tools` (201/400), `POST /v1/tools/suggest` (200/503/502) |
| Wiring | `backend/app/main.py` | Registered `tools_router` |
| Wiring | `backend/app/routes/bootstrap.py` | `GET /v1/bootstrap` now also returns `tools` (via `tools_repo.get_all()`) |
| Store | `src/kernel/store.ts` | Added `addTool` mutator; `hydrateFromServer` now optionally merges `tools` |
| Services | `src/kernel/services.ts` | Added `createTool()`, `suggestTool()` — same `postJson`/toast conventions as `bindTool`/`register` |
| API façade | `src/kernel/api.ts` | Re-exported both |
| UI | `src/modules/tools/ToolsPage.tsx` | "New tool" button → `Modal` with a "Suggest with AI" panel (textarea + Sparkles button, local `useState` loading, NOT the job queue) feeding an editable form (name/category/description/permission_ceiling restricted to the 5 advisory values/write_capable checkbox/inputs-outputs schema via `TagInput` `field:type` pairs) → "Create tool" |

### Key decisions made (asked of the user, then designed around)

1. **"Suggest" = a real Claude call**, not the local rule-based engine
   pattern used by onboarding — chosen explicitly over the cheaper
   deterministic-mimic option.
2. **Created tools persist to the backend DB** (not session-only) — this is
   *why* `bootstrap.py`/`hydrateFromServer` needed to change at all; without
   that, a created tool would vanish on refresh even though it made it into
   Postgres, because the frontend never re-reads the `tools` table otherwise.
3. **`write_capable` tools can still be created** (for cataloguing) — the
   existing `bind_tool` server-side guard already rejects binding them, so no
   new enforcement code was needed, just the same inline warning UI the
   detail drawer already showed.

### Verified this session (via direct HTTP calls against a disposable test DB, not the real dev DB — see §6 for why)

- `POST /v1/tools/suggest` with a real Claude call: correctly flagged
  `write_capable: true` for "close a ticket", `false` for a read-only lookup.
- `POST /v1/tools` persists correctly; `GET /v1/bootstrap` returns it
  afterward (proves refresh-survival).
- Binding a `write_capable` tool is rejected by the existing advisory-block
  guard; binding a read-only created tool succeeds normally.
- `tsc --noEmit` passes clean on the whole frontend.

### Not yet verified

- **A live browser click-through of the "New tool" modal** — see `CLAUDE.md`
  "Where we left off" for the current status and what's blocking it (the
  port-conflict fix in §6 was applied but not yet confirmed working after a
  full restart).

The original implementation plan for this feature (written during plan mode)
is preserved at `C:\Users\Rahul1.kumar\.claude\plans\iterative-sprouting-noodle.md`
if you want the full original reasoning/verification checklist.

> **Update:** the port-conflict fix from §6 **is now confirmed working.** The
> backend boots against port 5434, migrates, and seeds cleanly — no
> `InvalidPasswordError`. See §8.

---

## 8. MCP connectors moved server-side

The session after tool authoring. Tools had become backend-persisted while
connectors stayed a browser-memory simulation — but **tool status derives from
connector health**, so that split was unstable. This section closes it.

### The invariant this encodes

> **A tool is never healthier than the connector that serves it.**

An offline MCP server cannot serve its tools. The inverse has no physical
meaning, which is why the derivation is strictly one-directional: connector
status is authoritative, tool status is derived. Before this change the
relationship was maintained *by hand* in seed data — `jira_reader` was
hardcoded `degraded` with a comment explaining that its connector was
degraded, and nothing enforced it. Toggling a connector left tool status
stale, and a refresh reset everything.

**Tools with `connector_id = NULL` are local and deliberately untouched by the
cascade** — 5 of the 12 seeded tools are local, so cascading blindly would be
wrong. A tool does *not* require a connector; the relationship is optional
many-to-one.

### Files

| File | Change |
|---|---|
| `backend/app/db/migrate.py` | `connectors` table DDL |
| `backend/app/repositories/connectors_repo.py` | **new** — `insert`, `get_by_id`, `get_all`, `set_status` |
| `backend/app/repositories/tools_repo.py` | `set_status()` — only ever called by the cascade |
| `backend/app/services/connector_health.py` | **new** — `connector_health_to_tool_status`, `cascade_connector_health`, `run_healthcheck`, `toggle_offline`, `list_connector_tools` |
| `backend/app/routes/connectors.py` | **new** — 3 endpoints |
| `backend/app/routes/bootstrap.py` | returns `connectors` |
| `backend/app/db/seed.py` | seeds connectors (independently of tools, so an existing dev DB backfills) |
| `backend/app/seed_data/seed_snapshot.json` | regenerated with a `connectors` key |
| `backend/verify_connectors.py` | **new** — 24-assertion backend suite |
| `src/kernel/services.ts` | `healthcheck`/`toggleConnectorOffline` → real async calls; `listConnectorTools` added |
| `src/kernel/store.ts` | `hydrateFromServer` accepts `connectors` |
| `src/kernel/api.ts` | `listConnectorTools` re-export |
| `src/modules/tools/ToolsPage.tsx` | `status` column + status/connector filters; `ConnectorCard` extracted with local loading state + Discover-tools panel |
| `test/causality.ts` | offline-toggle block now sets its precondition via a store patch |

### Endpoints

```
POST /v1/connectors/:id/healthcheck    → {connector, changedTools, auditEvent, skipped?}
POST /v1/connectors/:id/toggle-offline → {connector, changedTools, auditEvent}
GET  /v1/connectors/:id/tools          → {connector, tools, undiscovered, orphaned}   # MCP tools/list
```

Both mutation endpoints return the same shape: the updated connector, **only
the tools whose status actually changed**, and the audit event. Returning a
precise patch list rather than forcing a full `/v1/bootstrap` refetch keeps the
client update cheap and lets the toast report how many tools were affected.

### `GET /v1/connectors/:id/tools` is the MCP seam

This is MCP `tools/list`. Today it reads the catalog the server already owns.
**A real MCP client would issue a `tools/list` RPC over the connector's
transport and map the response into this same shape** — that is the designated
swap point, and nothing else needs to change when it happens.

It already returns a discovery diff:
- `undiscovered` — advertised by the connector, absent from the catalog
- `orphaned` — catalogued against this connector, no longer advertised

Both are empty on a clean seed. They become meaningful the moment a real
client is wired in, or when connector CRUD lands.

### Deliberate deviation: healthcheck left the jobs queue

`healthcheck` used to run through `kernel/jobs.ts` for its "Probing endpoint…"
animation. It is now a real backend call, so per the convention in §2
("don't mix the two patterns") it moved to a local `useState` loading boolean
in `ConnectorCard`. Keeping the job would have raced the fixed-duration timer
against real HTTP latency. **Consequence: healthchecks no longer appear in the
TopBar job tray** — this is correct and consistent with `createTool`, not a
regression.

The ~18% degraded chance moved to the server (`connector_health.py`), so demo
behaviour is unchanged. An offline connector is *never* silently revived by a
healthcheck — the server returns `skipped: true`.

### Verified

`backend/verify_connectors.py` — 24 assertions, all passing against a live
backend: bootstrap exposes 5 connectors, tools/list shape + 404, cascade
offline (3 tools) with audit, **persistence across refetch**, connectorless
tool untouched, offline-not-revived, restore, live healthcheck.

Frontend: `tsc -b --noEmit` clean, `npm run build` clean, all 4 kernel suites
pass.

**Not verified:** a live browser click-through. No headless-browser tooling is
installed (same constraint as §7).

---

## 9. Connector resolution — the agent → MCP dependency set

*(Phase 0, 2026-08-03. `ROADMAP.md` §4 Phase 0.)*

§8 made connector health flow **down** onto tools. This section adds the
missing lookup in the other direction: given an agent, **which MCP servers does
it actually need?**

### Why this exists

The tool → connector edge is a **fixed foreign key on the tool row**, set when
the tool is catalogued. A tool has exactly one home system. So "which MCP?" is
a lookup, not a choice — there is no routing, scoring, or failover, and
deliberately so: slide 21 element 6 (*log the system accessed*) and element 4
(*declare which datasets an agent may reach*) both require the edge to be
static and auditable ahead of a run.

But nothing in the codebase ever **walked** that edge. `connector` appeared
nowhere in `kernel/engine/`; an agent's connector dependency set existed only
as an implication of the data. Three separate features needed it, so it is
derived once, server-side:

| Gate | When | Question | Behaviour |
|---|---|---|---|
| **Pick** | `Phase1Intent` | Does this tool exist, and what MCP does it pull in? | validate |
| **Bind** | `tool_binding.py` | Is this tool bindable? | **block** on `write_capable`; **warn** on unhealthy connector |
| **Deploy** | `PreFlight` #4 | Are *this agent's* connectors up? | **block** |
| **Run** | `tool_calls` (Phase 1) | Which system did it touch? | log |

### The design call: bind warns, deploy blocks

Binding is a **design-time declaration**; connector health is a **runtime
condition**. Gating a config write on flapping infrastructure would make agent
definitions non-deterministic with respect to a third party's uptime, so
`bind_tool()` returns `{"ok": true, "warning": "..."}` and writes the warning
into the audit detail. It does **not** add a second `ok: false` branch — the
only blocking check there remains `write_capable`.

The blocking gate is Pre-Flight check #4, which is where an operator is asking
"can this go live *now*?".

### Files

| File | Change |
|---|---|
| `backend/app/services/connector_resolution.py` | **new** — `parse_tool_ref`, `resolve_tool_connector`, `resolve_connectors_for_tools`, `resolve_agent_connectors` |
| `backend/app/routes/agents.py` | `GET /v1/agents/:id/connectors` → 200 / 404 |
| `backend/app/services/tool_binding.py` | `_health_warning()`; success payload gains `warning` |
| `backend/verify_connectors.py` | +26 assertions, and a **starting-state normalization** (see below) |
| `src/kernel/services.ts` | `listAgentConnectors()`, `AgentConnectorsResponse`; `bindTool` surfaces `warning` as a warn toast |
| `src/kernel/api.ts` | re-export |
| `src/modules/onboarding/ToolPicker.tsx` | **new** — catalog-backed typeahead replacing `TagInput` on the Tools field |
| `src/modules/onboarding/McpDependencies.tsx` | **new** — the resolved dependency panel |
| `src/modules/onboarding/PreFlight.tsx` | `usePreflight(toolIds?)` — check #4 scoped + connectors named in the label |
| `src/modules/onboarding/phases/PreFlightPhase.tsx` | passes `draft.intent.tools` |
| `src/modules/onboarding/phases/Phase1Intent.tsx` | uses `ToolPicker` |
| `src/modules/onboarding/phases/Phase4Configure.tsx` | renders `McpDependencies` |

No schema change. Pure derivation over `agents` + `tools` + `connectors`.

### Endpoint

```
GET /v1/agents/:id/connectors → {
  agent_id, bound_tools[],
  connectors[]    // full connector rows, each with the tools[] it serves here
  local_tools[],  // connector_id IS NULL — need no MCP server
  unknown_tools[],// bound, but no longer in the catalog
  offline[],      // deploy-time hard blockers
  unhealthy[]     // offline ∪ degraded
}
```

`local_tools` is reported separately and **never given a placeholder
connector** — 5 of 12 seeded tools are local, and inventing a pseudo-connector
for them would corrupt the same superset property §8 depends on.

### Pre-Flight scoping is narrower than it first looks

`usePreflight()` runs at two call sites that both execute **before any tool is
chosen** — `OnboardingPage` (no draft at all) and `PreFlightPhase` (phase
`pre`, ahead of Phase 1). At those points there is no agent to scope to, so the
platform-wide check is the honest answer and remains the fallback. The hook now
takes an optional `toolIds`; scoping engages once a draft has tools (i.e. on a
return visit to phase `pre`), and the label names the offending connectors
either way. **The genuinely agent-scoped readiness signal lives in
`McpDependencies`**, on Phase 4 — the first point where `bound_tools` exists.

### `verify_connectors.py` now normalizes its starting state

The suite drives `gcp-ticketing` with `toggle-offline`, which **flips** rather
than sets. A connector left offline by a UI click inverted every assertion
downstream — 17 failures with no code defect behind them. It now brings the
connector online on entry (and healthchecks past a `degraded` roll), then
restores the state it found. This is what the module docstring always claimed.

### Verified

`backend/verify_connectors.py` — **51 assertions, all passing** against a live
backend. New coverage: refs stripped to bare ids, 4 bound tools → 2 connectors
+ 2 local, a local-only agent resolving to zero connectors, unknown agent 404,
`offline` tracking a live toggle, bind warning present/absent/named and written
to the audit detail, no warning for a connectorless tool, and the
`write_capable` rejection still intact.

Frontend: `tsc -b --noEmit` clean, all 4 kernel suites pass.

**Not verified:** a live browser click-through (same constraint as §7/§8) —
specifically the typeahead dropdown, the dependency panel, and the scoped
Pre-Flight label.

---

## 10. Tool-call audit trail

*(Phase 1, 2026-08-03. Deck slide 21 element 6. `ROADMAP.md` §4 Phase 1.)*

The console could show *what an agent is allowed to do* (Tool Catalog) and *how
we reach the systems* (MCP Connectors). It could not show **what an agent
actually did** — every tool call the Playground simulated was discarded.

`/tools` now has a third tab. Same page, third concern: permissions →
connectivity → **evidence**.

### The table is the deck's field list, verbatim

Slide 21 names eight fields. The DDL carries them in the slide's own order so
the schema can be read against the commitment directly, plus `permission` (the
ceiling actually exercised) and `at`.

```
tool_calls(id, agent_id, request_id, consumer, tool_invoked, system_accessed,
           result_status, latency_ms, exception_detail, permission, at)
```

Indexed on `(agent_id, at DESC)` and `(tool_invoked, at DESC)` — the two access
patterns the tab's filters produce.

**Deliberately no FK to `agents`.** An audit trail outlives its subject; the
closest analogue in this schema is `audit_log`, which is also unreferenced.

### Four things the client cannot forge

This is what makes it a *trail* rather than a log. All three are resolved or
stamped server-side, and a client-supplied value is ignored, not merged:

| Field | Resolved from |
|---|---|
| `system_accessed` | `connector_resolution.resolve_tool_connector()` — §9's single place that walks the tool→connector edge |
| `permission` | the server's own `tools` table — the same trust boundary `tool_binding.py` uses |
| `at` | the server clock — the one field a caller would most want to bend |
| **authority** | the agent's own `bound_tools` (added 2026-08-04) — a claimed `resultStatus: ok` for a tool the agent was never bound to is **overridden to `blocked`** with the reason recorded. It records rather than rejects: refusing the write would destroy the evidence of the thing worth catching. |

`system_accessed` is `NULL` for local tools and renders as **"local — no MCP"**.
Never a placeholder, never a blank.

> **Honest limit.** `result_status` and `latency_ms` *are* client-supplied, and
> in a client-simulated Playground there is no server-side invocation to time or
> to observe failing — so they have no server-side truth to check against. The
> authority override above is what stops that being a hole worth exploiting.
> **Do not call this trail authoritative runtime evidence** until calls run
> through the Phase 6 gateway. Tracked as `ROADMAP.md` R7.

An uncatalogued `tool_invoked` is still recorded, with `permission = "unknown"`
and an `exception_detail` saying so — that mismatch is itself the finding, so
dropping the row would destroy the evidence.

### Blocked attempts are the point

Two paths write `result_status = "blocked"`:

1. **A rejected bind.** `tool_binding.py` already refused write-capable tools
   and wrote a `bind_rejected` audit event; the moment then vanished. It now
   also lands in `tool_calls` with `consumer = "console"`. The advisory-only
   invariant stops being a silent rejection and becomes a row you can point at.
2. **A denied runtime HITL gate** in the Playground, with the denial reason in
   `exception_detail`.

`record_blocked_bind()` is best-effort and swallows its own exceptions — the
rejection is the contract and must not fail because the audit trail did. It
deliberately writes no second audit event, since `bind_rejected` already exists.

**A refusal is not logged.** When the Playground classifies a message as
write-intent it returns `toolCalls: []` — no tool was named, so there is nothing
truthful to put in `tool_invoked`. Inventing one to produce a nicer demo row
would be fabricating an audit record. The two paths above are real and cover
the same demo beat.

### HITL timing

A HITL-gated call is *pending* at send time, so logging it as `ok` there would
be wrong. `PlaygroundPage` therefore logs non-gated calls immediately and defers
gated ones to `decideHitl` — `ok` on approve, `blocked` on deny. The turn
carries its `requestId` and measured `latencyMs` so the decision logs against
the same request as the turn that produced it.

Recording is **fire-and-forget** (`void api.recordToolCall(...)`): the trail
must never delay or fail the conversation that produced it.

### Files

| File | Change |
|---|---|
| `backend/app/db/migrate.py` | `tool_calls` DDL + 2 indexes |
| `backend/app/repositories/tool_calls_repo.py` | **new** — `insert`, `get_filtered`, `get_all` |
| `backend/app/services/tool_call_log.py` | **new** — `record_tool_call`, `record_blocked_bind`, `list_tool_calls` |
| `backend/app/routes/tools.py` | `POST /v1/tool-calls` (201/400) · `GET /v1/tool-calls` (200) |
| `backend/app/services/tool_binding.py` | rejection path calls `record_blocked_bind()` |
| `backend/verify_tool_calls.py` | **new** — 47-assertion suite |
| `src/kernel/services.ts` | `recordToolCall()`, `listToolCalls()`, `ToolCallRecord` |
| `src/kernel/api.ts` | re-exports |
| `src/modules/playground/PlaygroundPage.tsx` | fires records; `Turn` carries `requestId` / `latencyMs` |
| `src/modules/tools/ToolsPage.tsx` | **third tab: Tool Calls** — `DataTable` + agent/tool/result filters |

`get_filtered()` numbers its asyncpg placeholders dynamically because the
optional filters shift the positions — asyncpg has no named parameters.

### Verified

`backend/verify_tool_calls.py` — **47 assertions, all passing.** Covers the
eight fields, server-side resolution of all three unforgeable fields (including
explicit attempts to supply `system_accessed`, `permission`, and `at`), ref
normalization, generated `request_id`, the uncatalogued-tool path, five
validation 400s, the blocked-result audit event, the rejected bind landing as
`blocked` with `consumer = console`, all three filters plus ANDing, and
ordering/limit.

No regressions: `verify_connectors.py` 51/51 · `npm run test` 4/4 ·
`tsc -b --noEmit` clean · `npm run build` clean.

**Note:** this suite is append-only by design and **leaves rows behind** — same
as `audit_log`. It mutates no connector or tool state.

**Not verified:** the browser click-through (same constraint as §7/§8/§9).

---

## 11. Connector CRUD

*(Phase 2, 2026-08-04. Blueprint §3.5 capability #1; `ROADMAP.md` §4 Phase 2.)*

Connectors were seed-only — conspicuous once §8 made them persisted, and
promoted to MVP-critical by the Product Blueprint, which lists *"Register MCP
server"* first among connector capabilities and names *"Tool Registry / MCP
Connector Setup"* as an MVP screen.

### Two invariants the authoring path must not break

**1. Status is owned by the health cascade, never by an author.** A new
connector seeds `connected`; thereafter only `services/connector_health.py`
writes it. Neither create nor update accepts `status` from the client, and
`connectors_repo.update()` physically cannot set it — the UPDATE statement
lists only the four author-owned columns. This matters because §8's whole
chain starts here: a tool is never healthier than its connector, so an author
who could set `status` could launder a tool's status too.

**2. `tools_provided` is a *claim*, not a binding.** It is what the server
advertises; the catalog is separate, and the diff between them is exactly what
`GET /v1/connectors/:id/tools` reports as `undiscovered`/`orphaned`.
**Registering a connector therefore creates no tools**, and the create form
does not expose the field.

> **Correction (2026-08-04, external review).** An earlier draft said this
> finally makes `undiscovered` non-empty. It does not — `undiscovered =
> advertised − catalogued`, and a fresh connector advertises nothing, so
> **Discover tools** on it returns entirely empty. `verify_connector_crud.py`
> asserts exactly that. Worse, `tool_authoring.create_tool()` hardcodes
> `connector_id: None` and nothing ever sets it, so **no tool created through
> the product can ever be attached to a connector** — `undiscovered` and
> `orphaned` are structurally unreachable until a real `tools/list` writes
> discovered tools. Tracked as `ROADMAP.md` **D7**.

### Validation

`EDITABLE = (name, transport, endpoint, auth_mode)` — the only four fields an
author owns. `status`, `tools_provided` and `last_healthcheck` are deliberately
absent from that tuple.

Update **merges first, then validates the result**, so a partial patch cannot
slip an invalid *combination* past a per-field check. The clean case: neither
`transport: "http"` nor `endpoint: "sse://…"` is invalid alone — only the pair
is, and only merged validation catches it.

**`sse` accepts `http(s)://` as well as `sse://` on purpose.** MCP's SSE
transport is an HTTP endpoint that streams Server-Sent Events, so
`https://host/sse` is the canonical real-world form. The seed happens to use
`sse://` throughout, which makes the pair look stricter than it is — this is
noted in the code because it reads like a bug otherwise. `stdio` has no network
endpoint (it is a command line) and is checked only for non-emptiness.

Duplicate names get a suffixed id (`_unique_connector_id`), the same approach
`tool_authoring.py` uses — a collision is not an error.

### Files

| File | Change |
|---|---|
| `backend/app/services/connector_authoring.py` | **new** — `create_connector`, `update_connector`, validation, `EDITABLE` |
| `backend/app/repositories/connectors_repo.py` | `update()` — author-owned columns only |
| `backend/app/routes/connectors.py` | `POST /v1/connectors` (201/400) · `PATCH /v1/connectors/:id` (200/400/404) |
| `backend/verify_connector_crud.py` | **new** — 40-assertion suite |
| `src/kernel/services.ts` / `api.ts` | `createConnector`, `updateConnector` |
| `src/kernel/store.ts` | `addConnector` mutator |
| `src/modules/tools/ToolsPage.tsx` | **Register MCP server** button + `ConnectorModal` (create/edit in one), edit affordance on `ConnectorCard` |

### No delete endpoint — deliberate

A connector other rows reference (tools via `connector_id`, `tool_calls` via
`system_accessed`) should not vanish. Retirement, when it is needed, belongs
with the Blueprint's lifecycle states rather than a hard delete. The
verification suite therefore names everything it creates `zz-verify-*` so the
leftovers sort last and are obvious.

### One pre-existing assertion Phase 2 invalidated

`verify_connectors.py` asserted `len(connectors) == 5` — which quietly encoded
*"connectors are seed-only"*, precisely what this phase ends. It now asserts the
5 seeded ids are **present**, which is the invariant it actually cared about.

### Verified

`backend/verify_connector_crud.py` — **40 assertions, all passing.** Covers id
slugification, persistence across a refetch, that a new connector creates no
tools, both forged-field paths (`status`, `tools_provided` on create *and*
update), six validation 400s, `stdio` accepting a command, duplicate-name id
suffixing, partial-patch merged validation, no-op patches writing no audit
event, and the health cascade still owning status afterwards.

No regressions: `verify_connectors.py` 51/51 · `verify_tool_calls.py` 47/47 ·
`npm run test` 4/4 · `tsc -b --noEmit` clean · `npm run build` clean.

**Not verified:** the browser click-through (same standing constraint) —
specifically the Register modal, the transport-dependent endpoint hint, and the
edit pencil on `ConnectorCard`.

---

## 12. Tool governance — approval + policy fields

**Phase 3 (2026-08-05).** The Tool Catalog could say what a tool *is* and how
healthy it *is*, but not whether anyone had ever agreed to it. Three pieces
shipped together because they are one story — the permission model made
legible, consent made explicit, and accountability made recordable.

### 12.1 The permission matrix is presentation, not a second model

Deck slide 25 and Blueprint §3.4 independently specify the same nine permission
types (5 allowed / 4 blocked). The code has had that exact shape since day one
as a locked 5-value enum plus a `write_capable` boolean, which closed **D1** —
but the console could not *render* the nine rows, and a named Day-90 artifact
that exists only in the type system is not an artifact anyone can review.

`PERMISSION_MATRIX` in `kernel/constants.ts` is therefore a **view over the
model, not a source of truth**: nothing reads it for enforcement, and the five
allowed rows restate `ADVISORY_PERMISSIONS` verbatim. The panel lives on the
Tool Catalog behind a *Permission matrix* toggle.

**Updated 2026-08-05: it now quotes slide 25 rather than paraphrasing it.** The
first version used descriptions I wrote, which meant the console and a
client-facing artifact could drift with nobody noticing. `permission`,
`description` and `treatment_text` are now verbatim from the source `.pptx` —
including the detail that slide 25 qualifies **only** Read, as *"Allowed with
approved access"*. Editing those strings edits a commitment; change the deck
first.

The same read surfaced that **the deck is not internally consistent** about the
vocabulary, and that slide 25 is the one to follow:

| Source | Words used |
|---|---|
| Deck **slide 25** (*Detailed* Tool Permission Matrix) | read · summarize · draft · recommend · validate · create · update · approve · deploy |
| Deck slide 21 (Tool Permission Model row) | read · **retrieve** · summarize · draft · recommend · write-blocked |
| SOW (boundaries table) | summarize · draft · recommend · **classify** · validate |

The enum matches slide 25's five allowed values exactly. `retrieve` and
`classify` have no home in the model — tracked as **Q8**, and explicitly *not* a
reason to widen the enum.

The asymmetry it shows is the point. For the allowed rows the code is
**stronger** than the deck describes (an invalid permission is a *type error*,
not a policy violation). For the blocked rows it is **coarser**: all four
collapse into one boolean, so the model records *that* a tool writes and never
*which verb*. The live counts follow that honestly — the four blocked rows share
**one** count, because splitting three write-capable tools across
create/update/approve/deploy would be inventing attribution to fill a table.
Write-capable tools are counted against the blocked group regardless of their
declared ceiling, since counting `slack_notifier` under "draft" would overstate
what is actually reachable.

### 12.2 Approval reuses the shared queue rather than inventing one

Blueprint §11 names an **Approval Queue** covering *"prompt, tool, data, model,
deployment and exception approvals"*, which answered the standing question
(Q1/D3): tool approval is real **and it is a shared platform object**. So the
`approvals` table was widened rather than duplicated:

```
approvals
  agent_id         now NULLABLE  -- keeps its FK; a nullable FK still enforces
                                 -- integrity for every non-null value
  required_by_path now NULLABLE  -- a governance path is an agent concept
  entity_type      TEXT NOT NULL DEFAULT 'agent'
  entity_id        TEXT          -- backfilled from agent_id
```

**Why nullable and not a stand-in value.** Writing `required_by_path` =
`'standard'` on a tool row to satisfy a NOT NULL would have been inventing a
fact to satisfy a schema — the same failure mode as logging a placeholder
`system_accessed` for a local tool (§10). A tool has no governance path; NULL
says so.

**Why not a tool-local `pending_approval` status.** That was the plan of record
(ROADMAP Phase 3.2) and it is wrong for one specific reason: `tools.status` is
owned end-to-end by the connector health cascade (§8), so a governance state
living there would be overwritten the moment a connector flapped. Health and
consent are different questions about a tool, so `approval_state` is its own
column. `verify_tool_governance.py` asserts both directions of that
independence — approving cannot move `status`, and the cascade cannot move
`approval_state`.

**The seeded catalog is grandfathered, not retro-queued.** The column default is
`'approved'`, so the 12 seeded tools stay bindable and no Governance Officer
opens the queue to 12 items nobody requested. Everything created through the
console from here on starts `pending`.

### 12.3 Two independent gates in `bind_tool()`

```
write_capable?      -> reject   (advisory-only invariant, LOCKED)
approval_state?     -> reject   (Phase 3.2)
connector unhealthy -> warn     (Phase 0 — bind warns, deploy blocks)
```

Order matters and is deliberate: **approval is checked second and never
substitutes for the write check.** Approving a write-capable tool does *not*
make it bindable — otherwise approval would become a laundering path for the
one invariant the deck is most specific about. Whether a human-approved write
exception should ever exist is **Q6**, a governance decision, not a code tweak.

Both gates re-read the server's own `tools` row. A rejected bind is logged as a
`blocked` tool call with `consumer = console`, same as the write rejection —
the governance decision becomes evidence rather than a silent failure.

### 12.4 Policy fields: `owner` + `risk_level`

Blueprint §3.4 lists eleven fields the tool object lacks (**D6**). Two shipped
here; `rate_limits` / `timeout` / `logging_requirement` are deferred to Phase 5
because **a policy field with no enforcer is decoration**.

- **Nullable on purpose.** A seeded tool genuinely has no owner, and defaulting
  one in would fabricate accountability in the exact screen used to *find*
  missing accountability. NULL renders as "unassigned"/"unclassified" and the
  catalog banner counts them.
- **`risk_level` reuses the agent `RiskTier` vocabulary** — a platform with two
  risk vocabularies cannot report on risk.
- **One real rule:** a write-capable tool cannot be classified below `high`. If
  omitted it is raised to the floor; if supplied lower it is a 400, on create
  *and* on patch, validated against the merged result.

`PATCH /v1/tools/:id` is policy-only. `permission_ceiling`, `write_capable`,
`connector_id`, `status` and `approval_state` are all unreachable through it —
re-classifying a permission after approval would silently invalidate the
approval, and that belongs to versioning, not an edit form.

### Files

| Layer | Change |
|---|---|
| `db/migrate.py` | `tools.approval_state` / `owner` / `risk_level`; `approvals` widened + backfilled + `idx_approvals_entity` |
| `repositories/tools_repo.py` | the three new fields in the row map + insert; `set_approval_state()`, `update_policy()` |
| `repositories/approvals_repo.py` | `entity_type`/`entity_id` on insert, defaulting old callers to `agent` |
| `services/tool_approval.py` | **new** — `request_tool_approval()`, `decide_tool_approval()` |
| `services/approvals.py` | routes a decision by `entity_type`; returns `tool` alongside `agent` |
| `services/tool_authoring.py` | tools start `pending`; `RISK_LEVELS` + the write floor; `update_tool_policy()`; risk in the AI suggestion |
| `services/tool_binding.py` | second guard + a `_reject()` helper shared by both rejections |
| `routes/tools.py` | `PATCH /v1/tools/:id` (200/400/404) |
| `kernel/constants.ts` | `PERMISSION_MATRIX` — the 9 rows |
| `kernel/services.ts` / `api.ts` | `updateToolPolicy`; `createTool` handles the returned approval; `decideApproval` handles a tool subject; `postJson` gained an optional method |
| `types/assets.ts` / `types/governance.ts` | `ToolApprovalState`, `ToolRiskLevel`, `ApprovalEntityType`, nullable `agent_id`/`required_by_path` |
| `seed/tools.ts` | grandfathering applied once via a `map`, not repeated 12× |
| `modules/tools/ToolsPage.tsx` | matrix panel, approval/risk/owner columns + filters, gap banner, `ToolPolicyEditor` in the drawer, owner/risk on the create form |
| `governance/tabs/ApprovalsQueue.tsx` | renders tool items in their own card; tolerates a null `required_by_path` |

### Verified

`backend/verify_tool_governance.py` — **70 assertions, all passing.** Covers
grandfathering, the widened queue's backfill, cataloguing-is-not-consent, a
forged `approval_state`, the bind rejection and its `blocked` row, the shared
decide endpoint flipping the tool, both directions of health/consent
independence, approval-is-not-a-write-exemption, rejected tools staying
catalogued, the policy PATCH incl. clearing back to NULL, the write-capable risk
floor on create *and* patch, and six unreachable fields on the PATCH.

No regressions: `verify_connectors.py` 51 · `verify_tool_calls.py` 58 ·
`verify_connector_crud.py` 41 · `npm run test` 4/4 · `tsc -b --noEmit` clean ·
`npm run build` clean. (The tool-call and CRUD counts print higher than the
figures recorded in §10/§11 — those suites contain loop-driven assertions and
the earlier numbers were snapshots; neither gained a check in this phase.)

**This suite mutates a seeded agent and restores it.** Proving an approved tool
*binds* means writing to the Incident Coordinator's `bound_tools`, which
`verify_connectors.py` asserts has exactly 4 entries. It captures the config on
entry, restores on exit, and **strips any `zz-verify-` refs from the baseline
first**, so an interrupted run self-heals instead of writing its own pollution
back forever. It still leaves `zz-verify-*` tools and their approval items
behind — there is no tool delete endpoint, same reasoning as connectors.

**Not verified:** the browser click-through (same standing constraint) — the
matrix panel, the approval column, the drawer's policy editor, and tool items
in the Governance approvals queue.

---

## 13. The `bound_tools` guard — closing R8

**2026-08-05, same day as Phase 3.** Found while verifying Phase 3, fixed
immediately after: `bind_tool()` was the *governed* way a tool becomes bound to
an agent, and never the *only* way.

### What was wrong

Three routes write `config.tooling.bound_tools` straight out of a
client-supplied config, and none of them validated it:

| Route | Reached by |
|---|---|
| `POST /v1/agents/register` | the onboarding wizard's Register step |
| `PATCH /v1/agents/:id` | `syncAgentToServer()` after provisioning/pipeline jobs |
| `POST /v1/agents/:id/config-change` | `groupKey: 'tooling', field: 'bound_tools'` |

**Verified by experiment, not inferred:** registering with
`bound_tools: ["tools://ticket_updater@v1", "tools://<pending>@v1"]` returned
**201** with both refs persisted — bypassing the locked write-capable invariant
*and* Phase 3's brand-new approval gate. It compounds §10: `_binding_violation()`
authorizes tool calls **against** `bound_tools`, so a laundered bind makes a
write-capable call record `ok` in the audit trail.

**And it was reachable without curl.** The only thing filtering write tools
before registration was `kernel/engine/writeDetect.ts`, a **client-side name
heuristic** (`notifier`, `sender`, `updater`, …). The three seeded write tools
are caught by luck of naming; a tool called `payment_authorizer` is not. Nothing
at all filtered *unapproved* tools, so a tool catalogued a minute earlier walked
straight past Phase 3.

### Strip, don't reject

`services/bound_tools_guard.py` is now the one place that decides what may be
bound — the same "exactly one place walks this edge" discipline as
`connector_resolution.py` (§9). Three reasons, applied in `bind_tool()`'s order:

```
not_in_catalog   the ref names a tool that does not exist
write_capable    the locked advisory-only invariant  (checked FIRST)
not_approved     pending or rejected                 (Phase 3.2)
```

A bad ref does **not** fail the registration. The synthesis engine proposes
tools heuristically, so rejecting would dead-end an onboarding run over a tool
the user never hand-picked, and would leave no agent for the audit trail to
attach to. This matches the treatment write tools already get: catalogued,
visible, never bound.

The honest cost is that stripping rewrites the caller's config. That is paid for
in three places: the response carries `strippedTools[]` with a machine reason
and a human sentence, one `bind_stripped` audit event is written, and **one
`blocked` tool-call row per stripped ref** — the same evidence a refused
`bind_tool()` produces, so `/tools` → Tool Calls shows every refused bind
regardless of which door it came through.

### Two bugs the verification suite caught in the first draft

Worth recording, because both were mine and both were invisible by inspection:

1. **`guard_config()` only wrote back when something was removed.** That
   shortcut silently skipped duplicate collapsing, so `[a, a, b]` persisted with
   the duplicate. It now assigns unconditionally.
2. **The PATCH path suppressed "repeat" syncs — and swallowed real evidence.**
   The rule was "stay silent when the sanitized result equals what is stored",
   on the assumption the client re-sends an unsanitized config each provisioning
   step. **The premise was wrong**: `syncAgentToServer()` reads from the store,
   which adopted the server's sanitized agent at registration, so a repeat sync
   has nothing to strip and is silent for free. Worse, the condition could not
   tell a *first* attempt from a repeat — both look identical — so it suppressed
   the first one too. De-duplication removed; every genuine attempt is reported.

### Client behaviour

`register()` already did `store.addAgent(data.agent)`, so the client **adopts
the sanitized config automatically** — no drift between what the server holds
and what the UI shows. The flat `ok` toast becomes a **warn** toast naming what
was dropped and why. `ToolPicker` gained a `pending` badge alongside its
existing `WRITE` one, so an unbindable pick is visible *at pick time* rather
than as a surprise at Register — the same onboarding carve-out §9 used, and for
the same reason.

### Files

| Layer | Change |
|---|---|
| `services/bound_tools_guard.py` | **new** — `sanitize_bound_tools()`, `guard_config()`, `record_stripped()` |
| `services/registration.py` | guards the config before insert; returns `strippedTools` |
| `routes/agents.py` | guards `config` on the sync PATCH |
| `services/lifecycle.py` | guards `groupKey=tooling, field=bound_tools` |
| `kernel/services.ts` | `StrippedTool` + `describeStripped()`; warn toasts on register and config-change |
| `modules/onboarding/ToolPicker.tsx` | `unbindable()` — pending/rejected badge beside the existing WRITE badge |

### Verified

`backend/verify_bound_tools_guard.py` — **34 assertions, all passing.** All
three doors, all three strip reasons, that the *persisted* row is clean (not
just the response), the audit event and the three `blocked` rows, no false
positives on a clean registration, duplicate collapsing, ordering
(an **approved** write-capable tool is still refused, and refused *as*
`write_capable`), that approving the pending tool then lets it through, and that
seeded agents were untouched.

**This suite deletes what it creates.** It must register real agents and there is
no delete-agent endpoint; leftovers would appear in the Registry and the Home
page counts. It therefore uses asyncpg + `DATABASE_URL` for **teardown only** —
the first suite to touch the DB directly, deliberately, with every assertion
still over HTTP. The `zz-verify-guard-*` tools it catalogues are left behind,
same as the other suites.

No regressions: `verify_connectors.py` 51 · `verify_tool_calls.py` 58 ·
`verify_connector_crud.py` 41 · `verify_tool_governance.py` 70 ·
`npm run test` 4/4 · `tsc -b --noEmit` clean · `npm run build` clean.

**Not verified:** the browser click-through — the warn toast at Register and the
pending badge in `ToolPicker`.

---

## 14. Connector prioritization backlog

**Phase 4 (2026-08-05).** The last unbuilt element of deck slide 21's seven, and
the artifact the SOW's Week-11 deliverable 3.3 actually asks for: *"identify
which systems should be connected in the first 90 days versus future phases."*

### 14.1 Why this is a table and not a document

Slide 18 names this workstream's Day-90 evidence as an *"MCP and tool registry
strategy package"*, and the SOW's acceptance criterion is *"Internal
connectivity strategy and priority connector model **defined**"*. Both describe
a document — so the tempting build is a markdown file or a hardcoded constant
rendered as a page.

It is persisted instead, for one reason: **an assessment that cannot be revised
is a document, not a console feature.** A system's `status` moves across the
engagement (`proposed` → `access_requested` → `approved` → `connected`), and
ServiceNow stops being ineligible the day a server ships. A constant would need
a deploy to record either. *(That call was ours, not the client's — recorded as
`CONCERNS.md` **Q13**.)*

### 14.2 `connector_backlog` is not `connectors`

Two tables that look similar and mean different things:

| | `connector_backlog` | `connectors` |
|---|---|---|
| A row is | a **candidate system under assessment** | **a server we actually talk to** |
| Answers | *should we connect this, and when?* | *how do we reach it, and is it healthy?* |
| Lifecycle | ranked, phased, blocked/unblocked | connected / degraded / offline |

`existing_connector_id` links them where both exist (Jira and Confluence today).
They are deliberately separate: assessing ServiceNow must not create a connector
for it, and deleting a connector must not erase the assessment that chose it.

### 14.3 The invariant: a contract term with teeth

The SOW's boundaries table says:

> *"Will install and configure MCP servers only; building new MCP servers is out
> of scope."* → *"Install/configure approved/**existing** MCP servers and
> connectors; backlog custom MCP server creation."*

So **a system with no existing MCP server cannot be scheduled into the 90-day
phase.** A plan that puts ServiceNow in the first 90 days silently assumes work
the contract excludes — and that is precisely the kind of thing that is
invisible in a slide and expensive in week 10.

It is enforced in `services/connector_backlog.py`, server-side, on every write,
and **validated against the merged item** — so flipping `phase` and `mcp_server`
in two separate patches fails at whichever one first makes the pair invalid. The
legitimate route is to confirm a server exists *and then* schedule it, which the
suite exercises.

This is the same shape as the `write_capable` floor in `tool_binding.py`: a
document's constraint expressed as code rather than as a comment.

### 14.4 Three smaller decisions worth keeping

1. **`recommended` is derived, never stored** — it is rank 1 of the 90-day set,
   computed in `list_backlog()`. A stored "recommended" flag would drift from the
   ranking it claims to summarise, which is the same failure mode as re-deriving
   `system_accessed` on the client.
2. **`unknown` is not `none`.** ServiceNow is `none` (a widely-covered product
   with no server found); CCAI and MDR are `unknown` (we looked and could not
   confirm). Collapsing them would assert something we did not verify.
3. **There is no POST route.** The candidate set is the SOW's seven systems of
   record, and extending it is a contract change, not a UI action.

### 14.5 The MDR problem

**Neither source document ever expands "MDR".** It appears only inside the
connector lists on deck slides 17 and 21 and in the SOW's systems-of-record row —
never with a definition. It is kept in the backlog because it is a contracted
system of record, ranked last because *nobody can assess a system they cannot
identify*, and seeded `data_sensitivity: restricted` as the cautious default for
an unknown system. `CONCERNS.md` **Q11** — one sentence from the client closes it.

Encoding that honestly, rather than guessing, is the point. A backlog that
confidently ranked a system nobody can name would be worse than one that says so.

### Files

| Layer | Change |
|---|---|
| `db/migrate.py` | `connector_backlog` table + rank index |
| `repositories/connector_backlog_repo.py` | **new** — `insert`, `get_all` (rank order), `get_by_id`, `update`; `EDITABLE` excludes `id`/`system_name` |
| `services/connector_backlog.py` | **new** — vocabularies, merged-item validation, **the 90-day eligibility invariant**, derived summary |
| `seed_data/backlog_seed.py` | **new** — the SOW's 7, assessed 2026-08-05, with sources noted |
| `db/seed.py` | seeds the backlog independently, like connectors |
| `routes/connectors.py` | `GET /v1/connector-backlog` · `PATCH /v1/connector-backlog/:id` |
| `kernel/services.ts` / `api.ts` | `listConnectorBacklog`, `updateBacklogItem` |
| `types/assets.ts` | `ConnectorBacklogItem` + its five vocabularies. `BacklogTransport` deliberately excludes `sse` — it follows spec 2026-07-28, unlike `McpTransport` (see `CONCERNS.md` D8) |
| `modules/tools/ToolsPage.tsx` | fourth tab + detail drawer |

### Verified

`backend/verify_connector_backlog.py` — **43 assertions, all passing.** The
candidate set is the SOW's seven; rank ordering; the summary is derived and
matches the rows; the eligibility invariant on a direct patch, on a two-step
walk-around, and in reverse (you cannot remove the server while the system sits
in the 90 days); nine field validations including that the deprecated `sse`
transport is not a valid value here; `unknown` preserved; no-op honesty; identity
fields immutable; 404 for an unknown system and no POST route.

**It mutates seeded rows and restores them** — it captures each row it touches
and writes it back in a `finally` block, so an assertion failure still restores.
It creates nothing, so it leaves nothing behind.

No regressions: `verify_connectors.py` 51 · `verify_tool_calls.py` 58 ·
`verify_connector_crud.py` 41 · `verify_tool_governance.py` 70 ·
`verify_bound_tools_guard.py` 34 · `npm run test` 4/4 · `tsc -b --noEmit` clean ·
`npm run build` clean.

**Not verified:** the browser click-through — `CONCERNS.md` **V7**.

---

## 15. The real MCP client — Phase 5A

**This is the first code in the project that speaks MCP.** Everything in §8–§14
simulated the protocol; this section is the wire.

Target revision is **2026-07-28**, via the official Python SDK
(`mcp>=2.0,<3` — `CONCERNS.md` **Q9**, closed on measurement: v2 is the first
line supporting this revision, v1 cannot). The client asserts the negotiated
version rather than assuming it.

### The pieces

| File | Role |
|---|---|
| `backend/reference_mcp/server.py` | The **counterparty**, not the deliverable. A conformant read-only Jira-shaped server over synthetic data |
| `backend/app/services/mcp_client.py` | Pure protocol adapter. `list_remote_tools()`, `probe()`, `validate_header_annotation()`. Writes nothing to the database |
| `connector_health._discover_live()` | Persistence + governance. The only place discovery writes |
| `backend/verify_mcp_client.py` | 69 assertions across four layers |

The split matters: `mcp_client.py` touching no database is what lets the suite
run its protocol assertions **in memory**, with no port, no subprocess and no
Postgres. Only the persistence layer needs any of that.

### Why the reference server serves five tools

One listing exercises every outcome the discovery path can produce:

| Tool | Declares | Outcome |
|---|---|---|
| `jira_issue_reader`, `jira_search`, `jira_project_reader` | `readOnlyHint: true` | Accepted, `write_capable=false` — bindable once approved |
| `jira_issue_commenter` | *nothing* | Accepted, `write_capable=true` — **catalogued but never binds** |
| `bad_header_reader` | invalid `x-mcp-header` | **Rejected and excluded** from the listing, with a warning |

The last one is the reason to own the server rather than point at a public one:
the spec says a client MUST reject malformed `x-mcp-header` annotations and
exclude those tools while logging a warning, and a well-behaved public server
will never let you prove you do it.

### Three governance decisions at the boundary

A remote server is an **untrusted counterparty**. Nothing it says may widen the
permission model:

1. **`write_capable = not readOnlyHint`** — deny-by-default. A server must
   *explicitly* declare read-only. Silence means write-capable, which means
   catalogued-but-unbindable. This is the single most important line in
   `mcp_client.py`: a sloppy or hostile server produces unbindable tools rather
   than quietly bindable ones.
2. **`permission_ceiling` is always `read`.** Discovery cannot infer intent, and
   `read` is the floor of the locked advisory enum. A human widens it later.
3. **Discovery is not consent.** A discovered tool lands `pending` and
   `upsert_discovered()` hardcodes that — a client-supplied `approval_state` is
   not merged, it does not exist on this path.

**A defect the suite caught:** the first version set `pending` but queued no
approval item, so a discovered tool was visible, unbindable, and *unapprovable* —
the queue is the only route to a decision. Anything landing `pending` must also
be queued. That now happens on first discovery **and** when a write-capability
change sends an approved tool back to pending.

### Identity and idempotency

Discovered tools are `{connector_id}.{remote_tool_id}` — deterministic so
re-discovery updates rather than duplicates, namespaced so two connectors may
serve a same-named tool, and legible so origin is obvious from the id alone.

`remote_tool_id IS NULL` marks a seeded or console-authored tool. That
distinction is load-bearing: orphan detection only considers rows that were
actually advertised, so a hand-authored tool attached to a connector is never
mistaken for an orphan.

**Re-discovery preserves approval** — routine re-runs must not silently revoke a
human decision — **unless `write_capable` changed**, which is a material change
to what the tool does, so the prior approval no longer describes it.

**Orphans are reported, never deleted.** A tool can be referenced by audit rows
and tool-call history that must outlive it, and a transient outage must not
erase the catalog.

### Live vs simulated — the line that must stay visible

**`streamable_http` is the opt-in signal for real traffic**
(`connector_health.is_live_connector()`), not "the endpoint looks like a URL".

That was a bug first: the original check treated any `https://` endpoint as
reachable, and the seeded connectors carry plausible-but-unresolvable
`https://…brightspeed.internal/…` addresses — so the first healthcheck marked
every seeded connector **offline**. Gating on the spec-current transport means a
connector opts in to being contacted, and the D8 migration can land
incrementally.

The distinction is stored, not just behavioural:

- `connectors.last_probe` is non-NULL **if and only if** the most recent
  healthcheck actually reached a socket. The simulated path *clears* it rather
  than merely not writing it, so a connector that stops being live cannot keep
  presenting stale evidence.
- The UI badges every card **`live MCP`** or **`simulated`**, and shows the
  measured protocol, latency and advertised count when real.

A fabricated green tick on a connector nobody contacted is worse than no tick.

### D7 and D8

**D7 is closed.** A real `tools/list` writes tools with `connector_id` set, so
the `undiscovered`/`orphaned` diff is finally reachable — it was structurally
inert before, because nothing in the product could attach a tool to a connector.
After a live listing `undiscovered` is always empty by construction: we just
wrote everything the server advertised.

**D8 is partially closed.** `streamable_http` is added and is the default for
new connectors; `sse`/`http` remain **accepted but labelled deprecated** in both
the enum and the form, because five seeded rows carry them and dropping the
value would make existing rows unreadable and unpatchable.

### Verification

`verify_mcp_client.py` — **69 assertions** in four layers: protocol/conformance
in memory, the header validator as a unit (the malformed shapes a live server
will not produce), live Streamable HTTP probing, and persistence + governance
through the API.

**It creates real catalog rows and deletes them** (asyncpg, teardown only) —
discovery writes four tools per run, and leaving those behind would pollute the
Tool Catalog fast. It is the second suite after `verify_bound_tools_guard.py` to
clean up after itself.

The API layer **skips cleanly** if the reference server is not running, printing
the command to start it, rather than failing with a confusing connection error.

---

## 16. The policy-enforcing gateway — Phase 6

**Deck slide 21, elements 1, 4 and 5** — the MCP Gateway Pattern, Data Boundary
Controls, and the Identity & Access Pattern. The last three unbuilt cells of the
seven-element connectivity pattern.

### What actually changes

Every governance rule before this phase was enforced at **design time**.
`bind_tool()` decides what an agent may be *configured* to use; the Phase 1
audit trail records what a client *said* it then did. There was no point at
which the platform stood between an agent and a system at the moment of the
call.

`services/tool_gateway.py` is that point. One route —
`POST /v1/gateway/tool-call` — runs eleven checkpoints, deny-by-default, and
only then performs the invocation **itself**. Because it performs the
invocation, it starts its own clock and reads its own response, which is what
closes the measurement half of `CONCERNS.md` **R7**.

That last part is only reachable because Phase 5A exists. Without a real socket
there is nothing to measure, which is exactly why the phases were built in this
order.

### The checkpoint chain

Published at `GET /v1/gateway/policy` and rendered by the console from that
response — the chain is served rather than restated in TypeScript, because a
second copy is a second thing to keep in step with the enforcement, and the copy
always loses.

| # | Checkpoint | Denies when | Source |
|---|---|---|---|
| 1 | `identity` | the principal is absent or unknown | slide 21 el. 5 · Blueprint §8.1 |
| 2 | `catalog` | the tool is not catalogued | Tool Registry |
| 3 | `agent` | the agent is not registered | Agent Registry |
| 4 | `write_capable` | the tool can write | slide 25 · SOW boundary |
| 5 | `approval` | the tool is not `approved` | Blueprint §11 · Phase 3.2 |
| 6 | `allowlist` | the tool is not in the agent's `bound_tools` | R8 guard |
| 7 | `connector_health` | the serving connector is offline | Phase 0 resolver |
| 8 | `identity_binding` | the connector declares approved identities and this is not one | slide 21 el. 5 |
| 9 | `data_boundary` | the connector declares datasets and the call names none, or names one outside them | slide 21 el. 4 |
| 10 | `hitl` | the agent is on the `critical` path and no human decided this call | slide 22 |
| 11 | `rate_limit` | too many **allowed** calls for this (agent, tool) in the last 60s | Blueprint §3.4 |

**The order is load-bearing**, in three places:

- **Existence before policy.** You cannot evaluate a rule about a tool that is
  not in the catalog, and "not found" is a more useful denial than a downstream
  rule failing confusingly.
- **`write_capable` before `approval`, mirroring `bind_tool()` exactly.** An
  approved write-capable tool is denied *on write-capability*. If those two ever
  swap, approval becomes a laundering path for the locked invariant. The
  invariant now lives in two modules on purpose — design-time and run-time are
  separate gates — which also means an exception path (`CONCERNS.md` Q6) is a
  change in two places, not one.
- **`rate_limit` last.** A call denied on governance grounds never reached the
  system, so it must not consume the budget that exists to protect it.
  `count_recent()` therefore counts `gateway = TRUE AND decision = 'allow'`
  only.

### Three design decisions worth not undoing

**1. A denial is a 200 with a verdict, never a 4xx.** The gateway always writes
a row and always returns a decision. Making denials into HTTP errors would mean
the most valuable rows in the table are the ones a caller is encouraged to
swallow and retry past — and a caller could then tell a denial from a network
failure only by parsing prose. Only a request too malformed to attribute (no
agent, no tool, unknown consumer) raises, because there is then nothing truthful
to record. Same principle as `record_tool_call()` recording rather than
rejecting an unauthorized call.

**2. Empty policy means *undeclared*, not deny-all.** `allowed_datasets`,
`allowed_fields` and `approved_identities` are empty on all five seeded
connectors, and an empty list allows the call while recording the gap on the row
and on the connector card. Deny-all-until-declared is the stricter-*looking*
default and would have been enforcing a policy nobody wrote — none of those five
has a real dataset inventory behind it. A gateway that blocked everything on day
one gets switched off on day two, and that reads as a control being removed
rather than completed. Tracked as a decision in `CONCERNS.md` **Q14**; the other
eight checkpoints all have real data and deny properly.

**3. A failed live call does not cascade into connector health.** One call
failing is not a health verdict. `run_healthcheck()` owns `connectors.status`,
and letting any timeout mark a connector offline would make the catalog flap
under load — and take its served tools down with it, via the cascade.

### Two field sets, two routes, two personas

`PATCH /v1/connectors/:id` edits **how we reach** a server — name, transport,
endpoint, auth. `PATCH /v1/connectors/:id/policy` declares **what it may expose
and to whom** — datasets, fields, identities, service account, IAM principal,
rate limit, timeout.

They are disjoint, and the separation is enforced by two repository functions
that physically cannot write each other's columns (`connectors_repo.update()`
vs. `set_policy()`). An author who could widen their own data boundary is the
hole the gateway exists to close. It is the same shape as the older rule that
keeps `status` out of an author's hands, and as `tools.update_policy()` being
unable to touch `permission_ceiling`.

The audit personas differ too, deliberately: a connector edit is audited as the
**Platform Engineer**, a policy change as the **Governance Officer**. In the log
the persona is what tells the two acts apart.

### How much a row can be trusted

`tool_calls` keeps slide 21's eight fields unchanged and gains four that say how
much the row is worth:

| Row shape | Meaning |
|---|---|
| `gateway = FALSE` | client-reported — the Phase 1 path. Result and latency are claims |
| `gateway = TRUE`, `invocation = 'none'` | denied at a checkpoint; `denied_by` names which. Nothing was invoked, so `latency_ms = 0` rather than a fabricated number |
| `gateway = TRUE`, `invocation = 'simulated'` | policy fully enforced, tool body local. The **decision** is authoritative; the latency measures our own simulation |
| `gateway = TRUE`, `invocation = 'live'` | a real MCP round trip. This, and only this, is runtime evidence |

`gateway` is written `True` in exactly one function (`record_gateway_call`) and
is not settable from any payload. The Tool Calls tab labels and filters the four
shapes separately — merging them into one count is the easiest way to overclaim
this workstream, so the schema makes it awkward and the UI makes it visible.

### Identity: enforcement real, principal simulated

`principal` is a persona from the console's own switcher, not a federated IdP
subject. Both halves have to be said. Building an identity store is explicitly
out of scope — the SOW's boundary table says *"will not build a separate user
management or identity store … integrate with Brightspeed SSO / IdP"* — so the
gateway enforces a real allowlist against a simulated subject, and
`CONCERNS.md` **R6** records the rest.

### The HITL gate moved server-side

Before this phase the Playground's runtime HITL gate was client-side: denying it
merely declined to send an `ok`, which protected the UI rather than the system.
Now `governance_path = 'critical'` means the gateway denies unless the call
carries an explicit human decision, and a denial is a row. `PlaygroundPage`
passes the decision through instead of applying it.

### Files

| File | Role |
|---|---|
| `services/tool_gateway.py` | the chain, the invocation, the trace. The deliverable |
| `services/connector_policy.py` | the write side of the boundary + identity fields |
| `services/mcp_client.call_remote_tool()` | real `tools/call`, timed; a tool-level failure is data, not an exception |
| `services/tool_call_log.record_gateway_call()` | the observed-row writer; hardcodes `gateway = True` |
| `repositories/connectors_repo.set_policy()` | cannot write endpoint/status/name |
| `repositories/tool_calls_repo.count_recent()` | the rate-limit window, counted from the audit trail rather than a second store |
| `routes/gateway.py` | `POST /v1/gateway/tool-call`, `GET /v1/gateway/policy` |
| `ToolsPage.tsx` → `ConnectorPolicyPanel`, `EvidenceBadge` | declare a policy; read a row's trustworthiness |
| `PlaygroundPage.tsx` | invokes through the gateway rather than reporting afterwards |

### Verification

`verify_tool_gateway.py` — **215 assertions** in five layers: the published
policy, a denial for **every one of the eleven checkpoints** (each asserted
completely — verdict, checkpoint name, and the row it wrote), field-set
isolation between the two PATCH routes, a live invocation against the reference
MCP server with measured latency and field redaction over a real payload, and
teardown.

It creates a connector, discovered tools, an approval and a binding on a seeded
agent, and removes all of it. It **deliberately leaves its `tool_calls` rows** —
an audit trail that deletes its own evidence would be a strange thing to ship,
and those rows are the artefact the phase produces. The live layer skips cleanly
without the reference server.
