# CLAUDE.md

Guidance for Claude Code sessions working in this repo. Read this first, then
**`CONCERNS.md`** (every open question, risk and loose end — see the rule
below), `MCP_WORKSTREAM.md` (where the workstream stands), `ROADMAP.md` (what
the deck demands and in what order we build it), `ARCHITECTURE.md` for the deep
dive (system design, conventions, gotchas), and `README.md` for the product
framing / demo script.

> **Note on the companion documents.** `CONCERNS.md`, `ROADMAP.md` and
> `MCP_WORKSTREAM.md` are **internal and not published to this repository** —
> they quote the SOW and carry commercial detail. Only this file,
> `ARCHITECTURE.md` and `README.md` ship. References to concern ids (**R3**,
> **R6**, **Q13**, …) therefore point at a register you will not find in a
> clone; ask the workstream owner for it. Everything needed to *build* safely —
> the invariants, conventions and environment traps — is in this file and
> `ARCHITECTURE.md`.

## ⚠️ Standing rule: every concern goes in `CONCERNS.md`

**`CONCERNS.md` is the single register of everything unresolved about this
project** — open questions, product decisions nobody has made, risks we are
carrying, known defects we chose not to fix, environment traps, things built but
never verified, and problems observed in other workstreams. Closed items stay in
it, so the history of what worried us and how it resolved is preserved.

**Whenever you hit one of these, add it to `CONCERNS.md` before you finish the
turn:**

- a question you cannot answer from the code or the source documents;
- a decision you made because nobody had made it — record the decision *and*
  that it is unconfirmed;
- something you found that is wrong or risky but is out of scope to fix;
- a claim in any doc you could not verify, or found to be false;
- anything shipped that a human still needs to click through;
- a defect in another workstream you noticed in passing.

**How** (full template and prefix table at the top of `CONCERNS.md`):

1. Pick the prefix — **D** divergence · **Q** question · **R** risk/defect ·
   **E** environment · **V** unverified · **X** other workstream — and take the
   **next free number**. Never reuse one, even from a closed item; ids are cited
   across documents.
2. Fill in *What it is* / *Why it matters* / *What would close it*. The last two
   are what make it actionable months later.
3. Add the index row, bump **Last updated** and the open/closed counts.
4. Other docs cite **the id and one line** — never a copy of the entry. If you
   catch yourself restating a concern in `ROADMAP.md` or `MCP_WORKSTREAM.md`,
   replace it with a link.

**When a concern closes**, do not delete it: set `Status: CLOSED (date)`, write
how it closed, and add a **Carry forward** note if it leaves behind an invariant
someone could break later (see R8 for the pattern).

## ⚠️ Active scope: the `/tools` page only

**We own the Tool Catalog tab and the MCP Connectors tab. Nothing else.**

The console has eleven platform components; ten of them belong to other
workstreams. Do **not** plan, refactor, or "improve while we're here" in
registry, onboarding, prompts, knowledge/RAG, governance, evaluation,
monitoring/FinOps, playground, or A2A — **except** where a change is required to
land a Tools & MCP feature (e.g. Phase 1 fires a tool-call record from
`PlaygroundPage.tsx`; that is in scope, redesigning the Playground is not).

The commercial commitments for *this* workstream are deck **slide 21** (MCP
Connectivity Pattern, 7 elements), **slide 25** (Tool Permission Matrix), **slide
49**, and SOW **deliverable 3.3** (Week 11). `ROADMAP.md` §1 maps them onto the
code — read it before assuming a feature is in scope or already done.

## What this project is

Brightspeed Agent Ops & Governance Console — a Databricks-style control plane
for the lifecycle of AI agents (registry, onboarding, tools/MCP, knowledge/RAG,
governance, evaluation, monitoring, playground). Core thesis: **an agent is
data, not code** — every screen is a different lens over one canonical config.

Stack: Vite + React 18 + TypeScript (strict) + Zustand + Tailwind on the
frontend; FastAPI + asyncpg + Postgres/pgvector on the backend. Much of the
app is a deterministic client-side simulation (seeded PRNG, rule-based
"synthesis engine"); a growing subset of entities is real backend-persisted.
**Read `ARCHITECTURE.md` §1 before assuming any given entity is
server-persisted vs. client-only-simulated — it is not uniform across the app.**

Server-persisted today: **agents, approvals, audit log, eval packs, tools,
MCP connectors, connector backlog.**
Still client-only: knowledge sources, prompts, onboarding drafts,
jobs/telemetry, provisioning + pipeline + eval animations.

## Commands

```powershell
docker compose up -d      # Postgres on port 5434 (NOT 5432 — see gotcha below)
npm run dev:client        # client on :5173  (see CONCERNS E3 — `npm run dev` is broken)
& "backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload --port 8787
npm run typecheck         # tsc -b --noEmit
npm run build             # tsc -b && vite build
npm run test              # 4 frontend kernel suites (smoke/engine/playground/causality)

backend\.venv\Scripts\python.exe backend\verify_connectors.py   # 51 backend assertions (needs a live backend)
backend\.venv\Scripts\python.exe backend\verify_tool_calls.py   # 58 backend assertions (needs a live backend)
backend\.venv\Scripts\python.exe backend\verify_connector_crud.py  # 41 backend assertions (needs a live backend)
backend\.venv\Scripts\python.exe backend\verify_tool_governance.py # 70 backend assertions (needs a live backend)
backend\.venv\Scripts\python.exe backend\verify_bound_tools_guard.py # 34 backend assertions (needs a live backend)
backend\.venv\Scripts\python.exe backend\verify_connector_backlog.py # 43 backend assertions (needs a live backend)
```

Backend venv: `backend/.venv` (Windows: `backend\.venv\Scripts\python.exe`).

**⚠️ `npm run dev` does not start the backend** (measured 2026-08-06 — an
earlier version of this file claimed it did; that was wrong. `CONCERNS.md`
**E3**). The `dev:server` script's forward-slash path
(`backend/.venv/Scripts/python`) is not resolvable by `cmd.exe`, and
concurrently shells out to `cmd.exe` too — so the server leg dies with
`'backend' is not recognized...` while the **client leg comes up anyway**. You
get a Vite banner and a page that loads, talking to nothing. Start the two legs
separately (both commands are in the block above) until `package.json` is fixed.

## Non-negotiable conventions (see ARCHITECTURE.md for full detail + why)

- **Backend routes**: dict-in/dict-out, no Pydantic models. Errors are always
  `{"message": "..."}`. Status codes: 201 create / 200 ok / 400 validation /
  404 not found / 503 external service not configured / 502 upstream failure.
- **JSONB columns**: the asyncpg pool has a codec registered — pass/receive
  plain Python dicts, never `json.dumps`/`json.loads` yourself in a repo file.
- **No migration framework**: `db/migrate.py` is one idempotent DDL string.
  Widening an existing table needs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- **Governance invariant**: `ToolPermission` is a locked 5-value advisory
  enum (no `write` member); `write_capable` tools are catalogued but must
  never bind. Enforced **server-side** independent of client input — any new
  tool/permission-touching feature must re-validate server-side too.
- **Tool governance invariant** (Phase 3): a tool has **two independent
  states**. `status` is operational health, owned solely by the connector
  cascade. `approval_state` is consent, owned solely by the approval queue.
  Neither may write the other's column, and `bind_tool()` checks
  `write_capable` **before** `approval_state` — approving a write-capable tool
  must never make it bindable.
- **Bind guard invariant** (R8): any route that writes
  `config.tooling.bound_tools` must run it through
  `services/bound_tools_guard.py` first. There are three today; a fourth calls
  the guard rather than re-deriving the rules. Binding through the config is
  otherwise a silent way around `bind_tool()`.
- **MCP invariant**: *a tool is never healthier than the connector that serves
  it.* Connector status is authoritative; tool status is **derived** by
  `services/connector_health.py`. Never set `tools.status` from a client or
  from anywhere except the cascade. Tools with `connector_id = NULL` are local
  and must be left alone (5 of 12 seeded tools are local).
- **Frontend async UX**: real backend calls (`register`, `chatWithAgent`,
  `createTool`, `suggestTool`, `healthcheck`, `toggleConnectorOffline`) use a
  local `useState` loading boolean. The `kernel/jobs.ts` job queue is ONLY for
  fixed-duration client-simulated animations (provisioning, pipeline runs, the
  onboarding "synthesis" engine — which is rule-based, not a real AI call
  despite looking like one). Don't mix the two patterns.
- **`kernel/api.ts`/`kernel/services.ts`**: the only façade for backend calls.
  New calls go in `services.ts` (follow the `postJson` + toast pattern used by
  `bindTool`/`createTool`) and get re-exported through `api.ts`.
- **Seed snapshot**: `backend/app/seed_data/seed_snapshot.json` is generated
  from the TS seed, not hand-edited. To add a key, write a temporary
  `*.tmp.ts` at the repo root that imports from `@/seed/*`, run it with
  `npx tsx`, then delete it (that is how `connectors` was added).

## Known local environment issues

**1. Postgres port.** A native Windows PostgreSQL service (`postgresql-x64-18`)
squats on 5432 and silently shadows the project's container. The project's
Postgres is therefore on **5434** in both `docker-compose.yml` and `.env`.
**This is confirmed working** — the backend boots, migrates, and seeds cleanly
against it. If a fresh clone hits `asyncpg.exceptions.InvalidPasswordError`,
check the port mapping first. See `ARCHITECTURE.md` §6.

**2. The venv is machine-specific.** `backend/.venv` was originally created on
a different developer's machine and hardcoded their Python path, so it failed
with `No Python at '...'`. It has been rebuilt locally. **If you see that
error, delete `backend/.venv` and rebuild:**

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

**3. No browser automation.** No Playwright/headless-chromium is installed.
Backend suites + typecheck are the real verification; UI click-throughs must be
done by a human. Don't install a heavy toolchain for this without asking.

**4. Secrets.** `.env` holds the provider API keys and is gitignored.
**`.env.example` is committed and must contain placeholders only** — it once
held real keys verbatim, and `start.ps1` copies it to `.env` by design. Key
handling and rotation status are tracked in the internal concerns register
(**R3**), not here.

**4a. OpenAI is not an approved provider (confirmed from the SOW, 2026-08-05),
and the account has no credits (confirmed 2026-08-03).** The SOW's boundaries
table constrains the model layer to *"**agents available within Vertex AI**, not
external agent frameworks"*, and rules out assuming OpenAI API usage. So this is
a **scope** constraint as well as a billing one, and it applies to the Anthropic
calls too. Fine for a local prototype — the SOW explicitly blesses sandbox/mock
approaches — but do not present the current model layer as the target.
`ROADMAP.md` R5.

Every
`rag_enabled` agent's Playground chat returns **502**, and the UI silently falls
back to the placeholder text *"Retrieving relevant context and drafting a
grounded answer…"* (`kernel/services.ts` → `if (!ok || !data) return base`).

```
[chat] Error code: 429 - 'You have no credits remaining' / credit_balance_exhausted
POST /v1/agents/<rag-agent>/chat → 502 Bad Gateway
```

Chain: `routes/chat.py` → `retrieve_for_agent()` → `services/embeddings.py`
→ OpenAI `text-embedding-3-small`. **Anthropic is fine** — agents with
`rag_enabled = false` (HR Policy Bot, Field Ops FAQ Bot) still return real
Claude answers, which is the tell that this is billing, not code.

Unaffected: tool calls and refusals never reach this endpoint
(`chatWithAgent` returns early for those kinds), so the Phase 1 audit trail
demo works regardless.

**Observation, not ours to fix:** a failed *retrieval* takes down the *whole*
chat. `chat.py` wraps retrieval and the Claude call in one `try`, so no-credits
on embeddings loses an answer Claude could still have given un-grounded.
Degrading to `kind: "general_answer"` would be more robust. Knowledge/RAG
workstream's call.

**5. The repo IS under version control now (2026-08-06).** This folder is its
own standalone git repo, pushed to the team remote as branch `soham/tools-mcp`
(`https://github.com/Bharat-Pole/agent-ops-console`). `CONCERNS.md` **R4** has
the detail. Four things follow:

- **The parent `Documents/Projects` repo is a different repo** holding ML Orion,
  RGM Fashion, A2A and Kaggle work. Never push that remote from here.
- **The published repo is public and excludes the docs.** `CLAUDE.md`,
  `ROADMAP.md`, `CONCERNS.md` and `MCP_WORKSTREAM.md` are gitignored on purpose —
  they quote the SOW and Week-11 commercial terms. Only `ARCHITECTURE.md` and
  `README.md` ship. **A fresh clone cannot resume development**; these four files
  travel by the same channel as the SOW.
- **`*.docx/pptx/pdf/xlsx` are gitignored** — the signed SOW was found in the
  project root during the pre-push scan. Do not narrow that rule.
- **`.env.example` must contain placeholders only.** It is committed, and it
  previously held both live keys verbatim (`CONCERNS.md` R3).

There is an undo now, but history starts at `7bfc3d6` — nothing before
2026-08-06 is recoverable.

## Where we left off (2026-08-05 — Phases 0–4 shipped)

### Phase 4 — Connector prioritization backlog (slide 21 element 7)

**Slide 21 is now 3 of 7 complete.** The SOW's seven systems of record, assessed
and ranked, as a 4th tab on `/tools`. Detail in `ARCHITECTURE.md` §14.

**Result:** Jira (1), Confluence (2), GitHub (3), BigQuery (4) in the first 90
days — the four with existing first-party MCP servers. ServiceNow (5), CCAI (6),
MDR (7) later, all `blocked`. **Recommended reference connector: Jira.**

**The invariant — a contract term with teeth.** A system with **no existing MCP
server cannot be scheduled into the 90-day phase**, because the SOW says
*"install and configure MCP servers only; building new MCP servers is out of
scope."* Enforced server-side against the **merged** item, so two patches cannot
walk around it. Same shape as the `write_capable` floor: a document's constraint
expressed as code, not a comment.

**Four things to not weaken:**
1. **No POST route.** The candidate set is the SOW's seven; extending it is a
   contract change, not a UI action.
2. **`recommended` is derived** (rank 1 of the 90-day set), never stored — so it
   cannot drift from the ranking it summarises.
3. **`unknown` ≠ `none`.** ServiceNow is `none`; CCAI and MDR are `unknown`
   because we looked and could not confirm. Do not collapse them.
4. **MDR stays in the backlog, ranked last.** Neither source document expands
   the acronym — it cannot be assessed, and saying so is the honest output.

**Honest limits:** the ranking is ours and unconfirmed (`CONCERNS.md` **Q13**),
MDR is unidentified (**Q11**), CCAI's server availability is unverified (**Q12**).

**Status — all green:** `verify_connectors.py` 51 · `verify_tool_calls.py` 58 ·
`verify_connector_crud.py` 41 · `verify_tool_governance.py` 70 ·
`verify_bound_tools_guard.py` 34 · `verify_connector_backlog.py` 43 ·
`npm run test` 4/4 · `tsc -b --noEmit` clean · `npm run build` clean.

---

## Phase 3 and the R8 guard (2026-08-05)

### Phase 3 — Tool governance (slide 25 · Blueprint §3.4/§11)

The Tool Catalog could say what a tool *is* and how healthy it *is*, but not
whether anyone had ever agreed to it. Detail in `ARCHITECTURE.md` §12.

- **3.1 Permission matrix** — `PERMISSION_MATRIX` in `kernel/constants.ts` + a
  toggle panel on the Tool Catalog rendering slide 25's nine rows. Presentation
  only; nothing reads it for enforcement. **Closes D1.**
- **3.2 Tool approval** — `services/tool_approval.py`, the **shared** queue
  widened (`entity_type`/`entity_id`; `agent_id` and `required_by_path` now
  nullable), and a second server-side guard in `bind_tool()`. **Closes D3/Q1.**
- **3.3 `owner` + `risk_level`** + `PATCH /v1/tools/:id`. **D6 is now ◐** —
  nine of Blueprint §3.4's eleven fields are still unbuilt, deliberately.
- `backend/verify_tool_governance.py` — **70 assertions.**

**Deviation from the roadmap, on purpose:** the plan said "a `pending_approval`
state on `tools`". It shipped as a **separate `approval_state` column**, because
`tools.status` is owned end-to-end by the connector health cascade and would
overwrite a pending state the moment a connector flapped. Health and consent are
different questions about a tool. Don't merge them back.

**Four things to not weaken:**
1. **Approval is not a write exemption.** `write_capable` is checked *first* and
   independently. An approved write-capable tool still does not bind — otherwise
   approval becomes a laundering path for the locked invariant. Q6 is the
   decision to change that; it is *not* a code tweak, and Phase 3 made it a
   two-line change, which is exactly why it needs a decision.
2. **Cataloguing is not consent.** A console-created tool is `pending`; a
   client-supplied `approval_state` is *ignored, not merged*.
3. **The seeded 12 are grandfathered `approved`** via the column default. Do not
   "fix" this by retro-queueing them.
4. **A rejected tool is not deleted.** It stays catalogued, visible and
   unbindable — same principle as write-capable tools being catalogued.

**Note:** `verify_tool_governance.py` is the **only suite that mutates a seeded
agent** — proving an approved tool *binds* writes to the Incident Coordinator's
`bound_tools`, which `verify_connectors.py` asserts is exactly 4. It captures
and restores that config, and strips stale `zz-verify-` refs from its baseline
on entry so an interrupted run self-heals. It still leaves `zz-verify-*` tools
and their approval items behind (no tool delete endpoint).

**Status — all green:** `verify_connectors.py` 51 · `verify_tool_calls.py` 58 ·
`verify_connector_crud.py` 41 · `verify_tool_governance.py` 70 ·
`verify_bound_tools_guard.py` 34 · `npm run test` 4/4 · `tsc -b --noEmit` clean ·
`npm run build` clean. (The tool-call and CRUD suites print higher than the
47/40 recorded when they were written — loop-driven assertions, not new checks;
neither changed in Phase 3.)

---

## Phases 0, 1 and 2 (2026-08-03 / 2026-08-04)

### The Product Blueprint (read this before re-planning anything)

Management shared **Agent Ops & Governance Platform — Product Blueprint** (27pp)
on 2026-08-04. **Reconciled in `ROADMAP.md` §7** — read that, not the PDF, and
do not re-derive it. Headline: it **validates the architecture rather than
changing it.** Phases 0–2 need no rework.

Three things it settled:
1. **The permission model is right.** §3.4 gives the same 9 values as deck
   slide 25 (5 allowed / 4 blocked). Two independent sources now agree with the
   locked enum — **D1 closed. Still do not change the enum.**
2. **Tool approval is real** (§11 Approval Queue) — old Q1 answered *yes*, and
   it is a **shared platform object**. Phase 3.2 must reuse the existing
   `approvals` machinery, not invent a tool-local state.
3. **Connector CRUD is MVP-critical** (§3.5 capability #1, §10 MVP screen) —
   which is why Phase 2 was built next.

Three new open items, all decisions rather than tickets: **Q6** (do write tools
get a human-approved exception path? §3.4 permits it, our invariant forbids it —
**sharper after Phase 3**, since the machinery now exists), **Q7**
(`allowed_agents` — ours or Governance's?), and **Q3 got worse** (deck's
7 connectors vs. Blueprint's 8 — they disagree; do not guess).

### Phase 2 — Connector CRUD (Blueprint §3.5)

Register/edit an MCP server from the MCP Connectors tab. Detail in
`ARCHITECTURE.md` §11.

- `services/connector_authoring.py` + `POST /v1/connectors` /
  `PATCH /v1/connectors/:id`. Four author-owned fields only:
  `name`, `transport`, `endpoint`, `auth_mode`.
- **Register MCP server** button + one `ConnectorModal` for create *and* edit;
  pencil affordance on `ConnectorCard`.
- `backend/verify_connector_crud.py` — **40 assertions.**

**Two invariants to not weaken:**
1. **Status is owned by the health cascade, never by an author.** Not accepted
   on create or update, and `connectors_repo.update()` physically cannot set it.
   An author who could set connector status could launder tool status too.
2. **`tools_provided` is a claim, not a binding.** Registering a connector
   creates **no tools**.

**Correction (external review, 2026-08-04):** an earlier version of this section
claimed a new connector finally makes `undiscovered` non-empty. **It does not.**
A fresh connector advertises nothing, so **Discover tools** on it returns
entirely empty — `verify_connector_crud.py` asserts that. And
`tool_authoring.create_tool()` hardcodes `connector_id: None` with nothing ever
setting it, so **no tool created through the product can be attached to a
connector**. The discovery diff is structurally unreachable until a real
`tools/list` writes discovered tools. Tracked as `ROADMAP.md` **D7**.

**Two things that read like bugs but are not:**
- **`sse` accepts `http(s)://` endpoints.** MCP's SSE transport *is* an HTTP
  endpoint streaming events; `https://host/sse` is the canonical form. The seed's
  uniform `sse://` makes the rule look stricter than it is. **Don't tighten it** —
  a verification assertion got this wrong once already.
- **No delete endpoint.** Tools reference connectors via `connector_id` and
  `tool_calls` via `system_accessed`. Retirement belongs with lifecycle states.

**Note:** `verify_connector_crud.py` **leaves `zz-verify-*` connectors behind**
(no delete). They sort last and are obvious. It also invalidated a pre-existing
assertion — `verify_connectors.py` asserted `len(connectors) == 5`, quietly
encoding "connectors are seed-only", which is exactly what Phase 2 ended. It now
asserts the 5 seeded ids are *present*.

---

## Phases 0 and 1 (2026-08-03)

### Phase 1 — Tool-Call Audit Trail (deck slide 21, element 6)

**`/tools` now has a third tab.** The page covers permissions (Catalog) →
connectivity (MCP Connectors) → **evidence** (Tool Calls). Detail in
`ARCHITECTURE.md` §10.

- `tool_calls` table with slide 21's eight fields verbatim + `permission`, `at`.
  Indexed `(agent_id, at DESC)` and `(tool_invoked, at DESC)`. **No FK to
  `agents`** — a trail outlives its subject, same as `audit_log`.
- `tool_call_log.py` — `record_tool_call`, `record_blocked_bind`,
  `list_tool_calls`. `POST`/`GET /v1/tool-calls`.
- Playground fires records with real measured latency; `ToolsPage` renders the
  tab with agent/tool/result filters.
- `backend/verify_tool_calls.py` — **47 assertions.**

**Three invariants to not weaken:**
1. **`system_accessed`, `permission`, `at` and _authority_ are never taken from
   the client.** Resolved via Phase 0's resolver, the server's own `tools`
   table, the server clock, and the agent's own `bound_tools` respectively. A
   supplied value is *ignored*, not merged. Most of the suite exists to hold
   this line.

   **Authority check (added 2026-08-04, external review).** A claimed
   `resultStatus: ok` for a tool the agent was never bound to is **overridden to
   `blocked`**, server-side, reason recorded. It records rather than rejects —
   refusing the write would destroy the evidence of the thing worth catching.
   `record_blocked_bind()` deliberately bypasses it: a *bind attempt* is by
   definition for an unbound tool.

   **Honest limit:** `result_status` and `latency_ms` remain client-supplied.
   In a client-simulated Playground there is no server-side invocation to time
   or observe failing, so they have no server-side truth. **Do not describe this
   trail as authoritative runtime evidence** — it becomes that in Phase 5, when
   calls run through the gateway. `ROADMAP.md` R7.
2. **Blocked attempts are logged.** A rejected write-capable bind
   (`consumer = console`) and a denied HITL gate. That is the whole point —
   the advisory-only invariant as evidence, not a silent reject.
3. **Local tools log `system_accessed = NULL`.** Never a placeholder.

**A deliberate non-feature:** a write-intent *refusal* is **not** logged. It
returns `toolCalls: []` — no tool was named, so there is nothing truthful to
put in `tool_invoked`. Fabricating a row for a nicer demo would be fabricating
an audit record. Don't "fix" this.

**Note:** `verify_tool_calls.py` is append-only and **leaves rows behind** by
design. It mutates no connector or tool state.

---

### Phase 0 — Connector resolution

**Connector resolution.** The tool→connector edge (a fixed FK on the tool row —
"which MCP?" is a **lookup, never a choice**) was never walked anywhere in the
codebase. Phase 0 walks it once, server-side, and feeds four gates from that one
derivation. Detail in `ARCHITECTURE.md` §9; plan-of-record in `ROADMAP.md` §4
Phase 0.

Shipped:
- `services/connector_resolution.py` + `GET /v1/agents/:id/connectors` — the
  agent's MCP dependency set (`connectors[]` with the tools each serves,
  `local_tools`, `unknown_tools`, `offline`, `unhealthy`). No schema change.
- `tool_binding.py` gained `_health_warning()` — an unhealthy connector returns
  `{"ok": true, "warning": …}` and writes the warning into the audit detail.
- `usePreflight(toolIds?)` — check #4 scoped to the connectors a draft's tools
  resolve to, and the label names the offline connector.
- `ToolPicker.tsx` (new) replaces free-text `TagInput` on Phase 1's Tools field;
  `McpDependencies.tsx` (new) renders the resolved set on Phase 4.
- `verify_connectors.py` **24 → 51 assertions**, plus starting-state normalization.

**The one design call to not undo: _bind warns, deploy blocks._** Binding is a
design-time declaration; connector health is a runtime condition. Do **not** add
an `ok: false` health branch to `bind_tool()` — the only blocking check there is
`write_capable`.

**Status — all green:**
- `verify_connectors.py` **51/51** · `verify_tool_calls.py` **47/47** ·
  `verify_connector_crud.py` **40/40**.
- `npm run test` — 4/4 · `tsc -b --noEmit` clean · `npm run build` clean.

**Two things worth knowing:**
1. **`verify_connectors.py` was not re-runnable** against a dirty DB. `toggle-offline`
   *flips*; a connector left offline by a UI click inverted 17 assertions with no
   code defect behind them. It now normalizes on entry and restores what it found.
2. **0.2 landed narrower than planned.** `usePreflight()` runs at two call sites
   that both execute *before any tool is chosen* (`OnboardingPage`, and
   `PreFlightPhase` at phase `pre`), so platform-wide stays the honest fallback.
   The genuinely agent-scoped signal is `McpDependencies` on Phase 4.

**Scope note:** Phase 0 touched `src/modules/onboarding/` (Phase 1 picker,
Phase 4 panel, Pre-Flight). That is the same carve-out `ROADMAP.md` Phase 1 uses
for firing tool-call records from `PlaygroundPage.tsx` — required to land a
Tools & MCP feature, **not** a licence to work on onboarding.

**Not verified:** a browser click-through of any of it (no browser tooling).

---

## The MCP session before it (2026-07-31)

**Moved MCP connectors server-side**, closing the split that opened when tools
became backend-persisted but connectors stayed a browser-memory simulation —
unstable because tool status derives from connector health. Full detail in
`ARCHITECTURE.md` §8; roadmap in `MCP_WORKSTREAM.md`.

Shipped:
- `connectors` table + `connectors_repo` + seed (5 connectors, `jira` degraded).
- `services/connector_health.py` — server-side cascade, healthcheck (~18%
  degraded, moved from the client), toggle-offline, `list_connector_tools`.
- 3 endpoints under `/v1/connectors/:id/` (`healthcheck`, `toggle-offline`,
  `tools`); `/v1/bootstrap` now returns `connectors`.
- Frontend: `healthcheck`/`toggleConnectorOffline` are real async calls;
  `listConnectorTools` added; `ConnectorCard` extracted with local loading
  state and a **Discover tools** panel showing the `undiscovered`/`orphaned`
  diff; Tool Catalog gained the spec-required **status column** plus
  status/connector filters.
- `backend/verify_connectors.py` — 24-assertion backend suite.

**Status — all green:**
- `backend/verify_connectors.py` — 24/24 pass against a live backend, including
  cascade persistence across a refetch (proves it is in Postgres, not memory).
- `npm run test` — 4/4 frontend suites pass.
- `tsc -b --noEmit` clean; `npm run build` clean.
- Postgres port-5434 fix **confirmed working** (was the previous session's top
  open question).

**Not verified:** a live browser click-through of the Tools page — the status
column, the Discover-tools panel, and the connector toggle cascading visibly
into the catalog. No browser tooling available; this is a known constraint, not
an oversight.

**Behaviour change to be aware of:** healthchecks no longer appear in the
TopBar job tray, because the call moved off `kernel/jobs.ts` onto the
real-backend-call pattern. That is correct and consistent with `createTool` —
not a regression.

## Planning session — 2026-07-31 (no code changed)

Read the codebase against the deck and the SOW and rewrote **`ROADMAP.md`** as
the Tools & MCP build plan: slide-21/25/49 → code gap analysis, four divergences
needing a product decision, a seven-phase plan with schemas and file lists, and
an appendix of out-of-scope observations so they are not rediscovered.

**Where slide 21 stands: 3 of its 7 elements are green.** Tool Permission Model
✅, Reusable Tool Adapters ◐, Identity & Access ◐ — and **Tool-Call Audit Trail,
Data Boundary Controls, MCP Gateway Pattern, and Connector Prioritization
Backlog are all untouched.**

**The permission-model divergence is a presentation gap, not a model gap.** Deck
slide 25 is a 9-row matrix; the code has a locked 5-value enum plus a
`write_capable` boolean. The code is *stronger* than the deck describes — an
invalid permission is a type error and `tool_binding.py` re-reads its own table
rather than trusting the client. **Do not change the enum.** Add a view that
renders the deck's 9 rows and shows how each maps to the implementation.

Baseline confirmed green: `tsc -b --noEmit` clean.

## 📌 2026-08-05 — the SOW and deck were read directly for the first time

Every prior claim about them was second-hand. The two source files are the SOW
(`.docx`) and the deck (`.pptx`), held outside this repo — office documents are
gitignored. Both are OOXML: unzip and parse `word/document.xml` /
`ppt/slides/slideN.xml`; no extra dependencies needed.

**Two things this workstream believed were wrong:**

1. ❌ **"The SOW commits to a *working* connector at Week 11."** It does not. SOW
   acceptance for MCP is *"Internal connectivity strategy and priority connector
   model **defined**"*, and deck slide 18's Day-90 evidence is an *"MCP and tool
   registry **strategy package**"*. The SOW asks for working artifacts elsewhere
   — Runtime is *"demonstrated or implementation-ready"* — so the softer wording
   for MCP is deliberate. **Do not re-assert the working-connector claim.**
2. ❌ **"Q5 is a blocking question someone owes us."** Neither document names a
   priority connector — five generic mentions across both. Deck slide 21's
   seventh element, *"identify which systems should be connected in the first 90
   days versus future phases"*, **is the artifact that answers it.** The answer
   is our deliverable, and we had scheduled it last.

**Two hard boundaries that constrain the work:**

- *"**Will install and configure MCP servers only; building new MCP servers is
  out of scope**"* → only systems with an **existing** MCP server are eligible.
  Of the SOW's 7, that is **Jira, Confluence, GitHub, BigQuery**. ServiceNow,
  MDR and CCAI have none, so they cannot be the reference connector.
- *"Produce implementation-ready patterns and use **sandbox/mock/stub approaches
  until access is approved**"* — **the simulated MCP layer is the prescribed
  treatment**, not a shortcut. Stop apologising for it.

**Two questions closed, one opened:**
- ✅ **Q3/D2** — *"Jira, GitHub, Confluence, ServiceNow, MDR, CCAI, and BigQuery
  remain authoritative systems"*. The deck's 7 win; the Blueprint's "Internal
  APIs" is the deck's "internal applications" catch-all.
- ⚠️ **New Q8** — slide 21 says `retrieve`, the SOW says `classify`, slide 25
  (the *Detailed* matrix the enum follows) has neither. Three vocabularies in
  three client-facing documents. **Do not widen the enum** — it is the documents
  that disagree, not the code.

**Also read that day: the MCP spec at revision 2026-07-28.** The old Phase 4
plan said *"real `initialize` + `tools/list`"*. **There is no `initialize`** —
it is a legacy-era handshake, and the protocol is now stateless with
`_meta.io.modelcontextprotocol/*` per request. Sessions and the GET stream
endpoint were removed; only `stdio` and **Streamable HTTP** remain standard, and
HTTP+SSE is deprecated — which our `sse://` seed and `McpTransport` enum
contradict. Anyone writing client code must read `ROADMAP.md` Phase 5 first.

## R8 — the `bound_tools` guard (found and closed 2026-08-05)

**`bind_tool()` was the governed way a tool becomes bound, not the only way.**
Three routes persisted client-supplied `config.tooling.bound_tools` with no
validation: `POST /v1/agents/register`, the config-sync `PATCH /v1/agents/:id`,
and `POST /v1/agents/:id/config-change`. Verified by experiment — 201 with a
write-capable *and* a pending tool bound, bypassing the locked invariant and
Phase 3's approval gate. Design in `ARCHITECTURE.md` §13.

**Fixed with strip + audit** (the user's call, 2026-08-05).
`services/bound_tools_guard.py` is now the **single place that decides what may
be bound** — `sanitize_bound_tools()` called from all three routes. Reasons:
`not_in_catalog` / `write_capable` / `not_approved`, in `bind_tool()`'s order.

**Four things to not weaken:**
1. **A fourth write path calls this guard — it does not re-derive the rules.**
   That is the whole point of the module.
2. **Strip, don't reject.** A bad ref must not fail a registration; the
   synthesis engine proposes tools heuristically, and rejecting would dead-end
   an onboarding run over a tool nobody hand-picked.
3. **Every strip leaves evidence** — `strippedTools[]`, a `bind_stripped` audit
   event, and one `blocked` tool-call row per ref. Silent stripping would be
   worse than the bug.
4. **No de-duplication on the PATCH path.** An earlier draft suppressed "repeat"
   syncs and swallowed real evidence — it could not tell a first attempt from a
   repeat. The premise was wrong anyway: the client adopts the sanitized config,
   so a genuine re-sync has nothing to strip.

**`verify_bound_tools_guard.py` — 34 assertions**, and the **only suite that
deletes what it creates** (asyncpg, teardown only): it must register real
agents, and leftovers would pollute the Registry and the Home page counts.

## Two things not to overclaim

Full list in `ROADMAP.md` §6 / `MCP_WORKSTREAM.md` §7 (same numbering in both).
These two are the ones a session could accidentally misrepresent in a demo:

- **R6 — the auth and CORS layer is not implemented yet.** This is a local
  prototype: **run it on localhost only, and do not deploy or expose it as-is.**
  Hardening belongs to the deployment layer (API Gateway/IAM per Blueprint §6)
  — **not this workstream's** — and is recorded so nobody assumes it is handled.
  Detail in the internal concerns register (**R6**).
- **R7 — `tool_calls` is not yet authoritative runtime evidence.** Authority
  *is* server-checked, but `result_status`/`latency_ms` are client-reported.
  Closes in the Phase 6 gateway. Say "governed tool-call trail", not
  "tamper-proof runtime evidence".

## Next steps

See **`ROADMAP.md` §4** for the full plan with schemas and file lists, and **§7**
for the Blueprint reconciliation. **Phases 0–3 are done. Phase 4 is next and is
NOT blocked.**

1. ~~**Tool-Call Audit Trail**~~ — shipped 2026-08-03 (slide 21 element 6).
2. ~~**Connector CRUD**~~ — shipped 2026-08-04 (Blueprint §3.5).
3. ~~**Permission matrix, tool approval, tool policy fields**~~ — shipped
   2026-08-05 (slide 25, Blueprint §3.4/§11).
4. ~~**Connector prioritization backlog**~~ — shipped 2026-08-05 (slide 21
   element 7). Recommends **Jira**.
5. **Phase 5 — one real read-only MCP connector.** Phase 4 named the connector;
   what remains before code is **stakeholder sign-off on the ranking**
   (`CONCERNS.md` Q13) and **access** (R9) — open the access request in parallel,
   it is the long-lead item. Also fixes **D7**. **Read `ROADMAP.md` Phase 5
   before writing any client code** — the MCP spec has no `initialize` handshake
   any more, and our `sse://` seed is on a deprecated binding (**D8**). Decide
   the SDK-vs-hand-rolled question (**Q9**) after checking whether the SDK
   supports revision 2026-07-28. The client is protocol code and can be built
   against a local reference server before access lands.

### ⚠️ Phases 4–7 were reordered on 2026-08-04

**The real MCP client moved from Phase 7 to Phase 4, ahead of the gateway view**
(external review; I agreed). Reasons in `ROADMAP.md` §4, but in short: **SOW
deliverable 3.3 commits to a working reference connector at Week 11**, the old
Phase 6 note already said "build after the checkpoints are real", and **D7 makes
discovery structurally inert** until something real writes `tools_provided`.

New order: **3** matrix/approval → **4** one real read-only MCP connector
end-to-end (fixes D7; target **Streamable HTTP**, not legacy SSE) → **5**
policy-enforcing gateway (merges the old data-boundary + identity phases;
server-generated audit closes R7) → **6** gateway view → **7** backlog +
expansion.

**Q5 is now the blocking question** — Phase 4 cannot start until someone names
the SOW's "priority reference connector".

**Browser pass on Phase 4 (never verified — `CONCERNS.md` V7).** `/tools` →
**Connector Backlog** → seven rows in rank order, **Jira** badged *recommended*,
summary reading *4 in the first 90 days · 3 deferred*. Open **ServiceNow**'s
drawer and confirm the red explanation that it has no existing MCP server.
There is deliberately **no UI control** to move it into the 90 days; prove the
server refuses:

```powershell
curl.exe -s -X PATCH http://127.0.0.1:8787/v1/connector-backlog/servicenow -H "Content-Type: application/json" -d "{\"phase\":\"day_90\"}"
```

→ HTTP 400 quoting the SOW's out-of-scope wording. Then open **MDR** and confirm
it says the acronym is never expanded in either source document.

**Browser pass on Phase 3 (never verified).** `/tools` → **Tool Catalog** →
click **Permission matrix**: nine rows, the last four shaded and badged *not
allowed*, and the blocked rows showing **one** shared count (`3 (all 4)`), not
four counts. Then **New tool** → describe something read-only → **Suggest** →
confirm a `risk_level` comes back pre-filled → create it. The toast should say
*pending approval*, the row should show a **pending** badge with an
**available** status beside it (two different axes — that pairing is the
feature, not a bug), and the amber banner should count it. Now go to
**Governance → Approvals** as the **Governance Officer** persona: the tool item
appears in its own *Tool Catalog* card, above the agent cards, with no
governance-path line. **Approve** → the badge flips and a toast says *now
bindable*. Finally open the tool's drawer, set an **owner** and a **risk level**,
**Save**, and confirm the toast names the changed fields.

**Browser pass on the R8 guard (never verified).** Catalogue a read-only tool
and leave it **pending**. Start a new agent in the wizard → Phase 1 → type its
name in the Tools field: the suggestion should carry an amber
**`pending — not bindable yet`** badge, and the chip after picking it should be
amber with a clock icon (a `write_capable` tool still shows the red WRITE badge
— write is checked first). Pick it anyway, plus a normal tool, and register.
Expect a **warn** toast, not the usual green one:

> Registered <name>. 1 tool not bound: `<tool>` (pending approval).

Then confirm the agent's Registry page shows only the legitimate tool bound,
Governance → Audit has a **`bind_stripped`** event, and `/tools` → **Tool Calls**
filtered to `blocked` has a row for the stripped tool with the reason in the
detail. Finally approve the tool in Governance → Approvals and re-add it — this
time it should bind with no warning.

To see the rejection path without the UI (there is still no bind button —
see below), create a tool and then:

```powershell
curl.exe -s -X POST http://127.0.0.1:8787/v1/agents/agt-incident-response-coordinator-20260205-c3d9/tools/bind -H "Content-Type: application/json" -d "{\"toolId\":\"<the-new-pending-tool-id>\"}"
```

→ HTTP 400, message names approval, and a **blocked** row appears on the Tool
Calls tab with `consumer = console`.

**Browser pass on `/tools` (still never verified).** Toggle `gcp-ticketing`
offline on the MCP Connectors tab → switch to Tool Catalog, filter by that
connector → confirm its 3 tools show `offline` → **hard-refresh and confirm they
are still offline** (that is the proof the cascade is persisted, not local
state). Then click **Discover tools** and confirm the panel renders.

**Browser pass on Phase 0 (never verified either).** With `gcp-ticketing` still
offline: open the Incident Coordinator's wizard → **Phase 4** → the *MCP
dependencies* panel should list **GCP Ticketing (offline)** and **Jira
(degraded)**, plus "2 local tools need no connector", and a red line naming the
offline connector. Then **Phase 1** → type in the Tools field and confirm the
typeahead dropdown shows each tool's connector badge, that a nonsense name gets
a **not in catalog** chip, and that a `write_capable` tool is still selectable
with the red WRITE badge. Finally bind a `gcp-ticketing` tool from the Tool
Catalog and confirm a **warn** toast (not an error, and the bind succeeds).

**Browser pass on Phase 2 (never verified either).** `/tools` → **MCP
Connectors** → **Register MCP server** → name `ServiceNow`, transport `http`,
endpoint `https://mcp.servicenow.brightspeed.internal/v1` → confirm the card
appears as **connected** with an empty *tools provided*. Switch transport to
`stdio` in the form first and confirm the endpoint hint changes to a command.
Then click **Discover tools** on the new card and confirm it returns **entirely
empty** — no tools, no `undiscovered`, no `orphaned`. That is correct today
(`ROADMAP.md` D7), not a bug. Finally click the **pencil** on any card, rename
it, and confirm the toast names the changed fields.

**Browser pass on Phase 1 (never verified either).** `/tools` → **Tool Calls**
tab → confirm the table renders the eight slide-21 columns, that a local tool
shows **"local — no MCP"** rather than a blank, and that the three filters
(agent / tool / result) work.

**There is no bind button in the UI.** `api.bindTool` is exported through
`kernel/api.ts` but **no component calls it** — the bind path is reachable only
over the API. So the rejected-bind row cannot be produced by clicking; generate
it with:

```powershell
curl.exe -s -X POST http://127.0.0.1:8787/v1/agents/agt-incident-response-coordinator-20260205-c3d9/tools/bind -H "Content-Type: application/json" -d "{\"toolId\":\"ticket_updater\"}"
```

then filter Tool Calls to `blocked` and confirm `consumer = console`. Worth
raising separately: a Tool Catalog with no way to bind a tool is a real gap,
but it is the registry/catalog UI's, not this workstream's.

**Getting the Playground to actually emit a tool call is fiddly** — three gates
in `kernel/playground.ts` `classify()`, and missing any one silently yields no
`toolCalls`, hence no row:

1. **The agent must be `live` (or `demo_mode`) AND have bound tools.** HR Policy
   Bot and Field Ops FAQ Bot have **none** — they can never produce a tool call.
   Incident Response Coordinator has four but is `approved`, not live.
2. **The message must contain the tool id or its _first_ token** — `incident`,
   `log`, `health`, `jira`, `confluence`, `crm`, `capacity`, `filing`. The word
   **"reader" matches nothing**, so the old hint *"use the reader tool"* never
   worked (that string is now fixed in `PlaygroundPage.tsx` too).
3. **It must not be question-shaped.** Step 2 of `classify()` returns
   `grounded_answer` before the tool branch for anything starting with
   what/how/which/summarize/show/list/when/why/who/give/tell, or ending in `?`,
   when RAG is on. And no write verb, or it becomes a `refusal`.

Two that work:
- **NOC Incident Summarizer** (live, standard) → `check incident_reader`
  → logs `ok` immediately.
- **Regulatory Filing Coordinator** (live, **critical**) → `check filing_reader`
  → runtime HITL gate → **Approve** logs `ok`, **Deny** logs `blocked`. Best
  demo: both result statuses from one feature.
