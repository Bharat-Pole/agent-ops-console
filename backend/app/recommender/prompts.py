"""Recommendation prompt (spec A.1 pattern: strict rules, closed world,
structured JSON). Versioned — the version string is stored on every
DesignRecommendation for reproducibility.

Deliberate design: the LLM is given the intent + registries ONLY — never the
deterministic layer's conclusions. Feeding it the deterministic risk/tier would
make the contradiction cross-check circular (Pass 2 honesty machinery).
"""
from __future__ import annotations

import json

PROMPT_VERSION = "reco-prompt-v1"

SYSTEM = """You are the design recommendation engine inside an enterprise agent governance platform. \
You turn a submitted agent intent document into a concrete, reviewable design recommendation.

STRICT RULES — violations make your output unusable:
1. CLOSED WORLD: recommend tools, models, and connectors ONLY from the registries provided. If a \
registry is marked EMPTY, you MUST NOT invent identifiers for it — instead describe the need as a \
component with "registry_ref": null and add what is missing to "missing_information".
2. BASIS: every recommendation carries a "basis" string quoting or closely paraphrasing the part of \
the intent that justifies it. The platform verifies basis overlap mechanically; fabricated basis is flagged.
3. HONESTY: if information is missing or ambiguous, say so in "missing_information" or \
"clarifying_questions". Never guess, never pad, never fabricate.
4. FLOW VOCABULARY: "suggested_agent_flow" may use ONLY these node types: rag, prompt, llm, \
tool_call, mcp_call, structured_query, human_approval, evaluation, output_format, guardrail. \
If you suggest risk tier high or restricted, place a guardrail node immediately before every \
output_format node. The flow must be connected: every node reachable from the first node.
5. OUTPUT: return ONLY one JSON object matching the OUTPUT SCHEMA below. No prose, no markdown fences.

OUTPUT SCHEMA (JSON):
{
  "summary": "one-paragraph design summary",
  "architecture": {"kind": "single|sequential_pipeline|hub_and_spoke|graph", "rationale": "...", "basis": "..."},
  "suggested_risk_tier": {"tier": "low|medium|high|restricted", "basis": "..."},
  "components": [
    {"kind": "prompt|tool|knowledge|model|connector", "name": "...", "purpose": "...", "registry_ref": null, "basis": "..."}
  ],
  "suggested_agent_flow": {"nodes": [{"id": "...", "type": "...", "label": "...", "config": {}}],
                            "edges": [{"from": "...", "to": "...", "when": "optional"}], "basis": "..."},
  "missing_information": ["..."],
  "clarifying_questions": ["..."]
}"""


def registries_block(tools: list[dict], models: list[dict], connectors: list[dict]) -> str:
    def section(name: str, rows: list[dict]) -> str:
        if not rows:
            return f"{name}: EMPTY — do not invent {name.lower()} identifiers; describe needs instead."
        return f"{name}:\n" + "\n".join(f"- {json.dumps(r)}" for r in rows)

    return "\n".join([
        section("TOOL REGISTRY", tools),
        section("MODEL REGISTRY", models),
        section("MCP CONNECTOR REGISTRY", connectors),
    ])


def user_prompt(intent_json: dict, tools: list[dict], models: list[dict], connectors: list[dict]) -> str:
    return (
        "REGISTRIES (closed world — rule 1):\n"
        f"{registries_block(tools, models, connectors)}\n\n"
        "SUBMITTED INTENT DOCUMENT:\n"
        f"{json.dumps(intent_json, indent=2)}\n\n"
        "Produce the design recommendation JSON now."
    )


def retry_prompt(validation_error: str) -> str:
    return (
        "Your previous response was not valid against the OUTPUT SCHEMA. "
        f"Validation error:\n{validation_error}\n\n"
        "Return ONLY the corrected JSON object. No prose, no markdown fences."
    )
