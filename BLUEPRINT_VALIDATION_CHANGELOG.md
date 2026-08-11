# Blueprint Validation Changelog — Agent Registry, Prompt Repository, Knowledge Base, RAG Pipeline Studio

## Purpose

This document covers one specific slice of work on top of the real FastAPI+Postgres backend: validating four Blueprint modules capability-by-capability against the **actual running code** (not the UI's claims), then closing every real gap found. It's written for someone reviewing this branch or merging these changes into a different fork of the repo — it tells you *what changed, why, what's in the database now, and how to verify it*, without you having to re-derive it from the diff.

Method used throughout: read the real backend code for a module, check each Blueprint capability against it, label it **REAL** (persisted, enforced server-side), **PARTIAL** (real but incomplete — e.g. no edit UI, no persistence, wrong granularity), or **MISSING** (no backing code at all). Only PARTIAL/MISSING items got fixed; nothing here is a rewrite of already-REAL functionality.

No new npm or pip dependencies were introduced anywhere in this slice. All schema changes are idempotent (`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) and run automatically from `backend/app/db/migrate.py` on every backend boot — there is no manual migration step. Backfills for pre-existing rows (see each module below) also run automatically on boot, once, and are idempotent.

---

## 1. Agent Registry

**Gaps found:** the registry list was missing several fields the Blueprint calls for, and "current environment" was being read from a stale config field that real promote/rollback calls never update.

**Fixed:**
- `backend/app/domains/deployment/deployment_repo.py` — added `get_latest_environments()`, one bulk query (`SELECT DISTINCT ON (agent_id) ...`) returning the real current environment per agent from `deployment_records`, instead of trusting `config.deployment.environment.value` (which is only set once at registration).
- `backend/app/domains/deployment/service.py` — added `get_all_environments()`, joining that with every agent (falls back to the config field only for an agent with zero deployment records, which shouldn't happen given the existing backfill).
- `backend/app/domains/bootstrap/routes.py` — added `deployment.get_all_environments()` to the bootstrap gather, returned as `agentEnvironments`.
- `src/kernel/store.ts` — added `agentEnvironments: Record<string, Environment>`, hydrated from bootstrap.
- `src/modules/registry/RegistryPage.tsx` — rewritten with real Environment, Approvals, Eval score, combined Cost/Tokens, and Recent Activity columns, plus Domain / Cost Center / Owner filters, all computed from real store data (no fabricated numbers).

**Explicitly not fixed (flagged, not silently worked around):**
- No "Team" filter — there's no real backing field for it anywhere in the agent schema (`use_case_category` and `observability.cost_label` are real and now used for Domain/Cost Center; "Team" would need a genuine new `G_Identity` field plus a backfill, a schema decision left to the team).
- "Onboard existing agent" (Blueprint journey 2) remains entirely unbuilt — out of scope per explicit instruction this session.

### Lifecycle & governance correctness (found and fixed during the same validation pass)

- `backend/app/domains/chat/routes.py` — chat now checks `lifecycle_status` server-side and returns a real refusal (`kind: "refusal"`) for a `suspended` or `retired` agent, instead of trusting the client to hide the chat UI.
- `backend/app/domains/evaluations/service.py` / `routes.py` — `run_evaluation` raises on a suspended/retired agent, mapped to `409` (was previously unguarded server-side).
- `backend/app/domains/agents/lifecycle_service.py` — `set_lifecycle` rejects any change on an already-`retired` agent (retire is a one-way door, enforced server-side, not just hidden in the UI); added `update_risk_tier()`, which **re-derives `governance_path` from the real `policy_rules` table** on every risk-tier change instead of leaving it stale.
- `backend/app/domains/agents/routes.py` — new `POST /v1/agents/{agent_id}/risk-tier`.
- `src/modules/registry/AgentDetailPage.tsx` — badge tone and action buttons now key off the real `lifecycle` field; a suspended agent gets a "Reactivate" action, a retired one loses all lifecycle actions entirely (matches the one-way-door enforcement above).

**How to verify:** suspend or retire an agent from the Registry, then try to chat with it or run its eval pack — both should refuse with a real message, not a client-side-only disabled button. Check the Environment column against `deployment_records` directly; it should never just mirror the original registration-time config.

---

## 2. Golden Prompt Repository

**Gaps found:** no way to see what a prompt's body actually was at a past version (so compare/rollback were structurally impossible); only 4 of the Blueprint's ~10 prompt kinds existed; no domain/use-case/risk-tier/agent-type tagging; no bundled "approved prompt pack" output; delete existed in the UI but did nothing real and had no persona gate.

**Fixed:**
- **Real version snapshots + compare + rollback.** `backend/app/domains/prompts/service.py` — every history entry now carries a `body` snapshot frozen at the moment a version stops being live (`_freeze_last_snapshot`, called from `new_version`, `update_fields`, and `rollback_to`). New `compare_versions()` and `rollback_to()`; rollback creates a **new** version with the old body rather than destructively overwriting, with a real audit event. Pre-existing rows without a snapshot correctly 404 as "predates version snapshotting" rather than fabricating history — `backend/app/db/seed.py` has a one-time backfill that snapshots each row's current *known-real* body onto its last history entry (never invents older text).
  - New routes: `GET /v1/prompts/{id}/compare?a=&b=`, `POST /v1/prompts/{id}/rollback`.
  - New frontend: `src/modules/prompts/CompareVersionsDialog.tsx` (line-diff, `src/modules/prompts/diff.ts` — small self-contained LCS diff, no dependency) and rollback buttons per history entry in `PromptDetailPage.tsx`.
- **7 new prompt kinds.** `src/types/assets.ts` — `PromptKind` extended with `user_template | task | persona | tool_use | refusal | escalation | stop_condition` (existing: `system | citation | template | safety`). Guidance text for AI-generation added to `KIND_GUIDANCE` in `backend/app/domains/prompts/service.py`. Both `PromptsPage.tsx` and `PromptDetailPage.tsx` dropdowns/filters updated.
- **Tagging fields.** New real DB columns `domain, use_case, risk_tier, agent_type` on `prompts` (nullable, `backend/app/db/migrate.py`), threaded through `prompts_repo.py` / `service.py`, editable in `PromptDetailPage.tsx`, filterable in `PromptsPage.tsx`. Existing prompts get curated (not fabricated) tags backfilled from `backend/app/seed_data/seed_prompts.json` only when all four fields are still null — never overwrites a real edit.
- **Approved prompt pack export.** `GET /v1/prompts/approved-pack` (optional `domain`/`agent_type` filters) bundles every real `status='approved'` prompt into a downloadable JSON; "Export approved pack" button on `PromptsPage.tsx`.
- **Real delete, Governance-Officer gated.** `prompts_repo.delete_by_id`, `service.delete_prompt` (refuses server-side if `used_by` is non-empty — "deprecate instead of deleting" is enforced, not just a UI hint), `DELETE /v1/prompts/{id}` route with a real audit event. Delete button added to both the list (`PromptsPage.tsx`) and detail page (`PromptDetailPage.tsx`), disabled with a tooltip for any persona other than Governance Officer.
- **Citation format (see RAG Pipeline Studio §4 below — same underlying `citation_format` column, added to prompts here).**

**Approved-pack bundling was flagged as a decision point, not unilaterally built as a stateful entity** — it's implemented as a real filtered export of current data, not a new persisted "pack" object, since the Blueprint's wording didn't clearly require the latter.

**How to verify:** on any prompt, click "New version" twice with an edit in between, then use Compare on the version history list — you should see a real line diff. Roll back to the first version and confirm a new version number is created with the old text, not an overwrite. Try deleting a prompt that's `used_by` an agent — it should refuse with a real 400.

---

## 3. Knowledge Base Layer

**Gaps found:** uploads ingested immediately regardless of sensitivity (no approval gate); every document a connector pulled in (e.g. every Confluence page in a space) collapsed into one `doc_id`, making per-document tagging impossible; the Blueprint's prose-only source categories (runbooks, policy docs, etc.) had no real field; no KB-wide usage-map view; and there was dead, fully-unused simulated code left over from before the real backend existed.

**Fixed:**
- **Upload-time approval gate.** New `approval_status` column on `knowledge_sources` (`approved | pending | rejected`). A confidential/restricted upload is held at `pending` and **never reaches the ingestion pipeline** until a Governance Officer approves it — `backend/app/domains/knowledge/routes.py`'s `_start_or_gate_pipeline()` is now the single choke point every creation endpoint (upload, URL, database, text, and all 5 external connectors) funnels through. New `POST /sources/{id}/approve-upload` / `reject-upload`, each with a real audit event. UI: approval banner + Approve/Reject buttons in the source drawer (`KnowledgePage.tsx`), gated to Governance Officer.
- **Real per-document metadata (the core structural fix).** Root cause: `ingestion/pipeline.py` set `doc_id = source["uri"]` for every chunk regardless of how many discrete items (pages/issues/files/records) a connector actually fetched. New `backend/app/domains/knowledge/ingestion/document_splitter.py` splits the fetched text back into its real per-item documents using each connector's own existing text markers (Confluence's `=== CONFLUENCE PAGE: title ===`, GitHub's `=== FILE: path ===`, Jira's `--- JIRA ISSUE KEY | ... ---`, ServiceNow's `--- SERVICENOW ... RECORD #n ---`) — no fabricated boundaries, no NLP, just parsing markers those fetchers already emit. Single-item sources (file/url/text/database/bigquery) always resolve to exactly one document.
  - New table `knowledge_documents` (id = `{source_id}::{doc_ref}`, so it doubles as the chunk `doc_id`): `domain, owner, sensitivity, valid_until, lifecycle, last_queried_at`, defaulted from the parent source at ingestion time but independently editable and never overwritten by re-index.
  - New repo `backend/app/domains/knowledge/knowledge_documents_repo.py`.
  - `knowledge_chunks_repo.search_by_source_ids()` now excludes chunks belonging to a **retired document** (not just a retired source) — retiring one page out of a multi-page source really does stop it being retrieved, verified live.
  - New routes: `GET /sources/{id}/documents`, `PATCH /documents/{id}/metadata`, `POST /documents/{id}/retire` / `reactivate`.
  - New UI: collapsible "Documents" section in the source drawer (`KnowledgePage.tsx`), per-document tags/freshness/usage badges and a retire/reactivate action.
- **Content category.** New `category` column on `knowledge_sources` (`runbook | policy_document | mdr_golden_data | internal_business_rule | logs_evidence | other`) — this is a real tag layered on top of whatever connector actually fetched the bytes, not a fake new connector type (there's no real distinct protocol for "runbook" vs "policy document"). Dropdown in `AddSourceModal.tsx`, filter in `KnowledgePage.tsx`.
- **KB-wide usage map.** `GET /v1/knowledge/usage-map` aggregates every real agent↔source binding plus every currently-unused source in one call. "Usage Map" button/modal on `KnowledgePage.tsx`.
- **Dead code removed.** `addKnowledgeSource` and `triggerPipeline` in `src/kernel/services.ts` (and their `api.ts` exports) were fully client-simulated leftovers from before the real `/v1/knowledge/*` backend existed, with zero real callers anywhere in the current UI — deleted, not deprecated.

**How to verify:** upload a `confidential` text source — it should sit at `status: pending` / `approval_status: pending` with no pipeline run until approved. Connect a Confluence space with multiple pages (or inspect `GET /sources/{id}/documents` on any multi-item source) and confirm more than one row comes back, each independently taggable and retirable.

---

## 4. RAG Pipeline Studio

**Gaps found (all were "PARTIAL" — real backend field/logic existed but was either not enforced, not configurable, not tracked, or not honored end-to-end):**

- **Reranking had no real per-agent toggle.** It ran unconditionally in `execute_tool`. Added `rerank_enabled: Prov<boolean>` as a genuine `G_Data` field (`src/types/agent.ts`, `src/types/schema-meta.ts`, `src/seed/config-factory.ts`) — it's editable through the **existing generic** "Propose change" mechanism in `ConfigurationTab.tsx` (this also confirmed, on closer inspection, that `top_k` / `score_threshold` / `chunk_size` / `chunk_overlap` were already real and already editable there — an earlier read of this repo had missed that generic, schema-driven component). `backend/app/domains/chat/claude_service.py` and `groq_service.py` now read the real value and pass it to `tool_execution.execute_tool`. `backend/app/db/seed.py` backfills every pre-existing agent's `rerank_enabled` to `true`, matching the behavior they already had, so nothing's retrieval quality silently changes.
- **Metadata filters didn't reach the agent at runtime.** They existed only in the manual Retrieval Test panel's source picker. The `search_knowledge` tool schema the LLM is given now accepts an optional `domain` parameter; `knowledge_chunks_repo.search_by_source_ids()` accepts `document_domain` and applies a real SQL filter joined against `knowledge_documents.domain`. Verified directly: a query scoped to the wrong domain returns zero results, the right domain returns the real match.
- **RAG cost/latency wasn't tracked anywhere durable.** `tool_execution.execute_tool` now calls `monitoring.record_event(agent_id, "retrieval", ...)` on every real search — same `request_telemetry` table and cost-aggregation pipeline chat/eval already use (embedding cost is priced correctly per-provider because `text-embedding-3-small` / `local_bge_small` were already real catalog entries in the Model Repository). No frontend change was needed — the existing Monitoring/FinOps aggregation queries have no `source` filter, so retrieval events flow into the same per-agent daily series automatically.
- **Citation format ignored whatever the citation_rules prompt actually said.** The system-emitted citation string was hardcoded regardless of the bound citation prompt's content. Added a real, optional `citation_format` column on `prompts` (template string, placeholders `{source_name} {source_id} {doc_id} {doc_title}`) — set it on a `kind='citation'` prompt in `PromptDetailPage.tsx` and it is genuinely rendered per-citation (`tool_execution.render_citation`, looked up server-side via `get_citation_format()` from the agent's own bound prompt ref — the backend never trusts client-resolved text for this). Malformed templates fail safe to the platform default rather than breaking every citation. Verified live end-to-end: set a custom format, ran a real chat turn, got citations back in exactly that format.
- **Retrieval test results were purely ephemeral.** New `retrieval_test_runs` table — every real `/retrieve` call now persists a summary (query, sources, result/pass counts, latency, cost). New `GET /v1/knowledge/retrieval-test-runs`; "Recent tests" history list added to `RetrievalTestPanel.tsx`.

**Explicitly not fixed, and not realistically fixable:** "Configure vector store" isn't a real choice anywhere — pgvector is the only implementation. There's nothing to make configurable without standing up a second real vector database, which is out of scope.

**How to verify:** set a `citation_format` on a citation-kind prompt bound to a RAG-enabled agent, send it a real chat message, and check the `citations` array in the response reflects your template. Check `request_telemetry` for rows with `source = 'retrieval'` after any real chat turn that uses `search_knowledge`.

---

## Merge notes

- **Database:** nothing to run by hand. `backend/app/db/migrate.py` executes on every boot and is fully idempotent; new tables are `knowledge_documents`, `retrieval_test_runs`; new columns are `knowledge_sources.approval_status/category`, `prompts.domain/use_case/risk_tier/agent_type/citation_format`. Backfills (prompt body snapshots + curated tags, agent `rerank_enabled`) also run automatically on the first boot after merge and are safe to run repeatedly.
- **Dependencies:** none added (frontend or backend).
- **Breaking changes:** none to existing behavior — every new field defaults to a value that reproduces what the system already did before this change (e.g. `rerank_enabled` backfills to `true`, `approval_status` defaults to `approved` for anything not confidential/restricted, `citation_format` defaults to null which uses the pre-existing hardcoded bracket format).
- **Config/env:** no new environment variables.
- **Testing performed:** `tsc --noEmit` clean after every change; all new/modified Python files parsed with `ast.parse`; every capability above was exercised against the live running backend with real `curl` calls (not just read from code) before being called done — see the "How to verify" line under each module to repeat those checks yourself.
