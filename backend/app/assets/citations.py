"""Citation machinery (Pass 3, reused by evaluation in Pass 6):
retrieved chunks are wrapped `[Source N: name, location]` before prompt
assembly, and responses are mechanically checked — every `[Source N]` cited in
the output must exist in the provided context. No judge involved; this is
string-level truth.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SourceEntry:
    n: int
    name: str
    location: str
    text: str


def wrap_chunks(chunks: list[tuple[str, str, str]]) -> tuple[str, list[SourceEntry]]:
    """chunks = [(source_name, location, text)] → (context_block, source_map)."""
    entries: list[SourceEntry] = []
    lines: list[str] = []
    for i, (name, location, text) in enumerate(chunks, start=1):
        entries.append(SourceEntry(n=i, name=name, location=location, text=text))
        lines.append(f"[Source {i}: {name}, {location}]\n{text}")
    return "\n\n".join(lines), entries


_CITE_RE = re.compile(r"\[Source (\d+)")


def check_citations(response_text: str, source_map: list[SourceEntry]) -> dict:
    """Mechanical: cited numbers must exist in the context that was provided."""
    valid = {e.n for e in source_map}
    cited = [int(m) for m in _CITE_RE.findall(response_text)]
    invalid = sorted({c for c in cited if c not in valid})
    return {
        "cited": sorted(set(cited)),
        "invalid": invalid,                       # fabricated citations — hard fail signal
        "uncited_sources": sorted(valid - set(cited)),
        "ok": not invalid,
    }
