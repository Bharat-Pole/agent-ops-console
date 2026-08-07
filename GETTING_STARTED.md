# Getting Started — build a web-search agent

You will build **Web Answers**: an agent that answers questions by searching the
web and citing what it found. Every step below was executed against a live
backend, live Wikipedia, and a live Gemini call before this guide was written.

Final result, verbatim from the run:

```
Q: Which countries are hosting the 2026 FIFA World Cup?
A: The 2026 FIFA World Cup is jointly hosted by Canada, Mexico, and the
   United States (source: 2026 FIFA World Cup).

  1. sys     prompt          ok       0ms
  2. search  tool_call       ok     905ms
  3. answer  llm             ok    2937ms   gemini-flash-latest  1026/33 tokens  $0.000390
  4. guard   guardrail       ok      14ms
  5. out     output_format   ok       0ms
```

---

## 0. Start the platform

```bash
cd agent-ops-console/backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
# python -m venv .venv && .venv/bin/pip install -r requirements.txt     # macOS/Linux

export PLATFORM_GEMINI_API_KEY=your-key        # get one at aistudio.google.com
export PLATFORM_SESSION_SECRET=change-me

.venv/Scripts/python -m alembic upgrade head   # create schema
.venv/Scripts/python -m app.seed               # seed users + model catalog
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Frontend, in a second terminal:

```bash
cd agent-ops-console && npm install && npm run dev     # http://localhost:5173
```

Sign in with any seeded account, password `changeme!`:

| Account | Role | What it can do |
|---|---|---|
| `creator@platform.local` | agent_creator | create agents, capture intent, run tests |
| `engineer@platform.local` | ai_engineer | tools, prompts, knowledge, workflows |
| `governance@platform.local` | governance_reviewer | approve assets and workflows |
| `owner@platform.local` | agent_owner | activate workflows, deploy |
| `security@platform.local` | security_data_owner | co-sign write-class tools |
| `admin@platform.local` | platform_admin | model catalog, governance config |

**You will switch accounts as you go, and that is deliberate.** Separation of
duties is enforced server-side: the person who builds a thing cannot approve it,
and `platform_admin` does *not* bypass governance roles. Keep the login page
handy; the sign-out button is in the top bar.

> **No LLM key?** Everything except the `llm` node still works. Runs will fail at
> that node with the provider's real error — not a fake answer.

---

## 1. Create the agent (as `creator`)

**Agent Registry → New Agent** → name it `Web Answers`.

You now have a control record in `draft`. Nothing else exists yet.

## 2. Capture intent (as `creator`)

On the agent page → **Capture intent**. Fill in at least:

- **Objective**: `Answer user questions by searching the web and citing sources`
- **Data sensitivity**: `internal`
- **Deployment channel**: `sandbox`

**Submit intent.** The server validates the six field groups, scans free text for
PII, and freezes an immutable version. Warnings appear but do not block.

*Optional:* **Generate design recommendation** proposes an architecture and flow
grounded in your intent, with each claim marked `grounded` or `unverified` by a
mechanical basis check. Accepting a component materializes a draft asset. You can
skip this and build directly — the recommendation is an accelerator, never a gate.

## 3. Register the search tool (as `engineer`)

**Tools → New Tool**:

| Field | Value |
|---|---|
| Name | `Wikipedia Search` |
| Permission type | `read` |
| Implementation | `http_api` |
| Base URL | `https://en.wikipedia.org/w/api.php` |

Then **Submit for approval**.

Two details that matter:

- **Wikipedia rejects requests without a `User-Agent`** (HTTP 403). Add static
  headers to the tool's implementation config:
  ```json
  {"kind": "http_api",
   "config": {"base_url": "https://en.wikipedia.org/w/api.php",
              "headers": {"User-Agent": "AgentOpsPlatform/0.1 (contact: you@example.com)"}}}
  ```
- **`read` keeps it bindable.** Choosing `create`/`update`/`approve`/`deploy`
  marks it write-class: HITL and dual sign-off become mandatory, and the platform
  still refuses to bind or execute it in this phase. That is the advisory-only
  invariant, and it is enforced in three places, not just the UI.

**Switch to `governance` → Approval Queue → Approve.** The tool is now
`approved` and usable.

## 4. Write the system prompt (as `engineer`)

**Prompts → New Pack**, type `system`:

```
You answer questions using ONLY the SEARCH RESULTS provided in the user message.
Quote the article titles you used, as plain text like (source: Article Title).
Never write bracketed source markers. If the results do not contain the answer,
say so plainly and do not guess.
```

Submit it, then **approve it as `governance`**.

> **Why "never write bracketed source markers":** the guardrail node mechanically
> verifies every `[Source N]` citation against retrieved context. This flow has no
> RAG node, so a model writing `[Source 1]` would be fabricating a citation and the
> run would fail — correctly. Plain `(source: Title)` is the right form here.

## 5. Build the workflow (as `engineer`)

**Agent → Workflow builder → New workflow**. Add five nodes and wire them in a
line: `prompt → tool_call → llm → guardrail → output_format`.

Node configuration:

| Node | Setting |
|---|---|
| `prompt` | pack slug: `web-answers-system-prompt` |
| `llm` | temperature `0.2` |
| `output_format` | `text` |
| `guardrail` | leave default |

The `tool_call` node is where the agent becomes real:

```json
{
  "tool_ref": "wikipedia-search",
  "params": {
    "action": "query", "format": "json", "formatversion": 2,
    "prop": "extracts", "exintro": 1, "explaintext": 1,
    "generator": "search", "gsrlimit": 3,
    "gsrsearch": "{{user_input}}"
  },
  "response_extract": {
    "path": "query.pages",
    "fields": ["title", "extract"],
    "limit": 3
  }
}
```

Two mechanisms to understand:

- **`{{user_input}}`** injects the live question into the request. The only
  placeholders are `{{user_input}}` and `{{llm_output}}` — a closed set, no
  expressions, no code execution.
- **`response_extract`** turns the API's JSON into text the model can use. This
  is not cosmetic: feeding raw MediaWiki JSON to Gemini returns
  `MALFORMED_FUNCTION_CALL` and an empty answer. Declaring `path` + `fields`
  once fixes it. If extraction fails, the raw body is kept *and* the error is
  recorded on the span — never silently dropped.
- **`prop=extracts`, not snippets.** Search snippets are ~100 characters and
  truncate mid-sentence; the agent then honestly answers "the results don't say."
  Article intros give it something real to work with. This one change took the
  answer from *"only Mexico is mentioned"* to the correct three countries.

Click **Validate**. The server checks node vocabulary, graph reachability, that
the prompt pack has an *approved* version, that the tool is approved and not
write-class, and that its implementation kind is executable. Fix anything it
reports — validation failures keep the version in `draft`.

Then **Submit** → approve as `governance` → **Activate** as `owner`.

## 6. Run it (as `creator`)

**Agent → Testing console.** Ask:

> Which countries are hosting the 2026 FIFA World Cup?

You get the answer plus the full trace: which node ran, how long it took, the
tokens and cost of the model call, and the guardrail verdict. Every number comes
from the actual run — there is no simulated telemetry anywhere in this platform.

**When something fails, the trace tells you where.** A failed `llm` node reports
the provider's real finish reason. A refused `tool_call` shows the policy reason.
An empty answer is never invented.

---

## 7. Deploy it as an API (optional)

Sandbox deployment needs only an active workflow:

1. Agent page → **Deployments → Access keys → create a group**, then **mint a
   key**. Copy it — it is shown exactly once, and only a SHA-256 hash is stored.
2. Channel `sandbox`, pick the group, **Deploy**.
3. Call it with no session, just the key:

```bash
curl -X POST http://localhost:8000/api/deployed/web-answers-sandbox/invoke \
  -H "X-API-Key: pk_your_key" -H "Content-Type: application/json" \
  -d '{"input":"Which countries are hosting the 2026 FIFA World Cup?"}'
```

The `production` channel demands more, by design: production lifecycle state, a
passing evaluation on that exact workflow version, an evidence pack, and a cost
center. Denials list every unmet reason.

---

## 8. Make the answers provable (optional)

**Evaluations → New pack**, add a case:

```json
{"name": "world cup hosts", "category": "golden",
 "input": "Which countries are hosting the 2026 FIFA World Cup?",
 "expectations": {"must_contain": ["Canada", "Mexico"], "no_write": true}}
```

**Run** it. Cases execute the real engine with all governance controls on, and
the scorecard is computed from actual run traces. That score is what gates
promotion to production — there is no way to promote on a claim.

---

## Swapping in a full-web search engine

Wikipedia needs no key, which is why it is the starting point. For open-web
search, register a second tool and point the workflow at it:

| Provider | Base URL | Auth |
|---|---|---|
| Brave Search | `https://api.search.brave.com/res/v1/web/search` | header `X-Subscription-Token` |
| Tavily | `https://api.tavily.com/search` | bearer |
| Serper | `https://google.serper.dev/search` | header `X-API-KEY` |

1. **Secrets → add** your key under a name like `brave.search.key`. The value is
   encrypted at rest and never returned by any endpoint.
2. On the tool set `auth` to `{"method": "api_key_header", "header_name":
   "X-Subscription-Token", "credential_ref": "brave.search.key"}`.
3. Adjust `params` (`{"q": "{{user_input}}"}`) and `response_extract` to that
   provider's response shape.

The secret is injected server-side from the tool's persisted config at call time.
It is never accepted from a caller and never appears in a response or an audit
entry.

> **Not DuckDuckGo's instant-answer API.** It is keyless and tempting, but it
> returns empty for most real questions — verified while writing this guide. An
> agent built on it looks like it works and then confidently says nothing useful.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Tool try-out returns 403 "non-public address" | SSRF guard blocked a private/loopback host | Use a public URL, or add the host to `PLATFORM_TRYOUT_PRIVATE_HOST_ALLOWLIST` for local development |
| Validation: "pack has no APPROVED version" | Prompt still in draft | Submit it, then approve as `governance` |
| Validation: "tool is write-class" | Permission type is create/update/approve/deploy | Use `read` for retrieval tools |
| Run fails: "no model provider configured" | No API key | Set `PLATFORM_GEMINI_API_KEY` and restart |
| Run fails: "model returned no text (finish_reason=MALFORMED_FUNCTION_CALL…)" | Raw API JSON destabilized the model | Add `response_extract` to the tool node |
| Run fails: "guardrail violation: invalid citations" | Model wrote `[Source N]` with no RAG context | Tell the prompt to cite plain titles instead |
| Agent flips to `needs_review` unexpectedly | A prompt or tool it uses got a newly approved version | Re-run evaluation and re-promote; deployed manifests keep serving their pinned versions |

---

## What just happened, architecturally

The agent you built is not a script. It is a governed record:

- The **intent** is immutable and versioned.
- The **tool** and **prompt** are approved assets; changing either creates a new
  version that must be approved on its own.
- The **workflow** is an approved DAG. Editing an active version forks a draft —
  what runs is exactly what was approved.
- Every **run** writes per-node spans, and those spans are the only source for
  evaluation scores, dashboards, and cost.
- Every **denial** is audited with the policy version that produced it.

That is the difference between an agent that works once in a demo and one you can
put in front of a regulator.
