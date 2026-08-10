# Tools & MCP Workstream

**Owner:** Soham — owns **both** the Tool Catalog and the MCP Connectors surface, so there is no cross-team ownership boundary to negotiate here.
**Spec reference:** Master Build Spec §9.5, §8.4, §10 seam #1
**Commercial reference:** *Agent Ops Brightspeed* deck — slide 21 (MCP Connectivity Pattern), slide 25 (Tool Permission Matrix), slide 49 (Tools & MCP product capability)
**Last updated:** 2026-08-11
**Also measured against:** *Agent Ops & Governance Platform — Product Blueprint*
(27pp, shared 2026-08-04). Reconciled in `ROADMAP.md` §7 — it **validates** the
architecture, confirms the permission model, answers the tool-approval question,
and promotes connector CRUD to MVP-critical.

---

## 0. POC scope — what we build, what we skip *(set 2026-08-10)*

**This is a local-machine POC and the target is maximum capability coverage
within that constraint.** The SOW prescribes the approach — *"produce
implementation-ready patterns and use sandbox/mock/stub approaches until access
is approved"* — so a local counterparty is the specified treatment, not a
shortcut. Full reasoning in `ROADMAP.md` §4.0.

**The rule:** never simulate the thing being demonstrated; simulate only what
sits on the far side of it.

### Build now — nothing external gates these

| Capability | Phase | Why it is fully real locally |
|---|---|---|
| MCP client, spec 2026-07-28 | 5A | Protocol code. Identical against local or remote |
| Real `tools/list`, discovery **writing** tools | 5A | Closes **D7** genuinely |
| Malformed-definition exclusion | 5A | Our discovery layer validates and excludes, with a warning |
| Real healthcheck probing a live socket | 5A | Replaces the ~18% random roll for connectors that have one |
| Transport migration off deprecated `sse` | 5A | Closes **D8** while nothing real depends on it |
| ~~Policy-enforcing gateway~~ | 6 | ✅ shipped 2026-08-11 — every check was our own logic, as predicted |
| ~~**Server-generated audit**~~ | 6 | ✅ shipped — a real socket made latency measured and failure observed. **R7 closed inside the boundary** |
| ~~Data boundary controls~~ | 6 | ✅ shipped — field/dataset allowlists enforced by us |
| ~~Gateway view~~ | 7 | ✅ shipped 2026-08-11 — read-only over what 5A and 6 made real, exactly as scoped |

### Skip for now — and say so plainly rather than faking it

| Skipped | Why | How it is handled instead |
|---|---|---|
| Pointing at a real Brightspeed system | Needs tenant, OAuth app, credentials | **Phase 5B**, gated on Q10/Q13/**R9** |
| Real business data | No access, and none should be sought for a POC | Reference server serves synthetic Jira-shaped records |
| Real IAM principals | Needs an IdP and app registration | Persona switcher. **Enforcement is real, the principal is not** — state both halves |
| Auth layer / CORS / perimeter | Deployment layer, not this workstream | **R6**, recorded so nobody assumes it is handled |
| Vertex AI model layer | Needs GCP | **R5**; never present the current model layer as the target |
| Production-scale performance | A laptop is not a load test | Never claimed |
| Connector expansion beyond the reference | SOW scopes it out of the 90 days | **Phase 8**, ordered by the Phase 4 backlog |

**The signal that this went wrong:** if Phase 5B turns out to be large, Phase 5A
leaked POC assumptions past the seam. 5B should be small — swap an endpoint, add
an auth mode, run the same `tools/list`.

---

## 1. Where this workstream stands

| Layer | State |
|---|---|
| Tool catalog CRUD | ✅ backend-persisted, with AI-assisted authoring (`POST /v1/tools/suggest`) |
| Advisory-only enforcement | ✅ **server-side** trust boundary in `tool_binding.py` |
| MCP connectors | ✅ backend-persisted (this session) |
| Connector → tool health cascade | ✅ server-side, persisted |
| MCP `tools/list` + discovery diff | ✅ **real** — Phase 5A, spec 2026-07-28 over the wire; discovery **writes** tools (D7 closed) |
| Real MCP client + reference server | ✅ Phase 5A — `mcp>=2.0,<3`; malformed `x-mcp-header` definitions rejected and excluded |
| Real healthchecks | ✅ Phase 5A — `streamable_http` connectors are probed; `last_probe` distinguishes real from simulated |
| Agent → connector resolution | ✅ Phase 0 — `GET /v1/agents/:id/connectors`, one place that walks the tool→connector edge |
| Tool-call audit trail | ✅ Phase 1 — slide 21's 8 fields, third tab on `/tools` |
| Connector CRUD | ✅ Phase 2 — register/edit an MCP server (Blueprint §3.5 capability #1) |
| Permission matrix view | ✅ Phase 3 — slide 25's 9 rows with the implementation mapping |
| Tool approval | ✅ Phase 3 — the shared approval queue, plus a 2nd guard in `bind_tool()` |
| Tool policy fields | ◐ Phase 3 — `owner` + `risk_level` of Blueprint §3.4's eleven |
| Data boundary controls | ✅ Phase 6 — per-connector datasets deny a call, fields redact the response |
| Identity / IAM mapping | ✅ Phase 6 — `approved_identities` enforced per call; **principal is a persona, not an IdP subject** |
| Policy-enforcing gateway | ✅ Phase 6 — 11 checkpoints, deny-by-default; result + latency **observed** |
| MCP gateway view | ✅ Phase 7 — 5th tab on `/tools`; pure derivation, no new tables |
| Connector prioritization backlog | ✅ Phase 4 — 7 systems ranked, 4th tab on `/tools`; recommends **Jira** |

## 2. The deck's MCP promise vs. reality

Slide 21 defines a seven-element MCP Connectivity Pattern. Current status:

| Slide 21 element | Status |
|---|---|
| **Tool Permission Model** | ✅ locked 5-value advisory enum, enforced server-side — and since Phase 3 **legible**: slide 25's 9-row matrix renders on the Tool Catalog |
| **Reusable Tool Adapters** | ◐ the pattern is complete and proven end-to-end once; **breadth across the seven systems is Phase 8, scoped out of the 90 days by the SOW** |
| **Tool-Call Audit Trail** | ✅ all 8 fields; `system_accessed`/`permission`/`at`/authority resolved server-side; blocked attempts logged. **Phase 6 makes `result_status`/`latency_ms` observed for gateway rows — R7 closed within its stated boundary** |
| **Data Boundary Controls** | ✅ Phase 6 — `allowed_datasets` denies the call, `allowed_fields` redacts the response. Undeclared ≠ deny-all (**Q14**) |
| **Identity & Access Pattern** | ✅ Phase 6 — `approved_identities` enforced per call, `service_account`/`iam_principal` recorded. **Enforcement real, principal simulated** |
| **MCP Gateway Pattern** | ✅ Phase 6 the enforcement + Phase 7 the view. Slide 21's headline element, complete |
| **Connector Prioritization Backlog** | ✅ Phase 4 — the SOW's 7 systems of record assessed and ranked, with the no-server-no-90-days rule enforced server-side |

**Naming mismatch — RESOLVED 2026-08-05.** The SOW's boundaries table settles it: *"**Jira, GitHub, Confluence, ServiceNow, MDR, CCAI, and BigQuery** remain authoritative systems"* — the deck's 7 exactly, and slide 21 adds *"and internal applications"* as a catch-all (which is what the Blueprint calls "Internal APIs"). Our seed has `gcp-ticketing`, `confluence`, `jira`, `crm-readonly`, `filings-gateway` — overlap is Jira and Confluence only. Renaming seed IDs ripples into `seed_snapshot.json` and other suites, so schedule it rather than slipping it in.

**A hard scope boundary found the same day:** *"**Will install and configure MCP servers only; building new MCP servers is out of scope**"* → *"install/configure approved/**existing** MCP servers; backlog custom MCP server creation."* Of the 7, only **Jira, Confluence, GitHub and BigQuery** have an existing first-party MCP server. ServiceNow, MDR and CCAI would each need one built, which the SOW puts out of scope.

## 3. The data model — facts worth knowing

### A tool does *not* require a connector

The relationship is **optional many-to-one**. Verified against seed:

| | Count | Tools |
|---|---|---|
| Served by a connector | **7** | `incident_reader`, `confluence_reader`, `jira_reader`, `crm_reader`, `filing_reader`, `slack_notifier`, `ticket_updater` |
| `connector_id: null` (local) | **5** | `log_reader`, `health_checker`, `contract_reader`, `capacity_api_reader`, `email_sender` |

This matters because the health cascade must skip local tools. The intuition *"an MCP server exists, therefore its tools exist"* describes the **MCP protocol** correctly but not this platform: the Tool Catalog is a **superset** of every governed capability, and MCP is one delivery mechanism among several.

### Two concerns, one page

| | Tool Catalog tab | MCP Connectors tab |
|---|---|---|
| Question | *What are agents allowed to do?* | *How do we reach the systems?* |
| Concern | Governance / permissions | Connectivity / infrastructure |
| Persona | Governance Officer | Platform Engineer |
| Deck slide | 25 | 21 |

They currently share `/tools` as two tabs. If they are ever split into separate pages, note that the split is a **presentation** decision, not a data-model one — both read the same store and the same backend.

### The edge is a lookup, not a choice

A tool's `connector_id` is set when the tool is **catalogued** and never
recomputed — there is no routing, scoring, or failover between MCP servers, and
that is deliberate. Slide 21 element 6 (*log the system accessed*) and element 4
(*declare which datasets an agent may reach*) both require the edge to be static
and auditable ahead of a run; dynamic connector choice would trade a governance
property for a runtime convenience nobody asked for.

Three things people mean by "dynamic MCP", and where each stands:

| | Wanted? | State |
|---|---|---|
| Dynamic **discovery** (`tools/list` at runtime) | yes | ◐ endpoint live, reads the catalog — real RPC is §5.3 |
| Dynamic **tool calling** (LLM picks a bound tool per message) | yes | ✅ normal agent behaviour |
| Dynamic **connector choice** (pick between MCP servers) | not yet | ❌ needs two connectors fronting the *same* system first — the seed's 5 have zero overlap |

The third becomes real only for same-system duplicates (`crm-us` / `crm-eu` for
data residency, primary/failover, dev/prod). Even then it is routing **by rule**,
not selection by fitness. Don't build the machinery before the duplicates exist.

## 4. What shipped

### 2026-08-11 — Phase 7, the MCP gateway view *(slide 21 element 1's picture)*

**The last phase this workstream builds.** Detail in `ARCHITECTURE.md` §17.

- `GET /v1/gateway/graph` + a 5th tab on `/tools`. Agents → gateway → connectors
  → systems, each route drawn as **two** curves so it passes *through* the
  checkpoint stack rather than jumping it; stroke colour carries connector
  health; clicking an agent isolates its routes.
- **Pure derivation — no new tables, no new enforcement, no persisted state.**
  The test for any future change here: if it needs to store something, the phase
  before it was left unfinished.
- The checkpoint column carries **real denial counts** aggregated over
  `gateway = TRUE` rows. They are traffic, not illustration.
- **Local tools are counted, never given a placeholder node**, and agents with no
  route still appear with zero edges. A tidier picture that misrepresents the
  estate is worse than an honest gap.
- **It found R12 on its first run:** 77 connectors, 72 of them `zz-verify-*`
  residue. Every list view sorts those to the bottom where nobody scrolls; this
  is the first surface that renders all connectors at once.
- `verify_tool_gateway.py` **215 → 233 assertions**. A read-only view can drift
  from what it depicts and still render beautifully, so layer 2b asserts
  *consistency with the source*, not shape.

### 2026-08-11 — Phase 6, the policy-enforcing gateway *(slide 21 elements 1, 4, 5)*

**The phase where the platform starts standing between an agent and a system at
the moment of the call.** Everything before it governed *configuration*. Detail
in `ARCHITECTURE.md` §16.

- **`services/tool_gateway.py`** — one route, `POST /v1/gateway/tool-call`,
  **eleven checkpoints**, deny-by-default: identity · catalog · agent ·
  write_capable · approval · allowlist · connector_health · identity_binding ·
  data_boundary · hitl · rate_limit. The chain is published at
  `GET /v1/gateway/policy` and the console renders it from there rather than
  restating it.
- **The gateway performs the invocation itself**, so `result_status` and
  `latency_ms` are observed rather than reported. **R7 is closed inside its
  stated boundary** — and the boundary is in the data, not a footnote:
  `gateway = FALSE` is client-reported, `invocation = 'simulated'` means the
  decision was real and the tool body was not, `invocation = 'live'` is a real
  MCP round trip. Only the third is runtime evidence.
- **Data boundary (element 4)** — `allowed_datasets` denies the call,
  `allowed_fields` redacts the response and records what was dropped.
- **Identity (element 5)** — `approved_identities` enforced per call;
  `service_account` and `iam_principal` recorded. **Enforcement real, principal
  simulated**; both halves must be said.
- **The HITL gate moved server-side.** It was client-side before, which meant
  denying it declined to send an `ok` — it protected the UI, not the system.
- **`services/connector_policy.py`** + `PATCH /v1/connectors/:id/policy` — a
  *different route and a different persona* from connector authoring. Two
  disjoint field sets, two repository functions that cannot write each other's
  columns.
- `backend/verify_tool_gateway.py` — **215 assertions** at this phase (233 after
  Phase 7 added the graph layer), including a denial for
  every one of the eleven checkpoints and a live call with measured latency.

**Five things to not weaken:**

1. **`write_capable` before `approval`, exactly as in `bind_tool()`.** The
   invariant now lives in two modules on purpose; Q6's exception path is
   therefore a change in two places, and doing one produces a tool that cannot
   be bound but can be called.
2. **A denial is a 200 with a verdict, never a 4xx.** Denials are the rows worth
   having.
3. **`gateway = True` is written in one function and settable from no payload.**
   A second writer reopens R7.
4. **Authoring and policy stay disjoint.** An author who could widen their own
   data boundary is the hole this closes.
5. **Empty policy means undeclared, not deny-all** — and the gap is recorded on
   every call. `CONCERNS.md` **Q14** is the decision.

**Concerns moved:** **R7 CLOSED** (within its boundary) · **Q7 CLOSED** by our
decision — `bound_tools` *is* the allowlist, no `allowed_agents` column, and the
entry says why it still wants a stakeholder nod. **Opened:** **R11** (the gateway
is the governed path, not the only path — `POST /v1/tool-calls` still exists),
**Q14** (undeclared boundaries allow), **E5** (the suites die on a piped stdout),
**V9** (the browser pass).

### 2026-08-05 — Phase 4, the connector prioritization backlog *(slide 21 element 7)*

The last unbuilt element of slide 21's seven, and the contracted Week-11
artifact. Detail in `ARCHITECTURE.md` §14.

- **The SOW's seven systems of record, assessed and ranked** — Jira (1),
  Confluence (2), GitHub (3), BigQuery (4) in the first 90 days; ServiceNow (5),
  CCAI (6), MDR (7) later. Each row carries rationale, blockers, transport, auth
  model, data sensitivity, read-only tool candidates and access owner.
- **The rule with teeth:** a system with **no existing MCP server cannot be
  scheduled into the 90-day phase** — the SOW scopes out *building* servers, so
  a plan containing ServiceNow assumes work the contract excludes. Enforced
  server-side against the merged item, so two patches cannot walk around it.
- **`recommended` is derived**, never stored — rank 1 of the 90-day set, so the
  headline cannot drift from the table.
- **No POST route:** the candidate set is the SOW's and is not ours to extend.
- **`unknown` ≠ `none`.** CCAI and MDR are `unknown` because we looked and could
  not confirm, which is weaker evidence than confirmed absence.
- `backend/verify_connector_backlog.py` — **43 assertions**; mutates seeded rows
  and restores them.

**Honest limits:** the ranking is ours and unconfirmed (`CONCERNS.md` Q13),
**MDR could not be assessed at all** — neither source document ever expands the
acronym (Q11) — and CCAI's server availability is unverified (Q12).

### 2026-08-05 — the `bound_tools` guard *(closes R8)*

Found while verifying Phase 3 and fixed the same day. `bind_tool()` was the
*governed* way a tool becomes bound, not the *only* way: `register`, the config
sync `PATCH`, and `config-change` all persisted client-supplied `bound_tools`
with no validation. Detail in `ARCHITECTURE.md` §13.

- **`services/bound_tools_guard.py`** — one place decides what may be bound,
  called from all three routes. Reasons: `not_in_catalog`, `write_capable`,
  `not_approved`, applied in `bind_tool()`'s order so approval never overrides
  write-capability.
- **Strips rather than rejects.** A bad ref does not fail a registration — the
  synthesis engine proposes tools heuristically. The cost of stripping is paid
  by `strippedTools[]` in the response, a `bind_stripped` audit event, and one
  **`blocked` tool-call row per ref** — the same evidence a refused bind
  produces, so `/tools` → Tool Calls sees every door.
- **It was reachable without curl:** the only pre-registration filter was
  `writeDetect.ts`, a client-side *name* heuristic. The seeded write tools are
  caught by luck of naming; nothing filtered unapproved tools at all.
- Client adopts the sanitized config automatically; the Register toast becomes a
  **warn** naming what was dropped, and `ToolPicker` shows a `pending` badge so
  the pick is informed rather than a surprise.
- `backend/verify_bound_tools_guard.py` — **34 assertions**, and the first suite
  that **deletes what it creates** (asyncpg, teardown only) because leftover
  probe agents would pollute the Registry and Home counts.

### 2026-08-05 — Phase 3, tool governance *(slide 25 · Blueprint §3.4/§11)*

Three pieces, one story: the permission model made **legible**, consent made
**explicit**, accountability made **recordable**. Detail in `ARCHITECTURE.md` §12.

- **Permission matrix view** — `PERMISSION_MATRIX` + a toggle panel on the Tool
  Catalog rendering slide 25's nine rows with how each maps onto the code and a
  live count. Presentation only; nothing reads it for enforcement.
- **Tool approval** reuses the **shared** queue (Blueprint §11): `approvals`
  gained `entity_type`/`entity_id`, `agent_id` and `required_by_path` became
  nullable (`agent_id` **keeps its FK** — a nullable FK still enforces
  integrity for non-null values). A tool created through the console is
  `pending` and `bind_tool()` rejects it.
- **`approval_state` is a separate column from `status`, not a new status
  value** — the plan of record said otherwise. `status` is owned end-to-end by
  the health cascade and would overwrite a pending state the moment a connector
  flapped. Health and consent are different questions.
- **Approval is not a write exemption.** `write_capable` is checked first and
  independently; an approved write tool still does not bind. See Q6.
- **`owner` + `risk_level`**, nullable on purpose (a seeded tool has no real
  owner and inventing one fabricates accountability), with one real rule: a
  write-capable tool cannot be classified below `high`. `PATCH /v1/tools/:id`
  is policy-only — permission, write-capability, connector, status and approval
  state are all unreachable through it.
- `backend/verify_tool_governance.py` — **70 assertions.** It leaves
  `zz-verify-*` tools behind and, uniquely among the suites, **mutates a seeded
  agent** (proving an approved tool binds) — so it captures and restores that
  agent's config and self-heals a polluted baseline on entry.

### 2026-08-04 — Phase 2, connector CRUD *(Blueprint §3.5)*

Registering an MCP server is the most basic capability of an MCP page, and the
Blueprint makes it MVP-critical. Detail in `ARCHITECTURE.md` §11.

- **`POST /v1/connectors`** / **`PATCH /v1/connectors/:id`** +
  `services/connector_authoring.py`. Four author-owned fields: `name`,
  `transport`, `endpoint`, `auth_mode`.
- **Status stays owned by the health cascade** — not accepted on create or
  update, and `connectors_repo.update()` cannot set it. §3's chain starts here.
- **`tools_provided` is a claim, not a binding** — registering a connector
  creates no tools. **Correction (external review):** an earlier draft claimed
  this finally makes `undiscovered` non-empty. It does not — a fresh connector
  advertises nothing, so **Discover tools** on it returns entirely empty, and
  `verify_connector_crud.py` asserts that. See `ROADMAP.md` **D7**: no tool
  created through the product can be attached to a connector at all, so the
  discovery diff is structurally unreachable until a real `tools/list` lands.
- **Update merges, then validates the merged result** — `transport: http` +
  `endpoint: sse://…` is invalid only as a *pair*, and only merged validation
  catches it.
- UI: **Register MCP server** button + one `ConnectorModal` serving both create
  and edit; pencil affordance on each `ConnectorCard`.
- **No delete endpoint, deliberately** — tools reference connectors via
  `connector_id`, `tool_calls` via `system_accessed`.
- `backend/verify_connector_crud.py` — 40 assertions. Leaves `zz-verify-*`
  connectors behind (no delete).

### 2026-08-03 — Phase 1, tool-call audit trail *(slide 21 element 6)*

`ARCHITECTURE.md` **§10** has the detail. `/tools` gains a **third tab**: the
page now covers permissions (Catalog) → connectivity (MCP) → **evidence**.

- **`tool_calls` table** carrying slide 21's eight fields verbatim, plus
  `permission` and `at`. Indexed on `(agent_id, at DESC)` and
  `(tool_invoked, at DESC)`. No FK to `agents` — a trail outlives its subject.
- **Three fields the client cannot forge:** `system_accessed` (via Phase 0's
  resolver), `permission` (server's own `tools` table), `at` (server clock). A
  supplied value is ignored, not merged.
- **Blocked attempts are logged** — a rejected write-capable bind
  (`consumer = console`) and a denied runtime HITL gate. The advisory-only
  invariant becomes a row instead of a silent reject.
- **Local tools log `system_accessed = NULL`** and render "local — no MCP".
  Never a placeholder.
- `backend/verify_tool_calls.py` — 47 assertions. Append-only: it leaves rows
  behind by design.

### 2026-08-03 — Phase 0, connector resolution

`ARCHITECTURE.md` **§9** and `ROADMAP.md` §4 Phase 0 carry the detail. In short:
§8 made health flow *down* onto tools; this adds the lookup the other way —
**given an agent, which MCP servers does it need?**

- **`services/connector_resolution.py`** + `GET /v1/agents/:id/connectors`. The
  only place the tool→connector edge is walked. Phase 1's `system_accessed` and
  Phase 6's gateway view both consume it rather than re-deriving.
- **Bind warns, deploy blocks.** `tool_binding.py` returns
  `{"ok": true, "warning": …}` when a bound tool's connector is unhealthy, and
  writes it into the audit detail. Binding is design-time; health is runtime.
  The blocking gate stays Pre-Flight #4, now **scoped** and naming the offender.
- **`ToolPicker`** replaces free-text `TagInput` on Phase 1's Tools field —
  each suggestion shows the MCP connector it pulls in, uncatalogued names are
  flagged rather than silently accepted.
- **`McpDependencies`** panel on Phase 4 renders the resolved set.
- `verify_connectors.py` **24 → 51 assertions**, and it now normalizes its
  starting state (the toggle *flips*, so a connector left offline by a UI click
  used to invert 17 assertions with no code defect behind them).

### 2026-07-31 — connectors moved server-side

Connectors moved from browser-memory simulation to Postgres, closing the gap that opened when tools went server-side. Full file list, endpoint contracts, and design rationale are in **`ARCHITECTURE.md` §8**. Highlights:

- **`connectors` table** + repo + seed (5 connectors, `jira` seeded `degraded`).
- **Server-side health cascade** — connector status is authoritative; tool status is derived. Persists across refresh. Local tools untouched.
- **MCP `tools/list`** (`GET /v1/connectors/:id/tools`) returning the advertised tools plus an `undiscovered` / `orphaned` discovery diff. This is the swap point for a real MCP client.
- **`Discover tools`** action on each connector card, rendering that diff.
- **Status column + status/connector filters** on the Tool Catalog — spec-required by §9.5 and previously missing. Only meaningful now that the cascade keeps it honest.
- **`backend/verify_connectors.py`** — 24-assertion backend suite.
- Fixed a broken venv (hardcoded to a previous developer's user path) and **confirmed the port-5434 Postgres fix works** — that was the repo's top open question.

## 5. Roadmap

> **The sequenced build plan lives in `ROADMAP.md` §4** — schemas, endpoints,
> file lists, and the deck slide each phase closes. This section stays as the
> short index of *what* the items are; `ROADMAP.md` owns *when and how*.
> **Phases 0–3 shipped** (connector resolution + tool-call audit trail
> 2026-08-03; connector CRUD 2026-08-04; tool governance 2026-08-05).
>
> **⚠️ Re-sequenced twice.** 2026-08-04 moved the real MCP client up to Phase 4.
> **2026-08-05, after reading the SOW and deck directly, that was partly
> reversed:** the claim *"the SOW commits to a working connector at Week 11"* is
> false — acceptance is *"priority connector model **defined**"* and slide 18's
> Day-90 evidence is a *"strategy package"*. And Q5 was never a missing input:
> deck slide 21 element 7 makes the priority-connector answer **our deliverable**,
> so the backlog was scheduled *behind* the phase it unblocks.
>
> Current order: ~~**4** connector prioritization backlog~~ (2026-08-05) →
> ~~**5A** one real read-only MCP connector end-to-end~~ (2026-08-10) →
> ~~**6** policy-enforcing gateway~~ (2026-08-11) → ~~**7** gateway view~~
> (2026-08-11). **The build plan is complete.** What is left is **5B** — point it
> at a real Brightspeed system (access-gated) — and **8** connector expansion
> (out of 90-day scope by contract). Neither is engineering-gated.
>
> **Corrected 2026-08-11:** this line still said Phase 5 was "next" the morning
> after 5A shipped. A roadmap index that lags the section above it is how a
> session picks up the wrong next task — if you ship a phase, fix this line in
> the same pass.

### 5.0 Tool governance ✅ *shipped 2026-08-05*
Permission matrix view, tool approval on the shared queue, `owner` +
`risk_level`. See §4 and `ARCHITECTURE.md` §12.

### 5.1 Connector CRUD ✅ *shipped 2026-08-04*
Register/edit an MCP server from the UI. See §4 and `ARCHITECTURE.md` §11.

### 5.2 Tool-call audit trail ✅ *shipped 2026-08-03*
Slide 21's exact fields: **agent ID, request ID, consumer, tool invoked, system accessed, result status, latency, exception details.** Fed from the Playground's simulated tool calls plus rejected binds. See §4 and `ARCHITECTURE.md` §10.

**Follow-on worth considering:** the evaluation workstream's missing *data boundary* and *workflow control / no-write* categories (deck slide 24) are now testable against this table — a `blocked` row is the assertion. Not ours to build, but worth telling them.

### 5.3 Real MCP client behind `tools/list` — **now Phase 5**
Replace the body of `list_connector_tools()` with a real `tools/list` over the connector's transport. The return contract already matches — that was the point of the seam.

**Rewritten 2026-08-05 against MCP spec revision 2026-07-28.** The old plan said *"real `initialize` + `tools/list`"*. **There is no `initialize`** in the current revision — it is a legacy-era handshake reached only via backward-compat fallback, and the protocol is now stateless with `_meta.io.modelcontextprotocol/*` on every request. Protocol-level sessions and the GET stream endpoint were both removed. Only **two** standard bindings exist: `stdio` and **Streamable HTTP**; HTTP+SSE is Deprecated and *"eligible for removal in a future revision"* — which our `sse://` seed and `McpTransport` enum now contradict. Full detail in `ROADMAP.md` Phase 5.

**Must also fix D7**: discovery has to *write* the tools it finds, with `connector_id`, a remote tool id, and a schema hash. Without that, `undiscovered`/`orphaned` can never be non-empty, because `tool_authoring.create_tool()` hardcodes `connector_id: None` and nothing else sets it.

**Needs Phase 4's output** — the backlog names the connector; this builds it. The client itself is *protocol* code and can be built against any conformant server first.

### 5.4 + 5.5 → merged into the Phase 5 **policy-enforcing gateway**
Data boundary controls (per-connector datasets/fields) and identity mapping
(service-account / IAM-principal columns) are both *enforcement* concerns.
Enforcing them separately from a gateway means writing the same checkpoint
twice, so they now sit inside one deny-by-default `tools/call` path together
with the per-agent allowlist, rate limits, timeouts and HITL requirement. See
`ROADMAP.md` §4 Phase 5.

### 5.6 MCP gateway view ✅ *shipped 2026-08-11 (Phase 7)*
Agents → gateway → connectors → systems, with policy checkpoints marked and carrying their real denial counts. Slide 21's headline element. See §4 and `ARCHITECTURE.md` §17.

### 5.7 Connector prioritization backlog ✅ *shipped 2026-08-05 (Phase 4)*
Slide 21 element 7, and this workstream's Day-90 evidence per slide 18. The SOW's 7 systems of record, ranked with rationale, blockers, transport, auth model, data sensitivity and access owner; a 4th tab on `/tools`. **Recommends Jira.** See §4 and `ARCHITECTURE.md` §14.

## 6. Open questions and standing risks

> **Moved to [`CONCERNS.md`](CONCERNS.md) on 2026-08-05** — it is the single
> register for every open question, risk, divergence, environment trap,
> unverified item and cross-workstream observation. Ids are unchanged.
>
> The ones that bear most on this workstream: **Q5** (priority connector — now
> our deliverable, not a missing input) · **Q2** (scheduled healthchecks) ·
> **D7** (tools cannot attach to connectors) · **D8** (transport model vs. the
> 2026-07-28 spec) · **R7** (audit trail not yet authoritative) · **R9**
> (connector access is the long-lead item).

---

## Appendix — Commands

```powershell
docker compose up -d                                  # Postgres on 5434
npm run dev:client                                    # client :5173 (npm run dev is broken — CONCERNS E3)
& "backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload --port 8787

# Phase 5A/6 need the local reference MCP server as the counterparty:
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe -m reference_mcp.server --port 9100

npm run typecheck                                     # tsc -b --noEmit
npm run build
npm run test                                          # 4 frontend kernel suites

# ⚠️ Set this first or two suites die mid-run on a piped stdout (CONCERNS E5).
$env:PYTHONIOENCODING="utf-8"
backend\.venv\Scripts\python.exe backenderify_connectors.py           # 51
backend\.venv\Scripts\python.exe backenderify_tool_calls.py           # 58
backend\.venv\Scripts\python.exe backenderify_connector_crud.py       # 41
backend\.venv\Scripts\python.exe backenderify_tool_governance.py      # 70
backend\.venv\Scripts\python.exe backenderify_bound_tools_guard.py    # 34
backend\.venv\Scripts\python.exe backenderify_connector_backlog.py    # 43
backend\.venv\Scripts\python.exe backenderify_mcp_client.py           # 69  (needs :9100)
backend\.venv\Scripts\python.exe backenderify_tool_gateway.py         # 215 (needs :9100)
```

## Related documents

- **`CONCERNS.md`** — **the single register of every open question, risk,
  divergence, environment trap and unverified item.** Add to it whenever you
  find something; the rule is in `CLAUDE.md`
- `CLAUDE.md` — session handoff: state, next steps, gotchas
- `ROADMAP.md` — the sequenced build plan
- `ARCHITECTURE.md` — system design; **§8–§13** is this workstream
- `README.md` — product framing and demo script
