"""The seven systems of record, assessed — deck slide 21 element 7.

The candidate set is **not ours to choose**. The SOW's boundaries table fixes it:

    "Will not replace systems of record  ->  Jira, GitHub, Confluence,
     ServiceNow, MDR, CCAI, and BigQuery remain authoritative systems"

which is deck slide 21's list exactly. Slide 21 adds "and internal applications"
as a catch-all; that is a category, not a system, so it is surfaced in the UI
copy rather than given a row it could never be assessed against.

**Every `mcp_server` value below was checked on 2026-08-05, not assumed.**
Where it could not be confirmed the value is `unknown` and the blocker says so —
`unknown` is a real state here, and recording it honestly is the difference
between an assessment and a guess. Re-check these before the Week-11 handover:
the MCP ecosystem moves fast, and `none`/`unknown` are the values most likely to
have changed.
"""

from datetime import datetime, timezone

_AT = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _item(**kw) -> dict:
    return {"updated_at": _AT, "candidate_tools": [], "status": "proposed", **kw}


# Ranked. Ranks 1-4 are the 90-day set; 5-7 cannot be, because none of them has
# a confirmed MCP server and the SOW puts building one out of scope. That is
# enforced in services/connector_backlog.py, not just asserted here.
BACKLOG_SEED = [
    _item(
        id="jira",
        system_name="Jira",
        rank=1,
        phase="day_90",
        mcp_server="official",
        mcp_server_note="Atlassian remote MCP server — covers Jira, Confluence, JSM, Bitbucket and Compass from one integration.",
        transport="streamable_http",
        auth_model="oauth2",
        data_sensitivity="internal",
        candidate_tools=["jira_issue_search", "jira_issue_read", "jira_project_read"],
        access_owner="Engineering Tooling — Atlassian org admin",
        rationale=(
            "The recommendation. Present in all three source lists (deck slide 21, the SOW's "
            "systems of record, and our own seed), so it needs no reconciliation first. An "
            "official first-party server already exists, which is what the SOW's "
            "install-don't-build boundary requires. And it is what the reference agent "
            "actually runs on: the SOW's existing agent is the E2E Testing/QA agent, and the "
            "AI-DLC operating model is defined as 'GitHub issue orchestration, Jira "
            "integration'. Read-only issue/project lookups are a natural advisory fit."
        ),
        blockers="Cloud vs Data Center not yet confirmed — the official remote server is a Cloud offering (CONCERNS.md Q10). Access + OAuth app still to be requested (R9).",
        existing_connector_id="jira",
    ),
    _item(
        id="confluence",
        system_name="Confluence",
        rank=2,
        phase="day_90",
        mcp_server="official",
        mcp_server_note="Same Atlassian remote MCP server as Jira — one integration serves both.",
        transport="streamable_http",
        auth_model="oauth2",
        data_sensitivity="internal",
        candidate_tools=["confluence_page_search", "confluence_page_read"],
        access_owner="Knowledge Management — Atlassian org admin",
        rationale=(
            "Rides the Jira integration at near-zero marginal cost — the same server, the same "
            "auth, the same approval. Also the most natural advisory surface in the estate: "
            "policy and runbook retrieval is exactly the read/summarise pattern the base scope "
            "allows, and our seeded confluence_reader is already read-only."
        ),
        blockers="Same Atlassian Cloud/Data Center question as Jira (Q10).",
        existing_connector_id="confluence",
    ),
    _item(
        id="github",
        system_name="GitHub",
        rank=3,
        phase="day_90",
        mcp_server="official",
        mcp_server_note="Official first-party GitHub MCP server; remote, OAuth.",
        transport="streamable_http",
        auth_model="oauth2",
        data_sensitivity="internal",
        candidate_tools=["repo_read", "issue_read", "pull_request_read"],
        access_owner="Platform Engineering — GitHub org owner",
        rationale=(
            "Official first-party server and the most widely deployed in the ecosystem. The SOW "
            "leans on GitHub twice outside this workstream — prompt versioning is mapped to it "
            "(platform component 4) and the AI-DLC model runs on 'GitHub Issue orchestration' "
            "(component 11) — so connectivity here pays into two other workstreams."
        ),
        blockers="Org-owner approval for an OAuth app; scope must be restricted to read.",
        existing_connector_id=None,
    ),
    _item(
        id="bigquery",
        system_name="BigQuery",
        rank=4,
        phase="day_90",
        mcp_server="official",
        mcp_server_note="Google-managed remote BigQuery MCP server — HTTPS endpoint, IAM authorization, audit logging.",
        transport="streamable_http",
        auth_model="iam",
        data_sensitivity="confidential",
        candidate_tools=["dataset_list", "table_schema_read", "query_dry_run"],
        access_owner="Data Platform — GCP project owner",
        rationale=(
            "The only candidate already inside the SOW's approved target stack ('GCP-native', "
            "'Brightspeed-approved GCP / Vertex AI patterns'), and it arrives with IAM "
            "authorization and audit logging rather than needing them bolted on. Ranked below "
            "the other three because it fronts warehouse data: data-boundary controls (slide 21 "
            "element 4, still unbuilt) matter far more here than for issue trackers."
        ),
        blockers="Needs dataset-level scoping decided before any tool is bound — deferring this to a later gateway phase is what makes it rank 4 rather than 1.",
        existing_connector_id=None,
    ),
    _item(
        id="servicenow",
        system_name="ServiceNow",
        rank=5,
        phase="later",
        mcp_server="none",
        mcp_server_note="No first-party MCP server found (checked 2026-08-05).",
        transport=None,
        auth_model="unknown",
        data_sensitivity="confidential",
        access_owner="IT Service Management",
        status="blocked",
        rationale=(
            "A named system of record, so it belongs in the backlog — but it cannot be a 90-day "
            "candidate. With no vendor server, connecting it means building one, which the SOW "
            "explicitly excludes."
        ),
        blockers=(
            "No existing MCP server. The SOW's own treatment is 'backlog custom MCP server "
            "creation'. Unblocks if ServiceNow ships one, if an approved community server "
            "passes security review, or on an explicit scope change."
        ),
        existing_connector_id=None,
    ),
    _item(
        id="ccai",
        system_name="CCAI (Contact Center AI)",
        rank=6,
        phase="later",
        mcp_server="unknown",
        mcp_server_note="No first-party MCP server confirmed as of 2026-08-05 — searched, not found, which is weaker evidence than 'none'.",
        transport=None,
        auth_model="unknown",
        data_sensitivity="restricted",
        access_owner="Contact Center operations",
        status="blocked",
        rationale=(
            "Carries the most sensitive data in the list — customer conversations — so even "
            "with a server it should follow the data-boundary controls, not lead them. "
            "Sequencing it late is a governance choice as much as an availability one."
        ),
        blockers="MCP server availability unverified. Restricted data would need per-field boundary controls (slide 21 element 4) before any read tool is bound.",
        existing_connector_id=None,
    ),
    _item(
        id="mdr",
        system_name="MDR",
        rank=7,
        phase="later",
        mcp_server="unknown",
        mcp_server_note="Cannot be assessed — the system itself is unidentified.",
        transport=None,
        auth_model="unknown",
        # Deliberately the most cautious value: an unidentified system cannot be
        # assumed to be low-sensitivity.
        data_sensitivity="restricted",
        access_owner=None,
        status="blocked",
        rationale=(
            "**The acronym is never expanded in either source document.** 'MDR' appears only "
            "inside the connector lists on deck slides 17 and 21 and in the SOW's systems-of-"
            "record row — never with a definition. It is left in the backlog rather than "
            "dropped, because it is a contracted system of record; it is ranked last because "
            "nobody can assess a system they cannot identify."
        ),
        blockers="System not identified — see CONCERNS.md Q11. One sentence from the client closes this.",
        existing_connector_id=None,
    ),
]
