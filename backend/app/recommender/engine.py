"""Recommendation engine (Pass 2). Layer 1 (deterministic) always runs; Layer 2
(LLM) drafts when a provider is configured, and every LLM claim passes the
honesty machinery — as code, not prompt hopes:

  1. pydantic schema validation of the raw output (one corrective retry)
  2. per-item basis token-overlap vs the intent text → grounded | unverified
  3. closed-world enforcement: registry refs must resolve; unresolved refs are
     demoted to described-need entries (in Increment B the registries are empty
     by construction, so every ref demotes — Increment C wires resolution)
  4. suggested risk tier cross-checked against the deterministic heuristic —
     disagreement is surfaced as a contradiction, never silently resolved
  5. flow validation + guardrail auto-insert (spec §3.5); a flow that still
     fails validation is replaced by the deterministic flow (validator gates)

LLM failure is honest: the recommendation ships as the labeled deterministic
baseline with the error recorded — never fabricated content, never a gate.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from ..adapters.models import ModelAdapter, ModelCallError, ModelUnavailable, get_model_adapter
from ..intent.schema import NormalizedIntent, normalize
from . import deterministic
from .prompts import PROMPT_VERSION, SYSTEM, retry_prompt, user_prompt

ENGINE_VERSION = "reco-engine-v1"
BASIS_OVERLAP_THRESHOLD = 0.5

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "will",
    "should", "must", "have", "has", "can", "into", "over", "when", "then",
    "them", "their", "its", "also", "any", "all", "not", "our", "your",
}


# ---- LLM output contract ----------------------------------------------------

class RecoArchitecture(BaseModel):
    kind: Literal["single", "sequential_pipeline", "hub_and_spoke", "graph"]
    rationale: str = ""
    basis: str = ""


class RecoRisk(BaseModel):
    tier: Literal["low", "medium", "high", "restricted"]
    basis: str = ""


class RecoComponent(BaseModel):
    kind: Literal["prompt", "tool", "knowledge", "model", "connector"]
    name: str
    purpose: str = ""
    registry_ref: str | None = None
    basis: str = ""


class FlowNode(BaseModel):
    id: str
    type: str
    label: str = ""
    config: dict = Field(default_factory=dict)


class FlowEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    when: str | None = None

    model_config = {"populate_by_name": True}


class RecoFlow(BaseModel):
    nodes: list[FlowNode]
    edges: list[FlowEdge] = Field(default_factory=list)
    basis: str = ""

    def as_dict(self) -> dict:
        return {
            "nodes": [n.model_dump() for n in self.nodes],
            "edges": [{"from": e.from_, "to": e.to, **({"when": e.when} if e.when else {})} for e in self.edges],
        }


class LlmRecommendation(BaseModel):
    summary: str = ""
    architecture: RecoArchitecture
    suggested_risk_tier: RecoRisk
    components: list[RecoComponent] = Field(default_factory=list)
    suggested_agent_flow: RecoFlow | None = None
    missing_information: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)


class MalformedOutput(Exception):
    pass


# ---- basis verification -----------------------------------------------------

def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in _STOPWORDS}


def basis_overlap(basis: str, corpus_tokens: set[str]) -> float:
    b = _tokens(basis)
    if not b:
        return 0.0
    return len(b & corpus_tokens) / len(b)


def _corpus(intent: NormalizedIntent) -> set[str]:
    parts = list(intent.free_text().values())
    parts.extend(intent.data_sources)
    parts.extend(intent.tool_names())
    parts.extend(intent.external_systems)
    parts.append(intent.business_function)
    return _tokens(" ".join(parts))


def _verify_basis(basis: str, corpus_tokens: set[str]) -> dict:
    if not basis.strip():
        return {"verification": "unverified", "overlap": 0.0, "note": "no basis provided"}
    overlap = round(basis_overlap(basis, corpus_tokens), 3)
    if overlap >= BASIS_OVERLAP_THRESHOLD:
        return {"verification": "grounded", "overlap": overlap}
    return {"verification": "unverified", "overlap": overlap,
            "note": "basis does not sufficiently overlap the intent text — review carefully"}


# ---- closed world (Increment C: real registries) ----------------------------

def _norm_ref(ref: str) -> str:
    """'tools://slug@v1' | 'slug@v1' | 'slug' → 'slug'."""
    ref = ref.split("://", 1)[-1]
    return ref.split("@", 1)[0].strip().lower()


def resolve_registry_ref(kind: str, ref: str | None, db=None) -> bool:
    """A ref resolves only against the GOVERNED set: approved tools, active
    models/connectors. Draft assets are not recommendable ground truth."""
    if not ref or db is None:
        return False
    from sqlalchemy import select

    from ..models import AssetStatus, McpConnector, ModelCatalogEntry, ToolRecord
    name = _norm_ref(ref)
    if kind == "tool":
        return db.scalars(select(ToolRecord).where(
            ToolRecord.slug == name, ToolRecord.status == AssetStatus.approved)).first() is not None
    if kind == "model":
        return db.scalars(select(ModelCatalogEntry).where(
            ModelCatalogEntry.model_ref == ref.strip(),
            ModelCatalogEntry.status == "active")).first() is not None
    if kind == "connector":
        return db.scalars(select(McpConnector).where(
            McpConnector.name == ref.strip(), McpConnector.status == "active")).first() is not None
    return False


def registry_context(db) -> tuple[list[dict], list[dict], list[dict]]:
    """The closed world injected into the prompt: approved tools, active models
    and connectors — exactly what resolve_registry_ref accepts."""
    if db is None:
        return [], [], []
    from sqlalchemy import select

    from ..models import AssetStatus, McpConnector, ModelCatalogEntry, ToolRecord
    tools = [
        {"ref": f"tools://{t.slug}@v{t.version}", "name": t.name,
         "permission_type": t.permission_type.value, "description": t.description[:160]}
        for t in db.scalars(select(ToolRecord).where(ToolRecord.status == AssetStatus.approved)).all()
    ]
    models = [
        {"ref": m.model_ref, "kind": m.kind, "display_name": m.display_name}
        for m in db.scalars(select(ModelCatalogEntry).where(ModelCatalogEntry.status == "active")).all()
    ]
    connectors = [
        {"ref": c.name, "transport": c.transport}
        for c in db.scalars(select(McpConnector).where(McpConnector.status == "active")).all()
    ]
    return tools, models, connectors


# ---- LLM call ---------------------------------------------------------------

def _parse_llm(text: str) -> LlmRecommendation:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    try:
        return LlmRecommendation.model_validate(json.loads(cleaned))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise MalformedOutput(str(exc)) from exc


def _call_llm(adapter: ModelAdapter, intent_json: dict,
              registries: tuple[list[dict], list[dict], list[dict]]) -> tuple[LlmRecommendation, list[dict]]:
    """One corrective retry on malformed output (Pass 2 decision)."""
    attempts: list[dict] = []
    reg_tools, reg_models, reg_connectors = registries
    prompt = user_prompt(intent_json, tools=reg_tools, models=reg_models, connectors=reg_connectors)
    result = adapter.generate_json(SYSTEM, prompt, temperature=0.2)
    attempts.append({"model_id": result.model_id, "raw": result.text})
    try:
        return _parse_llm(result.text), attempts
    except MalformedOutput as first_error:
        retry = adapter.generate_json(
            SYSTEM, prompt + "\n\n" + retry_prompt(str(first_error)), temperature=0.2
        )
        attempts.append({"model_id": retry.model_id, "raw": retry.text, "retry": True})
        return _parse_llm(retry.text), attempts  # raises MalformedOutput again on 2nd failure


# ---- flow guardrail fix-up --------------------------------------------------

def ensure_guardrail(flow: dict, risk_tier: str) -> tuple[dict, list[str]]:
    """Auto-insert a guardrail before each unguarded output_format node for
    High/Restricted (spec §3.5). Returns (flow, adjustments)."""
    if risk_tier not in ("high", "restricted"):
        return flow, []
    nodes = [dict(n) for n in flow.get("nodes") or []]
    edges = [dict(e) for e in flow.get("edges") or []]
    by_id = {n["id"]: n for n in nodes}
    adjustments: list[str] = []
    for out in [n for n in nodes if n.get("type") == "output_format"]:
        feeders = [e for e in edges if e.get("to") == out["id"]]
        if any(by_id.get(e["from"], {}).get("type") == "guardrail" for e in feeders):
            continue
        gid = f"guardrail_{out['id']}"
        nodes.append({"id": gid, "type": "guardrail", "label": "Output guardrail (fails closed)",
                      "config": {"auto_inserted": True, "reason": f"{risk_tier} risk tier (spec §3.5)"}})
        for e in feeders:
            e["to"] = gid
        edges.append({"from": gid, "to": out["id"]})
        adjustments.append(f'guardrail auto-inserted before output node "{out["id"]}" ({risk_tier} risk)')
    return {"nodes": nodes, "edges": edges}, adjustments


# ---- result assembly --------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "item"


def generate(payload: dict, db=None) -> dict:
    """Engine entry: intent payload → recommendation record fields. `db` feeds
    the closed world (registry context + ref resolution); persistence/audit
    live in the router. Without db the closed world is empty (unit tests)."""
    intent = normalize(payload)
    det = deterministic.run(intent)
    det_risk = det["risk"]["risk_tier"]
    corpus = _corpus(intent)
    registries = registry_context(db)

    adapter = get_model_adapter()
    llm_out: LlmRecommendation | None = None
    llm_attempts: list[dict] = []
    llm_error: str | None = None
    model_id: str | None = None

    if adapter is not None:
        try:
            llm_out, llm_attempts = _call_llm(adapter, _intent_public_json(intent), registries)
            model_id = llm_attempts[-1]["model_id"]
        except (ModelUnavailable, ModelCallError, MalformedOutput) as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
            model_id = llm_attempts[-1]["model_id"] if llm_attempts else None

    items: list[dict] = []
    validation: dict = {
        "engine_version": ENGINE_VERSION,
        "deterministic_rules_version": det["rules_version"],
        "basis_threshold": BASIS_OVERLAP_THRESHOLD,
        "contradictions": [],
        "closed_world_demotions": [],
        "flow": {"source": "deterministic", "violations": [], "adjustments": []},
    }
    if llm_error:
        validation["llm_error"] = llm_error

    if llm_out is None:
        # honest deterministic baseline — labeled, never fabricated
        engine = "deterministic"
        rec = det["recommendation"]
        items.append({
            "id": "architecture", "kind": "architecture",
            "title": f"Architecture: {rec['architecture']}",
            "detail": {"architecture": rec["architecture"], "rationale": rec["rationale"],
                       "sub_agents": rec["sub_agents"], "graph": rec["graph"]},
            "basis": "; ".join(rec["rationale"]),
            "verification": "deterministic", "state": "proposed",
        })
        items.append({
            "id": "risk_tier", "kind": "risk_tier",
            "title": f"Risk tier: {det_risk}",
            "detail": {"tier": det_risk, "why": det["risk"]["why"],
                       "deterministic_tier": det_risk, "contradiction": False},
            "basis": det["risk"]["why"],
            "verification": "deterministic", "state": "proposed",
        })
        flow = rec["flow"]
    else:
        engine = "llm+deterministic"

        arch_check = _verify_basis(llm_out.architecture.basis, corpus)
        items.append({
            "id": "architecture", "kind": "architecture",
            "title": f"Architecture: {llm_out.architecture.kind}",
            "detail": {"architecture": llm_out.architecture.kind,
                       "rationale": [llm_out.architecture.rationale],
                       "deterministic_baseline": det["recommendation"]["architecture"]},
            "basis": llm_out.architecture.basis, **arch_check, "state": "proposed",
        })

        risk_check = _verify_basis(llm_out.suggested_risk_tier.basis, corpus)
        contradiction = llm_out.suggested_risk_tier.tier != det_risk
        if contradiction:
            validation["contradictions"].append({
                "field": "risk_tier",
                "llm": llm_out.suggested_risk_tier.tier,
                "deterministic": det_risk,
                "note": "LLM and deterministic risk disagree — reviewer must resolve; "
                        "the deterministic signal is never silently overridden",
            })
        items.append({
            "id": "risk_tier", "kind": "risk_tier",
            "title": f"Risk tier: {llm_out.suggested_risk_tier.tier}"
                     + (f" (deterministic says {det_risk})" if contradiction else ""),
            "detail": {"tier": llm_out.suggested_risk_tier.tier, "deterministic_tier": det_risk,
                       "contradiction": contradiction},
            "basis": llm_out.suggested_risk_tier.basis, **risk_check, "state": "proposed",
        })

        for i, comp in enumerate(llm_out.components):
            comp_check = _verify_basis(comp.basis, corpus)
            state = "proposed"
            detail = comp.model_dump()
            if comp.registry_ref and not resolve_registry_ref(comp.kind, comp.registry_ref, db):
                state = "described_need"
                detail["registry_ref"] = None
                detail["demoted_from_ref"] = comp.registry_ref
                validation["closed_world_demotions"].append({
                    "item": comp.name, "kind": comp.kind, "ref": comp.registry_ref,
                    "note": "reference does not resolve in the registry — demoted to described need",
                })
            elif comp.registry_ref is None:
                state = "described_need"
            items.append({
                "id": f"component:{i}:{comp.kind}:{_slug(comp.name)}", "kind": f"component_{comp.kind}",
                "title": f"{comp.kind.title()}: {comp.name}",
                "detail": detail, "basis": comp.basis, **comp_check, "state": state,
            })

        # flow: LLM drafts, validator gates
        risk_for_flow = det_risk  # governance floor comes from the deterministic signal
        if llm_out.suggested_agent_flow and llm_out.suggested_agent_flow.nodes:
            candidate = llm_out.suggested_agent_flow.as_dict()
            candidate, adjustments = ensure_guardrail(candidate, risk_for_flow)
            violations = deterministic.validate_flow(candidate, risk_for_flow)
            if violations:
                validation["flow"] = {"source": "deterministic", "violations": violations,
                                      "adjustments": adjustments,
                                      "note": "LLM flow failed validation — deterministic flow used"}
                flow = det["recommendation"]["flow"]
            else:
                validation["flow"] = {"source": "llm", "violations": [], "adjustments": adjustments}
                flow = candidate
        else:
            validation["flow"] = {"source": "deterministic", "violations": [],
                                  "adjustments": [], "note": "LLM supplied no flow"}
            flow = det["recommendation"]["flow"]

    flow_check = _verify_basis(
        llm_out.suggested_agent_flow.basis if (llm_out and llm_out.suggested_agent_flow) else "", corpus
    ) if validation["flow"]["source"] == "llm" else {"verification": "deterministic"}
    items.append({
        "id": "flow", "kind": "flow",
        "title": f"Agent flow ({validation['flow']['source']}, {len(flow.get('nodes', []))} nodes)",
        "detail": {"flow": flow, "source": validation["flow"]["source"]},
        "basis": (llm_out.suggested_agent_flow.basis if (llm_out and llm_out.suggested_agent_flow) else ""),
        **flow_check, "state": "proposed",
    })

    return {
        "engine": engine,
        "status": "ready",
        "model_id": model_id,
        "prompt_version": PROMPT_VERSION if llm_out is not None else None,
        "items": items,
        "validation": validation,
        "raw_output": {
            "deterministic": det,
            "llm": llm_out.model_dump() if llm_out else None,
            "llm_attempts": llm_attempts,
            "summary": llm_out.summary if llm_out else None,
            "missing_information": llm_out.missing_information if llm_out else [],
            "clarifying_questions": llm_out.clarifying_questions if llm_out else [],
        },
        "item_states": {item["id"]: "pending" for item in items},
    }


def _intent_public_json(intent: NormalizedIntent) -> dict:
    """The intent view handed to the LLM — normalized, no envelopes."""
    return {
        "objective": intent.objective,
        "business_function": intent.business_function,
        "target_users": intent.target_users,
        "success_criteria": intent.success_criteria,
        "trigger_type": intent.trigger_type,
        "input_description": intent.input_description,
        "output_description": intent.output_description,
        "output_format": intent.output_format,
        "data_sources": intent.data_sources,
        "data_sensitivity": intent.data_sensitivity,
        "business_rules": intent.business_rules,
        "knowledge_freshness": intent.knowledge_freshness,
        "tools_required": intent.tools_required,
        "mcp_connectors_required": intent.mcp_connectors_required,
        "interaction_style": intent.interaction_style,
        "external_systems": intent.external_systems,
        "declared_risk_tier": intent.risk_tier,
        "human_approval_requirement": intent.human_approval_requirement,
        "write_actions_expected": intent.write_actions_expected,
        "compliance_notes": intent.compliance_notes,
        "deployment_channel": intent.deployment_channel,
        "expected_volume_per_day": intent.expected_volume_per_day,
        "latency_target": intent.latency_target,
        "evidence_requirement": intent.evidence_requirement,
    }
