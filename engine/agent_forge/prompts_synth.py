"""System-prompt synthesis. The console's system_prompt_ref / safety_instructions
/ citation_rules are URIs (prompts://…, policies://…), not prose, and nothing
resolves them to text. So we COMPOSE the runtime system prompt from the real-text
leaves (persona_role, task_prompt) + a locked advisory-scope reminder, and record
the referenced assets as provenance comments the operator can resolve. The engine
never fabricates the referenced bodies.
"""
from __future__ import annotations

from .ir import PromptIR

ADVISORY_REMINDER = (
    "You operate under an advisory-only scope: you may read, summarize, draft, "
    "recommend, and validate, but you must never send, approve, deploy, update, "
    "create, delete, close, assign, notify, post, or execute. If asked to take a "
    "write action, refuse and offer to draft it for a human to act on."
)


def synthesize_prompt(
    *,
    persona_role: str | None,
    task_prompt: str | None,
    objective: str | None,
    system_prompt_ref: str | None,
    safety_ref: str | None,
    citation_ref: str | None,
    per_sub_agent: dict[str, str] | None = None,
    tool_names: list[str] | None = None,
) -> PromptIR:
    lines: list[str] = []
    if persona_role:
        lines.append(f"You are the {persona_role}.")
    if task_prompt:
        lines.append(task_prompt.strip())
    elif objective:
        lines.append(f"Your objective: {objective.strip()}")
    if tool_names:
        lines.append(
            "You have these tools: " + ", ".join(tool_names) + ". "
            "Call a tool instead of answering from memory whenever it can give fresher "
            "or more specific information — always use a search tool for current events, "
            "dates, scores, standings, prices, or anything that may have changed after "
            "your training data.\n"
            "GROUNDING RULE (critical): tool results are the authoritative, up-to-date "
            "source and OVERRIDE your own prior knowledge and training cutoff. When a "
            "tool returns relevant information, base your answer on it and state it as "
            "fact. Never claim an event has not happened, or give an outdated answer, "
            "when the tool results indicate otherwise — trust the results over your "
            "assumptions about the current date. Briefly cite the source when relevant.\n"
            "TOOL HONESTY: if a tool returns an error, 'unavailable', 'No results.', or "
            "a [stub:…] placeholder, tell the user plainly that the tool failed or is "
            "not connected — never present an answer from memory as if it came from the "
            "tool, and never claim you used or didn't use a tool contrary to what "
            "actually happened in this conversation."
        )
    lines.append(ADVISORY_REMINDER)
    system_prompt = "\n\n".join(lines).strip()

    prov: list[str] = []
    if system_prompt_ref:
        prov.append(
            f"system_prompt_ref: {system_prompt_ref} — resolve this governed prompt "
            f"and prepend/merge its body before production."
        )
    if safety_ref:
        prov.append(f"safety_instructions: {safety_ref} — resolve and enforce.")
    if citation_ref:
        prov.append(f"citation_rules: {citation_ref} — resolve; cite kb:// sources per this policy.")

    return PromptIR(
        system_prompt=system_prompt,
        provenance_comments=prov,
        per_sub_agent=dict(per_sub_agent or {}),
    )
