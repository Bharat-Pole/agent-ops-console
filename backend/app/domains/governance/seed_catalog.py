# Real Governance policy-as-configuration catalog (Blueprint §4 / §9). This is
# the SAME content as src/kernel/constants.ts GOVERNANCE_MATRIX/PATH_DEFS and
# the (now superseded) backend/app/seed_data/constants.py Python copy — moved
# into the DB, not invented, so registration.py reading it from here behaves
# identically to before until someone actually edits a rule via Admin Console.
POLICY_RULES: list[dict] = [
    {"capability_tier": "minimal", "risk_tier": "low", "governance_path": "fast"},
    {"capability_tier": "minimal", "risk_tier": "medium", "governance_path": "standard"},
    {"capability_tier": "minimal", "risk_tier": "high", "governance_path": "standard"},
    {"capability_tier": "minimal", "risk_tier": "critical", "governance_path": "deep"},
    {"capability_tier": "standardized", "risk_tier": "low", "governance_path": "fast"},
    {"capability_tier": "standardized", "risk_tier": "medium", "governance_path": "standard"},
    {"capability_tier": "standardized", "risk_tier": "high", "governance_path": "deep"},
    {"capability_tier": "standardized", "risk_tier": "critical", "governance_path": "deep"},
    {"capability_tier": "advanced", "risk_tier": "low", "governance_path": "standard"},
    {"capability_tier": "advanced", "risk_tier": "medium", "governance_path": "deep"},
    {"capability_tier": "advanced", "risk_tier": "high", "governance_path": "deep"},
    {"capability_tier": "advanced", "risk_tier": "critical", "governance_path": "critical"},
]

PATH_DEFINITIONS: list[dict] = [
    {
        "path": "fast",
        "label": "Fast",
        "approvals": [],
        "hitl_gates": 1,
        "description": "Auto-approve if schema valid; 1 HITL gate max (pre-deploy); 5-min auto-approval SLA.",
    },
    {
        "path": "standard",
        "label": "Standard",
        "approvals": ["business_owner", "risk_officer"],
        "hitl_gates": 2,
        "description": "business_owner approval + risk_officer review; 2 HITL gates.",
    },
    {
        "path": "deep",
        "label": "Deep",
        "approvals": ["business_owner", "risk_officer", "security_committee"],
        "hitl_gates": 2,
        "description": "Full Phase 6 eval (pack must score ≥90) + committee approval.",
    },
    {
        "path": "critical",
        "label": "Critical",
        "approvals": ["business_owner", "risk_officer", "security_committee"],
        "hitl_gates": 3,
        "description": "Deep + mandatory runtime HITL per action.",
    },
]
