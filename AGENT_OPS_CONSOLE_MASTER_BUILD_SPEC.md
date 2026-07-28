# BRIGHTSPEED AGENT OPS & GOVERNANCE CONSOLE

## Master Build Specification v1.0 — Full Web Application

| | |
|---|---|
| **Document type** | Implementation specification for an AI coding agent (Claude Code) |
| **Target output** | A complete, running single-page web application |
| **Date** | 2026-07-28 |
| **Supersedes** | The static 7-phase wizard POC (wizard becomes ONE module inside this console) |
| **Ground truth** | Brightspeed New-Agent Onboarding Blueprint v1.0.0 (all decisions LOCKED there are LOCKED here) |

---

## 0. HOW TO USE THIS DOCUMENT (INSTRUCTIONS TO THE CODING AGENT)

You are building the **Brightspeed Agent Ops & Governance Console**: a Databricks-style, multi-module workspace application for governing the full lifecycle of AI agents. The previous deliverable was a single static onboarding wizard. This document upgrades that into the **whole control plane**: registry, onboarding, prompts, tools/MCP, knowledge & RAG, governance, evaluation, monitoring/FinOps, A2A directory, and a playground — all sharing one canonical schema and one simulated platform kernel.

Rules of engagement:

1. **This document is the single source of truth.** Where it quotes the Blueprint (schema fields, signal weights, governance matrix, phase names), reuse that vocabulary **verbatim**. Never rename `risk_tier` to `riskLevel` or "Capture Intent" to "Intake".
2. **Everything runs client-side.** There is no server. The "backend" is a simulated platform kernel (Section 6) living in the browser: an in-memory store seeded from static JSON, a fake async job queue, and deterministic engine logic. It must *feel* like a real distributed platform (latency, job states, provisioning delays) without being one.
3. **Build in the milestone order of Section 14.** Each milestone ends with a working, navigable app.
4. **Deterministic over clever.** All "AI" behavior (the synthesis engine, playground answers, eval runs) is deterministic rule/keyword/template logic per Sections 7 and 11 — auditable, repeatable, demoable. No real LLM calls, no API keys.
5. **Do not use localStorage/sessionStorage.** State lives in memory (Zustand store). Provide Export/Import Workspace JSON instead (Section 6.6).
6. **Acceptance criteria in Section 15 are the definition of done.** Verify each item before declaring a milestone complete.

---

## 1. PRODUCT OVERVIEW & DESIGN INTENT

### 1.1 What this is

A **control plane console** through which every Brightspeed agent is registered, assessed, configured, governed, evaluated, deployed, and monitored. The mental model is Databricks / GCP Console: a persistent dark left navigation of platform capabilities, a content pane of list→detail views, and wizards/panels for creation flows.

Core thesis (LOCKED, from Blueprint §2.1): **"An agent is data, not code."** Onboarding produces one complete, validated agent specification (a config). Model, prompts, tools, orchestration shape, and risk are all settings. The console is therefore fundamentally a **schema editor with governance** — every screen is a different lens over the same canonical agent config.

### 1.2 Governing principles (NON-NEGOTIABLE, carried from Blueprint §2.2)

1. **One process, any agent.** The seven-phase lifecycle never changes; only which settings are filled changes.
2. **Metadata alone runs nothing.** Three tracks — Registry (describes/governs), Runtime (executes), Content (feeds) — each have independent status. An agent is LIVE only when all three are green. The console surfaces this everywhere (status pills, swimlanes, dashboard).
3. **Back-proof, single canonical schema.** Same schema for new-agent and existing-agent onboarding. Provenance envelope (`value_source`, `verified_flag`, `confidence`, `gap_note`) on every field.
4. **Advisory base scope only.** `tool_permission ∈ {read, summarize, draft, recommend, validate}`. Write verbs (create/update/approve/deploy/send/delete) are detected, FLAGGED, and never bound.
5. **No silent tier promotion.** Every engine-proposed tier bump is surfaced for human confirmation.

### 1.3 Seven-phase lifecycle (IMMUTABLE)

Phase 1 Capture Intent → Phase 2 Create Work Package → Phase 3 Register → Phase 4 Configure Workflow → Phase 5 Add Governance Gates → Phase 6 Evaluate & Approve → Phase 7 Deploy / Monitor / Improve. Tiers change values, never steps.

### 1.4 Capability tiers and risk tiers (orthogonal)

- Capability: `minimal` ("Simple Advisor"), `standardized` ("Knowledge Assistant" — the default), `advanced` ("Team Coordinator"). Defines WHAT the agent can do.
- Risk: `low | medium | high | critical`. Defines HOW it is governed. Inferred from data sensitivity, tool permissions, audience scope, regulatory domain — never from capability alone.
- Governance path = f(capability_tier, risk_tier) per the matrix in Section 8.1.

### 1.5 Personas the console serves

- **Business owner** — creates agents via the wizard, tracks approvals, reads cost.
- **Platform engineer** — manages tools/MCP connectors, runtime status, pipelines.
- **Governance officer** — works the approvals queue, risk matrix, audit log.
- **Team lead / consumer** — browses the A2A directory, tests agents in the Playground.

The app does not implement authentication. A **persona switcher** in the top bar (avatar menu) toggles the active persona; some actions are persona-gated (e.g., only Governance Officer can approve) purely as a UI simulation.

---

## 2. TECH STACK & PROJECT STRUCTURE

### 2.1 Stack (fixed)

- **Vite + React 18 + TypeScript** (strict mode).
- **react-router-dom v6** — one route per module, nested routes for detail views.
- **Zustand** — single workspace store (the platform kernel state) + slice pattern.
- **Tailwind CSS** — all styling via utility classes + a small set of CSS variables for theme tokens (Section 3). No component library; build the ~15 primitives by hand for full visual control.
- **Recharts** — dashboard and monitoring charts.
- **lucide-react** — icons.
- No other runtime dependencies.

### 2.2 Directory layout

```
agent-ops-console/
├── index.html
├── vite.config.ts / tsconfig.json / tailwind.config.js
├── src/
│   ├── main.tsx / App.tsx            # router + shell
│   ├── theme/tokens.css
│   ├── types/                        # canonical schema types (Section 5)
│   │   ├── agent.ts  provenance.ts  assets.ts  governance.ts  telemetry.ts
│   ├── kernel/                       # simulated platform (Section 6)
│   │   ├── store.ts                  # Zustand root store
│   │   ├── api.ts                    # service façade mirroring REST endpoints
│   │   ├── jobs.ts                   # async job queue simulation
│   │   ├── engine/                   # synthesis engine (Section 7)
│   │   │   ├── nlu.ts  signals.ts  templates.ts  writeDetect.ts
│   │   │   ├── confidence.ts  elicitation.ts  reviewCard.ts  evalGen.ts
│   │   ├── governance.ts             # matrix, paths, approvals (Section 8)
│   │   ├── pipelines.ts              # content pipeline simulation
│   │   ├── telemetry.ts              # seeded telemetry generator
│   │   └── rng.ts                    # seeded PRNG (mulberry32)
│   ├── seed/                         # seed data (Section 13) as .ts modules
│   ├── components/
│   │   ├── shell/                    # LeftNav, TopBar, PageHeader, Breadcrumbs
│   │   ├── primitives/               # Button, Card, Badge, Table, Drawer, Modal,
│   │   │                             # Tabs, Tooltip, EmptyState, StatusPill,
│   │   │                             # ProvenanceChip, TierBadge, RiskBadge, JsonViewer
│   │   └── domain/                   # ReviewCard, ThreeTrackSwimlanes, SignalTable,
│   │                                 # GovernanceMatrix, SchemaFieldRow, AssetRefLink
│   └── modules/                      # one folder per nav module (Section 9)
│       ├── home/  registry/  onboarding/  prompts/  tools/
│       ├── knowledge/  governance/  evaluations/  monitoring/
│       ├── a2a/  playground/
```

### 2.3 Global conventions

- Every module page = `PageHeader` (title, description line, primary action) + content.
- Every list view: filterable table with column sort, search box, status filters; row click → detail route.
- Every detail view: header (name, badges, status pills for three tracks) + tab bar.
- Every entity has a **JSON tab** showing its full canonical record via `JsonViewer` (collapsible, copy button) — this reinforces "an agent is data."
- All destructive/state-changing actions produce an **audit event** (Section 8.5) and a toast.
- Loading states: skeleton rows; all kernel calls resolve on simulated latency (Section 6.3).

---

## 3. DESIGN SYSTEM (DATABRICKS-STYLE)

### 3.1 Layout

```
┌──────────────────────────────────────────────────────────────┐
│ TopBar (h-12): product wordmark · global search · persona ▾  │
├───────────────┬──────────────────────────────────────────────┤
│ LeftNav       │  Content pane (scrolls independently)        │
│ (w-60, dark,  │  ┌ PageHeader ─────────────────────────────┐ │
│  collapsible  │  │ Title            [Primary action]       │ │
│  to w-14      │  └─────────────────────────────────────────┘ │
│  icon rail)   │  [tabs / table / detail…]                    │
└───────────────┴──────────────────────────────────────────────┘
```

- LeftNav: `+ New` button at top (accent red-orange like Databricks, opens create menu: New Agent → onboarding wizard; New Prompt; Register Tool; Add Knowledge Source), then grouped nav sections with small uppercase group labels (Section 4). Active item: filled pill background + left accent bar. Collapse toggle at bottom.
- TopBar: wordmark "◆ Brightspeed **Agent Ops**", global search (Cmd+K modal searching agents/prompts/tools/sources by name), persona switcher, help `?`, and a "Reset demo" action (re-seeds the kernel).

### 3.2 Theme tokens (dark, single theme)

```css
--bg-canvas:#0B1220;   --bg-surface:#111A2C;  --bg-raised:#16213A;
--bg-nav:#0A0F1C;      --border:#233250;      --border-strong:#33476B;
--text-hi:#E8EEF9;     --text-mid:#9FB0CC;    --text-low:#647291;
--accent:#3D7EFF;      --accent-new:#E4572E;  /* + New button */
--ok:#2FBF71;  --warn:#E5A50A;  --err:#E5484D;  --info:#7C5CFF;
--tier-minimal:#8A93A6; --tier-standardized:#3D7EFF; --tier-advanced:#7C5CFF;
--risk-low:#2FBF71; --risk-medium:#E5A50A; --risk-high:#F76808; --risk-critical:#E5484D;
```

Typography: Inter (UI), JetBrains Mono (code/JSON/IDs). Base 14px, page titles 20px/600. Radius 8px cards / 6px controls. Spacing on a 4px grid. Focus rings `--accent` 2px. Charts use `--accent`, `--info`, `--ok`, `--warn` only.

### 3.3 Signature domain components

- **StatusPill** — `✅ ready | ⏳ provisioning/indexing | ❌ blocked | ○ not-started`, used for track status everywhere.
- **ThreeTrackSwimlanes** — three columns (REGISTRY / RUNTIME / CONTENT), each a card with StatusPill, sub-step list, timestamp; banner above: `Agent Status: LIVE` (green) only if all ✅, else `NOT LIVE (waiting on: …)`.
- **TierBadge / RiskBadge** — colored badges with plain-language tooltip (e.g., Standardized → "Knowledge Assistant").
- **ProvenanceChip** — tiny chip on any field row: `U user · S system · D default · I inferred · G generated`, with confidence dot (green/amber/red) and `gap_note` tooltip. Clicking opens the field's provenance envelope JSON.
- **ReviewCard** — renders the engine's review card JSON (Section 7.8): proposed tier + archetype, signal breakdown table, config summary grid, governance summary, ⚠️ fields-requiring-confirmation list with inline edit, actions `[Confirm] [Change Tier] [Edit]`.
- **GovernanceMatrix** — 3×4 grid of capability × risk with the active cell highlighted.

---

## 4. INFORMATION ARCHITECTURE — LEFT NAVIGATION

Routes and grouping (Databricks-style group labels):

```
＋ New ▾
Home                          /home

WORKSPACE
  Agent Registry              /agents          (+ /agents/:id with tabs)
  Onboarding                  /onboarding      (7-phase wizard + drafts list)
  Playground                  /playground      (+ /playground/:agentId)

ASSETS
  Prompt Repository           /prompts         (+ /prompts/:id)
  Tools & MCP                 /tools           (tabs: Tool Catalog | MCP Connectors)
  Knowledge & RAG             /knowledge       (tabs: Sources | Pipelines | Indexes)
  A2A Directory               /a2a             (+ /a2a/:agentId card view)

GOVERNANCE
  Approvals & Gates           /governance      (tabs: Queue | Matrix & Policies | Audit Log)

OPERATIONS
  Evaluations                 /evaluations     (+ /evaluations/:packId)
  Monitoring & FinOps         /monitoring      (tabs: Health | Usage & Cost)
```

Deep-linking is first-class: every tab and detail view has a URL. The wizard resumes drafts via `/onboarding/:draftId/phase/:n`.

---

## 5. DOMAIN MODEL — CANONICAL SCHEMA (56 FIELDS, 13 GROUPS)

The single most important part of the codebase. Field names are **verbatim from the Blueprint** and must appear with these exact keys in TypeScript types, JSON views, and exports.

### 5.1 Provenance envelope (on EVERY leaf field)

```ts
type ValueSource = 'user' | 'system' | 'default' | 'inherited' | 'inferred';
type Confidence  = 'high' | 'medium' | 'low';

interface Prov<T> {
  value: T;
  value_source: ValueSource;
  verified_flag: boolean;
  confidence: Confidence;
  gap_note: string | null;
}
```

The store keeps every schema leaf wrapped in `Prov<T>`. UI components read `.value`; ProvenanceChip reads the envelope.

### 5.2 Schema groups and fields

| Group | Fields |
|---|---|
| **5.1 Identity & Ownership** | `agent_name, agent_id, business_owner, technical_owner, executive_sponsor, use_case_category, consumer_type, intended_audience, description, objective` |
| **5.2 Lifecycle & Risk** | `lifecycle_status, risk_tier, last_review_date, next_review_date, exception_status` |
| **5.3 Model** | `model_primary, model_fallback, temperature, max_output_tokens, context_window_ref, cost_awareness` |
| **5.4 Prompt & Instruction** | `system_prompt_ref, user_prompt_template, task_prompt, persona_role, tool_use_instructions, safety_instructions, citation_rules, response_format_contract, stop_conditions, per_sub_agent_prompts` |
| **5.5 Data & Knowledge** | `data_sources, rag_enabled, retrieval_type, chunk_size, chunk_overlap, top_k, score_threshold, knowledge_source_refs, structured_grounding` |
| **5.6 Tooling & MCP** | `bound_tools, tool_permission, mcp_connectors, tool_auth, rate_limits` |
| **5.7 Orchestration** | `orchestration_type, sub_agents, retries, fallback_behavior, hitl_gate_placement, a2a_enabled, agent_card, message_task_format, artifact_exchange` |
| **5.8 Governance & Approval** | `approvals_required, audit_level, policy_controls` |
| **5.9 Observability & FinOps** | `cost_label, logging_level, required_telemetry` |
| **5.10 Deployment** | `exposure_channel, auth_gating, deploy_rate_limits, environment, promotion_rollback` |
| **5.11 Runtime (execution)** | `runtime_host, resolver_profile, concurrency, timeout, scaling_policy, model_gateway_ref` |
| **5.12 Knowledge Sources (per RAG source)** | `source_uri, parser, source_chunking, embedding_model, index_target, sensitivity, source_approval, refresh_cadence, source_version` |
| **5.13 Evidence & Artifact Store** | `evidence_store_uri, evidence_retention, artifact_links` |

Key enums (verbatim):

```ts
type CapabilityTier   = 'minimal' | 'standardized' | 'advanced';
type RiskTier         = 'low' | 'medium' | 'high' | 'critical';
type LifecycleStatus  = 'draft' | 'registered' | 'in_review' | 'approved' | 'live' | 'suspended' | 'retired';
type OrchestrationType= 'single' | 'router' | 'coordinator+subagents';
type ToolPermission   = 'read' | 'summarize' | 'draft' | 'recommend' | 'validate';  // advisory-only, LOCKED
type RetrievalType    = 'semantic' | 'keyword' | 'hybrid';
type GovernancePath   = 'fast' | 'standard' | 'deep' | 'critical';
type TrackStatus      = 'not_started' | 'in_progress' | 'ready' | 'blocked';
```

The `AgentRecord` aggregates: `config` (all 13 groups, `Prov`-wrapped), plus platform state: `capability_tier`, `governance_path`, `tracks: {registry, runtime, content}` each `{status: TrackStatus, steps: {name, status, at}[]}`, `signal_breakdown`, `review_card`, `evaluation_pack_id`, `approval_ids`, `fast_path_expiry_date`, `created_at`, `demo_mode: boolean`.

### 5.3 Asset reference scheme (verbatim URI schemes)

`prompts://<id>@<version>` governed prompts · `tools://<id>@<version>` governed tools · `policies://<id>@<version>` safety/citation/policy assets · `kb://<id>@<version>` knowledge bases · `vector://<index-id>` vector indexes · `vertex://<model-endpoint>` model endpoints · `gs://<bucket>/<path>` storage URIs.

Component `AssetRefLink` renders any such URI as a monospace chip; clicking navigates to the owning module's detail view (e.g., `prompts://noc-summarizer@v2` → `/prompts/noc-summarizer`). Unresolvable refs render with a ⚠️ tooltip "asset not in catalog" — never crash.

### 5.4 Other entities

- **PromptAsset** `{id, version, name, kind: 'system'|'safety'|'citation'|'template', body, status: 'draft'|'approved'|'deprecated', owner, used_by: agent_id[], history: {version, date, note}[]}`
- **ToolAsset** `{id, version, name, description, category, permission_ceiling: ToolPermission, write_capable: boolean, connector_id, schema: {inputs, outputs}, status, used_by}`  — `write_capable:true` tools exist in the catalog but can never be bound (Section 7.6); they render with a red "WRITE — advisory-block" badge.
- **McpConnector** `{id, name, transport: 'sse'|'stdio'|'http', endpoint, auth_mode: 'secret_manager'|'oauth'|'none', status: 'connected'|'degraded'|'offline', tools_provided: tool_id[], last_healthcheck}`
- **KnowledgeSource** — the 5.12 group verbatim + `{id, name, ingestion: PipelineRun[], document_count, index_size_mb}`
- **PipelineRun** `{id, source_id, stages: [{name: 'Ingest'|'Parse'|'Chunk'|'Embed'|'Index'|'Tag & Govern'|'Refresh', status, started_at, duration_s, items}], trigger: 'manual'|'scheduled', overall: TrackStatus}`
- **EvaluationPack** `{id, agent_id, generated_by: 'engine', cases: EvalCase[], last_run: {date, score, results}}`; `EvalCase` `{test_id, category: 'grounding'|'correctness'|'safety_boundary'|'latency_cost'|'regression', input, expected_output, evaluation_method, pass_threshold, last_result: 'pass'|'fail'|null}`
- **ApprovalItem** `{id, agent_id, step: 'business_owner'|'risk_officer'|'security_committee'|'data_source', required_by_path, status: 'pending'|'approved'|'rejected', actor_persona, decided_at, note}`
- **AuditEvent** `{id, at, actor_persona, action, entity_type, entity_id, detail}` — append-only.
- **AgentCard** (A2A) `{agent_id, skills: string[], input_schema, output_schema, endpoint, discovery_only: boolean}`

---

## 6. THE SIMULATED PLATFORM KERNEL

The kernel is the app's fake backend. **No UI component touches the store directly for mutations** — everything goes through `kernel/api.ts`, whose function names mirror the Blueprint's REST API so the app could later be rewired to a real backend:

```
api.synthesize(intent) → {job_id}          // POST /v1/agents/synthesize
api.getSynthesisJob(job_id)                // GET  /v1/agents/synthesize/:id/status
api.validate(config)                       // POST /v1/agents/validate
api.register(config)                       // POST /v1/agents/register
api.getAgentStatus(agent_id)               // GET  /v1/agents/:id/status
api.provision(agent_id)                    // starts runtime+content track jobs
api.approve(approval_id, decision, note)   // governance actions
api.runEvaluation(pack_id)                 // eval runner
api.triggerPipeline(source_id)             // manual refresh
```

### 6.1 Store shape (Zustand slices)

`agents[] · prompts[] · tools[] · connectors[] · sources[] · pipelineRuns[] · evalPacks[] · approvals[] · auditLog[] · jobs[] · telemetry (generated) · ui (persona, nav collapsed, search open)` + `reset()` re-seeding everything from `/seed`.

### 6.2 Async job queue (`kernel/jobs.ts`)

All long operations create a `Job {id, kind, status: 'queued'|'processing'|'completed'|'failed', progress, result}` and advance via `setTimeout` chains:

- `synthesis` — 1.5–3.5s (Advanced-tier intents take the top of the range; the UI shows "Draft generating…" per the Blueprint's async engine pattern).
- `runtime_provision` — 4–8s, advancing named sub-steps: `Resolver profile → Runtime host (Cloud Run|GKE) → Model gateway (vertex://…) → MCP sidecars → Telemetry sink`.
- `content_index` — 6–12s per source, advancing the seven pipeline stages with per-stage item counts.
- `evaluation_run` — 2–4s, then per-case pass/fail per Section 11.3.

Jobs emit store updates on each transition so status pills animate live. A tiny **job tray** in the TopBar (spinner + count) lists active jobs.

### 6.3 Simulated latency

Every `api.*` read resolves after 150–400ms (seeded RNG); mutations 300–700ms. This makes skeletons and optimistic states real rather than decorative.

### 6.4 Determinism

`kernel/rng.ts` exports a mulberry32 PRNG seeded with a fixed constant. ALL randomness (latencies, telemetry curves, eval jitter) flows from it, so two demo runs look identical. "Reset demo" restores the initial seed.

### 6.5 Demo mode (Blueprint D9)

If a user opens the Playground for an agent whose Content track is not ✅, the kernel offers **Demo Mode**: it marks the agent `demo_mode: true`, attaches index `vector://alloydb-demo`, and the Playground banner shows "DEMO MODE — responding with synthetic data." Auto-clears when the content job completes.

### 6.6 Export / Import workspace

TopBar menu → "Export workspace JSON" downloads the full store (agents, assets, audit log). "Import" re-hydrates. This is the persistence story (no browser storage APIs).

---

## 7. THE OBJECTIVE-TO-ARCHITECTURE SYNTHESIS ENGINE (DETERMINISTIC IMPLEMENTATION)

The engine converts `{objective, intended_audience?, data_sources?, tools?, owners?}` into a full validated config through the Blueprint's **7 stages**. Implement each stage as a pure function; the synthesis job runs them in sequence and stores per-stage output on the draft (the wizard's "engine trace" panel shows all 7 stages — great for demos).

### 7.1 Stage 1 — Intake & Normalize (`nlu.ts`)

Keyword/regex NLU over the objective text extracts: `task_type` (first matching verb class: answer/summarize/analyze/draft/route/coordinate), `domain` (dictionary: HR, network_ops, finance, legal, support, sales…), `data_source_mentions` (from "from X", "based on", "using", plus the explicit data_sources input), `tool_mentions`, `audience`, `output_format`. Every canonical field not derivable is tagged `gap_note`.

### 7.2 Stage 2 — Archetype classification (`signals.ts`) — EXACT WEIGHTS, LOCKED

Six signals with detection rules and weights (Blueprint Appendix F, verbatim):

| Signal | Fires when objective/inputs contain | Weights (Min/Std/Adv) |
|---|---|---|
| S1 Retrieval Need | "documents", "knowledge", "from X", "based on", "using data", "grounded in", or ≥1 data source given | 0 / **+10** / +5 |
| S2 Multi-Skill | >1 distinct action verb (summarize AND flag, analyze AND draft…) | 0 / +3 / **+10** |
| S3 Cross-System | >1 distinct system mentioned (ticketing + Slack + email…) | 0 / +5 / **+10** |
| S4 Tool Actions | explicit tool/API/action language, or tools[] provided | +5 / +5 / +5 |
| S5 Hand-off/Routing | "route to", "escalate to", "assign to", "hand off", "notify X" | 0 / +2 / **+10** |
| S6 Explicit Multi-Agent | "coordinator", "orchestrator", "team of agents", multiple "agent"/"bot" mentions | 0 / 0 / **+15** |

```
score_minimal      = 20                          // base
score_standardized = S1 + S2 + S3 + S4 + S5
score_advanced     = S2 + S3 + S4 + S5 + S6
winner = argmax(...)
```

Override rules (hard gates): `S6 > 0 → force Advanced review`; `tools.length >= 4 → force Advanced review`; `S1=0 ∧ S2=0 ∧ S3=0 → Minimal`. **Capability floor:** if S1 fired, the tier can never resolve below Standardized (retrieval requires RAG, which Minimal cannot do) — surface this as a "CAPABILITY FLOOR" callout in the proposal, exactly like the POC screenshot.

Output: `{proposed_tier, proposed_archetype, signal_breakdown: {S1..S6, fired, why}}`. Archetypes: `simple_advisor`, `rag_grounded_assistant`, `faq_bot`, `report_generator`, `research_assistant`, `workflow_coordinator` (template library, LOCKED list).

### 7.3 Stage 3 — Architecture synthesis (`templates.ts`)

Apply the winning tier template, then overlay extracted specifics:

- **Minimal:** `model_primary=vertex://gemini-1.5-flash`, no fallback, `rag_enabled=false`, `bound_tools=[]` (≤1 read tool), `orchestration_type=single`, `a2a_enabled=false`. Runtime: Cloud Run single container.
- **Standardized:** + `model_fallback=vertex://gemini-1.5-pro`, `rag_enabled=true`, `retrieval_type=hybrid`, `chunk_size=512`, `chunk_overlap=128`, `top_k=5`, `score_threshold=0.75`, `citation_rules=policies://citation-standard-v1`, 1–3 read tools, `a2a_enabled=true` discovery-only (`message_task_format=null`, `artifact_exchange=false`). Runtime: Cloud Run/GKE + vector store attached.
- **Advanced:** + sub-agent decomposition, `orchestration_type=coordinator+subagents`, full A2A (`artifact_exchange=true`, `message_task_format` set), per-sub-agent prompts, structured_grounding. Runtime: GKE/Vertex Agent Engine, HITL approval queues.

Sub-agent decomposition (Advanced only): template-match against the pattern library first (e.g., incident-response → log_analyzer / impact_assessor / comms_drafter / notification_router); otherwise derive one sub-agent per detected verb-cluster. Constraints (LOCKED): each sub-agent ≤3 tools, no write permissions, coordinator owns routing.

Per knowledge source, auto-generate the 5.12 ingestion config: `{source_uri, parser: 'document_ai'|'native', chunk_size: 512, chunk_overlap: 128, embedding_model: 'vertex://text-embedding-004', index_target: 'vector://alloydb-default', sensitivity: inferred, source_approval: 'pending', refresh_cadence: 'weekly'}` at `confidence: low` with gap_note "Auto-generated. Confirm with data owner."

### 7.4 Stage 3b — Write-action detection (`writeDetect.ts`) — the advisory-only guardrail

Ensemble simulated as two passes: (1) keyword list — `send, approve, deploy, update, create, delete, close, assign, notify, post, execute, modify` when paired with an object noun; (2) context disambiguator — a rule table distinguishing advisory phrasings ("draft an email" → advisory) from write phrasings ("send an email" → write). Any suspected write: the matching tool is **FLAGGED, never bound** — it appears in the review card under "⚠️ Write actions detected — advisory-only enforced", with `gap_note` set. `risk_tier` floor rises to `high` when write intent is detected.

### 7.5 Stage 4 — Confidence & provenance (`confidence.ts`) — LOCKED rules

`user_provided → high` · `system_default → high` · `engine_inferred (tier, orchestration, risk) → medium` · `engine_generated (sub_agents, chunk_size, 5.12 configs) → low` · governance-critical fields (`risk_tier, tool_permission, sensitivity`) → never `high` until user-confirmed. Any field with `confidence != high ∧ governance_critical` goes on the review card's ⚠️ list.

### 7.6 Stage 5 — Targeted elicitation (`elicitation.ts`)

Question bank keyed by gap type; a question qualifies only if its answer changes (a) tier, (b) risk tier, or (c) a low-confidence field. Rank by `priority = 0.4*architecture_impact + 0.3*risk_impact + 0.2*confidence_gap + 0.1*user_burden_penalty`. **MAX 3 questions** shown as a mini-form between "Generate proposal" and the review card; the rest become "optional clarifications" collapsed on the review card. Plain language only (e.g., "Does incident_db contain customer personal information?" → answer raises/lowers risk_tier).

### 7.7 Stage 6 — Review card (`reviewCard.ts`)

Emit exactly the Blueprint's structure: `{proposed_tier, proposed_archetype, signal_breakdown, config_summary, governance_summary, fields_requiring_confirmation[], editable: true, user_can_override_tier: true, user_can_override_risk: true}`. Tier override: upward freely; downward triggers a visible "engine re-evaluation" (re-runs Stage 2 and either concedes or shows why not, e.g., "Retrieval need detected — Minimal cannot ground answers").

### 7.8 Stage 7 — Validation & certification (`evalGen.ts`)

Auto-generate the evaluation pack from the config: per category, instantiate templates with agent specifics — Grounding ("Summarize <domain artifact X>" → expected: cites `kb://…`), Correctness, Safety/Boundary (always includes a write-refusal case: "Delete all <domain> records" → Refusal), Latency/Cost (p95 target by tier: 2s/5s/15s), Regression. Output `evaluation_pack.json` attached to the agent record and visible in `/evaluations`.

---

## 8. GOVERNANCE MECHANICS

### 8.1 Governance matrix — f(capability, risk) (LOCKED)

| Capability \ Risk | Low | Medium | High | Critical |
|---|---|---|---|---|
| Minimal | Fast | Standard | Standard | Deep |
| Standardized | Fast | Standard | Deep | Deep |
| Advanced | Standard | Deep | Deep | Critical |

Paths: **Fast** = auto-approve if schema valid; 1 HITL gate max (pre-deploy); 5-min auto-approval SLA (simulated: auto-approves ~10s after registration). **Standard** = business_owner approval + risk_officer review; 2 HITL gates. **Deep** = full Phase 6 eval (pack must score ≥90) + committee approval. **Critical** = Deep + mandatory runtime HITL per action (Playground shows an approval interstitial on every tool call).

### 8.2 Approval workflow

Registering an agent creates `ApprovalItem`s per its path. The Approvals Queue lists pending items; only the matching persona can decide (UI-gated). Approve/reject updates the agent's `lifecycle_status` and Registry track. Deep path additionally blocks until the eval pack's last run score ≥ 90 ("Promote to Production" stays locked).

### 8.3 Fast-path auto-expiry (D10)

Fast-path agents get `fast_path_expiry_date = live_date + 90 days`. The dashboard and registry show a countdown badge when <14 days (seed data includes one agent at 6 days). "Re-certify" button (Governance Officer) extends 90 days and logs an audit event; expiry flips the agent to `in_review` with path Standard.

### 8.4 Pre-Flight readiness gate (wizard entry — LOCKED)

11 prerequisites; 🔴 hard blockers (GCP project access, data sources reachable, credentials in Secret Manager, MCP connectors available, runtime host & model gateway, vector store provisioned, model endpoint approved) must ALL be green before Phase 1 — `[Start Onboarding]` disabled otherwise. 🟡 soft blockers (owners named, risk pre-assessed, source docs approved, evidence store set, review cadence) may proceed as "pending" with a warning chip. In the simulation, hard-blocker state derives from kernel state (e.g., a connector marked `offline` in `/tools` genuinely turns that check red — cross-module causality that makes the demo feel real).

### 8.5 Audit log

Every mutation appends an `AuditEvent`. The Audit Log tab is a filterable, append-only table (time, persona, action, entity link, detail). Export as JSON.

---

## 9. MODULE SPECIFICATIONS

Each module below: purpose → layout → interactions → kernel operations. All lists follow the global list-view conventions (Section 2.3).

### 9.1 Home — `/home`

Purpose: the platform's front page; answers "what's running, what needs me, what is it costing."

Layout (12-col grid):
- **Row 1 — stat tiles (5):** Total agents · Live (all tracks ✅) · Pending approvals · Monthly token spend ($) · Avg eval score. Each tile links to its module.
- **Row 2 left — "Needs your attention"** (per active persona): pending approvals (Governance Officer), drafts in progress (Business Owner), degraded connectors/pipelines (Platform Engineer), fast-path expiry warnings. Each row deep-links.
- **Row 2 right — Tier & risk distribution:** stacked bar (agents by capability tier) + 3×4 mini governance-matrix heatmap of agent counts.
- **Row 3 — Cost trend:** 30-day stacked area of daily token cost per agent (top 5 + other), from the telemetry generator.
- **Row 4 — Recent activity:** last 10 audit events.

### 9.2 Agent Registry — `/agents`

Purpose: the system of record; every screen elsewhere links back here.

List: columns Name · TierBadge · RiskBadge · Governance path · Lifecycle status · three mini track pills (R/R/C) · Owner · Cost (30d) · Updated. Filters: tier, risk, lifecycle, "LIVE only". Primary action `+ New Agent` → wizard.

Detail `/agents/:id` — header: name, agent_id (mono), badges, ThreeTrackSwimlanes (compact), actions by state: `[Provision]` (registered, approved) · `[Open in Playground]` (live) · `[Suspend]/[Retire]` (Governance Officer). Tabs:
1. **Overview** — objective, owners, archetype, signal_breakdown table (S1–S6 with fired/why), governance summary, fast-path expiry badge, linked assets (AssetRefLinks).
2. **Configuration** — the 13 schema groups as collapsible sections; every field a `SchemaFieldRow`: label (verbatim field name, mono), value, ProvenanceChip. Read-only except through "Propose change" (creates an audit event + for governance-critical fields a new approval item — demonstrating change control).
3. **Governance** — matrix with active cell highlighted, approval history timeline, HITL gate placements, audit events scoped to this agent.
4. **Evaluations** — pack summary, last run score ring, per-case results table, `[Run evaluation]`.
5. **Deployment** — full ThreeTrackSwimlanes with sub-steps and timestamps; runtime mapping card (host, gateway, vector index, connectors — per tier template); `[Provision]` kicks both jobs; live-updating.
6. **Telemetry** — sparklines: requests/day, p95 latency, token spend, error rate (30d) + eval-score history.
7. **JSON** — full canonical record with provenance envelopes; `[Export config]`.

### 9.3 Onboarding — `/onboarding` (the wizard, now one module among many)

Landing: drafts table (name, phase reached, tier proposal, updated) + `[Start new onboarding]` + the Pre-Flight gate status strip.

The wizard preserves the POC's structure — horizontal phase stepper (Pre-Flight ▶ 1…7), phases locked until predecessors complete — with these behaviors:

- **Pre-Flight:** 11-item checklist per Section 8.4; hard blockers derive from live kernel state.
- **Phase 1 Capture Intent:** objective textarea + audience, data sources (tag input), tools (tag input), owners → `[Generate proposal]` → async job → **Engine Proposal Card**: proposed archetype + plain-language tier name, three tier score chips (minimal/standardized/advanced with numeric scores, winner highlighted), signal table (S1–S6, fired dot, why), capability-floor callout when applicable, config preview (model/RAG/tools/orchestration), `[Confirm] [Change tier] [Edit details]`. An **"Engine trace"** expander shows all 7 stages' raw outputs.
- **Phase 2 Create Work Package:** in-scope/out-of-scope lists, DoR checklist (objective measurable, sources approved, eval cases drafted), DoD checklist (grounding/correctness pass, advisory-only confirmed, latency target). DoR items are hard stops for `[Next]`.
- **Phase 3 Register:** review card (Section 7.7) + elicitation questions (max 3) if pending; `[Register agent]` → creates AgentRecord, approval items, audit events; Registry track → ✅.
- **Phase 4 Configure Workflow:** tier-dependent progressive disclosure. Standardized: model primary/fallback, knowledge sources list (each row: parser, status, `[Edit 5.12 config]` drawer), citation rules picker, tool picker (max 3, read-only tools only; write-capable rows disabled with the red badge), A2A discovery toggle. **Advanced settings accordion** (collapsed; content varies by tier per Blueprint §4.12): temperature/max tokens/cost label; + RAG params (chunk_size 512, chunk_overlap 128, top_k 5, score_threshold 0.75), per-source ingestion, response schema; Advanced tier adds per-sub-agent prompts/models, orchestration controls (parallel/serial, max calls), scaling (min/max instances, concurrency, timeout), granular HITL triggers. Governance-critical fields NEVER live inside the accordion. Advanced tier also gets a **sub-agent editor**: card per sub-agent (name, role, prompt_hint, tools ≤3) + a simple SVG workflow diagram (coordinator → sub-agents) with HITL gate markers insertable on edges.
- **Phase 5 Add Governance Gates:** data sensitivity + regulatory domain selects → matrix cell highlights → path card (required approvals list, HITL placement select). Risk overrides here re-derive the path live.
- **Phase 6 Evaluate & Approve:** auto-generated eval pack table; `[Run evaluation]` job → per-case pass/fail + score ring; `[Promote to Production]` locked until score ≥ 90 AND all approvals granted (Deep path). Fast path: shows auto-approval countdown.
- **Phase 7 Deploy / Monitor / Improve:** ThreeTrackSwimlanes full-width; `[Provision runtime]` + `[Start content indexing]` buttons trigger the respective jobs; when all ✅ → confetti-free but satisfying "AGENT IS LIVE" banner + links to Playground / Monitoring / Registry.

### 9.4 Prompt Repository — `/prompts`

List with kind filter (system/safety/citation/template), status, used-by count. Detail: body in mono block with copy, version history timeline, used-by agent links, `[New version]` (drafts a v+1, status draft) and `[Approve]` (Governance Officer). Prompts referenced by any agent cannot be deleted — deprecate only (enforced + explained by tooltip).

### 9.5 Tools & MCP — `/tools`

**Tab: Tool Catalog** — table: name, category, permission_ceiling (advisory enum badge), write_capable (red "WRITE — advisory-block" badge), connector, status, used-by. Detail drawer: description, input/output schema (JsonViewer), bound agents. Banner atop the catalog: "Advisory base scope: tool_permission ∈ {read, summarize, draft, recommend, validate}. Write-capable tools are catalogued for visibility but cannot be bound."
**Tab: MCP Connectors** — cards: name, transport, endpoint (mono), auth_mode, health dot, tools provided, last healthcheck. Actions: `[Run healthcheck]` (job; small chance of `degraded` from seeded RNG), `[Toggle offline]` (demo lever — flips Pre-Flight hard blocker #4 red and shows the cascade).

### 9.6 Knowledge & RAG — `/knowledge`

**Tab: Sources** — table: name, source_uri (mono), parser, sensitivity, source_approval, refresh_cadence, index_target, doc count, last refresh. Detail drawer = the full 5.12 group with ProvenanceChips + pipeline run history for that source + `[Trigger refresh]`.
**Tab: Pipelines** — run list; each run expands to the 7-stage horizontal tracker `Ingest → Parse → Chunk → Embed → Index → Tag & Govern → Refresh` with per-stage status/duration/item counts, animating live during jobs.
**Tab: Indexes** — cards per `vector://` index: size, sources feeding it, agents consuming it, embedding model. Includes `vector://alloydb-demo` labeled DEMO with purge-on-ready explanation.

### 9.7 Governance — `/governance`

**Tab: Approvals Queue** — pending items grouped by agent: step, required-by path, requested date, `[Approve] [Reject]` (persona-gated; disabled with tooltip "Switch to Governance Officer persona"). Decisions cascade: last approval flips agent lifecycle to `approved` and Registry shows it instantly.
**Tab: Matrix & Policies** — interactive GovernanceMatrix (click a cell → list of agents in it + path definition), path legend (Fast/Standard/Deep/Critical verbatim), policy asset list (`policies://…`), fast-path expiry table with `[Re-certify]`.
**Tab: Audit Log** — Section 8.5.

### 9.8 Evaluations — `/evaluations`

List of packs: agent, #cases by category, last score, last run. Detail `/evaluations/:packId`: category-grouped case table (test_id, input, expected_output, evaluation_method, pass_threshold, last result), `[Run all]` / per-case `[Run]`, score ring + category breakdown bars, run history line chart. `[Add custom case]` form. Failing safety cases render prominently red — safety is never buried.

### 9.9 Monitoring & FinOps — `/monitoring`

**Tab: Health** — per-agent grid: requests/day sparkline, p95 latency vs tier target, error rate, three-track status; degraded rows sort up. Platform row on top (aggregates).
**Tab: Usage & Cost** — 30-day charts from the telemetry generator: stacked daily tokens by agent, cost by cost_label (pie), cost per agent table (input/output tokens, $ estimate, trend arrow), monthly projection. `cost_awareness` fields from configs drive per-agent budget badges (over/under).

Telemetry generator (`kernel/telemetry.ts`): for each live agent, generate 30 days of `{requests, tokens_in, tokens_out, p95_ms, errors}` from the seeded PRNG shaped by tier (Advanced ≈ 3× tokens of Minimal) with weekly seasonality + one seeded incident spike (a visible story for demos: the Incident Coordinator has a bad day on day 22).

### 9.10 A2A Directory — `/a2a`

Grid of **agent cards** for agents with `a2a_enabled=true`: name, skills chips, discovery-only vs full-exchange badge, input/output schema expanders, endpoint (mono). Standardized agents show "Discovery only — findable but passive (message_task_format=null, artifact_exchange=false)"; Advanced agents show exchange config. Filter by skill. Card detail links to registry entry. Non-A2A agents don't appear — with an explainer of the tier split.

### 9.11 Playground — `/playground`

Left: agent picker (live agents; non-live offer Demo Mode per Section 6.5). Right: chat surface.

Response simulation (deterministic, `kernel/playground.ts` — see Section 11): responses are assembled from the agent's own config — grounded answers cite its `kb://` sources with fake snippets; tool calls render as collapsible "tool call" blocks (tool_id, permission, simulated result); Critical-path agents interpose a HITL approval interstitial before each tool call ("Runtime HITL gate — approve this action?" `[Approve] [Deny]`); asks that imply write actions get the refusal template ("I'm advisory-only. I can draft this for you, but I can't send/update/delete…"). A right-side **inspector panel** shows, for the last turn: retrieval trace (chunks + scores against `score_threshold`), sub-agent routing steps (Advanced), token count, and which config fields shaped the answer. The Playground is where "an agent is data" pays off — change `top_k` via registry change proposal and the inspector trace changes.

---

## 10. CROSS-MODULE CAUSALITY (WHAT MAKES IT FEEL REAL)

These seams are REQUIRED — they are the demo's magic moments:

1. Toggle a connector offline in `/tools` → Pre-Flight hard blocker #4 turns red → wizard `[Start Onboarding]` disables.
2. Approve the final pending item in `/governance` → agent flips to `approved` in `/agents` → `[Provision]` unlocks → provisioning animates the swimlanes → LIVE → agent appears in `/playground` picker and `/a2a` grid → telemetry starts accruing next reset.
3. Run a pipeline refresh in `/knowledge` → that agent's Content pill goes ⏳ then ✅ → Demo Mode banner auto-clears in Playground.
4. Deep-path agent's eval score < 90 → `[Promote to Production]` locked in both wizard Phase 6 and registry.
5. Every one of these writes audit events visible in `/governance` → Audit Log within seconds.

---

## 11. PLAYGROUND & EVAL RESPONSE MECHANICS (DETERMINISTIC)

### 11.1 Intent classification of the user's chat message

Rules in order: write-verb match (Section 7.4 lists) → `refusal`; question containing a seeded KB keyword → `grounded_answer`; tool-name/action mention → `tool_call`; else → `general_answer`.

### 11.2 Response assembly

`grounded_answer`: pick 2–3 seeded snippets from the agent's knowledge sources (each source in seed data carries 4–6 canned snippets with fake doc ids like `INC-2026-0142`), filter by simulated relevance score > `score_threshold`, compose an answer template citing `[source: kb://incident-db-prod-v3 · INC-2026-0142]` per `citation_rules`. `tool_call`: emit tool block with canned result from the tool's seed fixtures. Advanced agents prepend a routing trace: coordinator → chosen sub-agent(s). Latency: simulated to roughly match tier p95 targets.

### 11.3 Eval runner

Each case's result is deterministic: grounding/correctness cases pass if the agent's config actually satisfies them (e.g., grounding case passes iff `rag_enabled` and the cited source is attached and indexed); safety cases pass iff no write-capable tool is bound (always true) — BUT seed one Advanced agent with a deliberately mis-set `score_threshold=0.95` so two grounding cases fail (score 82) and the Deep-path promotion lock is demonstrable; fixing the threshold via config change proposal and re-running flips it to 94 and unlocks. Score = weighted pass % (safety cases ×2 weight).

---

## 12. SEED DATA SPECIFICATION (`/src/seed`)

Seed data is the demo's script. It must tell coherent stories, not be filler. IDs follow the Blueprint pattern `agt-<slug>-<yyyymmdd>-<4hex>`.

### 12.1 Agents (9)

| # | Name | Tier | Risk | Path | Lifecycle / tracks | Story it carries |
|---|---|---|---|---|---|---|
| 1 | HR Policy Bot | Minimal | Low | Fast | LIVE, all ✅ | Blueprint Appendix A Ex.1 verbatim; fast-path expiry in **6 days** (expiry story) |
| 2 | NOC Incident Summarizer | Standardized | Medium | Standard | LIVE, all ✅ | The POC's own example (sarah.chen / marcus.dev, incident_db); highest traffic |
| 3 | Incident Response Coordinator | Advanced | High | Deep | approved; Runtime ⏳ Content ⏳ | Appendix A Ex.2 verbatim: 4 sub-agents, slack_notifier + email_sender FLAGGED not bound; provisioning demo |
| 4 | Contract Clause Finder | Standardized | High | Deep | in_review; eval score **82** | The failing-eval story (Section 11.3, score_threshold=0.95) |
| 5 | Field Ops FAQ Bot | Minimal | Low | Fast | LIVE | faq_bot archetype; near-zero cost row |
| 6 | Churn Insight Assistant | Standardized | Medium | Standard | registered; 1 of 2 approvals pending | The approvals-queue story |
| 7 | Network Capacity Research Assistant | Standardized | Medium | Standard | LIVE; Content re-indexing ⏳ | Pipeline-refresh + Demo Mode story |
| 8 | Regulatory Filing Coordinator | Advanced | Critical | Critical | approved, LIVE | Runtime-HITL-per-action Playground story |
| 9 | Draft: Vendor SLA Watcher | — | — | — | wizard draft at Phase 3 | Resume-a-draft story |

Each seeded agent carries a full 56-field config with plausible provenance mix (user/system/default/inferred/generated) — write them by running the tier templates mentally, not by inventing new field names.

### 12.2 Assets

- **Prompts (8):** `prompts://noc-summarizer@v2` (+v1 history), `prompts://hr-safety-v2.1`, `prompts://citation-standard-v1` (kind: citation), safety pack, coordinator system prompt, 2 templates, 1 deprecated.
- **Tools (12):** read-only: incident_reader, confluence_reader, jira_reader, log_reader, health_checker, contract_reader, crm_reader, capacity_api_reader, filing_reader; write-capable (catalogued, never bindable): slack_notifier, email_sender, ticket_updater.
- **MCP connectors (5):** gcp-ticketing (sse, connected), confluence (http, connected), jira (http, **degraded**), crm-readonly (sse, connected), filings-gateway (http, connected).
- **Knowledge sources (6):** incident-db-prod-v3, hr-policies, contracts-repo, capacity-reports, churn-analytics, regulatory-filings — each with full 5.12 config, 4–6 canned snippets with fake doc IDs, and 1–3 historical pipeline runs (source #4 has one mid-flight run).
- **Eval packs:** one per non-draft agent (5–8 cases each), agent #4's pre-seeded with the two failing grounding cases.
- **Approvals:** agent #6's pending risk_officer item; history for the live agents.
- **Audit log:** ~40 back-dated events covering creations, approvals, provisions, config changes.

---

## 13. BUILD ORDER (MILESTONES FOR THE CODING AGENT)

Each milestone must compile, run (`npm run dev`), and be navigable before starting the next.

- **M1 — Shell & kernel skeleton.** Vite project, theme tokens, LeftNav/TopBar/routing with placeholder pages, Zustand store, seeded RNG, seed loaders, primitives (Button, Card, Table, Badge, Tabs, StatusPill, JsonViewer, EmptyState). *Done when: all 11 routes render with PageHeader + empty states; persona switcher and Reset demo work.*
- **M2 — Types & seed data.** Full canonical types (Section 5), all seed entities loading into the store. *Done when: JSON tab renders a seeded agent's full 56-field config with provenance.*
- **M3 — Registry + Home.** List/detail with all 7 tabs (Telemetry tab may stub), ThreeTrackSwimlanes, dashboard tiles/charts. 
- **M4 — Engine + Onboarding wizard.** Sections 7 + 9.3 complete, including engine trace, elicitation, review card, tier override re-evaluation. *Done when: the two Appendix-A worked examples reproduce their documented outcomes (HR bot → all signals 0, Minimal wins at base 20; Incident Coordinator → S1/S2/S3/S4/S5 all fire, Advanced wins, 4 sub-agents decomposed, slack_notifier + email_sender flagged not bound, risk_tier=high). Note: Appendix A's printed per-signal numbers mix weight columns and don't exactly re-derive from the Appendix F table — the F table weights and the formula are authoritative; match the OUTCOMES (winner tier, flags, sub-agents), not the printed intermediate sums.* 
- **M5 — Governance.** Approvals queue, matrix tab, audit log, fast-path expiry, persona gating; registration→approval→provision causality live.
- **M6 — Assets.** Prompts, Tools & MCP (incl. offline toggle → Pre-Flight cascade), Knowledge & RAG with animated pipeline runs.
- **M7 — Evaluations + jobs polish.** Eval runner, failing-eval story, promotion locks both places.
- **M8 — Playground + A2A.** Response simulation, inspector panel, Demo Mode, runtime HITL interstitial, A2A grid.
- **M9 — Monitoring & FinOps + hardening.** Telemetry generator + charts, export/import workspace, empty-state audit, keyboard nav for Cmd+K, README with demo script (the 5 causality moments of Section 10).

---

## 14. ACCEPTANCE CRITERIA (DEFINITION OF DONE)

**Fidelity to locked decisions**
1. All 56 schema fields appear with verbatim names; every leaf carries a provenance envelope; ProvenanceChip renders all five value_source codes.
2. Signal weights, scoring formula, base-20 minimal score, and all three override rules match Section 7.2 exactly; the engine trace shows raw scores.
3. `tool_permission` offers ONLY the five advisory values anywhere it appears; no flow can bind a write_capable tool (verify: attempt via tool picker, config change proposal, and seed-data tampering — the kernel's `bindTool` guard rejects all three and writes an audit event).
4. Governance matrix cells and path definitions match Section 8.1 verbatim; path derivation re-computes live when risk or tier changes.
5. Seven phases, three tracks, tier plain-language names, and the Pre-Flight checklist (7 hard 🔴 + 5 soft 🟡 items = 12 rows; keep the Blueprint's own heading text "11 prerequisites (Plan Section 8)" verbatim — the off-by-one is in the source document and the demo POC, and consistency with source wins) appear with exact wording.
6. Both Appendix-A worked examples reproduce end-to-end (M4 criterion).

**Application behavior**
7. Agent is shown LIVE if and only if all three tracks are ✅ — verified across dashboard, registry list, detail, playground picker.
8. All five causality seams of Section 10 work.
9. Jobs animate: synthesis, provisioning sub-steps, 7-stage pipeline, eval runs — with the job tray reflecting each.
10. Deterministic: two consecutive "Reset demo" runs produce identical telemetry charts and eval outcomes.
11. No localStorage/sessionStorage/IndexedDB anywhere (grep-verifiable); export/import round-trips the workspace.
12. Every route deep-links (hard refresh lands on the same view); browser back works through tabs and wizard phases.
13. TypeScript strict passes; `npm run build` clean; no console errors during the full demo script.

**Experience quality**
14. Databricks-family visual: dark nav + `+ New` accent button, grouped nav labels, list→detail rhythm, dense tables, skeleton loading.
15. Empty states everywhere data can be empty (fresh import, zero-agent workspace) with a call to action.
16. The README contains a 10-step demo script walking a new agent from Pre-Flight to LIVE to Playground, touching every module once.

---

## 15. NON-GOALS (v1 OF THIS CONSOLE)

No real backend, auth, or multi-user state; no real LLM/Vertex calls; no CLI companion (the Blueprint's standalone CLI/API is out of scope here — but `kernel/api.ts` mirrors its endpoint shapes so a future backend swap is mechanical); no schema version migration (56-field schema frozen, per Blueprint D11); no full A2A message exchange runtime (directory + card display only, exchange config shown as data); no mobile layout (min width 1200px).

---

## 16. TRACEABILITY

Section 1 ← Blueprint §2 · Section 5 ← Blueprint §8 + scratchpad §4 · Section 7 ← Blueprint §5 + Appendix F · Section 8 ← Blueprint §3.9, §7.2, Appendix B, D9/D10 · Section 9.3 ← Blueprint §4 + Appendix D · Worked examples ← Blueprint Appendix A · Component framework breadth (11 modules) ← Polestar SOW Platform Component Framework (11 components). Where this document and the Blueprint conflict, the Blueprint wins; report the conflict rather than improvising.

# END OF MASTER BUILD SPECIFICATION v1.0
