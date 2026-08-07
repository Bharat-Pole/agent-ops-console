"""LLM-first architecture recommender (Stage 2b, backend).

Given the console's intent plus the deterministic engine's NLU + classification,
ask Gemini to pick ONE of the generatable architecture shapes and justify it.
Structured output via langchain's `.with_structured_output` (the same mechanism
the supervisor template uses). The console re-validates every result with its own
deterministic guardrails (validateArchitecture) — this service is never trusted
blindly, and any failure here degrades to the console's rule-based baseline.
"""
from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from .model_map import MISSING_FALLBACK
from . import secrets as vault

ALLOWED = ["single", "sequential_pipeline", "hub_and_spoke", "graph"]


class NoKeyError(RuntimeError):
    """No Gemini key available — the endpoint maps this to 503 so the console
    falls back to its deterministic baseline."""


class _Reco(BaseModel):
    architecture: Literal["single", "sequential_pipeline", "hub_and_spoke", "graph"]
    rationale: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


DISCRIMINATORS = (
    "single           — one skill, one objective, no decomposition, ≤3 tools.\n"
    "sequential_pipeline — fixed ORDERED stages; each stage's output feeds the next "
    "(\"first … then … finally\").\n"
    "hub_and_spoke    — several INDEPENDENT specialists a coordinator routes to by task type.\n"
    "graph            — retrieval-grounded (retrieve→generate) or explicit conditional "
    "branching/looping over tools that fits none of the above."
)


def _has_key(api_key: str | None, llm_target: str) -> bool:
    if llm_target == "vertex":
        return True  # Vertex uses ADC / GOOGLE_APPLICATION_CREDENTIALS
    resolved, _src = vault.resolve_model_key(None, api_key)
    return bool(resolved or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def _build_model(api_key: str | None, llm_target: str):
    model_id = os.getenv("ARCHITECTURE_MODEL") or MISSING_FALLBACK
    if llm_target == "vertex":
        from langchain_google_vertexai import ChatVertexAI
        return ChatVertexAI(model=model_id, temperature=0.1, max_retries=2)
    from langchain_google_genai import ChatGoogleGenerativeAI
    resolved, _src = vault.resolve_model_key(None, api_key)
    kw = {"google_api_key": resolved} if resolved else {}
    return ChatGoogleGenerativeAI(model=model_id, temperature=0.1, max_retries=2, **kw)


def _prompt(req: dict[str, Any]) -> str:
    intent = req.get("intent") or {}
    nlu = req.get("nlu") or {}
    cls = req.get("classification") or {}
    allowed = req.get("allowed_architectures") or ALLOWED
    fired = [s for s, v in (cls.get("signal_breakdown") or {}).items() if isinstance(v, dict) and v.get("fired")]
    return (
        "You are an agent-architecture selector for an advisory-only agent platform.\n"
        "Choose the single best orchestration architecture for the agent described below.\n\n"
        f"Allowed architectures (choose exactly one of): {', '.join(allowed)}\n"
        f"{DISCRIMINATORS}\n\n"
        "HARD RULES:\n"
        "- Advisory-only: the agent never performs write actions; do not let write needs change the shape.\n"
        f"- If classification.forced is true you MUST pick a multi-agent shape "
        f"(hub_and_spoke or sequential_pipeline), never single.\n\n"
        "AGENT:\n"
        f"- objective: {intent.get('objective', '')}\n"
        f"- audience: {intent.get('intended_audience', '')}\n"
        f"- data_sources: {intent.get('data_sources', [])}\n"
        f"- tools: {intent.get('tools', [])}\n"
        f"- nlu.task_type: {nlu.get('task_type')}, domain: {nlu.get('domain')}, "
        f"systems: {nlu.get('systems', [])}, action_verbs: {nlu.get('action_verbs', [])}\n"
        f"- classification.proposed_tier: {cls.get('proposed_tier')}, forced: {cls.get('forced')}, "
        f"signals_fired: {fired}\n\n"
        "Return the architecture, a 1-3 bullet rationale grounded in the signals above, and your confidence."
    )


def recommend_architecture(req: dict[str, Any], api_key: str | None = None, llm_target: str = "aistudio") -> dict[str, Any]:
    if not _has_key(api_key, llm_target):
        raise NoKeyError("no Gemini key available (set GOOGLE_API_KEY or a GEMINI_DEFAULT vault secret)")

    allowed = req.get("allowed_architectures") or ALLOWED
    model = _build_model(api_key, llm_target)
    out: _Reco = model.with_structured_output(_Reco).invoke(_prompt(req))

    arch = out.architecture if out.architecture in allowed else "single"
    rationale = list(out.rationale)
    # Mirror the hard gate server-side too (defence in depth; the console re-checks).
    if bool((req.get("classification") or {}).get("forced")) and arch == "single":
        arch = "hub_and_spoke"
        rationale.append("Adjusted to multi-agent: classification forced it (S6 / ≥4 tools).")

    # graph_spec is left null on purpose: the console renders the concrete graph
    # deterministically for the chosen kind (guaranteed renderable). The LLM's job
    # is the shape decision + rationale.
    return {
        "architecture": arch,
        "graph_spec": None,
        "rationale": rationale or [f"Recommended {arch}."],
        "confidence": out.confidence,
    }
