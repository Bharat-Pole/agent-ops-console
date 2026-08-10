# Brightspeed Agent Ops & Governance Console

A Databricks-style, multi-module control plane for governing the full lifecycle of
AI agents — registry, onboarding, prompts, tools/MCP, knowledge & RAG, governance,
evaluation, monitoring/FinOps, A2A directory, and a playground — all sharing **one
canonical agent schema** and **one simulated platform kernel**.

Built to the _Agent Ops Console Master Build Specification v1.0_. Core thesis
(LOCKED): **an agent is data, not code.** Every screen is a different lens over the
same canonical config; an agent is **LIVE only when all three tracks — Registry,
Runtime, Content — are green.**

> ## ⚠️ This is a local proof of concept
>
> **Run it on localhost. Do not deploy it, and do not read the feature list above
> as a description of a production system.** Much of the console is a
> deterministic client-side simulation; a growing subset is genuinely
> server-persisted. The two are not distinguishable by looking at the UI, which
> is exactly why this note exists.
>
> **What is real:** the data model, the governance rules and the persistence
> behind agents, approvals, the audit log, eval packs, tools, MCP connectors, the
> connector backlog and the tool-call trail. Governance is enforced server-side
> and re-validated independently of anything the client sends. **The MCP client
> speaks the real protocol** (spec revision 2026-07-28), and every tool call runs
> through a policy gateway that enforces eleven checkpoints deny-by-default and
> performs the invocation itself.
>
> **What that buys, said precisely:** a tool-call row is *authoritative for every
> call that passes through the gateway* — not more than that. The table
> distinguishes three shapes so the claim cannot quietly widen: client-reported
> rows, gateway-enforced rows whose tool body was simulated, and rows from a real
> MCP round trip. Only the last carries a latency that measures a real system,
> and the UI labels all three.
>
> **What is simulated:** knowledge sources, prompts, onboarding drafts,
> jobs/telemetry, and the provisioning/pipeline/eval animations. The onboarding
> "synthesis engine" is rule-based, not a model call, despite looking like one.
>
> **Known limits, stated rather than hidden:**
> - **No authentication and wildcard CORS.** Localhost only.
> - **Identity: the enforcement is real, the principal is not.** The gateway
>   enforces a genuine per-connector allowlist against a console persona rather
>   than a federated IdP subject. Both halves matter.
> - **The counterparty is a local reference MCP server**, not a Brightspeed
>   system. Our half of the wire is real; the far side is `localhost`.
> - **The model layer is not the approved target stack** — the engagement
>   constrains it to Vertex AI. Anthropic/OpenAI here are a local stand-in.
> - **No browser-automated verification exists**; correctness is evidenced by
>   backend suites and typecheck, not click-throughs.
>
> Using sandbox and stub approaches at this stage is deliberate and contractually
> sanctioned, not a shortcut — but nothing here should be presented as
> production-ready.

## Stack

Vite · React 18 · TypeScript (strict) · react-router-dom v6 · Zustand · Tailwind
CSS · Recharts · lucide-react on the frontend, plus a FastAPI + asyncpg backend
backed by Postgres (`pgvector`) for persistence, real Anthropic chat, and
OpenAI-embeddings RAG retrieval. The original in-browser kernel (seeded PRNG,
rule/template engine) still drives all the deterministic synthesis/eval logic —
only storage and the Playground chat/RAG calls go through the real backend.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (runs Postgres/pgvector)
- [Node.js](https://nodejs.org/) 18+
- [Python](https://www.python.org/downloads/) 3.11+

## Quick start (Windows)

```powershell
.\start.ps1
```

This script is idempotent and safe to re-run: it copies `.env.example` → `.env`
if missing, starts the Postgres container via `docker compose`, waits for it to
be ready, creates/updates the backend's Python venv (`backend/.venv`), runs
`npm install`, and finally starts both dev servers. Use `.\start.ps1 -SkipInstall`
on later runs to skip the venv/npm install steps and just bring services up.

- Frontend: http://localhost:5173
- Backend API: http://localhost:8787

To use real Playground chat / RAG, set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in
`.env` (copied from `.env.example`) — the server boots and the rest of the app
works fine without them.

## Manual setup (any OS)

```bash
cp .env.example .env                 # fill in API keys later if you want real chat/RAG
docker compose up -d                 # starts Postgres (pgvector) on :5432

cd backend
python -m venv .venv
.venv/Scripts/activate                # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cd ..

npm install
npm run dev       # runs client (5173) + server (8787) concurrently
npm run build     # tsc -b (strict) + vite build
npm run test      # headless kernel/engine/playground/causality suites
```

Min viewport width is 1200px (no mobile layout — a stated non-goal).

## 10-step demo script

Walks a new agent from Pre-Flight to LIVE to Playground and touches every one of
the eleven nav modules (Prompt Repository, Knowledge & RAG, and A2A Directory are
folded into steps 4, 7, and 8).

1. **Home** — read the stat tiles, the tier/risk heatmap, and the 30-day cost trend.
   Switch persona (top-right) to **Governance Officer** and watch "Needs your
   attention" change.
2. **Tools & MCP → MCP Connectors** — click **Toggle offline** on the `jira`
   connector. (Causality #1: this turns a Pre-Flight hard blocker red.)
3. **Onboarding** — the Pre-Flight strip now shows a red hard blocker; **Start
   Onboarding** is disabled. Go back to Tools & MCP and bring `jira` online again.
4. **Onboarding → Start new onboarding → Pre-Flight → Start Onboarding.** In
   **Phase 1**, paste: _"Coordinate a team of agents to triage major incidents:
   analyze logs from the incident database and ticketing system, assess impact,
   draft comms, and route notifications to on-call and Slack."_ Add data sources
   `incident_db, ticketing` and tools `incident_reader, log_reader, slack_notifier,
   email_sender`. Click **Generate proposal** → the engine proposes **Advanced**,
   decomposes **4 sub-agents**, and **flags slack_notifier + email_sender
   (advisory-only, never bound)**. Expand the **Engine trace** to see all 7 stages'
   raw scores. Confirm. (The proposal references `citation-standard-v1` — open it
   in **Prompt Repository** to see the governed prompt and its used-by list.)
5. **Phases 2–3** — check the Definition-of-Ready items, answer the ≤3 elicitation
   questions, then **Register agent** (creates approval items + an eval pack).
6. **Governance → Approvals Queue** (as Governance Officer) — approve every pending
   item for your new agent. (Causality #2: the agent flips to **approved**.)
7. **Registry → your agent → Deployment → Provision** — watch the runtime and
   content swimlanes animate stage-by-stage until the **AGENT IS LIVE** banner. The
   agent now appears in the **A2A Directory** (discovery-only at Standardized, full
   exchange at Advanced).
8. **Playground** — pick a live agent. Ask _"Summarize the latest incident"_ (a
   grounded answer citing `kb://… · INC-…` with a retrieval trace), then _"Delete
   all records"_ (the advisory-only refusal). Open the **Regulatory Filing
   Coordinator** (Critical path), send _"check filing_reader"_, and **Deny** the
   **runtime HITL gate** — the denial is now enforced server-side at the gateway's
   `hitl` checkpoint, not by the UI declining to send. Then, in **Knowledge & RAG
   → Sources**, click **Trigger refresh** on _Capacity Reports_ — its Content pill
   animates ⏳→✓ through the 7-stage pipeline and any Playground Demo-Mode banner
   auto-clears (causality #3).

   **8a. Tools & MCP → Tool Calls** — the call you just denied is a row, badged
   **denied** with the checkpoint that refused it. Filter **Evidence →
   client-reported** vs **gateway-enforced** to see the distinction the platform
   refuses to blur: a reported result is a claim, an observed one was measured
   here. (Causality #5: every tool call routes through the policy gateway.)
9. **Evaluations → Contract Clause Finder** — it scores **82** (two grounding cases
   fail because `score_threshold` is mis-set to 0.95). Click **Fix score_threshold →
   0.75 & re-run** → it flips to **94** and the Deep-path promotion lock clears.
   (Causality #4.)
10. **Monitoring & FinOps** — Health tab (p95 vs tier target, degraded rows sort
    up) and Usage & Cost (stacked tokens, cost-by-label pie, per-agent budget
    badges). Finally, the top-bar menu → **Export workspace JSON**, then **Reset
    demo** and **Import** it back. (Causality #5: every action above appears in
    **Governance → Audit Log**.)

## The five cross-module causality seams (Section 10)

1. Connector offline in **Tools** → Pre-Flight hard blocker red → wizard **Start**
   disabled.
2. Final approval in **Governance** → agent **approved** → **Provision** unlocks →
   swimlanes animate → **LIVE** → appears in **Playground** and **A2A**.
3. Pipeline refresh in **Knowledge** → Content pill ⏳ → ✓ → Playground **Demo
   Mode** auto-clears.
4. Deep-path eval < 90 → **Promote to Production** locked in the wizard **and** the
   registry.
5. Every mutation writes an **audit event** visible in Governance → Audit Log.

## Determinism

All randomness (latencies, telemetry curves, eval jitter) flows from a `mulberry32`
PRNG seeded with a fixed constant; date math uses a fixed `DEMO_TODAY`. Two
consecutive **Reset demo** runs produce identical telemetry charts and eval
outcomes. The synthesis engine, playground, and eval runner are pure rule/template
logic.

## Tests

`npm run test` runs four headless suites (via `tsx`):

- **smoke** — seed invariants (entity counts, every schema leaf carries a provenance
  envelope, all five value_source codes render, governance-path derivation, no write
  tool bound, reset determinism).
- **engine** — both Appendix-A worked examples reproduce (HR → Minimal/all-signals-0;
  Incident → Advanced/4 sub-agents/flagged tools/risk=high), plus the capability
  floor, override rules, and tier-override re-evaluation.
- **playground** — intent classification (refusal / grounded+citations / tool_call /
  general) and Critical-path runtime HITL.
- **causality** — approval cascade, fast-path re-certify, suspend, advisory bind
  guard, offline-toggle, the failing-eval fix (82→94), provision→LIVE, and the
  export/import round-trip.

## Project layout

```text
src/
  types/         canonical 13-group schema + provenance envelope + entities
  kernel/        store (Zustand) · api/services façade · jobs · rng · telemetry
    engine/      7-stage synthesis engine (nlu, signals, templates, writeDetect, …)
  seed/          Section 12 seed data (8 agents + 1 draft, assets, evals, audit)
  components/    primitives · domain (ThreeTrackSwimlanes, ReviewCard, …) · shell
  modules/       one folder per nav module (home, registry, onboarding, …)
```

## Non-goals (v1)

No real backend/auth/multi-user; no real LLM/Vertex calls; no CLI companion (the
`kernel/api.ts` names mirror the REST endpoints for a future backend swap); no
schema-version migration; no full A2A exchange runtime (directory + card display
only); no mobile layout.
