# Module Validation Guide

Purpose: for each module, know (1) what to click/check on the frontend, (2) what actually happens on the backend, (3) whether that backend behavior is **REAL** (persisted in Postgres) or **SIMULATED** (client-only, resets on reload). Validate module by module against this.

---

## 1. Platform Vision

Blueprint: one enterprise control plane for the full agent lifecycle — **Registered → Assessed → Designed/Onboarded → Governed → Evaluated → Deployed → Accessed → Monitored → Costed → Reviewed → Improved/retired.** Two entry journeys: **New Agent Creation** and **Existing Agent Onboarding**.

Current build covers journey 1 (New Agent Creation, via the Onboarding wizard) end to end. Journey 2 (importing an *existing* agent's artifacts to reconstruct it in-platform) is **not built** — there is no "import existing agent" flow anywhere in the app today. Flag this as a gap if the doc requires it.

Lifecycle stage → module map (for later validation passes):

| Lifecycle stage | Module |
|---|---|
| Registered / Assessed / Designed | Onboarding wizard (this doc, section 2) |
| Governed | Governance (Approvals & Gates, Admin → Governance Config) |
| Evaluated | Evaluations |
| Deployed / Accessed | Registry → Deployment tab, Admin → Access |
| Monitored / Costed | Monitoring & FinOps |
| Reviewed / Improved / retired | Registry (lifecycle actions: recertify, suspend, retire) |

---

## 2. New Agent Onboarding (the Onboarding wizard)

Route: `/onboarding`. 8 screens in order: **PreFlight → Intent → WorkPackage → Register → Configure → Governance → Evaluate → Deploy.**

**Bottom line first:** only **Register** and the per-step sync during **Deploy** touch the database. Every other screen (Intent, WorkPackage, Configure, Governance, Evaluate, PreFlight) computes locally in the browser and is lost on refresh unless a later real call has already saved it.

| # | Phase | What to do on frontend | What backend does | Status |
|---|---|---|---|---|
| 0 | **PreFlight** | Check the 12-item readiness checklist renders; confirm "Start Onboarding" is disabled until all 🔴 hard blockers are green. | Nothing — checklist is derived from local store state (connectors/sources arrays), no server call. | 🟡 SIMULATED |
| 1 | **Intent** | Fill agent name, objective, audience, data sources, tools, owners → click "Generate proposal." Try overriding the proposed tier. | Nothing — `runEngine()` in `src/kernel/engine/*` computes signals S1–S6, tier score, archetype, review card entirely in-browser. No network call. | 🟡 SIMULATED |
| 2 | **WorkPackage** | Add in-scope/out-of-scope tags. Tick Definition-of-Ready / Definition-of-Done boxes — confirm unticked DoR items block "Next." | Nothing — local patch on the draft object only. | 🟡 SIMULATED |
| 3 | **Register** | Answer up to 3 clarification questions (watch tier/risk re-score live) → click "Register agent." | **`POST /v1/agents/register`** → real agent id (`agt-...`) created in `agents` table; governance path resolved from the real `policy_rules` table; eval pack generated and inserted; approval rows inserted per path; audit event written; fast-path agents get a real DB-scheduled auto-approval job (~10s). | 🟢 **REAL** |
| 4 | **Configure** | Review model/RAG/tool config (fields shown depend on tier). Toggle A2A. Pick or "Generate with AI" the citation rules prompt. | Both the A2A toggle and citation_rules field now call **`POST /v1/agents/{id}/config-change`** (`propose_config_change`) — real DB write + audit event, same endpoint the standalone Configuration tab uses. | 🟢 **REAL** *(fixed)* |
| 5 | **Governance** | Pick data sensitivity / regulatory domain, or manually override risk tier. Watch the governance-path matrix and required-approvals count update. | Risk override now calls **`POST /v1/agents/{id}/risk-tier`** (new endpoint) — re-derives `governance_path` server-side from the real `policy_rules` table and persists both fields + audit event. The matrix/path-definition display also now reads real `policyRules`/`pathDefinitions` from the store instead of a hardcoded copy. | 🟢 **REAL** *(fixed)* |
| 6 | **Evaluate** | Click "Run evaluation." Watch case-level pass/fail and score. Click "Promote → Deploy" once score/approvals clear. | Already correct — `api.runEvaluation(pack.id)` calls the real `POST /v1/evaluations/{pack_id}/run` endpoint (module 5). *(Earlier note that this was simulated was wrong — verified against current code.)* | 🟢 REAL |
| 7 | **Deploy** | Click "Provision runtime & index content." Watch the 3-track swimlane animate to green → "AGENT IS LIVE." | Progress timing/animation is simulated, but **each completed step does a real `PATCH /v1/agents/{id}`** persisting tracks/config/demo_mode to the DB. | 🟢 REAL (persistence), 🟡 simulated (timing) |

### What this means for validation right now (updated 2026-08-06)
- **Register, Configure, Governance, Evaluate, and the Deploy sync step are all real** — each persists to Postgres immediately, not just at the end of the wizard.
- Only **Intent, WorkPackage, and PreFlight** remain client-simulated — by design: nothing there is a real entity yet (no agent exists until Register), so there's nothing to persist. Tier/signal scoring (S1–S6) runs in the browser (`kernel/engine/*`); the server trusts the client's confirmed tier/risk at Register time rather than recomputing it independently — a known trust-boundary gap, not fixed here (would require porting the whole scoring engine to Python).
- Fixed this session: Configure's A2A toggle + citation_rules field, and Governance's risk-tier override (was silently drifting from the real policy_rules table an admin can edit — now re-derives `governance_path` server-side on every change).

---

*Next module to validate: tell me which one and I'll add a section the same way.*
