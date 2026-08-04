# Ported verbatim from src/kernel/constants.ts — only the pieces the server
# needs live (registration/lifecycle). The rest of that file (tier labels,
# persona metadata, etc.) is UI-only and stays client-side.

GOVERNANCE_MATRIX = {
    "minimal": {"low": "fast", "medium": "standard", "high": "standard", "critical": "deep"},
    "standardized": {"low": "fast", "medium": "standard", "high": "deep", "critical": "deep"},
    "advanced": {"low": "standard", "medium": "deep", "high": "deep", "critical": "critical"},
}


def governance_path_for(tier: str, risk: str) -> str:
    return GOVERNANCE_MATRIX[tier][risk]


PATH_DEFS = {
    "fast": {
        "path": "fast",
        "label": "Fast",
        "approvals": [],
        "hitl_gates": 1,
        "desc": "Auto-approve if schema valid; 1 HITL gate max (pre-deploy); 5-min auto-approval SLA.",
    },
    "standard": {
        "path": "standard",
        "label": "Standard",
        "approvals": ["business_owner", "risk_officer"],
        "hitl_gates": 2,
        "desc": "business_owner approval + risk_officer review; 2 HITL gates.",
    },
    "deep": {
        "path": "deep",
        "label": "Deep",
        "approvals": ["business_owner", "risk_officer", "security_committee"],
        "hitl_gates": 2,
        "desc": "Full Phase 6 eval (pack must score ≥90) + committee approval.",
    },
    "critical": {
        "path": "critical",
        "label": "Critical",
        "approvals": ["business_owner", "risk_officer", "security_committee"],
        "hitl_gates": 3,
        "desc": "Deep + mandatory runtime HITL per action.",
    },
}

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
