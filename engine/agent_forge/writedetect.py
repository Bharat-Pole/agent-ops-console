"""Port of the console's src/kernel/engine/writeDetect.ts heuristics.

Used as the PRIMARY guardrail path: re-scan bound_tools + the objective for
write intent, independent of review_card (which may be null on a pre-review
export). Advisory-only scope is LOCKED — anything flagged here is never bound.
"""
from __future__ import annotations

import re

WRITE_VERBS = [
    "send", "approve", "deploy", "update", "create", "delete", "close", "assign",
    "notify", "post", "execute", "modify", "file", "submit", "remove", "email",
]
WRITE_TOOL_FRAGMENTS = [
    "notifier", "sender", "updater", "writer", "poster", "creator", "deleter",
    "approver", "deployer",
]
ADVISORY_FRAMES = [
    "draft", "recommend", "suggest", "propose", "summarize", "summarise",
    "prepare a draft", "review",
]
OBJECT_NOUNS = [
    "email", "message", "ticket", "record", "notification", "notifications",
    "comms", "update", "filing", "report", "slack", "alert", "account",
]


def tool_is_write_capable(name: str) -> bool:
    n = name.lower()
    if any(f in n for f in WRITE_TOOL_FRAGMENTS):
        return True
    return any(v in n for v in WRITE_VERBS)


def objective_has_write_intent(objective: str) -> bool:
    t = (objective or "").lower()
    for verb in WRITE_VERBS:
        m = re.search(rf"\b{verb}\w*\b", t)
        if not m:
            continue
        before = t[max(0, m.start() - 20):m.start()]
        after = t[m.start():m.start() + 40]
        advisory = any(f in before for f in ADVISORY_FRAMES)
        has_object = any(nn in after for nn in OBJECT_NOUNS)
        if not advisory and has_object:
            return True
    return False
