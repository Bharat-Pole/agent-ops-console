# CLAUDE.md

Working guidance for Claude Code sessions in this repo. **This file is the
session handoff: scope, rules, invariants, environment, and where we are.** It
is deliberately *not* a history — each phase is written up once, in the document
that owns it.

## Which document owns what

Read this file first, then follow the pointer. **Do not restate another
document's content here** — that is how five files drift into five answers.

| Document | Owns | Published? |
|---|---|---|
| **`CLAUDE.md`** (this) | scope, invariants, commands, environment, current state, demo gotchas | ✅ |
| **`CONCERNS.md`** | **every** open question, risk, divergence, environment trap, unverified item | ❌ internal |
| `ROADMAP.md` | the sequenced build plan; what the deck/SOW demand and in what order | ❌ internal |
| `MCP_WORKSTREAM.md` | where the workstream stands; what shipped when | ❌ internal |
| `ARCHITECTURE.md` | system design, per-phase deep dives (§8–§16), conventions, gotchas | ✅ |
| `README.md` | product framing and the demo script | ✅ |

> **The four internal documents are gitignored on purpose** — they quote the SOW
> and Week-11 commercial terms. Concern ids (**R3**, **Q13**, **V9**, …) point at
> a register a fresh clone will not have; ask the workstream owner. Everything
> needed to *build* safely is in this file and `ARCHITECTURE.md`.

## ⚠️ Standing rule: every concern goes in `CONCERNS.md`

**`CONCERNS.md` is the single register of everything unresolved** — open
questions, decisions nobody made, risks we carry, defects we chose not to fix,
environment traps, things built but never verified, problems seen in other
workstreams. Closed items stay, so the history of what worried us is preserved.

**Whenever you hit one of these, add it before you finish the turn:**

- a question you cannot answer from the code or the source documents;
- a decision you made because nobody had made it — record the decision *and*
  that it is unconfirmed;
- something wrong or risky that is out of scope to fix;
- a claim in any doc you could not verify, or found to be false;
- anything shipped that a human still needs to click through;
- a defect in another workstream you noticed in passing.

**How** (template and prefix table at the top of `CONCERNS.md`):

1. Pick the prefix — **D** divergence · **Q** question · **R** risk/defect ·
   **E** environment · **V** unverified · **X** other workstream — and take the
   **next free number**. Never reuse one, even from a closed item.
2. Fill in *What it is* / *Why it matters* / *What would close it*. The last two
   are what make it actionable months later.
3. Add the index row and update the per-status counts in the header.
4. Other docs cite **the id and one line** — never a copy.

**When a concern closes**, don't delete it: set `Status: CLOSED (date)`, write
how it closed, and add a **Carry forward** note if it leaves an invariant someone
could break later (R7 and R8 are the pattern).

## ⚠️ Active scope: the `/tools` page only

**We own the Tool Catalog and MCP Connectors surface. Nothing else.**

The console has eleven platform components; ten belong to other workstreams. Do
**not** plan, refactor, or "improve while we're here" in registry, onboarding,
prompts, knowledge/RAG, governance, evaluation, monitoring/FinOps, playground, or
A2A — **except** where a change is required to land a Tools & MCP feature.

That carve-out has been used three times and each time it stayed narrow: Phase 0
touched the onboarding wizard's tool picker, Phase 1 fired tool-call records from
`PlaygroundPage.tsx`, Phase 6 pointed that same call at the gateway. Redesigning
the Playground is still not in scope.

Commercial commitments for *this* workstream: deck **slide 21** (MCP
Connectivity Pattern, 7 elements), **slide 25** (Tool Permission Matrix),
**slide 49**, and SOW **deliverable 3.3** (Week 11). `ROADMAP.md` §1 maps them
onto the code — read it before assuming a feature is in or out.

## What this project is

Brightspeed Agent Ops & Governance Console — a Databricks-style control plane for
the lifecycle of AI agents. Core thesis: **an agent is data, not code** — every
screen is a different lens over one canonical config.

Stack: Vite + React 18 + TypeScript (strict) + Zustand + Tailwind; FastAPI +
asyncpg + Postgres/pgvector. Much of the app is a deterministic client-side
simulation (seeded PRNG, rule-based "synthesis engine"); a growing subset is
backend-persisted. **Read `ARCHITECTURE.md` §1 before assuming any entity is
server-persisted vs. client-simulated — it is not uniform.**

Server-persisted: **agents, approvals, audit log, eval packs, tools, MCP
connectors, connector backlog, tool calls, gateway policy.**
Still client-only: knowledge sources, prompts, onboarding drafts, jobs/telemetry,
provisioning + pipeline + eval animations.

**This is a local POC and the docs say so.** `README.md` has a scope banner,
`ARCHITECTURE.md` §0 sets the boundary, `ROADMAP.md` §4.0 defines build-vs-skip.
The governing rule, worth memorising:

> **Never simulate the thing being demonstrated; simulate only what sits on the
> far side of it.** Our half of the wire is real; the counterparty may be
> `localhost`.

## Commands

```powershell
docker compose up -d      # Postgres on port 5434 (NOT 5432 — CONCERNS E1)
npm run dev:client        # client on :5173  (npm run dev is broken — CONCERNS E3)
& "backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload --port 8787

npm run typecheck         # tsc -b --noEmit
npm run build             # tsc -b && vite build
npm run test              # 4 frontend kernel suites (smoke/engine/playground/causality)
```

**The local reference MCP server** — the counterparty for Phases 5A and 6. Needed
by two suites (both skip cleanly without it) and by the V8/V9 browser passes:

```powershell
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe -m reference_mcp.server --port 9100
```

**The eight backend suites** — all need a live backend:

```powershell
# ⚠️ Set this FIRST. Piped through anything, two suites die mid-run on a cp1252
# encode and look like short *passing* runs. CONCERNS E5.
$env:PYTHONIOENCODING="utf-8"

backend\.venv\Scripts\python.exe backend\verify_connectors.py          #  51
backend\.venv\Scripts\python.exe backend\verify_tool_calls.py          #  58
backend\.venv\Scripts\python.exe backend\verify_connector_crud.py      #  41
backend\.venv\Scripts\python.exe backend\verify_tool_governance.py     #  70
backend\.venv\Scripts\python.exe backend\verify_bound_tools_guard.py   #  34
backend\.venv\Scripts\python.exe backend\verify_connector_backlog.py   #  43
backend\.venv\Scripts\python.exe backend\verify_mcp_client.py          #  69  (needs :9100)
backend\.venv\Scripts\python.exe backend\verify_tool_gateway.py        # 215  (needs :9100)
```

Backend venv: `backend/.venv` (`backend\.venv\Scripts\python.exe`).

**What each suite leaves behind** — matters when one run pollutes the next:

| Suite | Cleans up? |
|---|---|
| `verify_bound_tools_guard` · `verify_mcp_client` · `verify_tool_gateway` | ✅ deletes what it creates (asyncpg teardown) |
| `verify_connectors` · `verify_connector_backlog` | ✅ normalizes on entry, restores on exit |
| `verify_tool_governance` | ✅ captures/restores the one seeded agent it mutates; self-heals a polluted baseline |
| `verify_connector_crud` | ❌ leaves `zz-verify-*` connectors (no delete endpoint) |
| `verify_tool_calls` · `verify_tool_gateway` | ❌ leaves `tool_calls` rows **by design** — an audit trail that deletes its own evidence would be a strange thing to ship |

## Non-negotiable conventions

Full detail and rationale in `ARCHITECTURE.md`. These are the rules a change can
silently break.

### Backend

- **Routes are dict-in/dict-out, no Pydantic models.** Errors are always
  `{"message": "..."}`. Status: 201 create / 200 ok / 400 validation / 404 not
  found / 503 external service not configured / 502 upstream failure.
- **JSONB columns**: the asyncpg pool has a codec registered — pass and receive
  plain Python dicts. Never `json.dumps`/`json.loads` in a repo file.
- **No migration framework.** `db/migrate.py` is one idempotent DDL string.
  Widening a table needs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

### Frontend

- **Real backend calls use a local `useState` loading boolean.** The
  `kernel/jobs.ts` job queue is ONLY for fixed-duration client-simulated
  animations (provisioning, pipeline runs, the rule-based onboarding "synthesis"
  engine). Don't mix the two patterns.
- **`kernel/services.ts` is the only façade for backend calls**, re-exported
  through `kernel/api.ts`. Follow the `postJson` + toast pattern used by
  `bindTool` / `createTool` / `callToolThroughGateway`.
- **Seed snapshot**: `backend/app/seed_data/seed_snapshot.json` is generated from
  the TS seed, not hand-edited. To add a key, write a temporary `*.tmp.ts` at the
  repo root importing from `@/seed/*`, run it with `npx tsx`, then delete it.

### The governance invariants — read these before touching tools or MCP

1. **`ToolPermission` is a locked 5-value advisory enum** (no `write` member).
   `write_capable` tools are catalogued but must never bind **or be called**.
   Enforced server-side independent of client input; any new
   tool/permission-touching feature must re-validate server-side too.
   *Two independent sources agree with this enum (deck slide 25 and Blueprint
   §3.4) — **do not change it.*** Three client-facing documents use three
   permission vocabularies; that is the documents disagreeing, not the code
   (**Q8**).

2. **Health and consent are different columns.** `tools.status` is operational
   health, owned solely by the connector cascade. `tools.approval_state` is
   consent, owned solely by the approval queue. Neither may write the other's
   column. A tool can be `available` *and* `pending` — that pairing is the
   feature, not a bug.

3. **`write_capable` is checked *before* `approval_state`** — in `bind_tool()`
   **and** in the gateway. Approving a write-capable tool must never make it
   bindable or callable. The invariant now lives in two modules on purpose;
   changing only one produces a tool that cannot be bound but can be called.

4. **Bind guard (R8).** Any route that writes `config.tooling.bound_tools` must
   run it through `services/bound_tools_guard.py` first. There are three today;
   a fourth **calls the guard rather than re-deriving the rules**. It strips
   rather than rejects, and every strip leaves evidence.

5. **A tool is never healthier than the connector that serves it.** Connector
   status is authoritative; tool status is **derived** by
   `services/connector_health.py`. Never set `tools.status` from a client or from
   anywhere except the cascade. Tools with `connector_id = NULL` are local and
   must be left alone (5 of 12 seeded tools are local).

6. **`last_probe` is non-NULL iff the last healthcheck reached a socket.** The
   simulated path *clears* it. The UI badges `live MCP` vs `simulated` off this.
   A fabricated green tick is worse than no tick.

7. **`write_capable = not readOnlyHint`** for discovered tools — deny by default.
   A remote server must *explicitly* declare read-only. Silence means
   catalogued-but-unbindable. A server we do not control must not be able to
   widen our permission model.

8. **Discovery is not consent.** Discovered tools land `pending`, hardcoded in
   `upsert_discovered()`. **And anything landing `pending` must also be queued
   for approval** — the first version did not, leaving tools visible, unbindable
   and *unapprovable*. The suite caught it.

9. **`streamable_http` is the opt-in signal for real traffic**, not "the endpoint
   looks like a URL". An earlier check probed any `https://` and marked every
   seeded connector offline, because their `…brightspeed.internal` endpoints were
   never meant to resolve.

10. **Orphans are reported, never deleted.** Audit and tool-call history outlive
    the tool, and a transient outage must not erase the catalog.

### The gateway invariants (Phase 6)

11. **`tool_calls.gateway = True` is written in exactly one function**
    (`record_gateway_call`) and is settable from no payload. It is what separates
    an **observed** row from a **reported** one. A second writer reopens **R7**.

12. **A gateway denial is a 200 with a verdict, never a 4xx.** The gateway always
    writes a row and always returns a decision. Only a request too malformed to
    attribute raises. Denials are the rows worth having.

13. **Authoring and policy are disjoint field sets on disjoint routes.**
    `PATCH /v1/connectors/:id` edits *how we reach* a server;
    `PATCH /v1/connectors/:id/policy` declares *what it may expose and to whom*.
    Two repository functions that cannot write each other's columns. An author
    who could widen their own data boundary is the hole the gateway closes.

14. **Empty policy means *undeclared*, not deny-all** — and the gap is recorded
    on every call rather than passing silently. The reasoning is `CONCERNS.md`
    **Q14**; changing it needs a decision *and* a real dataset inventory.

15. **`bound_tools` is the per-agent allowlist.** We deliberately did **not** add
    an `allowed_agents` column — two lists encoding the same fact drift. See
    **Q7** for why, and for why it still wants a stakeholder nod.

## Local environment

Detail lives in `CONCERNS.md`; these are the one-liners plus what to do.

| Id | Trap |
|---|---|
| **E1** | A native Windows Postgres squats on 5432. **The project's Postgres is on 5434** in `docker-compose.yml` and `.env`. Confirmed working — if a fresh clone hits `InvalidPasswordError`, check the port first |
| **E2** | `backend/.venv` was once machine-specific. On `No Python at '...'`, delete and rebuild: `python -m venv backend\.venv` then `pip install -r backend\requirements.txt` |
| **E3** | **`npm run dev` does not start the backend** and does not fail loudly — you get a Vite banner and a page talking to nothing. Start the two legs separately |
| **E4** | **Both model providers are out of credits.** A 400 *with* a `request_id` means billing, not a missing key (401 = bad key, 503 = unconfigured) |
| **E5** | **Set `$env:PYTHONIOENCODING="utf-8"` before running the suites.** Piped, two of them die mid-run and look like short passing runs |
| **R1** | **No browser automation.** Backend suites + typecheck are the real verification; UI click-throughs need a human. Don't install a heavy toolchain without asking |
| **R3** | `.env` holds provider keys and is gitignored. **`.env.example` is committed and must contain placeholders only** — it once held live keys verbatim, and `start.ps1` copies it to `.env` by design |
| **R4** | The repo is its own git repo on branch `soham/tools-mcp`. **The parent `Documents/Projects` repo is a different repo — never push that remote from here.** `*.docx/pptx/pdf/xlsx` are gitignored (the signed SOW was found in the project root); do not narrow that rule |
| **R6** | **No auth or CORS layer. Run on localhost only; do not deploy or expose as-is** |

**On E4 specifically — what still works.** No governance path touches a model.
Catalog, permission matrix, approval, policy fields, connector CRUD, healthcheck,
the cascade, discovery, the backlog and **the entire gateway** are model-free.
Tool calls and refusals never reach the chat endpoint
([services.ts:483](src/kernel/services.ts#L483)), so the audit-trail and gateway
demos work with zero credits. Two things break: Playground chat falls back
*silently* to placeholder text, and **New tool → Suggest** renders the raw 400 on
screen. Fill the form by hand — `canCreate` needs only `name` + `category`.

**OpenAI is not an approved provider** (SOW: *"agents available within Vertex
AI"*), so E4 is a scope constraint as well as a billing one, and it applies to
the Anthropic calls too. Fine for a local POC — the SOW explicitly blesses
sandbox/mock approaches — but **do not present the current model layer as the
target** (**R5**).

## Where we are — 2026-08-11, Phase 6 shipped

**Slide 21 is 6 of 7 elements complete.** The seventh, *Reusable Tool Adapters*,
is partial **by contract rather than by omission**: the pattern is built and
proven end-to-end, and applying it to the other six systems is Phase 8, which the
SOW scopes out of the 90 days.

| Phase | What | Shipped | Detail |
|---|---|---|---|
| 0 | Connector resolution — the tool→connector edge, walked once | 08-03 | `ARCHITECTURE.md` §9 |
| 1 | Tool-call audit trail (slide 21 el. 6) | 08-03 | §10 |
| 2 | Connector CRUD (Blueprint §3.5) | 08-04 | §11 |
| 3 | Permission matrix, tool approval, policy fields (slide 25) | 08-05 | §12 |
| — | The `bound_tools` guard — R8 | 08-05 | §13 |
| 4 | Connector prioritization backlog (slide 21 el. 7) — recommends **Jira** | 08-05 | §14 |
| 5A | **The real MCP client**, spec 2026-07-28 | 08-10 | §15 |
| 6 | **The policy-enforcing gateway** (slide 21 el. 1, 4, 5) | 08-11 | §16 |

### Phase 6 in one paragraph

Every rule before it was enforced at *design time*: `bind_tool()` governs what an
agent may be **configured** to use, and the Phase 1 trail recorded what a client
**said** it did. `services/tool_gateway.py` is the first point at which the
platform stands between an agent and a system **at the moment of the call** —
one route, eleven checkpoints, deny-by-default, and the gateway performs the
invocation itself. Because it does, `result_status` and `latency_ms` are observed
rather than reported.

**The claim this earns, stated exactly:** *"authoritative for every call that
passes through the gateway."* Three row shapes keep that honest and they are in
the data, not a footnote — `gateway = FALSE` is client-reported;
`invocation = 'simulated'` means the decision was real and the tool body was not;
`invocation = 'live'` is a real MCP round trip and is the only runtime evidence.
**Never merge the three into one count.**

### Status — all green

8 backend suites, **581 assertions** (51 · 58 · 41 · 70 · 34 · 43 · 69 · 215) ·
`npm run test` 4/4 · `tsc -b --noEmit` clean · `npm run build` clean.

**Not verified:** any of it in a browser. **`CONCERNS.md` V1–V9** hold the
click-through scripts, one per phase — V9 is Phase 6's.

## Next steps

**`ROADMAP.md` §4 has the plan. Phase 7 is next, and it is the last phase this
workstream can build.**

1. **Phase 7 — the MCP Gateway view** (slide 21 element 1's *diagram*; the
   enforcement shipped in Phase 6). Agents → gateway → connectors → systems, with
   the checkpoints marked. Read-only over what already exists: Phase 0's resolver
   for edges, `GET /v1/gateway/policy` for the chain, `tool_calls?gateway=true`
   for traffic. **No new tables and no new enforcement** — if it needs either,
   something upstream was left unfinished.

Everything after that is gated on someone other than us:

| | Gated on |
|---|---|
| **Phase 5B** — point the client at a real Brightspeed system. Access-gated, **not** engineering-gated | **Q10** (Atlassian Cloud or on-prem — cheapest to answer and the only one that can invalidate Jira as the target), **Q13** (ranking sign-off), **R9** (tenant, OAuth app, credentials — longest lead, open in parallel) |
| **Phase 8** — connector expansion | the SOW scopes it out of the 90 days |
| **Q6 / D4 / D5** — the write-exception cluster, one question wearing four ids | a governance decision |
| **Q14** — strict-by-default data boundaries | a governance decision **plus** a real dataset inventory per connector |

**The signal to watch for on 5B:** it should be small — swap an endpoint, add an
auth mode, run the same `tools/list`. If it turns out large, Phase 5A leaked POC
assumptions past the seam.

## Two things not to overclaim

- **R6 — there is no auth or CORS layer.** Run on localhost only; do not deploy
  or expose as-is. Hardening belongs to the deployment layer (API Gateway/IAM per
  Blueprint §6), not this workstream, and is recorded so nobody assumes it is
  handled.
- **Identity: enforcement is real, the principal is simulated.** The gateway
  enforces a genuine allowlist against a console persona, not a federated IdP
  subject. Say both halves. Building an identity store is explicitly out of scope
  (SOW: *"will not build a separate user management or identity store"*).

## What the SOW and deck actually say

Both were read directly on 2026-08-05 and re-read 2026-08-11; every prior claim
about them had been second-hand. They live outside this repo (office documents
are gitignored). Both are OOXML — unzip and parse `word/document.xml` /
`ppt/slides/slideN.xml`; no dependencies needed.

**Two things this workstream believed that were wrong:**

1. ❌ *"The SOW commits to a working connector at Week 11."* It does not.
   Acceptance for MCP is *"Internal connectivity strategy and priority connector
   model **defined**"*, and slide 18's Day-90 evidence is an *"MCP and tool
   registry **strategy package**"*. The SOW asks for working artifacts elsewhere
   — Runtime is *"demonstrated or implementation-ready"* — so the softer wording
   is deliberate. **Do not re-assert the working-connector claim.** (We have
   built more than this, which is fine; the point is not to misquote the
   contract.)
2. ❌ *"Q5 is a blocking question someone owes us."* Neither document names a
   priority connector. **Slide 21's seventh element is the artifact that answers
   it** — the answer is our deliverable, and Phase 4 produced it.

**Two hard boundaries that constrain the work:**

- *"Will **install and configure MCP servers only**; building new MCP servers is
  out of scope"* → only systems with an **existing** MCP server are eligible. Of
  the SOW's seven, that is **Jira, Confluence, GitHub, BigQuery**. ServiceNow,
  MDR and CCAI have none, so they cannot be the reference connector — enforced
  server-side in the backlog, not just documented.
- *"Produce implementation-ready patterns and use **sandbox/mock/stub approaches
  until access is approved**"* — **the local reference server is the prescribed
  treatment**, not a shortcut. Stop apologising for it.

**The MCP spec, revision 2026-07-28.** **There is no `initialize`** — it is a
legacy-era handshake, and the protocol is now stateless with
`_meta.io.modelcontextprotocol/*` per request. Sessions and the GET stream
endpoint were removed; only `stdio` and **Streamable HTTP** remain standard, and
HTTP+SSE is deprecated — which our `sse://` seed and `McpTransport` enum still
contradict (**D8**, partially closed: `streamable_http` is added and defaulted,
`sse`/`http` remain readable so existing rows stay patchable).

## Demo gotchas

These cost time to rediscover.

**Getting the Playground to emit a tool call is fiddly** — three gates in
`kernel/playground.ts` `classify()`, and missing any one silently yields no
`toolCalls`, hence no row:

1. **The agent must be `live` (or `demo_mode`) AND have bound tools.** HR Policy
   Bot and Field Ops FAQ Bot have **none** — they can never produce a tool call.
   Incident Response Coordinator has four but is `approved`, not live.
2. **The message must contain the tool id or its _first_ token** — `incident`,
   `log`, `health`, `jira`, `confluence`, `crm`, `capacity`, `filing`. The word
   **"reader" matches nothing**.
3. **It must not be question-shaped.** `classify()` returns `grounded_answer`
   before the tool branch for anything starting with
   what/how/which/summarize/show/list/when/why/who/give/tell, or ending in `?`,
   when RAG is on. And no write verb, or it becomes a `refusal`.

Two that work:
- **NOC Incident Summarizer** (live, standard) → `check incident_reader`.
- **Regulatory Filing Coordinator** (live, **critical**) → `check filing_reader`
  → runtime HITL gate. Best demo: **Approve** and **Deny** produce both outcomes
  from one feature, and since Phase 6 the deny is enforced *server-side* at the
  `hitl` checkpoint rather than by the UI declining to send.

**A write-intent *refusal* is deliberately not logged.** It returns
`toolCalls: []` — no tool was named, so there is nothing truthful to put in
`tool_invoked`. Fabricating a row for a nicer demo would be fabricating an audit
record. Don't "fix" this.

**There is no bind button in the UI.** `api.bindTool` is exported but no
component calls it — binding is reachable only over the API. Worth raising
separately: a Tool Catalog with no way to bind is a real gap, but it is the
registry/catalog UI's, not this workstream's.

```powershell
# Bind (or watch a governed refusal + a `blocked` row with consumer = console)
curl.exe -s -X POST http://127.0.0.1:8787/v1/agents/agt-incident-response-coordinator-20260205-c3d9/tools/bind -H "Content-Type: application/json" -d "{\"toolId\":\"ticket_updater\"}"

# The gateway, end to end. A denial is a 200 with allowed:false — check the body,
# not the status code.
curl.exe -s -X POST http://127.0.0.1:8787/v1/gateway/tool-call -H "Content-Type: application/json" -d "{\"agentId\":\"agt-noc-incident-summarizer-20260122-b2e7\",\"toolId\":\"incident_reader\",\"principal\":\"platform_engineer\"}"

# The backlog's contract term with teeth — HTTP 400 quoting the SOW's wording.
curl.exe -s -X PATCH http://127.0.0.1:8787/v1/connector-backlog/servicenow -H "Content-Type: application/json" -d "{\"phase\":\"day_90\"}"
```

**Two things that read like bugs but are not:**

- **`sse` accepts `http(s)://` endpoints.** MCP's SSE transport *is* an HTTP
  endpoint streaming events; `https://host/sse` is the canonical form. The seed's
  uniform `sse://` makes the rule look stricter than it is. **Don't tighten it** —
  a verification assertion got this wrong once already.
- **No connector delete endpoint.** Tools reference connectors via
  `connector_id` and `tool_calls` via `system_accessed`. Retirement belongs with
  lifecycle states, not a delete button.
