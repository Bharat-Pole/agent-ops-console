"""PII detection — local, flag-only (Decision 2.1). Curated regex detectors
behind a small adapter seam; Cloud DLP (redact-before-write) replaces this in
GCP deployments. Findings NEVER block and NEVER mutate the payload — they are
stored as `pii_flags` and surfaced to reviewers before any LLM call.

Honesty note: this is a heuristic detector and is labeled as such in every
finding (`detector: "regex-v1"`). No claim of completeness is made.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

DETECTOR_VERSION = "regex-v1"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # +1 555 123 4567 / (555) 123-4567 / 555-123-4567 — 10+ digit phone shapes
    ("phone", re.compile(r"(?<!\d)(?:\+?\d{1,2}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\d)")),
    ("ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("ipv4", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")),
    ("card_number", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
]


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _mask(match: str) -> str:
    compact = match.strip()
    if len(compact) <= 4:
        return "***"
    return f"{compact[:2]}…{compact[-2:]}"


@dataclass
class PiiFlag:
    path: str
    kind: str
    preview: str  # masked — raw values are never copied out of the payload
    count: int
    detector: str = DETECTOR_VERSION


def scan_text(path: str, text: str) -> list[PiiFlag]:
    flags: list[PiiFlag] = []
    for kind, pattern in _PATTERNS:
        matches = [m.group(0) for m in pattern.finditer(text)]
        if kind == "card_number":
            matches = [m for m in matches if _luhn_ok(re.sub(r"[ -]", "", m))]
        if matches:
            flags.append(PiiFlag(path=path, kind=kind, preview=_mask(matches[0]), count=len(matches)))
    return flags


def scan_fields(fields: dict[str, str]) -> list[dict]:
    """Scan {path: text} and return JSON-serializable flags."""
    out: list[PiiFlag] = []
    for path, text in fields.items():
        out.extend(scan_text(path, text))
    return [asdict(f) for f in out]
