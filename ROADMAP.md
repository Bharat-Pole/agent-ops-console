# Tools & MCP — Deck Alignment & Build Plan

**Scope: the `/tools` page only** — the Tool Catalog tab and the MCP Connectors
tab. Soham owns both surfaces, so there is no cross-team boundary to negotiate
inside this workstream. Everything else in the console (registry, onboarding,
prompts, knowledge, governance, evaluation, monitoring, playground) is **out of
scope** and is not planned here.

**Relationship to the other docs**

| Doc | Answers |
|---|---|
| `MCP_WORKSTREAM.md` | *Where does this workstream stand?* — status, data-model facts, what shipped, open questions, risks |
| **`ROADMAP.md`** (this) | *What does the deck demand, and in what order do we build it?* — deck→code gap analysis and the sequenced plan with schemas, endpoints, and file lists |
| `ARCHITECTURE.md` §8–§17 | *How is it built?* — the design of what already shipped, one section per phase |
| `CLAUDE.md` | Session handoff, conventions, gotchas |
| **`CONCERNS.md`** | *What is unresolved?* — **the single register** of every open question, product decision, risk, environment trap, unverified item and cross-workstream observation. Add to it whenever you find one |

**Sources — read directly from the source files on 2026-08-05** (`.pptx` and
`.docx` in `Downloads/`; before that date every citation here was second-hand):
*Agent Ops Brightspeed* deck — **slide 18** (Deliverables by Workstream),
**slide 21** (MCP Connectivity Pattern), **slide 25** (Detailed Tool Permission
Matrix), **slide 49** (Tools & MCP product capability); SOW **deliverable 3.3** (*Tool Registry & MCP Connector
Design — tool schema, permission matrix, and MCP connector pattern for the
priority reference connector*, Week 11); Master Build Spec §9.5, §8.4, §10 seam #1;
**Agent Ops & Governance Platform — Product Blueprint** (27pp, shared by
management 2026-08-04) — §3.4 Tool Registry, §3.5 MCP Connector Layer,
§4.5 Tool and Action Controls. Reconciled in **§7**.

**Written:** 2026-07-31 (planning session — no code changed; `tsc -b --noEmit` clean).
**Updated:** 2026-08-03 — Phases 0 and 1. 2026-08-04 — Phase 2. 2026-08-05 —
Phase 3 + the R8 bind guard, and Phase 4. 2026-08-10 — Phase 5A, the real MCP
client. 2026-08-11 — Phase 6 (the gateway) and Phase 7 (the gateway view).
**The build plan is complete; see §4 "What remains".**

> ### 📌 2026-08-05 — the SOW and deck were read directly for the first time
>
> Everything before this date cited them second-hand. Reading the source
> `.docx` and `.pptx` **corrected two claims, closed two questions, and opened
> one.** If you are re-planning, start here:
>
> - ❌ **"The SOW commits to a working connector at Week 11" was false.** The
>   acceptance criterion is *"priority connector model **defined**"*. §1.
> - ❌ **Q5 was never a missing input** — deck slide 21 element 7 makes the
>   priority-connector answer *our deliverable*. Phases 4–8 re-sequenced. §4.
> - ✅ **Q3/D2 closed** — the SOW names the deck's 7 systems of record.
> - ✅ **New hard boundary:** *"install and configure MCP servers only; building
>   new MCP servers is out of scope."*
> - ⚠️ **New Q8** — `retrieve` and `classify` appear in the deck and SOW but not
>   in slide 25's matrix or the enum.
>
> Also on 2026-08-05, the **MCP spec was read at revision 2026-07-28** and the
> Phase 5 plan rewritten against it — there is no `initialize` handshake any
> more. See Phase 5.

---

## 1. What this workstream is measured against

### Slide 21 — the MCP Connectivity Pattern (7 elements)

This is the spine of the workstream. Status of each element today:

| # | Element | What the deck promises | Status |
|---|---|---|---|
| 1 | **MCP Gateway Pattern** | Standard architecture for routing agent requests to approved tools, systems, and data sources | ✅ Phase 6 — 11 checkpoints, deny-by-default, `POST /v1/gateway/tool-call`; Phase 7 — the view, 5th tab on `/tools` |
| 2 | **Reusable Tool Adapters** | Connector pattern for MDR, BigQuery, Jira, GitHub, Confluence, ServiceNow, CCAI | ◐ the pattern is complete and proven end-to-end once (register → discover → approve → bind → call). **Breadth across the seven is Phase 8, which the SOW scopes out of the 90 days** |
| 3 | **Tool Permission Model** | Classify tools as read, retrieve, summarize, draft, recommend, or write-blocked | ✅ locked 5-value enum, enforced **server-side** at bind *and* call |
| 4 | **Data Boundary Controls** | Define which datasets, systems, and fields each agent may access | ✅ Phase 6 — per-connector datasets deny the call, fields redact the response. Undeclared ≠ deny-all (**Q14**) |
| 5 | **Identity & Access Pattern** | Align tool access with IAM, service accounts, approved identities | ✅ Phase 6 — `approved_identities` enforced per call, `service_account`/`iam_principal` recorded. **Enforcement real, principal simulated** |
| 6 | **Tool-Call Audit Trail** | Log agent ID, request ID, consumer, tool invoked, system accessed, result status, latency, exception details | ✅ all 8 fields, `/tools` → Tool Calls tab. Phase 6 makes result + latency **observed** for gateway rows (**R7 closed**) |
| 7 | **Connector Prioritization Backlog** | Which systems connect in the first 90 days vs later | ✅ Phase 4 — 7 systems ranked, 4th tab on `/tools`; recommends **Jira** |

**Six of seven are complete** (1, 3, 4, 5, 6, 7); **one is partial** (2), and it
is partial by contract rather than by omission.

**Count the ✅ column, not the ◐ rows.** An early draft claimed "four of seven
are green" by counting partials; that was corrected on 2026-08-04, when the
honest number was two. The count has since moved on evidence each time: three
after Phase 4, six after Phase 6.

**Element 2 deserves its own sentence, because it is the one that could be
overclaimed.** The reusable *pattern* genuinely exists and has been driven
end-to-end against a conformant server. What does not exist is the pattern
*applied* to MDR, BigQuery, GitHub and the rest — and that is deliberate: the
SOW says *"will not production-integrate every internal application or connector
in 90 days… backlog the rest."* Phase 4's backlog **is** the contracted
treatment. So the honest form is "the adapter pattern is built and proven once;
expansion is scheduled and scoped out", not "adapters are done".

### Slide 25 — the Tool Permission Matrix (9 rows)

| Permission | Base 90-day treatment | Modelled? |
|---|---|---|
| Read | *"Allowed with approved access"* | ✅ the locked `ToolPermission` enum |
| Summarize · Draft · Recommend · Validate | Allowed | ✅ the locked `ToolPermission` enum |
| Create · Update · Approve · Deploy | **Not allowed in base scope** | ◐ collapsed into one `write_capable` boolean |

**Three vocabularies exist; slide 25 is the one to follow.** Read from source
2026-08-05:

| Source | Words used |
|---|---|
| Deck **slide 25** (*Detailed* Tool Permission Matrix) | read · summarize · draft · recommend · validate · create · update · approve · deploy |
| Deck slide 21 (Tool Permission Model row) | read · **retrieve** · summarize · draft · recommend · write-blocked |
| SOW (boundaries table) | summarize · draft · recommend · **classify** · validate · "produce evidence" |

The enum matches slide 25's five allowed values **exactly**, which is the right
choice — slide 25 is the detailed, named artifact and the other two are prose.
But note `retrieve` and `classify` have **no home in the model**. That is a
question for the product owner (new **Q8**), *not* a reason to widen the enum.

Behaviourally correct and better-enforced than the deck describes — the enum
has no `write` member at all, so an invalid permission is a *type error*, and
`tool_binding.py` re-reads its own `tools` table rather than trusting the client.

**The rendering gap closed 2026-08-05** (Phase 3.1): the Tool Catalog now has a
*Permission matrix* panel showing all nine rows with the implementation mapping
and a live count. The **model** gap in row 2 remains and is not a bug — the four
blocked verbs share one boolean, so the platform records *that* a tool writes
and never *which verb*. The view states that rather than splitting the count
four ways.

### Slide 49 — Tools & MCP product capability

> ▪ MCP servers with auto-discovered, schema-typed tools
> ▪ Permissions: read / validate / write-blocked (advisory)
> ▪ Any tool bindable to agents **and exposable as an API**

First two ✅. "Auto-discovered" is ◐ — `GET /v1/connectors/:id/tools` returns a
real discovery diff but reads the catalog rather than issuing a real RPC (§5.6).
"Exposable as an API" is out of this workstream (Deployment layer).

### SOW deliverable 3.3 — due Week 11

> **Read from the source documents on 2026-08-05.** Everything below is quoted
> from the SOW `.docx` and the deck `.pptx`, not from summaries. Two things this
> workstream believed turned out to be wrong; both are corrected here.

**The Week 11 bar is a *defined* connector, not a *working* one.**

| Source | Exact words |
|---|---|
| SOW deliverable 3.3 (Week 11) | *"Tool schema, permission matrix, and MCP connector pattern for the priority reference connector"* |
| SOW acceptance criteria, **MCP** row | *"Internal connectivity strategy and priority connector model **defined**"* |
| Deck slide 18, Day-90 evidence | *"MCP and tool registry **strategy package**"* |

Compare the SOW's **Runtime** acceptance row — *"Reference runtime/API pattern
**demonstrated or implementation-ready**"*. The SOW knows how to ask for a
working artifact; for MCP it asked for a defined one. ⚠️ **An earlier version of
this roadmap claimed the SOW commits to "a working connector, not a diagram."
That is false**, and it was the main justification for the Phase 4/7 reordering
— see the corrected sequencing note in §4.

**Two scope boundaries that constrain Phase 4, from the SOW's boundaries table:**

> *"**Will install and configure MCP servers only; building new MCP servers is
> out of scope.**"* → *"Install/configure approved/**existing** MCP servers and
> connectors; backlog custom MCP server creation."*

Any candidate connector **without an existing MCP server is out of scope by
contract.** That removes ServiceNow, MDR, CCAI and all three of our fictional
internal connectors, and leaves the four with real first-party servers: **Jira,
Confluence, GitHub, BigQuery.**

> *"Produce implementation-ready patterns and use **sandbox/mock/stub approaches
> until access is approved**"* — because *"Brightspeed-owned access, IAM,
> security, and project provisioning are dependencies."*

The simulated MCP layer is therefore **the prescribed treatment**, not a
shortcut we owe an apology for.

**Status:** tool schema ✅ · permission matrix ✅ (Phase 3.1) · **MCP connector
pattern for the priority reference connector** ◐ — pattern designed and swap
point documented; the *priority* half is unanswered and is **ours to answer**
(see Q5).

## 2. Where the code stands

```
✅  Tool catalog CRUD              backend-persisted + AI-assisted authoring
✅  Advisory-only enforcement      server-side trust boundary, tool_binding.py
✅  MCP connectors                 backend-persisted (connectors table)
✅  Connector → tool cascade       server-side, persisted, survives refresh
✅  MCP tools/list + diff          endpoint live; real-client swap point documented
✅  Status column + filters        Tool Catalog, spec §9.5
✅  Agent → connector resolution   Phase 0 — the tool→connector edge, walked once
✅  Catalog-backed tool picker     Phase 0 — MCP dependency visible at pick time
✅  Bind-time health warning       Phase 0 — warns, never blocks (deploy blocks)
✅  Tool-call audit trail          Phase 1 — slide 21 element 6, 3rd tab on /tools
✅  Blocked attempts logged        rejected binds + denied HITL gates, as evidence
✅  Connector backlog              Phase 4 — slide 21 element 7, 4th tab
✅  Connector CRUD                 Phase 2 — register/edit an MCP server
✅  Permission matrix view         Phase 3 — slide 25's 9 rows, with the mapping
✅  Tool approval process          Phase 3 — shared approval queue, 2nd bind gate
✅  Real MCP client                 Phase 5A — spec 2026-07-28, discovery writes tools
✅  Real healthchecks               Phase 5A — a live socket; `last_probe` is the evidence
✅  Policy-enforcing gateway        Phase 6 — 11 checkpoints, deny-by-default
✅  Data boundary controls          Phase 6 — slide 21 element 4
✅  Identity & access pattern       Phase 6 — slide 21 element 5 (principal simulated)
✅  Observed tool-call evidence     Phase 6 — result + latency measured, not reported
◐   Tool policy fields             Phase 3 — owner + risk_level; rate limit + timeout
                                   now live on the connector instead (Phase 6)
◐   Reusable tool adapters         the *pattern* is complete and proven once;
                                   breadth across the 7 systems is Phase 8
❌  MCP gateway view               Phase 7 — the diagram over what is now real
```

**Verified green (2026-08-11) — 8 suites, 599 assertions, 0 failures:**
`verify_connectors` 51 · `verify_tool_calls` 58 · `verify_connector_crud` 41 ·
`verify_tool_governance` 70 · `verify_bound_tools_guard` 34 ·
`verify_connector_backlog` 43 · `verify_mcp_client` 69 · `verify_tool_gateway` 233 ·
`npm run test` 4/4 · `tsc -b --noEmit` clean · `npm run build` clean.

⚠️ Run the suites with `$env:PYTHONIOENCODING="utf-8"`. Piped through anything,
two of them die mid-run on a cp1252 encode and *look* like short passing runs —
`CONCERNS.md` **E5**.

**Never verified:** a live browser click-through of `/tools`. No headless-browser
tooling is installed — this is a known constraint, not an oversight.

### The data-model fact that shapes everything

A tool does **not** require a connector. The relationship is **optional
many-to-one** — 7 of 12 seeded tools are served by a connector, 5 are local
(`connector_id = NULL`). The health cascade must skip local tools, and any new
connector-driven feature must too. The Tool Catalog is a **superset** of every
governed capability; MCP is one delivery mechanism among several.

## 3. Divergences that need a product decision, not a ticket

| # | Divergence | Why it is a decision |
|---|---|---|
| **D1** | ~~**Permission model shape.**~~ **CLOSED 2026-08-05.** Resolved as a decision 2026-08-04 (deck slide 25 and Blueprint §3.4 independently give the *same* 9-value list); the 9-row **view** shipped in Phase 3.1. | **Do not change the enum.** The matrix is presentation over the model — nothing reads `PERMISSION_MATRIX` for enforcement. |
| **D2** | ~~**Connector names — two disagreeing lists.**~~ **RESOLVED 2026-08-05 from the source documents.** The SOW's boundaries table names the authoritative systems outright: *"**Jira, GitHub, Confluence, ServiceNow, MDR, CCAI, and BigQuery** remain authoritative systems."* That is the deck's 7, exactly. Deck slide 21 adds *"and internal applications"* as a catch-all — which is what the Blueprint calls "Internal APIs", so the lists were never really in conflict; only "Cloud Storage" is the Blueprint's own addition. | **The SOW is the contract and it settles this: the deck's 7 are authoritative.** Renaming the seed still ripples into `seed_snapshot.json`, `verify_connectors.py` and `test/causality.ts`, so treat it as a scheduled change, not a drive-by. |
| **D3** | ~~**Tool approval.**~~ **CLOSED 2026-08-05.** Blueprint §11 names an **Approval Queue** — *"needed for prompt, tool, data, model, deployment, and exception approvals"*. Shipped in Phase 3.2 by **widening** `approvals` with `entity_type`/`entity_id` rather than duplicating it. | The queue is now shared platform machinery. When Prompts or Data want approval, widen the same table — do **not** add a third queue. |
| **D4** | **`write_capable` tools registerable, or only discoverable?** | Current behaviour catalogues them for visibility, consistent with the seed which ships three. Confirm this is intended. |
| **D5** | **NEW — hard block vs. human-approved.** Blueprint §3.4: write tools *"should be blocked **or human-approved only**"*. Our code makes `write_capable` **never** bindable, full stop. | Blueprint §9 says *"no-write enforcement in **base phase**"*, so today's behaviour is correct for Phase 1. The human-approved path is a later option and would ride Blueprint §11's **Exception Management** (with expiry). **Loosening the advisory-only invariant is a governance decision, not a ticket — see Q6.** |
| **D7** | **NEW (external review, 2026-08-04) — a tool can never be attached to a connector.** `tool_authoring.create_tool()` hardcodes `connector_id: None`, and no route, form, or service sets it afterwards. Every tool created through the product is **local, forever**; the 7 connector-served tools exist only because the seed wrote them directly. | This makes two shipped features structurally inert: `undiscovered` **can never be non-empty** (a connector advertises nothing, and nothing can be catalogued against it), and `orphaned` likewise. Blueprint §3.5 *"Register MCP tools"* is unbuilt. **Fixing this needs either a `connector_id` on the create/edit path, or a real `tools/list` that writes discovered tools — the second is the honest fix.** Feeds the re-sequencing note below. |
| **D6** | ◐ **Tool object is thinner than Blueprint §3.4 wants.** `owner` + `risk_level` **shipped in Phase 3.3**. Still missing: `business_purpose`, `authorization_rule`, `allowed_agents`, `allowed_users`, `rate_limits`, `timeout`, `logging_requirement`, `human_approval_requirement`, `error_handling`. | Unbuilt scope, not a divergence. `rate_limits`/`timeout`/`logging_requirement` stay in Phase 5 — a policy field with no enforcer is decoration. **`allowed_agents` is genuinely new**: today `used_by` is *descriptive* (who bound it), not an *allowlist* (who may) — see Q7. |

## 4. The build plan

Sequencing principle: **close the deck's named gaps in descending demo value**,
and prefer changes that make the existing simulation produce real evidence.

**Phases 0 and 1 shipped 2026-08-03; Phase 2 shipped 2026-08-04; Phase 3 and the
R8 bind guard shipped 2026-08-05.** **Phase 4 (connector prioritization backlog) shipped 2026-08-05** and recommends
**Jira** as the reference connector. **Phase 5A — the real MCP client against a
local reference server — is next, and is not blocked by anything.**

---

## 4.0 The POC boundary *(set 2026-08-10)*

**This is a local-machine proof of concept, and the goal is maximum capability
coverage within that constraint.** That is not a fallback position — the SOW
prescribes it: *"Produce implementation-ready patterns and use **sandbox / mock
/ stub approaches until access is approved**."* Every phase below is scoped
against this boundary, and each is labelled **POC-complete** or
**access-gated**.

### The dividing line: protocol fidelity vs. counterparty reality

The question for every capability is **which half of the wire is being
simulated.**

- **Our half must always be real.** The client, the gateway, the policy checks,
  the audit writer, the schema handling — this is the deliverable. It is
  implementation-ready code that would not change when a real endpoint arrives.
- **The counterparty may be local.** Whether a conformant MCP server is running
  on `localhost` or at `mcp.atlassian.com` changes a URL and an auth mode.
  It does not change one line of protocol code.

**The rule this yields: never simulate the thing being demonstrated; simulate
only what sits on the far side of it.** A fake healthcheck that always returns
green is dishonest, because health is the thing being shown. A local MCP server
answering a genuine `tools/list` is not, because the protocol exchange is real
and the server is merely nearby.

### What reaches full fidelity locally

| Capability | Why it is fully real locally |
|---|---|
| **The MCP client** (spec 2026-07-28) | Protocol code. Identical against local or remote |
| **Real `tools/list` + discovery writing tools** | Closes **D7** genuinely — a local server advertises tools, discovery upserts them with `connector_id` |
| **`x-mcp-header` conformance rejection** | The local server can deliberately serve one malformed definition, proving the client excludes it and warns |
| **Real healthchecks** | An actual probe against a real socket, replacing the random roll |
| **The policy gateway** (Phase 6) | Every check — allowlist, boundary, ceiling, HITL, rate limit — is local logic |
| **Server-generated audit** | **This is the big one.** Once calls pass through our gateway to a real socket, `result_status` and `latency_ms` become *observed*, not client-reported |
| **The gateway view** (Phase 7) | Read-only over data the phases above make real |
| **Data boundary controls** | Field/dataset allowlists are enforced by us, not by the counterparty |

### What is structurally impossible locally — and stays honestly labelled

| Not achievable | Why | How it is handled |
|---|---|---|
| Real Brightspeed business data | No access, and none should be sought for a POC | Local server serves realistic but synthetic Jira-shaped records |
| Real IAM / OAuth against Brightspeed | Needs a tenant and an app registration | `auth_mode` is modelled and carried end-to-end; only the credential exchange is stubbed |
| Network egress / perimeter policy | Belongs to the deployment layer | Recorded as **R6**, explicitly out of this workstream |
| Vertex AI model layer | Needs GCP | Recorded as **R5**; the model layer is not presented as the target |
| Production-scale performance evidence | A laptop is not a load test | Never claimed |

### What this changes about the blockers

**Q10 (Cloud vs on-prem), R9 (access) and Q13 (ranking sign-off) stop gating
code.** They gate *productionization* — the moment a real endpoint replaces
`localhost`. They remain open and still need answers for the Week-11 strategy
package, but **no engineering waits on them.**

**The one thing to protect:** the seam between our code and the counterparty must
stay a single, obvious, swappable boundary — one endpoint, one auth mode, one
transport. If POC-only assumptions leak past that seam into the client or the
gateway, the "implementation-ready" claim stops being true, and that is the only
promise this POC actually makes.

---

### Phase 0 — Connector Resolution ✅ *(shipped 2026-08-03)*

**Not a deck element** — an enabler. It closes no slide-21 row on its own, and
was built first because Phases 1 and 6 both need the same lookup and would
otherwise each re-derive it.

**The gap it closed.** The tool → connector edge is a fixed FK on the tool row
(a tool has exactly one home system; "which MCP?" is a lookup, never a choice).
Nothing walked that edge — `connector` appeared nowhere in `kernel/engine/`, so
an agent's MCP dependency set existed only as an implication of the data. Three
consequences, all now fixed:

1. Tool names in Phase 1 were **free text** — a typo was indistinguishable from
   a real tool, and the MCP it pulled in was invisible.
2. `bind_tool()` checked only `write_capable`; an unhealthy connector was
   **silent**.
3. Pre-Flight check #4 was **global** — `connectors.some(offline)` blocked every
   agent when any one connector was down.

**What shipped** — full detail in `ARCHITECTURE.md` §9.

| # | Change |
|---|---|
| 0.1 | `services/connector_resolution.py` + `GET /v1/agents/:id/connectors`; `listAgentConnectors()` through `services.ts` / `api.ts` |
| 0.2 | `usePreflight(toolIds?)` — check #4 scoped, offending connectors named in the label |
| 0.3 | `_health_warning()` in `tool_binding.py` — `{"ok": true, "warning": …}`, warn toast, warning in the audit detail |
| 0.4 | `ToolPicker.tsx` — catalog typeahead showing each tool's connector + status; uncatalogued names flagged, `write_capable` still selectable-and-doomed |
| 0.5 | `McpDependencies.tsx` on Phase 4 — the resolved set, rendered |
| 0.6 | `verify_connectors.py` 24 → **51 assertions**, plus starting-state normalization |

**The design call worth remembering:** *bind warns, deploy blocks.* Binding is a
design-time declaration; connector health is a runtime condition. Gating a
config write on flapping infrastructure would make agent definitions
non-deterministic w.r.t. a third party's uptime. Do **not** add an `ok: false`
branch for health to `bind_tool()`.

**Deviation from the written plan.** 0.2 was specified as "resolve the draft's
bound tools" — but `usePreflight()` runs at two call sites that both execute
*before any tool is chosen* (`OnboardingPage`, and `PreFlightPhase` at phase
`pre`). Platform-wide is the honest answer when there is no agent to scope to,
so it stays the fallback; scoping engages once a draft has tools. The genuinely
agent-scoped signal moved to 0.5's panel, on Phase 4, where `bound_tools` first
exists.

**Pays into:** Phase 1's `system_accessed` is `resolve_tool_connector()` at
runtime for one call; Phase 6's gateway view is the same data fanned out across
all agents. Neither needs to re-derive the edge.

---

### Phase 1 — Tool-Call Audit Trail ✅ *(shipped 2026-08-03 — slide 21 element 6)*

Was the largest gap in this workstream and the most directly demoable: make a
tool call in the Playground, come to `/tools`, see the call with full
provenance. Full design in `ARCHITECTURE.md` §10. Built as planned below, with
three decisions worth carrying forward:

- **Three fields the client cannot forge** — `system_accessed` (via Phase 0's
  resolver), `permission` (the server's own `tools` table) and `at` (server
  clock). A supplied value is *ignored*, not merged. That is what makes this a
  trail rather than a log, and it is what the suite spends most of its
  assertions on.
- **A refusal is not logged.** A write-intent refusal returns `toolCalls: []` —
  no tool was named, so there is nothing truthful to put in `tool_invoked`.
  Fabricating one for a nicer demo row would be fabricating an audit record.
  The two real `blocked` paths (rejected bind, denied HITL gate) cover the same
  beat.
- **HITL calls are logged at the decision, not at send** — they are *pending*
  until approved, so logging `ok` up front would be false.

`verify_tool_calls.py` — 47 assertions, all passing. It is append-only and
**leaves rows behind** by design, same as `audit_log`.

**Table — slide 21's field list, verbatim**

```
tool_calls
  id               TEXT PRIMARY KEY
  agent_id         TEXT NOT NULL        -- "agent ID"
  request_id       TEXT NOT NULL        -- "request ID"
  consumer         TEXT NOT NULL        -- "consumer"       (playground | api | workflow)
  tool_invoked     TEXT NOT NULL        -- "tool invoked"
  system_accessed  TEXT                 -- "system accessed" (connector_id, NULL for local)
  result_status    TEXT NOT NULL        -- "result status"   (ok | error | blocked)
  latency_ms       INTEGER NOT NULL     -- "latency"
  exception_detail TEXT                 -- "exception details"
  permission       TEXT NOT NULL        -- the ceiling actually exercised
  at               TEXT NOT NULL
```

Index on `(agent_id, at DESC)` and `(tool_invoked, at DESC)`.

**Work**

| Layer | Change |
|---|---|
| `db/migrate.py` | `tool_calls` DDL + indexes |
| `repositories/tool_calls_repo.py` | **new** — `insert`, `get_all`, `get_filtered(agent_id?, tool_id?, status?, limit)` |
| `services/tool_call_log.py` | **new** — `record_tool_call()`; resolves `system_accessed` via `connector_resolution.resolve_tool_connector()` (Phase 0 — do not re-derive it); writes an audit event for `blocked` results |
| `routes/tools.py` | `POST /v1/tool-calls` (201) · `GET /v1/tool-calls` (200, filterable) |
| `kernel/services.ts` | `recordToolCall()`, `listToolCalls()` — `postJson` + toast convention |
| `kernel/api.ts` | re-export both |
| `PlaygroundPage.tsx` | fire `recordToolCall()` when a simulated tool call resolves; capture real elapsed ms |
| `ToolsPage.tsx` | **new third tab: Tool Calls** — `DataTable` over the 8 slide-21 fields, filters by agent / tool / result status |
| `verify_connectors.py` | extend, or add `verify_tool_calls.py` |

**Design notes**
- A **blocked** bind attempt should also land here with `result_status=blocked`
  and the advisory-block reason in `exception_detail`. That turns the governance
  invariant into visible evidence rather than a silent rejection.
- `system_accessed` comes from the server's own tools table, never the client —
  call Phase 0's `resolve_tool_connector()` rather than reading `connector_id`
  inline, so there stays exactly one place that walks the tool→connector edge.
- Local tools (`connector_id = NULL`) log `system_accessed = NULL` — do not
  invent a value.

**Demo proof:** Playground → make a tool call → `/tools` → Tool Calls tab → the
row is there, with latency and the system it touched. Then ask an agent to do
something write-shaped and watch the `blocked` row appear.

---

### Phase 2 — Connector CRUD ✅ *(shipped 2026-08-04 — Blueprint §3.5)*

Connectors were seed-only, which was glaring once they became persisted.
**Promoted by the Blueprint:** §3.5 lists *"Register MCP server"* as connector
capability **#1**, and §10 names *"Tool Registry / MCP Connector Setup"* as an
MVP screen. Full design in `ARCHITECTURE.md` §11.

**Two invariants held, and worth not weakening:**
1. **Status is owned by the health cascade, never by an author.** Neither create
   nor update accepts `status`; `connectors_repo.update()` physically cannot set
   it. §8's chain starts here — an author who could set connector status could
   launder tool status too.
2. **`tools_provided` is a claim, not a binding.** Registering a connector
   creates **no tools**; the field is not on the form.

**CORRECTION (2026-08-04, external review).** An earlier draft of this section
claimed a fresh connector finally makes `undiscovered` non-empty. **That is
false.** `undiscovered = advertised − catalogued`, and a fresh connector
advertises nothing, so the set is empty — `verify_connector_crud.py` asserts
exactly that (`"nothing undiscovered yet"`). The claim contradicted our own
test. See **D7**: `undiscovered` is *structurally unreachable* today.

**Two design calls:**
- **Update merges, then validates the merged result** — a partial patch cannot
  slip an invalid *combination* past a per-field check (`transport: http` +
  `endpoint: sse://…` is invalid only as a pair).
- **`sse` accepts `http(s)://`** — MCP's SSE transport *is* an HTTP endpoint
  streaming events. The seed's uniform `sse://` makes this look like a bug; it
  is not. Do not tighten it.

**No delete endpoint, deliberately** — tools reference connectors via
`connector_id` and `tool_calls` via `system_accessed`. Retirement belongs with
the Blueprint's lifecycle states, not a hard delete.

`verify_connector_crud.py` — 40 assertions. It **leaves `zz-verify-*` connectors
behind** (no delete), named so they sort last and are obvious.

**Pre-existing assertion this invalidated:** `verify_connectors.py` asserted
`len(connectors) == 5`, quietly encoding *"connectors are seed-only"*. Now
asserts the 5 seeded ids are **present**.

| Layer | Change |
|---|---|
| `services/connector_authoring.py` | **new** — `create_connector()` / `update_connector()`; validate `transport ∈ {sse, stdio, http}`, `auth_mode ∈ {secret_manager, oauth, none}`, endpoint shape, id uniqueness |
| `routes/connectors.py` | `POST /v1/connectors` (201/400) · `PATCH /v1/connectors/:id` (200/404/400) |
| `kernel/services.ts` / `api.ts` | `createConnector`, `updateConnector` |
| `ToolsPage.tsx` | "Register MCP server" button + `NewConnectorModal` mirroring `NewToolModal`; edit affordance on `ConnectorCard` |

**Watch:** a newly registered connector starts with `tools_provided: []`, so
**Discover tools** on it returns an entirely empty result — no tools, no
`undiscovered`, no `orphaned`. That is correct given the current data flow and
is exactly why **D7** matters. Status seeds as `connected` and is thereafter
owned solely by the cascade — never let the create form set tool status.

---

> ### ⚠️ Phases 4–7 reordered 2026-08-04 — then **partly reversed 2026-08-05**
>
> **2026-08-04:** the real MCP client moved from Phase 7 up to Phase 4, on three
> reasons. **2026-08-05, after reading the SOW and deck directly, reason 1 turned
> out to be false and reason 3 turned out to be misapplied.**
>
> | # | Reason given 2026-08-04 | Status after reading the sources |
> |---|---|---|
> | 1 | *"SOW deliverable 3.3 commits to a working connector at Week 11 — not a diagram."* | ❌ **False.** SOW acceptance is *"priority connector model **defined**"*; deck slide 18's Day-90 evidence is a *"strategy **package**"*. See §1. |
> | 2 | The old Phase 6 note already said "build after the checkpoints are real" — apply it consistently | ✅ Still stands |
> | 3 | *"D7 makes discovery inert — only a real client closes it."* | ◐ **True but misapplied.** A real client needs a real endpoint, which needs the *priority connector answer*, which is **Phase 7's deliverable**. Moving the client ahead of Phase 7 put it ahead of its own input. |
>
> **The correction: the connector prioritization backlog (old Phase 7) comes
> first.** Deck slide 21's seventh element is *"Identify which systems should be
> connected in the first 90 days versus future phases"* — the backlog **is** the
> artifact that answers Q5. We had scheduled the thing that answers the blocking
> question *behind* the phase it blocks.
>
> Old Phase 4 (data boundary) and Phase 5 (identity) still merge into one
> enforcement phase — that reasoning was never in doubt.
>
> **Current order: 4** connector prioritization backlog (answers Q5, and is the
> Week-11 contracted artifact) → **5** one real read-only MCP connector →
> **6** policy-enforcing gateway → **7** gateway view.

### Phase 3 — Permission Matrix, tool approval, tool policy fields ✅ *(shipped 2026-08-05)*

Full design in `ARCHITECTURE.md` §12. All three parts landed as planned, with
one deliberate deviation recorded below.

1. **Permission Matrix view** (D1) ✅ — `PERMISSION_MATRIX` in
   `kernel/constants.ts` + a toggle panel on the Tool Catalog. Pure
   presentation; nothing reads it for enforcement.
2. **Tool approval** (D3) ✅ — `services/tool_approval.py`, the `approvals`
   table widened to `entity_type`/`entity_id`, and a second server-side guard
   in `bind_tool()`.
3. **Tool policy fields** (D6) ◐ — `owner` + `risk_level` shipped with
   `PATCH /v1/tools/:id`. The remaining nine Blueprint §3.4 fields are still
   unbuilt; `rate_limits`/`timeout`/`logging_requirement` stay deferred to
   Phase 5 on purpose.

**Deviation from the written plan — `pending_approval` is NOT a `status`
value.** The plan said "a `pending_approval` state on `tools`". That would have
broken §8's invariant: `tools.status` is owned end-to-end by the connector
health cascade, so a governance state parked there gets overwritten the moment a
connector flaps. It shipped as a separate `approval_state` column. Health and
consent are different questions about a tool and both directions of that
independence are asserted.

**Three things to not weaken:**
1. **Approval is not a write exemption.** `write_capable` is checked *first* and
   independently; approving a write-capable tool still does not bind it. If
   approval could unlock a write tool, approval would be a laundering path for
   the one invariant the deck is most specific about. Changing that is **Q6**.
2. **Cataloguing is not consent.** A tool created through the console is
   `pending` and unbindable, and a client-supplied `approval_state` is *ignored,
   not merged* — the same rule that governs `system_accessed`/`permission`/`at`.
3. **The seeded catalog is grandfathered, not retro-queued.** The column default
   is `approved`. Do not "fix" this by queueing the 12 seeded tools.

**A deliberate non-feature:** a rejected tool is **not** deleted. It stays
catalogued, visible and unbindable, carrying the decision — the same principle
that keeps write-capable tools in the catalog rather than hiding them.

`backend/verify_tool_governance.py` — **70 assertions.** It leaves `zz-verify-*`
tools and their approval items behind (no tool delete endpoint, same reasoning
as connectors), but unlike the other suites it **mutates a seeded agent** —
proving an approved tool binds writes to the Incident Coordinator's
`bound_tools`, which `verify_connectors.py` asserts is exactly 4. It captures
and restores that config, and strips stale `zz-verify-` refs from its baseline
on entry so an interrupted run self-heals.

✅ **Already done (2026-08-04):** the bound-tool authorization check in
`tool_call_log.py`. A claimed `resultStatus: ok` for a tool the agent was never
bound to is **overridden to `blocked`**, server-side, with the reason recorded.
Closes half of R7.

---

### Phase 4 — Connector prioritization backlog ✅ *(shipped 2026-08-05 — slide 21 element 7)*

**Took slide 21 to 3 of 7 complete** (6 of 7 as of Phase 6 — the running count
lives in §1, not here, so it cannot drift phase by phase). Full design in
`ARCHITECTURE.md` §14.

- `connector_backlog` table + repo + `services/connector_backlog.py`, seeded
  with the SOW's **seven systems of record**, ranked, each carrying its
  rationale, blockers, transport, auth model, data sensitivity, read-only tool
  candidates and access owner.
- `GET /v1/connector-backlog` returns the rows **plus a server-derived summary**
  (`recommended`, `blocked_on_no_server`, `unassessed`) — derived so the headline
  cannot drift from the table. `PATCH /v1/connector-backlog/:id` to re-rank or
  advance a system.
- **Fourth tab on `/tools`.**
- `backend/verify_connector_backlog.py` — **43 assertions.**

**The invariant, and the reason this is a feature rather than a page:** a system
with **no existing MCP server cannot be scheduled into the 90-day phase**,
enforced server-side against the *merged* item so two patches cannot walk around
it. The SOW says *"install and configure MCP servers only; building new MCP
servers is out of scope"* — so a 90-day plan containing ServiceNow silently
assumes work the contract excludes. **The boundary is enforced, not annotated.**

**The result:** Jira (1), Confluence (2), GitHub (3), BigQuery (4) in the first
90 days — the four with existing first-party servers. ServiceNow (5), CCAI (6),
MDR (7) later, all `blocked`. **Recommended reference connector: Jira.**

**Three things to not weaken:**
1. **There is no POST route.** The candidate set is the SOW's seven and is not
   ours to extend.
2. **`unknown` is a real state**, distinct from `none`. CCAI and MDR are
   `unknown` because we looked and could not confirm — which is weaker evidence
   than confirmed absence, and the difference matters.
3. **`recommended` is derived, never stored.** It is rank 1 of the 90-day set.

**Honest limits:** the ranking is *ours* and unconfirmed (`CONCERNS.md` **Q13**),
**MDR could not be assessed at all** because neither document expands the
acronym (**Q11**), and CCAI's server availability is unverified (**Q12**).

<details><summary>Original plan (kept for the reasoning)</summary>

**Promoted to next on 2026-08-05.** This is the contracted Week-11 artifact and
it is what *answers* Q5 rather than waiting on it. Slide 21's seventh element is
*"Identify which systems should be connected in the first 90 days versus future
phases"*, and slide 18's Day-90 evidence for this workstream is an *"MCP and
tool registry strategy package"*. Both describe this phase, not the real client.

Now unblocked, because reading the source documents supplied the inputs that
were missing:

1. **The candidate set is fixed** (D2, resolved): Jira, GitHub, Confluence,
   ServiceNow, MDR, CCAI, BigQuery — the SOW's own "systems of record" list —
   plus the deck's *"internal applications"* catch-all.
2. **A contractual filter applies:** *"install and configure MCP servers only;
   building new MCP servers is out of scope."* A system with no existing MCP
   server cannot be the reference connector without a scope change. As of
   2026-08-05: **Jira, Confluence** (official Atlassian remote server, OAuth 2.1
   or API tokens), **GitHub** (official first-party) and **BigQuery** (Google
   managed remote server, IAM) have one. **ServiceNow, MDR, CCAI do not** — for
   those the SOW's own treatment is *"backlog custom MCP server creation."*
3. **A signal on which to pick first:** the SOW's existing reference agent is
   *Bill Christian's E2E Testing/QA agent*, and the AI-DLC operating model is
   defined as *"GitHub issue orchestration, Jira integration."* The reference
   agent runs on Jira and GitHub.

**Deliverable:** the 7 systems ranked into 90-day vs. later, each with existing
MCP server (yes/no), transport, auth model, read-only tool candidates, data
sensitivity, and the owner who must approve access. **Recommendation to carry
in: Jira**, with GitHub second.

Build it as a real page/panel (slide 21 element 7 is currently ❌), not a
document — the console is the deliverable.

</details>

---

### Phase 5A — Real MCP client against a local reference server ✅ *(shipped 2026-08-10)*

**Not blocked by anything. This is the next thing to build.**

The vertical slice. Everything above this line is a simulation of MCP; this is
the first line of code that speaks the protocol. Splitting the old Phase 5 here
is the whole point of the POC boundary (§4.0): **the protocol work never needed
client input, and the access-gated remainder is now a thin, named seam** in
Phase 5B.

**The local reference server is a deliverable, not a crutch.** Write a small
`stdio` MCP server that serves a read-only, Jira-shaped tool surface
(`jira_issue_reader`, `jira_search`) over synthetic records. Two reasons it earns
its place beyond unblocking us:

1. **It makes the tests real.** Every assertion about the client runs against an
   actual protocol exchange rather than a mock object.
2. **It can be deliberately non-conformant in one place.** Serve one tool whose
   `x-mcp-header` annotations are invalid, and the suite proves the client
   **excludes it from `tools/list` and logs a warning** rather than poisoning the
   whole discovery — a spec MUST that is otherwise very hard to demonstrate.

Keep it under `backend/reference_mcp/`, clearly labelled, and never wire it into
the seeded connector set as though it were a Brightspeed system.

> ### ⚠️ Rewritten 2026-08-05 against MCP spec revision **2026-07-28**
>
> The previous plan was written against a superseded model of the protocol. It
> would have produced a client no current server expects.
>
> | Old plan | Spec 2026-07-28 |
> |---|---|
> | "Real **`initialize`** + `tools/list`" | **There is no `initialize`.** It is a legacy-era handshake reached only via backward-compat fallback. Modern MCP is stateless, carrying `_meta.io.modelcontextprotocol/{protocolVersion,clientInfo,clientCapabilities}` on every request |
> | — | **Protocol-level sessions removed** (`Mcp-Session-Id`), and the **GET stream endpoint removed** |
> | Transports `sse \| stdio \| http` | Only **two** standard bindings: **`stdio`** and **Streamable HTTP**. HTTP+SSE (2024-11-05) is Deprecated and *"eligible for removal in a future revision"* |
>
> **`tools/list` today** is one HTTP POST to a single MCP endpoint, with
> `MCP-Protocol-Version` and `Mcp-Method` headers whose values **must match** the
> body's `_meta` — mismatches are rejected `400` with `-32020 HeaderMismatch`.
>
> **A conformance rule that lands on our discovery path:** clients **MUST**
> reject tool definitions whose `x-mcp-header` annotations are invalid, and
> **exclude those tools from the `tools/list` result** while logging a warning.
> One malformed definition must not poison the whole discovery.

1. **Fix D7 first** — a tool must be attachable to a connector. The honest fix
   is not a `connector_id` field on the create form; it is that **discovery
   writes tools**. `tools/list` returns tool definitions, so the discovery path
   should upsert them with `connector_id` set, a `remote_tool_id`, and a schema
   hash/version. Until that exists, `undiscovered`/`orphaned` stay unreachable.
2. **Real `tools/list`** over one connector, replacing the body of
   `list_connector_tools()`. The return contract already matches — that was the
   point of the seam (`ARCHITECTURE.md` §8).
3. **Approval before binding** — a newly discovered tool arrives `pending`
   (Phase 3.2), never auto-bindable. Discovery is not consent.
4. **Real healthchecks** — replace the ~18% random roll with an actual probe for
   the connectors that have a real endpoint. Keep the roll for simulated ones
   and make the difference visible; a fabricated green tick on a real connector
   is worse than no tick.

**Transport:** **Streamable HTTP** remote, `stdio` for local development —
verified against the spec, no longer a from-memory note. Our `McpTransport` enum
still carries `sse`, and all five seeded connectors use `sse://`; that now
describes a deprecated binding. Migrating the enum is a modelling decision, not
a rename — schedule it, don't slip it in.

**Dependency decision needed:** adopt the MCP Python SDK, or hand-roll the
JSON-RPC POST over the `httpx` already in `requirements.txt`? Hand-rolling is
genuinely small now the protocol is stateless. Check the SDK's spec-revision
support before choosing.

**De-risking:** the client is *protocol* code, not connector-specific code. It
can be built and verified against any conformant server — a local `stdio` one
needs no endpoint, no credentials and no Brightspeed dependency. Doing that
first means Phase 5B's answer only supplies a URL and an auth mode.

**Definition of done for 5A:** a real `tools/list` against the local server
writes tools into the catalog with `connector_id` set (D7 closed), those tools
arrive `pending` and are not auto-bindable, a malformed definition is excluded
with a warning, healthchecks probe a real socket, and a `verify_mcp_client.py`
suite covers all of it. **No stakeholder input required for any of that.**

---

### Phase 5B — Point it at a Brightspeed system ⛔ access-gated

**Everything that Phase 5A cannot do without someone else acting.** Deliberately
its own phase so the dependency is visible rather than buried inside a phase
that is otherwise ready to ship.

Needs, in the order they must arrive:

| Need | Concern | Note |
|---|---|---|
| Is the Atlassian estate Cloud or on-prem? | **Q10** | Cheapest to answer and the only one that can invalidate the target — Atlassian's remote MCP server is Cloud-only. If on-prem, **BigQuery becomes the stronger candidate** |
| Sign-off on the ranking | **Q13** | Needed to *call* Jira the reference connector, not to build the client |
| Tenant, OAuth app, credentials | **R9** | Longest lead. Open in parallel, never after |

**The work itself is small** if 5A held the seam: register a connector with a
real endpoint and auth mode, exchange credentials, run the same `tools/list`
against it. If 5B turns out to be large, 5A leaked POC assumptions past the seam
— that is the signal to watch for.

**Transport reality check:** target **Streamable HTTP** for a remote endpoint.
Our `McpTransport` enum still carries `sse` and all five seeded connectors use
`sse://`, which is a deprecated binding (**D8**) — migrate the enum during 5A,
while nothing real depends on it.

---

### Phase 6 — Policy-enforcing gateway ✅ *(shipped 2026-08-11 — slide 21 elements 1, 4, 5)*

**Where the POC became genuinely defensible.** Every check is our own logic, so
none of it needed a remote counterparty. Full design in `ARCHITECTURE.md` §16.

Merged the old Phase 4 (data boundary) and Phase 5 (identity). One route,
`POST /v1/gateway/tool-call`, runs **eleven checkpoints** deny-by-default and
then performs the invocation itself:

| # | Checkpoint | Source |
|---|---|---|
| 1 | `identity` | slide 21 el. 5 · Blueprint §8.1 |
| 2 | `catalog` | Tool Registry |
| 3 | `agent` | Agent Registry |
| 4 | `write_capable` | slide 25 · SOW boundary |
| 5 | `approval` | Blueprint §11 · Phase 3.2 |
| 6 | `allowlist` | R8 guard — `bound_tools` **is** the allowlist (**closes Q7**) |
| 7 | `connector_health` | Phase 0's resolver |
| 8 | `identity_binding` | slide 21 el. 5 — `service_account`, `iam_principal`, `approved_identities` |
| 9 | `data_boundary` | slide 21 el. 4 — `allowed_datasets`, `allowed_fields` |
| 10 | `hitl` | slide 22 — now server-enforced, was client-side |
| 11 | `rate_limit` | D6 — per (agent, tool), counted from the audit trail |

**R7 is closed inside the POC boundary, and the claim has to be made precisely.**
Because Phase 5A gave the gateway a real socket, latency is measured and failure
is observed — the two things that made the trail non-authoritative. The honest
claim is **"authoritative for every call that passes through the gateway"**, and
`tool_calls.gateway` / `invocation` keep the three row shapes distinguishable in
the data so the claim cannot quietly widen. What remains outside the boundary is
not the audit's fidelity but the counterparty's identity — a real IAM principal
instead of a persona. Say both halves.

**Five things to not weaken:**

1. **`write_capable` is checked before `approval`, exactly as in `bind_tool()`.**
   The invariant now lives in two modules on purpose — design-time and run-time
   are separate gates. It also means Q6's exception path is a change in **two**
   places; changing one produces a tool that cannot be bound but can be called.
2. **A denial is a 200 with a verdict, never a 4xx.** Denials are the most
   valuable rows in the table; making them HTTP errors invites callers to
   swallow them.
3. **`gateway = True` is written in one function and settable from no payload.**
   If a second writer appears, R7 reopens.
4. **Authoring and policy are disjoint field sets on disjoint routes.** An author
   who could widen their own data boundary is the hole this phase closes.
5. **Empty policy means undeclared, not deny-all** — and the gap is recorded on
   every call rather than passing silently. The decision is `CONCERNS.md` **Q14**.

**Also closed:** **Q7** (`bound_tools` is the allowlist; no `allowed_agents`
column — see the entry for why, and for why it still wants a stakeholder nod).
**Also opened:** **R11** (the gateway is the governed path, not the only path —
`POST /v1/tool-calls` still exists), **Q14**, **E5**.

**Verification:** `verify_tool_gateway.py` — **215 assertions** at this phase
(233 after Phase 7), including a
denial for every one of the eleven checkpoints and a live invocation with
measured latency and real field redaction.

---

### Phase 7 — MCP Gateway view ✅ *(shipped 2026-08-11 — slide 21 element 1's picture)*

**The last phase this workstream builds.** Agents → gateway → connectors →
systems, with the checkpoints marked and carrying their real denial counts.
Design in `ARCHITECTURE.md` §17.

- `GET /v1/gateway/graph` — **pure derivation**: no new tables, no new
  enforcement, no persisted state. Edges from the tool→connector lookup Phase 0
  walks, the chain from `CHECKPOINTS` itself, counts aggregated in SQL over
  `tool_calls` where `gateway = TRUE`.
- A 5th tab on `/tools`. Fixed-height rows make edge endpoints computable; one
  SVG with a `viewBox` draws each route as **two** curves so it passes *through*
  the checkpoint stack rather than jumping it. Stroke colour carries connector
  health.
- **Local tools are counted, never given a placeholder node**; agents with no
  route still appear with zero edges. A tidier picture that misrepresents the
  estate is worse than an honest gap.
- **It found R12 on its first run** — 77 connectors, 72 of them `zz-verify-*`
  residue from suite runs. Every list view sorts those to the bottom where nobody
  scrolls; this is the first surface that renders all connectors at once. The
  view draws only what is reached and states the hidden count.
- `verify_tool_gateway.py` **215 → 233 assertions** (layer 2b). A read-only view
  can drift from what it depicts and still render beautifully, so every new
  assertion is a *consistency* check against the source, not a shape check.

**The test to apply to any change here:** if it needs to store something, the
phase before it was left unfinished.

---

### Phase 8 — Connector expansion ⛔ *out of 90-day scope by contract*

Expand beyond the reference connector using the Phase 5A + 6 pattern, in the
order Phase 4's backlog set. Everything here is repetition of a proven thing,
which is why it is last — and why the SOW scopes it out: *"Will not
production-integrate every internal application or connector in 90 days… backlog
the rest."*

---

### What remains — the build work is done

**Phases 0 through 7 are shipped. Nothing further is engineering-gated.**
Everything left is gated on someone other than us:

| | Status | Gated on |
|---|---|---|
| **Phase 5B** — point the client at a real Brightspeed system | access-gated, **not** engineering-gated | **Q10** (Cloud or on-prem — the only one that can invalidate Jira as the target), **Q13** (ranking sign-off), **R9** (tenant, OAuth app, credentials — longest lead, open it in parallel) |
| **Phase 8** — connector expansion | out of 90-day scope | the SOW itself |
| **Q6 / D4 / D5** — the write-exception cluster | a governance decision | product owner |
| **Q14** — strict-by-default data boundaries | a governance decision **plus** a real dataset inventory per connector | product owner + R9 |

If 5B turns out to be large when access lands, 5A leaked POC assumptions past
the seam — that is the signal to watch for. It should be: swap an endpoint, add
an auth mode, run the same `tools/list`.

## 5. Open questions and standing risks

> **Moved to [`CONCERNS.md`](CONCERNS.md) on 2026-08-05.** Both tables lived here
> *and* in `MCP_WORKSTREAM.md`, which both documents admitted ("same id, same
> risk, in both documents") and which is exactly how they drift. The register is
> now the single source; ids are unchanged.

| What used to be here | Where it is now |
|---|---|
| §5 Open questions Q1–Q10 | `CONCERNS.md` → **Q** section |
| §6 Standing risks R1–R10 | `CONCERNS.md` → **R** section |
| §3 Divergences D1–D8 | `CONCERNS.md` → **D** section (§3 above keeps the short table, since the build plan reasons about them directly) |
| Appendix — observed outside this workstream | `CONCERNS.md` → **X** section |

**The ones that most affect this plan**, by id — read them there, not here:
**Q5** (which connector, now *our* deliverable) · **R9** (access is the long-lead
item) · **D7** (a tool cannot be attached to a connector) · **D8** (our transport
model contradicts the spec) · **R7** (the audit trail is not yet authoritative).

---

## 7. Product Blueprint reconciliation *(added 2026-08-04)*

Management shared the **Agent Ops & Governance Platform — Product Blueprint**
(27pp). It is a *product* document — broader and less prescriptive than the deck
— and it **validates the architecture rather than changing it.** This section
records the deltas so they are not re-derived.

### 7.1 What it confirms

| Blueprint | Our code |
|---|---|
| §3.4 permission type: read · summarize · draft · recommend · validate · create · update · approve · deploy | The exact 5-allowed / 4-blocked split, as a locked enum + `write_capable`. **Two independent sources now agree — D1 is closed.** |
| §3.4 key output: *"Tool-call audit design"* | Phase 1 `tool_calls` |
| §4.5 control: *"Tool-call audit log"* | Phase 1 |
| §3.5: *"Monitor tool-call latency and failures"* | `latency_ms` + `result_status` |
| §3.4 metadata: *"System accessed"* | Phase 0 `resolve_tool_connector()` → `system_accessed` |
| §3.5: *"Test MCP connector"* | `POST /v1/connectors/:id/healthcheck` |
| §3.5: *"Auto-discover tools where supported"* | `GET /v1/connectors/:id/tools` (real RPC is Phase 7) |
| §3.5 key output: *"Connector backlog"* | Phase 7, matching slide 21 element 7 |
| §8.1: *"MCP connector health"* | the §8 cascade |

**Phases 0 and 1 need no rework.** Everything shipped is explicitly required.

### 7.2 Unbuilt scope it adds

**Tool object** (§3.4) — we model name, description, input/output schema, system
accessed, permission type, version, status. Missing: **`owner`**, **`risk_level`**,
`business_purpose`, `authorization_rule`, **`allowed_agents`**, `allowed_users`,
`rate_limits`, `timeout`, `logging_requirement`, `human_approval_requirement`,
`error_handling`. See D6.

**Connector layer** (§3.5) — missing *set allowed agents*, *set logging
requirement*, *track connector usage*. The third is now nearly free:
`GROUP BY system_accessed` over `tool_calls`.

**Sequencing** (§12) — Tools & MCP sits in **Increment 2** (*Assets + Workflow +
Evaluation*), not Increment 1. Useful context for prioritization arguments; it
does not change what we build.

### 7.3 Technical divergence (§6) — real, but not today's problem

| Blueprint target | Ours |
|---|---|
| One Cloud Run service **per domain** | single FastAPI app |
| **BigQuery** (telemetry, eval, FinOps) + Firestore/Cloud SQL (operational) | Postgres + pgvector |
| **Vertex AI / Gemini** | Anthropic Claude + OpenAI embeddings |
| API Gateway / Apigee, IAM, Secret Manager | none |

We are a local prototype; that is the production target. Two things in our
favour: the `routes/ · services/ · repositories/` split maps 1:1 onto per-domain
Cloud Run services, and dict-in/dict-out routes port cleanly. A BigQuery
telemetry export would be **additive** to `tool_calls`, not a rewrite.

The Gemini-vs-Claude question is real and belongs to whoever owns the model
layer — Blueprint §3.7 defines a **Model Repository** for exactly that. Not ours.

### 7.4 Watch: `tool_calls` vs. the Blueprint's `Runtime Trace`

§5 lists **Runtime Trace** as its own core data object, and §8.1's per-request
trace wants `User` and `Team` — which `tool_calls` does not carry (we have
`consumer`, i.e. which *surface* issued the call, not which *person*).

Our table is a **slice** of that object, scoped to tool invocations. When the
Monitoring workstream builds Runtime Trace there is a real risk of two
overlapping stores. Raise it then; do **not** pre-emptively widen `tool_calls`
into a general trace table — that would blur a governance artifact into a
telemetry one.

---

## Appendix — observed outside this workstream

> **Moved to [`CONCERNS.md`](CONCERNS.md) → X section** (X1–X7). Five
> observations recorded during the original codebase read, plus two found since:
> a failed retrieval taking down the whole chat, and there being **no bind
> button anywhere in the UI**. Not ours to fix; named workstream on each.
