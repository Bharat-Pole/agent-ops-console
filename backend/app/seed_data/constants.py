# Ported verbatim from src/kernel/constants.ts — only the pieces the server
# needs live (registration/lifecycle). The rest of that file (tier labels,
# persona metadata, etc.) is UI-only and stays client-side.
#
# GOVERNANCE_MATRIX / PATH_DEFS used to live here as a hardcoded Python copy of
# kernel/constants.ts — moved to the real policy_rules/path_definitions tables
# (see governance_repo.py / seed_data/governance_catalog.py) so editing a rule
# via Admin Console actually changes registration behavior. Import
# governance_repo.governance_path_for()/get_path_definition() instead.

FAST_PATH_DAYS = 90

RUNTIME_STEP_NAMES = [
    "Resolver profile",
    "Runtime host",
    "Model gateway",
    "MCP sidecars",
    "Telemetry sink",
]

CONTENT_STEP_NAMES = ["Ingest", "Parse", "Chunk", "Embed", "Index", "Tag & Govern", "Refresh"]

P95_TARGET_MS = {"minimal": 2000, "standardized": 5000, "advanced": 15000}
