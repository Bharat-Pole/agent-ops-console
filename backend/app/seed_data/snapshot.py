import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# The initial 8-agent demo workspace (agents/approvals/auditLog/evalPacks) plus
# SEED_TOOLS/SEED_SOURCES are pure, deterministic data in the frontend's own
# src/seed/*.ts (no Date.now()/Math.random() — fixed DEMO_TODAY). Rather than
# hand-transcribing ~13 TS generator files into Python (real risk of subtle
# drift in date math / provenance fields), this JSON is a byte-exact snapshot
# of createInitialWorkspace() + SEED_TOOLS + SEED_SOURCES, taken by running the
# actual, already-verified Node generator once. Regenerate by running (from
# the repo root, with a temporary script importing @/seed, @/seed/tools,
# @/seed/sources and writing this file) if src/seed/* ever changes.
_SNAPSHOT_PATH = Path(__file__).parent / "seed_snapshot.json"


@lru_cache(maxsize=1)
def load_seed_snapshot() -> dict[str, Any]:
    with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)
