"""Intent document schema (Pass 2): 6 field groups, Prov-enveloped leaves,
server-side cross-field validation.

Leaves may arrive either raw (`"x"`) or enveloped
(`{"value": "x", "source": "user"|"engine"|"default", "confirmed": bool}`) —
Decision 1.2 keeps Prov envelopes on intent + recommendation fields only.
Validation unwraps; storage preserves whatever shape the client sent (the
frozen payload is the user's artifact, untouched).

Hard errors block submission (422). Warnings are stored on the document and
surfaced to reviewers — they never block.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RULES_VERSION = "intent-validation-v1-increment-b"

GROUPS = (
    "identity_purpose", "trigger_contract", "data_rules",
    "tools_interaction", "risk_governance", "volume_evidence",
)

TRIGGER_TYPES = {"user_message", "api_call", "scheduled", "event"}
OUTPUT_FORMATS = {"text", "structured_json", "action_summary"}
SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
FRESHNESS = {"static", "periodic", "live"}
INTERACTION_STYLES = {"single_turn", "conversational"}
RISK_TIERS = {"low", "medium", "high", "restricted"}
APPROVAL_REQS = {"none", "pre_action", "post_action", "continuous"}
CHANNELS = {"sandbox", "internal_chat", "rest_api"}
LATENCY_TARGETS = {"interactive", "batch"}
EVIDENCE_REQS = {"basic", "standard", "full"}


def unwrap(leaf: Any) -> Any:
    """Prov envelope → value; raw values pass through."""
    if isinstance(leaf, dict) and "value" in leaf and ("source" in leaf or "confirmed" in leaf):
        return leaf["value"]
    return leaf


def group(payload: dict, name: str) -> dict:
    g = payload.get(name)
    return g if isinstance(g, dict) else {}


def gv(payload: dict, group_name: str, key: str, default: Any = None) -> Any:
    """Unwrapped value of payload[group][key]."""
    v = unwrap(group(payload, group_name).get(key, default))
    return default if v is None else v


@dataclass
class NormalizedIntent:
    """Flat, unwrapped view of the payload — the recommender's input contract."""
    objective: str = ""
    business_function: str = ""
    target_users: str = ""
    success_criteria: str = ""
    trigger_type: str = "user_message"
    input_description: str = ""
    output_description: str = ""
    output_format: str = "text"
    data_sources: list[str] = field(default_factory=list)
    data_sensitivity: str = "internal"
    business_rules: str = ""
    knowledge_freshness: str = "static"
    tools_required: list[dict] = field(default_factory=list)  # {name, purpose, system?}
    mcp_connectors_required: bool = False
    interaction_style: str = "single_turn"
    external_systems: list[str] = field(default_factory=list)
    risk_tier: str | None = None
    human_approval_requirement: str = "none"
    write_actions_expected: bool = False
    compliance_notes: str = ""
    deployment_channel: str = "sandbox"
    expected_volume_per_day: int | None = None
    latency_target: str = "interactive"
    evidence_requirement: str = "standard"

    def tool_names(self) -> list[str]:
        return [str(unwrap(t.get("name")) or "") for t in self.tools_required if isinstance(t, dict)]

    def free_text(self) -> dict[str, str]:
        """Free-text fields by path — the PII scan surface."""
        out = {
            "identity_purpose.objective": self.objective,
            "identity_purpose.target_users": self.target_users,
            "identity_purpose.success_criteria": self.success_criteria,
            "trigger_contract.input_description": self.input_description,
            "trigger_contract.output_description": self.output_description,
            "data_rules.business_rules": self.business_rules,
            "risk_governance.compliance_notes": self.compliance_notes,
        }
        return {k: v for k, v in out.items() if v}


def normalize(payload: dict) -> NormalizedIntent:
    def listify(v: Any) -> list:
        v = unwrap(v)
        if isinstance(v, list):
            return [unwrap(x) for x in v]
        return [] if v in (None, "") else [v]

    tools_raw = listify(group(payload, "tools_interaction").get("tools_required"))
    tools = [t if isinstance(t, dict) else {"name": str(t), "purpose": ""} for t in tools_raw]

    vol = gv(payload, "volume_evidence", "expected_volume_per_day")
    try:
        vol = int(vol) if vol not in (None, "") else None
    except (TypeError, ValueError):
        vol = None

    return NormalizedIntent(
        objective=str(gv(payload, "identity_purpose", "objective", "") or ""),
        business_function=str(gv(payload, "identity_purpose", "business_function", "") or ""),
        target_users=str(gv(payload, "identity_purpose", "target_users", "") or ""),
        success_criteria=str(gv(payload, "identity_purpose", "success_criteria", "") or ""),
        trigger_type=str(gv(payload, "trigger_contract", "trigger_type", "user_message")),
        input_description=str(gv(payload, "trigger_contract", "input_description", "") or ""),
        output_description=str(gv(payload, "trigger_contract", "output_description", "") or ""),
        output_format=str(gv(payload, "trigger_contract", "output_format", "text")),
        data_sources=[str(s) for s in listify(group(payload, "data_rules").get("data_sources")) if s],
        data_sensitivity=str(gv(payload, "data_rules", "data_sensitivity", "internal")),
        business_rules=str(gv(payload, "data_rules", "business_rules", "") or ""),
        knowledge_freshness=str(gv(payload, "data_rules", "knowledge_freshness", "static")),
        tools_required=tools,
        mcp_connectors_required=bool(gv(payload, "tools_interaction", "mcp_connectors_required", False)),
        interaction_style=str(gv(payload, "tools_interaction", "interaction_style", "single_turn")),
        external_systems=[str(s) for s in listify(group(payload, "tools_interaction").get("external_systems")) if s],
        risk_tier=(lambda r: str(r) if r not in (None, "") else None)(gv(payload, "risk_governance", "risk_tier")),
        human_approval_requirement=str(gv(payload, "risk_governance", "human_approval_requirement", "none") or "none"),
        write_actions_expected=bool(gv(payload, "risk_governance", "write_actions_expected", False)),
        compliance_notes=str(gv(payload, "risk_governance", "compliance_notes", "") or ""),
        deployment_channel=str(gv(payload, "risk_governance", "deployment_channel", "sandbox")),
        expected_volume_per_day=vol,
        latency_target=str(gv(payload, "volume_evidence", "latency_target", "interactive")),
        evidence_requirement=str(gv(payload, "volume_evidence", "evidence_requirement", "standard")),
    )


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]
    rules_version: str = RULES_VERSION

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_enum(value: str, allowed: set[str], label: str, errors: list[str]) -> None:
    if value and value not in allowed:
        errors.append(f"{label} must be one of {sorted(allowed)} (got {value!r})")


def validate(intent: NormalizedIntent) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if len(intent.objective.strip()) < 20:
        errors.append("identity_purpose.objective must describe the agent's job (min 20 characters)")

    _check_enum(intent.trigger_type, TRIGGER_TYPES, "trigger_contract.trigger_type", errors)
    _check_enum(intent.output_format, OUTPUT_FORMATS, "trigger_contract.output_format", errors)
    _check_enum(intent.data_sensitivity, SENSITIVITIES, "data_rules.data_sensitivity", errors)
    _check_enum(intent.knowledge_freshness, FRESHNESS, "data_rules.knowledge_freshness", errors)
    _check_enum(intent.interaction_style, INTERACTION_STYLES, "tools_interaction.interaction_style", errors)
    if intent.risk_tier is not None:
        _check_enum(intent.risk_tier, RISK_TIERS, "risk_governance.risk_tier", errors)
    _check_enum(intent.human_approval_requirement, APPROVAL_REQS, "risk_governance.human_approval_requirement", errors)
    _check_enum(intent.deployment_channel, CHANNELS, "risk_governance.deployment_channel", errors)
    _check_enum(intent.latency_target, LATENCY_TARGETS, "volume_evidence.latency_target", errors)
    _check_enum(intent.evidence_requirement, EVIDENCE_REQS, "volume_evidence.evidence_requirement", errors)

    # Cross-field HARD rules ---------------------------------------------------
    if intent.risk_tier == "restricted" and intent.human_approval_requirement in ("", "none"):
        errors.append(
            "Restricted risk tier requires a human approval requirement (Governance Policy 4.2)"
        )
    if intent.mcp_connectors_required and not intent.tools_required:
        errors.append("tools_interaction.mcp_connectors_required=true but no tools_required are declared")
    if intent.deployment_channel != "sandbox" and intent.expected_volume_per_day is None:
        errors.append(
            "volume_evidence.expected_volume_per_day is required when deployment_channel is not sandbox"
        )

    # Warnings (stored, never blocking) ---------------------------------------
    if intent.write_actions_expected:
        warnings.append(
            "write_actions_expected: this platform phase enforces advisory-only execution — "
            "write actions will be designed in but not enabled (phased write doctrine, Decision 0.3)"
        )
    if intent.data_sensitivity in ("confidential", "restricted") and intent.deployment_channel == "rest_api":
        warnings.append(
            f"{intent.data_sensitivity} data over a REST API channel — data-boundary review required"
        )
    if intent.risk_tier in ("high", "restricted") and intent.evidence_requirement == "basic":
        warnings.append("high/restricted risk with basic evidence requirement — 'full' is the governed default")
    if not intent.data_sources and intent.knowledge_freshness != "static":
        warnings.append("knowledge_freshness set but no data_sources declared")

    return ValidationResult(errors=errors, warnings=warnings)
