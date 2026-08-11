"""
Splits a fetched source's combined raw text back into its real, discrete
per-item documents (Confluence pages, Jira issues, GitHub files, ServiceNow
records) using the same delimiter markers those fetchers already embed when
they flatten multiple items into one blob (see confluence_fetcher.py,
jira_fetcher.py, github_fetcher.py, servicenow_fetcher.py).

This exists so a single connected source can carry real per-document tags
(domain/owner/sensitivity/validity) instead of collapsing every fetched item
into one governance unit. Splitting off the fetcher's own real markers (not a
generic heuristic) means no fabricated boundaries — a document only appears
here if the fetcher itself identified it as one.

Single-item source types (file/url/text/database/bigquery) are always
returned as one document — a query result or an uploaded file IS one
governance unit, there's nothing further to split.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PRIMARY_DOC_REF = "primary"

_CONFLUENCE_RE = re.compile(r"^=== CONFLUENCE PAGE: (.+?) ===$", re.MULTILINE)
_GITHUB_RE = re.compile(r"^=== FILE: (.+?) ===$", re.MULTILINE)
_JIRA_RE = re.compile(r"^--- JIRA ISSUE (\S+) \|.*?---$", re.MULTILINE)
_SERVICENOW_RE = re.compile(r"^--- SERVICENOW \w+ RECORD #\d+ \| sys_id: (\S+) ---$", re.MULTILINE)

_SPLITTERS: dict[str, re.Pattern] = {
    "confluence": _CONFLUENCE_RE,
    "github": _GITHUB_RE,
    "jira": _JIRA_RE,
    "servicenow": _SERVICENOW_RE,
}


@dataclass
class SplitDocument:
    doc_ref: str
    title: str
    text: str


def split_documents(source_type: str, raw_text: str, source_name: str) -> list[SplitDocument]:
    pattern = _SPLITTERS.get(source_type)
    if pattern is None:
        return [SplitDocument(doc_ref=PRIMARY_DOC_REF, title=source_name, text=raw_text)]

    matches = list(pattern.finditer(raw_text))
    if not matches:
        # Fetcher returned a single item (e.g. one Confluence page_id, not a
        # space search) — no per-item markers to split on, treat as one doc.
        return [SplitDocument(doc_ref=PRIMARY_DOC_REF, title=source_name, text=raw_text)]

    docs: list[SplitDocument] = []
    for i, m in enumerate(matches):
        ref_or_title = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        body = raw_text[body_start:body_end].strip()
        # Jira/ServiceNow capture a stable external key (issue key / sys_id) —
        # use it as both ref and a short title prefix. Confluence/GitHub capture
        # the title itself — reuse it as the ref too (unique within the source).
        docs.append(SplitDocument(doc_ref=ref_or_title, title=ref_or_title, text=body))
    return docs
