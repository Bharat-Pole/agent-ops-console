# Prompts Repository — Architecture & Build Plan

> **Status: creation + approval implemented (2026-07-30).** One deviation from the original plan below: §4 originally proposed reusing the agents-coupled `POST /v1/approvals/{id}/decide` endpoint. On inspection, the `approvals` table has `agent_id TEXT NOT NULL REFERENCES agents(id)` and `decide_approval()` unconditionally calls `finalize_registry(item["agent_id"])` — it's structurally an agent-lifecycle mechanism, not a generic one. Generalizing it would have meant touching agent registration logic, a much bigger change than asked for. Instead, prompts got their own `POST /v1/prompts/{id}/decide` endpoint that writes to the **same shared `audit_log` table** with `entity_type='prompt'` — so the real audit trail goal is met without risking the agent approval flow. Revisit generalizing the `approvals` table if/when the governance module needs prompt approvals to appear in the Approvals Queue UI itself.

Scope of this doc: **creation + approval** of prompts only. Governance gating (e.g. blocking agent promotion on unapproved prompts, multi-step approval chains, tier-based restrictions) is explicitly **out of scope** — governance is a separate module and will layer on top later.

---

## 1. Current State (before this build)

- Prompts exist only as a **frontend-only, simulated module**:
  - Type: `PromptAsset` — [`src/types/assets.ts`](src/types/assets.ts#L16-L26)
  - UI: [`PromptsPage.tsx`](src/modules/prompts/PromptsPage.tsx), [`PromptDetailPage.tsx`](src/modules/prompts/PromptDetailPage.tsx)
  - Agent linkage: `G_Prompt` group — [`src/types/agent.ts`](src/types/agent.ts#L92-L103) (`system_prompt_ref`, `user_prompt_template`, `task_prompt`, `safety_instructions`, `citation_rules`, `tool_use_instructions`, `per_sub_agent_prompts`)
- **No backend exists for prompts** — no table, no repo, no route. (Tools and Knowledge already have real Postgres persistence; Prompts don't.)
- `[Approve]` today just flips a local field + fires a local `audit()` call — never touches the real approvals pipeline agents use ([`backend/app/routes/approvals.py`](backend/app/routes/approvals.py)).
- Agent Builder wizard (7 phases) has no prompt-generation or prompt-selection UI in Phase 1 or Phase 4 yet.

---

## 2. Data Model

### 2.1 Frontend type changes (`src/types/assets.ts`)

Extend `PromptAsset` with two new fields:

```ts
export type PromptKind = 'system' | 'safety' | 'citation' | 'template';
export type PromptCategory = 'agent' | 'tool' | 'mcp' | 'rag'; // NEW — which module consumes it
export type PromptSource = 'manual' | 'llm_generated';          // NEW — how it was created
export type PromptStatus = 'draft' | 'approved' | 'deprecated';

export interface PromptAsset {
  id: string;
  version: string;
  name: string;
  kind: PromptKind;
  category: PromptCategory;      // NEW
  source: PromptSource;          // NEW
  generated_from?: string;       // NEW — agent_id or job_id that triggered generation, if source = llm_generated
  body: string;
  status: PromptStatus;
  owner: string;
  used_by: string[];             // agent_id[]
  history: PromptHistoryEntry[];
}
```

- `kind` = what the prompt *contains* (system/safety/citation/template).
- `category` = which module *owns/consumes* it (agent/tool/mcp/rag). Keeps one repository instead of separate prompt systems per module (see §6).

### 2.2 Backend table (implemented — `backend/app/db/migrate.py`)

One table, history kept as JSONB (matches the codebase's existing convention of `tracks_json`/`config_json` on `agents` — no separate history table):

```sql
CREATE TABLE prompts (
  id             TEXT PRIMARY KEY,
  version        TEXT NOT NULL,
  name           TEXT NOT NULL,
  kind           TEXT NOT NULL,
  category       TEXT NOT NULL DEFAULT 'agent',
  source         TEXT NOT NULL DEFAULT 'manual',
  generated_from TEXT,
  body           TEXT NOT NULL DEFAULT '',
  status         TEXT NOT NULL DEFAULT 'draft',
  owner          TEXT NOT NULL,
  used_by_json   JSONB NOT NULL DEFAULT '[]',
  history_json   JSONB NOT NULL DEFAULT '[]'
);
```

Repo: `backend/app/repositories/prompts_repo.py` — `insert`, `get_all`, `get_by_id`, `update` (full-row merge patch), same shape as `tools_repo.py`/`agents_repo.py`.

---

## 3. Creation Flow

Three ways a prompt row gets created, plus one way to reuse an existing one without creating anything.

| # | Trigger | Where (FE) | What happens (BE) | Resulting status |
|---|---|---|---|---|
| 1 | **Manual** | `[New Prompt]` on `/prompts` | `POST /v1/prompts` → insert row | `draft` |
| 2 | **AI-generated, rough draft** | `[Generate proposal]` in Agent Builder **Phase 1 (Capture Intent)** — objective + audience + data sources + tools is enough for a first pass | Same engine job that proposes the tier also calls prompt-generation → `POST /v1/prompts/generate` → insert row, `source: llm_generated`, `generated_from: <agent_id>` | `draft` |
| 3 | **AI-generated, per-field** | `[Generate with AI]` button next to each prompt slot in **Phase 4 (Configure Workflow)**, once tier/tools/RAG are locked | `POST /v1/prompts/generate` → insert row | `draft` |
| 4 | **Select existing** | Dropdown next to each prompt slot in Phase 4 — **no status filter**, drafts are selectable | `GET /v1/prompts?kind=...&category=agent` → no new row, just sets `agent.config.prompt.<field> = prompts://id@version` | unchanged |

Phase 4 field UI (per prompt slot: `system_prompt_ref`, `safety_instructions`, `citation_rules`, `tool_use_instructions`, per-sub-agent prompts) — three radio options:

```
○ Select existing prompt   → dropdown, searches Prompt Repo
○ Generate with AI         → drafts a new prompt, sets ref
○ Write new (blank)        → opens Prompt Repo "New Prompt", comes back with ref
```

---

## 4. Approval Flow (implemented)

Prompts get their own decide endpoint rather than the agents-coupled `approvals` table (see status note at top).

| Step | FE | BE |
|---|---|---|
| Submit for approval | `[Approve]` on `/prompts/:id` (Governance Officer persona only, client-side gated) | `POST /v1/prompts/{id}/decide` → [`backend/app/services/prompts.py::decide()`](backend/app/services/prompts.py) |
| Decision | — | Updates `prompts.status` → writes `audit_repo.insert(entity_type='prompt', entity_id, action='approve'|'reject', actor_persona, detail)` — same `audit_log` table agents use |
| Deprecate | `[Deprecate]` on `/prompts/:id` (only shown once approved) | `POST /v1/prompts/{id}/deprecate` → same pattern, `action='deprecate'` |

No draft/approved gating on prompt *selection* (per your decision) — a draft prompt can be bound to an agent freely right now. Gating, and surfacing prompt approvals in the Governance → Approvals Queue UI specifically, is deferred to the governance module.

---

## 5. API Contracts (implemented)

```
GET    /v1/prompts                      → list all
POST   /v1/prompts                      → manual create (status: draft)
POST   /v1/prompts/generate             → LLM-generate body, insert new row (status: draft, source: llm_generated)
        body: { kind, category, owner?, context: { objective, audience?, tools?, data_sources?, agent_id? } }
POST   /v1/prompts/generate-body        → preview-only draft text, no row inserted (used by the in-place "Generate with AI" button while editing an existing draft)
PATCH  /v1/prompts/{id}                 → edit name/kind/category/body/owner (draft only, enforced client-side)
POST   /v1/prompts/{id}/new-version     → bump version, status → draft, append history
POST   /v1/prompts/{id}/decide          → { decision: 'approved'|'rejected', actorPersona } → status + audit event
POST   /v1/prompts/{id}/deprecate       → { actorPersona } → status: deprecated + audit event
```

Real Claude generation via `claude_service.generate_text()` (new small helper alongside the existing `chat_with_agent()`), with a graceful fallback placeholder body when `ANTHROPIC_API_KEY` isn't configured — mirrors the existing Playground chat fallback pattern.

---

## 6. Frontend Changes

### `/prompts` (list page)
- Add **Type/Category** column + filter (agent/tool/mcp/rag) alongside existing Kind/Status filters.

### `/prompts/:id` (detail page)
- Add **Category** field, **Source** badge ("Manual" vs "AI-generated" with `generated_from` link if applicable).
- `[Approve]` now calls the real backend endpoint instead of a local state flip; optionally add a comment box for the audit trail.
- Keep `[New version]`, deprecate/no-delete-if-used_by behavior as-is.

### `/prompts/new`
- Add **Category** dropdown (required).
- Add **Source** = `manual` (fixed, since this is the hand-authored path).

### Agent Builder — Phase 1 (Capture Intent)
- `[Generate proposal]` job, in addition to the tier proposal, also drafts a rough `task_prompt` and saves it via `POST /v1/prompts/generate`.

### Agent Builder — Phase 4 (Configure Workflow)
- New UI per prompt field: the 3-option block from §3 (Select existing / Generate with AI / Write new).

---

## 7. Build Order

1. **Backend**: `prompts` + `prompt_history` tables (migration) → `prompts_repo.py` → `routes/prompts.py` (CRUD + generate).
2. **Backend**: extend `services/approvals.py` / `approvals_repo` to accept `entity_type='prompt'`.
3. **Frontend**: wire `/prompts`, `/prompts/:id`, `/prompts/new` to real API instead of Zustand-only store; add `category`/`source` fields to UI.
4. **Frontend**: wire `[Approve]` to `POST /v1/approvals/{id}/decide`; confirm it surfaces in Governance → Approvals Queue.
5. **Frontend**: Agent Builder Phase 1 — hook prompt draft generation into `[Generate proposal]`.
6. **Frontend**: Agent Builder Phase 4 — build the 3-option prompt field UI (select/generate/write) for each `G_Prompt` slot.

---

## 8. Explicitly Out of Scope (for now)

- Blocking `[Promote to Production]` on unapproved prompts.
- Multi-step approval chains (e.g. legal + security sign-off) for prompts.
- Tier/path-based restrictions on which prompt status can be selected.
- Tool description / MCP / RAG prompt UI beyond the `category` tag (the fields themselves in Tools & MCP / Knowledge & RAG pages are a follow-up, not part of this build).
